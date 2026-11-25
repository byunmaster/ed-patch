import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_comma as K
import patch_scn


def kinds(text):
    return {k for k, v in K.classify("t", text).items() if v}


class Comma(unittest.TestCase):
    def test_topic_comma_is_found(self):
        self.assertIn("주제 뒤 쉼표", kinds("파렌 왕국은, 작은 나라였다."))

    def test_leading_adverb_comma_is_found(self):
        self.assertIn("부사어 뒤 쉼표", kinds("처음에는, 좋았다."))
        self.assertIn("부사어 뒤 쉼표", kinds("그랬다.\n실은, 몰랐다."))

    def test_rule_9_short_front_clause_is_found(self):
        self.assertIn("⑨ 쉼표 규칙이 더 뺄 것", kinds("그건 맞는데, 좀 달라."))

    def test_kept_classes_are_not_flagged(self):
        for t in ("란도, 플로라, 레스가 왔다.", "왕자님, 이쪽입니다.", "그래, 알겠다.", "아이고, 놀랐어."):
            self.assertFalse(kinds(t) & set(K.FAIL + ("연결 어미(고·며·서)",)), t)

    def test_build_rule_removes_what_the_gate_looks_for(self):
        self.assertEqual(patch_scn.comma_rule("처음에는, 좋았다."), "처음에는 좋았다.")
        self.assertEqual(patch_scn.comma_rule("그는 실은, 아니다"), "그는 실은, 아니다")  # 문장 가운데는 안 건드린다

    def test_rule_10_11_then_and_short_connectives(self):
        r = patch_scn.comma_rule
        self.assertEqual(r("그럼, 하루라도 빨리"), "그럼 하루라도 빨리")
        for keep in ("그럼, 왕자님.", "그럼, 몸조리 잘하세요.", "그럼 그럼, 그래야 내 손자지."):  # 부르는 말 앞 · 작별 · 맞장구
            self.assertEqual(r(keep), keep)
        self.assertEqual(r("탈 없이 끝났고, 이제 성에는"), "탈 없이 끝났고 이제 성에는")
        self.assertEqual(r("나이가 들어서, 새로 넘겼네"), "나이가 들어서 새로 넘겼네")
        for keep in ("아이고, 놀랐어.", "그렇고말고, 신디.", "들지 말고, 들려면 마시지 마라"):
            self.assertEqual(r(keep), keep)
        self.assertEqual(r("가나다라마바사아자차카타파 하고, 타"), "가나다라마바사아자차카타파 하고, 타")  # 앞 절 12음절↑ 은 남김


if __name__ == "__main__":
    unittest.main()
