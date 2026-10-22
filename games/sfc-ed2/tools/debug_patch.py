"""sfc-ed2 시험 빌드 전용 디버그 입력 — `ED_DEBUG=1` + 꼬리표 `test-*` 일 때만 build.py 가 부른다(제품 롬은 한 바이트도 안 바뀐다).

원판의 디버그 명령(`$137A` 비트7 + 선택 번호, 입력 루프 `$C1:E2A5`)은 개발용 주변기기가 `$1377~$1380` 에 바이트를 채워야 열린다.
여기서는 입력 루프의 「버튼이 눌린 갈래」(`$C1:E306` — `lda $1359 / bit $1B06`)에 훅을 달아, **L+R+Select 를 누른 채** 다른 버튼을 누르면
같은 변수(`$137A`·`$137B~$1380`·`$0B57`)를 직접 채운다. 명령 번호표는 `docs/status.md` 「디버그 빌드」.

패드 변수: `$1B06`=`$0028`(A 80 · X 40 · L 20 · R 10), `$1B07`=`$0029`(B 80 · Y 40 · Select 20 · Start 10 · ↑08 ↓04 ←02 →01).
타이틀 = `$1B95`==0(`$0131` 비트7 자연히 켜짐), 필드 주메뉴 = `$1B95`≠0. 방향키 넷은 어디서나 `$0B57` 플래그를 하나씩 켠다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

HOOK = 0xC1E306  # `AD 59 13 2C 06 1B` (lda $1359 / bit $1B06) — 6바이트를 `JSL stub / NOP NOP` 으로
HOOK_OLD = bytes.fromhex("AD59132C061B")
STUB_OFF = 0x1FFE00  # 롬 꼬리(2MB 칸 끝 512B) — 비어 있어야 한다
STUB_LIMIT = 0x1C0  # 첫 스텁(입력 조합) 한도 — 뒤 0x40B 는 전투 스킵 스텁 자리
SKIP_OFF = STUB_OFF + STUB_LIMIT
HOOK2 = 0xC19CE4  # `AD BF 11 29 02`(lda $11BF / and #$02) — 랜덤 조우 판정(`$C1:9CE1`)을 `JSL stub2 / NOP` 으로
HOOK2_OLD = bytes.fromhex("ADBF112902")
SKIP_FLAG = 0x0B59  # 전투 스킵 켜짐 = $A5 (세이브 영역 밖 · 원판이 안 쓰는 칸 — 초기값 0 이 아니어도 우연히 켜지지 않게 매직값)
WARP_FLAGS = range(0x441, 0x472)  # 매직 코드가 켜는 전역 플래그 49개 — `$C1:8BD6` 가 `$0167+(f>>3)` 의 비트 `f&7` 로 푼다


class Asm:
    def __init__(self):
        self.b = bytearray()
        self.lab = {}
        self.fix = []
        self.fix16 = []

    def raw(self, *x):
        self.b += bytes(x)

    def label(self, n):
        self.lab[n] = len(self.b)

    def br(self, op, n):
        self.b += bytes([op, 0])
        self.fix.append((len(self.b) - 1, n))

    def brl(self, n):
        self.b += bytes([0x82, 0, 0])
        self.fix16.append((len(self.b) - 2, n))

    def far(self, op, n):
        """멀리 있는 `done` 으로: 조건을 뒤집어 `BRL` 을 건너뛴다(8비트 상대 분기는 ±127B)."""
        self.b += bytes([op ^ 0x20, 3, 0x82, 0, 0])
        self.fix16.append((len(self.b) - 2, n))

    def done(self) -> bytes:
        for pos, n in self.fix:
            rel = self.lab[n] - (pos + 1)
            assert -128 <= rel <= 127, (n, rel)
            self.b[pos] = rel & 0xFF
        for pos, n in self.fix16:
            rel = self.lab[n] - (pos + 2)
            self.b[pos : pos + 2] = (rel & 0xFFFF).to_bytes(2, "little")
        return bytes(self.b)


def stub() -> bytes:
    a = Asm()
    LDA, AND, CMP, STA, ORA, STZ = 0xAD, 0x29, 0xC9, 0x8D, 0x09, 0x9C
    BNE, BEQ, BRA = 0xD0, 0xF0, 0x80

    def lda_abs(x): a.raw(LDA, x & 255, x >> 8)
    def sta_abs(x): a.raw(STA, x & 255, x >> 8)
    def stz_abs(x): a.raw(STZ, x & 255, x >> 8)
    def lda_i(v): a.raw(0xA9, v)

    lda_abs(0x1B06); a.raw(AND, 0x30); a.raw(CMP, 0x30); a.far(BNE, "done")      # L+R
    lda_abs(0x1B07); a.raw(AND, 0x20); a.far(BEQ, "done")                        # Select
    lda_abs(0x137A); a.far(BNE, "done")                                          # 이미 명령 대기 중
    # ── 방향키: 플래그 하나씩(타이틀·필드 공통 — 능력치 최대는 새 게임·이어하기 때만 먹는다) ──
    for bit, flag in ((0x08, 0x10), (0x04, 0x20), (0x02, 0x0F), (0x01, 0x40)):  # ↑경험치·골드 2배 · ↓성장 2배 · ←능력치 최대 · →맵 공개
        lbl = f"nd{bit}"
        lda_abs(0x1B07); a.raw(AND, bit); a.br(BEQ, lbl)
        lda_abs(0x0B57); a.raw(ORA, flag); sta_abs(0x0B57); a.brl("done")
        a.label(lbl)
    lda_abs(0x1B95); a.br(BNE, "field")
    # ── 타이틀 ($1B95==0) ──
    lda_abs(0x1B06); a.raw(AND, 0x40); a.br(BEQ, "t_y")                         # +X: 플래그 전부(능력치 최대·경험치/골드 2배·성장 2배·맵 공개)
    lda_abs(0x0B57); a.raw(ORA, 0x7F); sta_abs(0x0B57); a.brl("done")
    a.label("t_y")
    lda_abs(0x1B07); a.raw(AND, 0x40); a.br(BEQ, "t_st")                        # +Y: 느닷없이 엔딩
    stz_abs(0x137B); lda_i(0x81); sta_abs(0x137A); a.brl("done")
    a.label("t_st")
    lda_abs(0x1B07); a.raw(AND, 0x10); a.br(BEQ, "t_b")                         # +Start: 사운드 모드
    stz_abs(0x137D); lda_i(0x85); sta_abs(0x137A); a.brl("done")
    a.label("t_b")
    lda_abs(0x1B07); a.raw(AND, 0x80); a.far(BEQ, "done")                        # +B: 몬스터 일람
    lda_i(0x09); sta_abs(0x137C); lda_i(0x84); sta_abs(0x137A); a.brl("done")
    # ── 필드 주메뉴 ($1B95≠0) ──
    a.label("field")
    lda_abs(0x1B07); a.raw(AND, 0x40); a.br(BEQ, "f_st")                        # +Y: 전투 스킵 토글(랜덤 조우를 판정 단계에서 지운다)
    lda_abs(SKIP_FLAG); a.raw(CMP, 0xA5); a.br(BEQ, "skip_off")
    lda_i(0xA5); sta_abs(SKIP_FLAG); a.brl("done")
    a.label("skip_off")
    stz_abs(SKIP_FLAG); a.brl("done")
    a.label("f_st")
    lda_abs(0x1B07); a.raw(AND, 0x10); a.br(BEQ, "f_x")                         # +Start: 워프 등록 49칸만 켠다(아이템은 안 줌)
    masks = {}
    for f in WARP_FLAGS:
        masks[0x167 + (f >> 3)] = masks.get(0x167 + (f >> 3), 0) | (1 << (f & 7))
    for addr, m in sorted(masks.items()):
        lda_abs(addr); a.raw(ORA, m); sta_abs(addr)
    a.brl("done")
    a.label("f_x")
    lda_abs(0x1B06); a.raw(AND, 0x40); a.far(BEQ, "done")                        # +X: 매직 코드(전 아이템 지급 + 워프 해방)
    for addr, v in ((0x137B, 0x99), (0x137C, 0x96), (0x137D, 0x18), (0x137E, 0x83), (0x137F, 0x48), (0x1380, 0x30)):
        lda_i(v); sta_abs(addr)
    lda_abs(0x0131); a.raw(ORA, 0x80); sta_abs(0x0131)                          # 주메뉴 목록 루프는 비트7 이 꺼져 있다
    lda_i(0x80); sta_abs(0x137A)
    a.label("done")
    a.raw(0xAD, 0x59, 0x13)        # lda $1359   (원래 명령)
    a.raw(0x2C, 0x06, 0x1B)        # bit $1B06
    a.raw(0x6B)                    # rtl
    return a.done()


def skip_stub() -> bytes:
    """랜덤 조우 판정(`$C1:9CE4` 의 `lda $11BF / and #$02`)을 대신한다 — 스킵이 켜지면 조우 비트를 지우고 Z=1 로 돌아간다(호출자는 곧바로 `beq`)."""
    return bytes.fromhex(
        "AD590B" "C9A5" "D006"        # lda $0B59 / cmp #$A5 / bne normal
        "9CBF11" "A900" "6B"          # stz $11BF / lda #$00 / rtl
        "ADBF11" "2902" "6B"          # normal: lda $11BF / and #$02 / rtl
    )


def apply(rom: bytes) -> bytes:
    r = bytearray(rom)
    s = stub()
    assert len(s) <= STUB_LIMIT, len(s)
    if set(r[STUB_OFF : STUB_OFF + 0x200]) - {0x00, 0xFF}:
        raise SystemExit("디버그 훅 자리($DF:FE00~)가 비어 있지 않다")
    h = common.snes2off(HOOK)
    if bytes(r[h : h + 6]) != HOOK_OLD:
        raise SystemExit("디버그 훅 자리가 원본과 다르다")
    r[STUB_OFF : STUB_OFF + len(s)] = s
    sn = common.off2snes(STUB_OFF)
    r[h : h + 6] = bytes([0x22, sn & 255, (sn >> 8) & 255, sn >> 16, 0xEA, 0xEA])
    k = skip_stub()
    r[SKIP_OFF : SKIP_OFF + len(k)] = k
    h2 = common.snes2off(HOOK2)
    if bytes(r[h2 : h2 + 5]) != HOOK2_OLD:
        raise SystemExit("전투 스킵 훅 자리가 원본과 다르다")
    sk = common.off2snes(SKIP_OFF)
    r[h2 : h2 + 5] = bytes([0x22, sk & 255, (sk >> 8) & 255, sk >> 16, 0xEA])
    return bytes(r)


if __name__ == "__main__":
    s = stub()
    print(len(s), "B", s.hex())
