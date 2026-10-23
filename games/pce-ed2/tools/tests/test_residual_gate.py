"""장면 패키지 전수 잔존 게이트 — 분모 분할·목록 꼴은 원본 없이, 「번역 안 된 이미지는 실패한다」는 원본이 있을 때만."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import package
import residual_gate as g


class Partition(unittest.TestCase):
    def test_본편과_제외_목록은_안_겹친다(self):
        book = {(r - 2) // 128 for r in package.CLEAN}
        sets = [book, g.BATTLE_TEST, g.UNDECIDED, g.NOT_ED2]
        for i, a in enumerate(sets):
            for b in sets[i + 1 :]:
                self.assertFalse(a & b)

    def test_최종_장면_21_이_본편에_있다(self):
        # 패키지 21 이 목록에서 빠져 일본어로 남았던 일(10-18)의 재발 방지
        self.assertIn(2690, package.CLEAN)
        self.assertNotIn(21, g.BATTLE_TEST | g.UNDECIDED | g.NOT_ED2)

    def test_알려진_목록에_원문이_없다(self):
        for k, c in g.known().items():
            rel, msg, line = (int(x) for x in k.split(":"))
            self.assertIn(rel, package.CLEAN)
            self.assertTrue(msg >= 0 and line >= 0)
            self.assertIn(c, {"행동", "기타"})


class CodeAreaHole(unittest.TestCase):
    """메시지 표 밖(코드 영역)에 박힌 일본어 문장 — 번역 단위 목록이 표 목표에서 만들어져 원리상 못 보던 자리(10-18)."""

    def _pkg(self, text: bytes):
        # 합성 패키지: 머리표(메시지 표 포인터) 없이 code_jp 의 입력 꼴만 시험하려고 msg_table 을 감싼다
        import package as pk

        orig = pk.msg_table
        pk.msg_table = lambda _p: (0x100, [0x100, 0x120])
        try:
            return g.code_jp(b"\x00" * 0x20 + text + b"\x00" * 0xE0 + b"\xff" * 0x40)
        finally:
            pk.msg_table = orig

    def test_코드_영역의_가나_문장은_걸린다(self):
        self.assertEqual(self._pkg(bytes.fromhex("82b382aa82c182bd")), [0x20])  # 「さがった」 SJIS

    def test_한글_글리프만_있으면_통과(self):
        self.assertEqual(self._pkg(bytes.fromhex("f23bf03cf1f8f29d")), [])

    def test_짧은_가나_조각은_코드_바이트_우연_일치로_본다(self):
        self.assertEqual(self._pkg(bytes.fromhex("82b382aa")), [])


class LeftoverHole(unittest.TestCase):
    """옛 판정은 「줄이 원본과 바이트까지 같다」였다 — 앞 이름만 일본어로 남고 꼬리가 번역된 줄이 새고, 4자 미만 짧은 문장도 샜다(10-18 sfc-ed2·md-ed1 발견)."""

    KR = bytes.fromhex("f23bf03cf1f8")  # 한글 글리프 코드(리드 F0~F9)

    def test_한글만_있는_줄은_통과(self):
        self.assertFalse(g.jp_left(self.KR + b"\x0d"))

    def test_이름만_일본어로_남고_꼬리는_번역된_줄은_걸린다(self):
        self.assertTrue(g.jp_left(bytes.fromhex("0e72d7afb8c50f") + self.KR))

    def test_글자_하나만_남아도_걸린다(self):
        self.assertTrue(g.jp_left(self.KR + bytes.fromhex("0e720f")))

    def test_잡음_길이_하한은_1(self):
        self.assertEqual(g.MIN_JP, 1)


@unittest.skipUnless(common.ORIG_ISO.exists(), "원본이 없다")
class Detects(unittest.TestCase):
    def test_번역_안_된_원본_이미지는_실패한다(self):
        errs, now = g.evaluate(common.ORIG_ISO)
        self.assertTrue(any("알려진 목록 밖 잔존" in e for e in errs))
        self.assertGreater(len(now), 1000)  # 원본엔 일본어 줄이 수천 줄 있다


if __name__ == "__main__":
    unittest.main()
