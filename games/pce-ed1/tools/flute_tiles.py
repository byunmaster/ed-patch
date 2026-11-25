"""용의 피리 접근 용 그림 — 1~5장도 종장처럼 흰 용으로(마스터 11-25 「1~5장 용의피리 드래곤조형」, ⑥).

── 원인(11-25 실측) ──
접근하는 용은 엔티티 둘째 칸 종류 0x38/0x39(필드 몬스터 계열 — 월드맵 객체 블록 0 `$A135 LDA #$38`)이고 VRAM `0x7C00` 두 칸을 그린다.
그 칸에는 **지역 몬스터 타일**이 올라와 있다 — 타일 자원 목록(`$C012+n`, 한 칸 = 자원 번호 한 바이트, 로더 `$69C7`/`$69CC` 가
캐시 `$CF24+n` 와 비교해 **다를 때만** 그 칸의 섹터를 읽는다)의 일곱째 칸(`$C019`) = 몬스터 세트. 1장은 자원 0x18(rel 0x612),
종장은 월드맵 진입 때 `$C144` 비트0 이면 `LDA #$4C / STA $C019`(`$6A+0x10DA`) — 자원 0x4C = rel 0x68A = 탑승 용 타일 섹터 맨 앞 두 칸 = 흰 용.
그래서 종장만 용이 용으로 보이고 1~5장은 몬스터 모양(또는 잡음)이다.

── 고침 ──
· 피리를 불어 접근 이동을 시작하는 루틴(`$B59B~` — `$C01A`≠0, 둘째 칸 위치 = 플레이어 ± `$F1/$0F` 칸, `JSR $6F7D` 로 이동 스크립트 `$B601`)의 끝(`$B5F4`)에서 `$C019` 를 0x4C 로 바꿔 로더(`$69C7` — 플레이어 칸 갱신 없이 목록만 읽는 꼬리)를 부른다 → 용 타일이 0x7C00 에 올라온다.
  원래 값은 `$247C`(+ 표시 `$247D`)에 두고, 이미 0x4C(종장)면 아무것도 안 한다.
· 내리는 자리(`$A2E9` — `STZ $C200 / STZ $C012` 직후 원판이 `JSR $6971` 로 목록을 다시 읽는다)에서 `$C019` 를 되돌린다 → 같은 로더 호출이 몬스터 세트를 다시 올린다.
  내리기 전에 다른 맵으로 가면 맵 입장이 목록을 새로 쓰고 캐시 비교로 알아서 다시 읽는다.
· 🔴 코드는 **뱅크 0x76 꼬리 `$BC00~`**(`STUB_OFF` — 블록이 풀리는 고정 뱅크, 원본 FF 1041B)에 둔다: 블록 0 은 풀린 블록 한계 6656B 에 번역분(6624B)이 이미 닿아 꼬리에 못 붙이고,
  먼 호출(`$4FD8`)은 MPR3·4 를 갈아 치워 `$81A8`·`$69C7` 을 못 부른다. 이 자리는 씬이 열려 있는 내내 MPR5 로 보여 그냥 `JSR` 이 된다(블록 길이 ≤ 6656 < 0x1C00 이라 풀 때 안 덮인다,
  `$BA00~$BBEF` 는 구역 작업표). 블록 0 은 24개 컨테이너에 바이트까지 같고 자리 둘만 같은 길이로 바꾼다. `$247C/D` 는 훅 페이로드 안 빈 칸(`$247A·B` 디버그 키 뒤 ~ `$2480` 조사표 앞).
· 1장 접근 숨김(`$985B` 루프가 둘째 칸부터 종류 0x38~0x3F 를 타이머로 숨긴다)은 시작 포인터 한 바이트(`$9861 LDA #$08` → `#$10`, 둘째 칸 건너뛰기)로 접근 용만 뺀다
  — 발견의 피리 전 필드 몬스터 숨김(셋째 칸부터)은 그대로. 표 끝 한 칸을 더 읽지만 빈 칸이라 무해.
"""

import hook

