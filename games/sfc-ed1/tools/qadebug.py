"""QA 전용 디버그 기능(마스터 11-18 야간 지시) — **`ED_DEBUG_QA=1` 빌드에만** 들어간다(꼬리표 `qa-debug`, 제품 롬 바이트 불변).

원판 디버그(메뉴 A·B)를 살린 위에 QA 편의 기능을 더한다. 진입은 기존 키 그대로 — **주메뉴(커서 창)를 연 채 L+R+Select 1초**
(+X 메뉴 A · +없음 메뉴 B) 에 **+Y 를 더하면 QA 메뉴(C)**. 창 안에서 열리고 **B 로 나가면 게임으로 돌아온다**(리셋 불필요).

화면은 원판 방식 그대로다 — 필드 HUD 의 지명 창에 항목 이름이 뜬다(메뉴 B 가 쓰는 `$02:9F97` + 지명 표, 이름은 `places.QA_NAMES`).
위/아래 = 항목 · A = 값 바꾸기/실행 · B = 나가기. 상태는 WRAM `$1F50~`(원판이 안 쓰는 칸 — 쓰기 감시 확인) 에 있고 전원을 끄면 사라진다.

기능(순서대로 더한다 — README `inbox/sfc-ed1/qa-debug/README.md`):
 2. 소지금 +100,000(Start 키 — 상한 9,999,999, `$11FE`).
 1. 경험치 배율(1·10·100배) — 승리 보상 EP(`$094E`)를 메시지 출력 직전(`$01:B3B8`)에 곱한다(저장되는 EP 가 곱해진다 — 세이브 위험).
"""

import common

BANK = 0x3F
ORG = 0xF000  # 뱅크 $3F 끝 빈 자리(0xBA05 이후 17,915B 중) — 적용 때 0xFF 인지 확인한다
STATE = 0x1F51  # 항목별 상태 바이트(항목 번호 + $1F51)
CUR = 0x1F50  # 현재 항목
MAGIC = 0x1F5C  # 서명 2B(A5 5A) — 전원 켤 때 WRAM 이 무작위라 상태가 살아 있는지 알린다
ITEMCUR = 0x1F52  # 아이템 넣기 — 다음에 넣을 아이템 번호(소지품 창에서 이름을 본다)
TMP = 0x1F5E  # 곱셈 임시(2B)
SPEED = 0x1F54  # 이동 속도 ×2(0=꺼짐·1=켜짐) — 걸음 크기 `$1502` 를 4 로(걸음 한 칸 4프레임 → 2프레임)
NOENC = 0x1F53  # 조우 끄기(0=꺼짐·1=켜짐) — 접촉형 오브젝트(`$124A,x` 비트7)의 접촉 판정을 건너뛴다

# (항목 이름 목록) — 지명 ID 는 `$95` 부터 차례로, 항목 안에선 값 순서대로 이어진다.
ITEMS: list[list[str]] = [
    ["경험치 1배", "경험치 10배", "경험치 100배"],
]
NAME_BASE = 0x95


def qa_names() -> list[str]:
    """지명 표에 올릴 QA 항목 이름 — 지금은 소리로 알리는 방식이라 비어 있다(HUD 지명 창에 그리는 길은 미해결, devlog 11-18)."""
    return []


