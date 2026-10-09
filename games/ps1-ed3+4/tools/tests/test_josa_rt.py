"""런타임 조사(F1)·조사 일치(F8)·일본어 잔존(F7)의 순수 부분 — 원본 없이 돈다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_jp_left
import josa_rt


class TestConvert(unittest.TestCase):
    def test_segment_head_josa_becomes_a_runtime_marker(self):
        """변수 바로 뒤(= 조각 첫머리)의 병기는 표지 — 실제 조사는 훅이 고른다."""
        for tok, i in (("을(를)", 2), ("은(는)", 0), ("이(가)", 1), ("과(와)", 3)):
            self.assertEqual(josa_rt.convert(f"{tok} 건네받았다."), josa_rt.MARKERS[i][0] + " 건네받았다.")

    def test_inner_josa_is_resolved_at_build_time(self):
        self.assertEqual(josa_rt.convert("쥬리오는 단검을(를) 받았다."), "쥬리오는 단검을 받았다.")
        self.assertEqual(josa_rt.convert("쥬리오는 방패을(를) 받았다."), "쥬리오는 방패를 받았다.")
        # 숫자 꼬리는 읽는 소리(9 구 → 를 · 1 일 → 을)
        self.assertEqual(josa_rt.convert("레스9을(를)"), "레스9를")
        self.assertEqual(josa_rt.convert("레스1을(를)"), "레스1을")

    def test_eu_ro_marker_plus_ro(self):
        self.assertEqual(josa_rt.convert("(으)로 간다."), josa_rt.MARKERS[4][0] + "로 간다.")
        self.assertEqual(josa_rt.convert("으로(로) 간다."), josa_rt.MARKERS[4][0] + "로 간다.")

    def test_unresolvable_stays_paired(self):
        """앞이 라틴이면 병기가 안전하다 — 잘못 고르지 않는다."""
        self.assertEqual(josa_rt.convert("abc을(를)"), "abc" + "을(를)")  # 첫머리가 아니라 앞이 있다

    def test_runtime_table_only_has_batchim_syllables(self):
        rc = josa_rt.runtime_chars(["철검", "방패", "회복약", "반지"])
        self.assertEqual(rc, {"검": 1, "약": 1})
        self.assertEqual(josa_rt.klass("달"), 2)  # ㄹ
        self.assertEqual(josa_rt.klass("1"), 2)
        self.assertEqual(josa_rt.klass("2"), 0)

    def test_runtime_data_needs_every_glyph(self):
        table = {m[0]: 0x600 + i for i, m in enumerate(josa_rt.MARKERS)}
        table.update({c: 0x700 + i for i, c in enumerate(josa_rt.baked_glyphs())})
        table[" "] = 0xE5
        with self.assertRaises(KeyError):  # 아이템 끝 글자가 배정표에 없다
            josa_rt.runtime(table, ["철검"], {d: 29 + int(d) for d in "0123456789"})
        table["검"] = 0x800
        d = josa_rt.runtime(table, ["철검"], {k: 29 + int(k) for k in "0123456789"})
        self.assertEqual(len(d["markers"]), 5)
        self.assertIn(0x800, d["blist"])


class TestJpLeft(unittest.TestCase):
    def test_has_jp(self):
        self.assertTrue(check_jp_left.has_jp("크리스の母"))
        self.assertTrue(check_jp_left.has_jp("短剣"))
        self.assertFalse(check_jp_left.has_jp("크리스 엄마"))
        self.assertFalse(check_jp_left.has_jp("그럼・말이야"))  # 말줄임 가운뎃점은 원문 부호


if __name__ == "__main__":
    unittest.main()


class TestTypesetRules(unittest.TestCase):
    def test_line_problems_ignores_the_first_line(self):
        import check_typeset_rules as C

        self.assertEqual(C.line_problems("…말줄임으로 시작"), [])
        # 🔴 말줄임은 「…」 전각 한 글자 — 점 셋 연속(`...`)이 문안에 남으면 실패(마스터 10-08)
        self.assertTrue(C.line_problems("그러니까..."))
        self.assertTrue(C.line_problems("아.... 그래"))
        self.assertEqual(C.line_problems("그러니까…"), [])
        self.assertTrue(C.line_problems("첫 줄\n,둘째 줄 머리 부호"))

    def test_name_echo_pattern(self):
        import check_name_echo as E

        rows = {("a", "m"): {0: {"kr": "크리스: 안녕"}, 1: {"kr": "크리스는 갔다"}, 2: {"kr": "크리스 「응」"}}}
        bad, n = E.echoes("ed3", rows)
        self.assertEqual(n, 3)
        self.assertEqual(len(bad), 2)  # 「크리스는」 은 이름 뒤가 표기 부호가 아니라 안 센다