BASE = 0xA000  # 블록이 걸리는 MPR5 창
STUB_BANK, STUB_OFF = 0x76, 0x1C00  # 블록이 풀리는 고정 뱅크의 꼬리(원본 FF) — `$BC00`
STUB_LEN_MAX = 0x1FF0 - STUB_OFF
SAVE = 0x247C  # 원래 `$C019`
DRAGONPAL = BASE + STUB_OFF + 0x180  # 용 팔레트 32B (자료)
PAL_SHADOW = 0x29A9  # 스프라이트 팔레트 10 의 RAM 그림자 32B(실측 11-25: 3·4·1장 상태에서 VCE 값과 바이트 일치). 🔴 VCE 는 읽기가 FF 라 되읽어 저장할 수 없다
SAVE_FLAG = 0x247D  # 0 이 아니면 SAVE 가 유효
LIST_SLOT = 0xC019  # 타일 자원 목록 일곱째 칸 = 지역 몬스터 세트
DRAGON_RES = 0x4C  # 자원 번호 — rel 0x68A(탑승 용 타일 섹터)
# 용 팔레트(종장 월드맵 실측 — 스프라이트 팔레트 10 = VCE 색 0x1A0~0x1AF, 마스터 11-25 「3장 분홍」): 접근 시작에 이걸 쓰고 내림에 원래 값(`SAVEPAL`)을 되돌린다
PAL_IDX = 10
DRAGON_PAL = (0x000, 0x0CD, 0x157, 0x1DF, 0x010, 0x068, 0x0B8, 0x168, 0x1F9, 0x084, 0x003, 0x0D8, 0x000, 0x000, 0x000, 0x1FF)
DATA_OFF = 0x180  # 스텁 자리 안 자료 시작(뱅크 0x76 +0x1D00): 용 팔레트 32B
VCE_ADDR_LO, VCE_ADDR_HI, VCE_DATA_LO, VCE_DATA_HI = 0x0402, 0x0403, 0x0404, 0x0405
LOADER = 0x69C7  # 목록 읽기 꼬리(플레이어 칸 갱신 건너뜀) — 뱅크 0x6A, `JSR` 로 부른다(끝이 `JMP $6288` → RTS)
SET_KIND = 0x81A8  # `STA ($10),Y=1`
SET_FLAG7 = 0x81BC  # `STA ($10),Y=7`

# 자리 둘(블록 0 안 원본 바이트 — 블록 안에서 정확히 한 번씩 나와야 한다)
SITE_START_CTX = bytes.fromhex("8d0bc2" "a901" "85fa" "a9b6" "85fb" "207d6f")  # STA $C20B / … / JSR $6F7D — 접근 시작 루틴(`$B59B~`)만의 앞 문맥(내림 `$A309` 쪽은 `A9 03` 이 낀다)
SITE_START_OLD = bytes.fromhex("9c1acf" "38" "60")  # STZ $CF1A / SEC / RTS (5B, `$B5F4`) — 접근 시작 루틴의 끝
SITE_MUSIC_OLD = bytes.fromhex("a907" "85f8" "8d0dc0" "202564")  # LDA #$07 / STA $F8 / STA $C00D / JSR $6425 (10B, `$A2DF`) — 내림에 평화로운 곡(종장 고정값 7)을 튼다
COUNT_SAVE = 0x247F  # 접근 시작 때의 엔티티 수 `$C011`(0 = 없음) — 비행 중 몬스터는 숨기고(0x40) 멈춰 있다가 내림 뒤 용이 떠날 때(`$A0D4`) 수를 되돌리고 숨김을 푼다
SITE_PRE_OLD = bytes.fromhex("207981")  # JSR $8179 (3B, `$B5B2`)
SITE_COUNT_OLD = bytes.fromhex("a901" "8d11c0")  # LDA #$01 / STA $C011 (5B, `$A0D4` — 용 개체가 떠나며 엔티티 수를 1 로)
MUSIC_SAVE = 0x247E  # 접근 시작 때의 `$C00D`(그 맵의 필드 곡 번호)
SITE_LAND_OLD = bytes.fromhex("9c00c2" "9c12c0")  # STZ $C200 / STZ $C012 (6B, `$A2E9`)

# 뱅크 0x6B(1장 월드맵 숨김 루프) — 시작 포인터 하위 바이트(`$9861 LDA #$08 / STA $10`)
HIDE_BANK, HIDE_OFF = 0x6B, 0x1862
HIDE_OLD, HIDE_NEW = 0x08, 0x10


def _pal_io(a, read_to=None, write_from=None):
    """VCE 색 표 `PAL_IDX` 팔레트(16색)를 저장 칸으로 읽거나 `write_from` 에서 쓴다 — 주소 두 바이트를 먼저 정하고 `$0404/5` 를 16번(주소는 높은 바이트 뒤 자동 증가)."""
    op = a.op
    base = 0x100 + 16 * PAL_IDX
    op("LDA", "imm", base & 0xFF)
    op("STA", "abs", VCE_ADDR_LO)
    op("LDA", "imm", base >> 8)
    op("STA", "abs", VCE_ADDR_HI)
    op("LDX", "imm", 0)
    lab = f"p{len(a.labels)}"
    a.label(lab)
    if read_to is not None:
        op("LDA", "abs", VCE_DATA_LO)
        op("STA", "absx", read_to)
        op("INX")
        op("LDA", "abs", VCE_DATA_HI)
        op("STA", "absx", read_to)
        op("INX")
    else:
        op("LDA", "absx", write_from)
        op("STA", "abs", VCE_DATA_LO)
        op("INX")
        op("LDA", "absx", write_from)
        op("STA", "abs", VCE_DATA_HI)
        op("INX")
    op("CPX", "imm", 32)
    op("BNE", "rel", lab)


