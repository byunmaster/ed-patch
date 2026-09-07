"""`MAP*.BIN` 구조·블록 회귀 — **원본 없이 돈다**(합성 바이트를 그 자리에서 만든다).

지키려는 것 셋:
  · 헤더 계약(매직 · 37칸 포인터표 · 절대주소)이 깨지면 곧바로 운다
  · 블록 경계가 밀리지 않는다 — **텍스트 왕복이 바이트 동일**
  · 그래픽 오탐(한자만 나오는 런)을 거른다
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mapfile as M


def _file(payload, ptrs=None, name="王城"):
    # ⚠ 맵 이름에 가나를 넣지 않는다 — `blocks()` 가 그것까지 블록으로 잡아
    #   테스트가 재는 대상이 흐려진다(실제 파일에서는 잡히는 게 맞다).
    """매직 + 37칸 포인터표 + 맵이름 + payload."""
    body = bytearray(M.MAGIC)
    head_len = M.NAME_OFF + len(name.encode("shift_jis")) + 1
    ptrs = ptrs or [head_len] * M.PTR_N
    for p in ptrs:
        body += (M.BASE + p).to_bytes(4, "big")
    body += name.encode("shift_jis") + b"\x00"
    assert len(body) == head_len, (len(body), head_len)
    return bytes(body + payload)


class TestHeader(unittest.TestCase):
    def test_읽는다(self):
        b = _file(b"\x00" * 4)
        ptrs, name = M.parse_header(b)
        self.assertEqual(len(ptrs), M.PTR_N)
        self.assertEqual(name, "王城")

    def test_매직이_다르면_운다(self):
        b = bytearray(_file(b"\x00" * 4))
        b[0] = 0x00
        self.assertRaises(ValueError, M.parse_header, bytes(b))

    def test_포인터가_파일_밖이면_운다(self):
        """🔴 절대주소라 **다른 맵의 표를 읽고도 그럴듯하게 돈다** — 범위로 막는다."""
        b = _file(b"\x00" * 4, ptrs=[0x999999] + [0xC0] * (M.PTR_N - 1))
        self.assertRaises(ValueError, M.parse_header, b)


class TestBlocks(unittest.TestCase):
    def _one(self, text, head=b"\xff\x00", term=b"\x10"):
        return _file(head + text.encode("shift_jis") + term)

    def test_블록_하나(self):
        b = self._one("ここは村です。")
        bl = M.blocks(b)
        self.assertEqual(len(bl), 1, bl)
        self.assertEqual(M.text_of(bl[0]["body"]), "ここは村です。")
        self.assertEqual(bl[0]["head"], "ff00")
        self.assertEqual(bl[0]["term"], 0x10)

    def test_개행과_페이지(self):
        raw = "あい".encode("shift_jis") + bytes([M.CTRL_NL]) + "うえ".encode("shift_jis")
        raw += bytes([M.CTRL_PAGE]) + "おか".encode("shift_jis")
        b = _file(b"\xff\x00" + raw + b"\x0e")
        (blk,) = M.blocks(b)
        self.assertEqual(M.text_of(blk["body"]), "あい\nうえ\fおか")

    def test_텍스트_왕복이_바이트_동일(self):
        """🔴 되끼울 때 한 바이트라도 달라지면 옆 자료를 먹는다."""
        b = self._one("勇者ロランは言った。\r本当に？")
        for blk in M.blocks(b):
            self.assertEqual(M.encode_text(M.text_of(blk["body"])), blk["body"])

    def test_디코드_안_되는_짝도_왕복한다(self):
        """게임 전용 글자로 보이는 짝이 실재한다 — `replace` 로 뭉개면 못 되돌린다."""
        raw = b"\x85\x40" + "です".encode("shift_jis")  # 0x8540 = 표준 SJIS 미정의
        b = _file(b"\xff\x00" + raw + b"\x10")
        (blk,) = M.blocks(b)
        self.assertIn("<85><40>", M.text_of(blk["body"]))
        self.assertEqual(M.encode_text(M.text_of(blk["body"])), blk["body"])

    def test_종료가_엉뚱하면_안_잡는다(self):
        b = _file(b"\xff\x00" + "ここは村です".encode("shift_jis") + b"\x77")
        self.assertEqual(M.blocks(b), [])

    def test_가나가_없으면_안_잡는다(self):
        """그래픽 바이트가 한자로 디코드되는 오탐 — 실제로 런 8,406 개를 이걸로 걸렀다."""
        b = _file(b"\xff\x00" + "県席秘碑".encode("shift_jis") + b"\x10")
        self.assertEqual(M.blocks(b), [])

    def test_너무_짧으면_안_잡는다(self):
        b = _file(b"\xff\x00" + "あ".encode("shift_jis") + b"\x10")
        self.assertEqual(M.blocks(b), [])


if __name__ == "__main__":
    unittest.main()
