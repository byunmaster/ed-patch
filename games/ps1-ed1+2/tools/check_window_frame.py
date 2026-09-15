#!/usr/bin/env python3
"""창 틀 갉힘 게이트 — **마지막 줄이 매달기로 14.5슬롯까지 늘어났는데 그 창이 이미
줄 수 리밋을 꽉 채웠나**를 본다(2026-09-14, 마스터 QA 040).

**040의 실체**: 온점 매달기(`patch_hang_punct.py`)는 반각 꼬리 부호를 창 틀 29열째(14.5슬롯)
까지 허용한다. 그런데 그 줄이 **창의 마지막 줄**이고 그 창이 **이미 리밋(이름+5/본문6)을
꽉 채웠으면**, 엔진이 그 부호만 다음 줄로 꺾어 창에 **줄이 하나 더 생기고 창 틀 아래선이
밀려난다**("술이라도 들고 말이야. 핫핫하." — 14.5슬롯 + 리밋 꽉 참, ED2SCN6:8 실측).

⚠ **⑴만으로 게이트를 걸지 않는다** — "마지막 줄 > 14.0" 만 보면 287건이 걸리는데 그중
**대부분(250건)은 정확히 14.5슬롯 안에서 정상 매달기다.** 위험한 건 **⑴ 이고 동시에 ⑵
(창이 이미 꽉 찼다)** 인 경우뿐이다. ⑴만 보면 첫날부터 빨간불이라 아무도 안 본다
(루트 CLAUDE.md "늘 빨간불이면 아무도 안 본다").

⚠ **런타임 조사 병기(`을(를)` 류) 줄은 폭이 실제보다 넓게 잡힌다** — 병기가 훅에서
한 글자로 접히는 게 전제인데, **그 전제 자체가 054에서 조사 중**이다(마스터 지적
2026-09-14). 이 게이트는 그 전제를 깔고 가되, 054가 "훅이 실제로 늘 접는 게 아니다"로
결론 나면 이 축도 다시 봐야 한다 — 지금은 병기 줄도 그대로 잰다(숨기지 않는다).

**재사용, 재구현 아님** — `reinsert_kr_pilot.wrap_page()`를 그대로 부르는 실제 빌드
경로(`build_scene`)를 통째로 돌려서 재는 것이지, 폭·줄바꿈 로직을 따로 흉내내지 않는다.

  python3 tools/check_window_frame.py         # 게이트(0건 기대)
  python3 tools/check_window_frame.py -v      # ⑴(폭>14.0) 전량도 같이 보여준다
"""

import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import ROOT

FRAME37_DUMP = os.path.join(ROOT, "script", "window_frame_over145.json")


def measure():
    """실제 빌드 경로로 전 창을 재삽입해 [(len(pg), lim, 마지막줄폭, pg)] 를 모은다."""
    records = []
    orig_wrap_page = R.wrap_page

    def traced(text, width=R.WRAP, target=None, max_lines=None):
        pages = orig_wrap_page(text, width=width, target=target, max_lines=max_lines)
        lim = max_lines or R.LINES_PER_PAGE
        for pg in pages:
            if not pg:
                continue
            last = pg[-1]
            w = sum(R.cell_w(c) for c in last.rstrip())
            records.append((len(pg), lim, round(w, 3), list(pg)))
        return pages

    R.wrap_page = traced
    try:
        R.donor_reset()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):  # 씬별 진행 로그는 이 게이트의 관심사가 아니다
            for name, lba, size in R.SCN_FILES:
                R.build_scene(name, lba, size, False, False)
    finally:
        R.wrap_page = orig_wrap_page
    return records


def check(*, strict=True, verbose=False):
    records = measure()
    over14 = [r for r in records if r[2] > 14.0]
    over145 = [r for r in records if r[2] > 14.5 + 1e-9]
    danger = [r for r in over14 if r[0] >= r[1]]  # ⑵ 창이 이미 리밋을 꽉 채웠다
    print(
        f"  창 틀 갉힘 — 전수 {len(records)}창 · 마지막줄 폭>14.0 {len(over14)}건"
        f"(그중 >14.5 {len(over145)}) · 리밋 꽉 찬 채로 겹침(위험) {len(danger)}건"
    )
    if verbose:
        for lenpg, lim, w, pg in over14:
            print(f"    len={lenpg} lim={lim} w={w} {pg}")
    # 054(조사 훅이 실제로 늘 접는가)가 아직 조사 중이라, 병기 전제가 깨지면 이 37건이
    # 그대로 피해 목록이 된다 — RE 가 재현할 수 있게 파일로 남긴다(스크래치로 날리지 않는다).
    if over145:
        with open(FRAME37_DUMP, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "_doc": (
                        "마지막 줄 폭이 14.5슬롯을 넘는 창들 — 전부 런타임 조사 병기"
                        "(을(를) 류) 라 훅이 접는다는 전제 위에서만 안전하다. 054가 "
                        "그 전제를 깨면 이 목록이 곧 피해 목록이다(마스터 QA 2026-09-14)."
                    ),
                    "_measured": "2026-09-14",
                    # 🔴 **키가 `_`로 시작해야 한다** — `reinsert_kr_pilot._load_script()`가
                    # `script/*.json` 전부를 씬으로 읽어 `_` 로 안 가린 키를 블록(entry) 취급
                    # 한다(2026-09-14 실측: `windows`(list) 키로 냈다가 `_load_overrides()`가
                    # 그걸 `t`/`ours` 문자열로 읽으려다 `AttributeError`로 **본빌드까지
                    # 죽였다** — patch_ed2_monster_lines.py 의 같은 함정 주석 참조).
                    "_windows": [{"lines": pg, "last_line_width": w} for _l, _lim, w, pg in over145],
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
    if danger:
        lines = [f"    len={lenpg} lim={lim} w={w} {pg}" for lenpg, lim, w, pg in danger]
        msg = "창 틀이 갉힐 위험 — 마지막 줄이 14.0슬롯을 넘는데 창도 이미 꽉 찼다\n" + "\n".join(
            lines
        )
        if strict:
            raise SystemExit(msg)
        print("  ⚠ " + msg.replace("\n", "\n  "))
    return len(danger)


if __name__ == "__main__":
    sys.exit(1 if check(strict=False, verbose="-v" in sys.argv) else 0)
