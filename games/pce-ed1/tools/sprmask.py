"""잘린 그림 사본(마스터 11-20 「진행」) — 창에 걸친 어둠 원 조각을 「창 쪽 픽셀만 지운 패턴 사본」으로 갈아 끼운다.

창 맨 위 장치(`winmask.py`)는 스프라이트 **조각 단위**로만 가릴 수 있어(우선순위 비트) 횃불 어둠 원이 창에 걸치면 조각째 BG 뒤로 가
원 가장자리가 평평해졌다(대사 창)거나, 걸친 조각이 창 위에 그대로 남았다(메뉴). 여기서는 걸친 조각마다 패턴을 VRAM 풀에 복사하면서
창 안 픽셀만 0(투명)으로 지우고, SAT 스텁이 그 조각의 패턴 번호를 사본으로 바꿔 낸다 → 창 밖은 원 그대로, 창 안은 비친다.

── 얼개 ──
· **대상**: 어둠 원 개체(종류 0x78~0x81)뿐. 그 밖 스프라이트는 `winmask` 의 옛 판정 그대로.
· **PRES[32]**(조각마다 한 칸, 색인 = SAT 루프의 남은 조각 수 `$33`): 0 = 아직 모름(옛 판정으로 폴백) · 1 = 앞·원래 패턴 · 2 = 통째로 창 안(우선순위 끔) ·
  0x80|lo = 사본(패턴 워드 = 0x100|lo, 앞).
· **서명 SIG[7]**(기준 좌표 `$2E~$31` · 서술자 포인터 `$FA/$FB` · 창 상태) — 프레임마다 어둠 원 첫 조각에서 한 번 비교(`sigchk`). 달라지면 PRES·풀을 비우고,
  **같은 서명이 한 프레임 더 이어질 때**(= 멈춰 섰을 때) 계획을 시작한다 → 걷는 동안은 빌드 비용 0(폴백 화면 = 옛 동작).
· **계획자**(`plan`, 프레임 머리): 조각을 차례로 분류하고, 걸친 조각은 풀에서 칸을 잡아 사본을 굽는다. 프레임당 `BUDGET` 셀까지 — 다 구우면 PCUR=0 이 돼 더 안 돈다(정지 중 비용 0).
· **풀**: 스프라이트 셀 0xA0~0xBF(32칸 = VRAM 0x2800~0x2FFF). 8칸 묶음 넷의 비트맵 `G[4]` — 폭 32 는 짝수 칸, 높이 32 는 비트 1, 높이 64 는 비트 1·2 가 0 인 칸에서 시작해야 해서
  (VDC 가 패턴 번호의 그 비트를 버린다) 조각 모양마다 필요한 칸 모양(`NEED`)과 정렬(`ALIGN`)이 다르다. 16×64 조각의 셀은 c, c+2, c+4, c+6 이다(연속 4칸이 아님).
· **VRAM 복사**: 틱(IRQ) 쪽이 MAWR 를 바꿀 수 있어 4워드씩 SEI 로 묶고 덩이마다 MARR·MAWR 를 다시 쓴다. `$F7`(VDC 선택 그림자)=2 로 두고, 끝나면 프레임 후크가 원래 값(0)으로 돌린다.

코드는 뱅크 0x70(`$6000` 창 — 프레임 후크·스텁이 MPR3 에 잠깐 건다, 먼 호출 트램펄린이 돌아갈 때 MPR3·4 를 되돌린다), 데이터는 뱅크 0x73 끝 116B(`$8000` 창 — 맨 끝 10B 는 인터럽트 벡터 사본 자리라 그 앞).
파이썬 참조 구현(`ref_*`)이 같은 일을 하고, 시험(`tests/test_sprmask.py`)이 시뮬레이터로 돌린 결과와 바이트로 대조한다.
"""

import re

import asm65

# ── 자리 ──
CODE_BANK = 0x70
CODE_WINDOW = 0x6000
# 뱅크 0x70 의 FF 패딩은 세 토막으로 남아 있다(이름 · 시작 · 끝 — 뱅크 안 오프셋). 이웃이 자라 넘어오면 빌드가 멈춘다(`build.code_patches` 끝의 겹침 검사)
SEGS = (
    ("a", 0x1980, 0x1C00),  # 디버그 목록 코드(끝 +190A, 상한 = 이 시작값 — `debug_item_list`) 뒤 ~ 조각 보관소(+1C00) 앞: 계획자·표
    ("b", 0x1D40, 0x1E00),  # 조각 복사 루틴(+1D00, 50B) 뒤 ~ +1E00: 서명 검사
    ("c", 0x1EC0, 0x2000),  # 옛 단계 숫자 루틴(끝 +1EA7) 뒤 ~ 뱅크 끝: 셀 굽기
    ("d", 0x1E00, 0x1EC0),  # 옛 단계 숫자 루틴 자리(11-22 글리프 뱅크 꼬리로 나가 빈 FF 192B): 엔진 가림 스프라이트 루틴 후크 둘
)
DEBUG_LIST_LIMIT = CODE_WINDOW + SEGS[0][1]

