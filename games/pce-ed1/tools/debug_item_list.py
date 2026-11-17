"""디버그 「I」(아이템 고르기)·「W」(워프) **목록** — 디버그 창 안에서 제목만 바꾸고 그 아래 7줄에 그린다(마스터 11-16 「창 위 창 말고, 제목을 워프/아이템으로 바꾸고 나머지 7줄 활용」).

옛 방식(날개 목록 창을 디버그 창 위에 띄움)은 두 가지가 틀렸다 — ① 목록이 글자 타일 번호를 되돌려(`$5B9C`) 디버그 창 글자 타일을 덮어써 **밑 창이 깨졌고** ② 위·아래 한 칸마다 목록 전체를 다시 그려 끊겼다.
지금: 창 틀은 그대로, 제목 줄(`디버그`)을 「워프」/「아이템」으로 바꿔 그리고 그 아래 7줄(BAT `$0187`, 줄마다 +0x80)에 이름을 그린다. 같은 창 안이라 겹침이 없고(목록이 디버그 글자를 통째로 덮는다), 닫으면 디버그 창 전체를 다시 그려 제목·메뉴가 돌아온다.
위·아래 ±1 이 같은 쪽 안이면 **다시 그리지 않고** 두 줄의 BAT 팔레트(상위 니블)만 VDC 로 바꾼다(고른 줄 5 · 나머지 6). 쪽이 넘어갈 때만 다시 그린다. 좌우 ±7 · I = 지급/워프 · II = 닫기/취소.

공통 엔진 하나(모드 I/W):
  · I: 위치 0~115(번호 = 위치 + 1, 아이템 1~116). 이름은 원판 이름 변환(뱅크 0x6E `$864B`, 입력 `$F8` = 번호 → `$CFF1` 14B). 진입 = I 행 핸들러(뱅크 0x6E `$6634`)의 호출 대상 `$629D`.
  · W: 목록 빌더(뱅크 0x6F `$85FD`, 훅이 장별 도착 표로 거름)가 `$CF43` 에 모은 장소 번호 배열(`$C031` = 개수). 이름은 날개 목록과 같은 이름 루틴(뱅크 0x6D `$9505` → `$C07D`). 진입 = 날개 사용 경로 `$92F1` 의 `JSR $855B` 를
    뱅크 0x6F 꼬리 스텁으로 돌린 것(`debug_warp.stub_code` — W 모드 암호가 있을 때만 이 엔진, 아니면 원래 `$855B`). 고르면 C=0 · `$F8`=장소 번호로 돌아가 원래 워프가 이어지고, 취소는 C=1.
이름은 `debug_item.justify` 로 왼쪽 정렬·공백 채움(88px 칸) 뒤 `$5BB1` 로 그린다. 자리: 뱅크 0x70 FF 패딩, 워프 코드 뒤.
"""

import debug_item
import debug_warp as W
import hook

