"""화자 이름 반복 — 구운 대사에서 화자 머리 `{16}이름{14}` 바로 뒤 본문이 같은 이름으로 시작하는데 원판 본문은 그렇지 않은 줄(11-18, pce-ed1 의 「본문 안 화자명 반복」 부류).

원판 본문도 화자 이름으로 시작하면(「신디 대단하다」 — 원문 호격) 통과다. 이름 둘 이상 글자만 본다.
    python3 check_name_repeat.py [--iso <이미지>]   → 걸린 줄이 있으면 rc 1
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import pairs

HEAD = re.compile(r"\{16\}(?:\{0E\})?([^{]*?)\{14\}")
CTRL = re.compile(r"\{[^}]*\}")


def body(s: str, m: re.Match) -> str:
    return CTRL.sub("", s[m.end() : m.end() + 80]).replace("↵", "").replace("⏎", "").lstrip(" 　")


def main() -> int:
    iso = sys.argv[sys.argv.index("--iso") + 1] if "--iso" in sys.argv else str(common.BUILD_DIR / "pce-ed2" / "ed2.iso")
    kg = pairs.KoGlyphs(iso)
    bad = []
    for key, o, k, _sh in pairs.package_rows(iso, kg):
        om = HEAD.search(o)
        for m in HEAD.finditer(k):
            nm = m.group(1).strip()
            if len(nm) < 2 or not body(k, m).startswith(nm):
                continue
            if om and body(o, om).startswith(om.group(1).strip()):
                continue
            bad.append(f"{key}: 〔{nm}〕 {body(k, m)[:24]}")
    print(f"화자 이름 반복 {len(bad)}")
    for b in bad:
        print("  ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
