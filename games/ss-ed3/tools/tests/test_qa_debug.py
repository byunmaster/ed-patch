"""QA 디버그 개조 — 스위치가 꺼지면 제품 바이트 불변, 꼬리표가 qa- 가 아니면 멈춘다."""

import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import patch_qa_debug as Q


def fake_bin():
    b = bytearray(0xC000)
    for a, v in ((Q.SPEED_X, 256.0), (Q.SPEED_Y, 192.0)):
        b[a - Q.BASE : a - Q.BASE + 8] = struct.pack(">d", v)
    b[Q.NOCLIP_SITE - Q.BASE : Q.NOCLIP_SITE - Q.BASE + 2] = Q.NOCLIP_ORIG
    b[Q.NOENC_SITE - Q.BASE : Q.NOENC_SITE - Q.BASE + 2] = Q.NOENC_ORIG
    return bytes(b)


class QaDebug(unittest.TestCase):
    def test_off_is_identity(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            b = fake_bin()
            self.assertIs(Q.patch(b), b)

    def test_non_qa_tag_refuses(self):
        with (
            mock.patch.dict(os.environ, {"ED_DEBUG_QA": "1", "ED_BUILD_TAG": "ss-ed3"}, clear=True),
            self.assertRaises(SystemExit),
        ):
            Q.patch(fake_bin())

    def test_speed_doubles(self):
        with mock.patch.dict(
            os.environ, {"ED_DEBUG_QA": "1", "ED_BUILD_TAG": "qa-debug"}, clear=True
        ):
            out = Q.patch(fake_bin())
        ox = Q.SPEED_X - Q.BASE
        oy = Q.SPEED_Y - Q.BASE
        self.assertEqual(struct.unpack(">d", out[ox : ox + 8])[0], 512.0)
        self.assertEqual(struct.unpack(">d", out[oy : oy + 8])[0], 384.0)

    def test_wrong_original_stops(self):
        with (
            mock.patch.dict(
                os.environ, {"ED_DEBUG_QA": "1", "ED_BUILD_TAG": "qa-debug"}, clear=True
            ),
            self.assertRaises(AssertionError),
        ):
            Q.patch(bytes(0x9000))


if __name__ == "__main__":
    unittest.main()


class NoClip(unittest.TestCase):
    def test_noclip_patched_and_switchable(self):
        env = {"ED_DEBUG_QA": "1", "ED_BUILD_TAG": "qa-debug"}
        o = Q.NOCLIP_SITE - Q.BASE
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(Q.patch(fake_bin())[o : o + 2], Q.NOCLIP_NEW)
        with mock.patch.dict(os.environ, {**env, "ED_QA_NOCLIP": "0"}, clear=True):
            self.assertEqual(Q.patch(fake_bin())[o : o + 2], Q.NOCLIP_ORIG)
