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

    def test_shrink_without_pad_leaves_empty_string_in_slack(self):
        """🔴 실측 사고(ED3, 2026-09-26): 칸이 줄면 남는 슬랙이 `TERM_FFFF` 두 개(=빈
        문자열)로 채워진다. 표를 안 보고 종결마다 이어 읽는 순차 스캔 UI 목록은 그 빈
        문자열을 「목록 끝」으로 읽어 뒤 항목이 안 보인다."""
        mem = make([[0x50, 0x51], [0x40, 0x41, 0x42]], terms=[0x8000, 0x8000])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        out, slack = exetext.rebuild(mem, 0, 0, n, [[0x50, 0x51], [0x40]])
        self.assertEqual(slack, 4)
        second = struct.unpack_from(f"<{n}H", out, 0)[1]
        codes, term = exetext.raw_string(out, second)
        self.assertEqual((codes, term), ([0x40], 0x8000))
        # 그 뒤에 남는 슬랙이 빈 문자열(종결부터 바로 또 종결)이다
        after = struct.unpack_from("<H", out, second + 2 * 2)[0]
        self.assertTrue(exetext.is_term(after))

    def test_pad_code_extends_last_chunk_entry_instead_of_faking_a_list_end(self):
        """`pad_code` 를 주면 슬랙이 **마지막 조각의 글자열**로 늘어나고(종결 앞), 화면엔 안
        보이는 채움 글자만 늘 뿐 슬랙 자리에 새 빈 문자열이 생기지 않는다(위 함정의 수정)."""
        mem = make([[0x50, 0x51], [0x40, 0x41, 0x42]], terms=[0x8000, 0x8000])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        out, slack = exetext.rebuild(mem, 0, 0, n, [[0x50, 0x51], [0x40]], pad_code=0x99)
        self.assertEqual(slack, 0, "채움 글자로 다 썼으니 슬랙은 안 남는다")
        second = struct.unpack_from(f"<{n}H", out, 0)[1]
        codes, term = exetext.raw_string(out, second)
        self.assertEqual((codes, term), ([0x40, 0x99, 0x99], 0x8000))
        # 종결이 칸의 원래 끝자리 그대로다 — 뒤에 다른 문자열이 있었다면 그 시작이 안 밀린다
        self.assertEqual(len(out), len(mem))

    def test_pad_code_does_not_touch_untouched_chunks(self):
        """짧아지지 않은 칸은 `pad_code` 를 줘도 그대로다."""
        mem = make([[0x40, 0x41], [0x42, 0x43]])
        n = exetext.table_at(mem, 0, CM, min_n=2)
        cur = [exetext.raw_string(mem, x)[0] for x in struct.unpack_from(f"<{n}H", mem, 0)]
        out, slack = exetext.rebuild(mem, 0, 0, n, cur, pad_code=0x99)
        self.assertEqual(out, mem)
        self.assertEqual(slack, 0)


class TestDetachedAndFixed(unittest.TestCase):
    """2026-09-27 — 표 규격 밖이라 **빌드가 통째로 건너뛰던** 두 자리(아이템·인물 이름).

    스캐너가 「표 없음」이라 하면 빌드는 조용히 넘어가고 화면엔 일본어가 남는다 — 실패가 아니라
    누락이라 게이트도 초록이었다. 여기서 박는 계약은 둘: 떨어진 표도 `rebuild` 로 싸진다 ·
    고정 칸은 모양(글자·0 채움·마지막 0xFFFF)을 지키고 넘치면 운다.
    """

    def test_rebuild_works_when_table_is_away_from_base(self):
        """아이템 표처럼 표 주소 ≠ base 여도 `rebuild` 가 풀을 싸고 표를 고친다."""
        pool = bytearray(b"\x00\x00")  # base 자리(빈 이름) — 실물처럼 풀 앞에 한 워드
        offs = []
        for codes in ([0x40, 0x41], [0x42, 0x43, 0x44]):
            offs.append(len(pool))
            pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", 0xFFFF)
        tbl = struct.pack("<2H", *offs)
        mem = bytearray(tbl + bytes(pool))
        base = len(tbl)
        out, _ = exetext.rebuild(bytes(mem), 0, base, 2, [[0x50], [0x51, 0x52]])
        got = [exetext.raw_string(out, base + x)[0] for x in struct.unpack_from("<2H", out, 0)]
        self.assertEqual(got, [[0x50], [0x51, 0x52]])

    def test_fixed_slot_keeps_shape(self):
        """넷 글자 → 셋 글자: 뒤는 0, 마지막 워드는 0xFFFF 그대로, 칸 크기 불변."""
        slot = bytearray(struct.pack("<7H", 0xA6, 0xD2, 0xD7, 0x98, 0, 0, 0xFFFF))
        exetext.write_fixed_slot(slot, 0, 7, [0x100, 0x101, 0x102])
        self.assertEqual(struct.unpack("<7H", slot), (0x100, 0x101, 0x102, 0, 0, 0, 0xFFFF))

    def test_fixed_slot_refuses_overflow(self):
        """칸(6글자)을 넘으면 운다 — 다음 사람의 이름을 덮지 않는다."""
        slot = bytearray(struct.pack("<7H", 0x40, 0, 0, 0, 0, 0, 0xFFFF))
        with self.assertRaises(exetext.ExeTextError):
            exetext.write_fixed_slot(slot, 0, 7, list(range(0x40, 0x47)))


if __name__ == "__main__":
    unittest.main()
