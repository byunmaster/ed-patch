"""출현 문구 유도 회귀 — **원본 없이 돈다**(레포 규약).

여기서 못 박는 함정은 하나다: **「정본에 이미 있다」가 「맞다」는 뜻이 아니다.**
`shared/glossary` 의 표기가 바뀌면 이미 적어 둔 출현 문구는 아무도 안 본다
(`docs/naming.md` 「잡히지 않는 건 문안이다」). 실측 2026-09-06 — PS1 이 main 에 머지되며
몬스터 여섯의 표기가 바뀌었는데 `script/system.json` 아홉 줄이 옛 표기로 남아 있었고
검사기가 하나도 안 울었다. 스캔이 `ED2MON*` 뿐이라 ED1 몫(`/ED.BIN` 86줄)이 사각지대였다.

⚠ **훑기 자체(`audit_lines`)는 여기서 못 돈다** — 원본 디스크가 필요하다. 여기서는
  그 위에 얹힌 **규칙**(꼴 셋 · 조사 · 머리 제어문자)을 본다.
"""

import os
import sys
import unittest
from typing import ClassVar

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(TOOLS))), "shared"))

import derive_encounters as D
from glossary import table


class Render(unittest.TestCase):
    MON: ClassVar[dict] = {"ワーラット": "웨어랫", "ヤマネコ": "산고양이", "キラーベア": "킬러베어"}

    def r(self, jp):
        kr, miss = D.render(jp, self.MON)
        self.assertEqual(miss, [], jp)
        return kr

    def test_shapes(self):
        self.assertEqual(self.r("ワーラットが現れた。"), "웨어랫이 나타났다.")
        self.assertEqual(self.r("ワーラットの群れが現れた。"), "웨어랫의 무리가 나타났다.")
        self.assertEqual(
            self.r("キラーベアとワーラットが現れた。"), "킬러베어와 웨어랫이 나타났다."
        )

    def test_josa_follows_the_name(self):
        """이름이 바뀌면 조사도 따라와야 한다 — 손으로 적으면 여기서 어긋난다."""
        self.assertEqual(self.r("ヤマネコが現れた。"), "산고양이가 나타났다.")

    def test_tail_newline_is_kept(self):
        self.assertEqual(self.r("ワーラットが現れた。\n"), "웨어랫이 나타났다.\n")

    def test_runtime_arg_is_skipped(self):
        self.assertEqual(D.render("%c%s%cが現れた。", self.MON)[0], None)

    def test_unknown_name_is_reported_not_swallowed(self):
        kr, miss = D.render("ナニカが現れた。", self.MON)
        self.assertIsNone(kr)
        self.assertEqual(miss, ["ナニカ"])


class Canon(unittest.TestCase):
    def test_names_the_audit_relies_on_exist(self):
        """훑기는 정본 표기로 판정한다 — 표에서 사라지면 조용히 0건이 된다."""
        mon = table("monster")
        for jp in ("ワーラット", "ヤマネコ", "ヂガバチ", "バルガー", "バルバス"):
            self.assertIn(jp, mon)


if __name__ == "__main__":
    unittest.main()
