"""코드표 회귀 — **원본 없이 돈다**. 🔴 카나 블록이 한 칸 밀리면 빌드도 검사도 통과하고 화면에서만 틀린다(주인공이 「ジヤラオ」로 읽혔다)."""

import unittest

import _path  # noqa: F401
import textenc


class TestKana(unittest.TestCase):
    def test_닻(self):
        m = textenc.kana_map()
        self.assertEqual(m[0x3F], "ぁ")  # 히라가나 첫 코드
        self.assertEqual(len(textenc.JIS_HIRA) - 4, 79)  # ぢ ゎ ゐ ゑ 가 빠진다
        self.assertEqual(len(textenc.JIS_KATA) - 4, 82)  # ヂ ヮ ヰ ヱ 가 빠진다(ヲ·ヴ 는 남는다)

    def test_카나_뒤_첫_한자_코드는_0xE0(self):
        """ED3 는 0xDF, ED4 는 0xE0 — 두 디스크의 탈락 집합이 다르다는 증거. 이 숫자가 어긋나면 한자 전부가 한 칸씩 밀린다."""
        self.assertEqual(max(textenc.kana_map()) + 1, 0xE0)

    def test_탈락한_글자는_표에_없다(self):
        got = set(textenc.kana_map().values())
        for ch in textenc.DROPPED["hira"] + textenc.DROPPED["kata"]:
            self.assertNotIn(ch, got)
        self.assertIn("ヲ", got)
        self.assertIn("ヴ", got)


class TestDecode(unittest.TestCase):
    def test_제어코드와_종결(self):
        self.assertEqual(textenc.decode([0x3F, 0x02, 0xFFFF, 0x3F]), "ぁ。")

    def test_모르는_코드는_조용히_안_지운다(self):
        self.assertIn("�7fe", textenc.decode([0x7FE]))

    def test_정본이_카나_블록을_덮지_않는다(self):
        kana = textenc.kana_map()
        with open(textenc.charmap_path(), encoding="utf-8") as f:
            import json

            doc = json.load(f)
        clash = [k for k in doc["map"] if int(k, 16) in kana]
        self.assertEqual(
            clash, [], "정본(charmap.json)에 카나 블록 코드가 있다 — 계산값과 이중 정의"
        )


class TestEquivalenceWithEd3(unittest.TestCase):
    """이전 대응 — ps1-ed3 의 `textenc`(ED4 몫)와 같은 코드표를 내야 옮겨 탈 수 있다(파일이 있을 때만)."""

    def test_ed4_코드표_동치(self):
        import importlib.util
        import os

        path = os.path.join(
            os.path.dirname(textenc.__file__), "..", "..", "ps1-ed3", "tools", "textenc.py"
        )
        if not os.path.exists(path):
            self.skipTest("games/ps1-ed3 없음")
        spec = importlib.util.spec_from_file_location("ed3_textenc_ref", path)
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
        self.assertEqual(ref.charmap("ed4"), textenc.charmap())


if __name__ == "__main__":
    unittest.main()
