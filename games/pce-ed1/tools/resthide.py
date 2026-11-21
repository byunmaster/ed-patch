"""서 있는 동안 HUD 이름판 스프라이트(SAT 0~8)를 숨긴다 — 한 줄 스프라이트 16개 한계로 필드 인물이 잘리는 것 (마스터 11-21 「레지스탕스짤림 먼저 확인」).

## 무엇이 잘렸나 (실측 11-21, mednafen · 제품 롬 74148ba0 · 장1 씬3 필드)

오른쪽 HUD 이름판은 **BG 판 위에 같은 그림의 스프라이트 9개(SAT 0~8)** 가 겹쳐 있다 — 맵이 스크롤되는 동안 BG 판이 밀리는 것을 스프라이트가 덮는 꼴이다.
이 9개 + 양쪽 막대(9~14)가 줄마다 칸을 먹어, 인물이 가로로 늘어선 줄(레지스탕스 장면 화면 줄 y96)은 17개가 되어 맨 뒤 조각이 안 그려진다(VDC 는 한 줄 16개).
맵이 **멈춰 있을 때**는 BG 판과 스프라이트 판이 같은 그림이다(실측: 네 귀퉁이 픽셀 4개만 다르다) → 그때만 스프라이트 판을 치우면 그 줄이 16개 안으로 들어온다.
⚠ 걷는 동안은 판을 다시 켜야 하므로(안 켜면 BG 판이 밀려 보인다) **걷는 중의 잘림은 그대로다.**

## 판정 재료 (엔진 — 뱅크 0x69 SAT 함수 `$6480`, 프레임마다 한 번 돈다)

- 스크롤 변수: 영 페이지 `$58/$59`(X) · `$5A/$5B`(Y). 멈춤 = 둘 다 `0x0008`. 걸음 한 번은 `0E → 0C → 0A → 08` 처럼 흐르고 **걸음과 걸음 사이에 멈춤 값이 한 프레임 낀다.**
- `$3411` = 이번에 SAT 를 몇 번째 칸부터 쓰는가(필드 0) · `$34` = 꼬리에서 `0x40 − 쓴 칸 수`.
- SATB = VRAM 단어 `$2214/$2215`(0x7F00). 칸 = y · x · 패턴 · 속성 네 단어. 이름판 첫 칸 = y 0x0060 · x 0x00F0 · 패턴 0x0380 · 속성 0x318D(서명 `TABLE`).
- 순서: [걸음 논리가 `$58/$5A` 를 바꾼다] → SAT 함수 → VBlank(SATB DMA) → 화면. 함수 꼬리 `$65BB` 의 `LDA #$13 · STA $F7 · ST0 #$13`(6B) 뒤가 DVSSR 쓰기다 — 그 6B 를 먼 호출로 바꾼다.

## 장치 (뱅크 0x70 FF 패딩 — 본체 117B + 표 8B + 셈 1B + 서명 검사 23B + 주소 세우기 21B)

1. 움직이는 중(`$58 ≠ 8` · `$5A ≠ 8` · 상위 ≠ 0) 이거나 `$3411 ≠ 0` 이거나 **버튼을 쥐고 있으면**(`$2228 ≠ 0`) → 셈 `CNT = 0xFF`, 아무것도 안 한다(엔진이 방금 쓴 판 그대로 = 같은 프레임에 판이 켜진다).
2. 멈춤이면 `LSR CNT` — 밀려 나온 비트가 1 이면 아직 안 숨긴다 ⇒ **연속 8프레임 멈춘 뒤(9번째 프레임)부터** 숨긴다(걸음 사이 한 프레임 멈춤에 판이 깜빡이지 않게 — 첫 판(v1)이 그랬다).
3. SAT 첫 칸이 서명과 같고, 이름판 밖 칸이 `NEED`(11) 이상이고(아래 「BG 판은 늘 믿을 수 있는 게 아니다」), 9번째 칸부터 끝까지 어느 스프라이트도 이름판 x 범위(오른쪽 끝 ≥ 0xE1, x 상위 ≠ 0 포함)에 안 걸칠 때만
   (걸친 게임 스프라이트가 있으면 판 스프라이트가 그 앞을 가려야 한다) 0~8 칸의 **y 단어만 0** 으로 쓴다(x·패턴·속성은 그대로 — 다음 프레임에 엔진이 어차피 전부 다시 쓴다).
4. 어느 길로든 끝은 원판 6B 와 같다: `$F7` = 0x13 · 레지스터 0x13 선택.

🔴 VDC 선택은 IRQ 가 `$F7` 값으로 되돌린다 — 본체는 `$F7` 을 안 바꾸고 선택 + 주소 쓰기를 `seta` 의 `SEI` 안에서 한다(부른 쪽이 `CLI`). 음성 자막 틱(IRQ)이 MAWR 을
옮기고 못 되돌리므로(devlog) 숨김은 단어 하나마다 주소를 다시 세운다. 읽기(MARR)는 틱이 안 건드린다.
⚠ `CLI` 는 원판이 이 자리를 인터럽트 허용 상태로 돈다는 전제다(실측으로 확인 — status).

## BG 판은 늘 믿을 수 있는 게 아니다 — 버튼 규칙과 `NEED` 가 생긴 까닭 (실측 11-21)

엔진이 판을 스프라이트로 한 벌 더 두는 건 스크롤 때문만이 아니다. **BG 판을 다시 쓰는 동안**(메뉴를 열 때 위에서부터 지우고 다시 쓴다)과
**래스터 효과가 BG 를 흔드는 동안**(전투 진입 디졸브)에도 스프라이트가 덮는다. 숨긴 채로 그 순간을 맞으면 빈 판·일그러진 판이 보인다.

- 버튼 규칙: 메뉴는 버튼으로만 열린다 ⇒ 버튼을 쥔 프레임부터 판을 켜 둔다. mednafen 실측(두 위상): 메뉴 여는 루틴(`$623E`)에 닿을 때 VRAM 의 SAT 는
  이미 켠 값이다(누른 걸 본 SAT 패스가 메뉴 판정보다 먼저 돈다) — 프레임 단위 화면 11장에 빈 판이 없다. ⚠ 헤드리스 코어(pcehl)에선 메뉴 여는 프레임에
  한 프레임 빈 판이 보이는 때가 있었다(세 번 중 두 번) — 코어의 타이밍 차이로 보고 mednafen 을 판정 근거로 삼았다(「왜 먼저 도는가」의 엔진 쪽 근거는 못 찾았다 — status).
- `NEED`: 전투는 쓴 칸이 11(디졸브 15)뿐이라 한 줄 16칸을 넘길 수 없다 — 칸 수로 걸러 전투·한산한 장면에선 손을 안 댄다(첫 시험판은 전투 디졸브에서 판이 일그러졌다).
  ⚠ 전투 「깃발」이 아니라 칸 수로 거른다 — 스프라이트가 20칸 넘게 붐비는 장면에서 버튼 없이 BG 판이 다시 쓰이는 자리(대사 시작·스크립트 전환)는 전부 보진 못했다.

실측(시험 롬 c1736920 · mednafen): 멈춘 뒤 9프레임째에 0~8 칸 y = 0 · 레지스탕스 장면 줄당 칸 수 최대 18 → 12(16 넘는 줄 8 → 0) ·
걷기 시작·멈춤 전환은 헤드리스 A/B 에서 네 귀퉁이 4픽셀 말고 원판과 픽셀까지 같다.
"""

