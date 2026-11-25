"""자기 인자 자리를 가리키는 호출(`10 00 00`)은 재조립 뒤에도 상대 0 이다(055-3:0x1853 — 절대 주소로 두면 글이 줄 때 2바이트 문자 가운데로 떨어졌다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene


class SelfCall(unittest.TestCase):
    def test_relative_zero_kept_when_stream_moves(self):
        b = bytes.fromhex("0e 82be 01 10 00 00 8e 81 42 05 06".replace(" ", ""))
        st = scene.parse_stream(b, 0)
        call = next(t for t in st.tokens if t.ref == scene.CALL)
        self.assertEqual(call.target, call.argpos)
        out = scene._emit_tokens(st.tokens, 0x100, {})  # 다른 자리에 놓아도
        self.assertEqual(out, b)
        out2 = scene._emit_tokens(st.tokens[:1] + st.tokens[2:], 0x100, {})  # 앞 글이 줄어도
        i = out2.index(0x10)
        self.assertEqual(out2[i + 1 : i + 3], b"\x00\x00")


if __name__ == "__main__":
    unittest.main()
