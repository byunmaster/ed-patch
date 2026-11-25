"""디버그 「I」(아이템 고르기) 화면의 아이템 이름 줄 — 왼쪽 정렬 + 줄 전체 다시 쓰기 (마스터 11-08).

원판 줄 그리기(뱅크 0x70 `$62F6`)는 이름 칸(14B, 7글자 폭)을 **오른쪽 끝에 맞춰** 앞을 공백(`20`)으로 채운 채 `$CFF1` 에 놓고,
앞 공백을 전각 공백(`81 40`)으로 바꾼 뒤 `$5BB1`(문자열 그리기)로 열 6/7(BAT `$0487`)에 그린다. 일본어 이름은 그래도 칸에 들었지만 한글 이름은
폭이 달라(변형 공백 포함 최대 86px) 긴 이름이 창 왼쪽 테두리 밖으로 나가거나(오른쪽 맞춤 + 열 6) 끝에 **글자 반쪽 잔재**가 남았다
(앞쪽만 공백으로 덮으니 이름이 칸을 못 채운 쪽 끝 타일은 이전 이름의 잔재가 안 지워진다).

고침: 같은 자리(`$6308`~`$632E`, 39B)를 `JMP ORG` 로 돌리고 뱅크 0x70 의 FF 패딩에 둔 새 꼬리가
  1. 앞 공백(`20`)의 개수 k 를 센다(이름 글자는 첫 바이트가 `20` 이 아니다 — 전부 2바이트 코드 · 칸 짝수)
  2. 이름을 버퍼 앞쪽으로 당기고 · 남은 칸을 전각 공백(`81 40`)으로 채워 **14B 전체를 다시 쓰며**(잔재 제거)
  3. 같은 BAT 주소(열 7 = 제목 「디버그」 글자 시작과 같은 선)에서 `$5BB1` 로 그린다.
`$CFFF` 의 종결자(`06`)는 건드리지 않는다(칸 끝을 안 넘는다).
"""

import hook

ORG = 0x73A8  # 뱅크 0x70 +0x13A8 — 띠 폴백(`band_fallback`, `$7320`+136B) 바로 뒤 FF 패딩(`$73A8~$7FFF`)
SITE_OFF = 0x0308  # 뱅크 0x70 안 — 원래 줄 그리기 꼬리 시작(`LDA #$F1`)
SITE_OLD = bytes.fromhex(
    "a9f18510a9cf8511c2b110c920d00ca9819110c8a9409110c880eea9878512a904851320b15b60"
)  # …`JSR $5BB1 / RTS` 까지 39B
BUF = 0xCFF1  # 이름 변환 결과(14B + `06`)
FIELD = 14
BAT_LO = 0x87  # BAT `$0487`(열 7) — 원판 값
BAT_HI = 0x04
DRAW = 0x5BB1  # 문자열 그리기(far call 래퍼) — `$10/$11` 원본 · `$12/$13` BAT 주소


def code() -> bytes:
    """이름을 왼쪽으로 당기고 **줄 폭이 이름 칸(11타일 = 88px)을 안 넘게** 전각 공백을 채운다.
    글자 하나 = 12px, 단어 사이 반 칸 변형(리드 F4~F7) = +4px. 폭이 88px 를 넘으면 12번째 타일이 BAT 의 창 오른쪽 테두리 칸을 덮고
    패턴까지 남는다(11-08 마스터 「오른쪽 테두리가 지워진다」 — 변형이 둘인 아이템 70번~ 에서 재현). 그래서 공백 칸 수 = ⌊(88 − 이름 폭) / 12⌋ 로 줄이고,
    그 뒤에 종결자(`06`)를 둔다. 임시 변수는 ZP `$10`(폭) · `$12`(공백 칸 수) — 그리기 직전에 원래대로 `$10~$13` 을 채운다."""
    return _emit(hook.Asm(ORG), draw=True)


def justify(org: int) -> bytes:
    """이름 왼쪽 정렬·공백 채움만 하는 서브루틴(끝 `RTS`, 그리지 않는다) — 디버그 「I」 목록창(`debug_item_list`)이 줄마다 부른다. 버퍼 `$CFF1`(14B + `06`) 제자리."""
    return _emit(hook.Asm(org), draw=False)


