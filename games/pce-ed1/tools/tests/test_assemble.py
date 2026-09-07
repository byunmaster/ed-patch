"""컨테이너 재조립 — 원본 없이 돈다. 디렉터리 형식·블록 공유·되풀기를 못 박는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import containers
import lz


def synth(entries, slot=0x2000):
    """(id, 풀린 블록) 목록 → **원본 노릇을 할** 컨테이너 바이트.

    `assemble` 은 이제 **원본에서 출발해 각 블록의 원래 슬롯만 덮어쓴다**(자리 보존)라
    원본 컨테이너가 있어야 한다. 원본 없이 돌려야 하니 여기서 하나 지어 준다.
    """
    packed, src_of, pos = {}, {}, len(entries) * containers.ENTRY + 1
    body = bytearray()
    for _, blk in entries:
        if blk in src_of:
            continue
        pk = lz.encode(blk)
        src_of[blk] = pos
        body += pk
        pos += len(pk)
        packed[blk] = pk
    d = bytearray()
    for id_, blk in entries:
        s0 = src_of[blk]
        d += bytes([id_, s0 & 0xFF, s0 >> 8, len(blk) & 0xFF, len(blk) >> 8])
    d.append(containers.DIR_END)
    out = bytes(d) + bytes(body)
    return out + b"\0" * (slot - len(out))


class Assemble(unittest.TestCase):
    def test_왕복과_공유(self):
        a = (
            b"\x1f"
            + "侍女".encode("cp932")
            + b"\x04\x01"
            + "おはよう".encode("cp932") * 20
            + b"\x00"
        )
        b = b"\x4c\x10\xa0" + bytes(range(64)) + b"\x00" * 50
        ents_in = [(0, a), (7, b), (9, a)]  # 9 는 0 과 같은 블록
        out = build.assemble(ents_in, synth(ents_in), "t")
        ents, dend = containers.parse_dir(out[:2048])
        self.assertEqual([e[0] for e in ents], [0, 7, 9])
        self.assertEqual(ents[0][1], ents[2][1])  # 같은 src 를 나눠 갖는다
        self.assertEqual(dend, 3 * 5 + 1)
        for id_, src, ln in ents:
            got, _ = lz.decode(out[src:], ln)
            self.assertEqual(got, a if id_ in (0, 9) else b)

    def test_뱅크를_넘으면_죽는다(self):
        with self.assertRaises(build.BuildError):
            build.assemble([(0, b"x" * 0x2001)], b"\0" * 0x2000, "t")

    def test_원래_슬롯을_넘치면_죽는다(self):
        """🔴 자리 보존이 계약이다 — 슬롯을 넘기면 조용히 밀지 말고 죽어야 한다."""
        a = b"\x1f" + "侍女".encode("cp932") + b"\x00"
        b = b"\x4c\x10\xa0" + bytes(range(32)) + b"\x00"
        orig = synth([(0, a), (7, b)])
        big = a + "ながいながいもんく".encode("cp932") * 40 + b"\x00"
        with self.assertRaises(build.BuildError):
            build.assemble([(0, big), (7, b)], orig, "t")

    def test_편집은_정확히_한_번_맞아야(self):
        with self.assertRaises(build.BuildError):
            build.apply_edits(b"abab", [(b"ab", b"cd")], "t")
        self.assertEqual(build.apply_edits(b"xab", [(b"ab", b"cde")], "t"), b"xcde")


if __name__ == "__main__":
    unittest.main()
