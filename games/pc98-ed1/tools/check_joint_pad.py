#!/usr/bin/env python3
"""🔴 **이음매의 여백이 화면 한복판에 떨어지나** — 여는 부호로 끝나는 조각을 본다.

시스템 문안은 조각 여럿이 이어 붙어 한 문장이 된다. 우리 문안이 자리보다 짧으면 패처가
**꼬리를 공백으로 채우는데, 그 꼬리가 곧 이음매**다. 조각이 **여는 부호**(`【`·`「`·`(`)로
끝나면 그 여백이 **괄호 안**에 떨어진다 — 화면엔 `【      RETURN】` 로 벌어져 보인다.

    조각 A  "…넣고【"   (자리 78, 우리 69B)  → 여백 9
    조각 B  "】키를…"                        ← 사이에 게임이 `RETURN` 을 끼운다
    화면    「…넣고【         RETURN】키를」

⇒ **여백을 낱말과 여는 부호 앞 공백으로 채워 0으로 만든다.** 한국어는 여는 괄호 **앞**에
띄우므로 그 공백은 표기로도 옳다. 반대로 닫는 괄호는 **뒤**에 띄운다(`】 키를`).

🔴 **닫는 부호 쪽은 게이트로 못 세운다** — 한국어는 조사가 닫는 괄호에 **붙는다**
   (`【8】과`·`「이셀하사」라`). 「띄운다/붙인다」가 **뒤에 오는 말이 조사인가**로 갈려서
   기계가 못 가린다. 실측으로 후보 다섯 중 넷이 오탐이었다. ⇒ 그쪽은 **사람이 화면에서** 본다.

⚠ 여는 부호 쪽은 **규칙으로 잡히는 부류**라 게이트로 세운다 — 눈으로는 화면을 열어야 보이는데,
   여기서는 **바이트로** 보인다(2026-09-08 유저 지적에서 나왔다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import patch_scn
import patch_sys

OPEN = "【「『（(［["
CLOSE = "】」』）)］]"


def main() -> int:
    canon = patch_sys.load()
    bad_pad = []
    for disk in patch_sys.DISKS:
        site = patch_sys.sites(disk)
        for key, v in canon.items():
            d, _, off = key.partition(":")
            if d != disk or "t" not in v:
                continue
            o = int(off, 16)
            if o not in site:
                continue
            t = v["t"]
            slack = site[o]["n"] - len(patch_scn.encode(t))
            if t.rstrip().endswith(tuple(OPEN)) and slack > 0:
                bad_pad.append((key, slack, t))
    if not bad_pad:
        print("  ✅ 이음매 여백이 괄호 안에 떨어지는 자리 없음")
        return 0
    for key, s, t in bad_pad:
        print(f"  🔴 여는 부호로 끝나는데 여백 {s} — {key}  {t[-26:]!r}")
    print("     ⚠ 여백은 **낱말과 여는 부호 앞 공백**으로 채운다(한국어 표기로도 그게 옳다)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
