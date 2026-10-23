"""대사 캡처 1차 검수 — 빈 창·잡음·정상 글을 합성 그림으로 가른다."""

import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dialog_review


def img(fn):
    a = np.zeros((82, 320, 3), np.uint8)
    fn(a)
    p = os.path.join(tempfile.mkdtemp(), "x.png")
    Image.fromarray(a).save(p)
    return p


class TestDialogReview(unittest.TestCase):
    def test_blank_window(self):
        self.assertEqual(dialog_review.review(img(lambda a: None), 0), ["빈창"])

    def test_noise_window(self):
        def fn(a):
            a[np.random.default_rng(1).random(a.shape[:2]) < 0.5] = 255

        self.assertEqual(dialog_review.review(img(fn), 0), ["잡음"])

    def test_text_rows(self):
        def fn(a):
            for y0 in (20, 34, 48):
                a[y0 : y0 + 10, 30:200] = 255

        self.assertEqual(dialog_review.review(img(fn), 0), [])

    def test_too_many_rows(self):
        def fn(a):
            for y0 in (4, 16, 28, 40, 52):
                a[y0 : y0 + 9, 30:110] = 255

        self.assertEqual(dialog_review.review(img(fn), 0), ["줄많음"])


if __name__ == "__main__":
    unittest.main()