def _hide_loop(a, hide):
    """엔티티 표 셋째 칸($C210)부터 30칸 — 종류 0x38~0x3F(몬스터 계열)의 플래그 비트6(0x40, `$985B` 루프와 같은 숨김)을 켜거나 끈다."""
    op = a.op
    lab = f"h{len(a.labels)}"
    skip = lab + "s"
    op("LDX", "imm", 0)
    a.label(lab)
    op("LDA", "absx", 0xC211)
    op("AND", "imm", 0xF8)
    op("CMP", "imm", 0x38)
    op("BNE", "rel", skip)
    op("LDA", "absx", 0xC210)
    if hide:
        op("ORA", "imm", 0x40)
    else:
        op("AND", "imm", 0xBF)
    op("STA", "absx", 0xC210)
    a.label(skip)
    op("TXA")
    op("CLC")
    op("ADC", "imm", 8)
    op("TAX")
    op("CPX", "imm", 0xF0)
    op("BNE", "rel", lab)


def _stub(org: int):
    a = hook.Asm(org)
    op = a.op
    a.label("start")
    op("STZ", "abs", 0xCF1A)  # 원래 자리의 첫 명령(끝의 SEC·RTS 는 호출 자리에 남는다 — 아래 `patch_block0`)
    op("LDA", "abs", LIST_SLOT)
    op("CMP", "imm", DRAGON_RES)
    op("BEQ", "rel", "sdone")  # 종장 — 이미 용 타일
    op("STA", "abs", SAVE)
    op("LDA", "imm", 1)
    op("STA", "abs", SAVE_FLAG)
    op("LDA", "abs", 0xC00D)  # 필드 곡 번호도 저장 — 내림 때 되튼다(원판은 종장 고정 7)
    op("STA", "abs", MUSIC_SAVE)
    op("LDA", "imm", DRAGON_RES)
    op("STA", "abs", LIST_SLOT)
    _pal_io(a, write_from=DRAGONPAL)  # 용 팔레트를 쓴다
    for z in (0x10, 0x11, 0x12, 0x13, 0xFE, 0xFF):  # 로더(`$6288`)가 `$12/$13/$FE/$FF` 를 쓴다 — 블록 코드가 이어 쓰는 영 페이지를 지킨다
        op("LDA", "zp", z)
        op("PHA")
    op("JSR", "abs", LOADER)
    for z in (0xFF, 0xFE, 0x13, 0x12, 0x11, 0x10):
        op("PLA")
        op("STA", "zp", z)
    a.label("sdone")
    op("RTS")  # 호출 자리가 `JSR 이 루틴 / SEC / RTS` — 캐리는 자리에서 켠다
    a.label("pre")  # 접근 시작 루틴(`$B5B2`)의 `JSR $8179`(엔티티 수를 `$A006`=2 로 줄이는 루틴) 앞 — 수를 저장하고 몬스터 칸(둘째 칸 뒤)을 숨긴 다음 원래 호출
    op("LDA", "abs", 0xC011)
    op("CMP", "imm", 3)
    op("BCC", "rel", "nohide")
    op("STA", "abs", COUNT_SAVE)
    _hide_loop(a, hide=True)
    a.label("nohide")
    op("JMP", "abs", 0x8179)
    a.label("music")  # 내림 자리의 10B 를 대신한다 — 저장값이 있으면(1~5장) 그 곡, 없으면(종장) 원래대로 7
    op("LDA", "abs", SAVE_FLAG)
    op("BEQ", "rel", "m7")
    op("LDA", "abs", MUSIC_SAVE)
    op("BRA", "rel", "mgo")
    a.label("m7")
    op("LDA", "imm", 7)
    a.label("mgo")
    op("STA", "zp", 0xF8)
    op("STA", "abs", 0xC00D)
    op("JSR", "abs", 0x6425)
    op("RTS")
    a.label("count")  # `$A0D4` 의 `LDA #$01 / STA $C011` 자리 — 용 개체가 화면 밖으로 떠나 사라진 뒤: 타일·팔레트를 되돌리고 저장한 수·몬스터 숨김도 푼다
    op("LDA", "abs", SAVE_FLAG)
    op("BEQ", "rel", "cnt")
    op("STZ", "abs", SAVE_FLAG)
    op("LDA", "abs", SAVE)
    op("STA", "abs", LIST_SLOT)
    _pal_io(a, write_from=PAL_SHADOW)  # 팔레트 10 복원 — 엔진의 RAM 그림자(`$29A9`)에서
    for z in (0x10, 0x11, 0x12, 0x13, 0xFE, 0xFF):
        op("LDA", "zp", z)
        op("PHA")
    op("JSR", "abs", LOADER)  # 몬스터 세트 타일을 다시 올린다
    for z in (0xFF, 0xFE, 0x13, 0x12, 0x11, 0x10):
        op("PLA")
        op("STA", "zp", z)
    a.label("cnt")
    op("LDA", "abs", COUNT_SAVE)
    op("BEQ", "rel", "c0")
    _hide_loop(a, hide=False)
    op("LDA", "abs", COUNT_SAVE)
    op("STZ", "abs", COUNT_SAVE)
    op("STA", "abs", 0xC011)
    op("RTS")
    a.label("c0")
    op("LDA", "imm", 1)
    op("STA", "abs", 0xC011)
    op("RTS")
    a.label("land")
    op("STZ", "abs", 0xC200)  # 원래 자리의 두 명령 — 타일·팔레트 복원은 용이 떠난 뒤(`count`)로 미룬다(떠나는 용이 몬스터 모양으로 보이던 것, 마스터 11-26)
    op("STZ", "abs", 0xC012)
    op("RTS")
    return a


