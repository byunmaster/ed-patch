import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import debug_build


class FakeRom:
    def __init__(self):
        self.buf = bytearray(common.rom())
        self.log = []

    def write(self, label, at, data):
        self.buf[at : at + len(data)] = data
        self.log.append(label)


class DebugSwitch(unittest.TestCase):
    def test_off_by_default_writes_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(debug_build.ENV, None)
            rom = FakeRom()
            self.assertEqual(debug_build.apply(rom), 0)
            self.assertEqual(rom.log, [])
            self.assertEqual(debug_build.allowed(), {})

    def test_original_bytes_match_expectation(self):
        # 엔진 주소가 밀리면 패치가 엉뚱한 곳을 쓴다 — 켜기 전에 원본 바이트를 못 박는다
        orig = common.rom()
        for _label, at, old, _new in debug_build.PATCHES:
            self.assertEqual(orig[at : at + len(old)], old)

    def test_refuses_product_tag(self):
        with (
            mock.patch.dict(os.environ, {debug_build.ENV: "1"}),
            mock.patch.object(debug_build, "BUILD_TAG", "game/md-ed2"),
            self.assertRaises(SystemExit),
        ):
            debug_build.apply(FakeRom())

    def test_tag_rules(self):
        self.assertTrue(debug_build.tag_ok("debug"))
        self.assertTrue(debug_build.tag_ok("test-debug"))
        self.assertFalse(debug_build.tag_ok("game/md-ed2"))
        self.assertFalse(debug_build.tag_ok("debugger"))

    def test_debug_tag_requires_switch(self):
        with mock.patch.object(debug_build, "BUILD_TAG", "debug"):
            os.environ.pop(debug_build.ENV, None)
            with self.assertRaises(SystemExit):
                debug_build.check_tag()
            with mock.patch.dict(os.environ, {debug_build.ENV: "1"}):
                debug_build.check_tag()
                self.assertEqual(debug_build.rom_name(), "ed2-kr (DEBUG).bin")

    def test_product_rom_name(self):
        os.environ.pop(debug_build.ENV, None)
        self.assertEqual(debug_build.rom_name(), "ed2-kr.bin")


if __name__ == "__main__":
    unittest.main()
