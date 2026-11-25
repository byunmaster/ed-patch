"""필드 퀵메뉴(SELECT) — 문자열 칸 안쪽에 겹친 「줄 머리 제어 바이트」를 읽고 쓰는 코드를 새 문자열에 맞춘다(11-07).

뱅크 0x6A `+0x258` 문자열 = 퀵메뉴 네 줄(`15 01 01 …`)이고 **줄 머리의 `01`(보통 색) / `04`(붉은 색 = 못 씀)이 곧 사용 가능 표**다.
메뉴를 그릴 때 코드가 항목을 가졌나 보고 `STX $625E · $626A · $626F · $627D`(줄 머리 바이트)에 1 또는 4 를 쓰고(+0x206·+0x217·+0x226·+0x23A),
선택할 때 `LDX $6282,Y`(위치 → 줄 머리 번호 1·13·18·32) · `LDY $625D,X · CPY #1` 로 그 바이트를 도로 읽는다.
`systext._remap_interior` 는 **쓰기(STX)만** 새 문자열 줄 머리로 옮겨서 — 읽기가 옛 칸을 봐 항상 실패했다(워프의 날개·횃불 무반응).
여기서 읽기도 새 문자열에 맞춘다: 새 줄 머리 주소 A_i(STX 피연산자)로 기준 B = min(A) − 1 을 정하고, 표 `$6282` 를 A_i − B 로, `LDY` 피연산자를 B 로.
"""

import layout

BANK = 0x6A
STX_SITES = (0x206, 0x217, 0x226, 0x23A)  # 워프의 날개 · 요슈아의 눈 · 비스니의 열매 · 횃불
ORIG_FLAGS = (0x625E, 0x626A, 0x626F, 0x627D)
LDX_TABLE = 0x283  # `$6282,Y` 의 Y=1 칸
LDY_SITE = 0xF5  # `LDY $625D,X`


def fix(prog: layout.Prog) -> None:
    addrs = []
    for s in STX_SITES:
        c = prog.cur(BANK, s, 3)
        if c[0] != 0x8E:
            raise ValueError(f"퀵메뉴 STX 자리가 아니다 6A+{s:04X} {c.hex()}")
        addrs.append(c[1] | c[2] << 8)
    if tuple(addrs) == ORIG_FLAGS:
        return  # 문자열이 제자리라 옛 표가 그대로 맞다
    base = min(addrs) - 1
    xs = [a - base for a in addrs]
    if not all(1 <= x <= 255 for x in xs):
        raise ValueError(f"퀵메뉴 줄 머리 번호가 범위 밖 {xs}")
    ldy = prog.cur(BANK, LDY_SITE, 3)
    if ldy != bytes.fromhex("bc5d62") or prog.cur(BANK, LDX_TABLE - 1, 5) != bytes.fromhex(
        "00010d1220"
    ):
        raise ValueError("퀵메뉴 읽기 자리가 원판과 다르다")
    prog.put(BANK, LDY_SITE + 1, base.to_bytes(2, "little"), "quickmenu LDY 기준")
    prog.put(BANK, LDX_TABLE, bytes(xs), "quickmenu 위치→줄 머리 번호 표")