PAD = W.PAD
WAIT = W.WAIT
FAR = W.FAR
TILE_RESET = W.TILE_RESET
DRAW = W.DRAW
DBG_DRAW = W.DBG_DRAW
ROW, ITEM = W.ROW, W.ITEM
TOP = W.TOP
BATV = 0x3E63  # (lo, hi) 줄 BAT 주소 — `BUF` 곁 빈 RAM (W 모드 암호와 같은 바이트지만 암호는 빌더가 돌 때 이미 풀린다)
MODE, NCNT, POS, OLD, TL = (
    0x3E66,
    0x3E67,
    0x3E68,
    0x3E69,
    0x3E6B,
)  # 엔진 상태 — 모드(0=I,1=W) · 개수 · 위치 · 옛 위치 · 임시
TILE_NO = 0x38BD  # 글자 타일 번호 배정(낮은 바이트) — 그리기 루틴이 글자마다 늘린다(원판 `$5B9C`/`$73BD` 가 되돌린다)
DELT = 0x3E90  # 줄마다 「보통 줄 타일 → 고른 줄(하늘색) 타일」 번호 차이 7B (`FRAG_BUF` `$3E60~$3E87` 뒤 빈 RAM)
DLO, DHI, TMP2, PALV, CNT = (
    0x3E98,
    0x3E99,
    0x3E9A,
    0x3E6C,
    0x3E6D,
)  # BAT 칸에 더할 16비트 값 · 그리기 전 타일 번호 · 이번에 쓸 글자색 · 타일 줄 수
CUE_MOVE, CUE_OK, CUE_CANCEL = (
    0x14,
    0x15,
    0x16,
)  # 원판 커서 메뉴(뱅크 0x6D `$82F0~`)의 효과음: 위·아래 · I · II
TITLE_BAT = 0x0107  # 제목 줄 BAT 주소(원판 「디버그」 글자 자리)
BAT_LIST = 0x0187  # 제목 아래 첫 줄 — 줄마다 +0x80(타일 두 줄)
assert BAT_LIST & 0x80  # 줄 주소 계산(`rowaddr`)이 낮은 바이트 넘침을 전제한다
LIST_ROWS = 7
PAGE = 7  # 좌우 = 한 쪽씩
CELLS = 11  # 이름 칸 = 88px = 타일 11칸(`debug_item.justify`)
SEL_PAL, NORM_PAL, TITLE_PAL = (
    5,
    7,
    6,
)  # 글자색(`$8A`): 고른 줄 5(하늘색) · 보통 줄 7(흰색 — 디버그 메뉴 줄과 같다) · 제목 6(노란색 — 원판 「디버그」 제목과 같다)
IDX = 0x37AC  # 고른 아이템 번호(원판 I 가 쓰던 바이트)
ITEMS = 116  # 아이템 1~116
NAME_BUF = debug_item.BUF  # $CFF1
SOUND = 0x57B1
BUILD = 0x85FD  # 뱅크 0x6F — 목록 빌더(`$CF43` 배열 · `$C031` 개수)
PLACE_NAME = 0x9505  # 뱅크 0x6D — 장소 번호(`$F8`) → 이름 `$C07D`
PLACE_BUF = 0xC07D
PLACE_ARR = 0xCF43
PLACE_N = 0xC031
ENTRY_ARG_OFF = 0x0638  # 뱅크 0x6E 안 — I 핸들러 호출 대상(2B, 원판 `$629D`)
ORIG_ENTRY = 0x629D
TITLE_W_TEXT, TITLE_I_TEXT = "워프", "아이템"
DUMMY_TITLES = (b"\x81\x40" * 3 + b"\x00", b"\x81\x40" * 3 + b"\x00")


def titles(table: dict) -> tuple[bytes, bytes]:
    """제목 줄 글자 — 원판 「디버그」(세 글자 36px)를 통째로 덮도록 세 글자 폭으로 채운다(끝 `00` — 원판 제목과 같다)."""
    import font

    out = []
    for t in (TITLE_W_TEXT, TITLE_I_TEXT):
        b = font.encode(t, table)
        assert len(b) == 2 * len(t), (t, b.hex())
        out.append(b + b"\x81\x40" * (3 - len(t)) + b"\x00")
    return out[0], out[1]


