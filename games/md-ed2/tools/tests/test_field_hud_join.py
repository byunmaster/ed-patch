"""월드 HUD 방위 둘 붙여 쓰기 — 마스터 11-09 「북동 남서 등 방향은 띄어쓰기 없이 붙여써야해」를 다른 작업이 되돌리지 못하게 잠근다."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import field_hud


class _Cs:
    def encode_char(self, ch):
        return struct.pack(">H", 0x9000 + ord(ch) % 0x100)


def _ink_cols(g):
    cols = [x for x in range(len(g[0])) if any(row[x] for row in g)]
    return cols[0], cols[-1]


class TestJoin(unittest.TestCase):
    def test_gap_between_directions(self):
        field_hud._ensure_custom_glyphs()
        g = field_hud.hangul.CUSTOM_GLYPHS
        for ns in ("북", "남"):
            for ew in ("동", "서"):
                _, r1 = _ink_cols(g[field_hud.PUA_DIR[ns]])
                l2, _ = _ink_cols(g[field_hud.PUA_DIR2[ew]])
                gap = (field_hud.PITCH + l2) - r1 - 1  # 둘째 칸은 12px 피치 뒤에 앉는다
                self.assertLessEqual(gap, 3, (ns, ew, gap))  # 공백 한 칸(6px) 없이 붙는다 — 글자 사이 3px 이하
                # 하나뿐일 때의 원래 글리프는 앞 공백(이름과의 띄움)을 그대로 둔다
                l_alone, _ = _ink_cols(g[field_hud.PUA_DIR[ew]])
                self.assertGreater(l_alone - l2, 2)

    def test_tramp_shape(self):
        code = field_hud.join_tramp(_Cs())
        self.assertLessEqual(len(code), 112)
        self.assertEqual(code[-6:], b"\x4e\xf9" + struct.pack(">I", field_hud.JOIN_RESUME))
        self.assertEqual(code[:2], b"\x17\x5a")  # move.b (a2)+,d(a3) 로 시작 — 원래 네 바이트 복사


if __name__ == "__main__":
    unittest.main()
