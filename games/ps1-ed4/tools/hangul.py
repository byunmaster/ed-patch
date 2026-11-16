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
HALF_PATH = os.path.join(
    common.ROOT, "halfwidth_map.json"
)  # 반각(6px) 글자 자리 — 훅(`halfwidth.py`)이 쓴다
SPACE_CODE = 610  # 공백 = 빈 글리프(반각으로 친다)


def load_half():
    """{글자: 코드} — 반각 자리. 한글 자리와 겹치면 실패."""
    with open(HALF_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    return dict(zip(doc["chars"], doc["codes"], strict=True))


def half_codes():
    """반각으로 그릴 글리프 코드(공백 포함) — 훅의 목록."""
    return [SPACE_CODE, *load_half().values()]


def load():
    """{글자: 코드} — 자리 정본(한글 + 반각). 폰트 밖·중복 코드면 실패."""
    with open(MAP_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    half = load_half()
    chars, codes = doc["chars"] + list(half), doc["codes"] + list(half.values())
    if len(chars) != len(codes) or len(set(codes)) != len(codes) or len(set(chars)) != len(chars):
        raise ValueError("글리프 자리 정본이 어긋났다(길이·중복)")
    if any(not 0 <= c < font.font_slots() for c in codes):
        raise ValueError("글리프 자리 정본에 폰트 밖 코드가 있다")
    return dict(zip(chars, codes, strict=True))


# 번역 문안이 쓰는 글자 → 원본 코드표의 같은 글리프(규칙 1-2: 물결표는 전각 `～`)
ALIAS = {"～": "〜", "·": "・"}


def reverse_charmap():
    rev = {ch: c for c, ch in textenc.charmap().items()}
    for ch, orig in ALIAS.items():
        rev.setdefault(ch, rev[orig])
    return rev


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
    half = load_half()
    for ch in sorted(set(chars)):
        if ch in half:
            font.write_glyph(exe, table[ch], font.half_glyph(ch))
            n += 1
        elif ch in font.SPLIT:  # 한 글자를 두 칸에 반씩 나눈 글리프(필드 메뉴 「시스템」)
            font.write_glyph(exe, table[ch], font.split_glyph(ch))
            n += 1
        elif ch in table and not (0xE000 <= ord(ch) < 0xF900):  # 사설 영역 = 조사 표지 — 글리프가 없다(훅이 갈아 끼운다)
            font.write_glyph(exe, table[ch], font.hangul_glyph(ch))
            n += 1
    return n