def code(
    org: int, ttl: tuple[bytes, bytes] = DUMMY_TITLES, tadr: tuple[int, int] = (0, 0)
) -> hook.Asm:
    a = hook.Asm(org)
    op = a.op

    def far(addr: int, n: int = 6) -> None:
        a.out += bytes([0x20, FAR & 0xFF, FAR >> 8, n, addr & 0xFF, addr >> 8])

    def vdc(reg: int, lo_addr: int) -> None:
        """VDC 레지스터 reg 에 (lo_addr, lo_addr+1) 두 바이트를 쓴다 — 원판 `$5D66` 과 같은 순서(`$F7` 그림자 · `ST0`)."""
        op("LDA", "imm", reg)
        op("STA", "zp", 0xF7)
        op("ST0", "imm", reg)
        op("LDA", "abs", lo_addr)
        op("STA", "abs", 0x0002)
        op("LDA", "abs", lo_addr + 1)
        op("STA", "abs", 0x0003)

    # ── 진입 — I
    a.label("entry")
    op("STZ", "abs", MODE)
    op("LDA", "imm", ITEMS)
    op("STA", "abs", NCNT)
    op("BRA", "rel", "start")
    # ── 진입 — W (스텁이 먼 호출로 부른다)
    a.label("entry_w")
    op("LDA", "imm", 1)
    op("STA", "abs", MODE)
    far(BUILD)
    op("LDA", "abs", PLACE_N)
    op("STA", "abs", NCNT)
    op("BNE", "rel", "start")
    op("SEC")
    op("RTS")
    a.label("start")
    op("STZ", "abs", POS)
    op("STZ", "abs", TOP)
    a.label("redraw")
    op("JSR", "abs", "draw")
    a.label("loop")
    op("JSR", "abs", WAIT)
    op("LDA", "abs", PAD)
    op("TAX")
    op("AND", "imm", 0x02)
    op("BEQ", "rel", "t_i")
    op("JMP", "abs", "iexit")
    a.label("t_i")
    op("TXA")
    op("AND", "imm", 0x01)
    op("BEQ", "rel", "t_up")
    op("JMP", "abs", "pick")
    a.label("t_up")
    op("TXA")
    op("AND", "imm", 0x10)
    op("BEQ", "rel", "t_dn")
    op("LDA", "abs", POS)
    op("STA", "abs", OLD)
    op("BNE", "rel", "up1")
    op("LDA", "abs", NCNT)
    a.label("up1")
    op("SEC")
    op("SBC", "imm", 1)
    op("STA", "abs", POS)
    op("JMP", "abs", "moved")
    a.label("t_dn")
    op("TXA")
    op("AND", "imm", 0x40)
    op("BEQ", "rel", "t_rt")
    op("LDA", "abs", POS)
    op("STA", "abs", OLD)
    op("CLC")
    op("ADC", "imm", 1)
    op("CMP", "abs", NCNT)
    op("BCC", "rel", "dn1")
    op("CLA")
    a.label("dn1")
    op("STA", "abs", POS)
    op("JMP", "abs", "moved")
    a.label("t_rt")
    op("TXA")
    op("AND", "imm", 0x20)
    op("BEQ", "rel", "t_lf")
    op("LDA", "abs", POS)
    op("STA", "abs", OLD)
    op("CLC")
    op("ADC", "imm", PAGE)
    op("CMP", "abs", NCNT)
    op("BCC", "rel", "rt1")
    op("LDA", "abs", NCNT)  # 마지막 쪽에선 끝에 붙는다
    op("SEC")
    op("SBC", "imm", 1)
    a.label("rt1")
    op("STA", "abs", POS)
    op("JMP", "abs", "moved")
    a.label("t_lf")
    op("TXA")
    op("AND", "imm", 0x80)
    op("BNE", "rel", "t_lf1")
    op("JMP", "abs", "loop")
    a.label("t_lf1")
    op("LDA", "abs", POS)
    op("STA", "abs", OLD)
    op("SEC")
    op("SBC", "imm", PAGE)
    op("BCS", "rel", "lf1")
    op("CLA")  # 첫 쪽에선 처음에 붙는다
    a.label("lf1")
    op("STA", "abs", POS)
    # ── 움직인 뒤 — 같은 쪽이면 두 줄만, 쪽이 바뀌면 다시 그린다
    a.label("moved")
    op("JSR", "abs", "calctop")
    op("CMP", "abs", TOP)
    op("BEQ", "rel", "same")
    op("STA", "abs", TOP)
    op("LDA", "imm", CUE_MOVE)
    op("JSR", "abs", SOUND)
    op("JMP", "abs", "redraw")
    a.label(
        "same"
    )  # 두 줄만 — 줄마다 미리 그려 둔 하늘색 타일 쪽으로 BAT 칸만 한 번에 바꾼다(타일을 지웠다 다시 쓰지 않아 중간 모습이 안 보인다)
    op("LDA", "abs", POS)
    op("CMP", "abs", OLD)
    op("BEQ", "rel", "same_d")
    op("LDA", "imm", CUE_MOVE)
    op("JSR", "abs", SOUND)
    op("LDA", "abs", OLD)
    op("SEC")
    op("SBC", "abs", TOP)
    op("STA", "abs", ROW)
    op("JSR", "abs", "adjn")
    op("LDA", "abs", POS)
    op("SEC")
    op("SBC", "abs", TOP)
    op("STA", "abs", ROW)
    op("JSR", "abs", "adjp")
    a.label("same_d")
    op("JMP", "abs", "loop")
    # ── 고르기
    a.label("pick")
    op("LDA", "abs", MODE)
    op("BNE", "rel", "pick_w")
    op("LDA", "abs", POS)  # I — 번호 = 위치 + 1
    op("CLC")
    op("ADC", "imm", 1)
    op("STA", "abs", IDX)
    far(0x9B41)
    op("BCC", "rel", "g_ok")
    op("JMP", "abs", "loop")  # 가득 참 — 지급 안 함
    a.label("g_ok")
    op("LDA", "abs", IDX)
    op("STA", "zp", 0xF8)
    far(0x864B)
    op("LDA", "abs", IDX)
    op("STA", "zp", 0xF8)
    far(0x9B5F)
    op("LDA", "imm", 0x23)
    op("JSR", "abs", SOUND)
    op("JMP", "abs", "loop")
    a.label("pick_w")  # W — 장소 번호를 `$F8` 에 두고 C=0 으로 돌아가면 원래 워프가 이어진다
    op("LDA", "imm", CUE_OK)
    op("JSR", "abs", SOUND)
    op("LDY", "abs", POS)
    op("LDA", "absy", PLACE_ARR)
    op("STA", "zp", 0xF8)
    op("CLC")
    op("RTS")
    # ── 닫기 — I 는 디버그 창 전체를 다시 그리고, W 는 C=1 로 돌아가 호출부(`wmain`)가 다시 그린다
    a.label("iexit")
    op("LDA", "imm", CUE_CANCEL)
    op("JSR", "abs", SOUND)
    op("LDA", "abs", MODE)
    op("BEQ", "rel", "ix_i")
    op("SEC")
    op("RTS")
    a.label("ix_i")
    far(DBG_DRAW)
    op("JSR", "abs", W.wdraw_addr())  # 「W」 라벨 빨강(씬 41) 복원
    op("JSR", "abs", WAIT)
    op("RTS")
    # ── 쪽 맨 앞 = 위치 − 위치 % 7 → A
    a.label("calctop")
    op("LDA", "abs", POS)
    a.label("ct_l")
    op("CMP", "imm", PAGE)
    op("BCC", "rel", "ct_d")
    op("SBC", "imm", PAGE)  # CMP 가 C=1 로 남겼다
    op("BRA", "rel", "ct_l")
    a.label("ct_d")
    op("STA", "abs", TL)
    op("LDA", "abs", POS)
    op("SEC")
    op("SBC", "abs", TL)
    op("RTS")
    # ── 줄 BAT 주소 = BAT_LIST + ROW × 0x80 → BATV (낮은 바이트 +0x80 이 넘친다: BAT_LIST 의 낮은 바이트가 0x80 이상이라 홀수 줄은 낮은 +0x80−0x100 · 높은 +1)
    a.label("rowaddr")
    op("LDA", "abs", ROW)
    op("LSR")  # C = 홀수 줄
    op("BCS", "rel", "ra_odd")
    op("ADC", "imm", BAT_LIST >> 8)
    op("STA", "abs", BATV + 1)
    op("LDA", "imm", BAT_LIST & 0xFF)
    op("BRA", "rel", "ra_lo")
    a.label("ra_odd")
    op("ADC", "imm", BAT_LIST >> 8)  # C = 1 → 높은 바이트 +1
    op("STA", "abs", BATV + 1)
    op("LDA", "imm", (BAT_LIST + 0x80) & 0xFF)
    a.label("ra_lo")
    op("STA", "abs", BATV)
    op("RTS")
    # ── 줄 ROW 의 글자 칸(BAT)을 DELT[ROW] 만큼 앞(하늘색 타일)·뒤(보통 타일)로 — 타일 번호가 0x500 미만인 칸(빈 칸 `$0240`)은 그대로
    a.label("adjp")
    op("LDX", "abs", ROW)
    op("LDA", "absx", DELT)
    op("STA", "abs", DLO)
    op("STZ", "abs", DHI)
    op("BRA", "rel", "adj")
    a.label("adjn")
    op("LDX", "abs", ROW)
    op("LDA", "absx", DELT)
    op("EOR", "imm", 0xFF)
    op("CLC")
    op("ADC", "imm", 1)
    op("STA", "abs", DLO)
    op("LDA", "imm", 0xFF)
    op("STA", "abs", DHI)
    a.label("adj")
    op("JSR", "abs", "rowaddr")
    op("LDA", "imm", 2)
    op("STA", "abs", CNT)
    a.label("aj_tr")
    vdc(0, BATV)  # MAWR
    vdc(1, BATV)  # MARR
    op("LDX", "imm", CELLS)
    a.label("aj_c")
    op("LDA", "imm", 2)
    op("STA", "zp", 0xF7)
    op("ST0", "imm", 2)
    op("LDA", "abs", 0x0002)
    op("STA", "abs", TL)
    op("LDA", "abs", 0x0003)
    op("TAY")
    op("AND", "imm", 0x0F)
    op("CMP", "imm", 5)
    op("BCC", "rel", "aj_w")
    op("LDA", "abs", TL)
    op("CLC")
    op("ADC", "abs", DLO)
    op("STA", "abs", TL)
    op("TYA")
    op("ADC", "abs", DHI)
    op("TAY")
    a.label("aj_w")
    op("LDA", "imm", 2)
    op("STA", "zp", 0xF7)
    op("ST0", "imm", 2)
    op("LDA", "abs", TL)
    op("STA", "abs", 0x0002)
    op("STY", "abs", 0x0003)
    op("DEX")
    op("BNE", "rel", "aj_c")
    op("LDA", "abs", BATV)  # 둘째 타일 줄 = +0x40
    op("CLC")
    op("ADC", "imm", 0x40)
    op("STA", "abs", BATV)
    op("LDA", "abs", BATV + 1)
    op("ADC", "imm", 0)
    op("STA", "abs", BATV + 1)
    op("DEC", "abs", CNT)
    op("BNE", "rel", "aj_tr")
    op("RTS")
    # ── 그리기 — 제목 + 일곱 줄
    a.label("draw")
    op("JSR", "abs", TILE_RESET)
    op("LDA", "imm", TITLE_PAL)
    op("STA", "zp", 0x8A)
    op(
        "LDY", "imm", len(ttl[0]) - 1
    )  # 제목 글자를 RAM 으로 — 그리는 루틴이 다른 뱅크를 켜서 이 뱅크의 글자를 못 읽는다
    op("LDA", "abs", MODE)
    op("BNE", "rel", "dr_tw")
    a.label("dr_ti")
    op("LDA", "absy", "TI")
    op("STA", "absy", NAME_BUF)
    op("DEY")
    op("BPL", "rel", "dr_ti")
    op("BRA", "rel", "dr_t")
    a.label("dr_tw")
    op("LDA", "absy", "TW")
    op("STA", "absy", NAME_BUF)
    op("DEY")
    op("BPL", "rel", "dr_tw")
    a.label("dr_t")
    op("LDA", "imm", NAME_BUF & 0xFF)
    op("STA", "zp", 0x10)
    op("LDA", "imm", NAME_BUF >> 8)
    op("STA", "zp", 0x11)
    op("LDA", "imm", TITLE_BAT & 0xFF)
    op("STA", "zp", 0x12)
    op("STA", "abs", BATV)
    op("LDA", "imm", TITLE_BAT >> 8)
    op("STA", "zp", 0x13)
    op("STA", "abs", BATV + 1)
    op("JSR", "abs", DRAW)
    op("STZ", "abs", ROW)
    a.label(
        "dr_row"
    )  # 줄마다 보통 타일(흰색)과 하늘색 타일 두 벌을 미리 그린다 — 고른 줄 바꿈은 BAT 만 바꿔 한 번에
    op("LDA", "imm", NORM_PAL)
    op("STA", "abs", PALV)
    op("LDA", "abs", TILE_NO)
    op("STA", "abs", TMP2)
    op("JSR", "abs", "drow")
    op("LDA", "abs", TILE_NO)
    op("SEC")
    op("SBC", "abs", TMP2)
    op("LDX", "abs", ROW)
    op("STA", "absx", DELT)
    op("LDA", "abs", ITEM)
    op("CMP", "abs", NCNT)
    op("BCS", "rel", "dr_nx")
    op("LDA", "imm", SEL_PAL)
    op("STA", "abs", PALV)
    op("JSR", "abs", "drow")
    op("LDA", "abs", ITEM)
    op("CMP", "abs", POS)
    op("BEQ", "rel", "dr_nx")
    op("JSR", "abs", "adjn")
    a.label("dr_nx")
    op("INC", "abs", ROW)
    op("LDA", "abs", ROW)
    op("CMP", "imm", LIST_ROWS)
    op("BCS", "rel", "dr_end")
    op("JMP", "abs", "dr_row")
    a.label("dr_end")
    op("RTS")
    a.label("drow")  # ROW 번째 줄 하나(이름 · 팔레트 · BAT 주소)를 그린다
    op("LDA", "abs", TOP)
    op("CLC")
    op("ADC", "abs", ROW)
    op("STA", "abs", ITEM)
    op("CMP", "abs", NCNT)
    op("BCS", "rel", "dr_bl")
    op("LDA", "abs", MODE)
    op("BNE", "rel", "dr_nw")
    op("LDA", "abs", ITEM)
    op("CLC")
    op("ADC", "imm", 1)
    op("STA", "zp", 0xF8)
    far(0x864B)
    op("BRA", "rel", "dr_go")
    a.label("dr_nw")
    op("LDY", "abs", ITEM)
    op("LDA", "absy", PLACE_ARR)
    op("STA", "zp", 0xF8)
    far(PLACE_NAME, 4)
    op("CLY")
    a.label(
        "nz"
    )  # 앞 공백(`20` 한 바이트 · `81 40` 한 쌍)을 건너뛴다 — 날개 목록은 이름을 12B 칸 가운데에 놓지만(앞에 `81 40`·`F8 24`, 뒤에 `06 00`) 여기선 왼쪽 정렬
    op("CPY", "imm", 12)
    op("BCS", "rel", "nz_d")
    op("LDA", "absy", PLACE_BUF)
    op("CMP", "imm", 0x20)
    op("BNE", "rel", "nz_a")
    op("INY")
    op("BRA", "rel", "nz")
    a.label("nz_a")
    op("CMP", "imm", 0x81)
    op("BEQ", "rel", "nz_p")
    op("CMP", "imm", 0xF8)  # `F8 24` = 반 칸(4px) 공백
    op("BNE", "rel", "nz_d")
    a.label("nz_p")
    op("INY")
    op("INY")
    op("BRA", "rel", "nz")
    a.label("nz_d")
    op("LDX", "imm", 0)
    a.label("nc")  # 글자(2바이트)를 옮긴다 — 공백이 나오면 거기서 끝
    op("CPY", "imm", 12)
    op("BCS", "rel", "nf")
    op("LDA", "absy", PLACE_BUF)
    op("CMP", "imm", 0x20)
    op("BEQ", "rel", "nf")
    op("CMP", "imm", 0x81)
    op("BEQ", "rel", "nf")
    op("CMP", "imm", 0x06)  # 이름 끝(종결자 `06 00` 이 12B 칸 안에 든다)
    op("BEQ", "rel", "nf")
    op("CMP", "imm", 0x00)
    op("BEQ", "rel", "nf")
    op("STA", "absx", NAME_BUF)
    op("INX")
    op("INY")
    op("LDA", "absy", PLACE_BUF)
    op("STA", "absx", NAME_BUF)
    op("INX")
    op("INY")
    op("BRA", "rel", "nc")
    a.label("nf")  # 남은 칸은 전각 공백으로
    op("CPX", "imm", 14)
    op("BCS", "rel", "nend")
    op("LDA", "imm", 0x81)
    op("STA", "absx", NAME_BUF)
    op("INX")
    op("LDA", "imm", 0x40)
    op("STA", "absx", NAME_BUF)
    op("INX")
    op("BRA", "rel", "nf")
    a.label("nend")
    op("LDA", "imm", 6)
    op("STA", "abs", NAME_BUF + 14)
    op("BRA", "rel", "dr_go")
    a.label("dr_bl")
    op("LDY", "imm", 14)
    a.label("dr_b1")
    op("LDA", "absy", "BLANK")
    op("STA", "absy", NAME_BUF)
    op("DEY")
    op("BPL", "rel", "dr_b1")
    a.label("dr_go")
    op("LDA", "abs", PALV)
    op("STA", "zp", 0x8A)
    op("JSR", "abs", "rowaddr")
    op("JSR", "abs", "just")
    op("LDA", "imm", NAME_BUF & 0xFF)
    op("STA", "zp", 0x10)
    op("LDA", "imm", NAME_BUF >> 8)
    op("STA", "zp", 0x11)
    op("LDA", "abs", BATV)
    op("STA", "zp", 0x12)
    op("LDA", "abs", BATV + 1)
    op("STA", "zp", 0x13)
    op("JSR", "abs", DRAW)
    op("RTS")
    a.label("BLANK")
    a.out += b"\x81\x40" * 7 + b"\x06"
    a.label("TW")
    a.out += ttl[0]
    a.label("TI")
    a.out += ttl[1]
    a.label("just")
    a.out += debug_item.justify(a.pc)
    return a


