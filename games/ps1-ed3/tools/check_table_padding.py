"""낱말 표 재삽입 검사 — **원본과 구운 이미지의 실행파일 표를 항목마다 맞대** 빈 칸·종결·별칭이 그대로인지 본다(관리자 10-24, sfc-ed2 사고).

배경(sfc-ed2): 몬스터 이름 군을 다시 쓰며 원판의 길이 0 패딩을 빠뜨렸고, 빈 슬롯이 **다음 군 이름을 읽어** 이벤트 전투에서 파티 상태가 깨져 멈췄다.
이 게임의 낱말 표는 `exetext.rebuild`(표 항목 = u16 오프셋)로 다시 쓴다 — 같은 부류의 사고(빈 항목이 내용을 얻거나, 종결이 바뀌거나, 같은 자리를 가리키던 항목이 갈라짐)를
**표 단위로 대조**한다. 대상 = 실행파일 전체 스캔으로 찾은 표(`exetext.scan_tables`) + 떨어진 표(`exetext.DETACHED`).

예외(자체 규칙·자체 게이트가 있는 구역 — 구조가 의도적으로 다르다):
 - 월드맵 장소 패널 표(`0x9B6FC`) — 제어 코드 열·가운데 스텁(`panel_structure_problems` · `check_panel`)
 - 시스템 설정·예/아니오·속도 목록(`0xA1160~0xA1258`) — 칸 폭에 맞춘 고정 칸 + 순차 스캔 목록(`build.YESNO` · `submenu_center` · `docs/devlog.md` 09-26)
 - 떨어진 표 `0x9D0F6` 은 **0 이 문자열 안의 빈 칸 글자**(`見 る` 사이)라 종결이 `0xFFFF`/`0x8000`↑ 뿐이다.

사용: `check_table_padding.py <구운 .bin>` — 이상 있으면 종료 코드 1.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import exetext as X
import textenc

DISC = "ed3"
EXE = "/ED3.EXE"
SKIP_TABLES = {0x9B6FC}  # 월드맵 패널
SKIP_STRINGS = (0xA1160, 0xA1258)  # 오프셋 범위(파일) — 이 안을 가리키는 항목은 건너뛴다
ZERO_IS_GLYPH = {0x9D0F6}  # 0 이 글자인 표
# 번호 아이템 「검사교본 N」(원문 「剣士教本」+0+「その１」) — 이름과 접미 사이 종결 0 이 전각 한 칸으로 그려져 틈이 넓어(마스터 11-08 「띄어쓰기는 반각」)
# 그 0 을 반각 공백 코드로 바꿨다(`build.reinsert_names`). 그래서 이 항목들은 종결이 0 → 0xFFFF 로 바뀐다 — 의도된 변경이라 이 셋만 허용한다.
SPACE_FOR_ZERO = set(X.SERIES_ENTRIES)  # 사피 제1~9권(#107~114·118) + 검사교본 1~3(#115~117) — 원판 문자열 시작(파일 오프셋)


def _read(data, off, zero_is_glyph):
    """(코드열, 종결) — `zero_is_glyph` 면 0 을 종결로 안 본다."""
    codes = []
    p = off
    for _ in range(64):
        if p + 1 >= len(data):
            return None, None
        v = struct.unpack_from("<H", data, p)[0]
        if v == 0xFFFF or (v & 0x8000) or (v == 0 and not zero_is_glyph):
            return codes, v
        codes.append(v)
        p += 2
    return None, None


def compare(orig, new, tables):
    """tables = [(표 오프셋, 기준 오프셋, 항목 수)] → 문제 문자열 목록."""
    out = []
    for tbl, base, n in tables:
        if tbl in SKIP_TABLES:
            continue
        zg = tbl in ZERO_IS_GLYPH
        eo = struct.unpack_from(f"<{n}H", orig, tbl)
        en = struct.unpack_from(f"<{n}H", new, tbl)
        for i in range(n):
            if SKIP_STRINGS[0] <= base + eo[i] < SKIP_STRINGS[1]:
                continue
            co, to = _read(orig, base + eo[i], zg)
            cn, tn = _read(new, base + en[i], zg)
            if co is None:
                continue
            if cn is None:
                out.append(f"표 0x{tbl:X} #{i}: 구운 항목이 종결로 안 끝난다")
                continue
            if (len(co) == 0) != (len(cn) == 0):
                out.append(f"표 0x{tbl:X} #{i}: 빈 항목 불일치(원본 {len(co)}자 → 구움 {len(cn)}자) — 빈 슬롯이 다른 항목을 읽게 된다")
            if to != tn and not (base + eo[i] in SPACE_FOR_ZERO and to == 0 and tn == 0xFFFF):
                out.append(f"표 0x{tbl:X} #{i}: 종결이 바뀌었다(원본 0x{to:04X} → 구움 0x{tn:04X})")
        groups = {}
        for i, x in enumerate(eo):
            groups.setdefault(x, []).append(i)
        for x, ids in groups.items():
            if len(ids) > 1 and len({en[i] for i in ids}) != 1:
                out.append(f"표 0x{tbl:X} {ids}: 같은 자리를 가리키던 항목이 갈라졌다")
    return out


def tables_of(orig):
    cm = textenc.charmap(DISC)
    ts = [(t["table"], t["base"], t["n"]) for t in X.scan_tables(orig, cm)]
    ts += [(lo, hi, n) for lo, hi, n in X.DETACHED[DISC]]
    return ts


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        raise SystemExit(__doc__)
    lba, size = common.iso_files(DISC)[EXE]
    orig = common.read_lba(DISC, lba, size)
    new = common.read_lba(DISC, lba, size, path=argv[0])
    ts = tables_of(orig)
    bad = compare(orig, new, ts)
    n_ent = sum(n for t, _b, n in ts if t not in SKIP_TABLES)
    print(f"  낱말 표 재삽입 대조 — 표 {len([t for t in ts if t[0] not in SKIP_TABLES])}개 · 항목 {n_ent}개 · 어긋남 {len(bad)}")
    for b in bad[:20]:
        print("   🔴", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
