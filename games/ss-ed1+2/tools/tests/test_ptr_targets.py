"""메시지 포인터 목표 점검(`check_ptr_targets`)의 판정 — 단위 밖 목표와 빌드에서 안 바뀐 목표를 **잡는다**(합성 데이터).

실측 근거: sfc-ed1 이 번역 단위 목록 밖을 포인터가 가리켜 장면 대사 101개가 일본어로 남았다(2026-10-18).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_ptr_targets as C

JP = "が現れた。".encode("cp932")


class Judge(unittest.TestCase):
    def test_target_outside_known_spans_is_caught(self):
        self.assertEqual(C.outside_spans({10, 40}, [(0, 20)]), [40])

    def test_target_inside_a_span_passes(self):
        self.assertEqual(C.outside_spans({10, 19}, [(0, 20)]), [])

    def test_jp_text_start_detected_and_midstring_ignored(self):
        data = b"\x00" + JP + b"\x00"
        self.assertIsNotNone(C.jp_text_at(data, 1))
        self.assertIsNone(C.jp_text_at(data, 3))  # 글 한복판(앞 바이트가 글자)

    def test_untouched_jp_in_build_is_caught(self):
        built = b"\x00" + JP + b"\x00"
        self.assertEqual(C.unchanged_jp({1}, built), [1])

    def test_translated_target_passes(self):
        built = b"\x00" + bytes.fromhex("88dc8a488ce08a49") + b"\x00" * 3
        self.assertEqual(C.unchanged_jp({1}, built), [])

    def test_stale_old_slot_is_not_a_target(self):
        """옮긴 블록의 옛 칸에 일본어가 남아도 아무 포인터도 안 가리키면 목표가 아니다."""
        built = b"\x00" + JP + b"\x00" + (0).to_bytes(4, "big")
        self.assertEqual(C.unchanged_jp(C.targets(built, 0x06000000), built), [])

    def test_targets_collects_in_file_pointers_only(self):
        base = 0x06000000
        data = (base + 8).to_bytes(4, "big") + (0x12345678).to_bytes(4, "big") + b"\x00" * 8
        self.assertEqual(C.targets(data, base), {8})


if __name__ == "__main__":
    unittest.main()