import asm65
import sprmask

BANK = sprmask.CODE_BANK  # 0x70 — `$6000` 창(MPR3). 먼 호출 인자 = 뱅크 − 0x68
W = sprmask.CODE_WINDOW
# 뱅크 안 오프셋 — 넷 다 FF 패딩(이웃이 자라 넘어오면 `build.code_patches` 의 겹침 검사가 멈춘다)
MAIN_OFF = sprmask.RESTHIDE_OFF  # 디버그 목록 코드 끝(+190A) ~ 잘린 그림 사본 토막 a(+1980) 앞
MAIN_END = sprmask.SEGS[0][1]
TBL_OFF = 0x1BF6  # 토막 a 끝(+1BF6) ~ 조각 보관소(+1C00) 앞: 서명 8B + 셈 1B
TBL_END = sprmask.SEGS[0][2]
SIG_OFF = 0x1DE8  # 토막 b 끝(+1DE8) ~ 단계 숫자 루틴(+1E00) 앞
SIG_END = sprmask.SEGS[1][2]
SETA_OFF = 0x1EA7  # 단계 숫자 루틴 끝(+1EA7) ~ 토막 c(+1EC0) 앞
SETA_END = sprmask.SEGS[2][1]
TBL = W + TBL_OFF
CNT = TBL + 8
SIG = W + SIG_OFF
SETA_R = W + SETA_OFF  # 「MARR ← SATB」 들머리(LDA #1 · CLY 3B) — 바로 뒤가 `SETA`
SETA = SETA_R + 3
MAIN = W + MAIN_OFF

