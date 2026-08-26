"""`backtrans.py` — 되돌려 맞추기. **망 없이** 가짜 응답으로 돈다.

🔴 이 엔진이 하는 일은 하나다 — **어긋난 것이 바닥에 오는가.** 그래서 시험도 그것만 본다.
"""

import io
import json
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.text import backtrans as B


def fake(payloads, fail=None):
    """DeepL 응답을 흉내 낸다. `fail` 이 있으면 그 횟수만큼 HTTPError 를 낸다."""
    state = {"n": 0}

    def opener(req):
        if fail and state["n"] < fail[0]:
            state["n"] += 1
            raise urllib.error.HTTPError(req.full_url, fail[1], "x", {}, None)
        body = json.dumps({"translations": [{"text": t} for t in payloads.pop(0)]})
        return io.BytesIO(body.encode())

    return opener


class Norm(unittest.TestCase):
    def test_flatten_and_norm(self):
        self.assertEqual(B.flatten("가\n나\f다　라"), "가 나 다 라")
        # 문장부호·공백은 대조에서 뺀다 — 표기 흔들림에 점수가 휘둘리지 않게
        self.assertEqual(B.norm("大丈夫よ、お母さん。"), B.norm("大丈夫よ お母さん"))


class Rank(unittest.TestCase):
    def test_worst_comes_first(self):
        pairs = [
            ("a", "ラグピック村", "라그픽 마을"),
            ("b", "大丈夫よ、お母さん。", "괜찮아요, 어머니."),
            ("c", "明日の準備はできているの？", "내일 준비는 다 됐니?"),
        ]
        cache = {
            "라그픽 마을": "ラグピック村",  # 딱 맞음
            "괜찮아요, 어머니.": "大丈夫ですよ、お母さん",  # 조금 다름
            "내일 준비는 다 됐니?": "今日の天気はとても良いですね",  # 딴소리
        }
        got = B.rank(pairs, cache)
        # ⚠ **순위만 본다.** 절대값에 선을 그으면 안 된다 — 문서가 「점수는 순위로 읽는다」고
        #   말하는데 시험이 임계값을 조이면 서로 어긋난다(0.3 으로 그었다가 0.31 에 깨졌다).
        self.assertEqual([x[1] for x in got], ["c", "b", "a"])  # 딴소리 → 조금 다름 → 딱 맞음
        self.assertLess(got[0][0], got[1][0])
        self.assertLess(got[1][0], got[2][0])
        self.assertEqual(got[-1][0], 1.0)  # 딱 맞으면 1.0 — 이건 정의라 고정이다

    def test_uncached_dropped(self):
        self.assertEqual(B.rank([("a", "x", "가")], {}), [])

    def test_short_flagged_and_droppable(self):
        """짧으면 표기 하나에 점수가 흔들린다 — 실측 `かんぱ〜い！` vs `乾杯～！` 는 0.00."""
        pairs = [
            ("a", "かんぱ〜い！", "건배〜!"),
            ("b", "明日の準備はできているの？", "내일 준비 됐니?"),
        ]
        cache = {"건배〜!": "乾杯～！", "내일 준비 됐니?": "明日の準備はできてる？"}
        self.assertTrue(B.is_short("かんぱ〜い！", "乾杯～！"))
        self.assertFalse(B.is_short(pairs[1][1], cache[pairs[1][2]]))
        self.assertEqual(len(B.rank(pairs, cache)), 2)  # 기본은 남긴다
        kept = B.rank(pairs, cache, drop_short=True)
        self.assertEqual([x[1] for x in kept], ["b"])


class Fetch(unittest.TestCase):
    def test_only_missing_and_deduped(self):
        pairs = [("a", "x", "같은 말"), ("b", "y", "같은 말"), ("c", "z", "다른 말")]
        cache = {}
        sent = [["A", "B"]]
        # 같은 문안이 두 자리에 있어도 **한 번만** 보낸다
        B.fetch(pairs, cache, "k", "KO", "JA", opener=fake(sent))
        self.assertEqual(cache, {"같은 말": "A", "다른 말": "B"})

    def test_soft_error_retries(self):
        B._RETRY = (0, 0, 0)  # 시험에서는 안 기다린다
        cache = {}
        B.fetch([("a", "x", "가")], cache, "k", "KO", "JA", opener=fake([["A"]], fail=(2, 429)))
        self.assertEqual(cache, {"가": "A"})

    def test_hard_error_raises(self):
        with self.assertRaises(RuntimeError):
            B.fetch([("a", "x", "가")], {}, "k", "KO", "JA", opener=fake([["A"]], fail=(1, 403)))


if __name__ == "__main__":
    unittest.main()