DATA_BANK = 0x73
DATA_OFF = 0x1F82  # 뱅크 0x73 끝 116B(어절 판정 루틴 뒤 ~ `+1FF6` 인터럽트 벡터 사본(`hook.WCK_VEC_OFF`, 11-22) 앞) — 이미지에서 0 으로 구워 둔다
DATA_LEN = 116
D = 0x8000 + DATA_OFF
PRES = D  # 32
SIG = D + 32  # 7: 기준 x(2) · 기준 y(2) · 서술자 포인터(2) · 창 상태
PCUR = D + 39  # 계획자가 아직 안 본 조각 수(0 = 할 일 없음)
PY = D + 40  # 다음 조각의 서술자 색인
PEND = D + 41  # 서명이 막 바뀌었다 — 한 프레임 더 같으면 계획 시작
FLAG = D + 42  # 이번 프레임에 서명을 본 개체 번호 + 1(프레임 후크가 0 으로)
G = D + 43  # 4: 풀 묶음 비트맵
FX, FY, FW, FH, SIDX, AH, PL, NR = (D + 47 + i for i in range(8))
R = D + 55  # 8: 지울 사각형 둘 × [r0, r1, c0, c1](조각 패턴 좌표)
IDX, BUD, CA, CB, RA, RB, SRC0, DST0 = (D + 63 + i for i in range(8))
SLO, SHI, DLO, DHI, CH, OI, NB, CMLO, CMHI, RI = (D + 71 + i for i in range(10))
M = D + 84  # 32: 행마다 남길 비트(낮은 바이트 16 + 높은 바이트 16)
assert M + 32 == D + DATA_LEN == 0x9FF6  # 벡터 사본 6B 와 그 뒤 4B(`+1FFC~+1FFF`, 빈 FF)는 안 쓴다

POOL_CELL = 0xA0
POOL_N = 32
BUDGET = 8  # 프레임당 굽는 셀 수 상한(가장 큰 조각 = 8셀이 한 프레임에 들어가야 한다)
RING_KIND0, RING_KINDS = 0x78, 10  # 횃불 밝기 $C01E(7~39) >> 2 + 0x78 — 0x78~0x7A 는 조각 넷짜리 가장 작은 원

# 조각 모양(색인 = 폭 32 | 높이 코드 << 1)
WTAB = (16, 32, 16, 32, 16, 32, 16, 32)
HTAB = (16, 16, 32, 32, 32, 32, 64, 64)
NEED = (0x01, 0x03, 0x05, 0x0F, 0x05, 0x0F, 0x55, 0xFF)
ALIGN = (0, 1, 2, 3, 2, 3, 6, 7)
CNT = tuple(n.bit_count() for n in NEED)
# 창 픽셀 사각형 [x0, x1, y0, y1) — SAT 좌표 실측(스크린샷 줄 + 46 · x + 14), y 는 32 를 뺀 값(8비트에 담으려고)
YBIAS = 32
WIN_BOTTOM = (48, 224, 180 - YBIAS, 256 - YBIAS)
WIN_TOP = (48, 224, 96 - YBIAS, 176 - YBIAS)
WIN_MENU = (48, 112, 96 - YBIAS, 224 - YBIAS)
DLG_BOTTOM_Y0 = 45  # `winmask.DLG_BOTTOM[0]` — 대사 슬롯의 y0 이 이 값이면 아래 창
# 0xFFFF >> k 의 낮은 바이트 = U[k] · 높은 바이트 = U[k + 8]
U = bytes([0xFF] * 8 + [0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01, 0x00] + [0x00] * 8)

VLO, VHI = 0x0002, 0x0003

# ── 엔진 가림 스프라이트 루틴(같은 뱅크 0x70 `$6000` — SAT 루프가 조각마다 먼 호출 `$4F9F` 로 부른다) ──
# 메뉴가 열려 있으면(`$37B9`) 조각 밑 맵 셀을 16px 블록(셀 2×2)마다 훑어 창 셀이 든 블록에 가림 스프라이트를 한 장씩 깐다 → 한 줄 16장 한도를 넘겨 뒤 스프라이트가 빠진다
# (마스터 11-20 「시스템메뉴 열때 … 살짝 사각형」 둘 — 메뉴 열 옆 8×8 구멍(한 줄 17장) · 화면 위 띠 바로 밑 12×5(한 줄 20장)). 후크 둘로 **필요 없는 가림 장만** 뺀다:
#  · `eg_bits`(늘 건다): 블록 비트를 적는 자리(`$6120 LDA $0E · STA $612E,X`). 화면 위 띠(SAT y < 96) 셀 몫을 뺀다 — 띠에는 스프라이트가 애초에 안 보인다(메뉴를 닫은 화면에 가림 장이 0 인데도 안 보인다)
#  · `eg_gate`(메뉴 열이 떠 있는 동안만 — `sigchk` 가 자리를 갈아 끼우고, 열이 걷히면 스스로 원판 명령으로 되돌린다): `$6028 LDA $37B9`. 그 조각이 **잘린 그림 사본**(PRES 비트 7)으로 나가면
#    창 쪽 픽셀이 이미 지워져 있으니 가림 장이 필요 없다. 부 메뉴(슬롯 표에 없는 창)·대사·목록이 떠 있으면 원판대로 — 사본은 메뉴 열·대사 창만 안다
ENG_BITS_OFF = 0x0120
ENG_BITS_OLD = bytes.fromhex("a50e9d2e61")
ENG_GATE_OFF = 0x0028
ENG_GATE_OLD = bytes.fromhex("adb937")  # `LDA $37B9` — 이미지에는 원판 그대로 둔다(런타임에만 `JSR eg_gate` 로)
ENG_MENU_FLAG = 0x37B9
ENG_KIND = 0x3509  # 개체 종류(X = 개체 번호)
ENG_BITS, ENG_Y, ENG_CNT = 0x612E, 0xFE, 0x33  # 블록 비트 표 · 블록 y(SAT) · 남은 조각 수
VIEW_TOP = 96  # 맵 창 맨 윗줄(SAT y) — 그 위는 화면 위 띠


