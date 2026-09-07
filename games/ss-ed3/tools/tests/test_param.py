"""`param.py` — 표 경계와 필터. **원본 없이** 합성 바이트로 돈다.

🔴 지키는 것 하나: **경계 표식이 곧 필터다.** 이걸 놓쳐서 예전에 이름 아닌 144 건을
아이템으로 읽었고, 그 오염이 번역 판단까지 갔다(`ネクロマンサー` 가 표에 없다고 오판).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import param as P


def _rec(names, stride):
    out = bytearray()
    for n in names:
        b = n.encode("shift_jis") if n else b""
        out += b.ljust(stride, b"\x00")
    return bytes(out)


class Boundary(unittest.TestCase):
    def test_names_filters_marks_and_blanks(self):
        st = 0x10
        b = _rec(["短剣", None, "reserve", "鉄の剣", "Sentinel"], st)
        self.assertEqual(P.records(b, (0, st, 5)), ["短剣", None, "reserve", "鉄の剣", "Sentinel"])
        self.assertEqual(P.names(b, (0, st, 5)), ["短剣", "鉄の剣"])

    def test_slot_never_reads_past_itself(self):
        # ⚠ NUL 없는 칸이 다음 칸을 먹으면 표가 통째로 밀린다 — stride 안에서만 읽는다.
        self.assertEqual(P.records("あいうえお".encode("shift_jis"), (0, 4, 1)), [None])

    def test_gap_is_declared_not_guessed(self):
        # 빈 영역은 **상수로 선언**한다 — 「비었으니 써도 되겠지」로 흘러가지 않게.
        self.assertEqual(P.GAP, (0x44EC, P.DESC_ITEM[0]))
        self.assertEqual(P.ITEM[0] + P.ITEM[1] * P.ITEM[2], P.GAP[0])


class Descriptions(unittest.TestCase):
    def _blob(self, raw):
        b = bytearray(b"\x00" * P.DESC_ITEM[1])
        enc = raw.encode("shift_jis")
        b[P.DESC_ITEM[0] : P.DESC_ITEM[0] + len(enc)] = enc
        return bytes(b)

    def test_drops_ascii_dummies(self):
        b = self._blob("ごく普通の短剣\x00剣の達人も＄認める剣\x00quux\x00Sentinel\x00")
        self.assertEqual(P.descs(b), ["ごく普通の短剣", "剣の達人も＄認める剣"])
        self.assertEqual(P.descs(b, keep_dummy=True)[-2:], ["quux", "Sentinel"])

    def test_spell_area_shares_the_same_contract(self):
        # 설명 영역이 둘인데 규약이 같다 — 파서를 갈래로 나누지 않는다.
        b = bytearray(b"\x00" * P.DESC_SPELL[1])
        enc = "敵を眠らせる。\x00".encode("shift_jis")
        b[P.DESC_SPELL[0] : P.DESC_SPELL[0] + len(enc)] = enc
        self.assertEqual(P.descs(bytes(b), P.DESC_SPELL), ["敵を眠らせる。"])

    def test_newline_is_a_fullwidth_char_not_a_control_byte(self):
        # `＄` 는 제어코드가 아니라 전각 문자다 — 제어 바이트로 찾으면 못 찾는다.
        self.assertEqual(len(P.DESC_NL.encode("shift_jis")), 2)
        b = self._blob("剣の達人も＄認める剣\x00")
        self.assertEqual(P.descs(b)[0].split(P.DESC_NL), ["剣の達人も", "認める剣"])


if __name__ == "__main__":
    unittest.main()
