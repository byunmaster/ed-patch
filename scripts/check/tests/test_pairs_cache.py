"""check_names.cached — 게이트 한 번 안에서 어댑터 pairs() 를 한 번만 돌리는지."""

import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_names


def _fake():
    m = types.SimpleNamespace(calls=0, TITLE="eiyuu")

    def pairs():
        m.calls += 1
        return [("a", "原文", "우리", "dialog"), ("b", "原", None, "slot")]

    m.pairs = pairs
    return m


class PairsCache(unittest.TestCase):
    def test_칸이_있으면_한_번만_만든다(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["CHECK_PAIRS_CACHE"] = d
            try:
                m = _fake()
                a = check_names.cached(m, "g")
                b = check_names.cached(m, "g")
                self.assertEqual(a.pairs(), b.pairs())
                self.assertEqual(m.calls, 1)
                self.assertEqual(a.TITLE, "eiyuu")  # 다른 속성은 그대로 넘긴다
            finally:
                del os.environ["CHECK_PAIRS_CACHE"]

    def test_칸이_없으면_원래대로(self):
        os.environ.pop("CHECK_PAIRS_CACHE", None)
        m = _fake()
        self.assertIs(check_names.cached(m, "g"), m)

    def test_어댑터_없음은_그대로_None(self):
        os.environ["CHECK_PAIRS_CACHE"] = tempfile.gettempdir()
        try:
            self.assertIsNone(check_names.cached(None, "g"))
        finally:
            del os.environ["CHECK_PAIRS_CACHE"]


if __name__ == "__main__":
    unittest.main()
