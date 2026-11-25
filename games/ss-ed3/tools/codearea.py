"""코드 예약 칸 — 우리 스텁·표를 두는 **`KANJI12.FON` 의 안 쓰는 글리프 칸**(정본).

🔴 **왜 여기냐**(10-24 디버그 메뉴 되살리기): 종전엔 우리 코드(조사 훅 · 음성 자막 스텁 · 크레딧 렌더러 · 배너 껍데기 · 문자열 이전 칸)를 죽은 디버그 메뉴 코드 구역
(`/0.BIN` `0x06016080~0x0601A20C`)에 얹었다. 메뉴를 되살리면 그 구역이 원판 바이트여야 하므로 **우리 쪽을 옮겼다.** 쓸 수 있는 자리는 `0.BIN` 안엔 2KB 뿐이고,
`KANJI12.FON` 은 부팅 때 **LWRAM `0x2B6004` 에 통째로 올라온다**(실측: 글리프 283·377·7000·7807 의 RAM 위치) — 한글 배정(본·내린 판·크레딧)을 빼고도 남는
글리프 칸의 연속 구간 둘을 코드 자리로 예약한다. 글리프 읽기는 함수 하나(`0x0604119A`)가 하고 그 번호대가 안 읽힘을 실행 중 0회로 쟀다(`glyph_guard.py`).

⚠ **조용히 틀리는 자리 판정을 막는다** — 예약 칸에 글리프를 배정하면 빌드가 멈춘다(`check_reserved`). 예약은 이 파일이 정본이고 `font.free_slots()` 도 여기서 뺀다.
ⓘ 코드는 LWRAM 에서 돈다(SH-2 는 어디서든 실행). 칸은 슬롯(18B) 단위로 잡히므로 시작이 슬롯 경계 + 2B 일 수 있다 — 코드 자리는 4 정렬로 깎아 쓴다.
"""

FON_BASE = 0x002B6004  # `KANJI12.FON` 이 RAM 에 올라오는 자리
SLOT = 18
FON_SIZE = 7808 * SLOT

#   (시작 슬롯, 칸 수) — `hangul_map`·`lowered_map`·`credits_map`·`book_map` 배정과 겹치지 않는 연속 구간
RUN_A = (7231, 573)  # 10,314B
RUN_B = (6636, 479)  # 8,622B
#   🔴 준비 표지 — **폰트 파일의 맨 끝 글리프 칸**(7807)에 둔다. 부팅 중 폰트는 CD 에서 **앞에서부터 차례로** RAM 에 올라오는데 프레임 태스크는 그동안에도 돈다
#   (첫 구현은 SEGA 로고에서 먹통이었다 — 태스크가 아직 안 올라온 코드로 뛰었다). 표지가 마지막에 올라오므로 표지가 보이면 코드는 전부 올라와 있다.
RUN_C = (7807, 1)
READY_ADDR = FON_BASE + 7807 * SLOT + 2  # 4 정렬
READY_MAGIC = 0xC0DEC0DE
#   0.BIN 안 문 트램펄린 자리(40B) — 조사 훅 종성 표(`patch_josa_hook.TBL` 0x06076170, 490B) 바로 뒤 · 같은 「실행 중 RAM 에서 0」 구역
TRAMP = 0x06076360
TRAMP_ROOM = 0x40
RESERVED_SLOTS = (
    frozenset(range(RUN_A[0], RUN_A[0] + RUN_A[1]))
    | frozenset(range(RUN_B[0], RUN_B[0] + RUN_B[1]))
    | frozenset(range(RUN_C[0], RUN_C[0] + RUN_C[1]))
)
assert READY_ADDR % 4 == 0


def _align4(a):
    return a + (-a % 4)


def run_start(run):
    return _align4(FON_BASE + run[0] * SLOT)


def run_end(run):
    return FON_BASE + (run[0] + run[1]) * SLOT