# ── 파이썬 참조 ──
def shape(ah: int) -> int:
    return (ah & 1) | ((ah >> 3) & 6)


def ref_classify(x: int, y: int, ah: int, wins) -> tuple[int, list]:
    """조각(SAT 좌표 x·y, 속성 높은 바이트) → (1 앞 | 2 통째로 안 | 0 걸침, 지울 사각형 [(r0, r1, c0, c1)] — 패턴 좌표(뒤집기 반영))."""
    s = shape(ah)
    w, h = WTAB[s], HTAB[s]
    yb = y - YBIAS
    if not (0 <= x <= 255 and 0 <= yb <= 255):
        return 1, []
    rects = []
    for x0, x1, y0, y1 in wins:
        c0, c1 = max(x0 - x, 0), min(x1 - x, w)
        r0, r1 = max(y0 - yb, 0), min(y1 - yb, h)
        if c0 >= c1 or r0 >= r1:
            continue
        if (c0, c1, r0, r1) == (0, w, 0, h):
            return 2, []
        if ah & 0x08:
            c0, c1 = w - c1, w - c0
        if ah & 0x80:
            r0, r1 = h - r1, h - r0
        rects.append((r0, r1, c0, c1))
    return (0, rects) if rects else (1, [])


def ref_alloc(g: list[int], s: int) -> int | None:
    """풀 묶음 비트맵 `g`(4)에서 모양 `s` 자리를 잡아 풀 색인을 돌려준다(없으면 None)."""
    for gi in range(4):
        for sh in range(8):
            if sh & ALIGN[s]:
                continue
            need = NEED[s] << sh
            if not g[gi] & need:
                g[gi] |= need
                return gi * 8 + sh
    return None


def ref_cell_mask(o: int, rects) -> list[int]:
    """조각 안 셀 `o`(비트 0 = 열, 그 위 = 행)의 행마다 남길 비트(16워드)."""
    cx, cy = (o & 1) * 16, (o >> 1) * 16
    m = [0xFFFF] * 16
    for r0, r1, c0, c1 in rects:
        a, b = min(max(c0 - cx, 0), 16), min(max(c1 - cx, 0), 16)
        ra, rb = min(max(r0 - cy, 0), 16), min(max(r1 - cy, 0), 16)
        if a >= b or ra >= rb:
            continue
        keep = (~(0xFFFF >> a) | (0xFFFF >> b)) & 0xFFFF
        for r in range(ra, rb):
            m[r] &= keep
    return m


def ref_build(vram: list[int], pat_lo: int, s: int, idx: int, rects) -> None:
    """원본 셀들을 풀 색인 `idx` 자리에 복사하면서 사각형을 지운다(VRAM 워드 리스트를 제자리에서 고친다)."""
    src0 = (pat_lo >> 1) & ~ALIGN[s] & 0xFF
    for o in range(8):
        if not NEED[s] >> o & 1:
            continue
        m = ref_cell_mask(o, rects)
        sa, da = (src0 + o) << 6, (POOL_CELL + idx + o) << 6
        for k in range(64):
            vram[da + k] = vram[sa + k] & m[k & 15]


def ref_plan(desc: bytes, bx: int, by: int, wins, vram: list[int]) -> list[int]:
    """서술자 하나를 끝까지 계획한 결과 PRES(색인 = 남은 조각 수) — 예산 무시."""
    n = desc[0]
    pres = [0] * 32
    g = [0] * 4
    for k in range(n):
        dx, dy, plo, _phi, ah = desc[1 + 5 * k : 6 + 5 * k]
        x = bx + (dx - 256 if dx & 0x80 else dx)
        y = by + (dy - 256 if dy & 0x80 else dy)
        kind, rects = ref_classify(x, y, ah, wins)
        q = n - k
        if kind:
            pres[q] = kind
            continue
        s = shape(ah)
        idx = ref_alloc(g, s)
        if idx is None:
            continue  # 풀이 모자라면 그 조각은 폴백(0)
        ref_build(vram, plo, s, idx, rects)
        pres[q] = 0xC0 + 2 * idx
    return pres


# ── 기계어 ──
class _Segs:
    """토막 셋에 나눠 어셈블한다 — 분기(rel)는 토막 안에서만, 절대 주소 라벨은 앞 회차가 모은 표(`ext`)에서 푼다(명령 길이가 값과 무관해 두 번 돌리면 맞는다)."""

    def __init__(self, ext: dict[str, int]):
        self.asm = {n: asm65.Asm(CODE_WINDOW + o) for n, o, _ in SEGS}
        self.ext = ext
        self.cur = None

    def seg(self, n: str):
        self.cur = self.asm[n]

    def L(self, name: str):
        self.cur.L(name)

    def raw(self, b: bytes):
        self.cur.raw(b)

    def op(self, mn: str, mode: str = "imp", arg=None):
        if isinstance(arg, str) and mode != "rel":
            m = re.fullmatch(r"(\w+?)([+-]\d+)?", arg)
            arg = (self.ext[m.group(1)] if self.ext else 0) + int(m.group(2) or 0)
        self.cur.op(mn, mode, arg)


