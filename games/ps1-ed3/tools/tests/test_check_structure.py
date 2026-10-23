"""구조 대조 검사기(`check_structure.compare_member`)의 회귀 — 가짜 멤버 바이트로 「일부러 망가뜨리면 우는가」를 본다(원본 바이트 없음)."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_structure as C

TERM = 0xFFFF


def make(segs, script=b"\x00" * 6, fill=0):
    """가짜 대본 멤버 — [u16 BASE][스크립트: 0x90 V 하나 + 나머지][풀]. 스크립트의 첫 포인터는 0번 조각을 가리킨다."""
    base = 2 + len(script) + 4  # 포인터 4B(0F 90 V) 자리
    base += base & 1
    head = bytearray(struct.pack("<H", base) + b"\x0f\x90\x00\x00" + script)
    head += b"\x00" * (base - len(head))
    pool = b"".join(struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", TERM) for s in segs)
    m = bytearray(head + pool + b"\x00" * fill)
    struct.pack_into("<H", m, 4, 0)  # V = 풀 첫 조각(TEXT_BASE + 0)
    return bytes(m)


def dec(codes):
    return "가나"  # 숫자 글자 없는 번역(한글 수사)


class StructureTest(unittest.TestCase):
    def setUp(self):
        self.orig = make([[100, 101, 102], [103, 0xEEEE, 20, 104], [105]])

    def run_cmp(self, new, orig=None):
        return C.compare_member(orig or self.orig, new, dec, lambda c: {c})

    def test_retranslated_and_filled_passes(self):
        # 글자 길이가 달라도(포인터 재계산) · 꼬리 0 채움이 있어도 구조는 같다.
        y = make([[200, 201], [202, 203, 204, 205, 206], [207]], fill=6)
        errs, info = self.run_cmp(y)
        self.assertEqual(errs, [], errs)
        self.assertEqual(info["fill"], 6)

    def test_script_byte_change_fails(self):
        y = bytearray(make([[200, 201, 202], [203, 204], [205]]))
        y[8] ^= 0x01  # 포인터 자리가 아닌 스크립트 바이트
        errs, _ = self.run_cmp(bytes(y))
        self.assertTrue(any("스크립트 바이트" in e for e in errs), errs)

    def test_segment_count_change_fails(self):
        errs, _ = self.run_cmp(make([[200], [201]]))
        self.assertTrue(any("조각 수" in e for e in errs), errs)

    def test_nonzero_fill_fails(self):
        y = bytearray(make([[200], [201], [202]], fill=4))
        y[-1] = 0xFF  # 마지막 종결 뒤 채움이 0 이 아니다 (ss-ed3 10-21: FF FF 채움 사고)
        errs, _ = self.run_cmp(bytes(y))
        self.assertTrue(any("0 이 아닌" in e for e in errs), errs)

    def test_unterminated_pool_fails(self):
        y = make([[200], [201], [202]])[:-2]  # 마지막 0xFFFF 가 잘렸다
        errs, _ = self.run_cmp(y)
        self.assertTrue(errs)

    def test_pointer_to_wrong_piece_fails(self):
        y = bytearray(make([[200, 201], [202], [203]]))
        struct.pack_into("<H", y, 4, 2 * 3)  # 0번이 아니라 1번 조각을 가리킨다
        errs, _ = self.run_cmp(bytes(y))
        self.assertTrue(any("새 시작을 안 가리킴" in e for e in errs), errs)

    def test_number_mark_mismatch_fails(self):
        # 원문 표식 값 20 ↔ 번역이 숫자 글자 「30」 — 값이 다르다
        y = make([[200], [201, 3, 0, 202], [203]])
        errs, _ = C.compare_member(self.orig, y, lambda c: "30" if 3 in c else "", lambda c: {c})
        self.assertTrue(any("숫자" in e for e in errs), errs)
        ok, _ = C.compare_member(self.orig, y, lambda c: "20" if 3 in c else "", lambda c: {c})
        self.assertEqual(ok, [], ok)


if __name__ == "__main__":
    unittest.main()
