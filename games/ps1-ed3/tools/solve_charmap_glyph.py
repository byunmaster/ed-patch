"""코드표를 **글리프로** 푼다 — 두 디스크가 같은 활자를 쓴다는 것을 로제타로 삼는다.

`solve_charmap.py` 는 **알려진 평문**(새턴 ED3 의 생 SJIS 덤프)이 있어야 돈다. ED4 는 그
평문이 없어 여섯 달을 열어 둔 자리였는데, 답은 대본이 아니라 **활자**에 있었다 —
ED3 와 ED4 는 같은 12×12 활자를 쓴다. 같은 그림이면 같은 글자다.

    ED3 글리프(비트 완전일치) ─┐
                              ├─→ ED4 코드 → 글자
    ED4 글리프 ───────────────┘

실측(2026-09-03): **1,595자가 비트까지 완전일치**한다. 다른 조합(생·전치·열 교환)에서는
공통 글리프가 16자뿐이었으니 우연이 아니다. 여기서 곧장 **ED4 코드 1,364자**가 나오고,
JIS 순서 보간이 나머지를 메운다.

⚠ **저장 규약이 디스크마다 다르다** — `font.LAYOUT` 이 그걸 흡수한다(ED3 은 열 짝 교환,
  ED4 는 몸통이 한 행 아래). 그걸 안 맞추면 로제타가 통째로 안 걸린다.

⚠ 이건 **비결정적 제안 단계가 아니다** — 비트 완전일치라 판단이 안 든다. 그래도 산출물
  (`charmap_<disc>.json`)이 정본이고 빌드는 정본만 읽는다(patcher-checklist 3).
🔴 **양쪽에서 유일한 글리프만 쓴다.** 같은 그림이 두 코드에 있으면(원본에 실제로 있다)
  어느 쪽인지 정할 근거가 없다 — 그런 건 보간에 맡긴다.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import solve_charmap
import textenc


def glyph_index(disc):
    """{글리프 비트 → [코드…]} — 빈 글리프는 뺀다."""
    exe, _, _ = font.exe_bytes(disc)
    idx = {}
    for c in range(font.glyph_count(exe, disc)):
        g = font.read_glyph(exe, c, disc)
        if g.any():
            idx.setdefault(bytes(np.packbits(g.reshape(-1))), []).append(c)
    return idx


def rosetta(src, dst):
    """{dst 코드: src 코드} — **양쪽에서 유일한** 글리프만."""
    a, b = glyph_index(src), glyph_index(dst)
    return {b[k][0]: a[k][0] for k in set(a) & set(b) if len(a[k]) == 1 and len(b[k]) == 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed4")
    ap.add_argument("--from-disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--fill-jis", action="store_true", help="아는 자리 사이를 JIS 순서로 메운다")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.disc == a.from_disc:
        raise SystemExit("같은 디스크끼리는 로제타가 안 된다")
    common.verify_source(a.disc)
    common.verify_source(a.from_disc)

    src_map = textenc.charmap(a.from_disc)
    kana = set(textenc.kana_map(a.disc))
    pairs = rosetta(a.from_disc, a.disc)
    learned = {c: src_map[s] for c, s in pairs.items() if s in src_map and c not in kana}
    print(f"글리프 완전일치 {len(pairs):,} · 그 중 글자를 아는 것 {len(learned):,} (카나 제외)")

    learned, dropped = solve_charmap.enforce_order(learned, kana)
    if dropped:
        print(
            f"  순서 정합: {len(dropped)} 버림 — "
            + ", ".join(f"{c:03x}={ch}" for c, ch in list(dropped.items())[:8])
        )

    if a.fill_jis:
        known = dict(learned)
        known.update(textenc.kana_map(a.disc))
        filled, gaps = solve_charmap.fill_jis(known, kana)
        for c, ch in filled.items():
            learned.setdefault(c, ch)
        print(f"  JIS 보간: {len(filled)} 채움 · 셈이 안 맞아 건너뛴 구간 {len(gaps)}")

    print(f"\n표: 카나 {len(kana)} + 배운 것 {len(learned)} = {len(kana) + len(learned)}")
    if a.write:
        doc = {
            "disc": a.disc,
            "note": "코드 → 일본어 글자. 카나는 textenc.kana_map 이 계산하고 여기엔 안 담는다.",
            "source": f"solve_charmap_glyph.py (활자 로제타: {a.from_disc} 와 글리프 비트 완전일치)",
            "map": {f"{c:04x}": ch for c, ch in sorted(learned.items())},
        }
        p = textenc.charmap_path(a.disc)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"→ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
