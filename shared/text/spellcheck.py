"""정발(한국어) 문안을 외부 맞춤법 검사기에 돌려 **치환 후보**를 뽑는 공용 엔진.

게임·트랙과 무관하다 — 문장 목록을 넣으면 치환쌍을 분류해 돌려준다. 게임별 어댑터가
코퍼스 수집(어디서 문장을 긁는가)과 반영(어느 JSON 의 `replace` 에 넣는가)을 맡는다.

**어투·말투는 보존하고 띄어쓰기·오타만 고친다** — 그 경계를 `공백만 차이` 로 긋는다.
검사기는 문체까지 표준어로 밀어버리는데(engram 실측 2026-08-02), 다행히 그 오작동이
전부 글자를 바꾸는 쪽에 몰린다:

    A급 (공백만)  무찌를수→무찌를 수 · 네녀석들→네 녀석들 · 감사 합니다→감사합니다
    B급 (글자)    뵈는 듯 하옵니다→뵈는 듯합니다(고어체 소멸) · 빨랑→빨리(구어체 소멸)

그래서 A급만 일괄 반영 후보로 올리고 B급은 사람이 고른다. 그 밖에 걸러야 할 것 둘:

- **주입 자리 오해** — 런타임 주입 코드를 지운 자리 주변에서 조사를 지어낸다
  (`` `1 무찌를 `` → `1을 무찌를`). `inject` 문장은 공백만 달라도 A급에서 뺀다.
- **부호 옆 공백** — 정발은 `알았잖아 !!` 처럼 띄우고 검사기는 붙인다. 조판이 이미
  다루므로 이 차이만 있는 제안은 버린다(노이즈의 대부분).

⚠ 치환은 보통 **전 문안 리터럴 치환**으로 쓰인다. 낱말 경계까지 넓힌 쌍만 내보내고,
문맥에 따라 갈리는 짧은 낱말(`한번`)은 A급에서 뺀다.
⚠ 원문을 외부 서비스로 보낸다 — 저작물이면 유저 승인 하에만 쓸 것.
"""

import concurrent.futures as cf
import difflib
import json
import re
import threading
import time
import urllib.error
import urllib.request

# ── 검사기 백엔드 ────────────────────────────────────────────────────
ENGRAM = {
    "url": "https://api.engram.us/trial/v9/spell",
    "headers": {
        "content-type": "application/json",
        "origin": "https://www.engram.us",
        "referer": "https://www.engram.us/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
    },
}

# 부호에 **붙은** 공백 — 앞(`멈춰 !!`)이든 뒤(`...더는` → `... 더는`)든 조판 관할이라
# 검사기 제안을 받을 이유가 없다. 비교용으로 양쪽에서 지워 차이를 무효화한다.
PUNCT_WS = re.compile(r"\s+(?=[.,!?…])|(?<=[.…])\s+")

# 붙임/띄움이 **문맥에 따라 갈리는** 낱말 — 전역 리터럴 치환에 올리면 안 된다.
#   한번 더(=한 번) vs 한번 해볼까(=한번) · 안 되다 vs 안되다 …
CONTEXT_SENSITIVE = {"한번", "한 번", "안되", "안 되", "못하", "못 하", "잘못", "잘 못"}
MIN_LEN = 3  # 원문 쪽 최소 길이 — 짧은 쌍은 사정거리가 넓다

# 보조용언 어간 — **띄어 씀이 원칙**(붙여 씀도 허용)이라 검사기가 곧잘 붙여버린다.
# 원칙 쪽을 지키기로 했으므로 `듯 하오`→`듯하오` · `척 하는`→`척하는` · `알려 줄`→`알려줄`
# 같은 **붙이는** 제안은 A급에서 뺀다.
#
# ⚠ 의존명사 + 조사와 헷갈리면 안 된다 — `것 입니다`(서술격조사) · `수 밖에`(조사) ·
# `것 뿐이니`(조사)는 붙이는 게 맞다. 뒤 어절의 첫 글자로 정확히 갈린다.
#
# ⚠ 한글은 음절이 한 코드포인트라 `"줄".startswith("주")` 가 거짓이다 — 어간 `주` 에
# 어미가 붙으면 종성만 채워진다(주→줄/준/줍). **종성을 뺀 초성·중성**으로 맞춘다.
AUX_STEMS = "하주보두놓버싶대치오"


