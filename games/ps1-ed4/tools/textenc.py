"""ED4 의 자체 문자 코드표 — 읽기의 **유일한 통로**(ED3 의 `textenc` 에서 ED4 몫만 옮겼다).

대본은 SJIS 가 아니라 **16비트 자체 코드**다. 표는 「JIS X 0208 순서에서 그 게임이 안 쓰는 글자를 뺀 목록」이고,
카나 블록은 계산, 한자·기호는 정본(`charmap.json`)에서 읽는다 — 빌드는 정본만 읽는다(결정성).

ED4 가 뺀 글자(글리프 대조 — 같은 활자 1,595자 완전일치로 유도, ED3 와 **다르다**):
  히라가나 `ぢゎゐゑ` · 가타카나 `ヂヮヰヱ`  ⇒ 카나 뒤 첫 한자가 ED3 0xDF · ED4 0xE0.
🔴 「무엇이 빠졌나」를 눈대중으로 정하지 않는다 — 닻·글리프로 유도한 값이고 `tests/test_textenc.py` 가 지킨다.
"""

import json
import os

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JIS_HIRA = "ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん"  # copyright:ok JIS X 0208 히라가나 문자표(문장 아님)
JIS_KATA = "ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶ"  # copyright:ok JIS X 0208 가타카나 문자표(문장 아님)
DROPPED = {"hira": "ぢゎゐゑ", "kata": "ヂヮヰヱ"}
KANA_BASE = 0x3F  # 히라가나 첫 코드

# 제어 코드 — 화면에 안 나가고 조판을 정한다. 🔴 0x01 은 줄바꿈이 아니라 「、」다(ED3 에서 글리프로 확정 — 한 조각 = 한 줄).
CONTROL = {0x00: "", 0x01: "、", 0x02: "。", 0x03: "・"}
TERM = 0xFFFF  # 블록 구분


def kana_map():
    """{코드: 글자} — **카나 블록만**(계산). 나머지는 정본(charmap)에서 온다."""
    kana = [c for c in JIS_HIRA if c not in DROPPED["hira"]] + [
        c for c in JIS_KATA if c not in DROPPED["kata"]
    ]
    return {KANA_BASE + i: c for i, c in enumerate(kana)}


def charmap_path():
    return os.path.join(GAME, "charmap.json")


_cache = {}


def charmap():
    """{코드: 글자} 정본 — 카나(계산) + 한자·기호(커밋된 정본)."""
    if "m" not in _cache:
        m = kana_map()
        with open(charmap_path(), encoding="utf-8") as f:
            doc = json.load(f)
        for k, v in doc["map"].items():
            m[int(k, 16)] = v
        _cache["m"] = m
    return _cache["m"]


def decode(codes, unknown="�{:03x}"):
    """코드열 → 문자열. 모르는 코드는 `unknown` 서식으로 남긴다(조용히 안 지운다)."""
    m = charmap()
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
