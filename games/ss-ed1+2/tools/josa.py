"""동적 조사 — 병기(`은(는)`)를 앞 음절의 받침으로 하나로 접는다.

빌드 시점엔 앞말을 모른다(`%s` 가 런타임 이름이다). 그래서 정본은 병기로 두고,
**표시 직전에** 버퍼를 한 번 훑어 접는다 — PS1 과 같은 설계
(`ps1-ed1+2/tools/patch_josa_hook.py`). 다른 건 CPU(SH-2)와 슬롯 배치뿐이다.

이 모듈이 내는 것 둘:
  1. **받침 표** — 우리 슬롯 SJIS 코드 → 1바이트(0/1). 기계어 루틴이 그대로 읽는다.
  2. **파이썬 시뮬레이터** `fix_buffer` — 기계어와 **같은 의미**. 회귀 테스트의 기준이고,
     기계어를 고칠 때마다 여기에 먼저 맞춘다.

⚠ 표는 **코드 구간 하나**를 덮는다(정본에서 유도 — 지금 0x88A0~0x8C5F). 슬롯 인덱스가 불연속이라
  인덱스로 잡으면 표가 4배가 된다 — 코드로 잡는 게 싸다.
🔴 **비트맵이 아니라 바이트 표다.** SH-2 엔 **가변 시프트가 없어**(`shld` 는 SH-3+)
   `표[i>>3] >> (i&7)` 을 못 한다. 1바이트/코드면 `mov.b @(r0,rTab),r1` 한 줄이다.
   958B 를 더 쓰지만 놓을 자리가 2,560B 라 아깝지 않다 — **명령 수가 공간보다 비싸다.**
⚠ 배정 안 된 코드(원본 한자)는 0(받침 없음)이 된다. 병기는 **우리 이름 뒤에만** 오므로
  거기 걸릴 일이 없고, 걸려도 무받침 쪽을 고를 뿐이라 조용히 안 깨진다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import common
import font
from text.josa import batchim

HMAP = os.path.join(common.GAME_DIR, "hangul_map_11kanji.json")

# 🔴 **구간을 상수로 박지 않는다** — 슬롯 정본에서 유도한다. 새 글자 하나가 늘면 코드가
#    구간 밖으로 나가는데(실측: `근` 이 0x8C5F 로 붙어 0x8C5D 상한을 넘겼다), 상수로 두면
#    그때마다 손으로 고쳐야 하고 **안 고치면 그 글자만 조용히 받침 판정을 못 받는다.**
_SPAN = None  # (lo, hi) — 처음 부를 때 정본에서 잰다


def code_span():
    global _SPAN
    if _SPAN is None:
        v = slot_codes().values()
        _SPAN = (min(v), max(v))
        assert _SPAN[1] - _SPAN[0] < 0x2000, f"코드 구간이 너무 넓다: {_SPAN}"
    return _SPAN


PAREN_L, PAREN_R = 0x28, 0x29  # 반각 괄호 — 병기는 `[조사A]([조사B])`
JOSA_PAIRS = (("은", "는"), ("이", "가"), ("을", "를"))


def slot_codes():
    """`{글자: SJIS 코드(int)}` — 커밋된 슬롯 정본에서."""
    with open(HMAP, encoding="utf-8") as f:
        m = json.load(f)["syllables"]
    return {ch: int.from_bytes(font.sjis_of_index(i), "big") for ch, i in m.items()}


def build_table(codes=None):
    """받침 표 — `표[code - lo]` 가 0/1. 기계어가 `mov.b @(r0,rTab)` 로 한 번에 읽는다."""
    codes = codes or slot_codes()
    lo, hi = code_span()
    tab = bytearray(hi - lo + 1)
    for ch, code in codes.items():
        assert lo <= code <= hi, f"{ch!r} 코드 0x{code:04X} 가 표 밖이다"
        if batchim(ch):
            tab[code - lo] = 1
    return bytes(tab)


def pairs(codes=None):
    """`[(조사A 코드, 조사B 코드)]` — 기계어가 그대로 비교한다."""
    codes = codes or slot_codes()
    return [(codes[a], codes[b]) for a, b in JOSA_PAIRS]


def has_batchim(code, table):
    lo, hi = code_span()
    if not lo <= code <= hi:
        return False
    return bool(table[code - lo])


def _lead(b):
    """SJIS 2바이트 문자의 첫 바이트인가."""
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def fix_buffer(buf, table=None, codes=None):
    """🔴 **기계어 루틴의 기준 구현.** 버퍼(bytearray)를 제자리에서 접는다 → 접은 횟수.

    한 번 훑으며 `prev`(마지막으로 본 우리 음절)를 들고 간다. 병기를 만나면 `prev` 의
    받침으로 조사 하나를 고르고 **4바이트를 왼쪽으로 당긴다**(6B → 2B).
    ⚠ ASCII·제어 바이트는 `prev` 를 **지우지 않는다** — 이름과 조사 사이에 `%c` 색 코드가
      낀다(원문이 `%c%s%c은(는)…` 꼴이다). 지우면 이름을 못 보고 늘 무받침을 고른다.
    ⚠ 병기가 없으면 아무것도 안 한다 — **멱등**이라 어느 경로에 걸어도 안전하다.
    """
    table = table if table is not None else build_table(codes)
    lo, hi = code_span()
    pr = pairs(codes)
    i, prev, n = 0, 0, 0
    while i < len(buf) and buf[i]:
        b = buf[i]
        if _lead(b) and i + 1 < len(buf):
            code = (b << 8) | buf[i + 1]
            hit = next((p for p in pr if p[0] == code), None)
            if (
                hit
                and i + 5 < len(buf)
                and buf[i + 2] == PAREN_L
                and ((buf[i + 3] << 8) | buf[i + 4]) == hit[1]
                and buf[i + 5] == PAREN_R
            ):
                keep = hit[0] if has_batchim(prev, table) else hit[1]
                buf[i] = keep >> 8
                buf[i + 1] = keep & 0xFF
                del buf[i + 2 : i + 6]
                buf.extend(b"\x00" * 4)  # 길이를 지킨다(꼬리는 널)
                prev, i, n = keep, i + 2, n + 1
                continue
            if lo <= code <= hi:
                prev = code
            i += 2
        else:
            i += 1  # ASCII·제어 — prev 유지
    return n
