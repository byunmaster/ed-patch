"""말투 경보 양성 대조 — 잡아야 할 꼴을 잡고, 멀쩡한 꼴은 안 잡는다(마스터 11-13 밤샘)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_register as cr


class Register(unittest.TestCase):
    def test_honor_in_plain_flagged(self):
        for s in ["그 이상은 못 가지시는 모양이야.", "너도 이제 가시지.", "벌써 가시네."]:
            self.assertTrue(cr.honor_mixed(s), s)

    def test_clean_not_flagged(self):
        for s in [
            "그 이상은 못 가지는 모양이야.",
            "또 오세요.",  # 해요체 — 반말이 아니다
            "이 나라에 평화를 되찾읍시다.",  # 청유
            "어서 오십시오.",
            "그분은 제르만님이시다.",
        ]:
            self.assertFalse(cr.honor_mixed(s), s)

    def test_length_collapse(self):
        self.assertTrue(cr.too_short("あ" * 40, "가" * 5))
        self.assertFalse(cr.too_short("あ" * 40, "가" * 30))
        self.assertFalse(cr.too_short("あ" * 8, "가"))  # 짧은 원문은 안 잰다

    def test_tilde_over(self):
        self.assertTrue(cr.tilde_over("こけっ～ !?", "꼬꼬댁～～!?"))
        self.assertFalse(cr.tilde_over("わーい", "와～"))  # ー 하나 → ～ 하나는 1:1
        self.assertTrue(cr.tilde_over("わーい", "와～～"))  # ー 하나에 ～～ 는 늘림
        self.assertFalse(cr.tilde_over("こけっ～ !?", "꼬꼬댁～!?"))
        self.assertFalse(cr.tilde_over("う～む", "그러나"))  # 줄임은 이 검사가 아니다

    def test_dropped_marks(self):
        self.assertIn("E", cr.dropped("それは残念です･･･ ･･･。", "그거 아쉽습니다…"))  # 점 6개 = …… 둘
        self.assertEqual([], cr.dropped("それは残念です･･･ ･･･。", "그거 아쉽습니다……"))
        self.assertIn("Q", cr.dropped("やあ 客人 元気そうだな？", "여어 손님, 건강해 보이는군."))
        self.assertEqual([], cr.dropped("やあ 客人 元気そうだな？", "여어 손님, 건강해 보이는군?"))
        self.assertIn("X", cr.dropped("やめろ !! だめだ !!", "그만해! 안 돼."))
        self.assertIn("T", cr.dropped("そうなの～", "그렇구나"))
        self.assertEqual([], cr.dropped("わーい ありがとう。", "와～ 고마워."))  # ー 는 세지 않는다
        self.assertEqual([], cr.dropped("【男】 あ、そう。 {p:0} え？", "응"))  # 이어진 스트림은 안 잰다
        self.assertEqual([], cr.dropped("そうなの～ ", "그렇구나<0f:0123>"))  # 점프

    def test_expand_call_and_jump(self):
        st = {"aaaa": {"ours": "찰싹!!\x0c"}, "bbbb": {"ours": "뒷 줄."}}
        self.assertEqual(cr._expand("앞<10:aaaa>", st).replace("\x0c", ""), "앞 찰싹!! ")
        self.assertEqual(cr._expand_jump("앞<0f:bbbb>", st), "앞뒷 줄.")

    def test_qx_order(self):
        self.assertTrue(cr.qx_order_changed("なんだと !?", "뭐라고?!"))  # 원문 !? 를 ?! 로 뒤집음
        self.assertTrue(cr.qx_order_changed("なんだと ？!", "뭐라고!?"))
        self.assertFalse(cr.qx_order_changed("なんだと !?", "뭐라고!?"))
        self.assertFalse(cr.qx_order_changed("セリオス ･ ･ ･ ？ !?", "세리오스…?!?"))  # 원문 ？ + !? 덩어리
        self.assertIn("O", cr.dropped("なんだと !?", "뭐라고 하는 거냐?!"))


if __name__ == "__main__":
    unittest.main()
