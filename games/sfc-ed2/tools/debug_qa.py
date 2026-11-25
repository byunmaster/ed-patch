"""sfc-ed2 QA 디버그 — 마스터 11-18 「내 qa용으로 사용해보고 괜찮으면 아예 기능으로 추가」. 제품 롬은 바이트 불변이다:
`ED_DEBUG_QA=1`(꼬리표 `ED_BUILD_TAG=qa-debug`)로 구울 때만 들어간다. 원판 디버그(`debug_patch.py` 입구 — L+R+Select 1초로 켠다) 위에 편의 기능을 얹는다.

조작(필드 주메뉴 B 를 연 채 — 열쇠·Select·Start 안 씀. 원판 필드는 Start=게임 세이브 창·Select=게임 로드 창이라 못 쓴다 11-22):
    L + Y 소지금 +100000 · B 경험치 최대(전투 승리 때 레벨이 99 쪽으로 이어서 오른다) · A 조우 끄기/켜기 · X 워프 해방 · ← 이동 속도 빠르게/원래대로 · → 벽 뚫기 켜기/끄기(맵 가장자리는 못 넘는다)
    R + ←/→ 아이템 번호 −1/+1 · Y −10 · X +10 · B 최강 장비 번호(16→25→33 순환) · A 그 번호 지급(원판 지급 루틴)
    ⚠ ↑↓ 는 쓰지 않는다 — 필드 주메뉴가 커서를 옮기며 입력 루프를 먼저 가져간다(실측 11-18).

구조: 입구 훅(`$C1:E306`)을 `QA_ENTRY` 로 돌려, 칸 조합이 맞으면 동작 번호와 원판 명령 대기(`$137A`=0x80 · `$0131` 비트7)를 세운 뒤 제품 스텁을 그대로 부른다.
버튼을 떼면 원판 루프가 명령 해석(`$C1:E43F`)으로 가고, 필드에서 모르는 선택(0)이 닿는 자리(`$C1:E57D` — 원래 거부음)를 `QA_FIELD` 로 돌려 동작을 한다.
메시지는 원판 창(`jsl $C0:A6E8`, 포인터 `$00A6~A8`)을 그대로 쓴다 — 닫으면 원판이 `$C1:EAF7` 로 메뉴를 되돌린다.
RAM(세이브 밖 WRAM `$7F:F800~`, 지도를 갈아타도 유지): `+0` 열쇠 표지 거울 · `+1` 조우 끄기(=A5) · `+2` 동작 번호 · `+3` 벽 뚫기(=A5) · `+4` 이동 속도(=A5) · `+5` 아이템 번호.
"""

import os

import debug_patch as dp

ENABLED = os.environ.get("ED_DEBUG_QA") == "1"

# QA 표지는 지도를 갈아타도 살아남게 WRAM 윗부분(`$7F:F800~`, 세이브 범위 밖)에 둔다 — 세계 지도·마을 지도 등 장면 덤프 5곳에서 늘 0 이던 칸(실측 11-19).
# 낮은 칸 `$0B59~$0B5F` 는 세계 지도가 덮어써서 표지가 지워졌다. 원판 열쇠 표지 `$0B5B` 는 제품 스텁 몫이라 못 옮기고, 입구 훅이 이 거울(UNL)에서 되살린다.
HI = 0x7FF800
UNL, ENC, ACT, WALL, FAST, ITEM = HI, HI + 1, HI + 2, HI + 3, HI + 4, HI + 5
MAGIC = 0xA5
BCC = 0x90

HOOK_FIELD = 0xC1E57D  # `lda #$06 / jsl $C0:07A1`(거부음) — 필드에서 모르는 선택일 때
HOOK_FIELD_OLD = bytes.fromhex("A906" "22A107C0")
ENC_HOOK = 0xC19CE4  # `lda $11BF / and #$02 / beq` — 몬스터 접촉 전투 판정
ENC_HOOK_OLD = bytes.fromhex("ADBF1129" "02F004")

