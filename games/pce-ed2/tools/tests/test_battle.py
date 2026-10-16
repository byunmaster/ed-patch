"""전투 문구 — 승리 보상 줄 · 나타남 줄 · `{1B}` 이름 줄이 정본 틀로 바뀐다(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import battle
import font
import msgs

EP = bytes.fromhex("0d4550601585" "1b06" "0e79b2ddc4" "0f1404" "60" "8a6c93be" "0d")
GOLD = bytes.fromhex("1585" "1b06" "60" "474f4c44" "1404" "60" "8ee8c693fcdacfbcc0" "12" "0d")
APPEAR = bytes.fromhex("0ebdd7b2d10f618cbbdac0" "12")  # 「スライムが現れた」 — 끝은 `12`


class Battle(unittest.TestCase):
    def test_EP_줄은_06_스타일을_빼고_글만_바뀐다(self):
        tab = font.GlyphTable()
        out = msgs.special(EP, tab)
        self.assertIsNotNone(out)
        self.assertNotIn(b"\x06", out)  # 06 안에서 한글이 깨졌다(10-13 화면)
        self.assertTrue(out.startswith(b"\r") and out.endswith(b"\r"))
        self.assertEqual(sorted(tab.chars), sorted("ＥＰ포인트획득"))

    def test_GOLD_줄은_원문_GOLD_바이트를_둔다(self):
        tab = font.GlyphTable()
        out = msgs.special(GOLD, tab)
        self.assertIsNotNone(out)
        self.assertIn(b"GOLD", out)
        self.assertEqual(sorted(tab.chars), sorted("를얻었다"))
        self.assertTrue(out.endswith(b"\x12\r"))

    def test_모르는_줄은_안_건드린다(self):
        self.assertIsNone(msgs.special(GOLD.replace(b"GOLD", b"GOLE"), font.GlyphTable()))

    def test_나타남_줄은_조사를_풀어_정본_문장으로(self):
        tab = font.GlyphTable()
        out = battle._appear(APPEAR, tab, set())
        self.assertTrue(out.endswith(b"\x12"))
        self.assertEqual(sorted(tab.chars), sorted(set("슬라임이 나타났다") - {" "}))

    def test_전투_1B_줄은_이름_자리로_읽는다(self):
        tab = font.GlyphTable()
        raw = bytes.fromhex("1b" "c98d558c82" "0d")  # {1B}の攻撃
        out = msgs.translate(raw, tab, battle=True)
        self.assertIsNotNone(out)
        self.assertTrue(out.startswith(b"\x1b"))
        self.assertEqual(sorted(tab.chars), sorted("의 공격".replace(" ", "")))
        self.assertEqual(msgs.battle_josa("을(를) 해치웠다."), "를 해치웠다.")
        self.assertEqual(msgs.battle_josa("의 공격"), "의 공격")
        # 일반 문맥(1B = 수)에서도 조각 맞춤(`segments`)이 「の攻撃」 조각을 정본으로 바꾼다 — 같은 바이트
        self.assertEqual(msgs.translate(raw, font.GlyphTable()), out)

    def test_조각_맞춤은_이름_자리표와_줄바꿈_사이_조각을_정본으로(self):
        use = bytes.fromhex("0c1389" "82cd" "1a" "0d" "1a" "82f0" "8e6782c182bd" "12" "0d")  # {0C}{13 89}は{1A}/{1A}を使った{12}/
        tab = font.GlyphTable()
        out = msgs.translate(use, tab)
        self.assertIsNotNone(out)
        self.assertIn(bytes([font.JOSA_LEAD, font.TRAIL0 + 0]), out)  # 이름 뒤 「は」 = 동적 조사 토큰(은/는)
        self.assertIn(bytes([font.JOSA_LEAD, font.TRAIL0 + 2]), out)  # 「を」 = 을/를
        self.assertTrue(out.startswith(b"\x0c\x13\x89") and out.endswith(b"\x12\r"))
        self.assertIsNone(msgs.translate(bytes.fromhex("82cd82cd"), font.GlyphTable()))  # 자리표 없는 문장은 조각 맞춤을 안 한다


if __name__ == "__main__":
    unittest.main()
