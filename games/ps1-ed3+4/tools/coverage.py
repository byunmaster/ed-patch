"""코드표 커버리지 — 대본 심볼 중 몇 %가 글자로 읽히나, 못 읽는 코드는 어디에 몰렸나.

⚠ 「표에 몇 개 있나」가 아니라 **화면에 나가는 심볼 기준**으로 잰다(patcher-checklist 4).
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc


def measure(disc):
    """(심볼 수, 못 읽은 수, 못 읽은 고유 코드 수) — 게이트와 리포트가 같은 자를 쓴다."""
    m = textenc.charmap(disc)
    tot = bad = 0
    uniq = set()
    for p in sorted(glob.glob(os.path.join(common.OUT_DIR, disc, "script", "*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for r in doc["runs"]:
            for w in r["codes"]:
                tot += 1
                if w not in m and w not in textenc.CONTROL:
                    bad += 1
                    uniq.add(w)
    return tot, bad, len(uniq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--show", type=int, default=20)
    a = ap.parse_args()
    m = textenc.charmap(a.disc)
    seen = collections.Counter()
    miss = collections.Counter()
    for p in sorted(glob.glob(os.path.join(common.OUT_DIR, a.disc, "script", "*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for r in doc["runs"]:
            for w in r["codes"]:
                seen[w] += 1
                if w not in m and w not in textenc.CONTROL:
                    miss[w] += 1
    tot = sum(seen.values())
    bad = sum(miss.values())
    print(f"{a.disc}: 심볼 {tot:,} · 고유 {len(seen):,}")
    print(f"  읽힘 {tot - bad:,} ({(tot - bad) / tot:.1%}) · 못 읽음 {bad:,} (고유 {len(miss):,})")
    band = collections.Counter()
    for w, n in miss.items():
        band[(w // 0x100) * 0x100] += n
    print(
        "  못 읽는 코드가 몰린 대역:",
        ", ".join(f"0x{b:03x}+:{n:,}" for b, n in band.most_common(8)),
    )
    print("  잦은 미지 코드:", ", ".join(f"{w:03x}×{n}" for w, n in miss.most_common(a.show)))


if __name__ == "__main__":
    main()