SPD_HOOK = 0xC042AB  # `bne +2 / ora #$01 / sta $1A9E` — 이동 속도(기타·시스템 창의 「이동」: `$0131` 비트4~5 → 1·2·4·6 칸/프레임)를 정하는 곳
SPD_HOOK_OLD = bytes.fromhex("D002" "0901" "8D9E1A")
FAST_PX = 8
WALL_HOOK = 0xC04A57  # `stz $1A31 / tsb $1A31` — 이동 방향 판정(`$C0:4A3C`)이 만든 「갈 수 있는 방향」(A)을 `$1A31` 에 넣는 곳
WALL_HOOK_OLD = bytes.fromhex("9C311A" "0C311A")

TEXTS = {
    "fast_on": "<1f>이동 속도 빠르게\n원래 시스템 창 설정보다 빠르다",
    "fast_off": "<1f>이동 속도 원래대로\n시스템 창 설정을 따른다",
    "money": "<1f>소지금 100000 골드를 얻었다",
    "exp": "<1f>경험치 최대\n전투에서 승리하면 레벨이 계속 오른다\n끝날 때까지 A 로 넘긴다",
    "warp": "<1f>워프 해방\n워프의 날개로 전 지역에 갈 수 있다",
    "enc_off": "<1f>조우 끄기\n몬스터와 닿아도 전투가 없다",
    "enc_on": "<1f>조우 켜기\n원래대로 전투한다",
    "wall_on": "<1f>벽 뚫기\n벽과 지형을 지나간다\n맵 가장자리는 못 넘는다",
    "wall_off": "<1f>벽 뚫기 끄기\n원래대로 막힌다",
}

A_MONEY, A_EXP, A_ENC, A_ITEM, A_WARP, A_WALL, A_FAST = 1, 2, 3, 4, 5, 6, 7
A_IM1, A_IP1, A_IP10, A_IM10, A_GEAR = 8, 9, 10, 11, 12  # 아이템 번호 −1 · +1 · +10 · −10 (A_ITEM = 지급)
GEAR_SEQ = (16, 25, 33)  # 태양의 성검 · 드래곤의 갑옷 · 드래곤의 방패
ITEM_MAX = 99  # 아이템 이름 표 `$C1772D` 의 칸 수


def item_text(i: int) -> str:
    return f"<1f>아이템 번호 {i:02d}\n지급은 R 을 누른 채 A"


def lda_i(a, v):
    a.raw(0xA9, v)


def sta(a, x):
    a.raw(0x8D, x & 255, x >> 8)


def lda(a, x):
    a.raw(0xAD, x & 255, x >> 8)


def lda_l(a, x):
    a.raw(0xAF, x & 255, (x >> 8) & 255, x >> 16)


def sta_l(a, x):
    a.raw(0x8F, x & 255, (x >> 8) & 255, x >> 16)


def stz_l(a, x):
    a.raw(0xA9, 0x00)  # lda #0 (A 가 망가진다 — 호출 자리는 A 를 더 안 쓴다)
    sta_l(a, x)


def msg(a, ptr):
    for i, b in enumerate((ptr & 255, (ptr >> 8) & 255, ptr >> 16)):
        lda_i(a, b)
        sta(a, 0xA6 + i)
    a.raw(0x22, 0xE8, 0xA6, 0xC0)  # jsl $C0:A6E8


def se(a, n):
    lda_i(a, n)
    a.raw(0x22, 0xA1, 0x07, 0xC0)  # jsl $C0:07A1