def _base(c):
    """한글 음절 → 종성을 뗀 형태. 그 밖의 글자는 그대로."""
    return chr(0xAC00 + (ord(c) - 0xAC00) // 28 * 28) if "가" <= c <= "힣" else c


def nospace(s):
    return re.sub(r"\s+", "", s)


def canon(s):
    """부호 옆 공백·중복 공백을 지운 비교용 형태."""
    return re.sub(r"\s+", " ", PUNCT_WS.sub("", s)).strip()


def call(text, backend=ENGRAM, tone="proof", retry=3, timeout=90):
    body = json.dumps(
        {
            "text": text,
            "session_id": "888002f5-9a41-4087-acba-581fc9b6d8d6",
            "source_lang": "ko",
            "tone": tone,
        }
    ).encode()
    req = urllib.request.Request(backend["url"], data=body, headers=backend["headers"])
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f).get("result", "")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if i == retry - 1:
                raise
            print(f"    재시도 {i + 1}/{retry - 1} ({type(e).__name__})")
            time.sleep(3 * (i + 1))
    return ""


def chunks(sentences, size):
    """문장 목록 → 요청 단위. **문장 경계로만** 자른다(줄 대응이 깨지면 안 된다)."""
    out, cur, n = [], [], 0
    for s in sentences:
        if cur and n + len(s) + 1 > size:
            out.append(cur)
            cur, n = [], 0
        cur.append(s)
        n += len(s) + 1
    if cur:
        out.append(cur)
    return out


def fetch(parts, cache, jobs=4, on_save=None, backend=ENGRAM):
    """캐시에 없는 청크만 병렬로 채운다. 청크끼리 독립이라 순서 의존이 없다."""
    todo = [p for p in parts if "\n".join(p) not in cache]
    if not todo:
        return 0
    done, lock = [0], threading.Lock()

    def work(part):
        src = "\n".join(part)
        res = call(src, backend)
        with lock:
            cache[src] = res
            done[0] += 1
            if done[0] % 10 == 0 or done[0] == len(todo):
                if on_save:
                    on_save(cache)
                print(f"    {done[0]}/{len(todo)}")

    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(work, todo))
    if on_save:
        on_save(cache)
    return len(todo)


def min_pairs(a, b):
    """원문 a → 제안 b 의 **낱말 경계까지 넓힌** 최소 치환쌍 목록.

    조각만 뽑으면 전역 치환에서 엉뚱한 데 걸린다 — 어절 통째로 잡아야 안전하다."""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        while i1 > 0 and not a[i1 - 1].isspace():
            i1 -= 1
            j1 -= 1
        while i2 < len(a) and not a[i2].isspace():
            i2 += 1
            j2 += 1
        if j1 < 0 or j2 > len(b):
            return [(a, b)]  # 경계 확장이 어긋나면 문장 통째로
        x, y = a[i1:i2].strip(), b[j1:j2].strip()
        if x and y and x != y:
            out.append((x, y))
    return out


def collate(parts, cache, meta):
    """캐시 → (문장별 제안, 치환쌍 집계, 줄 대응이 깨진 청크 수).

    meta: {문장: {"n": 등장 횟수, "inject": bool}} — 게임 어댑터가 준다."""
    changed, skewed, pairs = [], 0, {}
    for part in parts:
        src = "\n".join(part)
        if src not in cache:
            continue
        got = [x.strip() for x in cache[src].split("\n")]
        if len(got) != len(part):  # 줄 수가 어긋나면 그 청크는 대응이 깨진다
            skewed += 1
            continue
        for a, b in zip(part, got, strict=True):
            if not b or canon(a) == canon(b):
                continue  # 부호 공백만 다른 것 = 조판이 이미 처리
            m = meta.get(a, {"n": 1, "inject": False})
            changed.append((a, b, m))
            for x, y in min_pairs(a, b):
                p = pairs.setdefault((x, y), {"n": 0, "inject": False, "ex": a})
                p["n"] += m["n"]
                p["inject"] |= m["inject"]
    return changed, pairs, skewed


