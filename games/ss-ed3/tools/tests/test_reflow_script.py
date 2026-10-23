import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import reflow_script as R

NAMES = ["칸드 마스터"]


class ReflowPage(unittest.TestCase):
    def test_short_sentences_share_a_line(self):
        self.assertEqual(R.reflow_page("잘했다!\n역시 내 아들이야.", NAMES), "잘했다! 역시 내 아들이야.")

    def test_name_with_space_stays_on_one_line(self):
        out = R.reflow_page("그분이 바로\n칸드 마스터 님이시다. 정말로 대단하신 분이지.", NAMES)
        self.assertTrue(all("칸드 마스터" in x or "칸드" not in x for x in out.split("\n")), out)

    def test_single_line_page_unchanged(self):
        self.assertEqual(R.reflow_page("한 줄뿐이다.", NAMES), "한 줄뿐이다.")

    def test_narration_unchanged(self):
        t = "　어느 날의 일이다.\n　바람이 불었다."
        self.assertEqual(R.reflow(t, NAMES), t)

    def test_no_line_the_engine_would_fold(self):
        out = R.reflow_page("남의 방을 말없이\n엿보면 안 되겠지.", NAMES)
        self.assertTrue(all(R._fits(x) for x in out.split("\n")), out)

    def test_page_breaks_kept(self):
        out = R.reflow("첫째 쪽이다.\f둘째 쪽\n입니다.", NAMES)
        self.assertEqual(out.count("\f"), 1)


if __name__ == "__main__":
    unittest.main()