def layout() -> int:
    """워프 코드 끝(16B 올림) — 뱅크 0x70 논리 주소."""
    org, blob, _pool, _disp = W.assemble(0)
    return (org + len(blob) + 15) & ~15


def assemble(ttl: tuple[bytes, bytes] = DUMMY_TITLES) -> tuple[int, bytes, int, int]:
    """(시작 주소, 코드, I 진입, W 진입) — 제목 글자 주소가 즉치라 두 번 조립한다(첫 번엔 라벨만 얻는다)."""
    org = layout()
    a = code(org, ttl)
    a = code(org, ttl, (a.labels["TW"], a.labels["TI"]))
    blob = a.bytes()
    assert org + len(blob) <= 0x7B00, hex(org + len(blob))  # 보관소(`$7C00~`) 앞
    return org, blob, a.labels["entry"], a.labels["entry_w"]


STUB_AT = W.TABLE_AT + 48  # 뱅크 0x6F 꼬리 훅 구역 안 — 마스크 8B · 표 48B 뒤
STUB_SITE_OFF = 0x12F1  # 뱅크 0x6F 오프셋 — 날개 사용 경로의 `JSR $855B`(`20 5B 85`)
STUB_SITE_OLD = bytes.fromhex("205b85")
OPEN_SITE_OFF = 0x12EE  # 같은 경로 바로 앞의 `JSR $5CD5`(`20 D5 5C`)
OPEN_SITE_OLD = bytes.fromhex("20d55c")
LIST_BUILDER = 0x855B
WIN_OPEN_ORIG = 0x5CD5


