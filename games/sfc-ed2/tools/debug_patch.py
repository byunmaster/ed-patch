"""sfc-ed2 디버그 입력 — 제품 롬에 들어간다(마스터 10-24 「제품에 넣자. 빌드 2개 만드는 건 용량 낭비」). 새 기능은 없고, 원판에 남은 디버그 명령을 여는 입구만 단다.

원판의 디버그 명령(`$137A` 비트7 + 선택 번호, 입력 루프 `$C1:E2A5`)은 개발용 주변기기가 `$1377~$1380` 에 바이트를 채워야 열린다.
입구는 입력 루프의 「버튼이 눌린 갈래」(`$C1:E306` — `lda $1359 / bit $1B06`) 하나다. 이 갈래는 타이틀 메뉴·필드 주메뉴(B)가 열려 있는 동안 버튼이 눌려 있으면 3프레임쯤마다 돈다.
1. **열쇠**: **L+R+Select 만 정확히 1초(60프레임)** 누르면 디버그 입력이 켜진다(다시 1초면 꺼진다). 다른 버튼이 섞이면 세던 것이 0 으로 돌아간다.
   공통 열쇠 Start+A+B 를 필드에서 직접 받을 수 없다(실측 10-24): 필드의 A·B·Start·Select·X·Y·L·R 은 전부 누르는 즉시 창·동작을 여는 단축키라 먼저 눌린 쪽이 새어 나가고
   (Start = 세이브 창, Select = 로드 창, B = 주메뉴 …) 입력을 가리거나 미루면 일반 플레이 입력 전체가 바뀐다. 메뉴 안에서는 L·R·Select 가 아무 일도 안 해 새지 않는다.
   켜짐 표지는 WRAM `$0B5B`=`$A5`(세이브 밖 · 원판이 안 쓰는 칸 — 초기값 0 이 아니어도 우연히 켜지지 않게 매직값), 세는 값은 `$0B5A`·마지막 프레임 `$0B5C`.
2. **명령**: 켜진 뒤에만, **L+R+Select 를 누른 채** 다른 버튼을 누르면 같은 변수(`$137A`·`$137B~$1380`·`$0B57`)를 직접 채운다.
   명령 번호표는 `docs/status.md` 「디버그 입구」. 시험 롬에만 있던 전투 스킵·워프 등록은 원판에 없던 기능이라 뺐다.

패드 변수: `$1B06`=`$0028`(A 80 · X 40 · L 20 · R 10), `$1B07`=`$0029`(B 80 · Y 40 · Select 20 · Start 10 · ↑08 ↓04 ←02 →01).
타이틀 = `$1B95`==0(`$0131` 비트7 자연히 켜짐), 필드 주메뉴 = `$1B95`≠0. 방향키 넷은 어디서나 `$0B57` 플래그를 하나씩 켠다.
스텁은 뱅크 `$C0` 빈 자리에 두고(`patches.PATCHES` 가 원본 0xFF 인지 확인하며 쓴다) 입구 한 곳을 `JSL` 로 돌린다.
"""

HOOK = 0xC1E306  # `AD 59 13 2C 06 1B` (lda $1359 / bit $1B06) — 6바이트를 `JSL stub / NOP NOP` 으로
HOOK_OLD = bytes.fromhex("AD59132C061B")
CMD_STUB = 0xC0FD60  # 뱅크 $C0 빈 자리(0xFF) — 스텁(`$C0:FF00` 앞까지 416B 한도 — 그 뒤는 사운드 옵션 문자열)
CMD_LIMIT = 0x1A0
UNLOCK = 0x0B5B  # 디버그 켜짐 = $A5
HOLD_CNT = 0x0B5A  # Start+A+B 를 누른 프레임 수
HOLD_FRAMES = 60
HOLD_STALE = 12  # 열쇠를 누르는 동안 이 갈래는 3프레임쯤마다 돈다 — 이보다 뜸하면 중간에 뗀 것으로 본다
HOLD_LAST = 0x0B5C  # 마지막으로 센 프레임 번호(`$0027`)
SE_ON, SE_OFF = 0x03, 0x06  # `jsl $C0:07A1` 의 소리 번호 — 원판 디버그 명령이 받아들일 때(03)·거부할 때(06) 내는 소리


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


