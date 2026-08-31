"""부호가 홀로 다음 줄로 밀리는 자리를 **정본에서** 고친다.

    python3 games/ss-ed3/tools/fix_orphans.py            # 현황만 (안 고친다)
    python3 games/ss-ed3/tools/fix_orphans.py --apply    # script/MAP*.json 을 고친다

🔴 **엔진은 어절을 안 본다** — 폭이 차면 글자 한복판에서 접는다. 「전각 17 자 + 반각 부호」
   (17.5 슬롯)인 줄은 **부호 하나만 다음 줄에 남는다**(유저 실측 2026-08-30).
   폭은 엔진 것이라 넘겨 붙일 수 없다. 대신 **공백 한 칸을 개행으로 바꾼다** —
   어절 경계에서 접히니 부호가 제 낱말과 함께 가고, **공백 1B ↔ 개행 1B 라 길이가 안 변해서**
   길이 보존 재삽입(`reinsert.fit`)을 안 깨뜨린다.

⚠ **줄 수가 늘면 안 고친다** — 창은 3 줄이라 한 줄이 더 생기면 계약을 깨뜨린다
   (`typeset.rewrap` 이 그럴 때 `None` 을 낸다).
⚠ 문안이 바뀌므로 **조판 지문을 다시 얼려야 한다** — `check.sh` 가 알려 준다.
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import typeset as T

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")


def fix_block(text):
    """블록 하나 → `(고친 텍스트, 고친 줄 수)`. 줄 구조(페이지·개행)는 그대로 둔다."""
    if T.is_narration(text):
        return text, 0
    n = 0
    out_pages = []
    for pg in text.split(T.PAGE):
        rows = []
        for ln in pg.split(T.NL):
            v = T.visible(ln)
            if v and T.orphans(v):
                w = T.rewrap(v)
                if w is not None and w != v:
                    rows.append(w)
                    n += 1
                    continue
            rows.append(ln)
        out_pages.append(T.NL.join(rows))
    return T.PAGE.join(out_pages), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="정본을 고친다")
    ap.add_argument("--check", action="store_true", help="남아 있으면 1 로 죽는다 (게이트)")
    a = ap.parse_args()

    total, fixed, stuck = 0, 0, []
    for p in sorted(glob.glob(os.path.join(SCRIPT_DIR, "MAP*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        changed = 0
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            if not T.orphans(v):
                continue
            total += 1
            new, n = fix_block(v)
            if n:
                doc[k] = new
                changed += n
            else:
                stuck.append((os.path.basename(p), k, T.orphans(v)[0][0]))
        if changed:
            fixed += changed
            if a.apply:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=1)
                    f.write("\n")
            print(f"  {os.path.basename(p)}  {changed} 줄")

    print(f"\n부호 고아 {total} 블록 · 고칠 수 있는 줄 {fixed} · 못 고침 {len(stuck)}")
    for f, k, ln in stuck[:10]:
        print(f"  ⚠ {f} [{k}] {ln!r}  — 어절 경계로 접으면 줄이 는다")
    if not a.apply and fixed:
        print("\n→ `--apply` 로 정본을 고친다")
    if a.check and total:
        #   ⚠ 못 고치는 것도 실패로 친다 — 어절이 창보다 긴 줄이라 **문안을 손봐야** 한다
        print("  🔴 부호가 홀로 밀리는 자리가 남아 있다")
        return 1
    if a.check:
        print("  ✅ 부호 고아 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
