"""게시판 창 배치 패치(`halfwidth.BOARD_PATCH`) — 새 명령이 원판과 같은 명령 꼴(레지스터·연산)에 즉치만 다른지 디코드로 확인한다."""

import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import halfwidth


class TestBoardPatch(unittest.TestCase):
    def test_즉치만_다르다(self):
        import capstone

        md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
        for a, old, new in halfwidth.BOARD_PATCH:
            o = next(md.disasm(struct.pack("<I", old), a))
            n = next(md.disasm(struct.pack("<I", new), a))
            self.assertEqual(o.mnemonic, n.mnemonic, hex(a))
            self.assertEqual(o.op_str.split(",")[:2], n.op_str.split(",")[:2], hex(a))

    def test_주소_중복_없음(self):
        addrs = [a for a, _o, _n in halfwidth.BOARD_PATCH]
        self.assertEqual(len(addrs), len(set(addrs)))


if __name__ == "__main__":
    unittest.main()