LDA, AND, CMP, STA, ORA, STZ = 0xAD, 0x29, 0xC9, 0x8D, 0x09, 0x9C
BNE, BEQ, BRA, BCS = 0xD0, 0xF0, 0x80, 0xB0


def _helpers(a: Asm):
    def lda_abs(x): a.raw(LDA, x & 255, x >> 8)
    def sta_abs(x): a.raw(STA, x & 255, x >> 8)
    def stz_abs(x): a.raw(STZ, x & 255, x >> 8)
    def lda_i(v): a.raw(0xA9, v)
    return lda_abs, sta_abs, stz_abs, lda_i


def stub() -> bytes:
    """명령 스텁 — 켜진 뒤에만, L+R+Select 를 누른 채 다른 버튼."""
    a = Asm()
    lda_abs, sta_abs, stz_abs, lda_i = _helpers(a)

    # ── 열쇠: L+R+Select 만 1초 — 이 갈래는 3프레임쯤마다 도니 프레임 번호(`$0027`, NMI 마다 +1)로 흐른 시간을 센다 ──
    lda_abs(0x1B06); a.raw(AND, 0xF0); a.raw(CMP, 0x30); a.far(BNE, "nochord")  # L+R 뿐(A·X 없음)
    lda_abs(0x1B07); a.raw(CMP, 0x20); a.far(BNE, "nochord")                     # Select 뿐(방향키·B·Y·Start 없음)
    lda_abs(0x27); a.raw(0x38); a.raw(0xED, HOLD_LAST & 255, HOLD_LAST >> 8)     # sec / sbc last → 지난 호출 뒤 흐른 프레임
    a.raw(0xAA)                                                                  # tax
    lda_abs(0x27); sta_abs(HOLD_LAST)
    a.raw(0x8A)                                                                  # txa
    a.raw(CMP, HOLD_STALE); a.br(0x90, "cont")                                   # 12프레임 넘게 안 불렸다 = 손을 뗐다 다시 눌렀다 → 처음부터
    stz_abs(HOLD_CNT); a.br(BRA, "gate")
    a.label("cont")
    lda_abs(HOLD_CNT); a.raw(CMP, HOLD_FRAMES); a.br(BCS, "gate")                # 이미 일을 했으면 손 뗄 때까지 기다린다
    a.raw(0x8A); a.raw(0x18); a.raw(0x6D, HOLD_CNT & 255, HOLD_CNT >> 8)         # txa / clc / adc cnt
    a.br(BCS, "fire"); a.raw(CMP, HOLD_FRAMES); a.br(0x90, "store")              # 넘쳤거나 60 이상이면 발사, 아니면 저장
    a.label("fire")
    lda_i(HOLD_FRAMES); sta_abs(HOLD_CNT)
    lda_abs(UNLOCK); a.raw(CMP, 0xA5); a.br(BEQ, "off")                          # 켜짐 ↔ 꺼짐
    lda_i(0xA5); sta_abs(UNLOCK); lda_i(SE_ON)
    a.raw(0x22, 0xA1, 0x07, 0xC0)                                                # jsl $C0:07A1 (소리)
    a.br(BRA, "gate")
    a.label("off")
    stz_abs(UNLOCK); lda_i(SE_OFF)
    a.raw(0x22, 0xA1, 0x07, 0xC0)
    a.br(BRA, "gate")
    a.label("store")
    sta_abs(HOLD_CNT)
    a.br(BRA, "gate")
    a.label("nochord")
    stz_abs(HOLD_CNT)
    lda_abs(0x27); sta_abs(HOLD_LAST)
    a.label("gate")
    lda_abs(UNLOCK); a.raw(CMP, 0xA5); a.far(BNE, "done")                       # 열쇠로 켜지 않았으면 원판 그대로
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


def jsl(addr: int) -> bytes:
    return bytes([0x22, addr & 255, (addr >> 8) & 255, addr >> 16])


def patches() -> list[tuple[int, bytes, bytes]]:
    """(주소, 원본 바이트, 새 바이트) — `patches.PATCHES` 에 더해 쓴다(원본이 다르면 그 자리에서 죽는다)."""
    s = stub()
    assert len(s) <= CMD_LIMIT, len(s)
    return [
        (CMD_STUB, b"\xff" * len(s), s),
        (HOOK, HOOK_OLD, jsl(CMD_STUB) + b"\xea\xea"),
    ]


if __name__ == "__main__":
    b = stub()
    print("스텁", len(b), "B", b.hex())
