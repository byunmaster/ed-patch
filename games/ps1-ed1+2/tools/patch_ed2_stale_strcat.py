#!/usr/bin/env python3
"""ED2MON5 몬스터 행동 코드의 「안 채운 임시 버퍼를 먼저 `strcat`」 버그를 막는다(10-20, qa battle-ed2-r3 s94_09).

**증상.** 조우 94 홍아전사의 「…의 운이 N 떨어졌다.」 문구가 「운이 / [깨진 글리프 두 줄] / 떨어졌다.」로 나왔다
(같은 몬스터의 「운이 5 올랐다」 분기는 정상).

**원인(실측 — RAM 의 조립 버퍼에서 읽었다).** 그 행동 함수(ED2MON5 0x801548FC~)는 문구를 `s3` 버퍼에 `sprintf` 한 뒤
임시 버퍼 `sp+0x18` 을 `strcat(s3, sp+0x18)` 로 붙이는데, **「운이 N 떨어졌다」 분기 둘은 임시 버퍼를 `sprintf` 로 채우기
전에 한 번 더 붙인다**(`jal strcat` 뒤에 `addiu $a1,$sp,0x18` · `addiu $a0,$sp,0x18` — 곧바로 그 버퍼를 새로 채운다).
**함수가 `sp+0x18` 을 초기화하지 않으므로** 그때 버퍼는 호출 스택의 **옛 찌꺼기**다 — 이번엔 팔레트 데이터(0x7FFF)였다.
원판 코드가 같은 순서라 일본어 판에서도 찌꺼기 길이만큼 문구가 길어질 수 있었던 **원본 결함**이고, 스택 상태가 우연히
달라 우리 쪽에서 드러났다.

**고침.** 그 `jal strcat`(2곳)을 `nop` 으로 — 뒤에서 `sprintf` 로 채운 버퍼를 `strcat` 하는 정상 호출은 그대로다
(지연 슬롯의 `addiu $a1` 은 무해하다). 시험: 강제 조우 94 에서 RAM 으로 같은 두 곳을 nop 하자 「홍아전사의 운이 1 떨어졌다.」.

⚠ 패턴은 **ED2MON0~5 전체**를 읽어 찾는다 — 지금은 ED2MON5 에만 둘이다(`EXPECT`). 개수가 다르면(코드가 바뀜) 실패한다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import extract, write_user_data
from ed2_monster_review import MON
from patch_ed2_monster_lines import IMG, _live_group_lba

JAL_STRCAT = 0x0C000000 | ((0x800A8074 >> 2) & 0x3FFFFFF)  # BIOS A(15h) strcat 래퍼
ADDIU_A1_SP18 = 0x27A50018  # addiu $a1, $sp, 0x18
ADDIU_A0_SP18 = 0x27A40018  # addiu $a0, $sp, 0x18
NOP = 0
EXPECT = {5: 2}  # 그룹 → 고칠 곳 수 (그룹 5 = 조우 82~99)


def find_sites(buf):
    """strcat(·, sp+0x18) 직후 다시 sp+0x18 을 새로 채우는 자리(= 안 채운 버퍼를 붙이는 `jal`)의 파일 오프셋."""
    out = []
    for off in range(0, len(buf) - 12, 4):
        if (
            struct.unpack_from("<I", buf, off)[0] == JAL_STRCAT
            and struct.unpack_from("<I", buf, off + 4)[0] == ADDIU_A1_SP18
            and struct.unpack_from("<I", buf, off + 8)[0] == ADDIU_A0_SP18
        ):
            out.append(off)
    return out


def main():
    live = _live_group_lba(IMG)
    plan = {}
    for g in sorted(MON):
        lba, size = live[g]
        buf = bytearray(extract(lba, (size + 2047) // 2048 * 2048, path=IMG))
        sites = find_sites(buf)
        if len(sites) != EXPECT.get(g, 0):
            raise SystemExit(
                f"ED2MON{g}: 안 채운 버퍼 strcat {len(sites)}곳 — 기대 {EXPECT.get(g, 0)}곳(코드가 바뀌었다, 다시 본다)"
            )
        if sites:
            plan[g] = (lba, size, buf, sites)
    with open(IMG, "r+b") as f:
        for g, (lba, size, buf, sites) in sorted(plan.items()):
            for off in sites:
                struct.pack_into("<I", buf, off, NOP)
            write_user_data(f, lba, bytes(buf[:size]), label=f"ED2MON{g} 안 채운 버퍼 strcat 제거")
    print(f"ED2MON 안 채운 버퍼 strcat: {sum(len(v[3]) for v in plan.values())}곳을 nop 으로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
