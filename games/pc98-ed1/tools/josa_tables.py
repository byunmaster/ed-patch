#!/usr/bin/env python3
"""조사 훅이 런타임에 찾아볼 표 둘 — 한글 받침 비트맵(294B) · 숫자 받침 마스크(2B).

훅은 **직전에 찍힌 글자의 받침**으로 은/는·을/를을 고른다(PS1 방식, 마스터 09-27).
화자·시전자를 식별하지 않으므로 이름·주문·도구 어느 자리에서든 같은 장치를 쓴다.

## 색인 — 훅이 계산하는 그대로

게임은 SJIS 두 바이트를 `0x7da0`(program)에서 JIS 로 바꾼다. 우리 한글은 JIS 구
`KU_LO`~ 에 **구마다 94자**로 깔려 있으므로(`patch_scn.slot_of`)

    색인 = (JIS 상위 − KU_LO) × 94 + (JIS 하위 − 0x21)      # 0..2349

이고 이것이 `font.build()` 의 음절 차례와 같다. 🔴 **여기가 어긋나면 조사만 조용히 틀린다**
(빌드도 되읽기도 통과한다) — 그래서 `check()` 가 **인코딩된 바이트에서 출발해 `0x7da0` 을
그대로 흉내 내** 전 음절을 왕복시킨다.

## 숫자 — 읽는 소리대로(마스터 09-26)

0·1·3·6·7·8(영·일·삼·육·칠·팔) → 받침 있음, 2·4·5·9 → 없음. 영문·부호는 받침 없음.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_scn

DIGIT_BATCHIM = "013678"


def has_batchim(ch: str) -> bool:
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return ch in DIGIT_BATCHIM


def batchim_bitmap() -> bytes:
    """비트 i = 표 차례 i 음절의 받침(MSB 먼저). 2,350비트 → 294B."""
    syl = patch_scn.syllables()
    order = sorted(syl, key=syl.get)
    out = bytearray((len(order) + 7) // 8)
    for i, ch in enumerate(order):
        if has_batchim(ch):
            out[i >> 3] |= 0x80 >> (i & 7)
    return bytes(out)


def digit_mask() -> int:
    """비트 d = 숫자 d 의 받침. `bt ax, (al-'0')` 류로 한 번에 조회한다."""
    return sum(1 << int(d) for d in DIGIT_BATCHIM)


def sjis_to_jis(lead: int, trail: int) -> tuple[int, int]:
    """program `0x7da0` 의 한 줄 한 줄 흉내(8비트 감김 포함)."""
    ah, al = lead, trail
    ah = (ah - 0x71) & 0xFF
    if ah >= 0x2F:
        ah = (ah - 0x40) & 0xFF
    ah = (ah + ah + 1) & 0xFF
    if al >= 0x80:
        al = (al - 1) & 0xFF
    al = (al - 0x1F) & 0xFF
    if al >= 0x7F:
        al = (al - 0x5E) & 0xFF
        ah = (ah + 1) & 0xFF
    return ah, al


def runtime_index(lead: int, trail: int) -> int:
    ah, al = sjis_to_jis(lead, trail)
    return (ah - patch_scn.H.KU_LO) * 94 + (al - 0x21)


def check() -> None:
    bm = batchim_bitmap()
    syl = patch_scn.syllables()
    bad = []
    for ch, i in syl.items():
        b = patch_scn.encode(ch)
        idx = runtime_index(b[0], b[1])
        bit = bm[idx >> 3] >> (7 - (idx & 7)) & 1
        if idx != i or bit != has_batchim(ch):
            bad.append((ch, i, idx, bit))
    if bad:
        raise SystemExit(f"🔴 런타임 색인·받침이 어긋난다 {len(bad)}건 — {bad[:4]}")
    # 숫자는 반각 ASCII(0x30~0x39)로 찍힌다
    m = digit_mask()
    for d in "0123456789":
        assert bool(m >> int(d) & 1) == has_batchim(d), d


def main() -> int:
    check()
    bm = batchim_bitmap()
    print(
        f"받침 비트맵 {len(bm)}B · 켜진 비트 {sum(b.bit_count() for b in bm)}/{len(patch_scn.syllables())}"
    )
    print(f"숫자 마스크 0x{digit_mask():04x} ({DIGIT_BATCHIM})")
    print("✅ 2,350음절 전부 인코딩 → 0x7da0 흉내 → 색인·받침 왕복 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
