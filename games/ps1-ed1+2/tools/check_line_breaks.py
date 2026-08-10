#!/usr/bin/env python3
"""줄바꿈이 **한 덩어리를 가르는** 자리를 찾는다 — 조판기가 못 고친 잔여만.

**왜(유저 QA 2026-08-09).** "한줄에 나와야 의미가 제대로 전달되는 경우가 꽤 많은 것 같아.
일일이 눈으로 보면서 수정하고 있는데 이걸 자동화 할 수는 없을까?" — `괴물들에게 당해` /
`가면서 …` · `최소한 10개씩은 사` / `가는 …` · `그런데, 로우, 왜` / `이런 짓을 …` 셋이 다
같은 부류다.

**고치는 건 조판기가 한다** — `shared/text/krwrap.py` 의 `_pull_auxiliary`(본용언+보조용언 ·
`-지 못하다/않다`)와 `_pull_det_orphans`(관형사·부사·수관형사 고아)가 창 안에서 어절을 한 칸
옮겨 붙인다. 재배치라 글자·줄 수·바이트가 안 변한다(다른 `_pull_*` 과 같은 규약).

**이 도구는 그래도 남는 것**을 센다. 남는 이유가 둘이다 —
① 옮기면 폭(14슬롯)을 넘는다. 문안을 줄이거나 `ours` 로 손봐야 한다.
② **하드개행 보호 블록**(`protect_hard`)이라 고아 정리를 통째로 건너뛴다. 줄 경계가 작성자
   지정이라 자동으로 손대면 안 되는 자리다 — `HARD_NL` 마커를 사람이 다시 놓아야 한다.
   (`너무 가까이 하지` / `않으시는 편이...` 가 이것이다 — 규칙을 넣고도 안 고쳐졌다.)

⚠ 산출물은 정발 문안을 담으므로 **REVIEW_DIR(work/review, gitignore)** 로만 나간다.
⚠ 재조판으로 세면 안 된다 — 창 수 계약(`target`)·하드개행·조사 병기 접힘이 빠져 실제와
다른 줄바꿈이 나온다. `wrap_pages` 의 **출력을 가로채는** 게 유일하게 정확하다. 다만 후보
조판(채택되지 않은 시도)도 같이 잡히므로 **같은 쌍은 한 번만 센다**.

  python3 tools/check_line_breaks.py            # 요약
  python3 tools/check_line_breaks.py --report   # → work/review/line_breaks.md
"""

import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import REVIEW_DIR  # noqa: E402
from text import krwrap as K  # noqa: E402


def bad_breaks(pages):
    """창의 줄 경계에서 끊긴 덩어리 [(앞 줄, 뒷 줄, 사유)].

    ⚠ 판정 정본은 `krwrap.split_reason` 하나다 — 조판기(`_balance`·`_pull_tail_orphans`)가
    피하려는 자리와 검출기가 세는 자리가 같아야 한다. 여기 규칙을 따로 두면 "고쳤다"와
    "남았다"가 어긋난다(실제로 규칙이 두 벌이었다, 2026-08-10 통합)."""
    out = []
    for pg in pages:
        for i in range(1, len(pg)):
            prev, words = pg[i - 1].split(), pg[i].split()
            if not prev or not words:
                continue
            why = K.split_reason(prev[-1], words[0])
            if why:
                out.append((pg[i - 1], pg[i], why))
    return out


def main():
    orig, seen = K.wrap_pages, []

    def spy(*a, **kw):
        pages = orig(*a, **kw)
        seen.append(pages)
        return pages

    K.wrap_pages = R.kr_wrap_pages = spy
    rows, dedup = [], set()
    for scn, lba, size in R.SCN_FILES:
        seen.clear()
        R.build_scene(scn, lba, size, False, False)
        for pages in seen:
            for a, b, why in bad_breaks(pages):
                if (a, b) in dedup:
                    continue
                dedup.add((a, b))
                rows.append((scn, why, a, b))
    by_why = {}
    for _scn, why, _a, _b in rows:
        by_why[why] = by_why.get(why, 0) + 1
    print(
        f"줄 갈림 잔여 {len(rows)}건 — " + " · ".join(f"{k} {v}" for k, v in sorted(by_why.items()))
    )
    if "--report" in sys.argv:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        path = os.path.join(REVIEW_DIR, "line_breaks.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 줄 갈림 잔여 {len(rows)}건 (조판기가 못 고친 자리)\n\n")
            f.write("폭이 모자라거나(문안을 줄여야 한다) 하드개행 보호 블록이다.\n")
            for scn, why, a, b in rows:
                f.write(f"\n- {scn} [{why}]\n      {a}\n      {b}\n")
        print(f"  → {path}")


if __name__ == "__main__":
    main()