def _asm(ext: dict[str, int], slot_mode_menu: int, slot_mode_dlg: int, slot_y0_dlg: int, slot_mode_rest: tuple[int, ...] = ()) -> _Segs:
    a = _Segs(ext)
    op, L = a.op, a.L
    a.seg("b")
    T0, T1, T2 = 0xFC, 0xFD, 0xFE  # 영 페이지 임시(SAT 루프가 조각마다 다시 채우는 칸 — 프레임 머리·스텁 머리에서는 비어 있다… 스텁에서는 `$FC~$FF` 가 살아 있으니 sigchk 는 안 쓴다)

    # ── sigchk: 어둠 원 첫 조각에서 프레임당 한 번. X·Y 보존. 서명이 같으면 그대로, 다르면 비우고 PEND=1, 같은 서명이 이어지면 계획 시작 ──
    L("sigchk")
    op("PHX")
    op("TXA")  # FLAG = 개체 번호 + 1 — 스텁이 「이 개체를 이번 프레임에 봤나」로 쓴다
    op("INC")
    op("STA", "abs", FLAG)
    op("LDA", "abs", slot_mode_dlg)
    op("BEQ", "rel", "sg_w1")
    op("LDA", "abs", slot_y0_dlg)
    op("ORA", "imm", 0x80)
    L("sg_w1")
    op("LDX", "abs", slot_mode_menu)
    op("BEQ", "rel", "sg_w2")
    op("ORA", "imm", 0x40)
    L("sg_w2")
    op("CMP", "imm", 0x40)  # 메뉴 열만 떠 있다 → 엔진 가림 루틴 머리를 `eg_gate` 로(이미 걸려 있어도 같은 바이트를 다시 쓴다). A 보존
    op("BNE", "rel", "sg_na")
    op("JSR", "abs", "eg_arm")
    L("sg_na")
    op("LDX", "imm", 0)
    op("CMP", "abs", SIG + 6)
    op("BEQ", "rel", "sg_c0")
    op("STA", "abs", SIG + 6)
    op("INX")
    L("sg_c0")
    for i, zp in enumerate((0x2E, 0x2F, 0x30, 0x31, 0xFA, 0xFB)):
        op("LDA", "zp", zp)
        op("CMP", "abs", SIG + i)
        op("BEQ", "rel", f"sg_c{i + 1}")
        op("STA", "abs", SIG + i)
        op("INX")
        L(f"sg_c{i + 1}")
    op("CPX", "imm", 0)
    op("BEQ", "rel", "sg_same")
    op("LDX", "imm", 31)
    L("sg_clr")
    op("STZ", "absx", PRES)
    op("DEX")
    op("BPL", "rel", "sg_clr")
    for i in range(4):
        op("STZ", "abs", G + i)
    op("STZ", "abs", PCUR)
    op("LDA", "imm", 1)
    op("STA", "abs", PEND)
    op("PLX")
    op("RTS")
    L("sg_same")
    op("LDA", "abs", PEND)
    op("BEQ", "rel", "sg_done")
    op("STZ", "abs", PEND)
    op("LDA", "izp", 0xFA)  # 조각 수
    op("STA", "abs", PCUR)
    op("LDA", "imm", 1)
    op("STA", "abs", PY)
    L("sg_done")
    op("PLX")
    op("RTS")

    # ── 엔진 가림 루틴 후크(머리말 「엔진 가림 스프라이트 루틴」) ──
    a.seg("d")
    site = CODE_WINDOW + ENG_GATE_OFF
    L("eg_bits")  # `LDA $0E · STA $612E,X` 대신(JSR + NOP 둘). Y 는 이 뒤에 안 쓰인다(`$6125 INX · RTS` → `PLY`)
    op("LDA", "zp", ENG_Y)
    op("CMP", "imm", VIEW_TOP)
    op("LDA", "zp", 0x0E)  # (LDA 는 C 를 안 건드린다)
    op("BCS", "rel", "eb_st")
    op("AND", "imm", 0x0C)  # 블록 윗줄 셀(비트 0·1)이 띠 안 — 아랫줄 셀(비트 2·3)만 남긴다
    op("LDY", "zp", ENG_Y)
    op("CPY", "imm", VIEW_TOP - 8)
    op("BCS", "rel", "eb_st")
    op("LDA", "imm", 0)  # 아랫줄도 띠 안
    L("eb_st")
    op("STA", "absx", ENG_BITS)
    op("RTS")
    L("eg_gate")  # `LDA $37B9` 대신 — Z=1 이면 엔진이 이 조각에 가림 장을 안 깐다. X(개체)·Y 보존
    op("LDA", "abs", ENG_MENU_FLAG)
    op("BEQ", "rel", "eg_out")
    op("LDA", "absx", ENG_KIND)
    op("SEC")
    op("SBC", "imm", RING_KIND0)
    op("CMP", "imm", RING_KINDS)
    op("BCS", "rel", "eg_yes")  # 어둠 원이 아니다 — 원판대로
    op("TMA", "mpr", 4)
    op("PHA")
    op("LDA", "imm", DATA_BANK)
    op("TAM", "mpr", 4)
    op("STZ", "zp", 0x0E)  # 임시(엔진은 `$6106` 에서 STZ 한 뒤에야 쓴다)
    op("LDA", "abs", slot_mode_menu)
    op("BNE", "rel", "eg_on")
    for i, b in enumerate(ENG_GATE_OLD):  # 메뉴 열이 걷혔다(부 메뉴) — 자리를 원판 명령으로 되돌린다(그 뒤로는 비용 0)
        op("LDA", "imm", b)
        op("STA", "abs", site + i)
    op("BRA", "rel", "eg_rs")
    L("eg_on")
    if slot_mode_rest:  # 목록·대사·기타 창이 같이 떠 있다 — 원판대로
        op("LDA", "abs", slot_mode_rest[0])
        for s in slot_mode_rest[1:]:
            op("ORA", "abs", s)
        op("BNE", "rel", "eg_rs")
    op("TXA")  # 이번 프레임에 이 개체의 서명을 아직 안 봤으면 지금 본다(스텁보다 먼저 불린다 — 묵은 PRES 를 안 믿으려고). 스텁은 FLAG 를 보고 건너뛴다
    op("INC")
    op("CMP", "abs", FLAG)
    op("BEQ", "rel", "eg_seen")
    op("JSR", "abs", "sigchk")
    op("BRA", "rel", "eg_look")
    L("eg_seen")
    op("LDA", "abs", SIG + 5)  # 프레임 후크가 서명을 못 쓰게 해 뒀다(창이 다 꺼졌던 프레임) — PRES 가 묵었다
    op("BEQ", "rel", "eg_rs")
    L("eg_look")
    op("PHX")
    op("LDX", "zp", ENG_CNT)
    op("LDA", "absx", PRES)
    op("PLX")
    op("STA", "zp", 0x0E)
    L("eg_rs")
    op("PLA")
    op("TAM", "mpr", 4)
    op("LDA", "zp", 0x0E)
    op("BMI", "rel", "eg_no")  # 사본으로 나간다 — 가림 장 없이
    L("eg_yes")
    op("LDA", "imm", 1)
    op("RTS")
    L("eg_no")
    op("LDA", "imm", 0)
    L("eg_out")
    op("RTS")
    L("eg_arm")  # A 보존
    op("PHA")
    for i, b in enumerate(b"\x20" + (ext.get("eg_gate", 0)).to_bytes(2, "little")):
        op("LDA", "imm", b)
        op("STA", "abs", site + i)
    op("PLA")
    op("RTS")

    # ── plan: 프레임 머리(PCUR ≠ 0 일 때만 불린다). MPR4 = 뱅크 0x73 · MPR5 = 뱅크 0x69(서술자) ──
    a.seg("a")
    L("plan")
    op("LDA", "abs", SIG + 4)
    op("STA", "zp", 0xFA)
    op("LDA", "abs", SIG + 5)
    op("STA", "zp", 0xFB)
    op("LDA", "imm", BUDGET)
    op("STA", "abs", BUD)
    op("LDA", "imm", 2)
    op("STA", "zp", 0xF7)
    L("pl_loop")
    op("LDY", "abs", PY)
    op("LDX", "imm", 0)  # x = 기준 x + 부호 확장(dx) — 높은 바이트가 0 이 아니면 창과 못 만난다
    op("LDA", "izpy", 0xFA)
    op("BPL", "rel", "pl_x1")
    op("DEX")
    L("pl_x1")
    op("CLC")
    op("ADC", "abs", SIG + 0)
    op("STA", "abs", FX)
    op("TXA")
    op("ADC", "abs", SIG + 1)
    op("BEQ", "rel", "pl_xok")
    op("JMP", "abs", "pl_front")
    L("pl_xok")
    op("INY")
    op("LDX", "imm", 0)
    op("LDA", "izpy", 0xFA)
    op("BPL", "rel", "pl_y1")
    op("DEX")
    L("pl_y1")
    op("CLC")
    op("ADC", "abs", SIG + 2)
    op("STA", "abs", FY)
    op("TXA")
    op("ADC", "abs", SIG + 3)
    op("TAX")
    op("LDA", "abs", FY)
    op("SEC")
    op("SBC", "imm", YBIAS)
    op("STA", "abs", FY)
    op("TXA")
    op("SBC", "imm", 0)
    op("BEQ", "rel", "pl_yok")
    op("JMP", "abs", "pl_front")
    L("pl_yok")
    op("INY")
    op("LDA", "izpy", 0xFA)
    op("STA", "abs", PL)
    op("INY")
    op("INY")
    op("LDA", "izpy", 0xFA)
    op("STA", "abs", AH)
    op("AND", "imm", 1)
    op("STA", "zp", T0)
    op("LDA", "abs", AH)
    op("LSR")
    op("LSR")
    op("LSR")
    op("AND", "imm", 6)
    op("ORA", "zp", T0)
    op("STA", "abs", SIDX)
    op("TAX")
    op("LDA", "absx", "wtab")
    op("STA", "abs", FW)
    op("LDA", "absx", "htab")
    op("STA", "abs", FH)
    op("STZ", "abs", NR)
    op("LDA", "abs", slot_mode_menu)
    op("BEQ", "rel", "pl_nomenu")
    op("LDX", "imm", 8)
    op("JSR", "abs", "clipwin")
    op("BCS", "rel", "pl_behind")
    L("pl_nomenu")
    op("LDA", "abs", slot_mode_dlg)
    op("BEQ", "rel", "pl_nodlg")
    op("LDX", "imm", 0)
    op("LDA", "abs", slot_y0_dlg)
    op("CMP", "imm", DLG_BOTTOM_Y0)
    op("BEQ", "rel", "pl_dlg")
    op("LDX", "imm", 4)
    L("pl_dlg")
    op("JSR", "abs", "clipwin")
    op("BCS", "rel", "pl_behind")
    L("pl_nodlg")
    op("LDA", "abs", NR)
    op("BEQ", "rel", "pl_front")
    op("LDX", "abs", SIDX)  # 걸침 — 예산이 모자라면 이 조각부터 다음 프레임에
    op("LDA", "abs", BUD)
    op("CMP", "absx", "cnt")
    op("BCC", "rel", "pl_done")
    op("SBC", "absx", "cnt")
    op("STA", "abs", BUD)
    op("JSR", "abs", "alloc")
    op("BCS", "rel", "pl_adv")  # 풀이 모자람 — PRES 0(폴백) 그대로
    op("JSR", "abs", "build")
    op("LDA", "abs", IDX)
    op("ASL")
    op("ORA", "imm", 0xC0)
    op("BRA", "rel", "pl_set")
    L("pl_front")
    op("LDA", "imm", 1)
    op("BRA", "rel", "pl_set")
    L("pl_behind")
    op("LDA", "imm", 2)
    L("pl_set")
    op("LDX", "abs", PCUR)
    op("STA", "absx", PRES)
    L("pl_adv")
    op("LDA", "abs", PY)
    op("CLC")
    op("ADC", "imm", 5)
    op("STA", "abs", PY)
    op("DEC", "abs", PCUR)
    op("BEQ", "rel", "pl_done")
    op("JMP", "abs", "pl_loop")
    L("pl_done")
    op("RTS")

    # ── clipwin: X = 창 표 색인. C=1 통째로 안 · C=0 이면 걸친 만큼 R 에 한 칸 더(없으면 그대로) ──
    L("cw_none")
    op("CLC")
    op("RTS")
    L("clipwin")
    for pos, size, e0, lo, hi in ((FX, FW, 0, CA, CB), (FY, FH, 2, RA, RB)):
        op("LDA", "absx", f"win+{e0 + 1}")
        op("SEC")
        op("SBC", "abs", pos)
        op("BCC", "rel", "cw_none")
        op("BEQ", "rel", "cw_none")
        op("CMP", "abs", size)
        op("BCC", "rel", f"cw_b{e0}")
        op("LDA", "abs", size)
        L(f"cw_b{e0}")
        op("STA", "abs", hi)
        op("LDA", "absx", f"win+{e0}")
        op("SEC")
        op("SBC", "abs", pos)
        op("BCS", "rel", f"cw_a{e0}")
        op("LDA", "imm", 0)
        L(f"cw_a{e0}")
        op("STA", "abs", lo)
        op("CMP", "abs", hi)
        op("BCS", "rel", "cw_none")
    op("LDA", "abs", CA)
    op("ORA", "abs", RA)
    op("BNE", "rel", "cw_part")
    op("LDA", "abs", CB)
    op("CMP", "abs", FW)
    op("BNE", "rel", "cw_part")
    op("LDA", "abs", RB)
    op("CMP", "abs", FH)
    op("BNE", "rel", "cw_part")
    op("SEC")
    op("RTS")
    L("cw_part")
    op("LDA", "abs", AH)
    op("AND", "imm", 0x08)
    op("BEQ", "rel", "cw_nxf")
    op("LDA", "abs", FW)
    op("SEC")
    op("SBC", "abs", CB)
    op("TAY")
    op("LDA", "abs", FW)
    op("SEC")
    op("SBC", "abs", CA)
    op("STA", "abs", CB)
    op("STY", "abs", CA)
    L("cw_nxf")
    op("LDA", "abs", AH)
    op("BPL", "rel", "cw_nyf")
    op("LDA", "abs", FH)
    op("SEC")
    op("SBC", "abs", RB)
    op("TAY")
    op("LDA", "abs", FH)
    op("SEC")
    op("SBC", "abs", RA)
    op("STA", "abs", RB)
    op("STY", "abs", RA)
    L("cw_nyf")
    op("LDA", "abs", NR)
    op("ASL")
    op("ASL")
    op("TAY")
    for i, src in enumerate((RA, RB, CA, CB)):
        op("LDA", "abs", src)
        op("STA", "absy", R + i)
    op("INC", "abs", NR)
    op("CLC")
    op("RTS")

    # ── alloc: SIDX → IDX. C=1 이면 자리 없음 ──
    L("alloc")
    op("LDX", "abs", SIDX)
    op("LDA", "absx", "align")
    op("STA", "zp", T1)
    op("LDX", "imm", 0)
    L("al_g")
    op("LDY", "abs", SIDX)
    op("LDA", "absy", "need")
    op("STA", "zp", T0)
    op("LDY", "imm", 0)
    L("al_s")
    op("TYA")
    op("AND", "zp", T1)
    op("BNE", "rel", "al_n")
    op("LDA", "zp", T0)
    op("AND", "absx", G)
    op("BNE", "rel", "al_n")
    op("LDA", "zp", T0)
    op("ORA", "absx", G)
    op("STA", "absx", G)
    op("TXA")
    op("ASL")
    op("ASL")
    op("ASL")
    op("STA", "abs", IDX)
    op("TYA")
    op("CLC")
    op("ADC", "abs", IDX)
    op("STA", "abs", IDX)
    op("CLC")
    op("RTS")
    L("al_n")
    op("ASL", "zp", T0)
    op("INY")
    op("CPY", "imm", 8)
    op("BNE", "rel", "al_s")
    op("INX")
    op("CPX", "imm", 4)
    op("BNE", "rel", "al_g")
    op("SEC")
    op("RTS")

    # ── build: PL·SIDX·IDX·R[NR] → 풀 셀들 ──
    L("build")
    op("LDX", "abs", SIDX)
    op("LDA", "absx", "align")
    op("EOR", "imm", 0xFF)
    op("STA", "zp", T0)
    op("LDA", "abs", PL)
    op("LSR")
    op("AND", "zp", T0)
    op("STA", "abs", SRC0)
    op("LDA", "abs", IDX)
    op("CLC")
    op("ADC", "imm", POOL_CELL)
    op("STA", "abs", DST0)
    op("LDA", "absx", "need")
    op("STA", "abs", NB)
    op("STZ", "abs", OI)
    L("bd_c")
    op("LSR", "abs", NB)
    op("BCC", "rel", "bd_n")
    op("JSR", "abs", "cell")
    L("bd_n")
    op("INC", "abs", OI)
    op("LDA", "abs", NB)
    op("BNE", "rel", "bd_c")
    op("RTS")

    # ── cell: 셀 OI 한 칸 — 행 마스크를 만들고 64워드를 4워드씩 옮긴다 ──
    a.seg("c")
    L("cell")
    op("LDX", "imm", 31)
    op("LDA", "imm", 0xFF)
    L("ce_f")
    op("STA", "absx", M)
    op("DEX")
    op("BPL", "rel", "ce_f")
    op("LDA", "abs", NR)
    op("STA", "zp", T2)
    op("STZ", "abs", RI)
    L("ce_r")
    op("LDX", "abs", RI)
    op("LDA", "abs", OI)  # 열 오프셋 = (OI & 1) × 16
    op("AND", "imm", 1)
    for _ in range(4):
        op("ASL")
    op("STA", "zp", T1)
    op("LDA", "absx", R + 2)
    op("JSR", "abs", "clamp")
    op("STA", "abs", CA)
    op("LDA", "absx", R + 3)
    op("JSR", "abs", "clamp")
    op("STA", "abs", CB)
    op("LDA", "abs", OI)  # 행 오프셋 = (OI >> 1) × 16
    op("AND", "imm", 6)
    for _ in range(3):
        op("ASL")
    op("STA", "zp", T1)
    op("LDA", "absx", R + 0)
    op("JSR", "abs", "clamp")
    op("STA", "abs", RA)
    op("LDA", "absx", R + 1)
    op("JSR", "abs", "clamp")
    op("STA", "abs", RB)
    op("LDA", "abs", CA)
    op("CMP", "abs", CB)
    op("BCS", "rel", "ce_skip")
    op("LDA", "abs", RA)
    op("CMP", "abs", RB)
    op("BCS", "rel", "ce_skip")
    for tbl, dst in (("u", CMLO), ("u+8", CMHI)):
        op("LDX", "abs", CA)
        op("LDA", "absx", tbl)
        op("EOR", "imm", 0xFF)
        op("LDX", "abs", CB)
        op("ORA", "absx", tbl)
        op("STA", "abs", dst)
    op("LDY", "abs", RA)
    L("ce_m")
    op("LDA", "absy", M)
    op("AND", "abs", CMLO)
    op("STA", "absy", M)
    op("LDA", "absy", M + 16)
    op("AND", "abs", CMHI)
    op("STA", "absy", M + 16)
    op("INY")
    op("CPY", "abs", RB)
    op("BNE", "rel", "ce_m")
    L("ce_skip")
    op("LDA", "abs", RI)
    op("CLC")
    op("ADC", "imm", 4)
    op("STA", "abs", RI)
    op("DEC", "zp", T2)
    op("BEQ", "rel", "ce_rd")
    op("JMP", "abs", "ce_r")
    L("ce_rd")
    for base, lo, hi in ((SRC0, SLO, SHI), (DST0, DLO, DHI)):  # VRAM 주소 = 셀 << 6
        op("STZ", "abs", lo)
        op("LDA", "abs", base)
        op("CLC")
        op("ADC", "abs", OI)
        op("LSR")
        op("ROR", "abs", lo)
        op("LSR")
        op("ROR", "abs", lo)
        op("STA", "abs", hi)
    op("LDA", "imm", 16)
    op("STA", "abs", CH)
    op("LDY", "imm", 0)
    L("ce_ch")
    op("PHP")
    op("SEI")
    op("ST0", "imm", 1)
    op("LDA", "abs", SLO)
    op("STA", "abs", VLO)
    op("LDA", "abs", SHI)
    op("STA", "abs", VHI)
    op("ST0", "imm", 0)
    op("LDA", "abs", DLO)
    op("STA", "abs", VLO)
    op("LDA", "abs", DHI)
    op("STA", "abs", VHI)
    op("ST0", "imm", 2)
    op("LDX", "imm", 4)
    L("ce_w")
    op("LDA", "abs", VLO)
    op("AND", "absy", M)
    op("STA", "abs", VLO)
    op("LDA", "abs", VHI)
    op("AND", "absy", M + 16)
    op("STA", "abs", VHI)
    op("INY")
    op("DEX")
    op("BNE", "rel", "ce_w")
    op("PLP")
    op("TYA")
    op("AND", "imm", 15)
    op("TAY")
    for lo, hi in ((SLO, SHI), (DLO, DHI)):
        op("LDA", "abs", lo)
        op("CLC")
        op("ADC", "imm", 4)
        op("STA", "abs", lo)
        op("BCC", "rel", f"ce_i{lo:x}")
        op("INC", "abs", hi)
        L(f"ce_i{lo:x}")
    op("DEC", "abs", CH)
    op("BNE", "rel", "ce_ch")
    op("RTS")

    a.seg("b")
    L("clamp")  # A = clamp(A − T1, 0, 16)
    op("SEC")
    op("SBC", "zp", T1)
    op("BCS", "rel", "cl_1")
    op("LDA", "imm", 0)
    L("cl_1")
    op("CMP", "imm", 17)
    op("BCC", "rel", "cl_2")
    op("LDA", "imm", 16)
    L("cl_2")
    op("RTS")

    a.seg("a")
    L("wtab")
    a.raw(bytes(WTAB))
    L("htab")
    a.raw(bytes(HTAB))
    L("need")
    a.raw(bytes(NEED))
    L("align")
    a.raw(bytes(ALIGN))
    L("cnt")
    a.raw(bytes(CNT))
    L("win")
    a.raw(bytes(WIN_BOTTOM + WIN_TOP + WIN_MENU))
    L("u")
    a.raw(U)
    return a


