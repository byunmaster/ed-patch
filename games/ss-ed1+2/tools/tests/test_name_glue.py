import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_name_glue as G
import font
import msgwrap
import patch_ui

PLAN = {c: (bytes([0x88 + i, 0x40]), i) for i, c in enumerate("레스의잎")}


class NameGlue(unittest.TestCase):
    def test_glue_bytes(self):
        b = font.to_bytes(font.glue_name("레스의 잎"), PLAN)
        self.assertIn(bytes([font.NB_CODE]), b)
        self.assertNotIn(b" ", b)
        self.assertEqual(font.byte_len(font.glue_name("레스의 잎")), len(b))

    def test_wrap_keeps_name_whole(self):
        pre = b"a" * 21  # 줄 폭 28 — 품명 앞 낱말만 들어간다
        plain = font.to_bytes("레스의 잎", PLAN)
        glued = font.to_bytes(font.glue_name("레스의 잎"), PLAN)
        cut = msgwrap.wrap(pre + b" " + plain)
        whole = msgwrap.wrap(pre + b" " + glued)
        first = plain.split(b" ")[0]  # 대조군: 공백 꼴은 이름 가운데서 갈린다
        self.assertTrue(cut.split(bytes([msgwrap.NL]))[0].endswith(first))
        self.assertEqual(whole.count(bytes([msgwrap.NL])), 1)
        self.assertTrue(whole.split(bytes([msgwrap.NL]))[1].startswith(glued))

    def test_scan_positive_control(self):
        glued = font.to_bytes(font.glue_name("레스의 잎"), PLAN)
        plain = font.to_bytes("레스의 잎", PLAN)
        d = bytearray(0x100)
        d[0x20 : 0x20 + len(glued)] = glued
        d[0x60 : 0x60 + len(plain)] = plain
        ptr = lambda at: (at + patch_ui.NAME_PTR_BASE).to_bytes(4, "big")
        d[0:4], d[4:8] = ptr(0x20), ptr(0x60)
        n, bad = G.scan(bytes(d), [("레스의 잎", [0])], PLAN)
        self.assertEqual((n, bad), (1, []))
        n, bad = G.scan(bytes(d), [("레스의 잎", [4])], PLAN)
        self.assertEqual(len(bad), 1)

    def test_split_name_scan_and_glue(self):
        plan = {c: (bytes([0x88 + i, 0x40]), i) for i, c in enumerate("레스의잎")}
        raw = font.to_bytes("%c레스의 %c%c잎%c", plan)  # 색 표지로 쪼갠 조각 — 공백 꼴
        self.assertGreaterEqual(G.split_plain(b"\0" + raw, "레스의 잎", plan), 0)
        fixed = font.to_bytes(font.glue_in_text("%c레스의 %c%c잎%c", ["레스의 잎"]), plan)
        self.assertEqual(G.split_plain(b"\0" + fixed, "레스의 잎", plan), -1)
        self.assertEqual(G.split_plain(b"\0" + font.to_bytes("%c레스의 잎%c", plan), "레스의 잎", plan), -1)


if __name__ == "__main__":
    unittest.main()
