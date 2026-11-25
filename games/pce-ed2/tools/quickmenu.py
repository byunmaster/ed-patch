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
CURSOR_Y_SITE = 0xDF  # `LDY #$04`(`JSR $49C1` 바로 앞) — 4 = 항목 수이자 커서 틀 폭 단계(단계 4 = 74px; `cursorw.py` 머리말 표)
OPEN_SITE = 0x249  # `JSR $4ED5; BIT <창 열기 문자열>` 의 BIT 피연산자 — 문자열 머리 `16 x y w h`(각 +0x80, 칸 단위)
ORIG_HEAD = bytes.fromhex("168286" "8b89")
CURSOR_STEP = 5  # 90px — 가장 긴 이름 「요슈아의 거울」(76px)이 틀 안에 든다(마스터 11-22). 창 폭은 11→13칸이라 틀 오른쪽 여백이 왼쪽 여백과 같다(실측: 왼 6px · 오른 5px)
WIN_W = 0x8D


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


def widen(prog: layout.Prog) -> None:
    """퀵메뉴 커서 틀 폭 단계 4→5 · 창 폭 11→13칸(마스터 11-22 「커서크기를 늘리고 좌우 패딩 밸런스」) — 실화면 `proof-1122`."""
    ldy = prog.cur(BANK, CURSOR_Y_SITE, 2)
    if ldy != bytes([0xA0, 0x04]):
        raise ValueError(f"퀵메뉴 커서 단계 자리가 원판과 다르다 {ldy.hex()}")
    ptr = int.from_bytes(prog.cur(BANK, OPEN_SITE, 2), "little") - 0x6000
    head = prog.cur(BANK, ptr, 5)
    if head != ORIG_HEAD:
        raise ValueError(f"퀵메뉴 창 열기 문자열 머리가 다르다 {head.hex()}")
    prog.put(BANK, CURSOR_Y_SITE + 1, bytes([CURSOR_STEP]), "quickmenu 커서 폭 단계 seam")
    # 창 열기 문자열은 systext 가 옮겨 쓴 「literal」 쓰기 안에 있다 — 그 쓰기의 머리 폭 바이트만 바꾼다(겹쳐 쓰면 장부가 거부한다)
    for (b, off), (data, label) in list(prog.writes.items()):
        if b == BANK and off <= ptr < off + len(data):
            k = ptr - off
            assert data[k : k + 5] == ORIG_HEAD, "퀵메뉴 문자열 쓰기 머리가 다르다"
            prog.writes[(b, off)] = (data[: k + 3] + bytes([WIN_W]) + data[k + 4 :], label)
            return
    raise ValueError("퀵메뉴 창 열기 문자열을 쓰는 장부 항목이 없다")
