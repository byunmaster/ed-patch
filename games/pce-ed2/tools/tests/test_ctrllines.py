"""제어 낀 줄 틀 번역(`ctrllines`) — 원본 없이 돈다(바이트는 실측에서 옮긴 짧은 조각)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctrllines
import font

# 「{16}聖なるつるぎ{18 A6 91 95 94}ました。」 꼴 — `18` + 글 4바이트(`94` 가 다음 바이트와 SJIS 쌍을 이룬다) 줄임꼴
EQUIP = bytes.fromhex("10301690b9c5d9c2d9 62 18 a6919594 f5 bccfbcc0 a1".replace(" ", ""))
HEADER = bytes.fromhex("16 0e 6ea8b0c5 14 0d".replace(" ", ""))  # 「{16}ディーナ…{14}」 + 줄바꿈 (머리줄)


class Skeleton(unittest.TestCase):
    def test_18은_14와_글_넉_바이트다(self):
        n = ctrllines.normalize(EQUIP)
        self.assertNotIn(0x18, n[:12])
        self.assertIn(bytes.fromhex("14a6919594f5"), n)

    def test_뼈대는_속도_제어를_뺀다(self):
        skel, ctrls, head = ctrllines.parse(EQUIP)
        self.assertEqual(head, bytes.fromhex("1030"))
        self.assertNotIn("{10", skel)
        self.assertIn("装備しました", skel)  # 18 인라인 글이 펴진다
        self.assertEqual([c[0] for c in ctrls], [0x16, 0x14])

    def test_열쇠는_결정적이다(self):
        a = ctrllines.key_of(ctrllines.parse(EQUIP)[0])
        self.assertEqual(a, ctrllines.key_of(ctrllines.parse(EQUIP)[0]))
        self.assertEqual(len(a), 12)


class Build(unittest.TestCase):
    def setUp(self):
        self.tab = font.GlyphTable()

    def test_틀이_제어를_그_자리에_낸다(self):
        out = ctrllines.build(EQUIP, "{@0}검{@1}을 장비했습니다.", self.tab)
        self.assertEqual(out[:2], bytes.fromhex("1030"))  # 맨 앞 말 속도는 그대로
        self.assertEqual(out[2], 0x16)
        self.assertIn(b"\x14", out)

    def test_구조_제어를_안_가리키면_오류(self):
        with self.assertRaises(ValueError):
            ctrllines.build(EQUIP, "{@0}검", self.tab)

    def test_버림은_명시한다(self):
        out = ctrllines.build(EQUIP, "{@0}검{!1}", self.tab)
        self.assertEqual(out.count(b"\x14"), 0)

    def test_번호_초과는_오류(self):
        with self.assertRaises(ValueError):
            ctrllines.build(EQUIP, "{@0}검{@1}{@5}", self.tab)

    def test_전각_공백은_공백_바이트(self):
        out = ctrllines.build(HEADER, "{@0}　{@1}\n", self.tab)
        self.assertEqual(out.count(b"\x60"), 3)

    def test_머리줄(self):
        out = ctrllines.build(HEADER, "{@0}디나{@1}\n", self.tab)
        self.assertEqual(out[0], 0x16)
        self.assertEqual(out[-1], 0x0D)


if __name__ == "__main__":
    unittest.main()