def joins_aux(x, y):
    """`x` 의 어절 경계를 없애 `y` 를 만드는데, 붙는 뒤 어절이 보조용언인가."""
    if len(y.split()) >= len(x.split()):
        return False
    t = x.split()
    ny = nospace(y)
    return any(
        t[i] + t[i + 1] in ny and t[i + 1] and _base(t[i + 1][0]) in AUX_STEMS
        for i in range(len(t) - 1)
    )


def classify(pairs, known=()):
    """치환쌍 → (A급 자동 채택 후보, B급 수동 검토, 부호 공백이라 버린 수)."""
    known = {tuple(p) for p in known}
    auto, manual, dropped = [], [], 0
    for (x, y), v in sorted(pairs.items(), key=lambda kv: -kv[1]["n"]):
        if (x, y) in known:
            continue
        if canon(x) == canon(y):  # 부호 옆 공백만 다름 = 조판 관할
            dropped += 1
            continue
        safe = (
            nospace(x) == nospace(y)  # 글자가 그대로 = 문체 보존
            and not v["inject"]  # 주입 자리 주변은 제안이 지어낸 것일 수 있다
            and len(nospace(x)) >= MIN_LEN
            and nospace(x) not in CONTEXT_SENSITIVE
            and not joins_aux(x, y)  # 보조용언은 띄어 씀이 원칙
        )
        (auto if safe else manual).append((x, y, v))
    return auto, manual, dropped


def report(title, n_sent, changed, auto, manual, dropped, skewed):
    """검토용 마크다운. ⚠ 원문이 실리므로 저작물이면 gitignore 아래에만 쓸 것."""

    def table(rows):
        out = ["| 빈도 | 원문 | 제안 | 용례 |", "| ---: | --- | --- | --- |"]
        for x, y, v in rows:
            ex = v["ex"][:44].replace("|", "\\|")
            out.append(f"| {v['n']} | `{x}` | `{y}` | {'⚠주입 ' if v['inject'] else ''}{ex} |")
        return out

    md = [
        f"# {title}",
        "",
        "⚠ 원문이 실린다 — **커밋 금지**. `shared/text/spellcheck.py` 생성물.",
        "",
        f"- 검사 문장 {n_sent}종 · 제안 있음 **{len(changed)}**",
        f"- **A급(공백만·자동 채택 후보) {len(auto)}** · B급(글자 변경·수동) {len(manual)}"
        f" · 부호 공백이라 버림 {dropped}",
    ]
    if skewed:
        md.append(f"- ⚠ 줄 대응이 깨진 청크 {skewed}개 — 재검사 필요")
    md += [
        "",
        "## A. 공백만 차이 — 자동 채택 후보",
        "",
        "글자를 안 바꾸므로 **어투·말투가 보존된다**.",
        "",
        *table(auto),
        "",
        "## B. 글자 변경 — 수동 검토",
        "",
        "⚠ **문체를 미는 제안이 섞여 있다**(`듯 하옵니다`→`듯합니다`, `빨랑`→`빨리`). "
        "정발 어투는 보존 대상이니 진짜 오타만 골라 손으로 넣는다. "
        "`⚠주입` 은 런타임 주입 자리를 지운 문장이라 제안이 지어낸 것일 수 있다.",
        "",
        *table(manual),
        "",
        "## C. 문장 단위 제안 (전체)",
        "",
    ]
    for a, b, m in changed:
        md.append(f"- {'⚠주입 ' if m['inject'] else ''}×{m['n']}")
        md.append(f"  - 원: {a}")
        md.append(f"  - 안: {b}")
    return "\n".join(md)


def merge_replace(path, auto):
    """A급 치환쌍을 `{"replace": [[a, b], …]}` 형태의 JSON 에 병합한다.

    ⚠ 긴 쪽부터 걸리도록 길이 내림차순으로 정렬한다 — 짧은 쌍이 먼저 걸려 긴 쌍을
    영영 못 만나는 걸 막는다."""
    doc = json.load(open(path, encoding="utf-8"))
    rep = doc.setdefault("replace", [])
    have = {tuple(p) for p in rep}
    add = [[x, y] for x, y, _ in auto if (x, y) not in have]
    rep.extend(add)
    rep.sort(key=lambda p: -len(p[0]))
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(path, "a", encoding="utf-8").write("\n")
    return add
