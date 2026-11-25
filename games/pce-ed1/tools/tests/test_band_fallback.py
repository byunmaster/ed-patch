"""장 제목 띠 폴백(`band_fallback`) — 손으로 짠 기계어는 디스어셈블로 검산한다(연속 디코드 + 분기 목적지 + 호출 목적지, 체크리스트 「손인코딩 기계어」)."""

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import band_fallback as B
import huc6280_dis as D


def listing() -> list[str]:
    code, free_at = B.code()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D.dis(code, B.LOAD_ORG, 0, len(code))
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


class BandFallbackTest(unittest.TestCase):
    def test_decodes_without_unknown_bytes(self):
        ls = listing()
        self.assertFalse([ln for ln in ls if ".db" in ln], "디코드되지 않는 바이트")
        self.assertEqual(sum(1 for ln in ls if "JSR $E009" in ln), 2)  # 띠 읽기 + 글리프 되돌림
        self.assertTrue(any("JSR $56D8" in ln for ln in ls))  # 원래 로더 호출을 먼저 한다
        self.assertTrue(any("JSR $5597" in ln for ln in ls))  # 원래 그룹 풀기를 그대로 부른다
        self.assertTrue(any("JSR $578A" in ln for ln in ls))  # 빈 그룹 번호 얻기

    def test_branch_targets_land_on_instruction_starts(self):
        ls = listing()
        starts = {int(ln[:4], 16) for ln in ls}
        for ln in ls:
            m = re.search(r"\b(?:BCC|BCS|BNE|BEQ|BRA)\s+\$([0-9A-F]{4})", ln)
            if m:
                self.assertIn(int(m.group(1), 16), starts, ln)

    def test_free_entry_and_constants(self):
        code, free_at = B.code()
        self.assertGreater(free_at, B.LOAD_ORG)
        self.assertEqual(0x78 + B.BORROW_SLOT, B.BORROW_BANK)  # 슬롯 15 = 뱅크 0x87
        self.assertEqual(B.GLYPH1_REL, 34 + (0x7D - 0x68) * 4)  # 글리프 뱅크 1 앞 섹터의 디스크 위치
        self.assertLess(B.LOAD_ORG + len(code), 0x8000)  # 뱅크 0x70 의 FF 패딩 안(`$731E~$7FFF`)


if __name__ == "__main__":
    unittest.main()