def _asm(code: list[str], org: int, ext: dict[str, int] | None = None) -> bytes:
    """토큰: `AD 19 42`(16진 바이트) · `@lab`(라벨 정의) · `^lab`(상대 분기 목표) · `&lab`(같은 뱅크 16비트) · `%lab`(24비트 롱) · `#name`(ext 값 1바이트)."""
    ext = ext or {}
    # 1패스: 길이
    def toks(t):
        return t.split()

    pos, labels = 0, {}
    for t in code:
        if t.startswith("@"):
            labels[t[1:]] = org + pos
            continue
        for p in toks(t):
            pos += 3 if p.startswith("%") else 2 if p.startswith("&") else 1
    out = bytearray()
    for t in code:
        if t.startswith("@"):
            continue
        for p in toks(t):
            if p.startswith("^"):
                rel = labels[p[1:]] - (org + len(out) + 1)
                assert -128 <= rel < 128, (p, rel)
                out.append(rel & 0xFF)
            elif p.startswith("&"):
                a = labels[p[1:]]
                out += bytes([a & 0xFF, a >> 8 & 0xFF])
            elif p.startswith("%"):
                a = labels[p[1:]] if p[1:] in labels else ext[p[1:]]
                out += bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF])
            else:
                out.append(int(p, 16))
    return bytes(out)


def _lo(a):
    return f"{a & 0xFF:02X} {a >> 8 & 0xFF:02X}"


