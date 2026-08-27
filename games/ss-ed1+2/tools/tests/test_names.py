"""고유명사 파생 규칙 회귀 — **원본 없이 돈다**(레포 규약).

정본은 `shared/glossary` 하나고 사람이 읽는 판은 `docs/reference/manual-items-spells.md`
다. 표에는 정본에 없는 꼴이 섞여 들어오는데(변종 접미 · 주문서 · 반각 가나), 그걸
**규칙으로** 흡수한다 — 정본을 네 배로 불리지 않으려는 선택이다. 규칙이 틀리면 500칸이
한꺼번에 어긋나므로 여기서 못 박는다.

⚠ **표 자리와 원문 대조는 여기서 못 한다** — 원본 디스크가 필요하다. 그건 `patch_ui.py`
  의 `name_rows()` 가 매번 본다(앵커·개수·정본에 없는 이름).
"""

import os
import sys
import unittest
from typing import ClassVar

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(TOOLS))), "shared"))

import patch_ui
from glossary import table


def canon():
    m = {}
    for cat in ("item", "monster", "person", "place"):
        for k, v in table(cat).items():
            m.setdefault(k, v)
            m.setdefault(patch_ui._nname(k), v)
    return m


class Names(unittest.TestCase):
    def setUp(self):
        self.c = canon()

    def test_direct_hit_wins(self):
        self.assertEqual(patch_ui.name_kr("フラム", self.c), "프람")
        self.assertEqual(patch_ui.name_kr("レジナ", self.c), "레지나")

    def test_variant_suffix_is_halfwidth(self):
        """`スライムＢ` = 밑말 + **반각** B. 전각으로 붙이면 1바이트가 더 든다."""
        self.assertEqual(patch_ui.name_kr("スライムＢ", self.c), "슬라임B")
        self.assertEqual(patch_ui.name_kr("スライムＡ", self.c), "슬라임A")

    def test_spellbook_is_derived(self):
        self.assertEqual(patch_ui.name_kr("フラムの書", self.c), "프람의 서")

    def test_halfwidth_kana_and_middot_normalise(self):
        """표엔 반각 가나·중점 표기가 섞여 있다 — **맞출 때만** 눕힌다."""
        self.assertEqual(patch_ui._nname("ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝ"), "デスガーディアン")
        self.assertEqual(patch_ui.name_kr("ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝＡ", self.c), "데스 가디언A")

    def test_unknown_is_none_not_guess(self):
        """못 찾으면 **None** 이다 — 부르는 쪽이 실패로 친다(짐작해서 넣지 않는다)."""
        self.assertIsNone(patch_ui.name_kr("ゑゐんん", self.c))

    def test_placeholders_are_left_alone(self):
        """`ＭＧ１４` 류는 내부 자리표시자다 — 번역하면 오히려 틀린다."""
        self.assertIn("ＭＧ１４", patch_ui.NAME_SKIP)

    def test_tables_are_five_and_anchored(self):
        """자리는 손으로 적는다 — 앵커가 바뀌면 `name_rows` 가 실패해야 한다."""
        self.assertEqual(len(patch_ui.NAME_TABLES), 5)
        for _key, off, n, anchor, what in patch_ui.NAME_TABLES:
            self.assertTrue(off > 0 and n > 0 and anchor and what)

    def test_canon_covers_every_spell_in_the_manual(self):
        """매뉴얼에 오른 주문은 전부 정본에서 나온다 — 매뉴얼이 정본의 파생본이다."""
        for jp in ("レス", "レジナ", "リーフ", "ワプ", "サイレス"):
            self.assertIsNotNone(patch_ui.name_kr(jp, self.c), jp)


class Category(unittest.TestCase):
    """🔴 **범주를 먼저 본다** — 같은 원문이 범주에 따라 다른 것을 가리킨다.

    정본 머리말이 못 박은 계약인데 `name_rows` 가 표를 합쳐 읽어 **몬스터 표에 아이템
    이름(커스)이 들어가 있었다**(2026-08-24).
    """

    def test_kaasu_splits_by_category(self):
        self.assertEqual(patch_ui.name_kr("カース", patch_ui.name_canon("몬스터")), "카스")
        self.assertEqual(patch_ui.name_kr("カース", patch_ui.name_canon("아이템")), "커스")


