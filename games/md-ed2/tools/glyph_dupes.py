"""구운 글리프 중복 검사 — 롬에서 읽은 리소스 0~5(전각 14×14 · 반각 8×14 · HUD 8×8·8×12·12×12 · 타이틀 14×14)에서 **채움(fill) 비트맵이 같은 서로 다른 코드**를 센다.

    python3 tools/glyph_dupes.py [롬 경로]

⚠ 원본 글꼴 파일이 아니라 **구운 롬**에서 읽는다 — ss-ed1+2 에서 행 맞춤으로 쉼표 꼬리 행이 잘려 쉼표가 마침표와 같은 비트맵으로 구워졌다(10-20). 빈 글리프(공백)끼리는 센 뒤 제외한다.
`check.sh` 가 부른다 — 부호 쌍(`,` `.` · `、` `。` · `，` `．` · `:` `;` · `'` `` ` ``)이 같거나 허용 목록 밖의 새 중복이 생기면 실패.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font

# 비트맵이 같아도 되는 묶음 — 원판 글꼴이 이미 같게 그렸거나(ー·―·－ / 0·O) 설계상 같은 글자다(「의」 와 「의␣」 합성 코드, halfspace.py)
ALLOWED = {
    (0, frozenset({0x815B, 0x815C, 0x817C})),
    (0, frozenset({0x8ADC, 0x8B6E})),
    (1, frozenset({0x30, 0x4F})),
    (2, frozenset({0x30, 0x4F})),  # HUD 숫자 8×8 · 8×12 도 원판이 0·O 를 같게 그렸다
    (3, frozenset({0x30, 0x4F})),
}
# 부호 쌍은 **절대** 같으면 안 된다(ss-ed1+2: 쉼표 꼬리 행이 잘려 쉼표 3,983곳이 마침표로 그려졌다) — (리소스, 코드, 코드)
PUNCT = [
    (1, 0x2C, 0x2E),
    (1, 0x3A, 0x3B),
    (1, 0x27, 0x60),
    (0, 0x8141, 0x8142),
    (0, 0x8143, 0x8144),
]


def glyph_bits(rom, r, i):
    base = r["glyphs"] + i * r["stride"]
    return bytes(rom[base : base + r["nbytes"]])


def scan(rom: bytes):
    res = font.resources(rom)
    out = {}
    for ri, r in enumerate(res):
        cs = font.codes(rom, r)
        by = defaultdict(list)
        for i, c in enumerate(cs):
            b = glyph_bits(rom, r, i)
            if any(b):
                by[b].append(c)
        out[ri] = (cs, {k: v for k, v in by.items() if len(v) > 1}, by)
    return out


def main() -> None:
    rom = (Path(sys.argv[1]) if len(sys.argv) > 1 else common.BUILD_DIR / "ed2-kr.bin").read_bytes()
    res = scan(rom)
    bad = 0
    for ri, (cs, dup, by) in res.items():
        print(
            f"리소스 {ri}: 글리프 {len(cs)} · 비어 있지 않은 서로 다른 비트맵 {len(by)} · 같은 비트맵을 쓰는 코드 묶음 {len(dup)}"
        )
        pos = {c: k for k, v in by.items() for c in v}
        for v in dup.values():
            ok = (ri, frozenset(v)) in ALLOWED
            print("   ", " ".join(f"{c:#06x}" for c in v), "(허용)" if ok else "❌ 새 중복")
            bad += not ok
        for r_, a, b in PUNCT:
            if r_ == ri and a in pos and b in pos and pos[a] == pos[b]:
                print(
                    f"❌ 리소스 {ri}: {a:#06x} 와 {b:#06x} 가 같은 비트맵 — 부호 두 개가 같은 모양으로 구워졌다"
                )
                bad += 1
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