def menu_code(org: int = ORG) -> bytes:
    """진입 키가 한 번 불릴 때 `$05FB` 를 본다(위에서부터 첫 일치 하나만) —
    Y: 경험치 배율 한 칸 돌리기(1→10→100→1배, 효과음 `$14+상태`) ·
    Start: 소지금 +100,000 GOLD(상한 9,999,999 = `$98967F`, 효과음 `$18`) ·
    위: 소지품 첫 빈 칸에 아이템 `ITEMCUR` 를 넣고 번호를 하나 올린다(B 는 창을 닫아 못 쓴다 — 칸 31 개 `$1201~$121F` 다 차면 효과음 `$1B`) ·
    오른쪽/왼쪽: `ITEMCUR` ±10(효과음 `$15`/`$14`) — 어떤 아이템인지는 소지품 창에서 이름으로 본다."""
    cur = _lo(ITEMCUR)
    code = [
        "08 E2 30 48",  # php ; sep #$30 ; pha
        f"AD {_lo(MAGIC)} C9 A5 D0 ^init AD {_lo(MAGIC + 1)} C9 5A F0 ^ready",  # 전원 켤 때 WRAM 은 무작위 — 서명이 없으면 상태를 비운다
        "@init",
        f"A9 00 8D {_lo(STATE)} 8D {_lo(ITEMCUR)} 8D {_lo(NOENC)} 8D {_lo(SPEED)} A9 A5 8D {_lo(MAGIC)} A9 5A 8D {_lo(MAGIC + 1)}",
        "@ready",
        "AD FA 05 29 40 F0 ^nxw AD FB 05 29 0F F0 ^nxw 4C &wk",  # X+방향 = 워프(마스터 11-22: Start·Select 는 원판 저장·로드 단축키라 못 쓴다)
        "@nxw",
        "AD FB 05 29 48 C9 48 D0 03 4C &gold",  # Y+위 = 소지금 +100,000
        "AD FB 05 29 44 C9 44 D0 03 4C &spd",  # Y+아래 = 이동 속도 ×2 토글(켬 $19 · 끔 $17)
        "AD FB 05 29 40 F0 ^btn",  # Y?
        f"AD {_lo(STATE)} 1A C9 {len(ITEMS[0]):02X} 90 ^ok A9 00",  # lda 상태 ; inc ; cmp 개수 ; bcc ; lda #0
        "@ok",
        f"8D {_lo(STATE)}",
        "18 69 14 4C &play",  # clc ; adc #$14 — 효과음 번호 = $14 + 상태
        "@gold",
        "C2 20 AD FE 11 18 69 A0 86 8D FE 11",  # rep #$20 ; lda $11FE ; clc ; adc #$86A0 ; sta  (+100000 하위)
        "E2 20 AD 00 12 69 01 8D 00 12",  # sep #$20 ; lda $1200 ; adc #1 ; sta
        "C9 98 90 ^gok D0 ^cap",  # < $98 정상 · > $98 상한
        "C2 20 AD FE 11 C9 7F 96 E2 20 90 ^gok",  # 같으면 하위 비교
        "@cap",
        "C2 20 A9 7F 96 8D FE 11 E2 20 A9 98 8D 00 12",
        "@gok",
        "A9 04 8D A3 09 22 FD 96 00",  # HUD 소지금 다시 그리기 — 원판 소지금 감소 루틴(`$00:9E02`)과 같은 두 줄
        "A9 18 4C &play",
        "@btn",
        "AD FB 05 29 08 F0 ^rt",  # 위?
        f"AD {cur} F0 ^fix C9 77 90 ^cok",  # 0 이거나 사전 밖이면 1 로
        "@fix",
        f"A9 01 8D {cur}",
        "@cok",
        "A2 00",
        "@scan",
        "BD 01 12 F0 ^put E8 E0 1F 90 ^scan",  # 빈 칸(0) 찾기
        "A9 1B 4C &play",  # 가득 참
        "@put",
        f"AD {cur} 9D 01 12 1A C9 77 90 ^nx A9 01",  # 넣고 번호 +1(끝이면 1 로)
        "@nx",
        f"8D {cur}",
        "A9 18 4C &play",
        "@rt",
        "AD FB 05 29 01 F0 ^lf",  # 오른쪽?
        f"AD {cur} 18 69 0A C9 77 90 ^rok E9 77",  # +10 ; 넘치면 −$77 (carry 켜짐)
        "@rok",
        f"8D {cur}",
        "A9 15 4C &play",
        "@lf",
        "AD FB 05 29 02 F0 ^dn",  # 왼쪽?
        f"AD {cur} C9 0A B0 ^lok 18 69 77",  # < 10 이면 +$77
        "@lok",
        "38 E9 0A",  # −10
        f"8D {cur}",
        "A9 14 4C &play",
        "@dn",
        "AD FB 05 29 04 F0 ^out",  # 아래? — 조우 끄기 토글(켬 효과음 $19 · 끔 $17)
        f"AD {_lo(NOENC)} 49 01 8D {_lo(NOENC)}",
        "F0 ^offs A9 19 4C &play",  # eor 결과가 0 이면 꺼짐
        "@offs",
        "A9 17",
        "@play",
        "E2 30 22 %snd",
        "@out",
        "68 28 6B",
        "@spd",
        f"AD {_lo(SPEED)} 49 01 8D {_lo(SPEED)}",
        "22 E8 AD 00",  # ADE8 는 맵을 불러올 때만 도니(걸음 크기 `$1502` 를 그때만 정한다) 바로 다시 불러 켬/끔을 반영한다
        f"AD {_lo(SPEED)} F0 ^soff A9 19 4C &play",
        "@soff",
        "A9 17 4C &play",  # pla ; plp ; rtl
        # 워프 — 지금 맵 `$1231` 에서 +1(오른쪽)·−1(왼쪽)·+10(위)·−10(아래), 142 칸(0~$8D)을 돈다. 좌표는 맵 가운데 쯤(128,128)으로 고정한다.
        # 필드 루프 입구 `$02:F826`(스택을 비우고 장면 `$1468` 로 간다 — 1=월드맵·2=그 밖)로 뛴다 — 돌아오지 않는다.
        "@wk",
        "AD FB 05 29 01 F0 ^w1 A9 01 80 ^wgo",
        "@w1",
        "AD FB 05 29 02 F0 ^w2 A9 8D 80 ^wgo",
        "@w2",
        "AD FB 05 29 08 F0 ^w3 A9 0A 80 ^wgo",
        "@w3",
        "A9 84",
        "@wgo",
        "18 6D 31 12 B0 ^wsub C9 8E 90 ^wst",
        "@wsub",
        "E9 8E",
        "@wst",
        "8D 31 12",
        "C2 20 A9 80 00 8D 45 12 8D 47 12 A9 10 00 8D 32 12 8D 34 12 E2 30",
        "AD 31 12 D0 ^wfld A9 01 80 ^wsc",
        "@wfld",
        "A9 02",
        "@wsc",
        "8D 68 14 A9 05 8D 6A 14 AD 68 14 5C 26 F8 02",
    ]
    return _asm(code, org, {"snd": 0x1E8518})


