"""제품 롬의 디버그 진입키 — **주메뉴(커맨드 창 등 커서 창)를 연 채 L+R+Select 를 1초** 누르면 원판 디버그 메뉴 B 가, **L+R+Select+X 를 1초** 누르면 메뉴 A 가 열린다
(마스터 11-07 「SFC II 와 같이 메뉴·타이틀에서 L+R+Select 1초」 — 종전 필드 L+R 1초를 대체).

원판엔 두 메뉴가 있다. 메뉴 B(사운드 테스트·조합 일람·몬스터 일람, `$02:FB4D`)는 타이틀 선택 화면의 L+R+Y 로만(그대로 둔다), 메뉴 A(전투 테스트·
사운드 체크·맵 체크, `$02:FA34`)는 부르는 곳이 없다(status.md 「디버그 모드 분석」). 창 안에서 여는 길을 더할 뿐 새 기능은 없다.

🔴 필드에서 Select 만 누르면 「로드」 창이 열린다(원판 기능 — 11-07 실측) — 그래서 Select 길게를 필드에서 못 쓰고, 창이 열린 뒤(커서 창 루프 안)에서만 센다.
창 루프는 L·R·Select·X 를 받지 않으므로(받는 키 마스크 `$1704/$1705`) 누르고 있어도 창은 반응하지 않는다. 요슈아의 거울(L)·워프(R)는 필드 디스패처(`$00:881D`)의 몫이라 창 안에선 안 나간다.

⚠ 메뉴 A 는 파티 RAM 을 시험 파티로 덮고 두 메뉴 모두 나가는 길이 리셋뿐이다 — 저장 안 한 진행이 사라진다(SRAM 은 그대로).

방법: 모든 커서 창이 도는 `$02:9AC3` 루프가 매 반복 키를 읽는 `lda $05FA`(`$02:9B3F`)를 `JSR` 스텁으로 갈아 끼운다. 스텁이 `$05FB` 의 Select 와 `$05FA` 가 정확히
L+R(+X)인 반복을 세어(반복 = 1프레임) 60번째에 메뉴로 `JML` 한다. 아니면 세기를 비우고 원래 `lda $05FA` 를 대신한다(A·플래그는 원래와 같다).
"""

import common

SITE = 0x029B3F  # 커서 창 루프의 키 읽기 `lda $05FA`(첫 반복)
SITE2 = 0x029BC4  # 같은 읽기(키가 없는 동안 도는 대기 반복 — 창을 열어 두고 가만히 있을 때 지나는 쪽)
SITE_ORIG = bytes.fromhex("adfa05")
PAD_SITE = 0x00AAC2  # NMI 조이패드 읽기(`$00:AABF`) 안 `lda $4219 / sta $1918` — 프레임마다 한 번(세는 자리)
PAD_ORIG = bytes.fromhex("AD1942" "8D1819")
TRAMP = 0x02FF30  # 뱅크 $02 끝의 빈 자리(훅 스텁 뒤 $FF21~ 223B 중) — 앞이 센 스텁, 뒤가 창 루프 스텁
MENU_A = 0x02FA34
MENU_B = 0x02FB4D
COUNTER = 0x1F42  # 세는 프레임 수(1바이트, 60 에서 멈춤) — 원판이 안 쓰는 칸(쓰기 감시, 10-24)
FRAMES = 60  # NMI 프레임 = 약 1초


def _asm(code):
    # 두 패스: 라벨 위치 → 상대 분기
    pos, labels = 0, {}
    for t in code:
        if t.startswith("@"):
            labels[t[1:]] = pos
        else:
            pos += len(t.split())
    out = bytearray()
    for t in code:
        if t.startswith("@"):
            continue
        parts = t.split()
        if parts[-1].startswith("@"):
            rel = labels[parts[-1][1:]] - (len(out) + 2)
            assert -128 <= rel < 128
            out += bytes(int(p, 16) for p in parts[:-1]) + bytes([rel & 0xFF])
        else:
            out += bytes(int(p, 16) for p in parts)
    return bytes(out)


