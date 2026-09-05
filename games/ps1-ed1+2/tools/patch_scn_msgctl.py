#!/usr/bin/env python3
"""**원판이 안 그리고 넘어가는 창**을 되살린다 — 메시지 끝 제어값 오류를 고친다.

**증상.** 카울마을 보일네 보물상자에 닿으면 **창이 아예 안 그려진 채** 멈추고, 키를 누르면
그제야 게일 대사가 나온다. 플레이어에겐 순간 멈춤(프리징)으로 보인다.
JP 원판도 똑같다 — **우리가 깨뜨린 게 아니라 원판 결함**이다(유저 실측 2026-08-27).

**원인.** 씬 오버레이의 메시지 조립기 `0xcc740(buf, fmt, …)` 는 문안의 `%c` 개수만큼
가변인자를 먹는다. 마지막 `%c` 는 **창을 어떻게 닫는가**를 받는데, 이 핸들러의 규약은

    6 = 이 장이 마지막      8 = 다음 장이 있다(장 넘김)

이다. 실제로 한 블록만 조립하고 곧장 출력하는 케이스는 **전부 6** 이다(ED1SCN4 실측:
0x157dc·0x157f4·0x1580c·0x16704·0x1671c·0x16734 …). 그런데 **류난의 「남의 물건을
훔치실 생각은 아니겠지요」 케이스 셋만 `0xc`** 가 들어가 있다. 그 값이면 창이 안 그려진다.

**실측 근거**(에뮬레이터 계측 2026-08-27, 세이브 7 · 카울마을 보일네 상자):

- 디스패처 `0x8017f458` 에 실행 브레이크 → `$a0 = 11` → 인덱스 3 → 케이스 `0x8017f824`
  → 블록 388(류난). **상자는 류난을 부르는 게 맞다** — 분기가 아니라 렌더 실패였다.
- 그 자리 포인터도 정확했다(`a1 = 0x8017142c` = 재삽입된 류난 블록의 시작).
- RAM 에서 `0xc → 8` 로 바꾸니 대사가 뜨고 **빈 장이 하나 더** 붙었다(8 = 장 넘김).
- `0xc → 6` 으로 바꾸니 류난 → 게일 로 **빈 장 없이** 이어졌다. ✅

🔴 **`0xc` 를 일괄 치환하지 말 것.** 이 값은 다른 자리에서 멀쩡히 쓰인다(ED1SCN4 만
58곳). 고칠 수 있는 건 「한 블록만 조립하고 곧장 출력하는데 6 이 아닌」 자리뿐이고,
그마저도 화면으로 확인한 것만 표에 올린다. 그래서 이 도구는 **표를 손으로 든다.**

⚠ 코드는 재삽입해도 안 움직인다(텍스트만 옮겨진다) — 그래서 파일 오프셋을 못 박는다.
쓰기 전에 현재 워드가 기대값인지 확인하고, 아니면 죽는다.

  python3 tools/patch_scn_msgctl.py
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import BUILD_DIR, extract, write_user_data
from patch_sys_ui import _scn_layout

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

ADDIU_V0 = 0x24020000  # addiu $v0, $zero, imm
LAST_PAGE = 6  # 이 장이 마지막
NEXT_PAGE = 8  # 다음 장이 있다

# (씬, 파일 오프셋, 지금 값, 고칠 값, 무엇인가)
# ⚠ 오프셋은 **오버레이 파일 기준**이다. 런타임 주소 = 오프셋 + 0x8016a000 (ED1SCN4).
SITES = [
    ("ED1SCN4", 0x15824, 0xC, LAST_PAGE, "류난 「남의 물건을 훔치실…」 (해리 약속 전)"),
    ("ED1SCN4", 0x1585C, 0xC, LAST_PAGE, "류난 「약속도 지키지 않고…」 (해리 약속 전)"),
    ("ED1SCN4", 0x16A14, 0xC, LAST_PAGE, "류난 둘 (해리 약속 후 — 케이스 둘이 여기로 모인다)"),
]


def main():
    by_scn = {}
    for scn, off, was, now, why in SITES:
        by_scn.setdefault(scn, []).append((off, was, now, why))

    layout = {name: (lba, size) for name, lba, size in _scn_layout()}
    total = 0
    with open(IMG, "r+b") as f:
        for scn, rows in sorted(by_scn.items()):
            lba, size = layout[scn]
            data = bytearray(extract(lba, size, path=IMG))
            for off, was, now, why in rows:
                got = struct.unpack_from("<I", data, off)[0]
                if got == ADDIU_V0 | now:
                    # 이미 고쳐진 이미지에 또 돌린 것 — 멱등하게 넘긴다(제자리 층이라 흔하다)
                    print(f"  {scn}+{off:#x}: 이미 {now:#x} — 건너뜀")
                    continue
                # 쓰기 사전조건 — 빗나간 오프셋에 조용히 기계어를 박는 사고를 막는다
                assert got == ADDIU_V0 | was, (
                    f"{scn}+{off:#x}: `addiu $v0,$zero,{was:#x}` 를 기대했는데 {got:#010x} 다 — "
                    "오버레이가 바뀌었거나 오프셋이 틀렸다"
                )
                struct.pack_into("<I", data, off, ADDIU_V0 | now)
                print(f"  {scn}+{off:#x}: {was:#x} → {now:#x}  {why}")
                total += 1
            secs = write_user_data(f, lba, data, label=f"메시지 창 제어값 ({scn})")
            print(f"  {scn}: 섹터 {secs}개")
    print(f"창 제어값 교정 {total}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
