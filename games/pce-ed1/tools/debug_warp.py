"""디버그 메뉴 「W」 워프 — **원판 워프의 날개 목록을 그대로 쓰고, 방문 깃발만 무시한다**(마스터 11-16 「디버그 워프 전마을 방문상태로 진행해줘」 — 11-09 에 우리가 만든 장별 대표 입구 목록을 대체).

원판 W 는 핸들러가 빈 `RTS`(`$6534`)다(`status.md` 디버그 절). 그 자리에서 워프의 날개(아이템 78, 방문한 마을 목록) 사용 경로를 직접 부른다:
  · 날개 효과(뱅크 0x6E/0x6F — 먼 호출 n=6 으로 `$92EE`)의 `JSR $5CD5; JSR $855B(목록) ; BCC 워프` — 필드 `$C00F ≥ 0x30` 검사(던전에선 거부)는 `$92E4` 에 있어 **건너뛴다**.
  · 목록 빌더(뱅크 0x6F `$85FD~`)는 장소 번호 idx 0..0x3F 마다 방문 비트(`$C178~$C17F`, 비트 = 0x3C0 + idx)를 보고 켜진 것만 `$CF43` 배열에 모은다.
    `$8621`(`BEQ` — 꺼졌으면 건너뜀) · `$8623`(`LDA $FE`)를 `JSR hook; NOP` 으로 바꾼다(훅이 `LDA $FE` 까지 대신한다). 훅(뱅크 0x6F 꼬리 FF 구역)은 **W 모드 표시**(`$3E63=$A5` · `$3E64=$5A` — 두 바이트 암호라 부팅 쓰레기에 안 걸린다)가 있으면
    idx 1~49 중 이름 있는 36곳을 켜진 것으로 본다(이름 없는 번호 — idx 0 · 0x1C~0x1F · 0x27~0x2F 는 원판 목록에서도 빈 줄이고 방문 깃발이 안 서는 빈 번호 · 50 이상은 지명 표 밖). idx 0x3F 에서 표시를 스스로 지운다 — 빌더는 목록을 열 때 한 번만 읽으니 모달 목록이 끝나기 전에 풀려도 된다(워프하면 돌아오지 않으므로 핸들러에서 지울 수 없다).
  · **진행 깃발(`$C178~$C17F`)은 쓰지 않는다** — 훅은 읽기 결과만 바꾼다.
  · 취소하면 디버그 창을 `$6541` 로 다시 그리고 돌아간다.
옛 W(장별 대표 입구 목록 + 디스크립터 풀 섹터 + BIOS CD_READ)는 이 방식으로 **걷어냈다**(devlog 11-16). 디버그 「I」 목록(`debug_item_list`)이 이 모듈의 상수를 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import debug_item
import hook

BANK_CODE = 0x70
POOL_SECTORS = 1

CH, IDX = (
    0x37AD,
    0x37AC,
)  # 디버그 화면 상태 바이트 곁(`$37A5~$37AB` 는 화면이 지우고, `$37AC` 는 아이템 고르기가 쓴다)
PAD = 0x222D  # 새로 눌린 단추(비트 0 = I · 1 = II · 2 = SELECT · 4 = 위 · 5 = 오른쪽 · 6 = 아래 · 7 = 왼쪽)
BUF = 0x3E40  # 줄 버퍼(32B 안) — 아랫줄은 18B+종결자라 아이템 이름 버퍼(`$CFF1`, 15B)에 쓰면 `$D000~` 로 넘친다. 베이스 RAM `$3E40`(스텁 `$3E00~$3E1F` · 디스크립터 `$3F00` 사이)
DRAW = 0x5BB1
WAIT = 0x5BCD
TILE_RESET = 0x5B9C
TOP, ROW, ITEM = (
    0x3E60,
    0x3E61,
    0x3E62,
)  # 목록창 — 맨 윗줄 항목 · 그리는 줄 · 지금 그리는 항목(`BUF` 곁 빈 RAM)
BAT_LIST = 0x0107  # 목록창 첫 줄(디버그 창의 제목 줄 — 줄마다 +0x80)
LIST_ROWS = 8
FAR = 0x4FD8  # 먼 호출(`JSR $4FD8 / 뱅크 번호(0x68+n) / lo hi`) — 돌아오면 뱅크를 되돌린다
DBG_DRAW = 0x6541  # 뱅크 0x6E — 디버그 창 전체 그리기(제목 · 행 · 값)
BAT_NAME = 0x0387  # (옛) W 줄 이름 칸
BAT_INFO = 0x0407  # 「I」 줄 자리
STUB_AT = 0x3E00  # 워프 직전 RAM 스텁 · 디스크립터 사본(`$3F00`)
DESC_AT = 0x3F00
HOOK_DRAW_OFF = 0x04D4  # 뱅크 0x6E — 디버그 창 처음 그리기(`$64D4`)
ORIG_E = 0x621B  # 원래 E 행(EP +100) 처리 — 뱅크 0x70

TABLE_W = 0x0535 + 2 * 4  # 뱅크 0x6E 디버그 행 표 W 칸
STUB_E_ARG = 0x062A  # 뱅크 0x6E `$662A` — E 행 스텁 `JSR $4FD8 / 08 / <lo hi> / RTS` 의 호출 대상
E_STUB = 0x6626
ROW_W = 4
ROW_E = 3
BLOCK_SCENE = 41  # 베르가 사령관 처치 뒤 맵(`$C009` = 씬 번호) — 원판 날개도 여기서 멈춘다(11-17: 입구·마을 맵 둘 다, 월드맵은 `$C009`=0 이라 정상). W 를 막는다
SCENE_VAR = 0xC009
CUE_DENY = 0x27  # 원판 아이템 메뉴가 사용 못 하는 아이템을 골랐을 때(`$84DE` `LDA #$27 / JSR $57B1`)
SOUND = 0x57B1
RED = 2  # 글자색(`$8A`) 빨강 — 사용 불가 아이템과 같은 색
BAT_W = 0x0388  # 디버그 창 「W」 라벨 BAT(라벨 줄 `$0188` + 줄당 0x80 × 4 — 옛 W 줄 이름 칸 `BAT_NAME` 0x0387 과 한 칸 차이)


POOL_SECTORS = 0  # 옛 디스크립터 풀 섹터는 걷어냈다(`build` 가 트랙 끝 예약에 쓴다)
WMODE = 0x3E63  # W 모드 암호 — `$3E63=$A5`, `$3E64=$5A`(`BUF`/`TOP` 곁 빈 RAM)
WMODE_KEY = (0xA5, 0x5A)
WING_FAR_N = 6  # 먼 호출 n — 뱅크 0x6E(`$6000`) + 0x6F(`$8000`)
WING_USE = 0x92EE  # 날개 사용 경로 — 필드 `$C00F` 검사 뒤(`JSR $5CD5; JSR $855B; BCC 워프`)
HOOK_BANK = 0x6F
HOOK_ORG = 0x9F3C  # 뱅크 0x6F 끝 FF 196B(오프셋 0x1F3C~)의 앞 — `$8000` 창
HOOK_SITE_OFF = 0x0621  # 뱅크 0x6F 오프셋 — `BEQ $862D; LDA $FE`(`F0 0A A5 FE`, 앞 `82` 는 먼 호출 인자 마지막 바이트)
HOOK_SITE_OLD = bytes.fromhex("f00aa5fe")
HOOK_SKIP_TO = 0x862D  # 꺼진 장소를 건너뛰는 자리(`INC $FE` 증가부)
LAST_IDX = 0x3F
PLACES = 64  # 날개 목록 번호 범위(idx 0 = 빈 칸 · 마지막 0x3F) — 11-21 전엔 50 이었다(지명 표 항목 수). 50~63(구엔의탑·시련의동굴·왕가의묘·국경의동굴·용의알·바람의탑·방풍의동굴·늑대의입·수정의탑·폐광·니르기드·기라의길·바젤의탑·바니스성)도 장 표로 거른다
HOOK_CODE_ROOM = 100  # 훅 코드 자리(바이트, 코드 길이와 같게 — 뒤 훅 구역 꼬리를 W 목록 스텁에 내주려고 6B 줄였다) — 뒤에 마스크·표
TMP = 0x3E65  # 훅 작업 바이트(`WMODE` 곁 빈 RAM)
CHAPTER = 0x6B  # 지금 불러 둔 장(0~5 — 장 교체 루틴이 `$6C7B` 에서 세운다. `$C1B6`(세이브 장 번호)는 불러 온 직후엔 0 이라 못 쓴다)
MASK_AT = HOOK_ORG + HOOK_CODE_ROOM  # 비트 마스크 8B(01 02 04 … 80)
TABLE_AT = MASK_AT + 8  # 장 × 8B — 비트 idx 가 서 있으면 그 장에서 도착하는 곳
# 장(`$6B`: 0=1장 … 5=종장)별로 날개 목록에서 골라 이동했을 때 실제로 도착하는 장소 번호 — 헤드리스 전수 실측(devlog 11-16). 그 밖은 목적지 맵이 그 장의 컨테이너에 없어 검은 화면이 된다(원판 날개도 같다).
REACH = {
    0: (
        1,
        2,
        3,
        4,
        5,
        38,
        48,
    ),  # 엘아스타 · 루디아 · 크루즈마을 · 베르가광산 · 네리아항구 · 루디아성문 · 곶의동굴 (50~54 는 1500프레임 기다려도 검은 화면 — 11-21 실측)
    1: (1, 2, 3, 4, 5, 6, 7, 8, 9, 32, 33, 34, 35, 38, 48, 49, 50, 51),  # + 구엔의탑(50) · 시련의동굴(51 — 도착까지 300프레임 넘게 걸린다)
    2: (1, 10, 11, 12, 13, 14, 15, 33, 34, 35, 36, 37, 48, 49, 52, 53),  # + 왕가의묘(52) · 국경의동굴(53)
    3: (1, 48, 53, 56),  # 4장은 엘아스타·곶의동굴(두 지역 세이브로 확인) + 국경의동굴(53) · 방풍의동굴(56)
    4: (1, 20, 21, 22, 23, 24, 48, 52, 57, 58),  # + 왕가의묘(52) · 늑대의입(57) · 수정의탑(58)
    5: (1, 21, 22, 25, 26, 27, 48, 52, 57, 58, 59, 60, 61, 62, 63),  # + 왕가의묘 · 늑대의입 · 수정의탑 · 폐광(59) · 니르기드(60) · 기라의길(61) · 바젤의탑(62) · 바니스성(63)
}
# 50~63 은 11-21 실측: 장마다 W 목록(방문 깃발 전부 켠 상태)에서 번호를 골라 1500프레임 기다린 뒤 **HUD 지명 = 목록 이름 + 정상 맵**이면 도착으로 쳤다(검은 화면 + 지명 빔 = 못 가는 곳 — 장 컨테이너에 그 맵이 없다). 6장 × 14곳 전수.
# 표에서 뺀 곳: ① 용의알(54) — 마스터 판정 「워프의 날개에 등록되는 지명이 아니다」(도착하면 어두운 방에 HUD 「유혈의동굴」이 뜬다 — 이름이 안 맞는 곳은 디버그로 가면 진행이 꼬인다). ② 바람의탑(55) — 어느 장에서도 도착 안 함.
# 방문 깃발이 서 있으면 「날개가 보여 주는 곳」으로 목록에 오를 수는 있다(앞 장 마을과 같다) — 그건 원판 동작이다.


def reach_table() -> bytes:
    out = bytearray(48)
    for ch, idxs in REACH.items():
        for i in idxs:
            assert 1 <= i < PLACES, i
            out[ch * 8 + (i >> 3)] |= 1 << (i & 7)
    return bytes(out)


def hook_code() -> bytes:
    a = hook.Asm(HOOK_ORG)
    op = a.op
    op("PHP")  # 호출 시점 플래그 — Z=1 이면 방문 비트가 꺼진 것(원래 BEQ 가 보던 값)
    op("LDA", "abs", WMODE)
    op("CMP", "imm", WMODE_KEY[0])
    op("BNE", "rel", "plain")
    op("LDA", "abs", WMODE + 1)
    op("CMP", "imm", WMODE_KEY[1])
    op("BNE", "rel", "plain")
    op("LDA", "zp", 0xFE)
    op("CMP", "imm", LAST_IDX)
    op("BNE", "rel", "w1")
    op("STZ", "abs", WMODE)  # 마지막 idx — W 모드를 푼다(11-21: 이 idx 도 아래 장 표로 판정한다 — 바니스성(63)이 종장에서 도착한다)
    a.label("w1")
    op("LDA", "zp", 0xFE)
    op("BEQ", "rel", "plain")
    op("CMP", "imm", PLACES)
    op("BCS", "rel", "plain")
    # 장별 도착 표 — 지금 장(`$C1B6`)에서 도착하는 곳만 켜진 것으로 본다(없는 곳은 방문 깃발과 무관하게 건너뜀)
    op("PHX")
    op("PHY")
    op("LSR")
    op("LSR")
    op("LSR")
    op("STA", "abs", TMP)  # 바이트 번호 = idx >> 3
    op("LDA", "zp", CHAPTER)
    op("ASL")
    op("ASL")
    op("ASL")
    op("CLC")
    op("ADC", "abs", TMP)
    op("TAX")  # X = 장 × 8 + idx >> 3
    op("LDA", "zp", 0xFE)
    op("AND", "imm", 7)
    op("TAY")
    op("LDA", "absy", MASK_AT)
    op("STA", "abs", TMP)
    op("LDA", "absx", TABLE_AT)
    op("AND", "abs", TMP)
    op("BEQ", "rel", "no")
    op("PLY")
    op("PLX")
    op("BRA", "rel", "yes")
    a.label("no")  # 이 장 표에 없는 곳 — 원판 날개가 보여 주는 것(방문 비트가 서 있음)이면 그대로 올린다(마스터 11-18 「3장 날개에는 앞 장 방문 마을이 다 나온다」)
    op("PLY")
    op("PLX")
    op("PLP")  # 호출 시점 플래그 복원 — Z=1 이면 방문 비트가 꺼진 것
    op("BEQ", "rel", "skip")
    op("BRA", "rel", "cont")
    a.label("yes")
    op("PLA")  # 켜진 것으로 본다(저장한 플래그 버림)
    op("BRA", "rel", "cont")
    a.label("plain")
    op("PLP")
    op("BEQ", "rel", "skip")
    a.label("cont")  # 원래 다음 명령 `LDA $FE` 를 대신한다(A = idx)
    op("LDA", "zp", 0xFE)
    op("RTS")
    a.label("skip")  # 돌아갈 주소를 `HOOK_SKIP_TO` 로 바꾼다
    op("PLA")
    op("PLA")
    op("LDA", "imm", (HOOK_SKIP_TO - 1) >> 8)
    op("PHA")
    op("LDA", "imm", (HOOK_SKIP_TO - 1) & 0xFF)
    op("PHA")
    op("RTS")
    return a.bytes()


def hook_site_new() -> bytes:
    return b"\x20" + HOOK_ORG.to_bytes(2, "little") + b"\xea"


def code(org: int, wd: int | None = None) -> "hook.Asm":
    """분기기 — W 행이면 날개 목록, 아니면 원래 E 행 처리. `wd` = 라벨 그리기(`wdraw`) 주소(앞으로 점프라 두 번 조립)."""
    if wd is None:
        wd = code(org, org).labels["wdraw"]
    a = hook.Asm(org)
    op = a.op
    a.label("disp")
    op("LDA", "abs", 0x37A5)
    op("CMP", "imm", ROW_W)
    op("BEQ", "rel", "wmain")
    op("CMP", "imm", ROW_E)
    op("BNE", "rel", "redraw")
    op("JMP", "abs", ORIG_E)
    # 🔴 P·M·I 행 — 원판은 값을 뒤집은 뒤 `$64E0` 의 `JSR $6541`(창 다시 그리기)로 돌아온다(마스터 11-18 「P M 이 ON 으로 안 바뀌네」). 그 자리를 스텁(`$6626`)으로 바꿨으니 여기서 창 다시 그리기 + 「W」 빨강을 한다.
    a.label("redraw")
    a.out += bytes([0x20, FAR & 0xFF, FAR >> 8, 6, DBG_DRAW & 0xFF, DBG_DRAW >> 8])
    op("JSR", "abs", wd)
    op("RTS")
    a.label("wmain")
    op("LDA", "abs", SCENE_VAR)  # 이 맵에선 원판 워프가 멈춘다 — 무반응(라벨은 빨강)
    op("CMP", "imm", BLOCK_SCENE)
    op("BNE", "rel", "wgo")
    op("LDA", "imm", CUE_DENY)  # 사용 불가 아이템을 골랐을 때와 같은 효과음(원판 `$84DE` — 뱅크 0x6F)
    op("JSR", "abs", SOUND)
    op("RTS")
    a.label("wgo")
    op("LDA", "imm", WMODE_KEY[0])
    op("STA", "abs", WMODE)
    op("LDA", "imm", WMODE_KEY[1])
    op("STA", "abs", WMODE + 1)
    a.out += bytes([0x20, FAR & 0xFF, FAR >> 8, WING_FAR_N, WING_USE & 0xFF, WING_USE >> 8])
    op("STZ", "abs", WMODE)  # 취소로 돌아왔다 — 표시를 푼다(워프하면 여기 안 온다)
    a.out += bytes(
        [0x20, FAR & 0xFF, FAR >> 8, 6, DBG_DRAW & 0xFF, DBG_DRAW >> 8]
    )  # 디버그 창 전체를 다시 그린다
    op("JSR", "abs", wd)
    op("JSR", "abs", WAIT)
    op("RTS")
    # ── 「W」 라벨 빨강 — 막힌 맵(씬 41)에서만 디버그 창 맨 끝에 한 글자를 다시 그린다. 창을 그린 직후(`$64D4` 훅 · W 취소 · I 닫기)마다 부른다.
    a.label("wdraw")
    op("LDA", "abs", SCENE_VAR)
    op("CMP", "imm", BLOCK_SCENE)
    op("BNE", "rel", "wd_end")
    op(
        "LDA", "imm", 0x82
    )  # 원판 라벨은 전각 「Ｗ」(SJIS 8276) — 뱅크 0x77 +0x1FE3 의 줄 문자열(Ｐ Ｍ Ｇ Ｅ Ｗ Ｉ, 줄 사이 00)
    op("STA", "abs", BUF)
    op("LDA", "imm", 0x76)
    op("STA", "abs", BUF + 1)
    op("LDA", "imm", 0x06)
    op("STA", "abs", BUF + 2)
    op("LDA", "imm", RED)
    op("STA", "zp", 0x8A)
    op("LDA", "imm", BUF & 0xFF)
    op("STA", "zp", 0x10)
    op("LDA", "imm", BUF >> 8)
    op("STA", "zp", 0x11)
    op("LDA", "imm", BAT_W & 0xFF)
    op("STA", "zp", 0x12)
    op("LDA", "imm", BAT_W >> 8)
    op("STA", "zp", 0x13)
    op("JSR", "abs", DRAW)
    op("LDA", "imm", 7)
    op("STA", "zp", 0x8A)
    a.label("wd_end")
    op("RTS")
    return a


def assemble(pool_rel: int = 0):
    """(코드 시작 논리 주소, 코드 바이트, 풀 바이트(없음), 분기기 논리 주소) — 인터페이스는 옛 W 와 같게 둔다(`debug_item_list.layout`)."""
    org = layout()
    a = code(org)
    blob = a.bytes()
    assert org + len(blob) <= 0x8000, hex(org + len(blob))
    return org, blob, b"", a.labels["disp"]


def wdraw_addr() -> int:
    """「W」 라벨 빨강 루틴의 논리 주소(뱅크 0x70) — `debug_item_list` 가 I 닫기에서 부른다."""
    return code(layout()).labels["wdraw"]


def layout():
    start = debug_item.ORG + len(debug_item.code())
    return (start + 15) & ~15  # 뱅크 0x70 논리 주소


def pool_rel() -> int:
    import common

    return common.T2_LEN  # 풀 없음 — 예약 0


def patches(pool_rel: int = 0):
    """빌드 개입 목록 `(라벨, rel, 오프셋, 기대 바이트, 새 바이트)`."""
    import common

    org, blob, _pool, disp = assemble()
    rel6e = 34 + (0x6E - 0x68) * 4
    out = []

    def put(label, bank, off, old, new):
        pos = 0
        while pos < len(new):
            at = off + pos
            rel = 34 + (bank - 0x68) * 4 + at // common.USER
            o = at % common.USER
            n = min(len(new) - pos, common.USER - o)
            out.append((label, rel, o, old[pos : pos + n], new[pos : pos + n]))
            pos += n

    put("debug warp code", BANK_CODE, org - 0x6000, b"\xff" * len(blob), blob)
    hc = hook_code()
    assert len(hc) <= HOOK_CODE_ROOM, len(hc)
    hc = hc + b"\xff" * (HOOK_CODE_ROOM - len(hc)) + bytes(1 << i for i in range(8)) + reach_table()
    put("debug warp wing-list hook code", HOOK_BANK, HOOK_ORG - 0x8000, b"\xff" * len(hc), hc)
    put("debug warp wing-list hook site", HOOK_BANK, HOOK_SITE_OFF, HOOK_SITE_OLD, hook_site_new())
    # 디버그 창을 그리는 자리(`$64D4` — 처음 열 때와 P·M·I 행을 누른 뒤 `$64E0` 로 되돌아올 때 같은 자리) — 원래 `STZ $37A8~AB` 넷 + `JSR $6541`(15B): STZ 는 그대로 두고 `JSR` 만 스텁(`$6626` → `disp` → 창 그리기 + 라벨 빨강)으로
    out.append(
        (
            "debug warp label draw hook",
            rel6e + HOOK_DRAW_OFF // common.USER,
            HOOK_DRAW_OFF % common.USER,
            bytes.fromhex("9ca8379ca9379caa379cab37204165"),
            bytes.fromhex("9ca8379ca9379caa379cab37") + bytes([0x20, E_STUB & 0xFF, E_STUB >> 8]),  # STZ 넷은 그대로 · 마지막 `JSR $6541` → `JSR $6626`(스텁 → `disp` 가 다시 그리기 + 「W」 빨강). 되돌아오는 `$64E0` 도 같은 자리라 P·M·I 행이 다시 그려진다
        )
    )
    # 🔴 P·M 값(`$37A6`·`$37A7`)을 창을 열 때마다 지우지 않는다(마스터 11-18 「P M ON 으로 바꿔놓고 닫았다가 다시 열면 OFF 표시인데 기능은 ON… 열 때 항상 최신 상태가 나와야 해」). 원판 입구(`$64CB`)는
    #   `STZ $37A5~$37AB` 로 행 번호(`$37A5`)와 값 둘·화면 상태를 지운다 — 값 둘(`STZ $37A6`·`STZ $37A7`, 각 3B)만 NOP 으로 두면 다시 열었을 때 표시가 실제 값(`$37A6/7`)을 그대로 읽는다.
    #   표시와 효과가 같은 한 바이트라 어긋날 일이 없다(토글은 `EOR` 로 그 바이트를 뒤집는다).
    out.append(
        (
            "debug P/M keep value",
            rel6e + 0x04CE // common.USER,
            0x04CE % common.USER,
            bytes.fromhex("9ca6379ca737"),
            b"\xea" * 6,
        )
    )
    out.append(
        (
            "debug warp row table W",
            rel6e + TABLE_W // common.USER,
            TABLE_W % common.USER,
            (0x6534).to_bytes(2, "little"),
            E_STUB.to_bytes(2, "little"),
        )
    )
    out.append(
        (
            "debug warp E stub target",
            rel6e + STUB_E_ARG // common.USER,
            STUB_E_ARG % common.USER,
            ORIG_E.to_bytes(2, "little"),
            disp.to_bytes(2, "little"),
        )
    )
    return out


if __name__ == "__main__":
    org, blob, _pool, disp = assemble()
    print(
        f"W 핸들러 {len(blob)}B @0x70:${org:04X} · 분기기 ${disp:04X} · 훅 {len(hook_code())}B @0x6F:${HOOK_ORG:04X}"
    )
