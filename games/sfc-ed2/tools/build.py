"""sfc-ed2 배치기 뼈대 — 원본을 2MB 로 넓혀 쓰고 규율 검사를 건다(번역 문안은 아직 없다).

지금은 **한 바이트도 안 바꾼 2MB 롬**을 만든다(뒤 0.5MB 는 확장 뱅크 `$D8~$DF`, `$FF` 채움). 목적은 뼈대 검증이다:
  · 무변경 구간(`IMMUTABLE`)을 선언하고 출력과 원본을 byte 대조한다 — 헤더 체크섬 4바이트만 예외
  · 헤더 체크섬 재계산: 원본은 1.5MB 를 2MB 로 선언하고 0.5MB 를 반복해 합을 냈다(`common.verify_originals`) —
    실제 2MB 가 되면 단순 합이다
  · 결정성: 같은 입력이면 같은 바이트(`--twice` 로 두 번 만들어 sha1 대조)
  · 화면 일본어 게이트: 번역 안 된 메시지 단위 수를 센다. 번역 전엔 전부 남아 있으므로 **정보만 찍고** `--strict` 에서 실패
  · 실패하면 산출물을 `*.failed` 로 돌린다(낡은 이미지를 정상으로 오해하지 않게)

    python3 games/sfc-ed2/tools/build.py [--twice] [--strict]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import script
import ui

NEW_SIZE = 2 * 1024 * 1024
OUT_NAME = "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
CHK_OFF = common.HEADER_OFF + 0x1C  # 보수(2B) + 체크섬(2B)
# 무변경 구간 — 원본 1.5MB 전체. 예외는 체크섬 4바이트(재계산)뿐이다.
IMMUTABLE = [(0, common.ROM_SIZE)]

# 글꼴 이전 — 전각 글리프표를 `$D8:0000` 으로 옮긴다(원본은 `$D6:81D1`, 반각 글꼴 앞이라 1,284자뿐).
# 소비자는 `$C0:9F56` 한 곳: `adc #$81D1`(기준) · `mvn $00,$D6`(소스 뱅크) — 둘을 고친다. 길이 `$12` 는 그대로.
FONT_BANK = 0xD8
FONT_SLOTS = 2048  # 2바이트 코드 `$8000~$87FF` 전부
PATCHES = [  # (주소, 원본 바이트, 새 바이트) — 원본이 다르면 그 자리에서 죽는다
    (0xC09F71, bytes([0xD1, 0x81]), bytes([0x00, 0x00])),
    (0xC09F81, bytes([0xD6]), bytes([FONT_BANK])),
]

# 트램펄린 — 대사 제어코드 `$17`(원본 핸들러는 `rts` 뿐, 단위 안 출현 1회) 을 **24비트 점프**로 바꾼다: `17 lo hi bank`.
# 메시지 머리를 이 4바이트로 덮고 번역문은 확장 뱅크에 둔다(`$0F` 는 같은 뱅크 16비트라 뱅크를 못 넘는다).
# 핸들러는 `$0F`(`$C0:AD89`)와 같은 규약이다: Y = 제어코드 다음 색인(16비트), `[$A6]` 가 텍스트 포인터. 뱅크 `$C0` 끝 0xFF 빈 자리에 둔다.
STUB_ADDR = 0xC0FB10
STUB = bytes.fromhex(
    "B7A6" "C8" "8DAC00"  # lda [$A6],y ; iny ; sta $00AC   (lo)
    "B7A6" "C8" "8DAD00"  # lda [$A6],y ; iny ; sta $00AD   (hi)
    "B7A6" "8DA800"  # lda [$A6],y ; sta $00A8             (bank — 마지막에 읽고 바꾼다)
    "ACAC00" "8CA600"  # ldy $00AC ; sty $00A6
    "A00000" "60"  # ldy #$0000 ; rts
)
TRAMP_CODE = 0x17
TRAMP_ENTRY = 0xC0AB43 + 2 * TRAMP_CODE  # 제어코드 점프표(핸들러 주소 − 1, 리틀엔디언)
PATCHES += [
    (TRAMP_ENTRY, bytes([0xA2, 0xAE]), ((STUB_ADDR - 1) & 0xFFFF).to_bytes(2, "little")),
    (STUB_ADDR, b"\xff" * len(STUB), STUB),
]

# 창 블록 로더(`$C0:D6A7`)는 `mvn $7F,$C0` 으로 블록을 복사해 **소스 뱅크가 $C0 에 박혀 있다** — 블록을 확장 뱅크로 못 옮긴다.
# 복사 구간(`$C0:D6D9~D6E5`, 13B)을 `JML $C0:FB40` 으로 돌려 `[$AC],y`(24비트) 복사 루프로 바꾼다. 진입 상태: A·X·Y 16비트,
# `$11E8` = 블록 길이(5 + rows×stride), `[$AC..$AE]` = 블록 24비트 주소. 복귀는 원본 꼬리(`sep #$30; lda #0; pha; plb; plp; rtl`)와 같다.
LOADER_ADDR = 0xC0D6D9
LOADER_OLD = bytes.fromhex("AEAC00" "A028D4" "ADE811" "3A" "547FC0")
LOADER_STUB_ADDR = 0xC0FB40
LOADER_STUB = bytes.fromhex(
    "E220"  # sep #$20
    "A20000" "A00000"  # ldx #0 ; ldy #0
    "B7AC" "9F28D47F" "C8" "E8" "CCE811" "D0F3"  # loop: lda [$AC],y ; sta $7F:D428,x ; iny ; inx ; cpy $11E8 ; bne loop
    "E230" "A900" "48" "AB" "28" "6B"  # sep #$30 ; lda #0 ; pha ; plb ; plp ; rtl
)
PATCHES += [
    (LOADER_ADDR, LOADER_OLD, bytes([0x5C, LOADER_STUB_ADDR & 0xFF, (LOADER_STUB_ADDR >> 8) & 0xFF, LOADER_STUB_ADDR >> 16]) + b"\xea" * 9),
    (LOADER_STUB_ADDR, b"\xff" * len(LOADER_STUB), LOADER_STUB),
]
EXCEPT = [(CHK_OFF, CHK_OFF + 4)] + [(common.snes2off(a), common.snes2off(a) + len(n)) for a, _o, n in PATCHES]
FONT_OUT = common.snes2off(FONT_BANK << 16)


def fix_checksum(rom: bytearray) -> None:
    rom[CHK_OFF : CHK_OFF + 4] = b"\x00\x00\xff\xff"  # 합 계산 때 체크섬 칸은 00 00 FF FF 로 친다(SNES 규약)
    s = sum(rom) & 0xFFFF
    rom[CHK_OFF : CHK_OFF + 2] = (s ^ 0xFFFF).to_bytes(2, "little")
    rom[CHK_OFF + 2 : CHK_OFF + 4] = s.to_bytes(2, "little")


def apply_patches(rom: bytearray) -> None:
    for addr, old, new in PATCHES:
        o = common.snes2off(addr)
        if bytes(rom[o : o + len(old)]) != old:
            raise SystemExit(f"패치 자리가 원본과 다르다: {common.fmt(addr)} {bytes(rom[o : o + len(old)]).hex()} ≠ {old.hex()}")
        rom[o : o + len(new)] = new


# 시험 문안(`--demo`, 배포 아님) — 트램펄린이 한글을 띄우는지 보는 용도. 모든 대사($C2~$CA)의 첫 글자 자리를 이 문장으로 돌린다.
DEMO_TEXT = "안녕하세요 용사님 시험 문안입니다"
DEMO_BASE = 1300  # 시험 글리프 색인 시작(원본 글리프 1,284자 뒤)
DEMO_BANK = 0xD9


# 시작 메뉴(`$C0:CFFB`, 3줄) 시험 — 원본보다 **긴** 줄로 블록을 `$D9:1000` 으로 옮겨 stride·w 를 넓히는 길을 확인한다
DEMO_MENU_ADDR = 0xC0CFFB
DEMO_MENU = ["이어서 모험을 계속하기", "처음부터 새로 시작하기", "저장 데이터를 삭제하기"]
DEMO_MENU_NEW = (DEMO_BANK << 16) | 0x1000


def demo_glyphs() -> dict[str, int]:
    chars = DEMO_TEXT + "".join(DEMO_MENU)
    return {c: DEMO_BASE + i for i, c in enumerate(dict.fromkeys(c for c in chars if c != " "))}


def enc(text: str) -> bytes:
    """시험 문안 → 바이트(한글=시험 글리프 2바이트, 공백 `$20`)."""
    g = demo_glyphs()
    return b"".join(b" " if c == " " else (0x8000 + g[c]).to_bytes(2, "big") for c in text)


def font_table(demo: bool = False) -> bytes:
    """새 글꼴 표 — 원본 글리프표(1,284자)를 그대로 옮긴다. `--demo` 면 시험 한글 글리프를 뒤에 붙인다."""
    import font
    import hangul_font

    n = (common.snes2off(0xD6DC19) - font.FULL_BASE) // font.FULL_STRIDE  # 반각 글꼴 앞까지 = 1,284자
    ft = bytearray(common.rom_bytes()[font.FULL_BASE : font.FULL_BASE + n * font.FULL_STRIDE])
    if demo:
        ft += b"\x00" * ((DEMO_BASE - n) * 18)
        for c in demo_glyphs():
            ft += hangul_font.glyph12(c)
    return bytes(ft)


def demo_text() -> bytes:
    return enc(DEMO_TEXT) + b"\x00"


def trampoline(rom: bytearray, off: int, far: int, writes: list) -> None:
    """메시지 자리 `off` 를 `17 lo hi bank`(far = `$bb:aaaa`)로 덮는다."""
    rom[off : off + 4] = bytes([TRAMP_CODE, far & 0xFF, (far >> 8) & 0xFF, far >> 16])
    writes.append((off, off + 4))


def build(demo: bool = False) -> tuple[bytes, list]:
    src = common.rom_bytes()
    rom = bytearray(src) + bytearray(b"\xff" * (NEW_SIZE - len(src)))
    writes: list[tuple[int, int]] = []
    apply_patches(rom)
    ft = font_table(demo)
    if demo:
        dt = demo_text()
        o = common.snes2off(DEMO_BANK << 16)
        rom[o : o + len(dt)] = dt
        writes.append((o, o + len(dt)))
        ui.move_block(rom, src, DEMO_MENU_ADDR, DEMO_MENU_NEW, [b"\x1f\x20" + enc(t) + b"\x20" for t in DEMO_MENU], writes)
        units, _bad = script.units(src)
        for st, _e in units:
            if not 0x20000 <= st < 0xB0000:  # $C2~$CA — $D4~$D7 은 UI 출력기(`$C0:9395`)라 `$17` 을 모른다
                continue
            first = next((o2 for o2, _ln in script.tokens(src, st) if 0x80 <= src[o2] < 0x88), None)
            if first is not None:
                trampoline(rom, first, (DEMO_BANK << 16) | 0, writes)
    assert len(ft) <= FONT_SLOTS * 18
    rom[FONT_OUT : FONT_OUT + len(ft)] = ft
    # 새 글꼴 영역은 확장 구간 안(원본 1.5MB 뒤)이어야 한다
    assert FONT_OUT >= common.ROM_SIZE
    fix_checksum(rom)
    return bytes(rom), writes


def check_immutable(rom: bytes, writes: list) -> None:
    src = common.rom_bytes()
    bad = []
    for a, b in IMMUTABLE:
        for i in range(a, b):
            if rom[i] != src[i] and not any(x <= i < y for x, y in EXCEPT + writes):
                bad.append(i)
                if len(bad) >= 8:
                    break
    if bad:
        raise SystemExit("무변경 구간이 바뀌었다: " + ", ".join(common.fmt(common.off2snes(i)) for i in bad))
    if len(rom) != NEW_SIZE:
        raise SystemExit(f"크기 {len(rom):,}B (기대 {NEW_SIZE:,}B)")
    s = sum(rom[:CHK_OFF] + b"\x00\x00\xff\xff" + rom[CHK_OFF + 4 :]) & 0xFFFF
    got = int.from_bytes(rom[CHK_OFF + 2 : CHK_OFF + 4], "little")
    cmpl = int.from_bytes(rom[CHK_OFF : CHK_OFF + 2], "little")
    if got != s or cmpl != s ^ 0xFFFF:
        raise SystemExit("헤더 체크섬이 안 맞는다")


def screen_gate(rom: bytes, strict: bool) -> None:
    """번역 안 된 메시지 단위 수. 지금은 번역 문안이 없어 전부 남는다 — 정보만 찍는다."""
    units, _bad = script.units(rom[: common.ROM_SIZE])
    left = sum(1 for s, _e in units if any(0x80 <= rom[o] < 0x88 for o, _ln in script.tokens(rom, s)))
    print(f"  화면 일본어 게이트: 일본어 남은 메시지 단위 {left:,}/{len(units):,} (번역 전 — 정보만)")
    if strict and left:
        raise SystemExit("일본어가 남았다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--twice", action="store_true", help="두 번 만들어 sha1 대조(결정성)")
    ap.add_argument("--demo", action="store_true", help="시험 한글 문안(트램펄린 확인용 — 배포 아님)")
    ap.add_argument("--strict", action="store_true", help="일본어가 남으면 실패")
    a = ap.parse_args()
    common.verify_originals()
    out = common.BUILD_DIR / common.BUILD_TAG / (OUT_NAME.replace("(KR)", "(DEMO)") if a.demo else OUT_NAME)
    out.parent.mkdir(parents=True, exist_ok=True)
    failed = out.with_name(out.name + ".failed")
    for p in (out, failed):
        p.unlink(missing_ok=True)
    try:
        rom, writes = build(a.demo)
        if a.twice and common.sha1_of(build(a.demo)[0]) != common.sha1_of(rom):
            raise SystemExit("비결정적 — 같은 입력에서 sha1 이 갈렸다")
        check_immutable(rom, writes)
        screen_gate(rom, a.strict)
    except BaseException:
        failed.write_bytes(locals().get("rom", b""))
        raise
    out.write_bytes(rom)
    print(f"{out.name}  {len(rom):,}B  sha1={common.sha1_of(rom)}")


if __name__ == "__main__":
    main()
