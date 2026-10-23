#!/usr/bin/env python3
"""구운 글리프 중복 게이트 — **롬에서 읽은** 글리프 뱅크에서 서로 비트맵이 같은 글자 쌍이 있으면 실패한다(관리자 10-20: 새턴에서 쉼표 꼬리 행이 잘려
쉼표 3,983곳이 마침표로 그려졌다). 원본 글꼴 파일만 보면 못 잡는다 — 굽는 단계(행 맞춤·팩)에서 생기는 결함이라 이미지를 읽는다.

예외: 전용 글자(PUA U+E000~, `font.PACKED` 촘촘히 짠 줄)는 한 글자짜리 줄의 칸이 그 글자의 비트맵과 같다 — 같은 모양인 게 정상이다.
빈 글리프도 전용 글자(빈 칸)만 허용한다.

    python3 tools/check_glyph_dups.py          # 제품 칸(work/build/<꼬리표>/ed1.iso)
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "shared"))
import common  # noqa: E402
import font  # noqa: E402

NBANK_SECTORS = font.GLYPH_NBANKS * 0x2000 // common.USER


def pua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF


def read_bank(iso: Path) -> bytes:
    out = b""
    with open(iso, "rb") as f:
        for s in range(NBANK_SECTORS):
            f.seek((common.T2_SECTOR + 114 + s) * common.RAW + common.USER_OFF)
            out += f.read(common.USER)
    return out


def main() -> int:
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print(f"✗ {iso} 없음 — 먼저 build.py")
        return 2
    order = json.load(open(HERE.parent / "script" / "glyph_order.json", encoding="utf-8"))["order"]
    bank = read_bank(iso)
    by = defaultdict(list)
    empty = []
    for i, ch in enumerate(order):
        at = font.glyph_at(i)
        g = font.unpack(bank[at : at + font.PACKED_BYTES])
        (by[g] if any(g) else empty).append(ch)
    bad = []
    for g, chars in by.items():
        real = [c for c in chars if not pua(c)]
        if len(real) > 1:  # 전용 글자 말고 같은 비트맵이 둘 이상
            bad.append(real)
    bad_empty = [c for c in empty if not pua(c)]
    print(f"  구운 글리프 {len(order)}개 — 같은 비트맵 쌍 {len(bad)} · 빈 글리프(전용 글자 밖) {len(bad_empty)}")
    for b in bad:
        print("  ✗ 같은 비트맵:", " ".join(f"{c!r}(U+{ord(c):04X})" for c in b))
    for c in bad_empty:
        print(f"  ✗ 빈 글리프: {c!r} (U+{ord(c):04X})")
    return 1 if bad or bad_empty else 0


if __name__ == "__main__":
    sys.exit(main())
