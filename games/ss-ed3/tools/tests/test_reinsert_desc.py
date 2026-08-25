"""설명문 재삽입의 **세 계약**. 원본 없이 합성 바이트로 돈다.

실기에서 하나씩 배운 것들이라(2026-08-25) 회귀로 못 박는다 — 셋 다 어기면 **빌드도 길이
검사도 통과하고 화면에서만 어긋난다.**

  1. **조각마다 원문과 같은 칸** — 엔진이 조각 시작을 오프셋으로 잡는다
  2. **남는 자리는 전각 공백** — 반각(0x20)은 개행을 깨고 NUL 은 조각을 늘린다
  3. **줄 수도 원문과 같게** — 모자라면 끝에 빈 줄을 붙인다
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reinsert_desc as RD
import typeset as T


def _area_bytes(*chunks):
    return b"\x00".join(c.encode("shift_jis") for c in chunks) + b"\x00"


class Contracts(unittest.TestCase):
    def _run(self, jp_chunks, kr, size=None):
        raw = _area_bytes(*jp_chunks)
        size = size or len(raw)
        blob = raw.ljust(size, b"\x00")
        area = (0, size)
        # ⚠ 문안에 한글을 안 쓰면 **배정표 없이** 돈다 — 계약 자체는 언어와 무관하다.
        tbl = {}
        return RD._area(blob, area, kr, tbl)

    def test_keeps_each_slot_length(self):
        out, n, bad, over = self._run(["あいうえお", "かきくけこ"], {"0": "あい"})
        self.assertEqual(n, 1)
        self.assertEqual(len(out), len(_area_bytes("あいうえお", "かきくけこ")))
        # 첫 칸이 원문과 같은 길이여야 뒤 조각이 안 밀린다
        self.assertEqual(len(out.split(b"\x00")[0]), 10)

    def test_pads_with_fullwidth_never_halfwidth_or_nul(self):
        # 짧은 문안을 넣으면 남는 칸이 **전각 공백**으로 차야 한다.
        jp = ["あいうえおかきくけこ"]  # 20B
        out, n, bad, over = self._run(jp, {"0": "あ"})
        body = out.split(b"\x00")[0]
        self.assertEqual(len(body), 20, "칸 길이가 유지돼야 한다")
        self.assertNotIn(b" ", body[:-1], "반각 공백이 섞이면 개행이 깨진다")

    def test_row_count_must_match_original(self):
        # 원문이 2 줄이면 우리도 2 줄 — 모자라면 빈 줄을 붙인다.
        jp = ["あいう" + T.DESC_NL + "えおか"]
        out, n, bad, over = self._run(jp, {"0": "あ"})
        body = out.split(b"\x00")[0].decode("shift_jis")
        self.assertEqual(len(body.split(T.DESC_NL)), 2)

    def test_blank_chunks_survive(self):
        # 🔴 빈 조각(연속 NUL)을 버리면 뒤가 통째로 밀린다.
        raw = b"\xa0\xa0\x00\x00\xa1\xa1\x00"
        out, n, bad, over = RD._area(raw, (0, len(raw)), {}, {})
        self.assertEqual(out, raw)


if __name__ == "__main__":
    unittest.main()
