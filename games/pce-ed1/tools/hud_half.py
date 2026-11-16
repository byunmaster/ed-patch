"""HUD 지명 칸 4px 단위 가운데 — 이름 타일 **시작 열을 한 칸(8px) 뒤로** 미는 표시(마스터 11-08 「hud는 1번으로 해보자」 ≤3px 목표).

HUD 이름 렌더러(뱅크 0x6D `$92D8`)는 글자 둘을 3타일(24px)로 짝지어 닙블 이동·OR 로 합성해 BAT 의 시작 열(`$3ADB`=`$1B`)부터 타일을 깐다.
그래서 12px 셀 단위(앞 공백 한 칸 = 12px)로만 밀 수 있었다. 6px(반 칸) 짝 합성 시프트를 새로 짜는 길은 carry 를 둘 RAM·코드 자리(뱅크 0x6D 꼬리 224B 는 시스템 문구 조각이 이미
다 쓴다)가 없어 막혔고, 대신 **BAT 시작 열을 +1(8px)** 하는 길을 택했다 — 12k + 8h(h = 0/1)로 4px 단위가 되어 쏠림 ≤ 2px.

표시 — 지명 데이터 맨 앞 두 바이트가 `F8 24`(대사창 반 칸 공백 코드 — HUD 에선 안 쓴다)이면 「한 열 뒤로」. 렌더러는 그 두 바이트를 글자로 그리지 않고 건너뛴다:
`$92BE` `LDA #$1B; STA $3ADB`(5B) → `JSR NEW; NOP; NOP` — `NEW` 가 ($10) 첫 바이트를 보고 `F8` 이면 `$10` 포인터를 2 올리고 시작 열을 `$1C` 로 둔다.
"""

import hook

BANK = 0x6D
ORG = 0x9F20  # 뱅크 0x6D 끝 FF 224B 의 앞쪽(freespace.BANK6D_TAIL 에서 떼어 낸다)
OFF_ORG = ORG - 0x8000
CODE_LEN = 59  # code() 길이 이상 — freespace 가 이만큼 빼 둔다
MARK = b"\xf8\x24"
SITE_OFF = 0x12BE
SITE_OLD = bytes.fromhex("a91b8ddb3a")

hook.OPS.setdefault(("INC", "zp"), 0xE6)


def code() -> bytes:
    a = hook.Asm(ORG)
    a.op("LDA", "izp", 0x10)
    a.op("CMP", "imm", 0xF8)
    a.op("BNE", "rel", "no")
    a.op("INC", "zp", 0x10)
    a.op("INC", "zp", 0x10)
    a.op("JSR", "abs", "clr")  # 앞 이름이 $1B 열에 남긴 BAT 항목을 비운다(아래)
    a.op("LDA", "imm", 0x1C)
    a.op("BRA", "rel", "st")
    a.label("no")
    a.op("LDA", "imm", 0x1B)
    a.label("st")
    a.op("STA", "abs", 0x3ADB)
    a.op("RTS")
    # 🔴 시작 열을 $1C 로 밀면 $1B 열은 안 쓴다 — 앞 이름(시작 열 $1B)이 남긴 BAT 항목(첫 타일 번호)이 그대로라
    # **새 이름의 첫 타일을 한 번 더 그린다**(걸어 들어간 화면 「ㄴ네리아항구」, 11-08). BAT 행 24·25 의 $1B 열(VRAM $061B·$065B)을 패널 빈 칸($0145)으로 쓴다.
    a.label("clr")
    a.op("LDA", "imm", 0x1B)
    a.op("JSR", "abs", "w")
    a.op("LDA", "imm", 0x5B)  # 둘째 줄(+$40) — w 로 이어져 RTS
    a.label("w")
    a.op("STZ", "zp", 0xF7)
    a.op("ST0", "imm", 0x00)
    a.op("STA", "abs", 0x0002)
    a.op("LDY", "imm", 0x06)  # Y 는 이 뒤 렌더러(`$92EA` CLY)가 다시 0 으로 둔다 — 보존 불필요
    a.op("STY", "abs", 0x0003)
    a.op("LDY", "imm", 0x02)
    a.op("STY", "zp", 0xF7)
    a.op("ST0", "imm", 0x02)
    a.op("LDY", "imm", 0x45)  # 패널 안 빈 칸 타일 $0145(이름 뒤 칸이 쓰는 것 — 실측 BAT 행 24·25 열 36)
    a.op("STY", "abs", 0x0002)
    a.op("LDY", "imm", 0x01)
    a.op("STY", "abs", 0x0003)
    a.op("RTS")
    return a.bytes()


def site_new() -> bytes:
    return b"\x20" + ORG.to_bytes(2, "little") + b"\xea\xea"
