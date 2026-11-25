"""낫표 인용(『…』·「…」)이 원판에서 한 쪽(창)에 있으면 우리도 한 쪽에 — 쪽 경계가 인용 안에 들면 실패.

마스터 10-30: 씬 0 해설 「…라이아스의 말이 떠올랐다. 『…』」 의 인용이 원판은 한 창(4줄)인데 우리는 두 창에 걸쳤다. 원인은 번역 문안에 원판의 쪽 나눔(`\\f`)이 빠져 조판기가 한 덩이로
흘린 것이다. 원판 짝(`work/derived/messages`)의 쪽 나눔을 따라 인용 span 별로 「원판은 안 갈렸는데 우리는 갈렸다」를 센다.
창 크기(4줄)가 모자라 못 맞추는 자리는 `UNSPLIT_OK` 에 사유와 함께 둔다(마스터 판정 대기).

    python3 games/pce-ed1/tools/check_quote_pages.py
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import typeset

OPEN = {"『": "』", "「": "」"}
SCRIPT = Path(common.GAME_DIR) / "script"
DERIVED = Path(common.OUT_DIR) / "messages"
# 원판 한 창에 든 인용이 우리 글로는 4줄 창을 넘는 자리 — 문안을 줄여 해소하고 비웠다(씬 181, 마스터 10-30 「긴 인용후보 오케이」). 새로 생기면 사유와 함께 둔다(판정 대기)
UNSPLIT_OK: dict[tuple[str, str], str] = {}


def split_spans(pages: list[str]) -> list[tuple[str, int]]:
    """쪽별 평문 → [(인용 span, 그 안의 쪽 경계 수)]."""
    full = "\x00".join(pages)
    out, i = [], 0
    while i < len(full):
        c = full[i]
        if c in OPEN:
            j = full.find(OPEN[c], i + 1)
            if j < 0:
                j = len(full) - 1
            seg = full[i : j + 1]
            out.append((seg.replace("\x00", "|"), seg.count("\x00")))
            i = j + 1
        else:
            i += 1
    return out


def check() -> list[str]:
    bad, n, spans = [], 0, 0
    for f in sorted(glob.glob(str(SCRIPT / "scn*.json"))):
        sid = Path(f).stem
        dp = DERIVED / f"{sid}.json"
        if not dp.exists():
            continue
        o = json.load(open(dp, encoding="utf-8"))
        om = {m["key"]: m for m in (o["messages"] if isinstance(o, dict) and "messages" in o else o)}
        for k, v in json.load(open(f, encoding="utf-8")).get("messages", {}).items():
            if not isinstance(v, dict) or "t" not in v or k not in om:
                continue
            jp = om[k]
            jp_pages = [re.sub(r"[\n　]", "", p) for p in jp["jp"].split("\f")]
            osp = split_spans(jp_pages)
            if not osp:
                continue
            typeset.set_scene(int(sid[3:]))
            pg = typeset.pages(font.expand_packed(v["t"].lstrip(" ")), speaker=bool(jp["speaker"]), four=True)
            usp = split_spans(["".join(line) for line in pg])
            n += 1
            spans += len(osp)
            o_split = sum(1 for _, c in osp if c)
            u_split = [s for s, c in usp if c]
            if len(u_split) > o_split and (sid, k) not in UNSPLIT_OK:
                bad.append(f"{sid} {k}: 원판은 인용이 {o_split}곳만 쪽을 넘는데 우리는 {len(u_split)}곳 — 쪽 나눔(\\f)을 원판대로")
    print(f"낫표 인용 든 메시지 {n}개 · 인용 {spans}곳 · 판정 대기 예외 {len(UNSPLIT_OK)}")
    return bad


if __name__ == "__main__":
    e = check()
    for x in e:
        print("  ✗", x)
    sys.exit(1 if e else 0)
