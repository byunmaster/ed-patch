"""check_diff_audit — 쓴 적 없는 바이트가 바뀌면 잡는다(양성 대조)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_diff_audit as a


class BodyAudit(unittest.TestCase):
    def test_clean(self):
        o = bytes(64)
        n = bytearray(o)
        n[8:12] = b"\x01\x02\x03\x04"
        self.assertEqual(a.audit_body(o, bytes(n), [["x", 8, 4]]), [])

    def test_unwritten_change_is_caught(self):
        """패턴 치환이 쓴 기록 없이 바이트를 바꾼 꼴 — 잡혀야 한다."""
        o = bytes(64)
        n = bytearray(o)
        n[8:12] = b"\x01\x02\x03\x04"
        n[40] = 0x99  # 기록에 없다
        errs = a.audit_body(o, bytes(n), [["x", 8, 4]])
        self.assertEqual(len(errs), 1)
        self.assertIn("0x28", errs[0])

    def test_length_change_is_caught(self):
        self.assertTrue(a.audit_body(bytes(8), bytes(10), []))


if __name__ == "__main__":
    unittest.main()
