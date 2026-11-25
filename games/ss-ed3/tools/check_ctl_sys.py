"""시스템 문자열 제어 문자 대조 — 번역 표의 원문 키와 우리 값이 **같은 제어 문자**를 갖나(마스터 10-29 「대사 색 코드 누락 점검」).

    python3 games/ss-ed3/tools/check_ctl_sys.py

🔴 pce-ed1 에서 번역 조립기가 색 전환 옵코드를 처음부터 안 내 35 메시지가 엉뚱한 색으로 나왔다 — 빌드·게이트가 못 잡았다. 이 게임의 대사 본문 제어는
`check_structure` 가 센다(`제어 토큰 N개 대조`). 여기는 **시스템 문자열**(표 `reinsert_sys.table()`)의 제어 문자(`0x00~0x1F`)를 원문 키와 값에서 세어 대조한다.
의도한 차이만 허용한다 — `0x0D`(줄 나눔 — 조판이 정한다) · `0x1F`(조사 접기 스텁 표지 — `system_src.FOLD`). 그 밖이 갈리면 실패한다.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reinsert_sys as RS

ALLOWED = {0x0D, 0x1F}


def main():
    tbl = RS.table()
    n = tot = 0
    bad = []
    for jp, kr in tbl.items():
        n += 1
        cj = collections.Counter(ord(c) for c in jp if ord(c) < 0x20 and ord(c) not in ALLOWED)
        ck = collections.Counter(ord(c) for c in kr if ord(c) < 0x20 and ord(c) not in ALLOWED)
        tot += sum(cj.values())
        if cj != ck:
            bad.append((repr(kr)[:48], dict(cj), dict(ck)))
    print(f"  시스템 문자열 제어 문자 대조 — 문자열 {n} · 제어 문자 {tot}개(0x0D·0x1F 제외) · 어긋남 {len(bad)}")
    for b in bad[:10]:
        print("    ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
