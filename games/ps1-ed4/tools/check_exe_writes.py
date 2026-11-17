"""실행파일 쓰기 감사 — 원판과 제품 실행파일의 **바뀐 바이트 전수**를 「선언한 쓰기 자리」와 대조한다(마스터 공지 11-08 「포인터 바이트 패턴 치환이 남의 데이터까지 고친다」 부류).

선언한 자리 = ① 글자 표·문자열 단위가 든 구역(`exetab.scan_tables` 청크 + 옮긴 새 자리 + 글리프 arena) ② 반각 훅·아이템 스텁 동굴 ③ `halfwidth.*_PATCH` 명령 목록 · 훅 `jal` 자리
④ 옮긴 표의 기준 상수 참조(`find_base_refs` 의 `lui`·`use` 워드). **그 밖에서 바뀐 워드가 있으면 실패** — 우연히 같은 바이트열이라 남의 코드·데이터가 고쳐진 것이다.
    python3 tools/check_exe_writes.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import board4
import common
import exetab
import font
import halfwidth
import hangul
import slots
import textenc
import uitext

H, T = common.EXE_HDR, common.EXE_TADDR
INLINE_WORDS = frozenset(
    {
        0x8003AA48,
        0x8003AA50,
        0x80041E1C,
        0x80041E24,  # 전리품 창 둘(열·x)
        0x8001F7A8,
        0x8001FE14,  # 세이브/로드 슬롯 창 열 11→14
        0x8001E920,  # 세이브/로드 정보 창 아이콘·레벨 열 6·7·9·10 → 9·10·12·13 (창을 넓힌 만큼, 마스터 11-11)
        0x8001E94C,
        0x8001E96C,
        0x8001E984,
        0x80029098,  # 시스템 하위 메뉴 열 7→6
        0x8003FA3C,  # 게시판 빈 줄 제거(board4.BLANK_ROW_PATCH)
        0x80016528,
        0x800165D0,
        0x800171C0,
        0x800179DC,
        0x80017D64,  # 반각·조사 훅 `jal` 자리
        0x800275E0,
        0x800275E8,  # 장비 후보 목록 창 열 8→9·줄 8 고정(11-07)
        0x8003F760,  # 수량 창 단위 「個」→「개」 코드(11-07)
        0x80049FE8,  # 정보상 소재지 창 열 7→11(11-07)
    }
)


def declared(orig):
    """(구역 목록 [(시작, 끝)], 워드 집합) — RAM 주소."""
    cm = textenc.charmap()
    ranges, words = [], set()
    for t in exetab.scan_tables(orig, cm):
        ranges.append((t["table"] - H + T, t["table"] - H + T + 2 * t["n"]))
        for lo, hi, _us in exetab.unit_chunks(orig, t["table"], t["base"], t["n"]):
            ranges.append((lo - H + T, hi - H + T))
    # 표 밖(닻) 문자열 — 제자리 고정 길이로 바뀐다(`uitext.sites` 의 `table=None`)
    for off, info in uitext.sites(orig).items():
        ranges.append((off - H + T, off - H + T + 2 * (len(info["codes"]) + 1)))
    x = bytearray(orig)
    uitext.apply(x, hangul.load())
    for dest in uitext.RELOC.values():
        ranges.append((dest - H + T, dest - H + T + 0x3000))
    for name in dir(halfwidth):
        v = getattr(halfwidth, name)
        if name.endswith("_PATCH") and isinstance(v, list):
            words.update(t[0] for t in v)
    for nm in ("ITEM_SITE_A", "ITEM_SITE_B", "ITEM_COPY_LUI", "ITEM_COPY_ADD"):
        words.add(getattr(halfwidth, nm))
    for tbl in uitext.RELOC:
        for r in exetab.find_base_refs(orig, tbl - H + T):
            words.update((T + r["lui"] * 4 - H, T + r["use"] * 4 - H))
    # 글리프 배열(코드 0~arena 끝) — 한글·반각 글리프를 굽고 arena 가 표 단위를 받는다
    a_lo, a_hi = slots.arena_range()
    base0 = a_lo - slots.ARENA[0] * font.GLYPH_BYTES
    ranges.append((base0 - H + T, a_hi - H + T))
    # `build_kr.exe_edit` 안 즉치 패치 + 게시판 빈 줄 제거 + 훅 `jal` 자리(원판 명령을 `jal 동굴` 로) — 각 자리는 원판 명령 대조 뒤에 쓴다
    words.update(INLINE_WORDS)
    ranges.append(
        (board4.QUESTS - H + T, board4.QUESTS - H + T + 8 * 125)
    )  # 의뢰 표(8B 항목 — 시작 색인|본문 슬롯 수, `board4.apply`)
    ranges += [
        (halfwidth.CAVE, halfwidth.CAVE + halfwidth.CAVE_SIZE),
        (halfwidth.CAVE2, halfwidth.CAVE2 + halfwidth.CAVE2_SIZE),
        (halfwidth.ITEM_STUBS, halfwidth.ITEM_STUBS + 0x600),
        (
            0x80010228,
            0x80010768 + 0x20,
        ),  # 옛 아이템 구조체(죽은 사본 — 새 자리 `ITEM_STRUCT` 로 옮김)
    ]
    return ranges, words


def audit(orig, new, extra_words=frozenset()):
    ranges, words = declared(orig)
    words |= set(extra_words)
    bad = []
    for i in range(0, len(orig) - H, 4):
        a = H + i
        if orig[a : a + 4] == new[a : a + 4]:
            continue
        ra = T + i
        if ra in words or any(lo <= ra < hi for lo, hi in ranges):
            continue
        bad.append((ra, orig[a : a + 4].hex(), new[a : a + 4].hex()))
    return bad


def main():
    orig = bytes(common.read_file(common.EXE_PATH))
    new = bytes(common.read_file(common.EXE_PATH, image=common.build_bin()))
    bad = audit(orig, new)
    print(f"실행파일 바뀐 워드 중 선언 밖 {len(bad)}곳")
    for ra, o, n in bad[:40]:
        print(f"  {ra:#010x}  {o} → {n}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
