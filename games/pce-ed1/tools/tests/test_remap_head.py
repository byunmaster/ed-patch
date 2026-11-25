"""머리 바로 뒤·첫 글자 바로 뒤로 들어오는 스크립트 점프 옮기기(`translate.remap_page_jumps`, 11-21 「하루라도→라도」「방금→금」)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M
import translate as T


class _Msg:
    def __init__(self, key, start, end):
        self.key, self.start, self.end = key, start, end


class RemapHead(unittest.TestCase):
    def test_head_len(self):
        self.assertEqual(T._head_len(bytes([0x09, 0x03, 0x01, 0x82, 0xA0]), 0), 3)
        self.assertEqual(T._head_len(bytes([0x1F, 0x83, 0x57, 0x04, 0x01, 0x82, 0xA0]), 0), 5)
        self.assertEqual(T._head_len(bytes([0x82, 0xA0, 0x82, 0xA2]), 0), 0)
        self.assertEqual(T._head_len(bytes([0x1F, 0x83, 0x57, 0x04, 0x82, 0xA0]), 0), 0)  # 개행 없는 인라인 이름

    def test_jump_after_header_follows_new_header(self):
        # 원판: [코드 0F 점프→머리 뒤][메시지: 1F 이름(4B) 04 01 글 글 06] / 번역: 짧은 머리(1F 2B 04 01) + 글
        base = M.BASE
        orig = bytearray(40)
        msg_start = 10
        orig[msg_start : msg_start + 9] = bytes([0x1F, 0x83, 0x57, 0x83, 0x46, 0x04, 0x01, 0x82, 0xA0])
        orig[msg_start + 9] = 0x06
        w = msg_start + 7  # 머리(1F…04 01 = 7B) 바로 뒤
        orig[0:3] = bytes([M.JUMP, (base + w) & 0xFF, (base + w) >> 8])
        new = bytearray(orig)
        new[msg_start : msg_start + 8] = bytes([0x1F, 0xF0, 0x10, 0x04, 0x01, 0xF1, 0x11, 0x06])
        msgs = [_Msg("k", msg_start, msg_start + 10)]
        # `M._parse_from` 이 w 에서 읽을 수 있어야 한다(글 시작) — 원판 글자 `82 A0`
        out = T.remap_page_jumps(1, bytes(orig), bytes(new), msgs, {"k": {"t": "x"}})
        got = (out[1] | out[2] << 8) - base
        self.assertEqual(got, msg_start + 5)  # 우리 머리(1F 2B 04 01 = 5B) 뒤


if __name__ == "__main__":
    unittest.main()
