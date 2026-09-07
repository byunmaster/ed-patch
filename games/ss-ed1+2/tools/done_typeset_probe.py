#!/usr/bin/env python3
"""**조판 계약을 원문에서 잰다** — 창 폭·줄 수를 PS1 에서 옮겨 오지 않기 위해.

⛔ **끝난 1회성 계측이다**(`done_` 접두). 조판 계약은 이걸로 닫혔다 — 결과는
   `docs/policy.md` 6절(전각 15자 × 본문 5행 · 엔진이 글자 단위로 접는다).
   다시 돌릴 일은 창 규격을 의심할 때뿐이다.

⚠ PS1 은 **우리가 개행을 전부 넣는** 전제다(krwrap 이 14슬롯에서 끊는다). 새턴이 같은지를
가정하면 재삽입 조판이 통째로 틀린다 — 그래서 원문 대사를 직접 재서 전제부터 확인한다.

재는 것은 셋이고, 셋이 함께 **「엔진이 접는가」**를 가른다:

- **명시 개행으로 끝난 줄의 폭** — 작가가 직접 끊은 줄이니 한 줄에 반드시 들어간다.
  이것이 창 폭보다 크면 모순이다 → 엔진이 접는다는 뜻.
- **한 창 안에서 좁은 줄과 넓은 줄이 섞이는가** — 섞이면 작가가 앞줄만 끊고 나머지를
  흘린 것이다(엔진 개행).
- **공백 없는 긴 토큰** — 있으면 공백 단위가 아니라 **글자 단위**로 접는다.

**폭·행 수는 실행에서 읽었다**(2026-08-20, mednafen/saturn, `ED1SCN01:16`):
전각 advance 12px, 창 안쪽 x 16..201 에 글자가 x=22 부터 → **전각 15자(180px)**.
세로는 y 147..228 에 12px 피치 → **6행**(화자 1 + 본문 5). 아래 표가 그 값을 되짚는다 —
정적 코퍼스가 폭 15 에서 본문 최대 **정확히 5줄**이라 실측과 맞물린다.

⚠ **마지막 줄은 폭 판정에서 뺀다** — 뒤가 없으니 짧은 게 당연하고, 길면 엔진이 접은 것이라
어느 쪽으로도 증거가 안 된다.

  python3 games/ss-ed1+2/tools/typeset_probe.py
"""

import collections
import glob
import json
import math
import os
import re
import unicodedata

import common

# 이름창(`%c화자%c` + 개행)으로 시작하면 대사다 — 값 표·지명 헤더를 뺀다.
HDR = re.compile(r"^%c[^%\n]{1,12}%c\n")
WIDE = 20.0  # 「넓은 줄」의 문턱 — 손으로 끊은 봉우리(13~14.5)에서 충분히 떨어져 있다

# 실측 조판 계약 (mednafen/saturn 2026-08-20) — ⚠ PS1 은 14.0슬롯·6줄로 **다르다**
WRAP = 15.0  # 창 폭, 전각 15자 = 180px (전각 advance 12px)
BODY_LINES = 5  # 창 6행 중 화자 이름이 1행을 먹는다


def strip_ctrl(s):
    """서식 인자(`%c`·`%s`·`%d`)를 뺀 **화면에 나가는 글자만**."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "%" and i + 1 < len(s) and s[i + 1] in "csd":
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def slots(s):
    """전각 1.0 · 반각 0.5 로 잰 폭."""
    return sum(0.5 if unicodedata.east_asian_width(ch) in "HNa" else 1.0 for ch in s)


def windows(src=None):
    """대사 블록의 창들 → `(파일, entry_id, 창번호, [줄 폭…])`."""
    src = src or os.path.join(common.OUT_DIR, "scn_jp")
    files = sorted(glob.glob(os.path.join(src, "ED*SCN*.json")))
    if not files:
        raise SystemExit(f"덤프가 없다 — 먼저 dump_scn.py. ({src})")
    for path in files:
        tid = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["entries"]
        for e in entries:
            text = e.get("text") or ""
            if not HDR.match(text):
                continue
            for wi, win in enumerate(HDR.sub("", text).split("%c")):
                ls = [x for x in strip_ctrl(win).split("\n") if x.strip()]
                if ls:
                    yield tid, e["entry_id"], wi, [slots(x) for x in ls], ls


def main():
    wins = list(windows())
    mid = collections.Counter()  # 명시 개행으로 끝난 줄
    shape = collections.Counter()  # 창 모양 (좁다/넓다/섞였다)
    mixed, longtok = [], []
    for tid, eid, wi, ws, raw in wins:
        mid.update(ws[:-1])
        for x in raw:
            for tk in re.split(r"[ 　]+", x):
                if tk and slots(tk) >= WIDE:
                    longtok.append((slots(tk), tid, eid, tk))
        if len(ws) < 2:
            continue
        head = ws[:-1]
        if min(head) >= WIDE:
            shape["넓다"] += 1
        elif max(head) < WIDE:
            shape["좁다"] += 1
        else:
            shape["섞였다"] += 1
            mixed.append((tid, eid, wi, head))

    print(f"■ 대사 창 {len(wins):,} · 여러 줄 창 {sum(shape.values()):,}")
    print(f"■ 명시 개행으로 끝난 줄 {sum(mid.values()):,} · 최대 {max(mid):g}슬롯")
    print("   " + " ".join(f"{w:g}:{n}" for w, n in sorted(mid.items())[-6:]))
    print("■ 창 모양  " + " · ".join(f"{k} {v}" for k, v in shape.most_common()))
    for tid, eid, wi, head in mixed[:3]:
        print(f"     ▸ 섞였다 {tid}:{eid}#{wi}  {[f'{x:g}' for x in head]}")
    print(f"■ {WIDE:g}슬롯 넘는 **공백 없는** 토큰 {len(longtok):,} · 최대 {max(longtok)[0]:g}")

    verdict = max(mid) >= WIDE and shape["섞였다"] and longtok
    print(
        f"  {'🔴' if verdict else '✅'} 엔진이 접는가: "
        + ("**그렇다** — 개행을 우리가 다 넣는 PS1 전제가 안 통한다" if verdict else "증거 없음")
    )

    print(f"\n■ 후보 폭으로 접었을 때 창당 본문 줄 수 (실측 폭 {WRAP:g} · 본문 {BODY_LINES}행)")
    for cand in (12, 13, 14, WRAP, 16, 18, 20):
        c = collections.Counter(
            sum(max(1, math.ceil(w / cand)) for w in ws) for _, _, _, ws, _ in wins
        )
        over = sum(v for k, v in c.items() if k > BODY_LINES)
        mark = " ← 실측" if cand == WRAP else ""
        print(
            f"   폭 {cand:>4g} → "
            + " ".join(f"{k}줄:{v}" for k, v in sorted(c.items()))
            + (f"   ⚠ {BODY_LINES}줄 초과 {over}창" if over else "")
            + mark
        )
    print("  ⚠ 폭 13 이하는 원문조차 창을 넘긴다 — 실측 15 와 함께 계약이 양쪽에서 잠긴다.")


if __name__ == "__main__":
    main()
