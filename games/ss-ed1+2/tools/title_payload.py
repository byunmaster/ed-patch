#!/usr/bin/env python3
"""자막 번역 페이로드를 만든다 — **JP 원문만** 담아 번역자에게 넘긴다.

🔴 **왜 도구인가.** 이 레포는 「번역하는 쪽에 정발을 주지 않는다」를 규율로 둔다. 페이로드에서
가리는 것만으로는 부족하고 **같은 세션에서 앞서 읽었으면 문맥이 이미 오염된다** — 그래서
번역은 그 문안을 본 적 없는 별도 에이전트에게 넘기고, 이 파일이 그 경계다.
PS1 대사의 `rewrite_payload.py` 와 같은 자리다.

⚠ **PS1 의 동영상 문안을 저본으로 쓰지 않는다**(2026-08-21 실측). 새턴 자막과 줄 분할이
같아 그대로 부을 수 있어 보이지만, PS1 동영상 층은 **167줄 중 66줄이 08-18 자체번역 전환
이전**이라 정발 유래다. 부으면 두 번째 플랫폼으로 복제된다 — `docs/status.md` 8절.

## 이 층의 제약

- **줄 수가 고정**이다(레코드 자리가 고정). 한 문장이 여러 줄에 걸쳐 있으므로 번역자는
  **흐름 전체를 보고 줄마다 다시 나눠** 담아야 한다.
- **줄 폭이 전각 20칸**(한 구간만 21칸). 넘치면 재삽입이 실패한다.
- 스태프롤(`ＣＲＥＤＩＴＳ` 이후)은 회사명·직함·인명이라 **번역 대상이 아니다**(낱말 수준).

  python3 games/ss-ed1+2/tools/title_payload.py     # → work/review/title_payload.md
"""

import json
import os

import common

MARK = "ＣＲＥＤＩＴＳ"
REVIEW = os.path.join(common.WORK_DIR, "review")
GLOSS = os.path.join(common.ROOT, "shared", "glossary", "eiyuu.json")


def narration(lines):
    """스태프롤 앞까지 — `ＣＲＥＤＩＴＳ` 표지가 경계다."""
    for i, t in enumerate(lines):
        if MARK in t:
            return lines[:i], lines[i:]
    return lines, []


def main():
    src = os.path.join(common.OUT_DIR, "title_jp.json")
    if not os.path.exists(src):
        raise SystemExit(f"{src} 가 없다 — 먼저 dump_title.py")
    with open(src, encoding="utf-8") as f:
        doc = json.load(f)
    names = {}
    if os.path.exists(GLOSS):
        with open(GLOSS, encoding="utf-8") as f:
            g = json.load(f)
        # ⚠ 표는 `categories` 아래다 — 최상위에서 찾다가 페이로드에 정본이 **안 실렸다**
        #   (2026-08-21, 번역자가 지적해서 알았다). 빈 표를 조용히 넘기지 않는다.
        cats = g.get("categories", g)
        for cat in ("person", "place"):
            names.update(cats.get(cat, {}))
        assert names, f"고유명사 정본이 비었다 — {GLOSS} 구조를 확인할 것"

    os.makedirs(REVIEW, exist_ok=True)
    dst = os.path.join(REVIEW, "title_payload.md")
    n_tr = 0
    with open(dst, "w", encoding="utf-8") as f:
        f.write("# 새턴 자막 번역 페이로드 (JP 원문)\n\n")
        f.write(
            "⚠ **줄 수는 고정**이다 — 구간마다 정확히 그 줄 수로 답한다.\n"
            "⚠ **한 줄은 전각 N칸 이하**(구간마다 표시). 한글 1자 = 1칸, 반각 부호 = 0.5칸.\n"
            "⚠ 한 문장이 여러 줄에 걸쳐 있다 — **흐름을 보고 줄마다 다시 나눠** 담는다.\n"
            "⚠ 빈 줄은 빈 줄로 둔다.\n\n"
        )
        if names:
            f.write("## 고유명사 정본 (반드시 이대로)\n\n")
            f.write(" · ".join(f"{k}={v}" for k, v in sorted(names.items()) if k)[:4000] + "\n\n")
        for region, v in doc.items():
            body, staff = narration(v["lines"])
            n_tr += len(body)
            f.write(f"## {region} — {len(body)}줄 · 폭 {v['width']}칸\n\n")
            f.writelines(f"{i:>3} | {t}\n" for i, t in enumerate(body))
            if staff:
                f.write(f"\n(이하 {len(staff)}줄은 스태프롤 — 번역 대상 아님)\n")
            f.write("\n")
    print(f"■ 번역 대상 {n_tr}줄 → {dst}")
    print("  ⚠ 원문을 담으므로 review/ 아래다 — 커밋 금지")


if __name__ == "__main__":
    main()
