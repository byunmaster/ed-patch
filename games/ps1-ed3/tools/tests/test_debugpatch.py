"""시험 빌드 전용 디버그 스위치(`debugpatch.py`) — 원본 없이 도는 합성 실행파일 시험."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common
import debugpatch as D
import engine_patch as E


def fake_exe():
    exe = bytearray(716800)
    o = E._off(D.MAP_TABLE)
    for n in ("FT0000", "FT1000", "MR4300"):
        exe[o : o + 6] = n.encode()
        o += 10
    exe[o : o + 6] = b"ZZZZZZ"
    exe[E._off(D.NAME_ADDR) : E._off(D.NAME_ADDR) + 8] = D.NAME_ORIG
    struct.pack_into("<I", exe, E._off(D.DIR_NOP), D.NOP)
    struct.pack_into("<I", exe, E._off(D.DIR_STORE), D.SH_ZERO)
    return exe


class DebugPatchTest(unittest.TestCase):
    def setUp(self):
        self._chap = D.chapter_of
        D.chapter_of = lambda disc, name: {"FT1000": 0, "MR4300": 1}[name]

    def tearDown(self):
        D.chapter_of = self._chap

    def test_patch_words_and_name(self):
        exe = fake_exe()
        note = D.apply(exe, "ed3", "MR4300")
        self.assertIn("MR4300", note)
        n = E._off(D.NAME_ADDR)
        self.assertEqual(bytes(exe[n : n + 8]), b"MR4300\x00\x00")
        self.assertEqual(struct.unpack_from("<I", exe, E._off(D.DIR_NOP))[0], 0x24020001)  # addiu v0,zero,1
        self.assertEqual(struct.unpack_from("<I", exe, E._off(D.DIR_STORE))[0], 0xA4226468)  # sh v0,0x6468(at)

    def test_untouched_elsewhere(self):
        a, b = fake_exe(), fake_exe()
        D.apply(b, "ed3", "FT1000")
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        spans = {E._off(D.NAME_ADDR), E._off(D.DIR_NOP), E._off(D.DIR_STORE)}
        self.assertTrue(all(any(s <= i < s + 8 for s in spans) for i in diff), diff[:8])

    def test_unknown_or_bad_name_rejected(self):
        for bad in ("", "FT100", "XX9999", "FT10000"):
            with self.assertRaises(SystemExit):
                D.apply(fake_exe(), "ed3", bad)

    def test_original_words_checked(self):
        exe = fake_exe()
        struct.pack_into("<I", exe, E._off(D.DIR_STORE), 0)
        with self.assertRaises(SystemExit):
            D.apply(exe, "ed3", "FT1000")

    def test_debug_tag_must_be_test(self):
        old = (common.DEBUG, os.environ.get("ED_BUILD_TAG"))
        try:
            common.DEBUG = True
            os.environ["ED_BUILD_TAG"] = "ps1-ed3"
            with self.assertRaises(SystemExit):
                common._build_tag()
            os.environ["ED_BUILD_TAG"] = "test-x"
            self.assertEqual(common._build_tag(), "test-x")
            os.environ["ED_BUILD_TAG"] = "debug"  # 마스터용 칸
            self.assertEqual(common._build_tag(), "debug")
            os.environ.pop("ED_BUILD_TAG")
            self.assertEqual(common._build_tag(), "test-debug")
            common.DEBUG = False
            self.assertEqual(common._build_tag(), "ps1-ed3")
        finally:
            common.DEBUG = old[0]
            if old[1] is None:
                os.environ.pop("ED_BUILD_TAG", None)
            else:
                os.environ["ED_BUILD_TAG"] = old[1]


if __name__ == "__main__":
    unittest.main()