def _count() -> bytes:
    """NMI 조이패드 읽기에서 프레임마다 불린다 — Select(`$4219` bit5) + `$05FA` 가 정확히 L+R(+X)이면 센다, 아니면 비운다. 원래 두 명령을 대신한다."""
    c = f"{COUNTER & 0xFF:02X} {COUNTER >> 8:02X}"
    return _asm(
        [
            "AD 19 42",  # lda $4219      (원래)
            "8D 18 19",  # sta $1918      (원래)
            "0D 1B 42",  # ora $421B      (게임이 05FB 를 만드는 것과 같게 — 두 패드 OR)
            "29 20",  # and #$20       Select
            "F0 @clr",
            "AD FA 05",  # lda $05FA      A·X·L·R
            "29 BF",  # and #$BF       X 는 뺀다(L+R 이나 L+R+X)
            "C9 30",  # cmp #$30       정확히 L+R
            "D0 @clr",
            f"AD {c}",
            f"C9 {FRAMES:02X}",
            "B0 @done",  # 60 에서 멈춘다
            f"EE {c}",
            "80 @done",
            "@clr",
            f"9C {c}",
            "@done",
            "6B",  # rtl
        ]
    )


def _menu() -> bytes:
    """커서 창 루프가 매 반복 키를 읽는 자리 — 60 프레임을 센 뒤면 메뉴로 간다(X 를 같이 눌렀으면 A, 아니면 B). 아니면 원래 `lda $05FA` 를 대신한다."""
    c = f"{COUNTER & 0xFF:02X} {COUNTER >> 8:02X}"
    return _asm(
        [
            f"AD {c}",
            f"C9 {FRAMES:02X}",
            "90 @ret",  # < 60 : 평소대로
            f"9C {c}",
            "AD FA 05",
            "29 40",  # X ?
            "D0 @a",
            f"5C {MENU_B & 0xFF:02X} {MENU_B >> 8 & 0xFF:02X} {MENU_B >> 16:02X}",
            "@a",
            f"5C {MENU_A & 0xFF:02X} {MENU_A >> 8 & 0xFF:02X} {MENU_A >> 16:02X}",
            "@ret",
            "AD FA 05",  # 원래 명령(A = $05FA, 플래그 포함)
            "60",  # rts
        ]
    )


COUNT_BYTES = _count()
MENU_BYTES = _menu()
TRAMP_BYTES = COUNT_BYTES + MENU_BYTES
MENU_STUB = TRAMP + len(COUNT_BYTES)


def apply(out: bytearray, rom: bytes) -> dict:
    so, so2, po = common.snes2off(SITE), common.snes2off(SITE2), common.snes2off(PAD_SITE)
    for o in (so, so2):
        if bytes(rom[o : o + 3]) != SITE_ORIG:
            raise SystemExit(f"디버그 진입키 창 루프 자리가 예상과 다르다: {rom[o : o + 3].hex()}")
    if bytes(rom[po : po + 6]) != PAD_ORIG:
        raise SystemExit(f"디버그 진입키 조이패드 자리가 예상과 다르다: {rom[po : po + 6].hex()}")
    to = common.snes2off(TRAMP)
    if bytes(out[to : to + len(TRAMP_BYTES)]) != b"\xff" * len(TRAMP_BYTES):
        raise SystemExit(f"디버그 진입키 트램펄린 자리가 비어 있지 않다 {common.fmt(TRAMP)}")
    out[to : to + len(TRAMP_BYTES)] = TRAMP_BYTES
    for o in (so, so2):
        out[o : o + 3] = bytes([0x20, MENU_STUB & 0xFF, MENU_STUB >> 8 & 0xFF])  # jsr (뱅크 $02 안)
    out[po : po + 6] = bytes([0x22, TRAMP & 0xFF, TRAMP >> 8 & 0xFF, TRAMP >> 16, 0xEA, 0xEA])  # jsl + nop nop
    return {
        "키": "주메뉴(커서 창)를 연 채 L+R+Select 1초 → 메뉴 B · +X → 메뉴 A",
        "트램펄린": common.fmt(TRAMP),
        "바이트": len(TRAMP_BYTES),
        "상태 바이트": f"${COUNTER:04X}",
    }


def patch_ranges() -> list[tuple[int, int]]:
    so, so2, po, to = common.snes2off(SITE), common.snes2off(SITE2), common.snes2off(PAD_SITE), common.snes2off(TRAMP)
    return [(so, so + 3), (so2, so2 + 3), (po, po + 6), (to, to + len(TRAMP_BYTES))]
