"""폰트 후킹 루틴·초기화 스텁 — 손인코딩 HuC6280 을 **미니 어셈블러**로 낸다(오타 방지).

배치(status.md 9절):
  · 루틴 본체 `HOOK_ADDR`=`$2300~`(워크 RAM, `PAYLOAD_LEN` 0x348B — 아래 머리 주석의 자리 경위). 원본은 디스크
    rel 126(뱅크 0x7F 적재분)에 실어 두고 스텁이 TII 로 옮긴다.
  · 글리프 뱅크: rel 114~(뱅크 0x7C~0x7D 적재분, 원본 0) → 스텁이 font.GLYPH_BANK0(0x86)~0x87 로 복사.
    18B 묶음 저장 · 뱅크마다 꼬리에 풀기 루틴(`unpack_asm`), 마지막 뱅크 맨 끝에 어절 줄바꿈 루틴(`wordck`).
  · 스텁: 뱅크 0x69 +0x1852(루틴 사이 850B 패딩, 논리 $7852). 본 프로그램 진입 `JSR $5798` 을 스텁으로 돌리고
    스텁이 `JMP $5798` 로 잇는다.
  · 호출 규약은 EX_GETFNT 그대로: `_ax`=코드(`$F9` 리드 · `$F8` 트레일), `_bx`=출력 32B, 성공 시 A=0.
    리드 F0~F9 만 가로채고 나머지는 `JMP $E060`. BIOS 처럼 `$EC~$EE` 를 스크래치로 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

# 🔴 **워크 RAM 자리는 $3B00 이 아니다**(2026-09-07 확정). 거기에 이 페이로드(당시 768B)를 두면 마을 재입장에서
# 게임이 굳는다 — A/B 일곱 + 「잘 도는 램에 이 768B 만 심으니 다음 맵 전환에서 튕김」으로 못 박았다
# (devlog 09-06 ⑤). ⚠ **덤프가 0 이라는 건 근거가 못 된다** — $3B00~$3DFF 는 어느 덤프에서도 0인데
# 게임이 쓴다. 자리를 옮길 땐 **그 자리에 심은 채 한 바퀴(전투·필드·맵 전환·씬)** 를 돌아야 한다.
HOOK_ADDR = 0x2300
# 워크 RAM 배치(HOOK_ADDR ~ +0x2FF, 768B): 루틴 · 조사표 · 받침 비트맵 · 직전 글자
# ⚠ 아래는 **HOOK_ADDR 에서 유도**한다 — 옛 판은 절대값이라 base 를 옮기면 표만 제자리에 남았다.
JOSA_OFF_ADDR = HOOK_ADDR + 0x180  # 조사 오프셋표 28B (루틴 자리는 base ~ +0x17F, 384B)
_BIT_BYTES = (font.MAX_GLYPHS + 7) // 8  # 받침·ㄹ 비트맵 한 장(글리프 880 → 110B)
BATCHIM_ADDR = HOOK_ADDR + 0x1A0  # 받침 비트맵 110B
RIEUL_ADDR = (
    BATCHIM_ADDR + _BIT_BYTES
)  # ㄹ받침 비트맵 110B — 표를 128B 칸에 안 앉히고 바짝 붙였다(36B 를 걷었다)
LAST_ADDR = RIEUL_ADDR + _BIT_BYTES  # 직전 글자 코드 2B(리드·트레일)
EXT_ADDR = LAST_ADDR + 2  # 확장 블록(75B) — 주 루틴 자리(384B)가 꽉 차 여기로 넘긴다
EXT_ROOM = 76
BITCNT_ADDR = 0x3DA2  # 비트 위치 임시
HASBAT_ADDR = 0x3DA3  # 받침 판정 임시
# 🔴 **로그 자동 개행 품질 패치(①③, status.md 09-27)** — `$6D95`(자동 개행 판정) 자체엔 여유가
#   0B 라 새 코드는 못 넣지만, 그 판정·처리부가 부르는 **세 JSR 호출부**(`$6D9C`→`$6AB5`,
#   `$6723`→`$6AB9`, `$6730`→`$6D8A`)는 그대로 남아 있다 — 그 호출 대상만 우리 스텁으로 돌리면
#   원본 코드를 한 바이트도 안 늘리고 끼어들 수 있다(위 폰트 후킹과 같은 패턴). 자리는 페이로드
#   뒤(`$300~`, 이 섹터 나머지 1,280B 는 원본에서도 전부 0 — 실측 확인됨) 새 블록 하나.
WRAP_ADDR = EXT_ADDR + EXT_ROOM
WRAP_ROOM = 56  # `_wrap_asm` 56B
# 🔴 **반 칸(4px) 전진 변형 코드(마스터 10-07 「당연히 반각 공백으로」)** — 렌더러 입구 `$7047` 의 첫 3B(`INC $38BB`)를
#   `JSR NARROW_ADDR` 로 바꾼다. 리드 F4~F7 = 「리드 F0~F3 의 같은 트레일 글자를 그리고 +4px」(`font.VARIANT_LEAD0`).
NARROW_ADDR = WRAP_ADDR + WRAP_ROOM
NARROW_ROOM = HOOK_ADDR + 0x348 - NARROW_ADDR  # 페이로드 끝 `$2648` 까지
PAYLOAD_LEN = 0x348  # 루틴 + 조사표 + 비트맵 둘 + 줄바꿈 품질 + 반 칸 전진 — 스텁이 통째로 옮긴다. `$2648` 이 측정한 구간 끝
#   ⚠ 이 값을 안 맞추면 **뒤쪽 표만 안 옮겨져** 리드 F1 대역 글자가 조용히 다른 글자로 나온다(실측)
assert NARROW_ADDR + NARROW_ROOM <= HOOK_ADDR + PAYLOAD_LEN

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
# 마지막 글리프 뱅크 끝 코드 자리(`font.CODE_SLOTS`) 앞쪽 = 반 칸 전진(`entry`), 그 뒤 = 어절 줄바꿈(`wordck`) — MPR2 창 기준
CODE_ADDR = (WORDCK_MPR << 13) + font.BANK_GLYPH_END - font.CODE_BYTES
ENTRY_ADDR = CODE_ADDR
ENTRY_ROOM = 509  # 칸 분류(`pre`) · 반 칸 전진 · 부호 되감기(`post`)
WORDCK_ADDR = ENTRY_ADDR + ENTRY_ROOM
WORDCK_ROOM = font.CODE_BYTES - ENTRY_ROOM
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
UNPACK_ROOM = 0x2000 - font.BANK_GLYPH_END  # 272B(풀기 루틴은 103B — 뒤는 비어 있다)

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
    ("AND", "abs"): 0x2D,
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
    ("STZ", "absx"): 0x9E,
    ("ST0", "imm"): 0x03,
    ("ORA", "absy"): 0x19,
    ("STA", "absy"): 0x99,
    ("CLX", "imp"): 0x82,
    ("AND", "absx"): 0x3D,
    ("SBC", "zp"): 0xE5,
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


# 🔴 프레임 카운터 — 장면 연출 중엔 플레이 시계(`$C1B2`)가 멈추고 `$5BCF` 는 시간 기준이 못 되며(실측 10-12) 영 페이지 `$01` 은 8비트라 모자란다.
#   IRQ1 핸들러(`$40CF`) 안의 `JSR $57A5`(`$4154`)을 이 트램펄린으로 바꿔 끼우면 매 VBlank 에 16비트 카운터가 올라간다.
#   ⚠ 디스크에서 바꾸면 이 페이로드가 옮겨지기 전 IRQ 가 BRK 로 죽는다 — **런타임에 상주부가 RAM 에서 바꿔 끼운다**(`narration_gates` `inst`).
#   자리는 후킹 루틴 자리(384B) 끝의 0 패딩(루틴은 245B).
TICK_ADDR = HOOK_ADDR + 0x100  # 루틴 끝(`$23F5`) 뒤 빈 자리 — 아래 트램펄린 40B
FRAMECNT = HOOK_ADDR + 0x174  # 16비트(하위·상위)
VOICE_ARM = FRAMECNT + 3  # ≠ 0 이면 틱이 ADPCM 재생 시작(`$180C` 비트3)을 기다린다 — 보이면 0 으로 내리고 그 프레임을 `PLAYSTART` 에 적는다(마스터 10-13: 소리 시작은 환경마다 다르다)
PLAYSTART = FRAMECNT + 4  # 16비트 — 음성 재생이 실제로 시작된 프레임 카운터 값(안 보였으면 호출 때 값 그대로)
ADPCM_STAT = 0x180C  # 하드웨어 ADPCM 상태 — 비트3 = 재생 중
GW_FLAG = FRAMECNT + 2  # 0 이면 자막 틱 없음. 아니면 그 틱 코드가 사는 블록 뱅크 번호(MPR5 가 이 뱅크일 때만 부른다)
IRQ_SITE = 0x4154  # 뱅크 0x68 `$40CF` 핸들러 안 `JSR $57A5` — 🔴 매 VBlank 에 지나는 자리(`$414F` 의 `JSR $E063` 은 메인이 화면 갱신을 요청한 프레임에만 지나서 장면 연출 중 카운터가 멈췄다, 10-13)
IRQ_ORIG = 0x57A5  # IRQ_SITE 의 원래 호출 대상
GW_MAGIC = b"\xc7\x5e"  # 블록 꼬리의 서명 2B — 장면이 바뀌어 블록이 갈렸으면 이 자리에 이게 없다


PLAY_BLK = bytes(
    [0xAD, *VOICE_ARM.to_bytes(2, "little"), 0xF0, 22]  # LDA arm · BEQ skip
    + [0xAD, *ADPCM_STAT.to_bytes(2, "little"), 0x29, 0x08, 0xF0, 15]  # LDA $180C · AND #8 · BEQ skip
    + [0x9C, *VOICE_ARM.to_bytes(2, "little")]  # STZ arm
    + [0xAD, *FRAMECNT.to_bytes(2, "little"), 0x8D, *PLAYSTART.to_bytes(2, "little")]  # LDA cnt · STA ps
    + [0xAD, *(FRAMECNT + 1).to_bytes(2, "little"), 0x8D, *(PLAYSTART + 1).to_bytes(2, "little")]
)  # 27B — 재생이 시작됐나 보는 블록(카운터 증가 바로 뒤)


def tick_routine() -> bytes:
    """VBlank 마다 부르는 트램펄린(`IRQ_SITE` 가 `JSR` 한다) — 카운터를 올리고, **자막 틱이 켜져 있으면** 씬 블록 안의 틱을 부른 뒤 원래 대상(`JMP $57A5`)으로.

    켜짐 조건 셋: `GW_FLAG` ≠ 0 · MPR5($A000 창) 가 `GW_FLAG` 의 뱅크 · 블록 꼬리의 서명 2B 가 맞음. 둘째·셋째는 장면이 바뀌어 틱 코드가 사라진 뒤 엉뚱한 곳을 부르지 않게 한다.
    블록 쪽 초기화(`gwin_rt`)가 서명 주소(`TICK_SIG_OP`)·호출 대상(`TICK_CALL_OP`) 피연산자를 RAM 에서 채운다. A·X·Y 는 핸들러가 이미 저장했다.
    """
    c, f = FRAMECNT, GW_FLAG
    code = bytearray()
    br: list[int] = []  # `done` 으로 가는 분기 오프셋 자리

    def b(*bs):
        code.extend(bs)

    def to_done(opcode):
        b(opcode, 0)
        br.append(len(code) - 1)

    b(0xEE, *c.to_bytes(2, "little"), 0xD0, 0x03, 0xEE, *(c + 1).to_bytes(2, "little"))  # INC cnt · BNE +3 · INC cnt+1
    b(*PLAY_BLK)
    b(0xAD, *f.to_bytes(2, "little"))  # LDA flag
    to_done(0xF0)  # BEQ done
    b(0x43, 0x20, 0xCD, *f.to_bytes(2, "little"))  # TMA MPR5 · CMP flag
    to_done(0xD0)  # BNE done
    for m in GW_MAGIC:
        b(0xAD, 0, 0, 0xC9, m)  # LDA sig+k · CMP magic[k]
        to_done(0xD0)
    b(0x20, 0, 0)  # JSR tick
    done = len(code)
    b(0x4C, *IRQ_ORIG.to_bytes(2, "little"))
    for i in br:
        code[i] = done - (i + 1)
    return bytes(code)


# 🔴 나레이션 ON 자막 모드에서 대사창 넘김 커서(▽)를 숨긴다(마스터 10-16 「나래이션 일 때 대사창 커서도 안 나오게」).
#   커서는 엔진 뱅크 0x6C 의 `$6CC3` 가 매 프레임 상태 바이트(`$3559,X` 비트6)를 16프레임마다 뒤집어 깜빡인다(비트6=1 이 꺼진 쪽).
#   그 `JSR $6CC3` 넷(`$6BAA`·`$6BDD`·`$6C2C`·`$6D23`)을 이 루틴으로 돌린다 — 원래 루틴을 부른 뒤 자막 모드(`BLINK_FLAG`)면 비트6 을 1 로 고정.
#   X 는 `$6CC3` 가 남긴 커서 번호 그대로, A·Y 는 호출부(`$4FD8` 인자)가 쓰므로 비트6 이 1 인 원래 결과와 같은 꼴로 돌려준다.
BLINK_ADDR = TICK_ADDR + 0x50  # 틱 트램펄린 끝($2443) 뒤 빈 자리 — FRAMECNT($2474) 앞
BLINK_FLAG = 0x5FFD  # narration_gates.AUTO_FLAG — 자막 모드(뱅크 0x68 꼬리 `$5FFD`, 늘 `$4000` 창에 있다). 같은 값임을 테스트가 본다
BLINK_ORIG = 0x6CC3  # 원래 깜빡임 루틴(뱅크 0x6C)


def blink_routine() -> bytes:
    return bytes(
        [0x20, *BLINK_ORIG.to_bytes(2, "little")]  # JSR $6CC3
        + [0xAD, *BLINK_FLAG.to_bytes(2, "little"), 0xF0, 8]  # LDA mode · BEQ out
        + [0xBD, 0x59, 0x35, 0x09, 0x40, 0x9D, 0x59, 0x35]  # LDA $3559,X · ORA #$40 · STA $3559,X
        + [0x60]  # out: RTS
    )


# 🔴 나레이션 자막 모드 자동 넘김 때 넘김 효과음(`JSR $67EC` → 효과음 0x14)을 끈다(마스터 10-17). 호출 셋(`$6BFF`·`$6C3C`·`$6D3F`)을 이 거름 루틴으로 돌린다:
#   자막 모드(`BLINK_FLAG`)면 소리 없이 돌아가고 아니면 원래 `$67EC`. 자리 = 깜빡임 루틴 뒤 빈 자리(`$2461~$2473`, 19B 중 9B).
#   ⚠ 엔진 뱅크 0x6C 의 0 런(`$6973`)은 빈 자리가 아니다 — `STA $6973,X` 로 쓰이는 인덱스 표다(devlog 10-16). 처음 거기 얹었다가 옮겼다.
QUIET_ADDR = BLINK_ADDR + 0x11  # 깜빡임 루틴(17B) 바로 뒤
QUIET_ORIG = 0x67EC


def quiet_routine() -> bytes:
    return bytes([0xAD, *BLINK_FLAG.to_bytes(2, "little"), 0xD0, 0x03, 0x4C, *QUIET_ORIG.to_bytes(2, "little"), 0x60])  # LDA mode · BNE +3 · JMP $67EC · RTS


# 🔴 나레이션 자막 모드에서 **화자 이름 글자에도 글자 사이 대기를 건다**(마스터 10-23 「화자 바뀔 때만 흔들린다」 → 흔들림 원인 확정).
#   엔진 글자 찍기(뱅크 0x6C `$66DC`: `LDA $8A · CMP #$06 · BEQ $6712`)는 글자색이 6(노랑 = 화자 이름)이면 대기를 건너뛴다 — 그래서 이름 2~4번째 글자와 이름 뒤 본문 첫 글자가
#   한 틱에 몰린다(글리프 한 자가 프레임의 약 0.3 → 4자 ≈ 1.2프레임). 컷신이 흐르는 자막 모드에선 그 틱이 BG 스크롤 갱신을 한 프레임 밀어 화면 배경이 튄다.
#   그 4바이트를 `JSR 이 루틴 · NOP` 으로 돌린다: 색이 6 이어도 자막 모드(`BLINK_FLAG`)면 Z=0(= 대기를 건다), 아니면 원래 비교 결과 그대로(OFF·일반·전투 = 원판 동작).
#   A 는 이 뒤 곧바로 덮이니 상관없고 X·Y 는 건드리지 않는다. 자리 = 거름 루틴 뒤 빈 자리(`$246A~$2473`, 10B 에 꼭 맞는다).
NAMEWAIT_SITE = 0x66DC  # 뱅크 0x6C
NAMEWAIT_ADDR = QUIET_ADDR + 9  # 거름 루틴(9B) 바로 뒤


def namewait_routine() -> bytes:
    return bytes(
        [0xA5, 0x8A, 0xC9, 0x06, 0xD0, 0x03]  # LDA $8A · CMP #6 · BNE out(다르면 Z=0 그대로)
        + [0xAD, *BLINK_FLAG.to_bytes(2, "little")]  # LDA mode — 색 6 이면 자막 모드일 때 Z=0, 아니면 Z=1
        + [0x60]  # out: RTS
    )


def _tick_layout() -> tuple[tuple[int, int], int]:
    """(서명 `LDA` 피연산자 둘, `JSR tick` 피연산자)의 주소."""
    n = len(tick_routine())
    sig0 = TICK_ADDR + 8 + len(PLAY_BLK) + 3 + 2 + 2 + 3 + 2 + 1  # 앞 부분 길이 + LDA 옵코드 1
    return (sig0, sig0 + 7), TICK_ADDR + n - 3 - 2


TICK_SIG_OP, TICK_CALL_OP = _tick_layout()  # 블록 쪽 초기화가 RAM 에서 채우는 피연산자 자리: 서명 `LDA` 둘 · `JSR tick`


def hook_routine() -> bytes:
    b = _main_asm().bytes()
    assert len(b) <= TICK_ADDR - HOOK_ADDR, len(b)
    pad = bytearray(JOSA_OFF_ADDR - HOOK_ADDR - len(b))
    t = tick_routine()
    at = TICK_ADDR - HOOK_ADDR - len(b)
    pad[at : at + len(t)] = t
    bl = blink_routine()
    assert TICK_ADDR + len(t) <= BLINK_ADDR and BLINK_ADDR + len(bl) <= FRAMECNT, (len(t), len(bl))
    at = BLINK_ADDR - HOOK_ADDR - len(b)
    pad[at : at + len(bl)] = bl
    qr = quiet_routine()
    assert BLINK_ADDR + len(bl) <= QUIET_ADDR and QUIET_ADDR + len(qr) <= FRAMECNT, (len(bl), len(qr))
    at = QUIET_ADDR - HOOK_ADDR - len(b)
    pad[at : at + len(qr)] = qr
    nw = namewait_routine()
    assert QUIET_ADDR + len(qr) <= NAMEWAIT_ADDR and NAMEWAIT_ADDR + len(nw) <= FRAMECNT, (len(qr), len(nw))
    at = NAMEWAIT_ADDR - HOOK_ADDR - len(b)
    pad[at : at + len(nw)] = nw
    return b + bytes(pad)


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
    a.op("JSR", "abs", "josa_has")  # 받침 판정 → HASBAT (`pre` 도 같은 루틴을 부른다)
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
    a.label("josa_has")
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
    a.op("BNE", "rel", "hdone")
    _bit(a, RIEUL_ADDR, "ri")
    a.op("BEQ", "rel", "hdone")
    a.op("STZ", "abs", HASBAT_ADDR)
    a.label("hdone")
    a.op("RTS")
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
    assert len(b) <= EXT_ROOM, len(b)
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


# 🔴 반각 영숫자 표(마지막 글리프 뱅크 꼬리 — 풀기 루틴 바로 뒤 빈 자리): 리드 블록 시작 4B · 비트 마스크 8B · 비트맵 112B(리드마다 28B).
HALF_TAB_ADDR = (WORDCK_MPR << 13) + font.BANK_GLYPH_END + len(unpack_asm().bytes())
HALF_OFFTAB = HALF_TAB_ADDR
HALF_BITM = HALF_OFFTAB + 4
HALF_BITMAP = HALF_BITM + 8
HALF_NARR = HALF_BITMAP + 4 * 28  # 4px 전진 글리프 코드 쌍 셋(i·l·I) — 모자라면 0 쌍
HALF_TAB_LEN = 4 + 8 + 4 * 28 + 6
HALF_WIDE = "mwMW"  # 잉크가 9px 라 8px 전진 두 조각에 안 든다 — 반각으로 안 그리고 평소 12px 칸으로 둔다
HALF_NARROW = "ilI"  # 잉크가 3px 이하 — 4px 전진 한 조각
assert HALF_TAB_ADDR + HALF_TAB_LEN <= (WORDCK_MPR << 13) + 0x2000


def half_tables() -> bytes:
    """리드 F0~F3 의 글리프 번호 → 「ASCII 영숫자」 비트맵. 정본 순서가 곧 글리프 번호다(`font._order_canon`)."""
    bm = bytearray(4 * 28)
    for i, ch in enumerate(font._order_canon()):
        if ch.isascii() and ch.isalnum() and ch not in HALF_WIDE:
            lead, tr = divmod(i, font.PER_LEAD)
            assert lead < 4, i
            bm[lead * 28 + tr // 8] |= 0x80 >> (tr % 8)
    narr = b""
    for ch in HALF_NARROW:
        if ch in font._order_canon():
            narr += font.code_of(font._order_canon().index(ch))
    narr = narr.ljust(6, b"\0")
    return bytes([0, 28, 56, 84]) + bytes(0x80 >> i for i in range(8)) + bytes(bm) + narr


# 🔴 `으로/로` 무받침 — **그리지도 전진하지도 않는다**(10-21 「나이프로로는」). 문안은 「{으로/로}로」 꼴이고(`font.encode` 가 둘째 글자 「로」를 보통 글자로 낸다)
#   토큰은 받침 있으면 「으」, 없으면 **아무것도 안 낸다**(KIND_EATEN — 반각 공백 먹기와 같은 갈래: 칸 수도 안 센다). 판정은 EX_GETFNT 대체 루틴의 `josa_has`
#   를 그대로 부른다. 직전 글자가 우리 글자가 아니면(원문 SJIS) 무받침으로 본다. 자리는 반각 영숫자 표 뒤 꼬리(39B).
JOSA_PRE_ADDR = HALF_TAB_ADDR + HALF_TAB_LEN


def _josa_pre_asm() -> "Asm":
    a = Asm(JOSA_PRE_ADDR)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.JOSA_LEAD)
    a.op("BNE", "rel", "ret")
    a.op("LDA", "zp", 0xF8)
    a.op("CMP", "imm", font.TRAIL0 + 4)
    a.op("BNE", "rel", "ret")
    a.op("PHX")
    a.op("PHY")
    a.op("LDA", "abs", LAST_ADDR)
    a.op("CMP", "imm", font.LEAD0)
    a.op("BCC", "rel", "eat")
    a.op("JSR", "abs", MAIN_LABELS["josa_has"])
    a.op("LDA", "abs", HASBAT_ADDR)
    a.op("BNE", "rel", "out")
    a.label("eat")
    a.op("LDA", "imm", KIND_EATEN)
    a.op("STA", "abs", KIND_ADDR)
    a.label("out")
    a.op("PLY")
    a.op("PLX")
    a.label("ret")
    a.op("RTS")
    return a


def josa_pre() -> bytes:
    b = _josa_pre_asm().bytes()
    assert JOSA_PRE_ADDR + len(b) <= (WORDCK_MPR << 13) + 0x2000, len(b)
    return b


def finish_banks(glyph_bank: bytes) -> bytes:
    """글리프 뱅크에 코드를 얹는다 — 뱅크마다 꼬리에 풀기 루틴, 마지막 뱅크 글리프 끝 `CODE_SLOTS` 칸에 반 칸 전진 + 어절 줄바꿈."""
    gb = bytearray(glyph_bank)
    code = unpack_code()
    for k in range(font.GLYPH_NBANKS):
        at = k * 0x2000 + font.BANK_GLYPH_END
        assert not gb[at : (k + 1) * 0x2000].strip(b"\0"), "글리프가 뱅크 꼬리 코드 자리를 덮는다"
        gb[at : at + len(code)] = code
    at = len(gb) - 0x2000 + font.BANK_GLYPH_END - font.CODE_BYTES
    assert not gb[at : at + font.CODE_BYTES].strip(b"\0"), "글리프가 마지막 뱅크 코드 자리를 덮는다"
    gb[at : at + font.CODE_BYTES] = hook_entry() + wordck()
    tab = len(gb) - 0x2000 + (HALF_TAB_ADDR - (WORDCK_MPR << 13))
    assert not gb[tab : tab + HALF_TAB_LEN].strip(b"\0"), "반각 영숫자 표 자리가 비어 있지 않다"
    gb[tab : tab + HALF_TAB_LEN] = half_tables()
    jp = josa_pre()
    assert not gb[tab + HALF_TAB_LEN : tab + HALF_TAB_LEN + len(jp)].strip(b"\0"), "조사 선처리 자리가 비어 있지 않다"
    gb[tab + HALF_TAB_LEN : tab + HALF_TAB_LEN + len(jp)] = jp
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
    a.op("CMP", "imm", font.HALF_SPACE[0])  # 반각 공백(대사창)
    a.op("BEQ", "rel", "issp")
    a.op("CMP", "imm", SPACE_CODE[0])
    a.op("BNE", "rel", "nsp")
    a.op("LDA", "zp", 0xF8)
    a.op("CMP", "imm", SPACE_CODE[1])
    a.op("BNE", "rel", "nsp")
    a.label("issp")
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
    a.op("CMP", "imm", font.HALF_SPACE[0])  # 반각 공백도 어절 끝
    a.op("BEQ", "rel", "done")
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
    a.op("BNE", "rel", "j0")
    a.op("TXA")
    a.op("BEQ", "rel", "done")
    a.op("LDX", "imm", 0)
    a.op("LDA", "zp", 0x93)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0x94)
    a.op("STA", "zp", 0xED)
    a.label("rp")  # 새 읽기 위치(`$EC/$ED`)에서 처음부터 이어 잰다
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
    # 🔴 조각 이음(`0F lo hi` = 뒤 조각으로 점프): 한 낱말이 조각 경계에 걸리면(「맞」+「지 않았다」) 앞 조각만 재서 낱말이 짧게 잡혀
    #    줄 끝에서 「맞 / 지」로 갈렸다. 점프 목적지로 읽기 위치를 옮겨 낱말 끝(공백·제어)까지 이어 잰다. 문안마다 손대지 않는다.
    a.label("j0")
    a.op("CMP", "imm", 0x0F)
    a.op("BNE", "rel", "done")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("PHA")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "zp", 0xED)
    a.op("PLA")
    a.op("STA", "zp", 0xEC)
    a.op("BRA", "rel", "rp")
    for v in ("prevsp", "cnt"):
        a.label(v)
        a.data(b"\x00")
    return a


def wordck() -> bytes:
    b = _wordck_asm().bytes()
    assert len(b) <= WORDCK_ROOM, (len(b), WORDCK_ROOM)
    return b + b"\0" * (WORDCK_ROOM - len(b))


def hook_wrap_fix() -> bytes:
    b = _wrap_asm().bytes()
    assert len(b) <= WRAP_ROOM, len(b)
    return b


# ── 반 칸(4px) 전진 변형 코드 ───────────────────────────────────────────────────────────
# 엔진(뱅크 0x6C) 쪽 주소 — 전부 BP·디스어셈블로 확인했다(judgments 「조판 기반」 10-07 · devlog 10-07 (5)).
ENG_DRAW = 0x704A  # `$7047 INC $38BB` 바로 뒤 — 글자 하나 그리기 본체(토글 0 이면 `$6F7E`, 1 이면 `$7052`), 끝은 RTS
ENG_ADV_COL = 0x71EA  # `$717A`(열 패턴 쓰기)의 꼬리 — 패턴 포인터 `$38C1` 를 한 열(`$20`) 앞으로 + VDC MAWR 복원, RTS
ENG_BLANK_COLS = 0x70F5  # 토글 1 그리기 중 「패턴 두 열 쓰기 + 새 열 BAT 하나 + 풀 2장」 — 끝은 RTS
ENG_REWIND = (
    0x723C  # A = 되돌릴 워드 수 — `$38C1` 를 뒤로(고리 되감기 포함), 토글 0 그리기가 끝에 쓴다
)
ENG_PLANES = 0x72A5  # 글리프 버퍼(`$37BA`~ 24B)를 색 비트(`$8A`)대로 면 버퍼(`$37FA`·`$383A`·`$387A`, X 오프셋)로 옮긴다
ENG_COL_COUNT = 0x38BB  # 칸 수(글자마다 +1) — 줄바꿈 판정이 읽는다
ENG_TOGGLE = (
    0x38BA  # 0 = 열 경계에서 시작 · 1 = 열 가운데(앞 글자의 오른쪽 4px 가 이미 그 열에 있다)
)
ENG_GLYPH_BUF = 0x37BA  # 후킹 루틴이 글리프 24B 를 내는 버퍼
ENG_PLANE_A, ENG_PLANE_B, ENG_PLANE_C = (
    0x37FA,
    0x383A,
    0x387A,
)  # `$72A5` 가 채우는 면 버퍼(행마다 왼쪽·오른쪽 바이트)
ENG_PATTERN = 0x38C1  # 지금 열의 패턴 VRAM 주소(워드) — 한 열 = +$20
ENG_FETCH = 0x7040  # 글리프 24B 를 `($FA)` 로 받는다(후킹 루틴 — `$FF`=1 을 얹고 `JMP $2300`)
ENG_COLWRITE = 0x717A  # Y = 면 버퍼 시작 오프셋(+1 = 오른쪽 바이트) — 열 하나를 `$38C1` 에 쓰고 포인터를 한 열 앞으로


KIND_PLAIN, KIND_VARIANT, KIND_PUNCT, KIND_SPACE, KIND_EATEN, KIND_HALF, KIND_HALF4 = 0, 1, 2, 3, 4, 5, 6


def _narrow_codes():
    """반각 부호(. , ! ?)의 글리프 코드 — 글리프 정본에서 읽는다. 렌더러 훅은 「리드 F0 · 트레일 < LOW 또는 == Q」로 가른다."""
    canon = font._order_canon()
    return {ch: font.code_of(canon.index(ch)) for ch in font.NARROW_PUNCT}


_NC = _narrow_codes()
NARROW_LOW = 0x28  # 트레일 < 0x28 = 「! , - .」 (정본 앞 다섯 칸 중 앞 넷 — `/` 는 안 그려지는 조사 토큰 글자)
NARROW_Q = _NC["?"][1]
NARROW_DOT = _NC["·"]  # 가운뎃점은 정본 뒤쪽(다른 리드)이라 코드 한 쌍으로 비교한다
assert all(_NC[ch][0] == font.LEAD0 and _NC[ch][1] < NARROW_LOW for ch in "!,."), _NC
assert _NC["?"][0] == font.LEAD0 and NARROW_Q >= NARROW_LOW
assert NARROW_DOT[0] < font.VARIANT_LEAD0


def _narrow_asm() -> "Asm":
    """`JSR` 로 불리는 `$7047` 의 새 머리 — 원래 `INC $38BB` 였던 3B 를 대신한다. RAM 에는 얇은 껍데기만 두고 판단·전진은
    글리프 뱅크 꼬리(`_entry_asm`)에서 한다(MPR2 에 잠깐 걸어 SEI 로 부른다 — `mark` 와 같은 방식).

    ① `pre`(X=0)가 `F9/F8` 를 보고 `kind` 를 정한다: 0 평범 · 1 변형(F4~F7 — 리드를 F0~F3 로 내린다) · 2 반각 부호(`. , ! ?`) ·
       3 반각 공백(`F8 24`) · 4 줄 머리 공백(어절 판정 `flag` — 안 먹는다).
    ② kind 0 이면 RTS(= `$704A` 로 이어져 원래대로 그려진다). kind 1(변형)만 `JSR $704A` 로 평소처럼 그린다 — 나머지는 `post` 가 알아서 한다.
    ③ `$7047` 의 JSR 이 쌓은 복귀 주소를 버리고(PLA×2) `post`(X=1)로 4px 전진·부호 되감기를 한다 — 복귀가 원래 호출자다.

    `rem` = 4px 단위로 쌓인 나머지(0·4·8) — 12px 가 차면 칸 수를 하나 올린다. 줄이 바뀌거나 창이 비워질 때(`$6AEA`·`$6B73` 의
    `STZ $38BB`)는 `rstz` 가 같이 0 으로 만든다.
    """
    a = Asm(NARROW_ADDR)
    a.label("rem")
    a.data(b"\x00")
    a.label("kind")
    a.data(b"\x00")
    a.label("phase")  # 반각 영숫자 두 번째 그리기의 몫(0 = 부호 · 1 = 왼쪽 4px · 2 = 오른쪽 4px)
    a.data(b"\x00")
    a.label("glue")  # X = 0(pre) / 1(post) — A 는 못 쓴다(MPR 복원), X 는 지킨다
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", WORDCK_MPR)
    a.op("PHA")
    a.op("LDA", "imm", WORDCK_BANK)
    a.op("TAM", "tam", WORDCK_MPR)
    a.op("JSR", "abs", ENTRY_ADDR)
    a.op("PLA")
    a.op("TAM", "tam", WORDCK_MPR)
    a.op("PLP")
    a.op("RTS")
    a.label("entry")
    a.op("INC", "abs", ENG_COL_COUNT)
    a.op("LDX", "imm", 0)
    a.op("JSR", "abs", "glue")  # pre
    a.op("LDA", "abs", "kind")
    a.op("BEQ", "rel", "ret")
    a.op("CMP", "imm", KIND_VARIANT)
    a.op("BNE", "rel", "skip")
    a.op("JSR", "abs", ENG_DRAW)
    a.label("skip")
    a.op("PLA")
    a.op("PLA")
    a.op("LDX", "imm", 1)
    a.op("JSR", "abs", "glue")  # post
    a.label("ret")
    a.op("RTS")
    a.label("rstz")  # `STZ $38BB` 의 자리(3B)에 `JSR` — 칸 수와 나머지를 같이 0 으로
    a.op("STZ", "abs", ENG_COL_COUNT)
    a.op("STZ", "abs", "rem")
    a.op("RTS")
    return a


NARROW_LABELS = _narrow_asm().labels
REM_ADDR = NARROW_LABELS["rem"]
KIND_ADDR = NARROW_LABELS["kind"]
PHASE_ADDR = NARROW_LABELS["phase"]
GLUE_ADDR = NARROW_LABELS["glue"]
NARROW_ENTRY = NARROW_LABELS["entry"]  # `$7047` 의 새 JSR 대상
RSTZ_ADDR = NARROW_LABELS["rstz"]  # `$6AEA`·`$6B73` 의 새 JSR 대상


def _entry_asm() -> "Asm":
    """글리프 뱅크 꼬리 코드 — MPR2 에서 돈다. X=0 이면 `pre`(판단), X=1 이면 `post`(전진).

    **post** — 이미 그린(또는 안 그리는) 자리에서:
    · 나머지(`rem`)에 4 를 더해 12 가 되면 0 으로 하고 칸 수를 올린다 — 칸 수는 늘 「12px 로 몇 칸」(= 줄바꿈 판정의 단위)이다.
      반각 공백·반각 부호는 `INC` 를 먼저 물려(`DEC $38BB`) 글자 한 칸을 안 센다. 변형(kind 1)은 글자 칸 + 반 칸이다.
    · 토글 1(열 가운데)이면 4px 가 열 경계다 — 토글 0 으로, 패턴 포인터를 한 열 앞으로(`$71EA` 가 해 준다).
    · 토글 0(열 경계)이면 4px 가 열 가운데다 — 빈 열 하나를 새로 만든다: 면 버퍼를 0 으로 밀고(`$72A5`), 토글 1 그리기의
      「패턴 두 열 + BAT 한 열 + 풀 2장」(`$70F5`)을 그대로 불러 빈 열을 쓰고, 패턴 포인터를 두 열 되감는다(둘째 열은 쓰고 버리는
      자리 — 다음 글자가 덮어쓴다).
    **반각 부호**(kind 2)는 12px 칸에 그린 **뒤 8px 되감는다**(잉크가 왼쪽 4px 안이라 다음 글자가 그 뒤에 겹쳐 그려진다):
    · 토글 1(= 열 경계에서 그렸다) — 열 가운데 상태가 된다. 반쪽 열은 부호가 든 열이라 면 버퍼의 오른쪽 바이트를 왼쪽 바이트로 덮어
      「앞 글자의 오른쪽 4px」 자리에 부호 잉크가 오게 하고, BAT 를 한 열·패턴 포인터를 한 열 되감는다.
    · 토글 0(= 열 가운데에서 그렸다) — 새 열은 비어 있다. BAT 와 패턴 포인터만 한 열 되감는다.
    """
    a = Asm(ENTRY_ADDR)
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "pre")
    a.op("JMP", "abs", "post")
    a.label("pre")
    # ── pre ──
    a.op("STZ", "abs", KIND_ADDR)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", font.HALF_SPACE[0])
    a.op("BEQ", "rel", "ishalf")
    a.op("CMP", "imm", font.LEAD0)
    a.op("BNE", "rel", "notf0")
    a.op("LDA", "zp", 0xF8)
    a.op("CMP", "imm", NARROW_LOW)
    a.op("BCC", "rel", "ispunct")
    a.op("CMP", "imm", NARROW_Q)
    a.op("BEQ", "rel", "ispunct")
    a.op("JMP", "abs", "chkh")  # 그 밖의 우리 글리프 — 반각 영숫자인지 본다
    a.label("notf0")  # 가운뎃점 — 리드가 다르다
    a.op("CMP", "imm", NARROW_DOT[0])
    a.op("BNE", "rel", "tryvar")
    a.op("LDA", "zp", 0xF8)
    a.op("CMP", "imm", NARROW_DOT[1])
    a.op("BEQ", "rel", "ispunct")
    a.op("JMP", "abs", "chkh")
    a.label("tryvar")
    a.op("AND", "imm", 0xFC)
    a.op("CMP", "imm", font.VARIANT_LEAD0)
    a.op("BEQ", "rel", "isvar")
    a.op("CMP", "imm", font.LEAD0)
    a.op("BEQ", "rel", "chkh")  # 리드 F1~F3 — 우리 글리프
    a.op("JMP", "abs", JOSA_PRE_ADDR)  # 조사 토큰 — `으로/로` 무받침이면 안 그린다
    a.label("isvar")
    a.op("LDA", "zp", 0xF9)
    a.op("SBC", "imm", font.VARIANT_LEAD0 - font.LEAD0)  # CMP 가 같아서 캐리 1
    a.op("STA", "zp", 0xF9)
    a.op("LDA", "imm", KIND_VARIANT)
    a.op("BRA", "rel", "setk")
    a.label("ispunct")
    a.op("LDA", "imm", KIND_PUNCT)
    a.op("BRA", "rel", "setk")
    a.label("ishalf")
    a.op("LDA", "abs", WRAP_ADDR)  # `flag` — 넘긴 줄 첫 공백이면 먹는다
    a.op("BEQ", "rel", "h3")
    a.op("LDA", "imm", KIND_EATEN)
    a.op("BRA", "rel", "setk")
    a.label("h3")
    a.op("LDA", "imm", KIND_SPACE)
    a.label("setk")
    a.op("STA", "abs", KIND_ADDR)
    a.label("pre_done")
    a.op("RTS")
    # 🔴 반각 영숫자(마스터 10-09: 전투 문장은 공백·부호·**영숫자**가 반각) — 우리 글리프 코드(리드 F0~F3 · 트레일 0x24~)를 비트맵으로 가른다.
    #    리드마다 28B(220 비트) 블록이 이어진다: 주소 = `HALF_BITMAP + 리드×28 + 트레일/8` · 비트 = 트레일 % 8(MSB 먼저).
    a.label("chkh")
    a.op("PHX")
    a.op("PHY")
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", font.LEAD0)
    a.op("TAX")
    a.op("LDA", "absx", HALF_OFFTAB)
    a.op("STA", "abs", BITCNT_ADDR)  # 리드 블록 시작
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", font.TRAIL0)
    a.op("PHA")
    a.op("LSR")
    a.op("LSR")
    a.op("LSR")
    a.op("CLC")
    a.op("ADC", "abs", BITCNT_ADDR)
    a.op("TAY")
    a.op("PLA")
    a.op("AND", "imm", 7)
    a.op("TAX")
    a.op("LDA", "absy", HALF_BITMAP)
    a.op("AND", "absx", HALF_BITM)
    a.op("BEQ", "rel", "chk_out")
    a.op("LDX", "imm", 4)  # 좁은 영문(i·l·I — 잉크 3px 이하)은 4px 전진 한 조각이다 — 코드 쌍 셋을 훑는다
    a.label("nl")
    a.op("LDA", "absx", HALF_NARR)
    a.op("CMP", "zp", 0xF9)
    a.op("BNE", "rel", "nx")
    a.op("LDA", "absx", HALF_NARR + 1)
    a.op("CMP", "zp", 0xF8)
    a.op("BEQ", "rel", "nf")
    a.label("nx")
    a.op("DEX")
    a.op("DEX")
    a.op("BPL", "rel", "nl")
    a.op("LDA", "imm", KIND_HALF)
    a.op("BRA", "rel", "chk_st")
    a.label("nf")
    a.op("LDA", "imm", KIND_HALF4)
    a.label("chk_st")
    a.op("STA", "abs", KIND_ADDR)
    a.label("chk_out")
    a.op("PLY")
    a.op("PLX")
    a.op("RTS")
    # ── post ──
    a.label("post")
    a.op("LDA", "abs", KIND_ADDR)
    a.op("CMP", "imm", KIND_EATEN)
    a.op("BNE", "rel", "p1")
    a.op("DEC", "abs", ENG_COL_COUNT)
    a.op("RTS")
    a.label("p1")
    a.op("CMP", "imm", KIND_PUNCT)
    a.op("BEQ", "rel", "punct")
    a.op("CMP", "imm", KIND_HALF)
    a.op("BNE", "rel", "p2")
    a.op("JMP", "abs", "half")
    a.label("p2")
    a.op("CMP", "imm", KIND_HALF4)
    a.op("BNE", "rel", "p3")
    a.op("JMP", "abs", "half4")
    a.label("p3")
    a.op("CMP", "imm", KIND_SPACE)
    a.op("BNE", "rel", "adv")
    a.op("DEC", "abs", ENG_COL_COUNT)  # 반각 공백은 글자 칸을 안 센다
    a.label("adv")
    a.op("JSR", "abs", "remadd")
    a.op("LDA", "abs", ENG_TOGGLE)
    a.op("BEQ", "rel", "mid")
    a.op("STZ", "abs", ENG_TOGGLE)
    a.op("JMP", "abs", ENG_ADV_COL)
    a.label("mid")
    a.op("LDX", "imm", 23)
    a.label("zero")
    a.op("STZ", "absx", ENG_GLYPH_BUF)
    a.op("DEX")
    a.op("BPL", "rel", "zero")
    a.op("CLX")
    a.op("JSR", "abs", ENG_PLANES)
    a.op("INC", "abs", ENG_TOGGLE)
    a.op("JSR", "abs", ENG_BLANK_COLS)
    for _ in range(2):
        a.op("LDA", "imm", 0x20)
        a.op("JSR", "abs", ENG_REWIND)
    a.op("RTS")
    a.label("punct")
    a.op("DEC", "abs", ENG_COL_COUNT)  # 반각 부호도 글자 칸을 안 센다
    a.label("pun2")
    a.op("JSR", "abs", "remadd")
    a.op("LDA", "abs", ENG_TOGGLE)
    a.op("BNE", "rel", "pmid")
    # 열 경계에서 시작 — 부호는 열 가운데 상태(토글 1)로 끝난다: 4px 전진의 「빈 열」 자리에 부호 잉크를 담는다
    a.op("LDA", "imm", ENG_GLYPH_BUF & 0xFF)
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", ENG_GLYPH_BUF >> 8)
    a.op("STA", "zp", 0xFB)
    a.op("JSR", "abs", ENG_FETCH)
    a.op("CLA")
    a.op("JSR", "abs", "mask")
    a.op("LDX", "imm", 22)
    a.label("pc")
    a.op(
        "LDA", "absx", ENG_GLYPH_BUF
    )  # 행마다 오른쪽 바이트 := 왼쪽 바이트(`$70F5` 가 오른쪽 바이트로 열 하나를 쓴다)
    a.op("STA", "absx", ENG_GLYPH_BUF + 1)
    a.op("DEX")
    a.op("DEX")
    a.op("BPL", "rel", "pc")
    a.op("CLX")
    a.op("JSR", "abs", ENG_PLANES)
    a.op("INC", "abs", ENG_TOGGLE)
    a.op("JSR", "abs", ENG_BLANK_COLS)
    for _ in range(2):
        a.op("LDA", "imm", 0x20)
        a.op("JSR", "abs", ENG_REWIND)
    a.op("RTS")
    a.label("pmid")
    # 열 가운데에서 시작 — 앞 글자의 오른쪽 4px 가 든 반쪽 열에 부호 잉크를 겹쳐(토글 1 그리기의 첫 절반) 쓰고 열 경계(토글 0)로 간다
    a.op("LDA", "imm", (ENG_GLYPH_BUF + 0x20) & 0xFF)
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", (ENG_GLYPH_BUF + 0x20) >> 8)
    a.op("STA", "zp", 0xFB)
    a.op("JSR", "abs", ENG_FETCH)
    a.op("LDA", "imm", 0x20)
    a.op("JSR", "abs", "mask")
    a.op("LDX", "imm", 0x20)
    a.op("JSR", "abs", ENG_PLANES)
    a.op("LDY", "imm", 22)
    a.label("po")
    for base in (ENG_PLANE_A, ENG_PLANE_B, ENG_PLANE_C):
        a.op("LDA", "absy", base + 0x20)
        for _ in range(4):
            a.op("LSR")
        a.op("ORA", "absy", base + 1)
        a.op("STA", "absy", base + 1)
    a.op("DEY")
    a.op("DEY")
    a.op("BPL", "rel", "po")
    a.op("LDA", "imm", 0)
    a.op("STA", "zp", 0xF7)
    a.op("ST0", "imm", 0)
    a.op("LDA", "abs", ENG_PATTERN)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", ENG_PATTERN + 1)
    a.op("STA", "abs", 0x0003)
    a.op("LDA", "imm", 2)
    a.op("STA", "zp", 0xF7)
    a.op("ST0", "imm", 2)
    a.op("LDY", "imm", 1)
    a.op("JSR", "abs", ENG_COLWRITE)
    a.op("STZ", "abs", ENG_TOGGLE)
    a.op("RTS")
    # **반각 영숫자**(kind 5): 8px 전진 = 4px 잉크 조각 둘 — 같은 글자를 반각 부호 갈래로 **두 번** 그린다. 1번은 글리프 왼쪽 4px
    #   (`AND #$F0`), 2번은 오른쪽 4px 를 왼쪽으로 민 것(`ASL×4`) — 부호는 잉크가 왼쪽 4px 안이라야 하므로 영숫자 8px 를 둘로 쪼갠다.
    #   칸 수는 엔진의 `INC`(+1)를 한 번만 되돌리고(`DEC`), 나머지 `rem` 은 조각마다 +4 라 8px 가 쌓인다.
    a.label("half")
    a.op("DEC", "abs", ENG_COL_COUNT)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", PHASE_ADDR)
    a.op("JSR", "abs", "pun2")
    a.op("LDA", "imm", 2)
    a.op("STA", "abs", PHASE_ADDR)
    a.op("JSR", "abs", "pun2")
    a.op("STZ", "abs", PHASE_ADDR)
    a.op("RTS")
    a.label("half4")  # 좁은 영문 — 왼쪽 4px 조각 하나(4px 전진)
    a.op("DEC", "abs", ENG_COL_COUNT)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", PHASE_ADDR)
    a.op("JSR", "abs", "pun2")
    a.op("STZ", "abs", PHASE_ADDR)
    a.op("RTS")
    a.label("mask")  # A = 글리프 버퍼 시작 오프셋(0 또는 0x20) — 행마다 왼쪽 바이트를 phase 대로 거른다
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "abs", PHASE_ADDR)
    a.op("BEQ", "rel", "mk_out")
    a.op("LDA", "zp", 0xEC)
    a.op("CLC")
    a.op("ADC", "imm", 22)
    a.op("TAX")
    a.op("LDA", "abs", PHASE_ADDR)
    a.op("CMP", "imm", 2)
    a.op("BCS", "rel", "mk2")
    a.label("mk1")
    a.op("LDA", "absx", ENG_GLYPH_BUF)
    a.op("AND", "imm", 0xF0)
    a.op("STA", "absx", ENG_GLYPH_BUF)
    a.op("DEX")
    a.op("DEX")
    a.op("TXA")
    a.op("SEC")
    a.op("SBC", "zp", 0xEC)
    a.op("BPL", "rel", "mk1")
    a.op("RTS")
    a.label("mk2")
    a.op("LDA", "absx", ENG_GLYPH_BUF)
    for _ in range(4):
        a.op("ASL")
    a.op("STA", "absx", ENG_GLYPH_BUF)
    a.op("DEX")
    a.op("DEX")
    a.op("TXA")
    a.op("SEC")
    a.op("SBC", "zp", 0xEC)
    a.op("BPL", "rel", "mk2")
    a.label("mk_out")
    a.op("RTS")
    a.label("remadd")
    a.op("LDA", "abs", REM_ADDR)
    a.op("CLC")
    a.op("ADC", "imm", 4)
    a.op("CMP", "imm", 12)
    a.op("BCC", "rel", "st")
    a.op("INC", "abs", ENG_COL_COUNT)
    a.op("CLA")
    a.label("st")
    a.op("STA", "abs", REM_ADDR)
    a.op("RTS")
    return a


# 🔴 **파티 호칭 접미(마스터 10-09: 「도망쳤다는 파티 없을 땐 세리오스는, 있을 땐 (리더)들은」)** — 전투 문구의 파티 행위자 이름은
#   `$689C` 가 이름(`$C02D` 번 리더)을 버퍼에 옮긴 뒤 `$68A3~` 가 접미 6B(원본 「 たち」+종결 `06`)를 **언제나** 붙인다 — 혼자여도 「세리오스たち는」.
#   `$68A5` 의 `LDA #6 / STA $21 / CLX`(5B)를 `JSR 이 루틴 / NOP / NOP` 으로 바꿔 **복사 시작(X)·길이(`$21`)** 만 정한다.
#   자료(`$68C9`, 6B) = [들 2B][06] + 채움 — 파티 있음: X=0 · 길이 3(「들」+종결) / 혼자: X=2 · 길이 1(종결뿐).
#   파티 판정 = 동료 레코드 셋(`$C340`·`$C380`·`$C3C0`)의 첫 바이트 비트 7(=파티 밖) 이 **셋 다** 서 있으면 혼자.
PARTY_SUFFIX_SITE = 0x68A5


def _party_asm() -> "Asm":
    a = Asm(NARROW_ADDR + len(_narrow_asm().bytes()))
    a.label("party")
    a.op("LDA", "abs", 0xC340)
    a.op("AND", "abs", 0xC380)
    a.op("AND", "abs", 0xC3C0)  # 비트 7 = 셋 다 파티 밖(혼자)
    a.op("ASL")  # C = 혼자
    a.op("CLA")
    a.op("ROL")  # A = 혼자 ? 1 : 0
    a.op("ASL")  # A = 혼자 ? 2 : 0
    a.op("TAX")  # X = 복사 시작
    a.op("EOR", "imm", 3)  # A = 혼자 ? 1 : 3
    a.op("STA", "zp", 0x21)  # 복사 길이
    a.op("RTS")
    return a


PARTY_ADDR = _party_asm().labels["party"]


def party_suffix() -> bytes:
    return _party_asm().bytes()


def hook_narrow() -> bytes:
    b = _narrow_asm().bytes()
    assert len(b) <= NARROW_ROOM, (len(b), NARROW_ROOM)
    return b


def hook_entry() -> bytes:
    b = _entry_asm().bytes()
    assert len(b) <= ENTRY_ROOM, (len(b), ENTRY_ROOM)
    return b + b"\0" * (ENTRY_ROOM - len(b))


WRAP_LABELS = _wrap_asm().labels
ORPHAN_ADDR = WRAP_LABELS["orphan"]  # $6D9C 의 새 JSR 대상
MARK_ADDR = WRAP_LABELS["mark"]  # $6723 의 새 JSR 대상
EAT_ADDR = WRAP_LABELS["eat"]  # $6730 의 새 JSR 대상


def payload(table) -> bytes:
    """스텁이 통째로 옮기는 페이로드 — 루틴 · 조사표 · 받침 비트맵 둘 · LAST · 확장 블록 · 줄바꿈 품질 · 반 칸 전진."""
    p = bytearray(hook_routine())
    p += font.josa_offsets(table)
    p += b"\0" * (BATCHIM_ADDR - HOOK_ADDR - len(p))
    has, rieul = font.batchim_tables(font.build_table.order)
    assert len(has) == len(rieul) == _BIT_BYTES
    p += has
    p += rieul
    p += b"\0" * (EXT_ADDR - HOOK_ADDR - len(p))  # LAST(2B) 는 0 으로 시작
    p += hook_ext()
    p += b"\0" * (WRAP_ADDR - HOOK_ADDR - len(p))
    p += hook_wrap_fix()
    p += b"\0" * (NARROW_ADDR - HOOK_ADDR - len(p))
    p += hook_narrow()
    p += party_suffix()
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


MAIN_LABELS = _main_asm().labels  # EX_GETFNT 대체(조사 포함) 루틴의 라벨 — `pre` 가 `josa_pre` 로 뛴다


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
        # 🔴 **옮긴 뒤 원본 자리를 0 으로 되돌린다.** 뱅크 0x7C~0x7D 는 게임의 워크 영역이고
        #    (전투 중 덤프에서 게임이 덮어쓴 걸 봤다) 원판은 0 으로 실린다. 우리 글리프를 남겨 두면
        #    「0 으로 초기화된 자리」를 가정하는 코드가 다른 초기값을 본다 — 체크리스트 「빈 자리의 근거」.
        a.op("STZ", "abs", 0xA000)
        a.tii(0xA000, 0xA001, 0x1FFF)  # 겹침 복사로 0 을 뱅크 전체에 전파
    a.op("LDA", "imm", 0x7F)
    a.op("TAM", "tam", 5)
    a.tii(0xA000, HOOK_ADDR, PAYLOAD_LEN)
    a.op(
        "STZ", "abs", 0x22BC
    )  # ⚠ 옛 자동 넘김 표시 자리 — 지금은 안 쓴다(`narration_gates.AUTO_FLAG` 는 뱅크 0x68 `$5FFD`). `$22BC~` 는
    #   BIOS 가 쓰는 자리라(devlog 10-06) 이 0 쓰기는 다음 라운드에 뺀다 — 동작은 이번에 안 바꾼다(status 「다음 라운드」)
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