def entry_stub() -> bytes:
    """훅 `$C1:E306` — 칸 조합이면 동작 번호를 세우고, 어느 쪽이든 제품 스텁을 부른다(스텁이 원래 두 명령까지 실행하고 RTL)."""
    a = dp.Asm()
    a.raw(0x08, 0xE2, 0x20)  # php / sep #$20
    lda_l(a, UNL)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BNE, "nomir")
    lda_i(a, MAGIC)
    sta(a, dp.UNLOCK)  # 지도를 갈아타 지워진 열쇠 표지를 거울에서 되살린다
    a.label("nomir")
    a.raw(0x28)  # plp
    lda(a, 0x137A)
    a.far(dp.BNE, "chain")  # 이미 명령 대기 중
    lda(a, 0x1B95)
    a.far(dp.BEQ, "chain")  # 필드 주메뉴에서만
    lda(a, 0x1B06)
    a.raw(dp.AND, 0x30)
    a.raw(dp.CMP, 0x20)
    a.br(dp.BEQ, "lchord")  # L 만(R 없음) = 본 조합
    a.raw(dp.CMP, 0x10)
    a.far(dp.BNE, "chain")  # R 만 = 아이템 번호 조합, 둘 다 아니면 원판대로
    for src_, mask, act in (
        (0x1B07, 0x02, A_IM1),  # ←
        (0x1B07, 0x01, A_IP1),  # →
        (0x1B06, 0x40, A_IP10),  # X
        (0x1B07, 0x40, A_IM10),  # Y
        (0x1B06, 0x80, A_ITEM),  # A 지급
        (0x1B07, 0x80, A_GEAR),  # B 최강 장비 번호(태양의 성검 → 드래곤의 갑옷 → 드래곤의 방패)
    ):
        nxt = f"r{act}"
        lda(a, src_)
        a.raw(dp.AND, mask)
        a.br(dp.BEQ, nxt)
        a.brl(f"go{act}")
        a.label(nxt)
    a.brl("chain")
    a.label("lchord")
    for src_, mask, act in (
        (0x1B07, 0x40, A_MONEY),  # Y
        (0x1B07, 0x80, A_EXP),  # B
        (0x1B06, 0x80, A_ENC),  # A
        (0x1B06, 0x40, A_WARP),  # X
        (0x1B07, 0x01, A_WALL),  # →
        (0x1B07, 0x02, A_FAST),  # ←
    ):
        nxt = f"n{act}"
        lda(a, src_)
        a.raw(dp.AND, mask)
        a.br(dp.BEQ, nxt)
        a.brl(f"go{act}")
        a.label(nxt)
    a.brl("chain")
    for act in (A_MONEY, A_EXP, A_ENC, A_WARP, A_WALL, A_FAST, A_IM1, A_IP1, A_IP10, A_IM10, A_ITEM, A_GEAR):
        a.label(f"go{act}")
        lda_i(a, act)
        sta_l(a, ACT)
        lda_i(a, 0x80)
        sta(a, 0x137A)
        lda(a, 0x0131)
        a.raw(dp.ORA, 0x80)
        sta(a, 0x0131)
        a.brl("chain")
    a.label("chain")
    a.raw(0x22, dp.CMD_STUB & 255, (dp.CMD_STUB >> 8) & 255, dp.CMD_STUB >> 16)  # jsl 제품 스텁
    # 제품 스텁이 열쇠 표지를 바꿨을 수 있다(1초 열쇠로 켬·끔) — 거울에 베낀다. 플래그·A 는 그대로 돌려준다.
    a.raw(0x08, 0x48, 0xE2, 0x20)  # php / pha / sep #$20
    lda(a, dp.UNLOCK)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BEQ, "mset")
    lda_i(a, 0)
    a.label("mset")
    sta_l(a, UNL)
    a.raw(0x68, 0x28)  # pla / plp
    a.raw(0x6B)  # rtl (제품 스텁이 맞춘 플래그를 그대로 돌려준다)
    return a.done()


def enc_stub() -> bytes:
    """`$C1:9CE4` 를 대신한다(`jml`) — 켜져 있으면 접촉 비트를 지우고 「전투 없음」(A=0)으로 끝낸다. 나머지는 원문과 같다."""
    a = dp.Asm()
    lda_l(a, ENC)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BNE, "norm")
    a.raw(dp.STZ, 0xBF, 0x11)  # stz $11BF
    lda_i(a, 0)
    a.raw(0x28, 0x6B)  # plp / rtl
    a.label("norm")
    lda(a, 0x11BF)
    a.raw(dp.AND, 0x02)
    a.br(dp.BEQ, "out")
    a.raw(0x4A)  # lsr a
    a.raw(dp.STZ, 0xBF, 0x11)
    a.label("out")
    a.raw(0x28, 0x6B)
    return a.done()


