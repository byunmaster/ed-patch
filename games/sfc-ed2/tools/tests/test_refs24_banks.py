"""relocate.refs24 — 포인터 자리를 뱅크로 한정한다(11-07: 롬 전체 패턴 스캔이 BGM 데이터 `$D6:3189` 의 우연한 세 바이트를 덮어 3장 던전 음악 전송이 멈췄다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common
import relocate


class Refs24BanksTest(unittest.TestCase):
    def test_banks_filter_drops_accidental_match_in_other_bank(self):
        d = bytearray(common.ROM_SIZE)
        pat = bytes([0xAE, 0x0A, 0xD7])  # $D7:0AAE
        real, fake = 0x170000 + 0x0100, 0x160000 + 0x3189  # $D7:0100 / $D6:3189
        d[real : real + 3] = pat
        d[fake : fake + 3] = pat
        self.assertEqual(relocate.refs24(bytes(d), 0xD70AAE), [fake, real])
        self.assertEqual(relocate.refs24(bytes(d), 0xD70AAE, None, {0xD7}), [real])

    def test_site_gate_rejects_undeclared_bank(self):
        relocate.SITE_LOG.clear()
        relocate.SITE_LOG.append(("ref24", 0x160000 + 0x3189))  # $D6:3189
        with self.assertRaises(SystemExit):
            relocate.check_sites()
        relocate.SITE_LOG.clear()
        relocate.SITE_LOG.append(("ref24", 0x170000 + 0x100))
        relocate.check_sites()
        relocate.SITE_LOG.clear()


if __name__ == "__main__":
    unittest.main()
