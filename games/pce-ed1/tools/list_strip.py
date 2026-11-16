"""워프의 날개 목록 — 이름 앞 가운데 맞춤 공백 걷기(마스터 11-16 「목록 가운데 정렬」, 원판은 왼쪽 정렬).

날개 목록(뱅크 0x6C `$6401~`)은 항목마다 지명 표(뱅크 0x74 `$DC1E`, 12B)를 `$9505`(뱅크 0x6D — HUD 이름도 `$9294` 에서 부르는 **공용 복사 루틴**)로 `$C07D` 버퍼에 복사하고
`$5BB1` 로 그 문자열을 그린다. 우리는 HUD 칸 가운데 맞춤(11-05~11-08)을 위해 표 안에 **앞 반 칸 표시(`F8 24`) + 전각 공백(`81 40`)** 을 구워 넣었고, 목록이 그걸 그대로 그려 가운데처럼 보였다.
🔴 공용 복사 루틴(`$9505`)을 고치면 HUD 도 같이 바뀐다(첫 시도 — HUD 가 왼쪽으로 쏠리고 이름 뒤 글자가 붙었다). 그래서 **목록 쪽 호출 뒤**(`$6425`: 버퍼 포인터를 `$10/$11 = $C07D` 로 두는 두 쌍)만 바꾼다:
같은 포인터를 `$C07D` 로 두되 앞의 `F8 24` · `81 40` 쌍을 건너뛴 만큼 올린다. HUD 쪽은 한 바이트도 안 건드린다.

사이트(뱅크 0x6C 오프셋 0x0425): `A9 7D 85 10 A9 C0 85 11`(8B) → `JSR strip` + NOP×5 — strip 이 같은 두 쌍을 대신 한다.
"""

import hook
import hud_half

BANK = 0x6D  # 코드 자리(뱅크 0x6D 끝 FF 구역 — 날개 목록 코드가 이미 이 뱅크의 `$9505` 를 부르는 창)
ORG = hud_half.ORG + hud_half.CODE_LEN  # hud_half 코드 바로 뒤
OFF_ORG = ORG - 0x8000
CODE_LEN = 44  # code() 길이 이상 — freespace 가 이만큼 더 빼 둔다
SITE_BANK = 0x6C
SITE_OFF = 0x0425
SITE_OLD = bytes.fromhex("a97d8510a9c08511")


def code() -> bytes:
    a = hook.Asm(ORG)
    a.op("LDA", "imm", 0x7D)
    a.op("STA", "zp", 0x10)
    a.op("LDA", "imm", 0xC0)
    a.op("STA", "zp", 0x11)
    a.op("LDY", "imm", 0x00)
    a.op("LDA", "izpy", 0x10)
    a.op("CMP", "imm", 0xF8)
    a.op("BNE", "rel", "s1")
    a.op("INY", "imp")
    a.op("INY", "imp")
    a.label("s1")
    a.op("LDA", "izpy", 0x10)
    a.op("CMP", "imm", 0x81)
    a.op("BNE", "rel", "s2")
    a.op("INY", "imp")
    a.op("LDA", "izpy", 0x10)
    a.op("CMP", "imm", 0x40)
    a.op("BEQ", "rel", "s3")
    a.op("DEY", "imp")
    a.op("BRA", "rel", "s2")
    a.label("s3")
    a.op("INY", "imp")
    a.op("BRA", "rel", "s1")
    a.label("s2")
    a.op("TYA", "imp")
    a.op("CLC", "imp")
    a.op("ADC", "zp", 0x10)
    a.op("STA", "zp", 0x10)
    a.op("RTS", "imp")
    return a.bytes()


def site_new() -> bytes:
    return b"\x20" + ORG.to_bytes(2, "little") + b"\xea" * 5