def speed_stub() -> bytes:
    """`$C0:42AB` 를 대신한다(`jsl`) — 원래 값(시스템 창 설정)을 만든 뒤, 켜져 있으면 FAST_PX 로 올린다. A 는 `$0131` 비트4~5 를 >>3 한 값."""
    a = dp.Asm()
    a.br(dp.BNE, "nz")
    a.raw(dp.ORA, 0x01)
    a.label("nz")
    a.raw(0x48)  # pha
    lda_l(a, FAST)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BNE, "orig")
    a.raw(0x68)  # pla
    lda_i(a, FAST_PX)
    a.br(dp.BRA, "st")
    a.label("orig")
    a.raw(0x68)
    a.label("st")
    sta(a, 0x1A9E)
    a.raw(0x6B)
    return a.done()


def wall_stub() -> bytes:
    """`$C0:4A57` 를 대신한다(`jsl`) — 방향 판정 결과 A(갈 수 있는 방향, `$0133` 과 같은 비트: ↑8 ↓4 ←2 →1)를 `$1A31` 에 넣는다.
    켜져 있으면(필드 `$0100`≠0) A 대신 눌린 방향(`$0133`&0F)을 넣되, 맵 가장자리로 향하는 비트는 뺀다(`$C0:4691` 과 같은 가장자리 식 — 밖으로 나가면 화면이 깨진다)."""
    a = dp.Asm()
    a.raw(0x48)  # pha (원래 A)
    lda_l(a, WALL)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BNE, "orig")
    lda(a, 0x0100)
    a.br(dp.BEQ, "orig")
    lda(a, 0x0133)
    a.raw(dp.AND, 0x0F, 0x48)  # and #$0F / pha (눌린 방향)
    a.raw(0xC2, 0x20)  # rep #$20
    a.raw(0xB9, 0x8C, 0x03)  # lda $038C,y (x)
    a.br(dp.BNE, "nl")
    a.raw(0xE2, 0x20, 0xA3, 0x01, 0x29, 0xFD, 0x83, 0x01, 0xC2, 0x20)  # sep / lda 1,s / and #$FD / sta 1,s / rep
    a.label("nl")
    a.raw(0xAD, 0x08, 0x1A, 0x29, 0xFF, 0x00, 0x0A, 0x3A, 0x3A)  # lda $1A08 / and #$FF / asl / dec / dec
    a.raw(0xD9, 0x8C, 0x03)  # cmp $038C,y
    a.br(dp.BNE, "nr")
    a.raw(0xE2, 0x20, 0xA3, 0x01, 0x29, 0xFE, 0x83, 0x01, 0xC2, 0x20)  # 오른쪽 가장자리 → →(01) 뺌
    a.label("nr")
    a.raw(0xB9, 0x8E, 0x03)  # lda $038E,y (y)
    a.br(dp.BNE, "nu")
    a.raw(0xE2, 0x20, 0xA3, 0x01, 0x29, 0xF7, 0x83, 0x01, 0xC2, 0x20)  # 위 가장자리 → ↑(08) 뺌
    a.label("nu")
    a.raw(0xAD, 0x09, 0x1A, 0x29, 0xFF, 0x00, 0x0A, 0x3A, 0x3A)
    a.raw(0xD9, 0x8E, 0x03)  # cmp $038E,y
    a.br(dp.BNE, "nd")
    a.raw(0xE2, 0x20, 0xA3, 0x01, 0x29, 0xFB, 0x83, 0x01, 0xC2, 0x20)  # 아래 가장자리 → ↓(04) 뺌
    a.label("nd")
    a.raw(0xE2, 0x20)  # sep #$20
    a.raw(0x68)  # pla (방향)
    a.raw(0x83, 0x01)  # sta 1,s (원래 A 자리에 덮는다)
    a.label("orig")
    a.raw(0x68)  # pla
    a.raw(dp.STZ, 0x31, 0x1A)  # stz $1A31
    a.raw(0x0C, 0x31, 0x1A)  # tsb $1A31
    a.raw(0x6B)
    return a.done()


