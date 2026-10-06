"""조판 검사 게이트 — 씬 대사 · 시스템·전투(로그성) 문장 위반 0 유지.

🔴 마스터 09-30 번복 — 로그성 메시지(시스템·전투)도 **어절 단위 개행**(09-27 「글자 단위로 둔다」를 대체).
10-07 런타임 후킹(`hook.wordck`)으로 구현했고 `typeset_check.wrap` 이 그 런타임을 흉내 낸다. 그래서
①고아 부호 ②빈 줄 ③줄 첫 칸 공백 ④낱말 가운데 끊김을 **전 영역에서** 실패로 친다
(④는 이제 한 줄보다 긴 낱말에서만 날 수 있다).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import typeset_check as T

# 알려진 위반 — 새로 넣으려면 이유를 적는다.
#   (09-27 의 전투 32건(①11·③21)은 `hook._wrap_asm`(①③, 09-27)이 이미 막고 있었는데 검사기가 원판 넘김을
#   흉내 내고 있어 남아 보였다 — 10-07 `wrap()` 을 런타임 그대로로 고치며 0 이 됐다)
KNOWN_SYSTEM: set[str] = set()
KNOWN_BATTLE: set[str] = set()


class Typeset(unittest.TestCase):
    def test_wrap_blank_line_after_full_line(self):
        lines, _ = T.wrap("가" * 13 + "\n나")
        self.assertEqual(lines, ["가" * 13, "", "나"])

    def test_wrap_mid_word_is_flagged(self):
        lines, cuts = T.wrap("가나다라마바사아자차카타파하")
        self.assertIn("④", " ".join(T.problems(lines, cuts)))

    def test_wrap_word_unit(self):
        """어절이 이 줄에 안 들어가면 어절째 넘긴다 — 열 10 + 4글자 = 14칸."""
        lines, cuts = T.wrap("가" * 9 + " 나다라마")
        self.assertEqual(lines, ["가" * 9 + " ", "나다라마"])
        self.assertEqual(T.problems(lines, cuts), [])
        lines, _ = T.wrap("가" * 8 + " 나다라마")  # 13칸 — 들어간다
        self.assertEqual(len(lines), 1)

    def test_wrap_hangs_punct_and_eats_space(self):
        lines, cuts = T.wrap("가" * 13 + ". 나")
        self.assertEqual(
            lines, ["가" * 13 + ".", "나"]
        )  # 부호는 매달고, 넘긴 줄 첫 공백은 칸을 안 먹는다
        self.assertEqual(T.problems(lines, cuts), [])
        lines, _ = T.wrap("가" * 9 + " 나다라.")  # 매다는 부호는 어절 길이에 안 센다 — 13칸
        self.assertEqual(len(lines), 1)

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

    def test_battle_no_new_violation(self):
        bt, _n, _mon = T.battle_rows()
        bad = {k for k, _l, p in bt if p}
        self.assertLessEqual(bad, KNOWN_BATTLE, bad - KNOWN_BATTLE)


if __name__ == "__main__":
    unittest.main()
