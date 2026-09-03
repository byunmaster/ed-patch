"""실행파일 낱말 표의 구조 계약 — 원본 없이 도는 회귀.

밟은 함정 넷을 그대로 박는다(2026-09-03):

1. **표 자신을 문자열로 셌다** — 규격은 `N = 표[0] / 2` 인데 그걸 모르고 자리를 「그럴듯함」
   으로 넓혔다. ED4 인물 표의 0번이 「１ＢＪａあがざっねふめるェアヴィン」으로 읽혔는데
   그건 표 26바이트를 글자로 디코드한 것이었다.
2. **빈틈을 넘어 움직였다** — 표가 안 가리키는 문자열이 풀 안에 섞여 있다(계급 표의 「力」).
   붙여 싸면 그게 밀린다. 코드가 절대 주소로 가리킬 수 있으니 **빈틈은 닻**이다.
3. **되읽기를 코드표로 했다** — 미해독 한자가 낀 항목이 늘 「다르다」로 나왔다. 재삽입은
   코드표를 안 봐야 한다.
4. **읽힘 비율로 표를 걸렀다** — 0.85 로 뒀더니 ED4 지명 표(100항목, 67%)가 통째로 안 보였다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import exetext


def make(strings, terms=None, gap=None):
    """[코드열…] → `[표][풀]` 규격 바이트열. `gap` 은 i번 앞에 끼울 미참조 문자열."""
    n = len(strings)
    terms = terms or [0xFFFF] * n
    tbl, pool = [], bytearray()
    for i, codes in enumerate(strings):
        if gap and gap[0] == i:
            pool += struct.pack(f"<{len(gap[1])}H", *gap[1]) + struct.pack("<H", 0xFFFF)
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", terms[i])
    return struct.pack(f"<{n}H", *tbl) + bytes(pool)


CM = {c: "가" for c in range(0x40, 0x900)}


class TestExeText(unittest.TestCase):
    def test_table_is_detected_by_its_own_length(self):
        mem = make([[0x40], [0x41, 0x42], [0x43]])
        self.assertEqual(exetext.table_at(mem, 0, CM, min_n=3), 3)

    def test_first_entry_must_be_the_table_size(self):
        """🔴 이 규칙을 모르면 **표 자신이 문자열 하나로 세어진다.**"""
        mem = bytearray(make([[0x40], [0x41]]))
        struct.pack_into("<H", mem, 0, 0x0002)  # 첫 항목을 흐트러뜨린다
        self.assertIsNone(exetext.table_at(bytes(mem), 0, CM, min_n=2))

    def test_identity_rebuild_is_byte_identical(self):
        mem = make([[0x40, 0x41], [0x42], [0x43, 0x44, 0x45]])
        n = exetext.table_at(mem, 0, CM, min_n=3)
        cur = [exetext.raw_string(mem, x)[0] for x in struct.unpack_from(f"<{n}H", mem, 0)]
        out, slack = exetext.rebuild(mem, 0, 0, n, cur)
        self.assertEqual(out, mem)
        self.assertEqual(slack, 0)

    def test_budget_is_pooled_not_per_string(self):
        """짧은 이름에서 빌려 긴 이름에 쓸 수 있다 — 총량만 지키면 된다."""
        mem = make([[0x40, 0x41, 0x42], [0x43, 0x44, 0x45]])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        out, slack = exetext.rebuild(mem, 0, 0, n, [[0x40], [0x43, 0x44, 0x45, 0x46, 0x47]])
        got = [exetext.raw_string(out, x)[0] for x in struct.unpack_from(f"<{n}H", out, 0)]
        self.assertEqual(got, [[0x40], [0x43, 0x44, 0x45, 0x46, 0x47]])
        self.assertEqual(slack, 0)

    def test_over_budget_is_refused(self):
        mem = make([[0x40], [0x41]])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        with self.assertRaises(exetext.ExeTextError):
            exetext.rebuild(mem, 0, 0, n, [[0x40] * 8, [0x41]])

    def test_gap_is_an_anchor(self):
        """🔴 표가 안 가리키는 문자열은 **제자리에 남고**, 아무것도 그걸 넘지 못한다."""
        mem = make([[0x40, 0x41], [0x42, 0x43]], gap=(1, [0x99, 0x98]))
        n = exetext.table_at(mem, 0, CM, min_n=2)
        ch = exetext.chunks(mem, 0, 0, n)
        self.assertEqual(len(ch), 2, "빈틈이 칸을 갈라야 한다")
        # 앞 칸에서 남긴 자리를 뒤 칸이 못 쓴다
        with self.assertRaises(exetext.ExeTextError):
            exetext.rebuild(mem, 0, 0, n, [[0x40], [0x42, 0x43, 0x44, 0x45]])
        out, _ = exetext.rebuild(mem, 0, 0, n, [[0x40, 0x41], [0x42, 0x43]])
        self.assertEqual(out, mem)

    def test_terminator_is_preserved(self):
        """🔴 종결은 표마다 다르다(`0x8002`·`0xFFFF`) — 바꾸면 화면에 안 붙는다."""
        mem = make([[0x40], [0x41]], terms=[0x8002, 0xFFFF])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        out, _ = exetext.rebuild(mem, 0, 0, n, [[0x50], [0x51]])
        self.assertEqual(exetext.raw_string(out, struct.unpack_from("<H", out, 0)[0])[1], 0x8002)

    def test_rebuild_does_not_need_the_charmap(self):
        """미해독 한자가 낀 항목도 그대로 옮겨진다 — 코드표를 보면 그 자리를 빠뜨린다."""
        mem = make([[0x40], [0x7FF, 0x7FE]])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        cur = [exetext.raw_string(mem, x)[0] for x in struct.unpack_from(f"<{n}H", mem, 0)]
        out, _ = exetext.rebuild(mem, 0, 0, n, cur)
        self.assertEqual(out, mem)


if __name__ == "__main__":
    unittest.main()
