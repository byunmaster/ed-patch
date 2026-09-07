"""정발(DOS) 문안을 **표기 대조용 코퍼스**로 긁는다 — 인물·지명 표기의 근거.

이 게임의 방침은 **인물·지명은 정발을 따르고 나머지는 자체 번역**이다(새턴 ED3 와 같다).
따르려면 정발이 뭐라고 썼는지 **세어 봐야** 한다 — 「아마 이렇게 썼겠지」로 정하면 틀린다.

🔴 **산출물은 절대 커밋하지 않는다.** 정발 문안 전량이라 저작권 대상이다(루트 CLAUDE.md).
   커밋되는 건 우리가 고른 **낱말 하나**와 그 근거 한 줄뿐이다(`glossary_<disc>.json`).
⚠ 컨테이너를 안 판다 — `shared/text/ksc_scan` 이 완성형 런만 긁는다. 표기 **대조**엔 충분하고,
   문장을 저본으로 쓰지 않으므로(자체 번역) 블록 구조가 필요 없다.
"""

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common

from shared.text import ksc_scan

# 어느 정발이 어느 디스크의 짝인가 (originals.txt 의 규약).
# ⚠ **판본을 둘 다 본다** — ED4 는 DOS 쪽 문안이 눌려 있어 완성형으로 새는 게 1만 자뿐이고,
#   윈도판 `Lib/SCENARIO.KDT` 에 3만 자가 평문으로 있다(실측 2026-09-03). 한쪽만 보면
#   「정발에 그 이름이 없다」는 **틀린 결론**이 난다.
KR_DIRS = {"ed3": ("kr/dos-ed3", "kr/win-ed3"), "ed4": ("kr/dos-ed4", "kr/win-ed4")}
SKIP = (".wav", ".mid", ".bmp", ".avi", ".mp3", ".ogg")


def corpus(disc):
    """[문자열] — 그 작품 정발(DOS·윈도)의 완성형 런 전량 (중복 포함)."""
    out = []
    for rel in KR_DIRS[disc]:
        root = os.path.join(common.REPO, "originals", rel)
        if not os.path.isdir(root):
            continue
        for p in sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True)):
            if not os.path.isfile(p) or os.path.getsize(p) > 8 << 20:
                continue
            if p.lower().endswith(SKIP):  # 음성·그림에서 우연히 걸리는 4음절을 뺀다
                continue
            with open(p, "rb") as f:
                out.extend(ksc_scan.runs(f.read()))
    if not out:
        raise SystemExit(f"정발이 없다: {KR_DIRS[disc]}")
    return out


def index(disc):
    """{정발 런: 횟수} — 표기 후보를 셀 때 쓴다."""
    return collections.Counter(corpus(disc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--find", nargs="*", help="이 표기가 정발에 몇 번 나오나")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    runs = corpus(a.disc)
    joined = "\n".join(runs)
    print(f"{a.disc} ← {'·'.join(KR_DIRS[a.disc])}: 런 {len(runs):,} · 글자 {len(joined):,}")
    for q in a.find or []:
        print(f"  {q}: {joined.count(q)}회")
    if a.write:
        p = os.path.join(common.OUT_DIR, a.disc, "kr_corpus.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(runs, f, ensure_ascii=False)
        print(f"→ {p}  ⚠ 커밋 금지")
    return 0


if __name__ == "__main__":
    sys.exit(main())
