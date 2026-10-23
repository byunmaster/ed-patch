"""구조 대조 검사 — 줄 단위 분류 규칙(가짜 바이트 — 원본 데이터를 안 쓴다, 원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import structcheck

C = structcheck.classify
G = b"\xf0\x41\xf0\x42"  # 가짜 글자(한글 글리프 꼴 리드 F0)
J = b"\x82\xa0\x82\xa2"  # 가짜 글자(2바이트 SJIS 꼴)


class Struct(unittest.TestCase):
    def test_글자만_다르면_동일(self):
        self.assertEqual(C(b"\x16" + J + b"\x14\x0d" + J + b"\x13", b"\x16" + G + b"\x14\x0d" + G + G + b"\x13"), "동일")

    def test_줄바꿈_가나전환_강조_속도_멈춤은_열에서_빠진다(self):
        o = b"\x10\x30\x0e" + J + b"\x0f\x0d" + J + b"\x11\x33\x30\x06" + J + b"\x04\x12"
        n = b"\x0d" + G + G + b"\x12"
        self.assertEqual(C(o, n), "동일")

    def test_18은_14와_글자_넷의_줄임꼴이다(self):
        self.assertEqual(C(b"\x18" + b"\x82\xa0\x82\xa2" + J + b"\x14", b"\x14" + G + G + b"\x14"), "동일")

    def test_쪽_넘김이_늘거나_줄어도_끝_대기가_같으면_허용(self):
        o = J + b"\x13\x0d" + J
        n = G + b"\x13\x0d" + G + b"\x13\x0d" + G
        self.assertEqual(C(o, n), "쪽 넘김")
        self.assertEqual(C(b"\x16" + J + b"\x14" + J + b"\x13\x0d" + J + b"\x13", b"\x16" + G + b"\x14" + G + G + b"\x13"), "쪽 넘김")

    def test_끝_대기_13이_사라지거나_생기면_실패(self):
        self.assertIsNone(C(J + b"\x13", G))
        self.assertIsNone(C(J, G + b"\x13"))

    def test_끝_12_대기가_사라지면_실패(self):  # 10-22 실결함 — 「…{12}↵　」 의 끝 대기가 틀 번역에서 빠졌다
        self.assertIsNone(C(b"\x07" + J + b"\x12\x0d\x20", b"\x07" + G))

    def test_13_뒤_여백만_달린_끝도_끝_대기다(self):  # 「…{13}　」
        self.assertEqual(C(J + b"\x13\x20", G + b"\x13"), "동일")
        self.assertIsNone(C(J + b"\x13\x20", G))

    def test_FF_채움이_글자_자리에_끼면_실패(self):
        self.assertIsNone(C(J + b"\x13", G + b"\xff\xff\x13"))
        self.assertEqual(C(J + b"\x13", G + b"\xf2\xff\x13"), "동일")  # 글리프 둘째 바이트로 쓰인 FF 는 토큰 안이다

    def test_다른_구조_제어가_생기거나_사라지면_실패(self):
        self.assertIsNone(C(b"\x16" + J + b"\x14" + J, J))  # 말머리 삭제
        self.assertIsNone(C(J, J + b"\x1b"))  # 이름 값 삽입 추가
        self.assertIsNone(C(b"\x1c\x30" + J, b"\x1c\x31" + G))  # 인자가 다른 제어

    def test_상수_이름_삽입을_글자로_풀어_쓴_줄은_허용(self):
        o = b"\x16\x0e" + J + b"\x1a\x0f" + J + b"\x13"
        n = G + G + b"\x13"
        self.assertEqual(C(o, n), "이름 상수")

    def test_이름_삽입에_변수_제어가_끼면_허용_밖(self):
        o = b"\x16" + J + b"\x1b" + J + b"\x1a" + J
        self.assertIsNone(C(o, G + G))


if __name__ == "__main__":
    unittest.main()


class FakePkg(unittest.TestCase):
    """`check_package` 를 가짜 패키지 둘로 — 글자 바이트는 가짜, 구조(표 · 덩이 이음 · 줄 수 · 제어 열)만 본다. 일부러 망가뜨린 사본이 실제로 걸리는지(회귀)."""

    S = structcheck.package.SENTINEL

    def _run(self, o_lines, b_lines, o_tab=(0, 20, 40, 40), b_tab=(90, 50, 70, 70), b_end=None):
        from unittest import mock

        po_, pb_ = bytearray(120), bytearray(120)
        po_[60:68] = self.S
        pb_[100:108] = self.S
        po, pb = bytes(po_), bytes(pb_)
        chunks_o = [(20, 40), (40, 60), (60, 68)]
        chunks_b = [(50, 70), (70, 100), (100, 108)]
        data = {("o", 20): o_lines[0], ("o", 40): o_lines[1], ("b", 50): b_lines[0], ("b", 70): b_lines[1]}

        def msg_table(pkg):
            return (8, list(o_tab) if pkg is po else list(b_tab))

        def chunks(pkg):
            return chunks_o if pkg is po else chunks_b

        def decode_chunk(pkg, a, b):
            key = ("o" if pkg is po else "b", a)
            d = b"\x00".join(data[key]) + b"\x00"
            end = (b_end or {}).get(a, b)
            return d, end

        rep = structcheck.Report()
        with (
            mock.patch.object(structcheck.package, "msg_table", msg_table),
            mock.patch.object(structcheck.package, "chunks", chunks),
            mock.patch.object(structcheck.package, "decode_chunk", decode_chunk),
        ):
            structcheck.check_package(1, po, pb, rep, set())
        return rep

    LINE_O = [[J + b"\x13", b"\x16" + J + b"\x14\x0d" + J]]

    def _base(self):
        return ([[J + b"\x13", J + b"\x12"], [b"\x16" + J + b"\x14\x0d" + J + b"\x13", J]], [[G + b"\x13", G + b"\x12"], [b"\x16" + G + b"\x14\x0d" + G + b"\x13", G]])

    def test_멀쩡한_사본은_통과(self):
        o, b = self._base()
        rep = self._run(o, b)
        self.assertEqual(rep.fails, [], rep.fails)
        self.assertEqual(rep.chunks_checked, 2)

    def test_제어_한_바이트가_사라진_사본은_걸린다(self):
        o, b = self._base()
        b[0][1] = G  # `12` 가 사라졌다
        self.assertTrue(any("S4" in f for f in self._run(o, b).fails))

    def test_줄_수가_다르면_걸린다(self):
        o, b = self._base()
        b[0] = [G + b"\x13"]
        self.assertTrue(any("S3" in f for f in self._run(o, b).fails))

    def test_덩이가_다음_시작에_안_닿으면_걸린다(self):
        o, b = self._base()
        self.assertTrue(any("S2" in f for f in self._run(o, b, b_end={50: 69}).fails))

    def test_표_별칭이_갈리거나_합쳐지면_걸린다(self):
        o, b = self._base()
        self.assertTrue(any("S1" in f for f in self._run(o, b, b_tab=(90, 50, 70, 50)).fails))  # 같은 원본 덩이(40)를 가리키던 둘이 갈렸다
        self.assertTrue(any("S1" in f for f in self._run(o, b, o_tab=(0, 20, 40, 20), b_tab=(90, 50, 50, 50)).fails))  # 다른 원본 덩이 둘이 한 덩이로 합쳐졌다
