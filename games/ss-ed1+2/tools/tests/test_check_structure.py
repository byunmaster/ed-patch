"""구조 대조(`check_structure`)의 판정 — **일부러 망가뜨린 사본(제어 코드 한 바이트)으로 검사가 실제로 우는지** 본다(합성 바이트 — 원본 데이터 없음).

배경: ss-ed3 재조판의 채움 바이트(FF FF)가 다음 블록 호출을 막아 첫 장면 대사가 통째로 빠졌다(1,046블록, 마스터 10-22). 이 게임의 구조는 「포인터 → NUL 까지 문자열」이라
같은 사고의 모양은 ① 형식 토큰(%c %s %d) 열이 바뀜 ② 글 뒤 채움 바이트 ③ 종단 NUL 없음 ④ 블록 겹침 ⑤ 코드 위에 이주분이 깔림 이다 — 아래가 각각을 잡는다.
"""

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_structure as C

BASE = 0x06000000
KR = bytes.fromhex("88fc88eb")  # 가짜 2바이트 글자 둘


def blk(*parts):
    return b"".join(parts)


def make(orig_blocks, size=0x100):
    """`[(오프셋, 바이트)]` → (파일 바이트, 덤프 엔트리). 포인터 표는 0x10 부터 4B 씩, 블록 뒤는 `NUL NUL 09` 꼬리."""
    d = bytearray(size)
    ents = []
    for i, (off, raw) in enumerate(orig_blocks):
        d[off : off + len(raw)] = raw
        d[off + len(raw) + 1 : off + len(raw) + 2] = b"\x00"
        d[off + len(raw) + 2 : off + len(raw) + 3] = b"\x09"
        q = 0x10 + 4 * i
        d[q : q + 4] = (BASE + off).to_bytes(4, "big")
        ents.append({"entry_id": i, "file_offset": hex(off), "ptr_at": [hex(q)], "raw_hex": raw.hex()})
    return d, ents


A = b"%c" + KR + b"\x0a" + KR + b"%c"  # 창 하나: 형식 토큰 둘
B = b"%c%s%c" + KR


def scan(orig, built, ents, **kw):
    return C.scan_file(bytes(orig), bytes(built), BASE, ents, **kw)


class Columns(unittest.TestCase):
    def test_ctrl_column_ignores_text_bytes_inside_two_byte_chars(self):
        """2바이트 글자의 뒷 바이트(0x40~)는 제어로 안 센다 — 뒷 바이트가 0x45 여도 글자 한 개."""
        fmt, other, lf = C.ctrl_column(bytes([0x88, 0x45, 0x25, 0x63, 0x0A]))
        self.assertEqual((fmt, other, lf), (["c"], [], 1))

    def test_lead_byte_followed_by_out_of_range_is_other(self):
        """글자 선두 뒤에 SJIS 범위 밖 바이트(FF 채움이 글자에 붙은 꼴)가 오면 제어로 센다."""
        _f, other, _l = C.ctrl_column(bytes([0x88, 0xFF]))
        self.assertIn(0xFF, other)

    def test_fill_ff_is_other_control(self):
        """ss-ed3 사고의 모양 — 글 뒤 FF FF 채움은 기타 제어로 센다."""
        _f, other, _l = C.ctrl_column(KR + b"\xff\xff")
        self.assertEqual(other, [0xFF, 0xFF])

    def test_one_missing_percent_c_is_caught(self):
        bad, _dl, _dp = C.compare_blocks(A, b"%c" + KR + b"\x0a" + KR)
        self.assertTrue(any("형식 토큰" in w for w in bad))

    def test_format_order_swap_is_caught(self):
        bad, *_ = C.compare_blocks(b"%c%s", b"%s%c")
        self.assertTrue(any("형식 토큰" in w for w in bad))

    def test_line_count_change_is_allowed_but_counted(self):
        bad, dl, _dp = C.compare_blocks(A, b"%c" + KR + KR + b"%c")
        self.assertEqual((bad, dl), ([], -1))

    def test_page_break_may_be_added_never_removed(self):
        bad, _dl, dp = C.compare_blocks(A, b"%c" + KR + b"\x08" + KR + b"%c")
        self.assertEqual((bad, dp), ([], 1))
        bad, *_ = C.compare_blocks(b"%c\x08%c", b"%c%c")
        self.assertTrue(any("쪽 넘김" in w for w in bad))

    def test_extra_unknown_control_byte_is_caught(self):
        bad, *_ = C.compare_blocks(A, b"%c" + KR + b"\x0a" + KR + b"%c\x01")
        self.assertTrue(any("기타 제어" in w for w in bad))


