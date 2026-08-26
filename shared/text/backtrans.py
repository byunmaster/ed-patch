"""옮긴 문안을 **원어로 되돌려** 원문과 맞추는 공용 엔진 — 뜻이 미끄러진 자리를 추린다.

게임·트랙과 무관하다 — `(키, 원문, 우리 문안)` 목록을 넣으면 **어긋난 순으로** 돌려준다.
게임별 어댑터가 코퍼스 수집(어디서 블록을 긁는가)과 보고(무엇을 보여 주는가)를 맡는다.
`spellcheck.py` 와 같은 경계다.

🔴 **오역 중에 제일 조용한 것이 「그럴듯한 딴소리」다.** 빠뜨림은 숫자·고유명사로 잡히지만,
뜻이 통째로 미끄러진 자리는 문장이 매끄러워서 아무 검사도 안 운다. 44만 자를 사람이 다시
읽을 수는 없으니 **의심 자리만 추린다.**

기계번역이 이 일에는 잘 맞는다 — 문체도 길이도 필요 없고 **뜻만 되돌리면** 되기 때문이다.
(초벌에는 반대로 못 쓴다: 예산·조판·말투 같은 제약을 줄 수 없어 되던지기 루프가 안 돈다.)

⚠ **점수는 절대값이 아니라 순위로 읽는다.** 역번역이 원문과 같을 수는 없다 — 표기가
흔들리고, 옮기는 쪽에서 일부러 바꾼 자리(사투리·조사 회피·길이 줄이기)도 점수를 깎는다.
**낮은 것부터 사람이 본다**가 이 엔진의 전부다.

⚠ **나가는 것은 우리 문안뿐이다** — 원문은 보내지 않는다(대조는 이쪽에서 한다).
저작물을 바깥 서비스로 보내지 않기 위한 경계이므로 어댑터도 이 순서를 지킨다.
"""

import difflib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# 백엔드는 갈아끼울 수 있다 — 지금은 DeepL API Free(월 50만 자).
DEEPL = {
    "url": "https://api-free.deepl.com/v2/translate",
    "auth": "DeepL-Auth-Key {key}",
    "batch": 40,  # 한 번에 여러 문장을 받는다 — 호출 수를 줄인다
}

_CTRL = re.compile(r"[\n\f\r\t　]+")
_PUNCT = re.compile(r"[。、！？…・.,!?\s]+")
_RETRY = (0, 5, 15)
_SOFT = frozenset({429, 456, 500, 502, 503})


def flatten(s):
    """제어·전각공백을 지우고 한 줄로 — 번역기에 넣을 꼴."""
    return _CTRL.sub(" ", s).strip()


def norm(s):
    """대조용 정규화 — 문장부호와 공백은 뺀다(표기 흔들림에 점수가 휘둘리지 않게)."""
    return _PUNCT.sub("", s)


# 🔴 **짧은 문장은 점수가 못 미덥다.** 문자 단위 대조라 표기가 갈리면 곧장 0 이 된다 —
#   `かんぱ〜い！` → 「건배〜!」 → `乾杯～！` 는 뜻이 정확한데 **0.00** 이었다(가나 vs 한자).
#   긴 문장은 나머지 글자가 받쳐 주지만 짧으면 표기 하나가 전부를 흔든다.
#   실측 기준: `乾杯～`(3자)는 못 믿고 `明日の準備はできてる`(10자)는 믿을 만하다.
SHORT = 8


def similarity(src, back):
    """원문과 역번역의 닮은 정도 `0.0~1.0`."""
    return difflib.SequenceMatcher(None, norm(src), norm(back)).ratio()


def is_short(src, back):
    """점수를 못 믿을 만큼 짧은가 — 보고에서 갈라 보여 주라는 표시."""
    return min(len(norm(src)), len(norm(back))) < SHORT


def load_cache(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def translate(texts, key, src_lang, dst_lang, backend=DEEPL, timeout=120, opener=None):
    """`src_lang → dst_lang`. 한 번에 여러 문장. 실패하면 `RuntimeError`.

    `opener` 는 시험용 갈고리다 — 넣으면 그것으로 부른다(망 없이 테스트).
    """
    body = [("target_lang", dst_lang), ("source_lang", src_lang)] + [("text", t) for t in texts]
    data = urllib.parse.urlencode(body).encode()
    req = urllib.request.Request(
        backend["url"], data=data, headers={"Authorization": backend["auth"].format(key=key)}
    )
    call = opener or (lambda r: urllib.request.urlopen(r, timeout=timeout))
    last = None
    for wait in _RETRY:
        if wait:
            time.sleep(wait)
        try:
            with call(req) as r:
                return [x["text"] for x in json.loads(r.read())["translations"]]
        except urllib.error.HTTPError as e:
            if e.code not in _SOFT:
                raise RuntimeError(f"HTTP {e.code}") from None
            last = e.code
    raise RuntimeError(f"바깥 서비스가 계속 거절한다(HTTP {last}) — 한도이거나 열쇠가 잘못됐다")


def fetch(pairs, cache, key, src_lang, dst_lang, backend=DEEPL, on_save=None, **kw):
    """캐시에 없는 문안만 되돌려 채운다. `pairs` = `[(키, 원문, 우리 문안)]`.

    ⚠ 캐시는 **우리 문안**을 열쇠로 삼는다 — 문안을 고치면 저절로 다시 돈다.
    """
    todo = [p[2] for p in pairs if p[2] not in cache]
    todo = list(dict.fromkeys(todo))  # 같은 문안이 여러 자리에 있다
    n = backend["batch"]
    for s in range(0, len(todo), n):
        chunk = todo[s : s + n]
        for text, back in zip(
            chunk, translate(chunk, key, src_lang, dst_lang, backend, **kw), strict=False
        ):
            cache[text] = back
        if on_save:
            on_save(min(s + n, len(todo)), len(todo))
    return cache


def rank(pairs, cache, drop_short=False):
    """`[(점수, 키, 원문, 우리 문안, 되돌린 것)]` — **어긋난 순**. 캐시에 없는 것은 뺀다.

    `drop_short` 면 **짧아서 점수를 못 믿는 것**을 뺀다(`is_short`). 기본은 남긴다 —
    짧은 자리에도 오역은 있고, 무엇을 뺐는지 부르는 쪽이 알아야 한다.
    """
    out = []
    for k, src, ko in pairs:
        back = cache.get(ko)
        if back is None or (drop_short and is_short(src, back)):
            continue
        out.append((similarity(src, back), k, src, ko, back))
    out.sort(key=lambda x: x[0])
    return out
