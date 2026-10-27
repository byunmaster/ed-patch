"""GMF 아카이브·RLE·TIZ 회귀 — **원본 없이 돈다**(합성 데이터).

🔴 지키는 것: ① 오프셋 단위를 잘못 잡아 **빈 슬라이스**가 나오는 사고 ② 재배치가 안 건드린 멤버를 바꾸는 사고
③ TIZ 의 「사전이 비면 스트림은 134 부터」 — 처음 해독에서 16개가 이걸로 틀렸다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.ps1 import gmf_arc, gmf_rle, tiz


def _toc(members, unit=4):
    """[(이름, 바이트)] → 아카이브. 첫 멤버는 TOC 뒤 `unit` 정렬 자리."""
    toc_len = len(members) * 32
    off = (toc_len + 32 + unit - 1) // unit * unit  # 끝 표시용 빈 항목 하나를 둔다
    toc = bytearray()
    body = bytearray()
    for n, b in members:
        toc += n.encode().ljust(20, b"\0") + struct.pack(
            "<III", (off + len(body)) // unit, len(b), 0
        )
        body += b
        body += b"\0" * (-len(body) % unit)
    out = bytes(toc) + b"\0" * (off - toc_len) + bytes(body)
    return out


class TestArchive(unittest.TestCase):
    def test_단위_4(self):
        d = _toc([("..\\BIN\\A.BIN", b"hello"), ("..\\BIN\\B.BIN", b"world!!")])
        u, ents = gmf_arc.arc_parse(d)
        self.assertEqual(u, 4)
        self.assertEqual({n: d[o : o + s] for n, o, s in ents}["..\\BIN\\B.BIN"], b"world!!")

    def test_단위_섹터(self):
        d = _toc([("A", b"x" * 10), ("B", b"y" * 3000)], unit=2048)
        u, ents = gmf_arc.arc_parse(d)
        self.assertEqual(u, 2048)
        self.assertEqual(d[ents[1][1] : ents[1][1] + 4], b"yyyy")

    def test_빈_TOC는_실패(self):
        with self.assertRaises(gmf_arc.ArchiveError):
            gmf_arc.arc_parse(bytes(64))

    def test_재배치_안_건드린_멤버는_그대로(self):
        d = _toc([("A", b"a" * 1000), ("B", b"b" * 500), ("C", b"c" * 300)])
        d += bytes(-len(d) % 2048 + 400)  # 마지막 섹터 여유를 넉넉히
        out, p = gmf_arc.repack(d, {"A": b"A" * 1100})
        members = gmf_arc.arc_members(out)
        o, s = members["B"]
        self.assertEqual(out[o : o + s], b"b" * 500)
        o, s = members["A"]
        self.assertEqual(out[o : o + s], b"A" * 1100)
        self.assertEqual(p["grow"], 100)

    def test_여유가_모자라면_멈춘다(self):
        d = _toc([("A", b"a" * 1000)])
        d += bytes(-len(d) % 2048)
        with self.assertRaises(gmf_arc.PackError):
            gmf_arc.repack(d, {"A": b"A" * 5000})

    def test_없는_멤버는_실패(self):
        d = _toc([("A", b"a" * 8)])
        with self.assertRaises(gmf_arc.PackError):
            gmf_arc.plan(d, {"Z": b"x"})


class TestRle(unittest.TestCase):
    def test_왕복(self):
        for blob in (b"", b"\x00" * 300, bytes(range(256)) * 3, b"abc" + b"\x07" * 200 + b"xyz"):
            if not blob:
                continue
            raw, short = gmf_rle.decompress(gmf_rle.wrap(blob))
            self.assertEqual((raw, short), (blob, 0))

    def test_헤더가_아니면_None(self):
        self.assertIsNone(gmf_rle.parse_header(b"\x10\x00\x00\x00\x09\x00\x00\x00"))


def _tiz(size, stream, dic=()):
    """합성 TIZ: 사전(항목들 = 바이트열)과 스트림으로 블록을 짓는다."""
    ents = [0] * 64
    blob = b""
    pos = tiz.STREAM_MIN
    for i, d in enumerate(dic):
        ents[i] = (len(d) << 12) | pos
        pos += len(d)
        blob += d
    head = bytes([1, 3]) + struct.pack("<I", size) + struct.pack("<64H", *ents)
    return head + blob + stream


class TestTiz(unittest.TestCase):
    def test_네_가지_op(self):
        dic = [b"\x11\x22\x33", b"\xaa\xbb"]
        stream = (
            bytes([0x80])
            + b"\x10"  # 리터럴 1 : 10
            + bytes([0x02, 0x00])  # 반복 3×00
            + bytes([0x41])
            + b"\x80\x00"  # 쌍 2× (80 00)
            + bytes([0x81])
            + b"\x0c\x02"  # 리터럴 2
            + bytes([0xC0])  # 사전 0
            + bytes([0xC1])  # 사전 1
        )
        want = (
            b"\x10"
            + b"\x00" * 3
            + b"\x80\x00\x80\x00"
            + b"\x0c\x02"
            + b"\x11\x22\x33"
            + b"\xaa\xbb"
        )
        self.assertEqual(tiz.decompress(_tiz(len(want), stream, dic)), want)

    def test_사전이_비면_스트림은_134부터(self):
        stream = bytes([0x03, 0x55])
        blk = _tiz(4, stream)
        self.assertEqual(len(blk) - len(stream), 134)
        self.assertEqual(tiz.decompress(blk), b"\x55" * 4)

    def test_입력이_남으면_실패(self):
        with self.assertRaises(tiz.TizError):
            tiz.decompress(_tiz(2, bytes([0x01, 0x55]) + b"\x00\x00"))

    def test_푼_크기를_넘기면_실패(self):
        with self.assertRaises(tiz.TizError):
            tiz.decompress(_tiz(2, bytes([0x03, 0x55])))

    def test_입력이_모자라면_실패(self):
        with self.assertRaises(tiz.TizError):
            tiz.decompress(_tiz(8, bytes([0x01, 0x55])))

    def test_헤더가_아니면_None(self):
        self.assertIsNone(tiz.parse_header(b"\x4e\x00\x01\x03" + bytes(200)))
        with self.assertRaises(tiz.TizError):
            tiz.decompress(b"\x4e\x00\x01\x03" + bytes(200))


if __name__ == "__main__":
    unittest.main()
