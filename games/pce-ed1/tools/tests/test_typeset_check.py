"""조판 검사 게이트 — 씬 대사 · 시스템·전투(로그성) 문장 위반 0 유지.

🔴 마스터(09-27, 두 번째 판정) — 로그성 메시지(시스템·전투)는 **어절 단위 개행을 하지 않는다.**
인터프리터가 글자 단위로 접는 대로 둔다(「…책 / 을」 같은 낱말 가운데 끊김 = ④ 는 **허용**).
막는 건 ①**고아 부호**(부호만 남아 다음 줄로 넘어감)과 ③**줄 첫 칸 공백**뿐이다 — 화면에서 진짜
이상해 보이는 자리는 이 둘이지 ④가 아니다. 그래서 이 게이트는 ①③만 실패로 치고 ④는 무시한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import typeset_check as T

LOG_IGNORE = "④"  # 로그성(시스템·전투) 영역에서 무시하는 규칙 — 어절/낱말 가운데 끊김


def _log_bad(probs):
    return [p for p in probs if not p.startswith(LOG_IGNORE)]


# 알려진 위반 — 새로 넣으려면 이유를 적는다(①③만, ④는 이제 위반이 아니라 여기 안 올라온다).
KNOWN_SYSTEM: set[str] = set()

# 전투 32건(①11·③21) — 마스터(09-27) 「①고아 부호·③줄 첫 칸 공백을 막을 방법을 봐 달라」에 대한
# 조사 결과: 자동 줄바꿈은 `$6D95`(뱅크 0x6C, `LDA $38BB / CMP $99 / BCC.. / JSR $6AB5`)가 다 정한다.
# 호출부 `$6720`(뱅크 0x6C)이 부르기 **직전**에 다음 글자 2B 를 `$F9:$F8`에 담아 두므로, ①(부호면 줄을
# 안 끊고 매단다)은 `$F9:$F8`을 부호 코드(F024=! F025=, F027=. F02E=?)와 비교하는 짧은 패치로 될 걸로
# 보인다. ③(줄이 막 넘어간 자리의 공백을 삼킨다)은 그리기(JSR 계열 `$6AB9`/`$7047`)를 **건너뛰고
# `$6712` 루프 머리로 되돌아가야** 해서 스택 프레임을 접는 손질이 필요해 ①보다 손이 크다.
# 🔴 이 루틴은 뱅크 0x6C 안에 있고 여유 11B(6D95~6D9F)뿐이라 **자리가 없다** — 반각 작업이 코드
# 자리를 새로 트면(마스터 09-27, 같은 자리 공유) 그때 같이 넣는다. 그때까지는 이 32건이 알려진 위반.
KNOWN_BATTLE = {
    "013d412336a99a69", "0d5d7c992477e5a6", "0df289703b317fb6", "17f1a0d64efa7215",
    "1c56c7d543cc28b6", "27494547a81fc4b6", "3307170c81c411d0", "363ef40a9138180a",
    "39319dc86d43baf8", "3e4dfb2d7bf0a936", "45c89873c364d917", "4d0fd5868fb4db64",
    "5b04628657f1c350", "5ebcc60fa6f84f00", "670907cbe34cf3b2", "8cb8aad38eff9162",
    "90208fd8142ebbd0", "9187ce62e3739187", "9d054c39dda31d90", "a0e50ce03a6eb385",
    "a3b83bb719732ed2", "ae88fa7478fcfdcc", "b8b3aa1b2685ea57", "b91f98cbf6119d1f",
    "c49b43f3b867de28", "cd86fcfc90e29259", "cdeb58caeceeaf8b", "ce7ddcfa19a1e709",
    "d6cbc40dc6b2b328", "dadf341b3ffc282c", "de6807bf645429f8", "f11569f308bdcb80",
}


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
        bad = {c.name for c, _l, p in rows if _log_bad(p)}
        self.assertLessEqual(bad, KNOWN_SYSTEM, bad - KNOWN_SYSTEM)

    def test_battle_no_new_violation(self):
        """전투 — ①③(고아 부호·줄 첫 칸 공백)만 실패로 친다(마스터 09-27, ④ 는 로그 영역 전부 허용)."""
        bt, _n, _mon = T.battle_rows()
        bad = {k for k, _l, p in bt if _log_bad(p)}
        self.assertLessEqual(bad, KNOWN_BATTLE, bad - KNOWN_BATTLE)


if __name__ == "__main__":
    unittest.main()