def field_stub(p: dict) -> bytes:
    """`$C1:E57D` 를 대신한다(`jsl`) — 동작 번호대로 한다. 끝나면 원판이 `jmp $EAF7` 로 메뉴를 되돌린다."""
    a = dp.Asm()
    a.raw(0x08, 0xE2, 0x30)  # php / sep #$30
    lda_l(a, ACT)
    a.raw(0x48)  # pha (동작 번호 — 지우는 동안 지킨다)
    stz_l(a, ACT)
    a.raw(0x68)  # pla
    # 소지금
    a.raw(dp.CMP, A_MONEY)
    a.far(dp.BNE, "m2")
    for ad, v in ((0x11F6, 0xA0), (0x11F7, 0x86), (0x11F8, 0x01)):  # +100000 = 0x0186A0
        lda_i(a, v)
        sta(a, ad)
    a.raw(0x22, 0x0A, 0x22, 0xC1)  # jsl $C1:220A (소지금 += $11F6~F8)
    se(a, 3)
    msg(a, p["money"])
    a.brl("out")
    a.label("m2")
    # 경험치 +5000(파티 4칸 — 살아 있는 칸만. 세 바이트 `$0517+0x40n`, 상한 넘으면 0xFFFFFF)
    a.raw(dp.CMP, A_EXP)
    a.far(dp.BNE, "m2b")
    a.raw(0xA2, 0x00)  # ldx #$00 (8비트)
    a.label("xl")
    a.raw(0xBD, 0x0B, 0x05)  # lda $050B,x
    a.raw(dp.AND, 0x80)
    a.br(dp.BNE, "xn")  # 비트7 = 없는 칸
    lda_i(a, 0xFF)  # 경험치 = 0xFFFFFF (x 는 8비트라 0xC0 까지 — 0x517+0xC0 이 한계)
    a.raw(0x9D, 0x17, 0x05)
    a.raw(0x9D, 0x18, 0x05)
    a.raw(0x9D, 0x19, 0x05)
    a.label("xn")
    a.raw(0x8A, 0x18, 0x69, 0x40, 0xAA)  # txa / clc / adc #$40 / tax
    a.raw(0xE0, 0x00)  # cpx #$00 — 4칸(0x00·0x40·0x80·0xC0) 뒤 0 으로 돌아온다
    a.br(dp.BNE, "xl")
    se(a, 3)
    msg(a, p["exp"])
    a.brl("out")
    a.label("m2b")
    # 조우 끄기 토글
    a.raw(dp.CMP, A_ENC)
    a.far(dp.BNE, "m3")
    lda_l(a, ENC)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BEQ, "encoff")
    lda_i(a, MAGIC)
    sta_l(a, ENC)
    se(a, 3)
    msg(a, p["enc_off"])
    a.brl("out")
    a.label("encoff")
    stz_l(a, ENC)
    se(a, 3)
    msg(a, p["enc_on"])
    a.brl("out")
    a.label("m3")
    # 아이템 번호 조절 · 지급(원판 지급 루틴 `$C1:E9FC` — 가득이면 버릴 것 묻기까지 원판이 한다)
    a.raw(dp.CMP, A_IM1)
    a.far(dp.BCS, "ic")  # A_IM1 이상이면 아이템 번호 동작(8~11) — 아래서 가른다
    a.brl("m4")
    a.label("ic")
    a.raw(dp.CMP, A_IM10 + 1)
    a.far(BCC, "isel")
    a.brl("m4")
    a.label("isel")
    a.raw(0xA8)  # tay (Y = 동작 번호)
    lda_l(a, ITEM)
    a.br(dp.BNE, "i0")
    lda_i(a, 1)
    a.label("i0")
    a.raw(0xAA)  # tax (번호)
    a.raw(0x98)  # tya
    a.raw(dp.CMP, A_IM1)
    a.br(dp.BNE, "i1")
    a.raw(0x8A, 0x38, 0xE9, 0x01, 0xAA)  # txa / sec / sbc #1 / tax
    a.br(dp.BRA, "iw")
    a.label("i1")
    a.raw(dp.CMP, A_IP1)
    a.br(dp.BNE, "i2")
    a.raw(0xE8)  # inx
    a.br(dp.BRA, "iw")
    a.label("i2")
    a.raw(dp.CMP, A_IP10)
    a.br(dp.BNE, "i3")
    a.raw(0x8A, 0x18, 0x69, 0x0A, 0xAA)  # +10
    a.br(dp.BRA, "iw")
    a.label("i3")
    a.raw(0x8A, 0x38, 0xE9, 0x0A, 0xAA)  # −10
    a.label("iw")
    a.raw(0x8A)  # txa
    a.raw(dp.CMP, 0xF0)
    a.br(BCC, "ihi")  # 0xF0 미만이면 아래 비교로
    lda_i(a, ITEM_MAX)  # 음수로 넘쳤다 → 끝으로
    a.br(dp.BRA, "ist")
    a.label("ihi")
    a.raw(dp.CMP, ITEM_MAX + 1)
    a.br(BCC, "ilo")
    lda_i(a, 1)  # 끝 넘김 → 1
    a.br(dp.BRA, "ist")
    a.label("ilo")
    a.raw(dp.CMP, 1)
    a.br(dp.BCS, "ist")
    lda_i(a, ITEM_MAX)  # 0 → 끝으로
    a.label("ist")
    sta_l(a, ITEM)
    se(a, 3)
    lda_l(a, ITEM)  # 효과음 루틴이 A 를 망가뜨린다
    a.raw(0xC2, 0x30)  # rep #$30
    a.raw(0x29, 0xFF, 0x00)  # and #$00FF
    a.raw(0x0A, 0xAA)  # asl / tax
    a.raw(0xBF, p["itab"] & 255, (p["itab"] >> 8) & 255, p["itab"] >> 16)  # lda long,x
    a.raw(0x8D, 0xA6, 0x00)  # sta $00A6 (16비트)
    a.raw(0xE2, 0x30)  # sep #$30
    lda_i(a, p["itab"] >> 16)
    sta(a, 0xA8)
    a.raw(0x22, 0xE8, 0xA6, 0xC0)  # jsl $C0:A6E8
    a.brl("out")
    a.label("m4")
    a.raw(dp.CMP, A_ITEM)
    a.far(dp.BNE, "m5")
    a.raw(0x28)  # plp (맨 앞 php)
    a.raw(0xE2, 0x30)
    a.raw(0x68, 0x68, 0x68)  # 훅 JSL 의 되돌아갈 주소 3바이트를 버린다(원판 루틴이 `jmp $EAF7` 로 끝난다)
    lda_l(a, ITEM)
    a.br(dp.BNE, "g0")
    lda_i(a, 1)
    a.label("g0")
    a.raw(0x5C, 0xFC, 0xE9, 0xC1)  # jml $C1:E9FC
    a.label("m5")
    a.raw(dp.CMP, A_WARP)
    a.far(dp.BNE, "m6")
    # 워프 해방 — 원판 매직 코드의 등록 루프(`$C1:E4AB~E4C7`)와 같다: 플래그 `$0441~$0471` 49개를 켠다(워프의 날개 목록이 전 지역)
    a.raw(0xC2, 0x10)  # rep #$10
    a.raw(0xA2, 0x41, 0x04)  # ldx #$0441
    a.label("wl")
    a.raw(0x8E, 0xB0, 0x11)  # stx $11B0
    a.raw(0xDA)  # phx
    a.raw(0x22, 0xD6, 0x8B, 0xC1)  # jsl $C1:8BD6
    a.raw(0xAE, 0xB2, 0x11)  # ldx $11B2
    lda(a, 0x11B4)
    a.raw(0x1D, 0x67, 0x01)  # ora $0167,x
    a.raw(0x9D, 0x67, 0x01)  # sta $0167,x
    a.raw(0xFA, 0xE8)  # plx / inx
    a.raw(0xE0, 0x72, 0x04)  # cpx #$0472
    a.br(dp.BNE, "wl")
    a.raw(0xE2, 0x30)  # sep #$30
    se(a, 3)
    msg(a, p["warp"])
    a.brl("out")
    a.label("m6")
    a.raw(dp.CMP, A_FAST)
    a.far(dp.BNE, "m7")
    lda_l(a, FAST)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BEQ, "fastoff")
    lda_i(a, MAGIC)
    sta_l(a, FAST)
    lda_i(a, FAST_PX)
    sta(a, 0x1A9E)  # 속도 변수는 설정이 바뀔 때만 다시 계산되니 지금 바로 쓴다
    se(a, 3)
    msg(a, p["fast_on"])
    a.brl("out")
    a.label("fastoff")
    stz_l(a, FAST)
    lda(a, 0x0131)
    a.raw(dp.AND, 0x30, 0x4A, 0x4A, 0x4A)  # and #$30 / lsr×3 — 원래 설정값(`$C0:42A1` 과 같다)
    a.br(dp.BNE, "fz")
    a.raw(dp.ORA, 0x01)
    a.label("fz")
    sta(a, 0x1A9E)
    se(a, 3)
    msg(a, p["fast_off"])
    a.brl("out")
    a.label("m7")
    a.raw(dp.CMP, A_WALL)
    a.far(dp.BNE, "m8")
    lda_l(a, WALL)
    a.raw(dp.CMP, MAGIC)
    a.br(dp.BEQ, "walloff")
    lda_i(a, MAGIC)
    sta_l(a, WALL)
    se(a, 3)
    msg(a, p["wall_on"])
    a.brl("out")
    a.label("walloff")
    stz_l(a, WALL)
    se(a, 3)
    msg(a, p["wall_off"])
    a.brl("out")
    a.label("m8")
    a.raw(dp.CMP, A_GEAR)
    a.far(dp.BNE, "rej")
    lda_l(a, ITEM)
    a.raw(dp.CMP, GEAR_SEQ[0])
    a.br(dp.BEQ, "g1")
    a.raw(dp.CMP, GEAR_SEQ[1])
    a.br(dp.BEQ, "g2")
    lda_i(a, GEAR_SEQ[0])
    a.br(dp.BRA, "gs")
    a.label("g1")
    lda_i(a, GEAR_SEQ[1])
    a.br(dp.BRA, "gs")
    a.label("g2")
    lda_i(a, GEAR_SEQ[2])
    a.label("gs")
    a.brl("ist")
    a.label("rej")
    se(a, 6)  # 모르는 동작 — 거부음
    a.label("out")
    a.raw(0x28, 0x6B)  # plp / rtl
    return a.done()


