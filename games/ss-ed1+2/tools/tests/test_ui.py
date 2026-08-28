"""HUD·시스템 메뉴 정본 회귀 — **원본 없이 돈다**(레포 규약).

여기서 보는 건 셋이다:
  ① 정본이 표마다 원본과 같은 줄 수인가 (한 줄 밀리면 엉뚱한 칸을 덮는다)
  ② 문안이 레코드 폭에 드는가 (넘치면 다음 칸을 먹어 메뉴가 통째로 밀린다)
  ③ 같은 자리를 두 표가 겹쳐 쓰지 않는가

⚠ **원문 대조는 여기서 못 한다** — 원본 디스크가 필요하다. 그건 `patch_ui.py` 의
  사전조건(`rows()` 의 assert)이 매번 본다.
"""

import itertools
import json
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import dump_ui
import patch_ui
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


class PinnedInPlace(unittest.TestCase):
    """🔴 **포인터가 있어도 못 옮기는 자리가 있다**(2026-08-28 실기).

    `ED.BIN` 0x44BC8 의 HUD 접미 표(`入口`·`付近`·`北`·`南`·`東`·`西`)는 조립 루틴이
    **4B 간격의 표로** 집는다. 참조를 갱신해도 표가 흩어지면 깨진다 — 시스템 메시지가
    늘자 배치기가 여섯을 옮겼고 화면에 `メ§電 リ…처` 가 떴다.
    ⚠ 「포인터가 없으면 못 옮긴다」만으로는 부족하다. 코드가 그 주소를 쓰는지는
      **포인터 유무로 안 갈린다.**
    """

    def test_table_is_four_byte_strided(self):
        """표라는 근거 — 여섯이 4B(앞 둘은 8B) 간격으로 붙어 있다."""
        pin = patch_ui.PINNED_INPLACE["/ED.BIN"]
        self.assertEqual(len(pin), 6)
        self.assertEqual(pin, tuple(sorted(pin)))
        self.assertEqual([b - a for a, b in itertools.pairwise(pin)], [8, 8, 4, 4, 4])

    def test_korean_fits_the_original_slot(self):
        """제자리에 박으므로 **원문 칸을 넘으면 안 된다** — 넘으면 표가 밀린다."""
        for kr, room in (("입구", 4), ("근처", 4), ("북", 2), ("남", 2), ("동", 2), ("서", 2)):
            self.assertLessEqual(len(kr) * 2, room, kr)


class TablesAreNotRelocated(unittest.TestCase):
    """🔴 **표는 색인으로 집힌다 — 한 칸도 못 옮긴다**(2026-08-28 실기).

    시스템 메시지 스캔이 지명 표의 첫 칸(`エルアスタ`)을 「옮길 수 있는 문자열」로 보고
    옮겼고, 그 자리를 가리키던 **표 베이스 포인터**까지 새 주소로 바꿨다. 루틴은 거기에
    `색인×14` 를 더해 집으므로 첫 칸만 맞고 나머지는 **코드 바이트를 이름으로 읽었다**
    (화면에 `A!A!A!B근처`).
    ⚠ 런 시작만 막으면 모자란다 — 표 앞에서 시작한 런이 표 안까지 삼킨다. **맞은 자리**를
      봐야 한다.
    """

    def test_no_system_message_inside_a_table(self):
        import common

        _f, mm = common.open_image()
        try:
            spans = {}
            for r in patch_ui.rows():
                path = dump_ui.FILES[r[0]]
                spans.setdefault(path, []).append((int(r[3]), int(r[3]) + int(r[4])))
            bad = [
                (r[0], int(r[3]))
                for r in patch_ui.sys_rows(mm)
                if any(a <= int(r[3]) < b for a, b in spans.get(r[0], ()))
            ]
        finally:
            mm.close()
            _f.close()
        self.assertEqual(bad, [], f"표 안에 시스템 메시지 레코드가 있다: {bad[:4]}")
