"""GMF 아카이브 TOC — **오프셋 단위**를 잘못 잡으면 예외가 아니라 빈 멤버가 나온다.

2026-09-03 에 실제로 밟았다: 단위를 정한 뒤 한 번 더 곱해서 595 멤버가 전부 0바이트였는데
덤퍼는 「런 0」을 조용히 찍었다. 원본 없이 도는 합성 아카이브로 그 자리를 박는다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common


def build(unit, members, toc_slots=None):
    """(이름, 바이트) 목록으로 아카이브 하나를 만든다."""
    toc_slots = toc_slots or len(members) + 1  # ⚠ 마지막 한 칸은 0 — TOC 의 끝 표시다
    toc = toc_slots * 32
    head = (toc + unit - 1) // unit * unit  # 첫 멤버는 단위에 맞춰 시작
    body, offs = bytearray(), []
    for _, data in members:
        offs.append(head + len(body))
        body += data
        while len(body) % unit:
            body += b"\x00"
    ents = bytearray()
    for (name, data), off in zip(members, offs, strict=True):
        ents += name.encode("ascii").ljust(20, b"\x00")
        ents += struct.pack("<III", off // unit, len(data), 0)
    ents = ents.ljust(toc, b"\x00")
    return bytes(ents) + b"\x00" * (head - toc) + bytes(body)


class TestArc(unittest.TestCase):
    def test_unit_word(self):
        members = [("..\\DATA\\A.BIN", b"\x11" * 100), ("..\\DATA\\B.BIN", b"\x22" * 250)]
        data = build(4, members)
        unit, ents = common.arc_parse(data)
        self.assertEqual(unit, 4)
        self.assertEqual([n for n, _, _ in ents], [n for n, _ in members])
        for (name, want), (_, off, size) in zip(members, ents, strict=True):
            self.assertEqual(data[off : off + size], want, name)

    def test_unit_sector(self):
        members = [("MD00.BIN", b"\xaa" * 4096), ("MD01.BIN", b"\xbb" * 2048)]
        data = build(2048, members)
        unit, ents = common.arc_parse(data)
        self.assertEqual(unit, 2048)
        for (name, want), (_, off, size) in zip(members, ents, strict=True):
            self.assertEqual(data[off : off + size], want, name)

    def test_members_never_empty(self):
        """🔴 멤버가 비면 그건 성공이 아니라 **단위를 잘못 잡은 것**이다."""
        data = build(4, [("..\\DATA\\A.BIN", b"\x11" * 100)])
        _, ents = common.arc_parse(data)
        for name, off, size in ents:
            self.assertGreater(size, 0, name)
            self.assertEqual(len(data[off : off + size]), size, name)

    def test_bad_toc_raises(self):
        with self.assertRaises(common.ArchiveError):
            common.arc_parse(b"NAME".ljust(20, b"\x00") + struct.pack("<III", 1 << 20, 1 << 20, 0))


if __name__ == "__main__":
    unittest.main()