SITE_BANK = 0x69
SITE_OFF = 0x05BB  # 논리 `$65BB` — SAT 함수 꼬리
SITE_OLD = bytes.fromhex("a91385f70313")  # LDA #$13 · STA $F7 · ST0 #$13

SCROLL_X, SCROLL_Y, REST = 0x58, 0x5A, 0x08
SAT_FIRST = 0x3411
PAD = 0x2228  # BIOS joy(패드 1 누름 상태 — VBlank 마다 갱신)
SAT_LEFT = 0x34
SATB = 0x2214
NPANEL = 9  # 이름판 칸 수(SAT 0~8)
PANEL_X = 0xE1  # 스프라이트 오른쪽 끝이 이 값 이상이면 이름판에 걸친다(판 x = 0xF0, 오른쪽 막대 x = 0xE0 폭 16 은 안 걸친다)
SIG_WORDS = (0x0060, 0x00F0, 0x0380, 0x318D)  # 이름판 첫 칸 y · x · 패턴 · 속성
CNT_INIT = 0xFF
# 이름판 밖 칸(막대 6 + 게임 스프라이트)이 이 수보다 적으면 숨기지 않는다 — 한 줄 16칸을 넘길 수 없는 수다:
# 이름판 줄엔 판 3장(32폭 = 2칸씩 6칸) + 막대 2칸 = 8칸이 깔리고, 남은 8칸을 넘기려면 32폭 게임 스프라이트가 5장은 있어야 한다.
NEED = 6 + 5


def table() -> bytes:
    """서명 8B(검사가 X=7 부터 거꾸로 읽는다 — 속성 상위가 맨 앞) + 셈 초기값."""
    b = bytearray(8)
    for k, w in enumerate(SIG_WORDS):
        b[7 - 2 * k] = w & 0xFF
        b[6 - 2 * k] = w >> 8
    return bytes(b) + bytes([CNT_INIT])


def seta() -> bytes:
    """A = VDC 레지스터(0 MAWR · 1 MARR), Y = SATB 로부터 단어 오프셋 → 주소를 세우고 레지스터 2 를 고른 채, **I 를 세운 채** 돌아간다."""
    a = asm65.Asm(SETA_R)
    a.op("LDA", "imm", 1)
    a.raw(b"\xc2")  # CLY
    assert a.pc == SETA, hex(a.pc)
    a.op("SEI")
    a.op("STA", "abs", 0x0000)
    a.op("TYA")
    a.op("CLC")
    a.op("ADC", "abs", SATB)
    a.op("STA", "abs", 0x0002)
    a.op("LDA", "abs", SATB + 1)
    a.op("STA", "abs", 0x0003)
    a.op("ST0", "imm", 2)
    a.op("RTS")
    b = a.bytes()
    assert SETA_OFF + len(b) <= SETA_END, len(b)
    return b


def sig() -> bytes:
    """MARR 이 가리키는 칸의 8B 를 서명과 견준다 — 같으면 X = 0xFF · 올림 1 로 돌아간다."""
    a = asm65.Asm(SIG)
    a.op("LDX", "imm", 7)
    a.L("l")
    a.op("LDA", "abs", 0x0002)
    a.op("CMP", "absx", TBL)
    a.op("BNE", "rel", "r")
    a.op("DEX")
    a.op("LDA", "abs", 0x0003)
    a.op("CMP", "absx", TBL)
    a.op("BNE", "rel", "r")
    a.op("DEX")
    a.op("BPL", "rel", "l")
    a.L("r")
    a.op("RTS")
    b = a.bytes()
    assert SIG_OFF + len(b) <= SIG_END, len(b)
    return b


