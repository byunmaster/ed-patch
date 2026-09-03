"""PS1 ED3·ED4 의 자체 문자 코드표 — 읽기/쓰기의 **유일한 통로**.

이 게임의 대본은 SJIS 가 아니라 **16비트 자체 코드**다(2026-09-03 실측). 표의 정체는
「JIS X 0208 순서에서 **그 게임이 실제로 쓰는 글자만** 남긴 목록」으로 보인다 —
근거는 히라가나 블록이 JIS 4구 순서 그대로인데 **ゎゐゑ 만 빠져 있고**(ED3),
ED4 는 거기서 하나가 더 빠져 뒤쪽이 1씩 밀린다는 것이다.

⚠ **여기 있는 카나 블록은 실측이고, 한자는 정본(charmap_<disc>.json)에서 읽는다.**
   정본은 `solve_charmap.py` 가 만들고 사람이 확인해 커밋한다 — 빌드는 정본만 읽는다
   (결정성: 제안과 정본을 가른다, patcher-checklist 3).
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)

# JIS X 0208 4구(히라가나 83) · 5구(가타카나 86) 전량 — 여기서 「안 쓰는 글자」를 뺀다.
JIS_HIRA = "ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん"
JIS_KATA = "ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶ"

# 각 디스크가 **빼먹은** 글자 (실측으로 채운다 — 늘어나면 여기만 고친다)
# 각 디스크가 **빼먹은** 글자. 값은 가정이 아니라 **닻에서 유도**한 것이다 —
# 닻(높은 확신으로 배운 코드)의 「코드 = JIS위치 − 앞쪽 탈락 수」가 전부 성립해야 한다.
# `check_kana_block.py` 가 그 셈을 다시 세운다(상수를 코드로 검산한다, 체크리스트 10).
DROPPED = {
    # ED3 — 히라가나는 문장으로(「なんで」「いうわけだ」「ごちそうを」),
    #       가타카나는 닻 ジ23·チ32·ツ35·テ37·リ73·ロ76·ワ78·ン82 로 유도했다.
    #       🔴 **ヴ 는 뒤늦게 찾았다**(2026-09-03, 글리프 대조) — ン 뒤라 닻이 하나도
    #       안 걸려 여섯 달 뒤에도 안 보였을 자리다. 빠뜨린 동안 0xDD~0xDF 가 한 칸씩
    #       밀려 **哀 가 「ヶ」로 읽혔다.** 닻 없는 꼬리는 닻으로 못 잡는다 —
    #       그래서 `solve_charmap_glyph.py` 가 글리프로 다시 센다.
    "ed3": {"hira": "ゎゐゑ", "kata": "ヂヮヰヱヲヴ"},
    # ED4 — ED3 과 **다르다**. 글리프 대조(같은 활자 1,595자 완전일치)로 유도했다:
    #   ぢ 를 더 빼고(히라 79), 가타카나는 ヲ·ヴ 를 **남긴다**(가타 82).
    #   ⇒ 카나 뒤 첫 한자가 ED3 0xDF · ED4 0xE0 으로 한 칸 어긋난다.
    "ed4": {"hira": "ぢゎゐゑ", "kata": "ヂヮヰヱ"},
}

KANA_BASE = 0x3F  # 히라가나 첫 코드 (양 디스크 공통, 실측)


def kana_map(disc):
    """{코드: 글자} — **히라가나 블록만**. 나머지는 전부 정본(charmap)에서 온다.

    ⚠ 「무엇이 빠졌나」를 **눈대중으로 정하지 않는다**: 「무엇이 빠졌나」를 손으로 가정했다가 이름이
      통째로 어긋났다(2026-09-03 실측 — ジュリオ 가 「ジヤラオ」로 읽혔다). 빠진 글자는
      디스크마다 다르고 눈으로 안 보인다. **가정하지 말고 해독기가 배우게 한다.**
      히라가나만 남긴 것은 그 블록만 문장을 읽어 직접 검증했기 때문이다
      (「なんで」·「いうわけだ」·「ごちそうを」).
    """
    d = DROPPED[disc]
    kana = [c for c in JIS_HIRA if c not in d["hira"]] + [c for c in JIS_KATA if c not in d["kata"]]
    return {KANA_BASE + i: c for i, c in enumerate(kana)}


# 제어 코드 — 화면에 안 나가고 조판을 정한다 (실측: 0x01 개행 · 0x02 문장 끝)
CONTROL = {0x00: "", 0x01: "\n", 0x02: "。", 0x03: "・"}
TERM = 0xFFFF  # 블록 구분


def kuten_char(ku, ten):
    """JIS 구·점 → 글자. 없으면 None.

    ⚠ 이 변환을 손으로 두 번 쓰지 않는다 — 한 번 틀렸다(2026-09-03: 첫 한자가 亜 가 아니라
      엉뚱한 글자로 나와, 순서 보간과 채택 창이 통째로 헛돌았다). 통로는 여기 하나다.
    """
    if not (1 <= ku <= 94 and 1 <= ten <= 94):
        return None
    s1 = (ku + 257) // 2 if ku <= 62 else (ku + 385) // 2
    s2 = ten + 63 + (1 if ten >= 64 else 0) if ku % 2 else ten + 158
    try:
        return bytes((s1, s2)).decode("cp932")
    except UnicodeDecodeError:
        return None


_ORDER = None


def jis_order():
    """JIS X 0208 전 글자를 구·점 순서로 (= SJIS 바이트 순서와 같은 순서)."""
    global _ORDER
    if _ORDER is None:
        _ORDER = [c for ku in range(1, 95) for ten in range(1, 95) if (c := kuten_char(ku, ten))]
    return _ORDER


def jis_index():
    """{글자: 순서 색인}"""
    return {ch: i for i, ch in enumerate(jis_order())}


def charmap_path(disc):
    return os.path.join(GAME, f"charmap_{disc}.json")


_cache = {}


def charmap(disc):
    """{코드: 글자} 정본 — 카나(계산) + 한자·기호(커밋된 정본)."""
    if disc in _cache:
        return _cache[disc]
    m = kana_map(disc)
    p = charmap_path(disc)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for k, v in doc["map"].items():
            m[int(k, 16)] = v
    _cache[disc] = m
    return m


def decode(codes, disc, unknown="�{:03x}"):
    """코드열 → 문자열. 모르는 코드는 `unknown` 서식으로 남긴다(조용히 안 지운다)."""
    m = charmap(disc)
    out = []
    for w in codes:
        if w == TERM:
            break
        if w in CONTROL:
            out.append(CONTROL[w])
        elif w in m:
            out.append(m[w])
        else:
            out.append(unknown.format(w))
    return "".join(out)
