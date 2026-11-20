"""손으로 줄을 정한 메시지(`translate.HARD_LINES`) — 줄 폭(13칸 156px)과 문안(`t`) 일치. 조판기 대조(test_ship_path)에서 빠지는 대신 여기서 본다."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M
import translate as T
import typeset


class HardLines(unittest.TestCase):
    def test_widths_and_text(self):
        found = {}
        for p in sorted(M.SCRIPT_DIR.glob("scn*.json")):
            for k, v in M.load_translations(int(p.stem[3:])).items():
                if k in T.HARD_LINES:
                    found[k] = v["t"]
        self.assertEqual(set(found), set(T.HARD_LINES), "HARD_LINES 열쇠가 문안(script)에 없다")
        for k, lines in T.HARD_LINES.items():
            for ln in lines:
                self.assertLessEqual(typeset.px(ln), typeset.FULL * 12, (k, ln))
            joined = re.sub(r"\s+", "", "".join(lines))
            self.assertEqual(joined, re.sub(r"\s+", "", found[k]), (k, "줄 목록과 문안이 다르다"))


if __name__ == "__main__":
    unittest.main()