# --- 경험치 배율 — 승리 보상 EP($094E, 16비트)를 메시지 출력 직전에 곱한다 -------------------
EP_SITE = 0x01B3B8  # `E2 30 A9 2F`(sep #$30 ; lda #$2F) 4B — 바로 앞 `ldx $0950 / beq / inc $094E` 다음
EP_ORIG = bytes.fromhex("e230a92f")


def ep_code(org: int) -> bytes:
    s = f"{STATE:04X}"  # noqa: F841
    code = [
        f"E2 20 AD {_lo(MAGIC)} C9 A5 D0 ^done AD {_lo(MAGIC + 1)} C9 5A D0 ^done",  # 서명이 없으면(메뉴를 한 번도 안 열었다) 1배
        "C2 20 E2 10",  # rep #$20 ; sep #$10 (원래 이 자리의 상태)
        f"AE {_lo(STATE)}",  # ldx 상태(0·1·2)
        "F0 ^done",
        "AD 4E 09",  # lda $094E
        "@m",
        f"8D {_lo(TMP)}",  # sta tmp
        "0A 90 ^c1 80 ^sat",  # ×2  (넘치면 포화)
        "@c1",
        "0A 90 ^c2 80 ^sat",  # ×4
        "@c2",
        "18",
        f"6D {_lo(TMP)} B0 ^sat",  # ×5
        "0A B0 ^sat",  # ×10
        "CA D0 ^m",  # 다음 배율 단계(×10 한 번 더)
        "80 ^store",
        "@sat",
        "A9 FF FF",
        "@store",
        "8D 4E 09",
        "@done",
        "E2 30 A9 2F 6B",  # 원래 두 명령 + rtl
    ]
    return _asm(code, org)


# --- 조우 끄기 — 접촉 판정(`$02:F41B` 입구 `lda $124A,x / bit #$80`)을 훅해서 켜져 있으면 비트7 없음으로 돌려준다 -------------
CT_SITE = 0x02F420  # `BD 4A 12 89 80`(lda $124A,x ; bit #$80) 5B — 뒤따르는 `bne` 가 Z 로 갈린다
CT_ORIG = bytes.fromhex("bd4a128980")
CT2_SITE = 0x00B02C  # 이동 중 오브젝트에 부딪히는 경로 — `BD 4A 12 29 80`(lda $124A,x ; and #$80), 뒤 `bne` 가 Z 로 갈린다(A 는 안 쓴다)
CT2_ORIG = bytes.fromhex("bd4a122980")


def ct_code(org: int) -> bytes:
    code = [
        f"AD {_lo(MAGIC)} C9 A5 D0 ^off AD {_lo(MAGIC + 1)} C9 5A D0 ^off",  # 서명 없으면 꺼짐
        f"AD {_lo(NOENC)} F0 ^off",
        "A9 00 6B",  # lda #0 → Z=1 : 접촉형이 아닌 것으로 본다
        "@off",
        "BD 4A 12 89 80 6B",  # 원래 두 명령 + rtl
    ]
    return _asm(code, org)


# --- 이동 속도 ×2 — `$00:ADE8` 가 `$1239` 로 걸음 크기 `$1502`(기본 2)를 정한 직후 4 로 덮는다 ----------------------------------
# 걸음 한 칸은 `$150B`=8 에서 프레임마다 `$1502` 씩 줄어 0 이 될 때까지(2 → 4프레임) — 4 면 2프레임. 6 은 8 에서 나누어떨어지지 않아 쓰지 못한다.
SP_SITE = 0x00ADF7  # `8D 02 15 A9 00`(sta $1502 ; lda #0) 5B
SP_ORIG = bytes.fromhex("8d0215a900")