def stub_code() -> tuple[bytes, int, int, int, int, int]:
    """(코드, 접근 시작 주소, 내림 주소)"""
    a = _stub(BASE + STUB_OFF)
    code = a.bytes()
    assert len(code) <= DATA_OFF, len(code)
    code += b"\xff" * (DATA_OFF - len(code))
    for w in DRAGON_PAL:
        code += w.to_bytes(2, "little")
    assert len(code) <= STUB_LEN_MAX, len(code)
    return code, a.labels["start"], a.labels["land"], a.labels["music"], a.labels["count"], a.labels["pre"]


def patch_block0(blk: bytes) -> bytes:
    """블록 0 의 두 자리를 `JSR 스텁` 으로 바꾼다(같은 길이 — 블록은 안 자란다)."""
    ctx = SITE_START_CTX + SITE_START_OLD
    for old, name in ((ctx, "접근 시작"), (SITE_LAND_OLD, "내림"), (SITE_MUSIC_OLD, "내림 음악"), (SITE_COUNT_OLD, "엔티티 수"), (SITE_PRE_OLD, "수 줄이기 앞")):
        if blk.count(old) != 1:
            raise ValueError(f"flute_tiles: 블록 0 의 {name} 자리가 {blk.count(old)}번 나온다(정확히 1번이어야)")
    _code, start, land, music, count, pre = stub_code()
    jsr = lambda t: bytes([0x20, t & 0xFF, t >> 8])  # noqa: E731
    out = blk.replace(ctx, SITE_START_CTX + jsr(start) + b"\x38\x60")  # JSR 스텁 / SEC / RTS — 원래 자리와 같은 5B
    out = out.replace(SITE_PRE_OLD, jsr(pre))
    out = out.replace(SITE_COUNT_OLD, jsr(count) + b"\xea\xea")
    out = out.replace(SITE_MUSIC_OLD, jsr(music) + b"\xea" * (len(SITE_MUSIC_OLD) - 3))
    return out.replace(SITE_LAND_OLD, jsr(land) + b"\xea" * (len(SITE_LAND_OLD) - 3))


def stub_patch(main_off):
    """뱅크 0x76 꼬리에 스텁 코드를 쓴다 — (라벨, rel, 오프셋, 기대 FF, 새 바이트)."""
    code, _s, _l, _m, _c, _p = stub_code()
    return ("flute stub code", *main_off(STUB_BANK, STUB_OFF), b"\xff" * len(code), code)


def hide_patch(main_off):
    """1장 접근 숨김 — (라벨, rel, 오프셋, 기대, 새 바이트) 한 건. `main_off` = build 의 `_main` 함수."""
    return ("flute 1장 접근 용 숨김 제외", *main_off(HIDE_BANK, HIDE_OFF), bytes([HIDE_OLD]), bytes([HIDE_NEW]))


if __name__ == "__main__":
    c, st, ld, mu, ct, pr = stub_code()
    print(len(c), hex(st), hex(ld), hex(mu), hex(ct), hex(pr))
