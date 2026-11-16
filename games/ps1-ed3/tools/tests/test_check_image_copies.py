import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_image_copies as C


def _bytes(codes):
    return np.asarray(codes, dtype="<u2").tobytes()


class ImageCopies(unittest.TestCase):
    TEXT = (0x120, 0x240, 0x151, 0x3A0, 0x199, 0x222, 0x310)

    def grams(self):
        return np.unique(C.hashes(np.asarray(self.TEXT, dtype=np.uint16)))

    def test_found_at_both_parities(self):
        pad = bytes(range(1, 40)) * 3
        for par in (0, 1):
            data = pad[:par] + b"\xff\xff" * 5 + _bytes(self.TEXT) + pad
            self.assertEqual(C.scan_file(data, self.grams()), 1, par)

    def test_adjacent_windows_are_one_run(self):
        data = b"\x00\x80" * 8 + _bytes(self.TEXT)
        self.assertEqual(C.scan_file(data, self.grams()), 1)

    def test_clean_data_is_zero(self):
        data = _bytes([0x7000 + i for i in range(60)])
        self.assertEqual(C.scan_file(data, self.grams()), 0)

    def test_repetition_is_not_text(self):
        rep = [0x6A] * 7
        g = np.unique(C.hashes(np.asarray(rep, dtype=np.uint16)))
        self.assertEqual(C.scan_file(_bytes(rep), g), 0)


if __name__ == "__main__":
    unittest.main()