def stub_code(entry_w: int) -> tuple[bytes, int, int]:
    """뱅크 0x6F 꼬리 스텁 둘 + 공용 판정 → (바이트, 목록 스텁 주소, 창 열기 스텁 주소). W 모드 암호가 있을 때만 우리 쪽, 아니면 원래 날개 경로.
    · 목록 스텁(`$92F1` 의 `JSR $855B` 자리) — 우리 목록(먼 호출 n=8) / 원래 `$855B`
    · 창 열기 스텁(`$92EE` 의 `JSR $5CD5` 자리) — W 에선 건너뛴다(`$5CD5` 는 숨은 BAT 칸 4줄×8칸을 화면 왼쪽 위(1줄 3칸)로 복사해, 우리 창(디버그 창 안) 왼쪽 위 모서리를 지도 조각으로 덮었다 — 마스터 11-16)"""
    a = hook.Asm(STUB_AT)
    op = a.op
    a.label("ismode")  # Z=1 이면 W 모드
    op("LDA", "abs", W.WMODE)
    op("CMP", "imm", W.WMODE_KEY[0])
    op("BNE", "rel", "im_x")
    op("LDA", "abs", W.WMODE + 1)
    op("CMP", "imm", W.WMODE_KEY[1])
    a.label("im_x")
    op("RTS")
    a.label("list")
    op("JSR", "abs", "ismode")
    op("BNE", "rel", "l_orig")
    a.out += bytes([0x20, FAR & 0xFF, FAR >> 8, 8, entry_w & 0xFF, entry_w >> 8])
    op("RTS")
    a.label("l_orig")
    op("JMP", "abs", LIST_BUILDER)
    a.label("open")
    op("JSR", "abs", "ismode")
    op("BNE", "rel", "o_orig")
    op("RTS")
    a.label("o_orig")
    op("JMP", "abs", WIN_OPEN_ORIG)
    return a.bytes(), a.labels["list"], a.labels["open"]


