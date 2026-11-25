"""씬 54 지도 구역 이미지(`zone_image`) — 복사 길이 패치·상수. 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M
import zone_image as Z


class ZoneImage(unittest.TestCase):
    def _blk(self):
        b = bytearray(0x300)
        b[0x294], b[0x295], b[0x298], b[0x299] = 0xA9, 0x8B, 0xA9, 0x18
        return bytes(b)

    def test_patch_count(self):
        out = Z.patch_count(self._blk(), 0x1974)
        self.assertEqual((out[0x295], out[0x299]), (0x74, 0x19))
        self.assertEqual(sum(a != b for a, b in zip(out, self._blk())), 2)  # 같은 길이 제자리 교체 둘뿐

    def test_patch_count_expects_original(self):
        bad = bytearray(self._blk())
        bad[0x295] = 0x00
        with self.assertRaises(Z.ZoneError):
            Z.patch_count(bytes(bad), 100)

    def test_constants_match_loader(self):
        # 원판 복사 길이 = 블록 + 오버레이, 즉시값 `8B 18` = 0x188B
        self.assertEqual(Z.COUNT_OLD, (b"\x8b", b"\x18"))
        self.assertEqual(0x188B, Z.ORIG_LEN)
        self.assertEqual(Z.COUNT_TABLE, (43, 1512))

    def test_pad_exit_clears(self):
        M.PAD = b"x"
        Z.pad().__exit__(None, None, None)  # __enter__ 는 원본을 읽으므로 이 시험은 나가는 쪽만 본다
        self.assertEqual(M.PAD, b"")


if __name__ == "__main__":
    unittest.main()
