"""글리프 자리 정본(`hangul_map.json`) 과 한글 인코딩 — **글자 → 코드**의 통로.

정본은 글자 → 글리프 코드(원본이 안 쓰는 자리를 한글이 차지한다). 🔴 파생물이 아니라 정본이다 — 배포 뒤에는 못 옮긴다.
ED3 의 같은 파일(`hangul_map_ed4.json`)에서 옮겼다(배정 58자). ED4 번역이 시작되면 이 파일이 ED4 의 정본이다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import textenc

MAP_PATH = os.path.join(common.ROOT, "hangul_map.json")


def load():
    """{글자: 코드} — 자리 정본. 폰트 밖·중복 코드면 실패."""
    with open(MAP_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    chars, codes = doc["chars"], doc["codes"]
    if len(chars) != len(codes) or len(set(codes)) != len(codes) or len(set(chars)) != len(chars):
        raise ValueError("글리프 자리 정본이 어긋났다(길이·중복)")
    if any(not 0 <= c < font.font_slots() for c in codes):
        raise ValueError("글리프 자리 정본에 폰트 밖 코드가 있다")
    return dict(zip(chars, codes, strict=True))


def reverse_charmap():
    return {ch: c for c, ch in textenc.charmap().items()}


def encode(text, table=None):
    """문자열 → 코드열. 원본이 아는 글자(카나·한자·전각 부호)는 원본 코드, 한글은 자리 정본.

    🔴 **모르는 글자는 조용히 빼지 않는다** — `KeyError`(화면에서 그 글자만 사라지는 사고를 막는다).
    """
    table = table if table is not None else load()
    rev = reverse_charmap()
    out = []
    for ch in text:
        if ch in table:
            out.append(table[ch])
        elif ch in rev:
            out.append(rev[ch])
        else:
            raise KeyError(ch)
    return out


def bake(exe, table, chars):
    """`chars` 의 글리프를 실행파일 버퍼에 굽는다 — 쓰는 글자만(안 쓰는 자리는 원본 그대로, 무변경 구간을 넓게 지킨다)."""
    n = 0
    for ch in sorted(set(chars)):
        if ch in table:
            font.write_glyph(exe, table[ch], font.hangul_glyph(ch))
            n += 1
    return n