def patches(table: dict | None = None):
    """`(라벨, rel, 오프셋, 기대 바이트, 새 바이트)` — 코드 + I 핸들러 호출 대상 + W 목록 스텁."""
    import common

    org, blob, entry, entry_w = assemble(titles(table) if table is not None else DUMMY_TITLES)
    out = []

    def put(label, bank, off, old, new):
        pos = 0
        while pos < len(new):
            at = off + pos
            rel = 34 + (bank - 0x68) * 4 + at // common.USER
            o = at % common.USER
            n = min(len(new) - pos, common.USER - o)
            out.append((label, rel, o, old[pos : pos + n], new[pos : pos + n]))
            pos += n

    put("debug list code", 0x70, org - 0x6000, b"\xff" * len(blob), blob)
    stub, list_at, open_at = stub_code(entry_w)
    assert STUB_AT - 0x8000 + len(stub) <= 0x2000, "훅 구역을 넘는다"
    put("debug W list stub", W.HOOK_BANK, STUB_AT - 0x8000, b"\xff" * len(stub), stub)
    put(
        "debug W list stub site",
        W.HOOK_BANK,
        STUB_SITE_OFF,
        STUB_SITE_OLD,
        b"\x20" + list_at.to_bytes(2, "little"),
    )
    put(
        "debug W open stub site",
        W.HOOK_BANK,
        OPEN_SITE_OFF,
        OPEN_SITE_OLD,
        b"\x20" + open_at.to_bytes(2, "little"),
    )
    rel6e = 34 + (0x6E - 0x68) * 4
    out.append(
        (
            "debug item list entry",
            rel6e + ENTRY_ARG_OFF // common.USER,
            ENTRY_ARG_OFF % common.USER,
            ORIG_ENTRY.to_bytes(2, "little"),
            entry.to_bytes(2, "little"),
        )
    )
    return out


if __name__ == "__main__":
    org, blob, entry, entry_w = assemble()
    print(
        f"목록 코드 {len(blob)}B @0x70:${org:04X}~${org + len(blob):04X} · 진입 I ${entry:04X} · W ${entry_w:04X}"
    )
