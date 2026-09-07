"""**줄 끝 쉼표를 뺀다** — 개행이 이미 쉼을 준다.

    python3 games/ss-ed3/tools/fix_line_commas.py          # 현황만
    python3 games/ss-ed3/tools/fix_line_commas.py --apply  # 정본을 고친다

🔴 **일본어 `、` 가 그대로 남은 자리가 많다**(유저 지적 2026-09-06). 일본어는 절 경계마다
   `、` 를 찍지만 한국어는 안 찍는 자리가 대부분이다 — 실측 표본이 그대로 그 꼴이었다:

       다섯 사당이 있고,↵          ← `-고` 뒤에 쉼표를 찍지 않는다
       마법의 거울을 보는 것이,↵    ← 주어와 서술어 사이를 쉼표로 끊지 않는다
       순례를 떠나는 자는,↵        ← 주제어 뒤 쉼표는 일본어 꼴이다

   ⇒ **판정을 문법이 아니라 조판으로 건다** — 「바로 뒤에 개행이 오는 쉼표」만 뺀다.
   문장 안의 쉼표는 손대지 않으므로 「이건 문법적으로 필요한가」를 3,534 번 판정할 필요가 없고,
   빼는 자리는 **개행이 쉼을 이미 주고 있어** 뜻이 안 상한다.

✅ 덤으로 **폭이 반 칸 준다** — 창을 꽉 채워 부호만 다음 줄로 밀리던 자리가 그만큼 풀린다
   (유저 스크린샷의 「…있거든,」 이 그 자리였다).

⚠ **바이트는 준다**(반각 1B) — 재삽입기가 줄 끝을 전각 공백으로 채워 예산을 맞춘다.
  `reinsert.py --check` 로 확인하고, 뺀 뒤에는 **`fix_orphans.py` 를 다시 돌린다**(폭이 바뀐다).
⚠ 나레이션(전각 공백 가운데맞춤)은 건드리지 않는다 — 줄 자체가 조판물이다.
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


def strip_line_commas(text):
    """`(고친 텍스트, 뺀 수)` — **개행 바로 앞**의 쉼표만 뺀다(페이지·블록 끝은 그대로)."""
    if T.is_narration(text):
        return text, 0
    n = 0
    pages = []
    for pg in text.split(T.PAGE):
        rows = pg.split(T.NL)
        #   ⚠ **뒤가 빈 줄뿐이면 「다음 줄」이 아니다** — 「쥬리오 씨,↵」 처럼 보이는 글자가
        #     거기서 끝나는 자리다. 그 쉼표는 **다음 창으로 이어진다**는 표시라 살린다.
        last = max((i for i, r in enumerate(rows) if r.strip()), default=-1)
        for i in range(last):
            r = rows[i]
            if r.endswith(","):
                rows[i] = r[:-1]
                n += 1
        pages.append(T.NL.join(rows))
    return T.PAGE.join(pages), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="정본을 고친다")
    ap.add_argument("--check", action="store_true", help="남아 있으면 1 로 죽는다 (게이트)")
    a = ap.parse_args()

    total = 0
    for p in sorted(glob.glob(os.path.join(SCRIPT_DIR, "MAP*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        n = 0
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            new, cnt = strip_line_commas(v)
            if cnt:
                doc[k] = new
                n += cnt
        if n:
            total += n
            if a.apply:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=1)
                    f.write("\n")
            print(f"  {os.path.basename(p)}  {n} 자리")

    print(f"\n줄 끝 쉼표 {total:,}")
    if a.check and total:
        print("  🔴 개행 앞 쉼표가 남아 있다 — `fix_line_commas.py --apply`")
        return 1
    if a.check:
        print("  ✅ 개행 앞 쉼표 없음")
    if not a.apply and total:
        print("\n→ `--apply` 로 정본을 고친다 (그 뒤 `fix_orphans.py` 를 다시 돌린다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
