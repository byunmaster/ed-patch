"""원판 사본 점검 — 제어 인자 바이트를 글자로 세지 않고, 허용 목록은 사유를 갖는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001
import check_orig_copies as c


class OrigCopies(unittest.TestCase):
    def test_제어_인자는_글자가_아니다(self):
        self.assertEqual(
            c._kana(bytes.fromhex("e3f029fa0900d021fa0600d308e1")), 0
        )  # 화자·분기만 — 글자 없음

    def test_가나는_센다(self):
        self.assertGreaterEqual(c._kana(bytes([0x11, 0x12, 0x13, 0x14, 0x15, 0xE0])), 4)

    def test_허용은_모두_사유가_있다(self):
        for d in (c.ALLOW, c.ALLOW_BINARY):
            for why in d.values():
                self.assertTrue(len(why) > 10)


if __name__ == "__main__":
    unittest.main()
