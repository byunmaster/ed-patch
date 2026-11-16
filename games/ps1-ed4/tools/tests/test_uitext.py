"""UI 문안 정본 규칙 회귀 — **원본 없이 돈다**(합성 바이트)."""

import struct
import unittest

import _path  # noqa: F401
import uitext


def words(*w):
    return struct.pack(f"<{len(w)}H", *w)


class TestRaw(unittest.TestCase):
    def test_종결까지_읽고_종결값을_돌려준다(self):
        exe = words(10, 11, 12, 0x8002, 99)
        self.assertEqual(uitext.raw_string(exe, 0), ([10, 11, 12], 0x8002))

    def test_종결이_없으면_None(self):
        self.assertEqual(uitext.raw_string(words(1, 2, 3), 0, limit=3), (None, None))

    def test_지문은_코드열이_같으면_같다(self):
        self.assertEqual(uitext.stamp([1, 2, 3]), uitext.stamp([1, 2, 3]))
        self.assertNotEqual(uitext.stamp([1, 2, 3]), uitext.stamp([1, 2, 4]))
        self.assertEqual(len(uitext.stamp([1])), 10)


if __name__ == "__main__":
    unittest.main()