def _built() -> tuple[dict[str, bytes], dict[str, int]]:
    import winmask

    assert winmask.BANK == DATA_BANK  # `eg_gate` 가 MPR4 에 이 뱅크 하나만 걸고 슬롯 표와 PRES 를 다 읽는다
    rest = tuple(winmask.slot_addr(k) for k in range(winmask.NSLOT) if k not in (winmask.SLOT_MENU, winmask.SLOT_DLG))
    slots = (winmask.slot_addr(winmask.SLOT_MENU), winmask.slot_addr(winmask.SLOT_DLG), winmask.slot_addr(winmask.SLOT_DLG, 1), rest + (winmask.slot_addr(winmask.SLOT_DLG),))
    ext: dict[str, int] = {}
    for _ in range(2):
        a = _asm(ext, *slots)
        out = {n: x.bytes() for n, x in a.asm.items()}
        ext = {k: v for x in a.asm.values() for k, v in x.labels.items()}
    for n, o, e in SEGS:
        assert o + len(out[n]) <= e, (n, len(out[n]), e - o)
    return out, ext


def segments() -> list[tuple[int, bytes]]:
    """(뱅크 0x70 안 오프셋, 코드) 셋."""
    out, _ = _built()
    return [(o, out[n]) for n, o, _ in SEGS]


