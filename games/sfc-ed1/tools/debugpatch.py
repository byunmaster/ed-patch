"""시험 빌드 전용 디버그 진입 — 메뉴 A(전투 테스트·사운드 체크·맵 체크)를 타이틀 선택 화면에서 여는 둘째 조합.

🔴 **제품 롬에는 들어가지 않는다.** `ED_DEBUG=1`(꼬리표 `test-debug` 로 강제)일 때만 `build.py` 가 부른다.
   스위치 없이 구운 롬의 sha1 이 이 모듈이 생기기 전과 같아야 한다(`status.md` 「디버그 빌드」).

원판엔 디버그 메뉴가 둘 있다. 메뉴 B(`$02:FB4D`)는 L+R+Y 로 열리지만(`$02:F61B` 가 `$05FA==$30 && $05FB==$40`
을 정확 비교), 메뉴 A(`$02:FA34`)는 **부르는 곳이 롬 전체에 없다**(status.md 「디버그 모드 분석」). 둘째 조합
**L+R+X**(`$05FA==$70`, `$05FB==0`)를 같은 자리에 더해 `$FA34` 로 보낸다.

⚠ 메뉴 A 는 시작에서 `$1220~$122E`·`$11D9~$11F8` 을 0 으로 지우고 시험 파티를 `$13CB~` 에 쓴다 — 불러온 게임 위에서
열면 게임 상태가 덮인다. 이 조합 검사는 **타이틀 선택 화면 진입 직후 한 번**만 돈다(원판 L+R+Y 와 같은 자리).

방법: `$02:F61B`(원본 17바이트 비교)의 첫 3바이트를 `JMP $FEA0` 으로 바꾸고, 빈 자리(`$02:FEA0`)에 비교를 다시 쓴다
(둘째 조합 → A, 원본 조합 → B, 아니면 원래 흐름 `$02:F62C`). 8비트 레지스터 문맥(`$02:F57F` 의 `SEP #$30`) 그대로.
"""

import common

SITE = 0x02F61B
SITE_ORIG = bytes.fromhex("adfa05c930d00aadfb05c940d0034c4dfb")  # 원본 비교 17바이트
TRAMP = 0x02FEA0
MENU_A = 0x02FA34
MENU_B = 0x02FB4D
CONT = 0x02F62C

TRAMP_BYTES = bytes(
    [
        0xAD, 0xFA, 0x05,  # LDA $05FA
        0xC9, 0x70,  # CMP #$70        (L+R+X)
        0xD0, 0x08,  # BNE orig
        0xAD, 0xFB, 0x05,  # LDA $05FB
        0xD0, 0x03,  # BNE orig        (다른 버튼이 같이 눌렸다)
        0x4C, MENU_A & 0xFF, MENU_A >> 8 & 0xFF,  # JMP $FA34
        # orig:
        0xAD, 0xFA, 0x05,  # LDA $05FA
        0xC9, 0x30,  # CMP #$30        (L+R)
        0xD0, 0x0A,  # BNE cont
        0xAD, 0xFB, 0x05,  # LDA $05FB
        0xC9, 0x40,  # CMP #$40        (Y)
        0xD0, 0x03,  # BNE cont
        0x4C, MENU_B & 0xFF, MENU_B >> 8 & 0xFF,  # JMP $FB4D
        # cont:
        0x4C, CONT & 0xFF, CONT >> 8 & 0xFF,  # JMP $F62C
    ]
)


def apply(out: bytearray, rom: bytes) -> dict:
    so = common.snes2off(SITE)
    if bytes(rom[so : so + len(SITE_ORIG)]) != SITE_ORIG:
        raise SystemExit(f"디버그 조합 자리가 예상과 다르다: {rom[so : so + len(SITE_ORIG)].hex()}")
    to = common.snes2off(TRAMP)
    if bytes(out[to : to + len(TRAMP_BYTES)]) != b"\xff" * len(TRAMP_BYTES):
        raise SystemExit(f"디버그 트램펄린 자리가 비어 있지 않다 {common.fmt(TRAMP)}")
    out[to : to + len(TRAMP_BYTES)] = TRAMP_BYTES
    out[so : so + 3] = bytes([0x4C, TRAMP & 0xFF, TRAMP >> 8 & 0xFF])
    return {"조합": "L+R+X → 메뉴 A($02:FA34)", "트램펄린": common.fmt(TRAMP), "바이트": len(TRAMP_BYTES)}


def patch_ranges() -> list[tuple[int, int]]:
    so, to = common.snes2off(SITE), common.snes2off(TRAMP)
    return [(so, so + 3), (to, to + len(TRAMP_BYTES))]
