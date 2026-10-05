"""빌드 칸의 해시 이름 세이브 — 원본 없이 돈다(가짜 파일)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import save_names as SN

GID = "0123456789abcdef0123456789abcdef"


class Emit(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.t.name, "save")
        self.out = os.path.join(self.t.name, "build")
        os.makedirs(self.src)
        os.makedirs(self.out)
        for n in ("Game (Disc 1)", "Game"):
            open(os.path.join(self.out, n + (".cue" if "Disc" in n else ".m3u")), "w").close()
        open(os.path.join(self.src, "Game (Disc 1).bkr"), "wb").write(b"SAVE1")
        open(os.path.join(self.src, "Game.bkr"), "wb").write(b"SAVEM")

    def tearDown(self):
        self.t.cleanup()

    def images(self):
        return [os.path.join(self.out, "Game (Disc 1).cue"), os.path.join(self.out, "Game.m3u")]

    def test_puts_hashed_copies_next_to_the_images(self):
        made = SN.emit(self.src, self.out, self.images(), lambda p: GID)
        self.assertEqual(len(made), 2)
        self.assertEqual(open(os.path.join(self.out, f"Game (Disc 1).{GID}.bkr"), "rb").read(), b"SAVE1")
        self.assertEqual(open(os.path.join(self.out, f"Game.{GID}.bkr"), "rb").read(), b"SAVEM")

    def test_old_hashed_copies_are_removed(self):
        stale = os.path.join(self.out, "Game.ffffffffffffffffffffffffffffffff.bkr")
        open(stale, "w").close()
        SN.emit(self.src, self.out, self.images(), lambda p: GID)
        self.assertFalse(os.path.exists(stale))

    def test_the_source_is_only_read(self):
        before = sorted(os.listdir(self.src))
        SN.emit(self.src, self.out, self.images(), lambda p: GID)
        self.assertEqual(sorted(os.listdir(self.src)), before)

    def test_missing_source_dir_does_nothing(self):
        self.assertEqual(SN.emit(os.path.join(self.t.name, "nope"), self.out, self.images(), lambda p: GID), [])


if __name__ == "__main__":
    unittest.main()
