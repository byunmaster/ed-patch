"""코드표 커버리지 게이트 — 대본 심볼 중 글자로 읽히는 비율이 문턱 아래면 실패.

⚠ 「표에 항목이 몇 개인가」가 아니라 **화면에 나가는 심볼 기준**이다(체크리스트 4).
   표가 한 칸 밀리면 항목 수는 그대로인데 읽히는 비율이 떨어진다 — 그걸 잡는 자다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import coverage
import textenc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--min", type=float, default=99.0)
    a = ap.parse_args()
    d = os.path.join(common.OUT_DIR, a.disc, "script")
    if not os.path.isdir(d) or not os.listdir(d):
        raise SystemExit(
            f"⏭ 대본 덤프가 없다: {d}\n"
            f"   `python3 games/ps1-ed3/tools/dump_script.py --disc {a.disc}` 부터."
        )
    if not os.path.exists(textenc.charmap_path(a.disc)):
        print(f"⏭ {a.disc}: 코드표 정본이 아직 없다 (charmap_{a.disc}.json)")
        return 0
    tot, bad, uniq = coverage.measure(a.disc)
    pct = (tot - bad) / tot * 100
    ok = pct >= a.min
    print(f"{a.disc}: 읽힘 {pct:.2f}% ({tot - bad:,}/{tot:,}) · 미지 고유 {uniq:,} · 문턱 {a.min}%")
    if not ok:
        print(
            "  🔴 표가 밀렸거나 덤프 경계가 어긋났다 — solve_charmap 을 다시 돌리기 전에 원인을 본다"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
