"""아카이브 재배치(`arcpack`) — 합성 아카이브로 회귀. 원본 없이 돈다.

🔴 밟을 수 있는 함정: 멤버가 커지면 뒤 멤버의 **오프셋 단위(4B)·정렬 패딩**이 어긋나 조용히 남의 자리를 읽는다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import arcpack
import common


def make(members, pad_to=None):
    """합성 SC 아카이브 — TOC(32B × N) + 4B 정렬된 멤버. members = [(이름, bytes)]."""
    toc_len = (len(members) + 1) * 32  # 끝 항목은 0(실물 TOC 도 0 으로 닫힌다)
    body = bytearray()
    ents = []
    pos = toc_len
    for n, b in members:
        ents.append((n, pos, len(b)))
        body += b
        pad = -len(b) % 4
        body += b"\x00" * pad
        pos += len(b) + pad
    toc = bytearray()
    for n, off, sz in ents:
        toc += n.encode().ljust(20, b"\x00") + struct.pack("<III", off // 4, sz, 0)
    data = bytes(toc).ljust(toc_len, b"\x00") + bytes(body)
    return data.ljust(pad_to, b"\x00") if pad_to else data


class TestArcPack(unittest.TestCase):
    def setUp(self):
        self.m = [("A", b"a" * 10), ("B", b"b" * 21), ("C", b"c" * 8)]
        self.data = make(self.m)  # 파일 길이 = 마지막 멤버 끝(실물 ISO 파일 크기와 같다) — 섹터 끝까지가 여유다

    def parse(self, d):
        return common.arc_parse(d)[1]

    def test_identity_is_byte_equal_except_pad(self):
        new, p = arcpack.repack(self.data, {})
        self.assertEqual(new, self.data)
        self.assertEqual(p["grow"], 0)

    def test_grown_member_pushes_followers_and_toc_follows(self):
        new, p = arcpack.repack(self.data, {"B": b"B" * 30})
        ents = {n: (o, s) for n, o, s in self.parse(new)}
        self.assertEqual(ents["B"][1], 30)
        self.assertEqual(new[ents["B"][0] : ents["B"][0] + 30], b"B" * 30)
        # 뒤 멤버는 바이트 그대로, 위치만 밀렸다
        o, s = ents["C"]
        self.assertEqual(new[o : o + s], b"c" * 8)
        self.assertEqual(o % 4, 0)
        old = {n: (o2, s2) for n, o2, s2 in self.parse(self.data)}
        self.assertGreater(o, old["C"][0])
        # 앞 멤버는 안 움직였다
        self.assertEqual(ents["A"], old["A"])
        self.assertEqual(len(new), len(self.data) + p["grow"])

    def test_sector_count_never_changes(self):
        new, _ = arcpack.repack(self.data, {"A": b"x" * 50})
        self.assertEqual(-(-len(new) // 2048), -(-len(self.data) // 2048))

    def test_refuses_when_sector_would_grow(self):
        with self.assertRaises(arcpack.PackError):
            arcpack.repack(self.data, {"B": b"B" * 3000})

    def test_reclaims_trailing_zeros_of_shrunk_members(self):
        data = make([("A", b"a" * 40), ("B", b"b" * 20)])
        # 여유(2048 - 길이)를 넘는 증가 — 줄어든 멤버 A 의 꼬리로 메운다
        slack = 2048 - len(data)
        new, p = arcpack.repack(data, {"A": b"a" * 8, "B": b"B" * (20 + slack + 8)})
        self.assertGreater(p["reclaimed"], 0)
        ents = {n: (o, s) for n, o, s in self.parse(new)}
        self.assertEqual(new[ents["A"][0] : ents["A"][0] + 8], b"a" * 8)
        self.assertEqual(-(-len(new) // 2048), 1)

    def test_unknown_member_is_an_error(self):
        with self.assertRaises(arcpack.PackError):
            arcpack.repack(self.data, {"Z": b"z"})

    def test_untouched_members_are_byte_identical_after_shift(self):
        new, _ = arcpack.repack(self.data, {"A": b"A" * 33})
        ents = {n: (o, s) for n, o, s in self.parse(new)}
        self.assertEqual(new[ents["B"][0] : ents["B"][0] + ents["B"][1]], b"b" * 21)
        self.assertEqual(new[ents["C"][0] : ents["C"][0] + ents["C"][1]], b"c" * 8)

    def test_verify_catches_a_corrupted_member(self):
        new, p = arcpack.repack(self.data, {"B": b"B" * 30})
        bad = bytearray(new)
        o = {n: o for n, o, _ in self.parse(new)}["C"]
        bad[o] ^= 0xFF
        with self.assertRaises(arcpack.PackError):
            arcpack.verify(self.data, bytes(bad), {"B": b"B" * 30}, p)


def _rec(name, lba, size, flags=0):
    nm = name.encode()
    ln = 33 + len(nm)
    ln += ln % 2
    r = bytearray(ln)
    r[0] = ln
    r[2:6] = struct.pack("<I", lba)
    r[6:10] = struct.pack(">I", lba)
    r[10:14] = struct.pack("<I", size)
    r[14:18] = struct.pack(">I", size)
    r[25] = flags
    r[32] = len(nm)
    r[33 : 33 + len(nm)] = nm
    return bytes(r)


class TestIsoSize(unittest.TestCase):
    def test_set_file_size_patches_both_endians_and_walks_back(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.bin")
            with open(path, "wb") as f:
                for i in range(24):  # 합성 MODE2 Form1 섹터 — 동기·헤더·서브헤더만 채운다
                    sec = bytearray(common.SECTOR)
                    sec[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
                    sec[15] = 2
                    f.write(sec)
            with open(path, "r+b") as f:
                root = _rec("\x00", 18, 2048, 2)
                pvd = bytearray(2048)
                pvd[156 : 156 + len(root)] = root
                common.write_user_data(f, "ed3", 16, bytes(pvd), label="pvd")
                dirdata = _rec("\x00", 18, 2048, 2) + _rec("\x01", 18, 2048, 2) + _rec("A.DAT;1", 20, 1000)
                common.write_user_data(f, "ed3", 18, dirdata, label="dir")
            files, pos = common.iso_tree(path)
            self.assertEqual(files["/A.DAT"], (20, 1000))
            with open(path, "r+b") as f:
                common.set_file_size(f, "ed3", *pos["/A.DAT"], 1500, label="t")
            files2, _ = common.iso_tree(path)
            self.assertEqual(files2["/A.DAT"], (20, 1500))


if __name__ == "__main__":
    unittest.main()