def labels() -> dict[str, int]:
    return _built()[1]


def engine_patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """(이름, 뱅크, 뱅크 안 오프셋, 원판, 새) — 엔진 가림 루틴의 블록 비트 자리를 `eg_bits` 로. 머리(`$6028`)는 원판 그대로(같은 바이트를 써서 원판 값만 확인한다 — 런타임에 `sigchk` 가 갈아 끼운다)."""
    bits = b"\x20" + labels()["eg_bits"].to_bytes(2, "little") + b"\xea\xea"
    return [("bits", CODE_BANK, ENG_BITS_OFF, ENG_BITS_OLD, bits), ("gate", CODE_BANK, ENG_GATE_OFF, ENG_GATE_OLD, ENG_GATE_OLD)]


def data_init() -> bytes:
    return bytes(DATA_LEN)


def check_descriptors(bank69: bytes) -> None:
    """원본 뱅크 0x69 의 어둠 원 서술자가 이 모듈의 가정(조각 ≤ 31 · 패턴 높은 바이트 0 · 원본 셀이 풀과 안 겹침)에 맞나 — 빌드가 부른다."""
    for kind in range(RING_KIND0, RING_KIND0 + RING_KINDS):
        lo, hi = bank69[0x09EE + kind * 2], bank69[0x09EE + kind * 2 + 1]
        off = (hi & 0x1F) << 8 | lo
        n = bank69[off]
        assert 1 <= n <= 31, (hex(kind), n)
        for k in range(n):
            _dx, _dy, plo, phi, ah = bank69[off + 1 + 5 * k : off + 6 + 5 * k]
            assert phi == 0, (hex(kind), k, phi)
            assert (plo >> 1) + 8 <= POOL_CELL, (hex(kind), k, plo)
            assert (ah >> 4) & 3 != 2, (hex(kind), k, ah)  # 높이 코드 2 는 안 쓴다(에뮬레이터마다 해석이 갈린다)


if __name__ == "__main__":
    for (n, o, e), (_, b) in zip(SEGS, segments(), strict=True):
        print(f"sprmask {n}: {len(b)}B @ bank {CODE_BANK:#x}+{o:#x} (자리 {e - o}B)")
    print(f"data {DATA_LEN}B @ bank {DATA_BANK:#x}+{DATA_OFF:#x}")
    for k, v in labels().items():
        if k in ("sigchk", "plan", "clipwin", "alloc", "build", "cell"):
            print(f"  {k} = ${v:04X}")