def main() -> bytes:
    a = asm65.Asm(MAIN)
    a.op("LDA", "zp", SCROLL_X)
    a.op("CMP", "imm", REST)
    a.op("BNE", "rel", "mv")
    a.op("EOR", "zp", SCROLL_Y)  # A = 8 ^ Y하위 — 0 이면 멈춤
    a.op("ORA", "zp", SCROLL_X + 1)
    a.op("ORA", "zp", SCROLL_Y + 1)
    a.op("ORA", "abs", SAT_FIRST)
    a.op(
        "ORA", "abs", PAD
    )  # 버튼을 쥐고 있으면 「움직이는 중」 — 메뉴를 여는 프레임에 엔진이 BG 판을 지우고 다시 쓴다
    a.op("BEQ", "rel", "rest")
    a.L("mv")
    a.op("LDA", "imm", CNT_INIT)
    a.op("STA", "abs", CNT)
    a.op("BRA", "rel", "done")
    a.L("rest")
    a.op("LSR", "abs", CNT)
    a.op("BCS", "rel", "done")  # 아직 8프레임을 안 채웠다
    a.op("JSR", "abs", SETA_R)  # MARR ← SATB
    a.op("CLI")
    a.op("JSR", "abs", SIG)
    a.op("INX")
    a.op("BNE", "rel", "done")  # 첫 칸이 이름판이 아니다
    a.op("LDX", "imm", (NPANEL - 1) * 4)  # 1~8 칸 건너뛰기(상위를 읽으면 MARR 이 는다)
    a.L("sk")
    a.op("LDA", "abs", 0x0003)
    a.op("DEX")
    a.op("BNE", "rel", "sk")
    a.op(
        "LDA", "imm", 0x40 - NPANEL - NEED
    )  # 올림 = 1(서명 마지막 CMP 가 같았다) → A = 쓴 칸 수 − 9 − NEED
    a.op("SBC", "zp", SAT_LEFT)
    a.op(
        "BCC", "rel", "done"
    )  # 넘칠 수 없는 칸 수 — 숨겨서 얻을 게 없다(전투·한산한 장면은 손을 안 댄다)
    a.op("ADC", "imm", NEED - 1)  # 올림 1 → X = 쓴 칸 수 − 9(훑을 칸 수)
    a.op("TAX")
    a.L("sc")
    a.op("LDA", "abs", 0x0003)  # y 건너뛰기
    a.op("LDY", "abs", 0x0002)  # x 하위
    a.op("LDA", "abs", 0x0003)  # x 상위
    a.op("AND", "imm", 3)
    a.op("BNE", "rel", "done")
    a.op("LDA", "abs", 0x0003)  # 패턴 건너뛰기
    a.op("LDA", "abs", 0x0003)  # 속성 상위 — 비트 0 = 폭 32
    a.op("LSR")
    a.op("TYA")
    a.op("BCC", "rel", "w16")
    a.op("ADC", "imm", 0x0F)  # 올림 1 → +16
    a.op("BCS", "rel", "done")
    a.L("w16")
    a.op("CMP", "imm", PANEL_X)
    a.op("BCS", "rel", "done")
    a.op("DEX")
    a.op("BNE", "rel", "sc")
    a.op("LDY", "imm", (NPANEL - 1) * 4)
    a.L("h")
    a.raw(b"\x62")  # CLA — MAWR ← SATB + Y
    a.op("JSR", "abs", SETA)
    a.op("ST1", "imm", 0)
    a.op("ST2", "imm", 0)
    a.op("CLI")
    for _ in range(4):
        a.op("DEY")
    a.op("BPL", "rel", "h")
    a.L("done")
    a.op("LDA", "imm", 0x13)
    a.op("STA", "zp", 0xF7)
    a.op("ST0", "imm", 0x13)
    a.op("RTS")
    b = a.bytes()
    assert MAIN_OFF + len(b) <= MAIN_END, len(b)
    return b


def site() -> bytes:
    """SAT 함수 꼬리 6B → 본체 먼 호출(`JSR $4FD8` + 인자 뱅크 + 주소). A·Y 는 트램펄린이 지킨다 — 원판 6B 뒤의 A = 0x13 은 본체 끝이 다시 싣는다."""
    return b"\x20\xd8\x4f" + bytes([BANK - 0x68]) + MAIN.to_bytes(2, "little")


def patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """(이름, 뱅크, 뱅크 안 오프셋, 기대 바이트, 새 바이트)."""
    out = [("site", SITE_BANK, SITE_OFF, SITE_OLD, site())]
    for nm, off, blob in (
        ("main", MAIN_OFF, main()),
        ("table", TBL_OFF, table()),
        ("sig", SIG_OFF, sig()),
        ("seta", SETA_OFF, seta()),
    ):
        out.append((nm, BANK, off, b"\xff" * len(blob), blob))
    return out
