"""옛 컨테이너 먼저 내리기(`earlyfree`) — 손으로 짠 기계어는 디스어셈블로 검산한다(연속 디코드 + 분기 목적지 + 호출 목적지)."""

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import debug_item_list
import earlyfree as E
import huc6280_dis as D
import sprmask


def listing() -> list[str]:
    code = E.code()
    body = code[: code.index(E.SITE_OLD)]  # 꼬리의 먼 호출 6B(인라인 인자 3B)와 RTS 는 따로 본다
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D.dis(body, E.ORG, 0, len(body))
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


class EarlyFreeTest(unittest.TestCase):
    def test_decodes_and_calls(self):
        ls = listing()
        self.assertFalse([ln for ln in ls if ".db" in ln], "디코드되지 않는 바이트")
        self.assertEqual(sum(1 for ln in ls if "JSR $5597" in ln), 1)  # 엔진의 그룹 내림을 그대로 부른다
        self.assertTrue(any("LDY $61" in ln for ln in ls))  # 씬 컨테이너 그룹
        self.assertEqual(sum(1 for ln in ls if "$378D,Y" in ln), 2)  # 올라와 있나 보기 + 번호를 슬롯 14 에 세워 두기

    def test_branch_targets_land_on_instruction_starts(self):
        ls = listing()
        starts = {int(ln[:4], 16) for ln in ls} | {E.ORG + E.code().index(E.SITE_OLD)}  # skip = 원래 먼 호출
        for ln in ls:
            m = re.search(r"\b(?:BCC|BCS|BNE|BEQ|BMI|BRA)\s+\$([0-9A-F]{4})", ln)
            if m:
                self.assertIn(int(m.group(1), 16), starts, ln)

    def test_tail_is_original_far_call_then_rts(self):
        code = E.code()
        self.assertEqual(code[-7:], E.SITE_OLD + b"\x60")  # 묶음 올리기(원판 6B 그대로) 뒤 RTS
        self.assertEqual(code.count(E.SITE_OLD), 1)

    def test_condition_mirrors_engine(self):
        """`$6B8C` 의 「컨테이너를 바꾼다」 조건 — `$C009 == 3` 이면 바꾸고, 아니면 `$C00F + $C010` 이 0 일 때만 안 바꾼다."""
        self.assertEqual(E.code()[:16], bytes.fromhex("ad09c0c903f009ad0fc0186d10c0f014"))

    def test_parks_group_on_glyph_slot(self):
        self.assertEqual(E.PARK_SLOT, 14)  # 할당기·조각 모으기의 `CPX #$0E` 바깥 첫 칸 — 주인표가 늘 0
        self.assertIn(bytes([0xA9, E.PARK_SLOT, 0x99, 0x8D, 0x37]), E.code())

    def test_site_and_room(self):
        self.assertEqual(E.site_new(), bytes.fromhex("20d84f085079"))
        self.assertEqual(len(E.site_new()), len(E.SITE_OLD))
        self.assertLessEqual(len(E.code()), E.ROOM)
        self.assertEqual(E.ORG + E.ROOM, sprmask.DEBUG_LIST_LIMIT)  # 뒤는 잘린 그림 사본 토막 a
        org, blob, _i, _w = debug_item_list.assemble()
        self.assertLessEqual(org + len(blob), E.ORG)  # 앞은 디버그 목록 코드


if __name__ == "__main__":
    unittest.main()
