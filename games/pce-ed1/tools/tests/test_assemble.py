"""컨테이너 재조립 — 원본 없이 돈다. 디렉터리 형식·블록 공유·되풀기를 못 박는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import common
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


class Ledger(unittest.TestCase):
    """🔴 **뒤 단계가 앞 단계의 바이트를 지웠나** — 게이트 셋이 다 못 보는 자리다.

    되읽기는 *자기가 쓴 직후*를, 라운드트립은 *덤프↔원본*을, 무변경 구간은 *안 여는 파일*을
    본다. 덮어쓰기는 아무도 안 본다(ss-ed1+2 실측, 중계 2026-09-07).
    """

    def _iso(self, sectors=2):
        import tempfile

        p = Path(tempfile.mkdtemp()) / "t.iso"
        p.write_bytes(bytes(sectors * common.RAW))
        return p

    def _put(self, iso, lba, off, data):
        b = bytearray(iso.read_bytes())
        s = lba * common.RAW + common.USER_OFF + off
        b[s : s + len(data)] = data
        iso.write_bytes(bytes(b))

    def test_덮이면_운다(self):
        iso = self._iso()
        led = build.WriteLedger()
        led.add(0 * common.USER + 10, b"\xaa\xbb", "앞 단계")
        self._put(iso, 0, 10, b"\x11\x22")  # 뒤 단계가 그 자리를 덮었다
        with self.assertRaises(build.BuildError) as cm:
            led.verify(iso)
        self.assertIn("앞 단계", str(cm.exception))

    def test_안_덮이면_안_운다(self):
        iso = self._iso()
        led = build.WriteLedger()
        led.add(0 * common.USER + 10, b"\xaa\xbb", "앞 단계")
        self._put(iso, 0, 10, b"\xaa\xbb")
        led.add(0 * common.USER + 20, b"\xcc", "뒤 단계")
        self._put(iso, 0, 20, b"\xcc")
        self.assertEqual(led.verify(iso), 2)

    def test_섹터_경계를_걸쳐도_읽는다(self):
        """⚠ 우리 쓰기는 섹터를 걸친다 — 되읽기가 거기서 틀리면 가드가 조용히 죽는다."""
        iso = self._iso()
        data = bytes(range(1, 33))
        led = build.WriteLedger()
        led.add(common.USER - 16, data, "걸침")
        self._put(iso, 0, common.USER - 16, data[:16])
        self._put(iso, 1, 0, data[16:])
        self.assertEqual(led.verify(iso), 1)
