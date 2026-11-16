"""구운 롬 되읽기(`jump_readout`)의 읽기 규칙 — 원본 없이 돈다(합성 바이트).

양성 대조: 한글 머리를 원문(SJIS) 이름으로 되돌려 쓴 블록을 읽기 도구가 실패로 가르는가(11-06 — 씬 46 선장 머리가 일본어로 나가던 회귀)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jump_readout as J

INV = {b"\xf1\x7e": "선", b"\xf1\xf8": "장", b"\xf0\x10": "예"}


class ReadTest(unittest.TestCase):
    def test_korean_header_passes_sjis_header_fails(self):
        kr = bytes([0x1F]) + b"\xf1\x7e\xf1\xf8" + bytes([0x04, 0x01]) + b"\xf0\x10" + bytes([0x00])
        jp = bytes([0x1F]) + "船長".encode("cp932") + bytes([0x04, 0x01]) + b"\xf0\x10" + bytes([0x00])
        r_kr, _j, u = J.read(kr, 0, INV)
        r_jp, _j2, _u2 = J.read(jp, 0, INV)
        self.assertEqual(u, 0)
        self.assertTrue(J.header_korean(r_kr), r_kr)
        self.assertFalse(J.header_korean(r_jp), r_jp)  # 롬에 SJIS 이름이 남았다 — 실패로 잡는다

    def test_header_name_follows_jump(self):
        # 긴 이름 머리는 재배치로 이름 중간에 `0F` 가 낀다 — 따라가며 읽는다. 0F 목적지 = 논리 주소(BASE + 오프셋)
        base = 0xA000
        blk = bytearray(32)
        blk[0:3] = bytes([0x1F, 0xF1, 0x7E])
        blk[3:6] = bytes([0x0F, (base + 10) & 0xFF, (base + 10) >> 8])
        blk[10:13] = bytes([0xF1, 0xF8, 0x04])
        blk[13:15] = bytes([0x01, 0x00])
        r, jumps, u = J.read(bytes(blk), 0, INV)
        self.assertEqual(u, 0)
        self.assertTrue(r.startswith("〔선장〕"), r)
        self.assertTrue(jumps)


if __name__ == "__main__":
    unittest.main()
