#!/usr/bin/env python3
"""공유 이름 호출(`10 lo hi`) 바로 뒤 원판 가나 조사(を·の·は·が…)가 메시지 밖에 남은 곳 — 0 이어야 한다(11-24).

  python3 tools/check_name_kana.py

마스터 11-24 「아그니쟈 뒤에 일본어가 붙는다」(씬 181 종장): 이름은 공유 문자열이 찍고 그 뒤 한 글자 조사(を)는 런이 한 글자라 메시지로 안 열려
원판 바이트 그대로 우리 글리프로 엉뚱하게 그려졌다. `messages.parse` 가 이제 그 조사를 메시지 머리로 연다 — 이 검사는 **그래도 남은** 곳(메시지 시작·범위 밖)을 잡는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import messages


def main() -> int:
    seen: set[int] = set()
    bad = []
    n_ok = 0
    for c in containers.scan():
        for blk in c["blocks"]:
            if blk["id"] in seen:
                continue
            seen.add(blk["id"])
            d = blk["data"]
            ops = messages.branch_operands(d)
            starts = {m.start for m in messages.parse(d)}
            for i in range(len(d) - 6):
                if d[i] == 0x10 and i not in ops and d[i + 2] >= 0x80 and messages.is_lead(d[i + 3]) and not messages.is_lead(d[i + 5]):
                    if messages._decode_pair(d[i + 3 : i + 5]) in messages.NAME_JOSA:
                        if i + 3 in starts:
                            n_ok += 1
                        else:
                            bad.append((blk["id"], i))
    print(f"공유 이름 호출 뒤 한 글자 조사 — 메시지로 열림 {n_ok} · 남음 {len(bad)}")
    for b, i in bad:
        print(f"  ❌ 씬 {b} +{i}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