#   ── 칸 배분 ──────────────────────────────────────────────────────────────
#   A: 크레딧 렌더러 + V20 표(코드 · 변수 · 글자 명령 · 표 = 8,166B)  — 표가 늘 여유를 남긴다
CRED = run_start(RUN_A)
CRED_END = run_end(RUN_A) & ~1
#   B: 나머지 — 조사 훅 · 음성 자막 스텁 · 배너 껍데기 둘 · 전역 프레임 시계 · 이전 문자열 칸
JOSA = run_start(RUN_B)  # 조사 훅(코드 + 접기 버퍼)
JOSA_ROOM = 704
SUB = JOSA + JOSA_ROOM  # 음성 자막 스텁(코드 + 변수 표)
SUB_ROOM = 1536
WRAP3 = SUB + SUB_ROOM  # 대사창 끝 공백 껍데기(`patch_ui_center`)
WRAP3_ROOM = 192
WRAP2 = WRAP3 + WRAP3_ROOM  # 배너 이름 글자 껍데기
WRAP2_ROOM = 512
RELOC = WRAP2 + WRAP2_ROOM  # 예산이 모자라 옮긴 시스템 문자열 칸(32B × RELOC_SLOTS)
RELOC_LEN = 32
RELOC_SLOTS = 4  # 11-15: 정본 4-17 존댓말 문구(익혔습니다·전수받았습니다·팔았습니다)가 제자리 예산을 넘어 칸을 셋 더했다(1 → 4)
GCLK = RELOC + RELOC_LEN * RELOC_SLOTS  # 전역 프레임 시계(16B, 쓴다)
GCLK_LEN = 16
BOOKH = GCLK + GCLK_LEN  # 서책 반각 전진 스텁(`patch_book_half` — 코드 + 풀)
BOOKH_ROOM = 64
VCHK = BOOKH + BOOKH_ROOM  # 확인용 롬(`voicecheck`) 스텁 — 제품 빌드엔 안 쓴다(예약 칸이 비어 있을 뿐)
VCHK_ROOM = 256
NAMEJ = VCHK + VCHK_ROOM  # 이름 뒤 조각 조사 훅(`patch_josa_hook.name_routine` — 코드 + 상수 + 표지 8B)
NAMEJ_ROOM = 640
NTBL = NAMEJ + NAMEJ_ROOM  # 조사 훅 종성 표(606B — 본 판 + 내린 판 슬롯). 종전 `0x06076170`(490B)은 트램펄린 자리와 부딪혀 옮겼다
NTBL_ROOM = 704
ASH = NTBL + NTBL_ROOM  # 대사창 반각 글리프를 한 행 올리는 껍데기 둘(`patch_ui_center`, 시험 롬 전용 — 켜지 않으면 안 쓴다)
ASH_ROOM = 64
B_END = ASH + ASH_ROOM
assert B_END <= run_end(RUN_B), (B_END, run_end(RUN_B))
assert all(x % 4 == 0 for x in (CRED, JOSA, SUB, WRAP3, WRAP2, GCLK, RELOC, BOOKH, VCHK, NAMEJ, NTBL, ASH))

#   ── 쓰기 길 — 패치 함수는 `/0.BIN` 바이트를 돌려주므로 폰트 쪽 쓰기는 여기 모았다가 빌드가 폰트에 얹는다
SIDE = []  # [(주소, bytes)]


def reset():
    SIDE.clear()


def in_font(addr, n=1):
    return FON_BASE <= addr and addr + n <= FON_BASE + FON_SIZE


def put(out, base, addr, blob):
    """`addr` 가 폰트 RAM 이면 SIDE 에, 아니면 `/0.BIN`(`out` · 적재 주소 `base`)에 쓴다."""
    if in_font(addr, len(blob)):
        SIDE.append((addr, bytes(blob)))
        return
    off = addr - base
    assert 0 <= off and off + len(blob) <= len(out), hex(addr)
    out[off : off + len(blob)] = blob


def apply(fon):
    """SIDE 의 쓰기를 폰트 바이트(`bytearray`)에 얹는다. **예약 칸 안**이어야 하고 서로 겹치면 멈춘다."""
    used = []
    for addr, blob in SIDE:
        off = addr - FON_BASE
        assert off + len(blob) <= len(fon), hex(addr)
        slots = range(off // SLOT, (off + len(blob) - 1) // SLOT + 1)
        bad = [s for s in slots if s not in RESERVED_SLOTS]
        assert not bad, f"예약 밖 글리프 칸 {bad[:3]} 에 코드를 쓴다 ({addr:#x})"
        for lo, hi in used:
            assert off + len(blob) <= lo or hi <= off, f"코드 칸이 겹친다 ({addr:#x})"
        used.append((off, off + len(blob)))
        fon[off : off + len(blob)] = blob
    return len(SIDE)


def check_reserved(*maps):
    """글리프 배정 정본(`hangul_map` 등)이 예약 칸에 앉지 않았나 — 앉았으면 이유 목록."""
    bad = []
    for name, slots in maps:
        hit = sorted(RESERVED_SLOTS & set(slots))
        if hit:
            bad.append(f"{name}: 예약 칸 {len(hit)} 개 (예 {hit[:3]})")
    return bad
