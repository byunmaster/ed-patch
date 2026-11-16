"""SELECT+RUN 디버그 키 — 코드 자리·트램펄린 배치 계약(실행은 헤드리스 시험으로 본다: status)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debugkey
import font
import hook


class DebugKeyLayoutTest(unittest.TestCase):
    def test_code_fits_reserved_dyn_slots(self):
        self.assertLessEqual(len(debugkey.code()), debugkey.ROOM)
        # 코드 자리는 동적 칸 16~23 — 씬 하나의 동적 글자 한도(16)가 그 앞에서 끝난다
        self.assertEqual(debugkey.OFF, font.glyph_at(font.DYN0) % 0x2000 + font.DYN_RESERVE_FROM * font.PACKED_BYTES)

    def test_tick_tail_ends_with_jmp_to_original_and_call_operand_is_where_hook_says(self):
        t = hook.tick_routine()
        self.assertEqual(t[-3:], bytes([0x4C, hook.IRQ_ORIG & 0xFF, hook.IRQ_ORIG >> 8]))  # 끝은 원래 대상으로 JMP
        o = hook.TICK_CALL_OP - hook.TICK_ADDR
        self.assertEqual(t[o - 1 : o + 2], b"\x20\x00\x00")  # 블록 쪽이 채우는 `JSR tick` 피연산자 자리
        self.assertLessEqual(len(t), hook.BLINK_ADDR - hook.TICK_ADDR)

    def test_entry_restores_mapping_outside_the_mapped_window(self):
        e = debugkey.entry()
        i = e.index(0x20)  # JSR tick
        self.assertEqual(e[i + 3 : i + 6], bytes([0x68, 0x53, 0x08]))  # 돌아온 뒤 PLA · TAM #MPR3 — 호출한 쪽에서 복원
        tick_end = debugkey._asm().labels["done"] - debugkey.ORG
        self.assertEqual(debugkey.code()[tick_end], 0x60)  # tick 은 RTS 로 끝난다(안에서 복원하지 않는다)

    def test_menu_site_shape(self):
        old, new = debugkey.menu_site()
        self.assertEqual(len(old), len(new))
        self.assertEqual(new[-5:], bytes([0x90, 0x03, 0x20, 0xCB, 0x64]))  # BCC +3 · JSR $64CB


if __name__ == "__main__":
    unittest.main()