def build(rom, src, writes, far, enc):
    """`far` = Space, `enc(text) -> bytes`. 제품 패치가 쓴 입구 훅을 QA 입구로 바꾸고 나머지 자리를 단언하며 고친다."""
    import common

    def off(ad):
        return common.snes2off(ad)

    p = {}
    for k, t in TEXTS.items():
        p[k] = far.put(enc(t) + b"\x00")
    # 아이템 번호 문구 표 — 한 뱅크 안(16비트 포인터)에 몰아 둔다. 0번 칸은 1번 문구로 채운다.
    ptrs = []
    base_bank = None
    for i in range(0, ITEM_MAX + 1):
        ad = far.put(enc(item_text(max(i, 1))) + b"\x00")
        base_bank = base_bank if base_bank is not None else ad >> 16
        assert ad >> 16 == base_bank, "아이템 문구가 뱅크 경계를 넘었다"
        ptrs.append(ad & 0xFFFF)
    tab = bytearray()
    for q in ptrs:
        tab += q.to_bytes(2, "little")
    p["itab"] = far.put(bytes(tab))
    assert p["itab"] >> 16 == base_bank, "아이템 포인터 표가 뱅크 경계를 넘었다"
    e = far.put(entry_stub())
    f = far.put(field_stub(p))
    z = far.put(enc_stub())
    sp = far.put(speed_stub())
    wl = far.put(wall_stub())

    def poke(ad, old, new):
        o = off(ad)
        assert bytes(rom[o : o + len(old)]) == old, f"QA 자리 {ad:06X} 가 예상과 다르다: {bytes(rom[o:o+len(old)]).hex()}"
        rom[o : o + len(new)] = new
        writes.append((o, o + len(new)))

    poke(dp.HOOK, dp.jsl(dp.CMD_STUB) + b"\xea\xea", dp.jsl(e) + b"\xea\xea")
    poke(HOOK_FIELD, HOOK_FIELD_OLD, dp.jsl(f) + b"\xea\xea")
    poke(ENC_HOOK, ENC_HOOK_OLD, bytes([0x5C, z & 255, (z >> 8) & 255, z >> 16]) + b"\xea\xea\xea")
    poke(WALL_HOOK, WALL_HOOK_OLD, dp.jsl(wl) + b"\xea\xea")
    poke(SPD_HOOK, SPD_HOOK_OLD, dp.jsl(sp) + b"\xea\xea\xea")
