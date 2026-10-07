"""조판 검사기의 칸 모델 — 엔진(`$02:DE53`·`$DE73`)과 같게 세는가. **원본 없이** 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401
import typeset


def flow(s: str) -> tuple[list[str], list[str]]:
    return typeset.layout_px(typeset.expand(s, {}, {}))


def flow_cells(s: str) -> tuple[list[str], list[str]]:
    return typeset.layout_cells(typeset.expand(s, {}, {}))


class NewlineCursor(unittest.TestCase):
    def test_엔진_산술(self):
        # 마지막으로 쓴 칸 → 개행 뒤 칸 번호(그 줄의 끝 칸). 쪽 첫머리 $FF 는 15 로 간다(8비트 넘침).
        for c, want in [
            (0, 16),
            (5, 16),
            (16, 16),
            (17, 33),
            (33, 33),
            (51, 67),
            (67, 67),
            (0xFF, 15),
        ]:
            self.assertEqual(typeset.newline_cursor(c), want, c)


class LayoutCells(unittest.TestCase):
    """옛 칸 모델(가변 폭 꺼짐 — 정본 롬)."""

    def test_꽉_찬_줄_뒤_개행은_빈_줄이_아니다(self):
        lines, bad = flow_cells("가" * 17 + "\n나")
        self.assertEqual(lines, ["가" * 17, "나"])
        self.assertEqual(bad, [])

    def test_겹친_개행은_엔진이_무시한다(self):
        lines, bad = flow_cells("가\n\n나")
        self.assertEqual(lines, ["가", "나"])  # 화면엔 빈 줄이 없다
        self.assertEqual(bad, ["② 빈 줄(겹친 개행 — 엔진은 무시한다)"])

    def test_쪽_첫머리_개행은_16칸째로_튄다(self):
        lines, bad = flow_cells("\n나")
        self.assertEqual(lines, [" " * 16 + "나"])
        self.assertEqual(bad, ["② 쪽 첫머리 개행"])

    def test_기계적_넘침(self):
        # ①③ 은 엔진 훅(`kinsoku_carry`·`h_kspace`/`hb_kspace`)이 그리기 전에 고쳐 화면에 안 남는다
        # — 이 시뮬레이션도 같은 자리에서 고치므로 `bad` 가 비어야 한다(2026-09-27④ 판정).
        lines, bad = flow_cells("가" * 17 + ".")
        self.assertEqual(lines, ["가" * 16, "가."])  # 이전 줄 마지막 글자를 당겨 붙인다
        self.assertEqual(bad, [])
        lines, bad = flow_cells("가" * 17 + " 나")
        self.assertEqual(lines, ["가" * 17, "나"])  # 줄 첫 칸 공백은 칸을 안 쓰고 버린다
        self.assertEqual(bad, [])
        self.assertEqual(flow_cells("가" * 15 + " 나다")[1], ["④ 묶음 끊김"])  # 「나|다」— 훅 대상 아님

    def test_개행으로_넘긴_줄은_넘침이_아니다(self):
        self.assertEqual(flow_cells("가" * 16 + "\n.")[1], [])

    def test_네_줄을_넘으면_한_줄_올린다(self):
        lines, bad = flow_cells("\n".join("가나다라마"[i] * 17 for i in range(5)))
        self.assertEqual(len(lines), 5)
        self.assertEqual(bad, [])


class Layout(unittest.TestCase):
    """px 모델 — 공백·`. , ? !` 4px, 그 밖 8px, 줄 136px(17칸). 훅(`hook_vwf`)이 하는 대로 흘린다."""

    def setUp(self):
        self._vwf = typeset.VWF
        typeset.VWF = True

    def tearDown(self):
        typeset.VWF = self._vwf

    def test_꽉_찬_줄_뒤_개행은_빈_줄이_아니다(self):
        lines, bad = flow("가" * 17 + "\n나")
        self.assertEqual(lines, ["가" * 17, "나"])
        self.assertEqual(bad, [])

    def test_겹친_개행은_엔진이_무시한다(self):
        lines, bad = flow("가\n\n나")
        self.assertEqual(lines, ["가", "나"])  # 화면엔 빈 줄이 없다
        self.assertEqual(bad, ["② 빈 줄(겹친 개행 — 엔진은 무시한다)"])

    def test_쪽_첫머리_개행은_16칸째로_튄다(self):
        lines, bad = flow("\n나")
        self.assertEqual(lines, [" " * 16 + "나"])
        self.assertEqual(bad, ["② 쪽 첫머리 개행"])

    def test_기계적_넘침(self):
        # 가변 폭 훅에는 고아 부호 끌어오기가 없다 — 줄 첫머리가 된 부호는 그대로 ① 이다(조판기가 미리 막는다).
        lines, bad = flow("가" * 17 + ".")
        self.assertEqual(lines, ["가" * 17, "."])
        self.assertEqual(bad, ["① 고아 부호", "④ 묶음 끊김"])  # 같은 어절 가운데서 끊겼다
        lines, bad = flow("가" * 17 + " 나")
        self.assertEqual(lines, ["가" * 17, "나"])  # 줄 첫 칸 공백은 훅이 버린다
        self.assertEqual(bad, [])
        self.assertEqual(flow("가" * 16 + "나다")[1], ["④ 묶음 끊김"])  # 「나|다」

    def test_8px_글자가_줄_끝에_걸치면_5(self):
        lines, bad = flow("가" * 15 + " 나다")  # 120+4+8=132 → 다(8)가 132~140 — 칸 경계에 걸친다
        self.assertEqual(bad, ["⑤ 줄 끝 걸침"])

    def test_반각은_줄_끝_4px_에_든다(self):
        lines, bad = flow("가" * 16 + " .")  # 128+4+4=136 — 17칸에 꼭 든다(예전 칸 모델은 18칸)
        self.assertEqual((lines, bad), (["가" * 16 + " ."], []))

    def test_개행으로_넘긴_줄은_넘침이_아니다(self):
        self.assertEqual(flow("가" * 16 + "\n.")[1], [])

    def test_네_줄을_넘으면_한_줄_올린다(self):
        lines, bad = flow("\n".join("가나다라마"[i] * 17 for i in range(5)))
        self.assertEqual(len(lines), 5)
        self.assertEqual(bad, [])


class Wrap(unittest.TestCase):
    def setUp(self):
        self._vwf = typeset.VWF
        typeset.VWF = True  # px 모델(가변 폭 켬)

    def tearDown(self):
        typeset.VWF = self._vwf

    def test_반각_공백은_더_채운다(self):
        # 가 16개(128px) + 공백(4) + 부호 어절(4) = 136 — 들어간다. 예전(1칸 공백)엔 18칸이라 꺾였다.
        self.assertEqual(typeset.wrap("가" * 16 + " .", {}, {}), "가" * 16 + " .")
        self.assertEqual(typeset.wrap("가" * 16 + " 나", {}, {}), "가" * 16 + "\n나")  # 128+4+8=140


class Lossless(unittest.TestCase):
    def test_폭마다_글을_안_잃는다(self):
        # 폭 1~17 의 어절을 여러 벌 섞어 17칸 경계를 전부 밟아 본다 — 조판 전후 공백·개행 뺀 글자가 같아야 한다.
        for a in range(1, 18):
            for b in range(1, 18):
                s = " ".join(["가" * a, "나" * b, "다" * (18 - a), "라."]) + "\n" + "마" * b + " 바"
                out = typeset.wrap(s, {}, {})
                strip = lambda x: x.replace(" ", "").replace("\n", "")
                self.assertEqual(strip(out), strip(s), (a, b))

    def test_공백을_개행으로_바꾸는_것_말고는_막는다(self):
        typeset.lossless("가 나", "가\n나")
        for bad in ("가\n", "가 나다", "가\n\n나", "가 너"):
            with self.assertRaises(typeset.TextLost):
                typeset.lossless("가 나", bad)



class IndentQuotes(unittest.TestCase):
    def test_둘째_줄부터_두_칸(self):
        self.assertEqual(
            typeset.indent_quotes("「가나\n 다라\n 마바」\n사"), "「가나\n  다라\n  마바」\n사"
        )

    def test_쪽_사이에서_다시_열려도_이어진다(self):
        self.assertEqual(
            typeset.indent_quotes("「가\n 나」<FF>「다\n 라」"), "「가\n  나」<FF>「다\n  라」"
        )

    def test_따옴표_밖은_그대로(self):
        self.assertEqual(typeset.indent_quotes("가\n 나"), "가\n 나")


if __name__ == "__main__":
    unittest.main()