class VariantSuffix(unittest.TestCase):
    """변종 접미는 **Ｅ 에서 안 끊긴다** — 소환 목록은 `毒大ガエルＨ` 까지 간다."""

    def test_suffix_beyond_e(self):
        c = patch_ui.name_canon("몬스터")
        for suf in "ABCDEFGH":
            self.assertEqual(patch_ui.name_kr(f"毒大ガエル{suf}", c), f"큰독개구리{suf}")


class MonsterCellSuffix(unittest.TestCase):
    """전투 이름 칸의 접미 — **Ｊ 까지 가고, 분열체엔 프라임이 붙는다**(2026-08-27 실측).

    좁게 잡아 두면 그 이름들만 조용히 일본어로 남는다(`ニュートハニーJ` · `赤スライムA'`).
    """

    MON: ClassVar = {"赤スライム": "붉은슬라임", "ゴドウィン２世": "고드윈2세"}

    def test_suffix_reaches_j(self):
        import patch_mon_names as M

        for a, b in (("Ａ", "A"), ("Ｇ", "G"), ("J", "J")):
            self.assertEqual(M.split_mark(f"赤スライム{a}", self.MON), ("붉은슬라임", b))

    def test_prime_marks_are_kept(self):
        import patch_mon_names as M

        self.assertEqual(M.split_mark("赤スライムA'", self.MON), ("붉은슬라임", "A'"))
        self.assertEqual(M.split_mark("赤スライムＡ''", self.MON), ("붉은슬라임", "A''"))
        self.assertEqual(M.split_mark("赤スライム'", self.MON), ("붉은슬라임", "'"))

    def test_whole_name_wins_over_suffix(self):
        """🔴 통짜부터 본다 — 끝 글자가 접미처럼 생긴 이름이 있다."""
        import patch_mon_names as M

        self.assertEqual(M.split_mark("ゴドウィン２世", self.MON), ("고드윈2세", ""))

    def test_unknown_is_none(self):
        import patch_mon_names as M

        self.assertEqual(M.split_mark("知らない名前Ａ", self.MON), (None, ""))


class ScnSuffix(unittest.TestCase):
    """🔴 **헤더 창의 규칙은 아직 모른다 — 대신 불변식을 지킨다**(2026-08-25 실기 실측).

    실측: 원판 `エルアスタ入口`(14B)는 온전한데 우리 `엘아스타 근처`(13B)·`엘아스타　입구`(14B)는
    둘 다 12B 로 잘렸다. 총 길이가 원인이 아니라 규칙을 아직 못 밝혔다.
    그래서 **「우리 지명이 원문보다 길지 않다」**만 지킨다 — 원판이 멀쩡히 그리는 걸 봤으니
    더 길게만 안 만들면 같은 그림이다. 접미에 공백을 못 넣는 이유도 이것이다.
    """

    def _rows(self, kr, jp):
        return [("/X", 0, 0, 0, 12, jp, kr, 0)]

    def test_shorter_than_original_is_fine(self):
        # 엘아스타(8B) ≤ エルアスタ(10B)
        self.assertEqual(patch_ui.scn_suffix_fit(self._rows("엘아스타", "エルアスタ")), [])

    def test_same_length_is_fine(self):
        # 크루즈마을(10B) = クルスの村(10B) — 원판이 `クルスの村入口` 를 온전히 그린다
        self.assertEqual(patch_ui.scn_suffix_fit(self._rows("크루즈마을", "クルスの村")), [])

    def test_longer_than_original_is_flagged(self):
        bad = patch_ui.scn_suffix_fit(self._rows("엘아스타시티", "エルアスタ"))
        self.assertEqual([(b[0], b[1], b[3]) for b in bad], [("엘아스타시티", 12, 10)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
