"""월드 스테이트 신선도(`ss_shop_sweep.world_fresh`) — 이미지 지문이 다르거나 `.key` 가 없으면 **거짓**이다.

실측 근거: 옛 이미지로 만든 스테이트의 ED.BIN RAM 에 조사 훅이 없어 전투 로그가 병기 그대로 찍혔다(2026-11-05 오진).
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ss_shop_sweep as S


class WorldFresh(unittest.TestCase):
    def _state(self, d, key):
        p = os.path.join(d, "w.state")
        if key is not None:
            with open(p + ".key", "w") as f:
                f.write(key + "\n")
        return p

    def test_same_key_is_fresh(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "image_key", return_value="abc"):
            self.assertTrue(S.world_fresh(self._state(d, "abc"), "x.cue"))

    def test_other_key_is_stale(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "image_key", return_value="abc"):
            self.assertFalse(S.world_fresh(self._state(d, "old"), "x.cue"))

    def test_missing_key_is_stale(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "image_key", return_value="abc"):
            self.assertFalse(S.world_fresh(self._state(d, None), "x.cue"))


if __name__ == "__main__":
    unittest.main()