def sp_code(org: int) -> bytes:
    code = [
        "8D 02 15",  # 원래 sta $1502
        f"AD {_lo(MAGIC)} C9 A5 D0 ^no AD {_lo(MAGIC + 1)} C9 5A D0 ^no",
        f"AD {_lo(SPEED)} F0 ^no",
        "A9 04 8D 02 15",
        "@no",
        "A9 00 6B",  # 원래 lda #0 + rtl
    ]
    return _asm(code, org)


def apply(out: bytearray, rom: bytes) -> dict:
    org = ORG
    menu = menu_code(org)
    ep_org = org + len(menu)
    ep = ep_code(ep_org)
    ct_org = ep_org + len(ep)
    ct = ct_code(ct_org)
    sp_org = ct_org + len(ct)
    sp = sp_code(sp_org)
    blob = menu + ep + ct + sp
    o = common.snes2off((BANK << 16) | org)
    if bytes(out[o : o + len(blob)]) != b"\xff" * len(blob):
        raise SystemExit(f"QA 디버그 코드 자리가 비어 있지 않다 ${BANK:02X}:{org:04X}")
    out[o : o + len(blob)] = blob
    so = common.snes2off(EP_SITE)
    if bytes(rom[so : so + 4]) != EP_ORIG:
        raise SystemExit(f"QA 경험치 훅 자리가 예상과 다르다: {rom[so : so + 4].hex()}")
    ep_addr = (BANK << 16) | ep_org
    out[so : so + 4] = bytes([0x22, ep_addr & 0xFF, ep_addr >> 8 & 0xFF, ep_addr >> 16])
    co = common.snes2off(CT_SITE)
    if bytes(rom[co : co + 5]) != CT_ORIG:
        raise SystemExit(f"QA 접촉 훅 자리가 예상과 다르다: {rom[co : co + 5].hex()}")
    ct_addr = (BANK << 16) | ct_org
    out[co : co + 5] = bytes([0x22, ct_addr & 0xFF, ct_addr >> 8 & 0xFF, ct_addr >> 16, 0xEA])
    c2 = common.snes2off(CT2_SITE)
    if bytes(rom[c2 : c2 + 5]) != CT2_ORIG:
        raise SystemExit(f"QA 접촉 훅2 자리가 예상과 다르다: {rom[c2 : c2 + 5].hex()}")
    out[c2 : c2 + 5] = bytes([0x22, ct_addr & 0xFF, ct_addr >> 8 & 0xFF, ct_addr >> 16, 0xEA])
    spo = common.snes2off(SP_SITE)
    if bytes(rom[spo : spo + 5]) != SP_ORIG:
        raise SystemExit(f"QA 속도 훅 자리가 예상과 다르다: {rom[spo : spo + 5].hex()}")
    sp_addr = (BANK << 16) | sp_org
    out[spo : spo + 5] = bytes([0x22, sp_addr & 0xFF, sp_addr >> 8 & 0xFF, sp_addr >> 16, 0xEA])
    return {
        "QA 메뉴": f"${BANK:02X}:{org:04X}",
        "경험치 훅": f"${BANK:02X}:{ep_org:04X}",
        "바이트": len(blob),
    }


def menu_entry() -> int:
    return (BANK << 16) | ORG


def patch_ranges() -> list[tuple[int, int]]:
    m = len(menu_code(ORG))
    e = len(ep_code(ORG + m))
    c = len(ct_code(ORG + m + e))
    sl = len(sp_code(ORG + m + e + c))
    n = m + e + c + sl
    o = common.snes2off((BANK << 16) | ORG)
    so = common.snes2off(EP_SITE)
    co = common.snes2off(CT_SITE)
    c2 = common.snes2off(CT2_SITE)
    spo = common.snes2off(SP_SITE)
    return [(o, o + n), (so, so + 4), (co, co + 5), (c2, c2 + 5), (spo, spo + 5)]
