"""조판 검사 게이트 — 씬 대사 · 시스템 문장 위반 0 유지."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import typeset_check as T

# 알려진 시스템 위반 — 새로 넣으려면 이유를 적는다.
# 「도구 사용 · 아무 일 없음」: 세리오스+7칸 도구는 「…고대 검의 책/을」로 낱말 가운데서 넘어간다. 마스터(09-27)
#   「강제 개행은 『사용했다.』 앞 하나만」 — 넘칠 때만 어절로 끊는 건 인터프리터 훅(어절 선측정)이 필요해 **전투 라운드**로.
KNOWN_SYSTEM = {"도구 사용 · 아무 일 없음"}


class Typeset(unittest.TestCase):
    def test_wrap_blank_line_after_full_line(self):
        lines, _ = T.wrap("가" * 13 + "\n나")
        self.assertEqual(lines, ["가" * 13, "", "나"])

    def test_wrap_mid_word_is_flagged(self):
        lines, cuts = T.wrap("가나다라마바사아자차카타파하")
        self.assertIn("④", " ".join(T.problems(lines, cuts)))

    def test_no_loss_invariant_catches_dropped_tail(self):
        T.assert_no_loss("가나 다라", ["가나", "다라"])  # 공백·개행만 다르면 통과
        with self.assertRaises(AssertionError):
            T.assert_no_loss("가나 다라마", ["가나", "다라"])  # 꼬리 「마」 소실

    def test_follow_jump_drops_dead_text(self):
        """`0F` 뒤 글은 아무도 안 읽는다 — 점프 자리 조각으로 잇는다(레벨업 「최대ＨＰ가+수치+→올랐다.」)."""
        raw = {1: "가{1F}{22}{04}{0F0200}죽은글", 2: " 올랐다."}.get
        self.assertEqual(T.clean(T.follow(raw, 1, {"1F}{22}{04": "9999"})), "가9999 올랐다.")

    def test_scene_compose_no_newline_after_full_line(self):
        """씬 대사의 ②(빈 줄)는 검사기가 아니라 **빌드(translate.compose)가 막는다** — 꽉 찬 13칸 줄 뒤엔
        `01` 을 안 넣는다(인터프리터가 스스로 넘긴다). 검사기는 그 보장을 믿고 씬의 ②를 건너뛰므로 여기서 못 박는다."""
        import font
        import messages as M
        import translate

        tbl, _ = font.build_table(font._order_canon())
        m = M.Message(0, 0, None, None, [("op", 0x00)])
        out = translate.compose(m, {"t": "가" * 13 + " 나다"}, tbl, {})
        full = font.encode("가" * 13, tbl)
        self.assertTrue(out.startswith(full))
        self.assertNotEqual(out[len(full)], 0x01, out.hex(" "))

    def test_scene_dialogue_has_no_violation(self):
        self.assertEqual(T.scene_rows(), [])

    def test_system_no_new_violation(self):
        rows = T.run()
        if rows is None:
            self.skipTest("원본 파생물 없음")
        bad = {c.name for c, _l, p in rows if p}
        self.assertLessEqual(bad, KNOWN_SYSTEM, bad - KNOWN_SYSTEM)


if __name__ == "__main__":
    unittest.main()
