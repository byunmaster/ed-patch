"""NUL 문자열 표 회귀 — **원본 없이 돈다**(합성 바이트).

🔴 지키는 것 셋:
  · **정렬이 안 밀린다** — 앞에 서식 바이트가 붙어도 문자열을 한 글자 먹지 않는다
  · 포인터로 확인된 것과 휴리스틱을 **구분해서** 낸다
  · 되끼우면 **바이트 동일**
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import strtab as S

BASE = 0x06004000


def _img(*parts):
    """NUL 로 끊긴 조각들을 이어 붙인다 → `(bytes, {조각번호: 오프셋})`."""
    out = bytearray()
    offs = {}
    for i, p in enumerate(parts):
        offs[i] = len(out)
        out += p + b"\x00"
    return bytes(out), offs


class TestShape(unittest.TestCase):
    def test_일본어_없으면_안_잡는다(self):
        b, _ = _img(b"ABCDEF")
        self.assertEqual(S.strings(b), [])

    def test_이진이_섞이면_안_잡는다(self):
        b, _ = _img(b"\x01\x02" + "村です".encode("shift_jis"))
        self.assertEqual(S.strings(b), [])

    def test_서식_제어는_허용한다(self):
        """실측: 안내문이 `00 00 09 20 20 20 …` 꼴로 늘어선다."""
        b, off = _img(b"\x09   " + "試験用のならびかえ".encode("shift_jis"))
        (x,) = S.strings(b)
        self.assertEqual(x["off"], off[0])
        self.assertEqual(S.text_of(x["raw"]), "<09>   試験用のならびかえ")


class TestFilters(unittest.TestCase):
    def test_한_글자는_포인터가_있어야_잡힌다(self):
        one = "７".encode("shift_jis")
        b, off = _img(one)
        self.assertEqual(S.strings(b), [])  # 포인터 없이는 안 받는다
        # 그 자리를 가리키는 BE32 를 붙이면 받는다.
        # ⚠ **짝수 자리에 놓는다** — `ptr_targets` 는 2바이트 걸음으로 훑는다(SH-2 리터럴
        #   풀은 4B 정렬이라 짝수만 봐도 다 걸린다). 홀수에 두면 못 찾는 게 정상이다.
        b2 = b + b"\x00" * ((-len(b)) % 2) + (BASE + off[0]).to_bytes(4, "big")
        (x,) = S.strings(b2, BASE)
        self.assertEqual((x["off"], x["by"]), (off[0], "ptr"))

    def test_제2수준_한자만_있으면_버린다(self):
        """🔴 코드·데이터가 SJIS 로 디코드되면 희귀 한자로 나온다 — 게임 UI 는 안 쓴다."""
        b, _ = _img("聶稘琢".encode("shift_jis"))
        self.assertEqual(S.strings(b), [])

    def test_제1수준_두_글자는_받는다(self):
        b, off = _img("売る".encode("shift_jis"), "武器".encode("shift_jis"))
        got = [(x["off"], x["by"], S.text_of(x["raw"])) for x in S.strings(b)]
        self.assertEqual(got, [(off[0], "heur", "売る"), (off[1], "heur", "武器")])

    def test_앞에_서식이_붙어도_구_판정이_안_밀린다(self):
        """🔴 실제로 물렸다 — `\\t売る` 가 정렬이 밀려 쓰레기로 읽히고 통째로 탈락했다."""
        b, _ = _img(b"\x09" + "売る".encode("shift_jis"))
        (x,) = S.strings(b)
        self.assertEqual(S.text_of(x["raw"]), "<09>売る")


class TestPointers(unittest.TestCase):
    def test_파일_밖을_가리키는_값은_무시한다(self):
        b, _ = _img("村です".encode("shift_jis"))
        b2 = b + (BASE + 0x999999).to_bytes(4, "big")
        self.assertNotIn("ptr", [x["by"] for x in S.strings(b2, BASE)])

    def test_로드베이스는_0_BIN_만_안다(self):
        """⚠ 틀린 베이스는 포인터를 안 찾아 주는 게 아니라 **엉뚱한 자리를 확인해 준다.**"""
        self.assertEqual(set(S.LOAD_BASE), {"/0.BIN"})
        self.assertEqual(S.LOAD_BASE["/0.BIN"], 0x06004000)  # IP.BIN 0xF0 실측


class TestRoundTrip(unittest.TestCase):
    def test_왕복이_바이트_동일(self):
        for raw in (
            "第９章　　〜試験の巻〜".encode("shift_jis"),
            b"\x09   " + "試験をやりなおしてください".encode("shift_jis"),
            "  もっと%2d%s".encode("shift_jis"),
        ):
            b, _ = _img(raw)
            for x in S.strings(b):
                self.assertEqual(S.encode_text(S.text_of(x["raw"])), x["raw"])

    def test_디코드_안_되는_짝은_버린다(self):
        """표에서는 **버리는 게 맞다** — 실측 `sys_jp` 전량에 그런 짝이 하나도 없고,
        받아 주면 그래픽 바이트가 그 문으로 들어온다. (스크립트 쪽 `mapfile` 은 반대로
        **살린다** — 거긴 진짜 문안 안에 실재한다.)"""
        b, _ = _img(b"\x85\x40" + "です".encode("shift_jis"))
        self.assertEqual(S.strings(b), [])


if __name__ == "__main__":
    unittest.main()