class ScanFile(unittest.TestCase):
    def setUp(self):
        self.orig, self.ents = make([(0x40, A), (0x60, B)])

    def test_identical_build_passes(self):
        st, bad, moved, _p = scan(self.orig, self.orig, self.ents)
        self.assertEqual((bad, moved, st["바이트 동일"], st["대조"]), ([], [], 2, 2))

    def test_in_place_shorter_text_with_zero_fill_passes(self):
        built = bytearray(self.orig)
        new = b"%c" + KR + b"%c"  # 줄 하나 빠진 짧은 문안
        built[0x40 : 0x40 + len(A)] = new + b"\x00" * (len(A) - len(new))
        st, bad, _m, _p = scan(self.orig, built, self.ents)
        self.assertEqual(bad, [])
        self.assertEqual(st["채움 블록"], 1)

    def test_dropped_percent_c_in_build_fails(self):
        built = bytearray(self.orig)
        built[0x40 : 0x40 + len(A)] = b"%c" + KR + b"\x0a" + KR + b"\x00\x00"  # 끝 %c 가 빠졌다
        _st, bad, _m, _p = scan(self.orig, built, self.ents)
        self.assertTrue(any("형식 토큰" in w for _k, w in bad))

    def test_ff_fill_after_text_fails(self):
        """글 뒤 NUL 앞에 FF 채움이 끼면 — 글자 바이트를 빼고 봐도 제어 열이 달라 잡힌다."""
        built = bytearray(self.orig)
        built[0x40 : 0x40 + len(A)] = A[:-2] + b"\xff\xff"  # 끝 %c 를 FF FF 로 덮음
        _st, bad, _m, _p = scan(self.orig, built, self.ents)
        self.assertTrue(bad)

    def test_nonzero_fill_in_slack_fails(self):
        built = bytearray(self.orig)
        new = b"%c" + KR + b"%c"
        built[0x40 : 0x40 + len(A)] = new + b"\x00\xff" + b"\x00" * (len(A) - len(new) - 2)  # NUL 뒤 FF 채움
        _st, bad, _m, _p = scan(self.orig, built, self.ents)
        self.assertTrue(any("채움" in w for _k, w in bad))

    def test_missing_terminator_fails(self):
        small = bytearray(b"\xaa" * 0x80)
        d, ents = make([(0x40, A)], size=0x80)
        built = bytearray(d)
        built[0x40:0x80] = b"%c" + KR + b"%c" + b"\xaa" * (0x40 - 6)  # NUL 이 없다
        _st, bad, _m, _p = scan(d, built, ents)
        self.assertTrue(any("NUL" in w for _k, w in bad))
        del small

    def test_pointer_to_other_block_overlap_fails(self):
        built = bytearray(self.orig)
        built[0x14:0x18] = (BASE + 0x42).to_bytes(4, "big")  # 둘째 블록 포인터가 첫 블록 한가운데로
        _st, bad, _m, _p = scan(self.orig, built, self.ents)
        self.assertTrue(bad)

    def test_moved_block_over_code_fails(self):
        """이주분이 원본의 글 구간 밖 · 0 이 아닌 자리(코드)에 깔리면 운다."""
        orig, ents = make([(0x40, A)], size=0x100)
        orig[0x80:0x90] = bytes(range(1, 17))  # 코드/표 자리
        built = bytearray(orig)
        new = b"%c" + KR + b"\x0a" + KR + b"%c\x00"
        built[0x80 : 0x80 + len(new)] = new
        built[0x10:0x14] = (BASE + 0x80).to_bytes(4, "big")
        _st, bad, moved, _p = scan(orig, built, ents)
        self.assertEqual(len(moved), 1)
        self.assertTrue(any("0 이 아닌 자리" in w for _k, w in bad))

    def _grow_first(self, move_neighbor):
        """첫 블록이 제자리에서 이웃 칸까지 늘어난다. 이웃을 이주시켰는지에 따라 허용/실패."""
        orig, ents = make([(0x40, A), (0x50, B)])  # A 뒤 곧바로 B
        built = bytearray(orig)
        grown = A + KR  # 원문보다 2B 길다 → B 의 앞 바이트를 덮는다
        built[0x40 : 0x40 + len(grown) + 1] = grown + b"\x00"
        if move_neighbor:
            built[0xA0 : 0xA0 + len(B) + 1] = B + b"\x00"
            built[0x14:0x18] = (BASE + 0xA0).to_bytes(4, "big")
        return scan(orig, built, ents)

    def test_in_place_growth_over_moved_neighbor_passes_and_is_counted(self):
        st, bad, _m, _p = self._grow_first(True)
        self.assertEqual((bad, st["이웃 칸 인수"]), ([], 1))

    def test_in_place_growth_over_live_neighbor_fails(self):
        _st, bad, _m, _p = self._grow_first(False)
        self.assertTrue(any("원문보다 길다" in w for _k, w in bad))

    def test_pointer_into_block_tail_with_changed_byte_is_reported(self):
        """남의 포인터가 블록 꼬리(NUL 뒤)로 들어오는데 그 바이트를 빌드가 바꿨으면 알린다."""
        orig, ents = make([(0x40, A)])
        tail = 0x40 + len(A) + 1  # NUL 바로 뒤(0 채움 구간)
        orig[0x80:0x84] = (BASE + tail).to_bytes(4, "big")  # 덤프에 없는 리터럴 풀 포인터
        built = bytearray(orig)
        built[tail : tail + 2] = b"\x68\x3f"  # 우리 글자가 꼬리를 덮었다
        self.assertEqual(len(C.tail_entry_changed(bytes(orig), bytes(built), BASE, ents)), 1)
        self.assertEqual(C.tail_entry_changed(bytes(orig), bytes(orig), BASE, ents), [])

    def test_moved_block_into_zero_area_passes(self):
        orig, ents = make([(0x40, A)], size=0x100)
        built = bytearray(orig)
        new = b"%c" + KR + b"\x0a" + KR + b"%c\x00"
        built[0xA0 : 0xA0 + len(new)] = new
        built[0x10:0x14] = (BASE + 0xA0).to_bytes(4, "big")
        _st, bad, moved, _p = scan(orig, built, ents)
        self.assertEqual((bad, len(moved)), ([], 1))

    def test_moved_block_at_odd_address_fails(self):
        orig, ents = make([(0x40, A)], size=0x100)
        built = bytearray(orig)
        new = b"%c" + KR + b"\x0a" + KR + b"%c\x00"
        built[0xA1 : 0xA1 + len(new)] = new
        built[0x10:0x14] = (BASE + 0xA1).to_bytes(4, "big")
        _st, bad, _m, _p = scan(orig, built, ents)
        self.assertTrue(any("홀수" in w for _k, w in bad))

    def test_move_not_in_ledger_fails(self):
        orig, ents = make([(0x40, A)], size=0x100)
        built = bytearray(orig)
        new = b"%c" + KR + b"\x0a" + KR + b"%c\x00"
        built[0xA0 : 0xA0 + len(new)] = new
        built[0x10:0x14] = (BASE + 0xA0).to_bytes(4, "big")
        _st, bad, _m, _p = scan(orig, built, ents, moved_ok=set())
        self.assertTrue(any("장부" in w for _k, w in bad))
        _st, bad, _m, _p = scan(orig, built, ents, moved_ok={"#0"})
        self.assertEqual(bad, [])

    def test_pointers_of_one_block_must_agree(self):
        orig, ents = make([(0x40, A)])
        ents[0]["ptr_at"] = ["0x10", "0x18"]
        orig[0x18:0x1C] = (BASE + 0x40).to_bytes(4, "big")
        built = bytearray(orig)
        built[0x18:0x1C] = (BASE + 0x50).to_bytes(4, "big")
        _st, bad, _m, _p = scan(orig, built, ents)
        self.assertTrue(any("서로 다른 목표" in w for _k, w in bad))

    def test_marker_09_in_slot_tail_may_be_reused_by_pool(self):
        """비운 칸 꼬리의 0x09 는 풀로 나간다 — 그 위에 이주분이 깔려도(실기 무죄) 통과."""
        orig, ents = make([(0x40, A), (0x60, B)])
        built = bytearray(orig)
        # 첫 블록을 옮기고 그 칸(0x40..꼬리 09 까지)에 둘째 블록의 새 문안을 깐다 — 칸 끝은 slot_tail_end
        new = b"%c%s%c" + KR + b"\x00"
        end = C.slot_tail_end(orig, 0x40 + len(A))
        self.assertGreater(end, 0x40 + len(A) + 1)  # 꼬리에 09 가 들어 있다
        built[0x40 : 0x40 + len(new)] = new
        built[0x14:0x18] = (BASE + 0x40).to_bytes(4, "big")
        built[0x10:0x14] = (BASE + 0xA0).to_bytes(4, "big")  # 첫 블록은 0 영역으로
        a = b"%c" + KR + b"\x0a" + KR + b"%c\x00"
        built[0xA0 : 0xA0 + len(a)] = a
        _st, bad, _m, _p = scan(orig, built, ents)
        self.assertEqual(bad, [])


