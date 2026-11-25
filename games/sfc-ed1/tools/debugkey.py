"""제품 롬의 디버그 진입키 — 필드에서 **L+R 을 1초** 누르면 원판 디버그 메뉴 B 가, **L+R+X 를 1초** 누르면 메뉴 A 가 열린다(마스터 10-24).

원판엔 두 메뉴가 있다. 메뉴 B(사운드 테스트·조합 일람·몬스터 일람, `$02:FB4D`)는 타이틀 선택 화면의 L+R+Y 로만, 메뉴 A(전투 테스트·
사운드 체크·맵 체크, `$02:FA34`)는 부르는 곳이 없다(status.md 「디버그 모드 분석」). 필드에서 여는 길을 더할 뿐 새 기능은 없다.

🔴 필드의 다른 버튼(Start·B·X·Y·Select)은 누르는 즉시 창을 연다 — 그래서 L+R 이다. 필드 디스패처(`$00:881D`)는 L 이면 요슈아의
거울, R 이면 바로 워프(둘 다 소지 시만)를 쓴다. **L 과 R 이 같은 프레임에 눌려 있을 때만** 세고 그때만 디스패치를 막으므로, 평소
입력에는 지연이 없다. 잔여 위험: 거울을 가진 채 L 을 R 보다 한두 프레임 먼저 누르면 거울이 먼저 뜬다.

⚠ 메뉴 A 는 파티 RAM 을 시험 파티로 덮고 두 메뉴 모두 나가는 길이 리셋뿐이다 — 저장 안 한 진행이 사라진다(SRAM 은 그대로).

방법: 디스패처가 `$1144==$FF` 를 확인한 직후(`$00:8827` — `lda $1145 / bit #$2F`)를 `JML` 로 빼고, 트램펄린이 그 두 명령을 대신 실행한 뒤
`$00:882C` 로 되돌린다. 시간은 프레임 카운터 `$05EF`(필드에서 프레임마다 +1)로 잰다 — 디스패처가 4프레임마다 불려서 호출 수로는 4배가 걸린다(첫 시도의 실측).\n세는 상태는 WRAM `$1F42`(표시)·`$1F43`(시작 프레임) 두 바이트(롬 전체에서 쓰는 곳이 없다).
"""

import common

SITE = 0x008827
SITE_ORIG = bytes.fromhex("ad4511892f")  # lda $1145 / bit #$2F
BACK = 0x00882C  # beq $882F (플래그는 bit 결과)
TRAMP = 0x02FF30  # 뱅크 $02 끝의 빈 자리(훅 스텁 뒤 $FF21~ 223B 중)
MENU_A = 0x02FA34
MENU_B = 0x02FB4D
COUNTER = 0x1F42  # +0 세는 중 표시 · +1 시작 프레임
FRAME_CTR = 0x05EF  # 필드에서 프레임마다 1 오르는 바이트(실측) — 디스패처는 4프레임마다 불려서 호출 수로는 못 잰다
FRAMES = 60  # 약 1초


def _tramp() -> bytes:
    f, t = COUNTER, COUNTER + 1
    fl = f"{f & 0xFF:02X} {f >> 8:02X}"
    st = f"{t & 0xFF:02X} {t >> 8:02X}"
    code = [
        ("AD FB 05", None),  # lda $05FB       Start·Select·Y·B·십자키
        ("D0 @no", None),
        ("AD FA 05", None),  # lda $05FA       A·X·L·R
        ("29 BF", None),  # and #$BF        X 는 뺀다(L+R 이나 L+R+X)
        ("C9 30", None),  # cmp #$30        정확히 L+R
        ("D0 @no", None),
        (f"AD {fl}", None),  # lda flag
        ("D0 @cont", None),
        ("@start", None),
        ("A9 01", None),
        (f"8D {fl}", None),  # 세기 시작
        (f"AD {FRAME_CTR & 0xFF:02X} {FRAME_CTR >> 8:02X}", None),  # lda 프레임 카운터
        (f"8D {st}", None),  # 시작 프레임
        ("80 @sup", None),
        ("@cont", None),
        (f"AD {FRAME_CTR & 0xFF:02X} {FRAME_CTR >> 8:02X}", None),
        ("38", None),  # sec
        (f"ED {st}", None),  # sbc 시작 프레임 → 지난 프레임(모듈로 256)
        (f"C9 {FRAMES:02X}", None),
        ("90 @sup", None),  # < 60 : 열지 않고 이번 디스패치도 막는다
        (f"C9 {FRAMES + 12:02X}", None),
        ("B0 @start", None),  # 너무 오래(디스패처가 한동안 안 불렸다) : 다시 센다
        (f"9C {fl}", None),  # stz flag
        ("AD FA 05", None),
        ("C9 70", None),  # L+R+X ?
        ("F0 @a", None),
        (f"5C {MENU_B & 0xFF:02X} {MENU_B >> 8 & 0xFF:02X} {MENU_B >> 16:02X}", None),
        ("@a", None),
        (f"5C {MENU_A & 0xFF:02X} {MENU_A >> 8 & 0xFF:02X} {MENU_A >> 16:02X}", None),
        ("@sup", None),
        ("6B", None),  # rtl
        ("@no", None),
        (f"9C {fl}", None),
        ("AD 45 11", None),  # 원래 명령
        ("89 2F", None),
        (f"5C {BACK & 0xFF:02X} {BACK >> 8 & 0xFF:02X} {BACK >> 16:02X}", None),
    ]
    # 두 패스: 라벨 위치 → 상대 분기
    pos, labels = 0, {}
    for t, _ in code:
        if t.startswith("@"):
            labels[t[1:]] = pos
        else:
            pos += len(t.split())
    out = bytearray()
    for t, _ in code:
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


TRAMP_BYTES = _tramp()


def apply(out: bytearray, rom: bytes) -> dict:
    so = common.snes2off(SITE)
    if bytes(rom[so : so + 5]) != SITE_ORIG:
        raise SystemExit(f"디버그 진입키 자리가 예상과 다르다: {rom[so : so + 5].hex()}")
    to = common.snes2off(TRAMP)
    if bytes(out[to : to + len(TRAMP_BYTES)]) != b"\xff" * len(TRAMP_BYTES):
        raise SystemExit(f"디버그 진입키 트램펄린 자리가 비어 있지 않다 {common.fmt(TRAMP)}")
    out[to : to + len(TRAMP_BYTES)] = TRAMP_BYTES
    out[so : so + 5] = bytes([0x5C, TRAMP & 0xFF, TRAMP >> 8 & 0xFF, TRAMP >> 16, 0xEA])
    return {
        "키": "필드 L+R 1초 → 메뉴 B · L+R+X 1초 → 메뉴 A",
        "트램펄린": common.fmt(TRAMP),
        "바이트": len(TRAMP_BYTES),
        "상태 바이트": f"${COUNTER:04X}~{COUNTER + 1:04X}",
    }


def patch_ranges() -> list[tuple[int, int]]:
    so, to = common.snes2off(SITE), common.snes2off(TRAMP)
    return [(so, so + 5), (to, to + len(TRAMP_BYTES))]
