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

# 🔴 **반각으로 끝나는 이름이 있다** — 몬스터 개체 접미가 `슬라임A`~`니어트허니J` 다
#    (171칸, `patch_mon_names`). 앞말이 반각이면 우리 슬롯 코드가 아니라 받침 표에 없고,
#    `prev` 는 **직전 한글 음절**에 머문다 ⇒ `슬라임A` 가 「임」으로 판정돼 **「슬라임A을」**
#    이 나왔다(2026-09-01 실기, 4배 확대로 확인).
# ⚠ 그렇다고 「반각을 만나면 prev 를 지운다」로 가면 **더 크게 깨진다** — 이름과 조사 사이엔
#   `%c` 색 코드가 늘 끼어서(`%c%s%c은(는)`) 전부 무받침이 된다(아래 `fix_buffer` 주석).
# ⇒ **숫자·대문자만** prev 를 갱신한다. 색 코드는 이 구간 밖이라 안 걸린다.
HALF_LO, HALF_HI = 0x30, 0x5A  # '0' ~ 'Z'

# 알파벳·숫자를 **한국어로 읽은 소리**가 정본이다 — 받침은 거기서 유도한다. 값을 손으로
# 적으면 「왜 L 만 1 인가」를 아무도 모른다. ⚠ 실제로 A~J 는 **전부 무받침**이라 개체
# 접미가 붙은 이름은 모두 「를/는/가」다.
HALF_READING = {
    "0": "영", "1": "일", "2": "이", "3": "삼", "4": "사",
    "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구",
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이",
    "F": "에프", "G": "지", "H": "에이치", "I": "아이", "J": "제이",
    "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오",
    "P": "피", "Q": "큐", "R": "아르", "S": "에스", "T": "티",
    "U": "유", "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이",
    "Z": "제트",
}  # fmt: skip


def build_half_table():
    """반각 받침 표 — `표[코드 - HALF_LO]` 가 0/1. **한 바이트에 한 글자**다.

    ⚠ 한글 표와 달리 니블로 안 접는다 — 43B 뿐이라 접어도 21B 를 아낄 뿐인데 루틴엔
      홀짝 분기가 붙는다. **명령 수가 공간보다 비싸다**(위 `build_table` 과 같은 이유).
    """
    tab = bytearray(HALF_HI - HALF_LO + 1)
    for ch, reading in HALF_READING.items():
        tab[ord(ch) - HALF_LO] = 1 if batchim(reading[-1]) else 0
    return bytes(tab)


def slot_codes():
    """`{글자: SJIS 코드(int)}` — 커밋된 슬롯 정본에서."""
    with open(HMAP, encoding="utf-8") as f:
        m = json.load(f)["syllables"]
    return {ch: int.from_bytes(font.sjis_of_index(i), "big") for ch, i in m.items()}


def build_table(codes=None):
    """받침 표 — **니블 하나가 한 글자**다. `표[(code-lo)>>1]` 의 하위/상위 4비트.

    🔴 **바이트 하나씩 쓰다가 자리를 넘겼다**(2026-08-27). 씬 대사가 들어오며 슬롯이
       630 → 1,104 자로 늘자 코드 구간이 2,563B 가 됐고, 코드까지 3,279B 라 놓을 자리
       (2,432B)를 넘었다. **니블로 반으로 줄인다** — 1,282B.
    ⚠ 비트맵(1/8)이면 321B 지만 SH-2 엔 **가변 시프트가 없어**(`shld` 는 SH-3+) 비트를
      꺼내려면 8분기가 붙는다. 니블은 `shlr2` 두 번이면 되고 지금 자리로 충분하다.
      ⚠ 슬롯이 더 늘어 또 넘치면 그때 비트맵으로 간다.
    """
    codes = codes or slot_codes()
    lo, hi = code_span()
    tab = bytearray(((hi - lo) >> 1) + 1)
    for ch, code in codes.items():
        assert lo <= code <= hi, f"{ch!r} 코드 0x{code:04X} 가 표 밖이다"
        if batchim(ch):
            i = code - lo
            tab[i >> 1] |= 0x10 if (i & 1) else 0x01  # 홀수 = 상위 니블
    return bytes(tab)


def pairs(codes=None):
    """`[(조사A 코드, 조사B 코드)]` — 기계어가 그대로 비교한다."""
    codes = codes or slot_codes()
    return [(codes[a], codes[b]) for a, b in JOSA_PAIRS]


_HALF = None


def half_table():
    global _HALF
    if _HALF is None:
        _HALF = build_half_table()
    return _HALF


def has_batchim(code, table, half=None):
    """🔴 **기계어와 같은 의미**여야 한다 — 니블로 읽는다(위 `build_table` 주석).

    ⚠ `code` 는 우리 한글 슬롯(2바이트)일 수도 **반각 한 바이트**일 수도 있다 — 이름이
      개체 접미로 끝나는 자리가 그렇다(`슬라임A`). 반각은 별도 표를 본다.
    """
    half = half if half is not None else half_table()
    if HALF_LO <= code <= HALF_HI:
        return bool(half[code - HALF_LO])
    lo, hi = code_span()
    if not lo <= code <= hi:
        return False
    i = code - lo
    return bool(table[i >> 1] & (0x10 if (i & 1) else 0x01))


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
    🔴 **줄어든 4바이트를 반각 공백으로 메운다 — 길이가 그대로여야 한다.**
       게임은 **접기 전 길이만큼** 그린다. NUL 로 채웠더니 줄어든 두 칸을 글리프 0 으로
       찍어 **화면에 흰 네모**가 남았다(2026-08-26 실기 · 원판엔 없다 · 훅을 램에서 꺼서
       사라지는 것까지 확인). 공백 넷 = 전각 두 칸이라 폭이 정확히 되돌아간다.
       ⚠ **종단은 원래 자리**에 둔다 — 안 그러면 길이가 여전히 줄어든다.
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
                t = i
                while t < len(buf) and buf[t]:
                    t += 1  # 종단 자리 — **여기가 안 움직인다**
                buf[i] = keep >> 8
                buf[i + 1] = keep & 0xFF
                tail = bytes(buf[i + 6 : t])
                buf[i + 2 : i + 2 + len(tail)] = tail
                j = i + 2 + len(tail)
                buf[j : j + 4] = b"    "  # 🔴 **NUL 이 아니라 반각 공백 넷** — 아래 주석
                if j + 4 < len(buf):
                    buf[j + 4] = 0
                prev, i, n = keep, i + 2, n + 1
                continue
            if lo <= code <= hi:
                prev = code
            i += 2
        else:
            # ⚠ 숫자·대문자만 `prev` 를 갱신한다 — 개체 접미(`슬라임A`)를 보기 위해서다.
            #   나머지 ASCII·제어는 **유지**한다(색 코드 `%c` 가 늘 끼므로 위 주석).
            if HALF_LO <= b <= HALF_HI:
                prev = b
            i += 1
    return n