class Switch(unittest.TestCase):
    def test_reloc_off_reads_keys_and_is_off_by_default(self):
        import patch_scn as P

        old_env, old = os.environ.get("ED_RELOC_OFF"), P._RELOC_OFF
        try:
            P._RELOC_OFF = None
            os.environ["ED_RELOC_OFF"] = os.path.join(tempfile.gettempdir(), "nonexistent_reloc_off.txt")
            self.assertFalse(P.reloc_off("/BIN/ED1SCN08.BIN", {"entry_id": 170}))  # 파일 없음 = 아무것도 안 끈다
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write("# 주석\nED1SCN08#170  # 사유\nED2#6\n")
            P._RELOC_OFF = None
            os.environ["ED_RELOC_OFF"] = f.name
            self.assertTrue(P.reloc_off("/BIN/ED1SCN08.BIN", {"entry_id": 170}))
            self.assertTrue(P.reloc_off("/ED2.BIN", {"entry_id": 6}))
            self.assertFalse(P.reloc_off("/BIN/ED1SCN08.BIN", {"entry_id": 171}))
            os.unlink(f.name)
        finally:
            P._RELOC_OFF = old
            if old_env is None:
                os.environ.pop("ED_RELOC_OFF", None)
            else:
                os.environ["ED_RELOC_OFF"] = old_env


if __name__ == "__main__":
    unittest.main()