def _emit(a: "hook.Asm", draw: bool) -> bytes:
    for lab in ("lead", "lead2"):
        a.op("LDY", "imm", 0)
        a.label(lab)  # Y = 앞 공백(20) 바이트 수
        a.op("LDA", "absy", BUF)
        a.op("CMP", "imm", 0x20)
        a.op("BNE", "rel", lab + "_e")
        a.op("INY")
        a.op("BRA", "rel", lab)
        a.label(lab + "_e")
        if lab == "lead":
            a.op("LDA", "imm", 0)
            a.op("STA", "zp", 0x10)
            a.label("wl")  # 이름 폭 합산 — 글자마다 +12, 변형 리드(F4~F7)면 +4
            a.op("CPY", "imm", FIELD)
            a.op("BCS", "rel", "wd")
            a.op("LDA", "zp", 0x10)
            a.op("CLC")
            a.op("ADC", "imm", 12)
            a.op("STA", "zp", 0x10)
            a.op("LDA", "absy", BUF)
            a.op("CMP", "imm", 0xF4)
            a.op("BCC", "rel", "nv")
            a.op("CMP", "imm", 0xF8)
            a.op("BCS", "rel", "nv")
            a.op("LDA", "zp", 0x10)
            a.op("CLC")
            a.op("ADC", "imm", 4)
            a.op("STA", "zp", 0x10)
            a.label("nv")
            a.op("INY")
            a.op("INY")
            a.op("BRA", "rel", "wl")
            a.label("wd")  # X = 공백 칸 수 = 12px 를 더해 88px 안에 드는 횟수
            a.op("LDX", "imm", 0)
            a.label("fc")
            a.op("LDA", "zp", 0x10)
            a.op("CLC")
            a.op("ADC", "imm", 12)
            a.op("CMP", "imm", 89)
            a.op("BCS", "rel", "fd0")
            a.op("STA", "zp", 0x10)
            a.op("INX")
            a.op("BRA", "rel", "fc")
            a.label("fd0")
            a.op("STX", "zp", 0x12)
    a.op("LDX", "imm", 0)
    a.label("mv")  # 이름을 앞으로 당긴다
    a.op("CPY", "imm", FIELD)
    a.op("BCS", "rel", "fill")
    a.op("LDA", "absy", BUF)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.op("INY")
    a.op("BRA", "rel", "mv")
    a.label("fill")  # 공백 칸 수만큼 전각 공백 `81 40`
    a.op("LDA", "zp", 0x12)
    a.op("BEQ", "rel", "term")
    a.op("SEC")
    a.op("SBC", "imm", 1)
    a.op("STA", "zp", 0x12)
    a.op("LDA", "imm", 0x81)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.op("LDA", "imm", 0x40)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.op("BRA", "rel", "fill")
    a.label("term")
    # 🔴 줄 폭이 80px 로 끝나면(전각 공백 ⌊(88−폭)/12⌋ 칸을 채운 뒤) 그림은 10타일에서 멈추고 **11번째 타일은 안 다시 쓰여** 지난 줄 글자 조각이 남는다
    #   (마스터 11-16 「고대 무기의 책」 뒤 「혼」 — 폭 80 = 전각 6자 + 변형 둘). 폭이 81 미만이면 반 칸 공백(`F8 24`, 4px 전진)을 하나 더 붙여 84px(타일 11개)로
    #   끝나게 한다. 바이트 수: 폭 80 이 되는 이름은 최대 14B(전각 c + 변형 v=2 → 2(c+k)+2v+2 = 14)라 버퍼(14B + 종결자)에 든다.
    a.op("LDA", "zp", 0x10)
    a.op("CMP", "imm", 81)
    a.op("BCS", "rel", "term_e")
    a.op("LDA", "imm", 0xF8)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.op("LDA", "imm", 0x24)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.label("term_e")  # 종결자 — 그 뒤 칸은 그리지 않는다
    a.op("LDA", "imm", 0x06)
    a.op("STA", "absx", BUF)
    if not draw:
        a.op("RTS")
        return a.bytes()
    a.op("LDA", "imm", BUF & 0xFF)
    a.op("STA", "zp", 0x10)
    a.op("LDA", "imm", BUF >> 8)
    a.op("STA", "zp", 0x11)
    a.op("LDA", "imm", BAT_LO)
    a.op("STA", "zp", 0x12)
    a.op("LDA", "imm", BAT_HI)
    a.op("STA", "zp", 0x13)
    a.op("JSR", "abs", DRAW)
    a.op("RTS")
    return a.bytes()


def site_new() -> bytes:
    """원래 꼬리 39B 자리 — `JMP ORG` + NOP(도달하지 않는 나머지)."""
    return b"\x4c" + ORG.to_bytes(2, "little") + b"\xea" * (len(SITE_OLD) - 3)
