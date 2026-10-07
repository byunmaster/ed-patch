"""⑨ 고유명사 뒤 조사 받침 — 틀린 꼴을 실제로 잡는가(검사기가 조용히 비어 있지 않은가, 체크리스트 4-B)."""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import check_text


class NameJosa(unittest.TestCase):
    def rows(self, *kr):
        return [("p", i, "", t) for i, t in enumerate(kr)]

    def test_맞는_조사는_통과(self):
        ok = self.rows("세리오스가 갔다.", "세리오스는 웃었다.", "세리오스를 불렀다.", "세리오스와 함께")
        self.assertEqual(check_text.axis_name_josa(ok), [])

    def test_틀린_조사는_잡힌다(self):
        bad = self.rows("세리오스이 갔다.", "세리오스은 웃었다.", "세리오스을 불렀다.", "세리오스과 함께")
        self.assertEqual(len(check_text.axis_name_josa(bad)), 4)

    def test_으로_로(self):
        # 받침 없음 → 로 · ㄹ 받침 → 로 · 그 밖 받침 → 으로
        ok = self.rows("세리오스로 간다.")
        self.assertEqual(check_text.axis_name_josa(ok), [])
        bad = self.rows("세리오스으로 간다.")
        self.assertEqual(len(check_text.axis_name_josa(bad)), 1)

    def test_어미는_안_본다(self):
        """이름 뒤가 아니면 `먹는`·`있는` 같은 어미를 조사로 오인하지 않는다."""
        self.assertEqual(check_text.axis_name_josa(self.rows("먹는 사람이 있는 곳")), [])


class SpeakerWidth(unittest.TestCase):
    def test_이름_칸_폭(self):
        ok = [("p", 0, "", "%c세리오스%c\n안녕.%c")]
        self.assertEqual(check_text.axis_speaker_width(ok), [])
        long = [("p", 0, "", "%c" + "가" * 15 + "%c\n안녕.%c")]
        self.assertEqual(len(check_text.axis_speaker_width(long)), 1)

    def test_문장_속_주입_자리는_이름칸이_아니다(self):
        ok = [("p", 0, "", "%c" + "가" * 15 + "%c이(가) 나타났다.")]
        self.assertEqual(check_text.axis_speaker_width(ok), [])


if __name__ == "__main__":
    unittest.main()
