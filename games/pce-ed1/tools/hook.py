"""폰트 후킹 루틴·초기화 스텁 — 손인코딩 HuC6280 을 **미니 어셈블러**로 낸다(오타 방지).

배치(status.md 9절):
  · 루틴 본체 `$3B00~`(워크 RAM, 쓰기 0회 확인 구간). 원본은 디스크 rel 126(뱅크 0x7F 적재분) 앞 256B 에
    실어 두고 스텁이 TII 로 옮긴다.
  · 글리프 뱅크: rel 114~(뱅크 0x7C~ 적재분, 원본 0) → 스텁이 font.GLYPH_BANK0~0x87 로 복사(font.GLYPH_NBANKS 뱅크).
  · 스텁: 뱅크 0x69 +0x1852(루틴 사이 850B 패딩, 논리 $7852). 본 프로그램 진입 `JSR $5798` 을 스텁으로 돌리고
    스텁이 `JMP $5798` 로 잇는다.
  · 호출 규약은 EX_GETFNT 그대로: `_ax`=코드(`$F9` 리드 · `$F8` 트레일), `_bx`=출력 32B, 성공 시 A=0.
    리드 F0~F9 만 가로채고 나머지는 `JMP $E060`. BIOS 처럼 `$EC~$EE` 를 스크래치로 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

# 🔴 **워크 RAM 자리는 $3B00 이 아니다**(2026-09-07 확정). 거기에 이 768B 를 두면 마을 재입장에서
# 게임이 굳는다 — A/B 일곱 + 「잘 도는 램에 이 768B 만 심으니 다음 맵 전환에서 튕김」으로 못 박았다
# (devlog 09-06 ⑤). ⚠ **덤프가 0 이라는 건 근거가 못 된다** — $3B00~$3DFF 는 어느 덤프에서도 0인데
# 게임이 쓴다. 자리를 옮길 땐 **그 자리에 심은 채 한 바퀴(전투·필드·맵 전환·씬)** 를 돌아야 한다.
HOOK_ADDR = 0x2300
# 워크 RAM 배치(HOOK_ADDR ~ +0x2FF, 768B): 루틴 · 조사표 · 받침 비트맵 · 직전 글자
# ⚠ 아래는 **HOOK_ADDR 에서 유도**한다 — 옛 판은 절대값이라 base 를 옮기면 표만 제자리에 남았다.
JOSA_OFF_ADDR = HOOK_ADDR + 0x180  # 조사 오프셋표 28B (루틴 자리는 base ~ +0x17F, 384B)
BATCHIM_ADDR = HOOK_ADDR + 0x1A0  # 받침 비트맵 128B
RIEUL_ADDR = HOOK_ADDR + 0x220  # ㄹ받침 비트맵 128B
PAYLOAD_LEN = (
    0x340  # 루틴 + 조사표 + 비트맵 둘 + 줄바꿈 품질 블록(62B, `WRAP_ADDR`) — 스텁이 통째로 옮긴다
)
#   ⚠ 이 값을 안 맞추면 **뒤쪽 표만 안 옮겨져** 리드 F1 대역 글자가 조용히 다른 글자로 나온다(실측)
LAST_ADDR = HOOK_ADDR + 0x2A0  # 직전 글자 코드 2B(리드·트레일)
EXT_ADDR = HOOK_ADDR + 0x2A2  # 확장 블록(~+0x2FF, 94B) — 주 루틴 자리(384B)가 꽉 차 여기로 넘긴다
BITCNT_ADDR = 0x3DA2  # 비트 위치 임시
HASBAT_ADDR = 0x3DA3  # 받침 판정 임시
# 🔴 **로그 자동 개행 품질 패치(①③, status.md 09-27)** — `$6D95`(자동 개행 판정) 자체엔 여유가
#   0B 라 새 코드는 못 넣지만, 그 판정·처리부가 부르는 **세 JSR 호출부**(`$6D9C`→`$6AB5`,
#   `$6723`→`$6AB9`, `$6730`→`$6D8A`)는 그대로 남아 있다 — 그 호출 대상만 우리 스텁으로 돌리면
#   원본 코드를 한 바이트도 안 늘리고 끼어들 수 있다(위 폰트 후킹과 같은 패턴). 자리는 페이로드
#   뒤(`$300~`, 이 섹터 나머지 1,280B 는 원본에서도 전부 0 — 실측 확인됨) 새 블록 하나.
WRAP_ADDR = HOOK_ADDR + 0x300
# 원본 호출 대상(그대로 남는다 — 우리 스텁이 필요하면 부른다)
ORIG_SET_PENDING = 0x6AB5  # $6D9C 가 부르던 것 — "개행 보류" 플래그(`$CF15`) 증가
ORIG_DO_WRAP = 0x6AB9  # $6723 가 부르던 것 — 보류 플래그가 서 있으면 실제로 줄을 넘긴다
ORIG_ADV_COL = 0x6D8A  # $6730 이 부르던 것 — 칸 카운터(`$38BB`) 전진
# 🔴 **로그 어절 줄바꿈(마스터 09-30 「로그성 메시지도 어절 단위」, 10-07 구현)** — `mark` 가 글자마다
#   마지막 글리프 뱅크 꼬리의 `wordck` 를 **MPR2($4000)** 에 잠깐 걸어 부른다(SEI). 공백 다음 글자(어절 첫 글자)에서
#   어절 길이를 앞질러 재고(이름·도구 삽입이면 06 에서 `$93/$94` 로 돌아가 이어 잰다) 「열 + 길이 > 13」이면
#   개행 보류 플래그(`$CF15`)를 세워 그 글자부터 새 줄에 그린다. 13 보다 긴 낱말은 원래대로 글자 단위.
WORDCK_BANK = font.GLYPH_BANK0 + font.GLYPH_NBANKS - 1
# 🔴 창은 **글이 안 사는 곳**이어야 한다 — 앞질러 읽는 글은 `$6000`(삽입 버퍼, 0x6C) · `$8000`(시스템 문구, 0x6D) ·
#   `$A000`(씬 블록) · `$C000`(전투 블록·이름표, 0x74) 에 산다. 처음엔 MPR4($8000) 에 걸었다가 시스템 문구
#   (「을/를 사용했다.」)를 읽을 자리에서 **우리 루틴 자신을 읽어** 「류난은 / 횃불을…」로 넘겼다(10-07 실측).
#   MPR2($4000, 본 프로그램 0x68) 는 코드뿐이라 거기 건다 — 혹시 포인터가 `$4000~$5FFF` 면 판정을 건너뛴다.
WORDCK_MPR = 2
WORDCK_ADDR = (WORDCK_MPR << 13) + 0x2000 - font.GLYPH_TAIL  # MPR2 창 기준
LINE_COLS_ZP = 0x99  # 줄 폭(칸) — `$6D95` 가 비교하는 그 값(로그·필드 창 13)
# 부호 넷(4px, glyph_order.json 로 유도) — 줄 끝에 매단다(고아로 새 줄 첫 칸에 혼자 안 남긴다)
HANG_PUNCT = ((font.LEAD0, 0x24), (font.LEAD0, 0x25), (font.LEAD0, 0x27), (font.LEAD0, 0x2E))
SPACE_CODE = (0x81, 0x40)  # 공백(전각) — 개행 직후 첫 글자면 그린 그대로 두고 칸만 안 늘린다
# ⚠ 임시값은 워크 RAM 에 둔다 — 게임 ZP 를 빌리면 어느 자리가 비는지 증명해야 한다($EC~$EE 는
#   BIOS 가 쓰는 스크래치라 그대로 쓴다).
STUB_ADDR = 0x7852  # 뱅크 0x69 +0x1852
ORIG_INIT = 0x5798
GLYPH_WINDOW_HI = 0x60  # 글리프 뱅크를 MPR3($6000) 에 잠깐 건다
GLYPH_BANK0 = font.GLYPH_BANK0
UNPACK_ADDR = (
    GLYPH_WINDOW_HI << 8
) + font.BANK_GLYPH_END  # 글리프 뱅크마다 같은 자리 — MPR3 창 기준
UNPACK_ROOM = 0x2000 - font.GLYPH_TAIL - font.BANK_GLYPH_END  # 112B(마지막 뱅크는 뒤에 어절 루틴)

# (니모닉, 모드) → 옵코드. 모드: imp · imm · zp · abs · absx · absy · izpy · rel · tma · tam
OPS = {
    ("LDA", "zp"): 0xA5,
    ("LDA", "imm"): 0xA9,
    ("LDA", "abs"): 0xAD,
    ("LDA", "absx"): 0xBD,
    ("LDA", "izpy"): 0xB1,
    ("LDA", "izp"): 0xB2,
    ("ROL", "imp"): 0x2A,
    ("STA", "zp"): 0x85,
    ("STA", "abs"): 0x8D,
    ("STA", "izpy"): 0x91,
    ("STZ", "zp"): 0x64,
    ("CMP", "imm"): 0xC9,
    ("CMP", "zp"): 0xC5,
    ("CPY", "imm"): 0xC0,
    ("BEQ", "rel"): 0xF0,
    ("BRA", "rel"): 0x80,
    ("LDA", "absy"): 0xB9,
    ("LDX", "abs"): 0xAE,
    ("LDY", "imm"): 0xA0,
    ("LDX", "imm"): 0xA2,
    ("STX", "zp"): 0x86,
    ("LDX", "zp"): 0xA6,
    ("STY", "zp"): 0x84,
    ("STX", "abs"): 0x8E,
    ("STY", "abs"): 0x8C,
    ("SBC", "abs"): 0xED,
    ("DEC", "abs"): 0xCE,
    ("INC", "abs"): 0xEE,
    ("CPX", "imm"): 0xE0,
    ("EOR", "imm"): 0x49,
    ("ADC", "abs"): 0x6D,
    ("BMI", "rel"): 0x30,
    ("LDY", "abs"): 0xAC,
    ("CMP", "absx"): 0xDD,
    ("CMP", "izpy"): 0xD1,
    ("BPL", "rel"): 0x10,
    ("TSX", "imp"): 0xBA,
    ("INC", "zp"): 0xE6,
    ("ORA", "abs"): 0x0D,
    ("CMP", "abs"): 0xCD,
    ("SBC", "absx"): 0xFD,
    ("CPY", "abs"): 0xCC,
    ("TAY", "imp"): 0xA8,
    ("TYA", "imp"): 0x98,
    ("TXA", "imp"): 0x8A,
    ("AND", "zp"): 0x25,
    ("INX", "imp"): 0xE8,
    ("DEX", "imp"): 0xCA,
    ("LSR", "zp"): 0x46,
    ("ROR", "zp"): 0x66,
    ("STZ", "abs"): 0x9C,
    ("STA", "absx"): 0x9D,
    ("INC", "imp"): 0x1A,
    ("BCC", "rel"): 0x90,
    ("BCS", "rel"): 0xB0,
    ("BNE", "rel"): 0xD0,
    ("JMP", "abs"): 0x4C,
    ("JSR", "abs"): 0x20,
    ("RTS", "imp"): 0x60,
    ("INY", "imp"): 0xC8,
    ("DEY", "imp"): 0x88,
    ("CLA", "imp"): 0x62,
    ("CLY", "imp"): 0xC2,
    ("PHA", "imp"): 0x48,
    ("PLA", "imp"): 0x68,
    ("PHP", "imp"): 0x08,
    ("PLP", "imp"): 0x28,
    ("SEI", "imp"): 0x78,
    ("PHX", "imp"): 0xDA,
    ("PLX", "imp"): 0xFA,
    ("PHY", "imp"): 0x5A,
    ("PLY", "imp"): 0x7A,
    ("TAX", "imp"): 0xAA,
    ("SEC", "imp"): 0x38,
    ("CLC", "imp"): 0x18,
    ("ASL", "imp"): 0x0A,
    ("SBC", "imm"): 0xE9,
    ("ADC", "imm"): 0x69,
    ("ADC", "zp"): 0x65,
    ("ADC", "absx"): 0x7D,
    ("AND", "imm"): 0x29,
    ("ORA", "imm"): 0x09,
    ("ASL", "zp"): 0x06,
    ("ROL", "zp"): 0x26,
    ("LSR", "imp"): 0x4A,
    ("TMA", "tma"): 0x43,
    ("TAM", "tam"): 0x53,
}


class Asm:
    def __init__(self, org: int):
        self.org = org
        self.out = bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []  # (pos, label, kind)

    @property
    def pc(self):
        return self.org + len(self.out)

    def label(self, name):
        self.labels[name] = self.pc

    def op(self, mn, mode="imp", arg=None):
        self.out.append(OPS[(mn, mode)])
        if mode == "imp":
            return
        if mode in ("imm", "zp", "izpy", "izp"):
            self.out.append(arg & 0xFF)
        elif mode in ("tma", "tam"):
            self.out.append(1 << arg)  # MPR 번호 → 비트
        elif mode == "rel":
            self.fix.append((len(self.out), arg, "rel"))
            self.out.append(0)
        elif mode in ("abs", "absx", "absy"):
            if isinstance(arg, str):
                self.fix.append((len(self.out), arg, "abs"))
                self.out += b"\0\0"
            else:
                self.out += arg.to_bytes(2, "little")

    def tii(self, src, dst, ln):
        self.out += (
            b"\x73"
            + src.to_bytes(2, "little")
            + dst.to_bytes(2, "little")
            + ln.to_bytes(2, "little")
        )

    def data(self, b: bytes):
        self.out += b

    def bytes(self) -> bytes:
        for pos, lab, kind in self.fix:
            tgt = self.labels[lab]
            if kind == "rel":
                d = tgt - (self.org + pos + 1)
                assert -128 <= d <= 127, (lab, d)
                self.out[pos] = d & 0xFF
            else:
                self.out[pos : pos + 2] = tgt.to_bytes(2, "little")
        return bytes(self.out)


def hook_routine() -> bytes:
    b = _main_asm().bytes()
    assert len(b) <= JOSA_OFF_ADDR - HOOK_ADDR, len(b)
    return b + b"\0" * (JOSA_OFF_ADDR - HOOK_ADDR - len(b))


def _main_asm() -> "Asm":
    """EX_GETFNT 대체 — 우리 코드면 글리프를 내고, 조사 코드면 **직전 글자의 받침**으로 고른다.

    · 리드 < F0 또는 > F9 → `JMP $E060`(BIOS)
    · 리드 F9 → 조사: 종류 k = 트레일−0x24, 직전 글자(LAST)가 우리 코드면 받침 비트맵 조회,
      아니면 받침 없음으로 본다(원문 전각 숫자·영문·부호 뒤 — 기종 간 규칙 09-26). `으로/로` 는 ㄹ 비트맵을 한 번 더 본다.
    · 그 밖(F0~F8) → 글리프 인덱스 계산 후 복사하고 **LAST 를 갱신**한다.
    """
    a = Asm(HOOK_ADDR)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BCC", "rel", "bios")
    a.op("CMP", "imm", font.JOSA_LEAD + 1)
    a.op("BCC", "rel", "ours")
    a.label("bios")
    a.op("JMP", "abs", EXT_ADDR)  # 우리 범위 밖 — LAST 를 적고 BIOS 로(`hook_ext`)
    a.label("ours")
    a.op("PHP")
    a.op("SEI")
    a.op("PHX")
    a.op("PHY")
    a.op("CMP", "imm", font.JOSA_LEAD)
    a.op("BNE", "rel", "normal")  # 조사 블록은 복사 블록 뒤라 짧은 분기로 못 간다
    a.op("JMP", "abs", "josa")
    a.label("normal")
    a.op("LDA", "zp", 0xF9)
    a.op("STA", "abs", LAST_ADDR)
    a.op("LDA", "zp", 0xF8)
    a.op("STA", "abs", LAST_ADDR + 1)
    a.op("STA", "zp", 0xEC)  # 트레일
    a.op("LDA", "zp", 0xF9)
    # ─ 글리프 내기(A = 리드, $EC = 트레일): 뱅크 = GLYPH_BANK0 + (리드−F0)>>1 를 MPR3 창에 걸고 그 뱅크
    #   꼬리의 풀기 루틴(`unpack_asm`, 18B → 24B)을 부른다. 루틴이 뱅크마다 같은 자리에 있어 어느 뱅크든 된다.
    a.label("fetch")
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("TAX")
    a.op("TMA", "tma", 3)
    a.op("STA", "zp", 0xEE)
    a.op("TXA")
    a.op("LSR")  # C = 뱅크 안 리드 짝(0 = 앞 3,960B · 1 = 뒤) — 풀기 루틴이 C 로 받는다
    assert GLYPH_BANK0 % font.GLYPH_NBANKS == 0  # ORA 로 더한다(C 를 안 건드린다)
    a.op("ORA", "imm", GLYPH_BANK0)
    a.op("TAM", "tam", 3)
    a.op("JSR", "abs", UNPACK_ADDR)
    a.op("LDA", "zp", 0xEE)
    a.op("TAM", "tam", 3)
    a.op("PLY")
    a.op("PLX")
    a.op("PLP")
    a.op("CLA")
    a.op("RTS")
    # ─ 조사: 직전 글자의 받침으로 고른다 ─
    a.label("josa")
    a.op("LDA", "abs", LAST_ADDR)  # 직전 리드
    a.op("CMP", "imm", font.LEAD0)
    # 우리 글자가 아니면(원문 SJIS — 게임이 붙이는 전각 숫자·영문·부호) `hook_ext` 가 가른다:
    # 전각 숫자는 **읽는 소리대로**, 나머지는 무받침(기종 간 규칙, 마스터 09-26).
    a.op("BCC", "rel", "not_ours")
    a.op("CMP", "imm", font.JOSA_LEAD)
    a.op("BCC", "rel", "calc")
    a.label("not_ours")
    a.op("JMP", "abs", EXT_ADDR + EXT_JOSA_OFF)
    a.label("calc")
    # 인덱스 = (리드−F0)×220 + (트레일−0x24) → $EC/$ED
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("TAX")
    a.op("LDA", "absx", "idx_lo")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "absx", "idx_hi")
    a.op("STA", "zp", 0xED)
    a.op("LDA", "abs", LAST_ADDR + 1)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("CLC")
    a.op("ADC", "zp", 0xEC)
    a.op("STA", "zp", 0xEC)
    a.op("CLA")
    a.op("ADC", "zp", 0xED)
    a.op("STA", "zp", 0xED)
    # 비트 = idx&7, 바이트 = idx>>3
    a.op("LDA", "zp", 0xEC)
    a.op("AND", "imm", 0x07)
    a.op("STA", "abs", BITCNT_ADDR)
    for _ in range(3):
        a.op("LSR", "zp", 0xED)
        a.op("ROR", "zp", 0xEC)
    _bit(a, BATCHIM_ADDR, "has")
    a.op("STA", "abs", HASBAT_ADDR)
    # `으로/로`(종류 4)는 ㄹ 받침이면 「로」 — 받침 있음에서 도로 뺀다
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("CMP", "imm", 4)
    a.op("BNE", "rel", "decide")
    _bit(a, RIEUL_ADDR, "ri")
    a.op("BEQ", "rel", "decide")
    a.op("STZ", "abs", HASBAT_ADDR)
    a.label("decide")
    a.op("LDA", "abs", HASBAT_ADDR)
    a.op("BNE", "rel", "has_batchim")
    # 받침 없음 → 표의 둘째 항목: (k×2+1)×2 = k×4+2
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("ASL")
    a.op("INC")
    a.op("BRA", "rel", "josa_lookup")
    a.label("has_batchim")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("ASL")
    a.label("josa_lookup")
    a.op("ASL")
    a.op("TAX")  # 받침 k×4 · 무받침 k×4+2
    a.op("LDA", "absx", JOSA_OFF_ADDR)  # 표 = (트레일, 리드) — 보통 글자 길로 낸다
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "absx", JOSA_OFF_ADDR + 1)
    a.op("JMP", "abs", "fetch")
    a.label("idx_lo")
    a.data(bytes((i * font.PER_LEAD) & 0xFF for i in range(10)))
    a.label("idx_hi")
    a.data(bytes((i * font.PER_LEAD) >> 8 & 0xFF for i in range(10)))
    a.bytes()  # 분기 거리 검산
    return a


EXT_JOSA_OFF = 15  # hook_ext 안 조사 판정 입구(ext_bios 15B 뒤)
# 전각 숫자 ０~９ 를 읽은 소리: 0 무받침 · 1 받침 · 2 받침+ㄹ — 영일이삼사오육칠팔구
DIGIT_KIND = bytes((1, 2, 0, 1, 0, 0, 1, 2, 2, 0))


def hook_ext() -> bytes:
    """확장 블록(EXT_ADDR~, 94B) — 주 루틴 자리가 꽉 차 여기로 뺐다.

    · ext_bios: BIOS 로 가는 글자도 **LAST 에 적는다** — 안 적으면 「레스１」(게임이 붙이는 SJIS 전각 숫자)
      뒤 조사가 **숫자 앞 한글**(「스」)을 보고 골라 「레스1를」이 됐다(마스터 규칙 09-26, 화면 실측).
    · ext_josa: LAST 가 우리 글자가 아닐 때 — SJIS 전각 숫자(82 4F~82 58)면 읽는 소리대로, 나머지는 무받침.
      `으로/로`(종류 4)는 ㄹ받침(1·7·8)이면 「로」.
    """
    decide = _main_asm().labels["decide"]
    a = Asm(EXT_ADDR)
    a.label("ext_bios")
    a.op("LDA", "zp", 0xF9)
    a.op("STA", "abs", LAST_ADDR)
    a.op("LDA", "zp", 0xF8)
    a.op("STA", "abs", LAST_ADDR + 1)
    a.op("LDA", "zp", 0xF9)  # A 를 들어올 때 값으로
    a.op("JMP", "abs", 0xE060)
    assert a.pc - EXT_ADDR == EXT_JOSA_OFF, a.pc - EXT_ADDR
    a.label("ext_josa")
    a.op("LDA", "abs", LAST_ADDR)
    a.op("CMP", "imm", 0x82)
    a.op("BNE", "rel", "plain")
    a.op("LDA", "abs", LAST_ADDR + 1)
    a.op("SEC")
    a.op("SBC", "imm", 0x4F)
    a.op("CMP", "imm", 10)
    a.op("BCS", "rel", "plain")
    a.op("TAX")
    a.op("LDA", "absx", "digit_kind")
    a.op("BEQ", "rel", "plain")
    a.op("CMP", "imm", 2)
    a.op("BNE", "rel", "has")
    a.op("LDA", "zp", 0xF8)  # ㄹ받침 — `으로/로` 면 무받침 쪽(로)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("CMP", "imm", 4)
    a.op("BEQ", "rel", "plain")
    a.label("has")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", HASBAT_ADDR)
    a.op("JMP", "abs", decide)
    a.label("plain")
    a.op("STZ", "abs", HASBAT_ADDR)
    a.op("JMP", "abs", decide)
    a.label("digit_kind")
    a.data(DIGIT_KIND)
    b = a.bytes()
    assert len(b) <= HOOK_ADDR + PAYLOAD_LEN - EXT_ADDR, len(b)
    return b


def _wrap_asm() -> "Asm":
    """줄바꿈 품질 패치(①③) — 세 JSR 호출부(`$6D9C`·`$6723`·`$6730`)의 대상을 여기로 돌린다.

    · `orphan`(→$6D9C 대신): 다음 글자가 부호 넷 중 하나면 **개행 보류 플래그를 안 세운다** —
      이번 글자는 이번 줄에 그대로 그려진다(줄 끝에 매달린다). 아니면 원래대로 `$6AB5` 호출.
    · `mark`(→$6723 대신): 글리프 뱅크를 MPR2 에 잠깐 걸어(SEI — 그 창의 본 프로그램을 인터럽트가 못 부르게) `wordck`(어절 줄바꿈 판정 + `flag`
      기록)를 부르고 원래 `$6AB9` 로 넘어간다. `$6AB9` 가 보류 플래그를 지우므로 「이번 글자에서
      개행이 일어나는가」는 **호출 전**에만 알 수 있다 — 그래서 `flag` 를 거기서 적는다.
    · `eat`(→$6730 대신): 방금 개행이 일어났고 이번 글자가 공백이면(위 `flag`) **칸 전진을
      건너뛴다** — 공백은 원래대로 그려지지만(안 그려도 잉크가 없어 상관없다) 칸을 안 먹으므로
      다음 실제 글자가 줄 맨 앞(칸 0)에 온다. 아니면 원래대로 `$6D8A` 호출.
    """
    a = Asm(WRAP_ADDR)
    a.label("flag")
    a.data(b"\x00")
    a.label("orphan")
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BNE", "rel", "orphan_normal")
    a.op("LDA", "zp", 0xF8)
    for lead, trail in HANG_PUNCT:
        assert lead == font.LEAD0
        a.op("CMP", "imm", trail)
        a.op("BEQ", "rel", "ret")
    a.label("orphan_normal")
    a.op("JMP", "abs", ORIG_SET_PENDING)
    a.label("mark")  # 어절 판정 + `flag` 기록(글리프 뱅크) → 원래 `$6AB9`
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", WORDCK_MPR)
    a.op("PHA")
    a.op("LDA", "imm", WORDCK_BANK)
    a.op("TAM", "tam", WORDCK_MPR)
    a.op("JSR", "abs", WORDCK_ADDR)
    a.op("PLA")
    a.op("TAM", "tam", WORDCK_MPR)
    a.op("PLP")
    a.op("JMP", "abs", ORIG_DO_WRAP)
    a.label("eat")
    a.op("LDA", "abs", "flag")
    a.op("BEQ", "rel", "eat_normal")
    a.label("ret")
    a.op("RTS")  # 먹는다 — 칸 전진을 건너뛴다(부호 매달기도 여기로 돌아간다)
    a.label("eat_normal")
    a.op("JMP", "abs", ORIG_ADV_COL)
    return a


def unpack_asm() -> "Asm":
    """글리프 뱅크 꼬리 루틴(뱅크마다 같은 바이트) — 18B 묶음 글리프를 ($FA) 에 화면용 24B(+0 채움 32B)로 푼다.

    들어올 때: C = 뱅크 안 리드 짝(0/1), `$EC` = 트레일 바이트. 이 뱅크가 MPR3($6000) 에 걸려 있다.
    자리 = 짝×3,960 + (트레일−0x24)×18. 두 행 = 3B: hiA · (loA | hiB>>4) · (hiB<<4 | loB>>4) — `font.pack`.
    """
    a = Asm(UNPACK_ADDR)
    a.op("LDX", "zp", 0xEC)  # 트레일 — $24 까지 세어 내려가며 18 씩 더한다(곱셈 대신, 최대 219번)
    a.op("STZ", "zp", 0xEC)
    a.op("LDY", "imm", GLYPH_WINDOW_HI)
    a.op("BCC", "rel", "even")
    a.op("LDA", "imm", font.GROUP_BYTES & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDY", "imm", GLYPH_WINDOW_HI + (font.GROUP_BYTES >> 8))
    a.label("even")
    a.op("STY", "zp", 0xED)
    a.label("mul")
    a.op("CPX", "imm", font.TRAIL0)
    a.op("BEQ", "rel", "go")
    a.op("DEX")
    a.op("LDA", "zp", 0xEC)
    a.op("CLC")
    a.op("ADC", "imm", font.PACKED_BYTES)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "mul")
    a.op("INC", "zp", 0xED)
    a.op("BRA", "rel", "mul")
    a.label("go")
    a.op("CLY")
    a.label("lp")
    a.op("JSR", "abs", "rd")
    a.op("STA", "izpy", 0xFA)  # hiA
    a.op("INY")
    a.op("JSR", "abs", "rd")
    a.op("PHA")
    a.op("AND", "imm", 0xF0)
    a.op("STA", "izpy", 0xFA)  # loA
    a.op("INY")
    a.op("PLA")
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "abs", "tmp")
    a.op("JSR", "abs", "rd")
    a.op("PHA")
    for _ in range(4):
        a.op("LSR")
    a.op("ORA", "abs", "tmp")
    a.op("STA", "izpy", 0xFA)  # hiB
    a.op("INY")
    a.op("PLA")
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "izpy", 0xFA)  # loB
    a.op("INY")
    a.op("CPY", "imm", font.GLYPH_BYTES)
    a.op("BNE", "rel", "lp")
    a.op("CLA")
    a.label("zero")
    a.op("STA", "izpy", 0xFA)
    a.op("INY")
    a.op("CPY", "imm", 0x20)
    a.op("BNE", "rel", "zero")
    a.op("RTS")
    a.label("rd")
    a.op("LDA", "izp", 0xEC)
    a.op("INC", "zp", 0xEC)
    a.op("BNE", "rel", "rd_ret")
    a.op("INC", "zp", 0xED)
    a.label("rd_ret")
    a.op("RTS")
    a.label("tmp")
    a.data(b"\x00")
    return a


def unpack_code() -> bytes:
    b = unpack_asm().bytes()
    assert len(b) <= UNPACK_ROOM, len(b)
    return b


def finish_banks(glyph_bank: bytes) -> bytes:
    """글리프 뱅크에 꼬리 코드를 얹는다 — 뱅크마다 풀기 루틴, 마지막 뱅크 맨 끝은 어절 줄바꿈 루틴."""
    gb = bytearray(glyph_bank)
    code = unpack_code()
    for k in range(font.GLYPH_NBANKS):
        at = k * 0x2000 + font.BANK_GLYPH_END
        assert not gb[at : (k + 1) * 0x2000].strip(b"\0"), "글리프가 뱅크 꼬리 코드 자리를 덮는다"
        gb[at : at + len(code)] = code
    gb[-font.GLYPH_TAIL :] = wordck()
    return bytes(gb)


def _wordck_asm() -> "Asm":
    """어절 첫 글자에서 「열 + 어절 길이 > 13」이면 개행 보류(`$CF15`)를 세운다. X·Y 를 지킨다.

    지금 글자 = `$F9:$F8`, 열 = `$38BB`(이 글자가 들어갈 칸), 다음 바이트 = `($14),Y`.
    길이는 글자(≥$24, 2B) 수 — 공백(`81 40`)·제어(<$24)에서 끝난다. 단 이름·도구 삽입 중(`$90` 비트1)에
    `06` 을 만나면 삽입 전 자리(`$93/$94`)로 돌아가 이어 잰다(「캐리온크롤러A는」처럼 조사가 뒤에 붙는다).
    """
    a = Asm(WORDCK_ADDR)
    a.op("PHY")
    a.op("PHX")
    a.op("LDX", "abs", "prevsp")  # 직전 글자가 공백이었나
    a.op("STZ", "abs", "prevsp")
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", SPACE_CODE[0])
    a.op("BNE", "rel", "nsp")
    a.op("LDA", "zp", 0xF8)
    a.op("CMP", "imm", SPACE_CODE[1])
    a.op("BNE", "rel", "nsp")
    a.op("INC", "abs", "prevsp")
    a.op("BRA", "rel", "out")
    a.label("nsp")
    a.op("TXA")
    a.op("BEQ", "rel", "out")  # 어절 첫 글자가 아니다
    a.op("LDA", "abs", 0x38BB)
    a.op("BEQ", "rel", "out")  # 줄 머리
    a.op("STZ", "abs", "cnt")  # 지금 글자 뒤로 몇 칸 — 마지막 글자 열 = 열 + cnt
    a.op("LDA", "zp", 0x14)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0x15)
    a.op("STA", "zp", 0xED)
    a.op("JSR", "abs", "guard")
    a.op("LDA", "zp", 0x90)
    a.op("AND", "imm", 2)
    a.op("TAX")  # X = 삽입 중인가
    a.label("lp")
    a.op("LDA", "izpy", 0xEC)
    a.op("CMP", "imm", 0x24)
    a.op("BCC", "rel", "ctl")
    a.op("CMP", "imm", SPACE_CODE[0])
    a.op("BNE", "rel", "ch")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("DEY")
    a.op("CMP", "imm", SPACE_CODE[1])
    a.op("BEQ", "rel", "done")
    a.label("ch")  # A = 리드(공백 갈래에서 왔으면 트레일 $40 — 리드 F0 과 안 겹친다)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BNE", "rel", "cnt1")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("DEY")
    for _lead, trail in HANG_PUNCT:  # 매다는 부호는 줄 밖에 걸리니 길이에 안 센다
        a.op("CMP", "imm", trail)
        a.op("BEQ", "rel", "skip")
    a.label("cnt1")
    a.op("INC", "abs", "cnt")
    a.label("skip")
    a.op("INY")
    a.op("INY")
    a.op("BRA", "rel", "lp")  # 끝은 늘 제어 코드(00·01·04 …)라 멈춘다
    a.label("ctl")
    a.op("CMP", "imm", 6)
    a.op("BNE", "rel", "done")
    a.op("TXA")
    a.op("BEQ", "rel", "done")
    a.op("LDX", "imm", 0)
    a.op("LDA", "zp", 0x93)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0x94)
    a.op("STA", "zp", 0xED)
    a.op("JSR", "abs", "guard")
    a.op("LDY", "imm", 0)
    a.op("BRA", "rel", "lp")
    a.label("done")
    a.op("LDA", "abs", 0x38BB)
    a.op("CLC")
    a.op("ADC", "abs", "cnt")
    a.op(
        "CMP", "zp", LINE_COLS_ZP
    )  # 창마다의 줄 폭(로그·필드 13) — 마지막 글자 열 < 폭이면 들어간다
    a.op("BCC", "rel", "out")
    a.op("INC", "abs", 0xCF15)  # 이 글자부터 새 줄
    a.label("out")
    # `flag`(RAM) = 「이 글자에서 개행이 일어나고 이 글자가 공백」 — `eat` 이 칸 전진을 건너뛴다.
    #   `$6AB9` 가 `$CF15` 를 지우므로 호출 전인 여기서만 알 수 있다.
    a.op("LDA", "abs", 0xCF15)
    a.op("BEQ", "rel", "st")
    a.op("LDA", "abs", "prevsp")
    a.label("st")
    a.op("STA", "abs", WRAP_ADDR)
    a.op("PLX")
    a.op("PLY")
    a.op("RTS")
    a.label("guard")  # 포인터가 우리 창(`$4000~$5FFF`)이면 못 읽는다 — 판정 없이 나간다
    a.op("LDA", "zp", 0xED)
    a.op("AND", "imm", 0xE0)
    a.op("CMP", "imm", WORDCK_MPR << 5)
    a.op("BNE", "rel", "g_ok")
    a.op("PLA")
    a.op("PLA")
    a.op("BRA", "rel", "out")
    a.label("g_ok")
    a.op("RTS")
    for v in ("prevsp", "cnt"):
        a.label(v)
        a.data(b"\x00")
    return a


def wordck() -> bytes:
    b = _wordck_asm().bytes()
    assert len(b) <= font.GLYPH_TAIL, len(b)
    return b + b"\0" * (font.GLYPH_TAIL - len(b))


def hook_wrap_fix() -> bytes:
    return _wrap_asm().bytes()


WRAP_LABELS = _wrap_asm().labels
ORPHAN_ADDR = WRAP_LABELS["orphan"]  # $6D9C 의 새 JSR 대상
MARK_ADDR = WRAP_LABELS["mark"]  # $6723 의 새 JSR 대상
EAT_ADDR = WRAP_LABELS["eat"]  # $6730 의 새 JSR 대상


def payload(table) -> bytes:
    """스텁이 통째로 옮기는 페이로드 — 루틴 · 조사표 · 받침 비트맵 둘 · LAST · 확장 블록 · 줄바꿈 품질."""
    p = bytearray(hook_routine())
    p += font.josa_offsets(table)
    p += b"\0" * (BATCHIM_ADDR - HOOK_ADDR - len(p))
    has, rieul = font.batchim_tables(font.build_table.order)
    p += has
    p += b"\0" * (RIEUL_ADDR - HOOK_ADDR - len(p))
    p += rieul
    p += b"\0" * (EXT_ADDR - HOOK_ADDR - len(p))  # LAST(2B) 는 0 으로 시작
    p += hook_ext()
    p += b"\0" * (WRAP_ADDR - HOOK_ADDR - len(p))
    p += hook_wrap_fix()
    p += b"\0" * (PAYLOAD_LEN - len(p))
    assert len(p) == PAYLOAD_LEN
    return bytes(p)


def _bit(a: "Asm", table_addr: int, tag: str) -> None:
    """비트맵[$EC] 의 BITCNT 번째 비트를 A(0/1)로. X·Y 를 쓴다."""
    a.op("LDA", "zp", 0xEC)
    a.op("TAY")
    a.op("LDA", "absy", table_addr)
    a.op("STA", "zp", 0xEE)
    a.op("LDA", "abs", BITCNT_ADDR)
    a.op("TAX")
    a.label(f"{tag}_shift")
    a.op("TXA")
    a.op("BEQ", "rel", f"{tag}_done")
    a.op("LSR", "zp", 0xEE)
    a.op("DEX")
    a.op("BRA", "rel", f"{tag}_shift")
    a.label(f"{tag}_done")
    a.op("LDA", "zp", 0xEE)
    a.op("AND", "imm", 1)


def _mul24(a: "Asm") -> None:
    """$EC/$ED ×= 24 (×8 + ×16)."""
    for _ in range(3):
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)
    a.op("LDA", "zp", 0xEC)
    a.op("PHA")
    a.op("LDA", "zp", 0xED)
    a.op("PHA")
    a.op("ASL", "zp", 0xEC)
    a.op("ROL", "zp", 0xED)
    a.op("PLA")
    a.op("STA", "zp", 0xEE)
    a.op("PLA")
    a.op("CLC")
    a.op("ADC", "zp", 0xEC)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xEE)
    a.op("ADC", "zp", 0xED)
    a.op("STA", "zp", 0xED)


def init_stub() -> bytes:
    a = Asm(STUB_ADDR)
    a.op("TMA", "tma", 5)
    a.op("PHA")
    a.op("TMA", "tma", 6)
    a.op("PHA")
    for i in range(font.GLYPH_NBANKS):
        a.op("LDA", "imm", 0x7C + i)
        a.op("TAM", "tam", 5)
        a.op("LDA", "imm", GLYPH_BANK0 + i)
        a.op("TAM", "tam", 6)
        a.tii(0xA000, 0xC000, 0x2000)
        # 🔴 **옮긴 뒤 원본 자리를 0 으로 되돌린다.** 뱅크 0x7C~0x7E 는 게임의 워크 영역이고
        #    (전투 중 덤프에서 게임이 덮어쓴 걸 봤다) 원판은 0 으로 실린다. 우리 글리프를 남겨 두면
        #    「0 으로 초기화된 자리」를 가정하는 코드가 다른 초기값을 본다 — 체크리스트 「빈 자리의 근거」.
        a.op("STZ", "abs", 0xA000)
        a.tii(0xA000, 0xA001, 0x1FFF)  # 겹침 복사로 0 을 뱅크 전체에 전파
    a.op("LDA", "imm", 0x7F)
    a.op("TAM", "tam", 5)
    a.tii(0xA000, HOOK_ADDR, PAYLOAD_LEN)
    a.op(
        "STZ", "abs", 0x22BC
    )  # 나레이션 자동 넘김 표시(`narration_gates.AUTO_FLAG`) — 리셋 때 남지 않게
    a.op("STZ", "abs", 0xA000)
    a.tii(0xA000, 0xA001, 0x1FFF)
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("JMP", "abs", ORIG_INIT)
    return a.bytes()


if __name__ == "__main__":
    h = hook_routine()
    print("hook", len(h.rstrip(b"\0")), "B:", h.rstrip(b"\0").hex())
    s = init_stub()
    print("stub", len(s), "B:", s.hex())
