"""HUD·시스템 메뉴 정본 회귀 — **원본 없이 돈다**(레포 규약).

여기서 보는 건 셋이다:
  ① 정본이 표마다 원본과 같은 줄 수인가 (한 줄 밀리면 엉뚱한 칸을 덮는다)
  ② 문안이 레코드 폭에 드는가 (넘치면 다음 칸을 먹어 메뉴가 통째로 밀린다)
  ③ 같은 자리를 두 표가 겹쳐 쓰지 않는가

⚠ **원문 대조는 여기서 못 한다** — 원본 디스크가 필요하다. 그건 `patch_ui.py` 의
  사전조건(`rows()` 의 assert)이 매번 본다.
"""

import json
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import dump_ui
from patch_ui import CANON, PAD, rec_len


class TestUiCanon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CANON, encoding="utf-8") as f:
            d = json.load(f)
        cls.tables, cls.pad = d["tables"], d.get("pad", {})

    def test_표마다_줄_수가_원본과_같다(self):
        for name, _ed, ed2, _stride, n, n2 in dump_ui.TABLES:
            want = max(n, n2 or 0) if ed2 else n
            self.assertIn(name, self.tables, f"정본에 표가 없다: {name}")
            self.assertEqual(len(self.tables[name]), want, name)

    def test_문안이_레코드_폭에_든다(self):
        for name, _ed, ed2, stride, n, n2 in dump_ui.TABLES:
            cnt = max(n, n2 or 0) if ed2 else n
            for i, (_jp, kr) in enumerate(self.tables[name][:cnt]):
                if kr is None:
                    continue
                if w := self.pad.get(name):
                    kr = kr + PAD * (w - len(kr))
                self.assertLessEqual(rec_len(kr), stride, f"{name}[{i}] {kr!r}")

    def test_자리가_겹치지_않는다(self):
        """오프셋을 손으로 적었다 — 표 둘이 같은 칸을 물면 뒤엣것이 앞엣것을 지운다."""
        specs = list(dump_ui.TABLES) + [t[:6] for t in dump_ui.GLOSSARY_TABLES]
        for col in (0, 1):
            seen = {}
            for name, ed, ed2, stride, n, n2 in specs:
                off = (ed, ed2)[col]
                if off is None:
                    continue
                for i in range(n2 if (col == 1 and n2) else n):
                    for b in range(off + i * stride, off + (i + 1) * stride):
                        self.assertNotIn(b, seen, f"0x{b:06x}: {name} 과 {seen.get(b)} 가 겹친다")
                        seen[b] = name

    def test_null_은_영문_표기뿐이다(self):
        """`null`(원본 유지)은 ＯＮ·ＥＰ 같은 영문 자리에만 쓴다 — 일본어가 남으면 안 된다."""
        for name, rows in self.tables.items():
            for i, (jp, kr) in enumerate(rows):
                if kr is None:
                    self.assertTrue(
                        all(ord(c) < 0x3000 or 0xFF01 <= ord(c) <= 0xFF5E or c == "　" for c in jp),
                        f"{name}[{i}] {jp!r} 가 그대로 남는다",
                    )


if __name__ == "__main__":
    unittest.main()
