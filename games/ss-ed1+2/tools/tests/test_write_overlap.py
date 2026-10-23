"""쓰기 겹침 감사 회귀 — 번역 위에 다른 번역을 덮는 결함(ED2MON 꼬리·챕터 카드 꼬리, 2026-10-19)을 잡고, 정당한 겹침은 통과시킨다. 원본 없이 돈다."""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "..", "shared"))

import check_write_overlap as C
import font


def row(t, label, o, data):
    return {"t": t, "a": o, "n": len(data), "l": label, "h": "x", "z": int(not any(data)), "d": data.hex(), "o": o}


def kr(n=3):
    """우리 한글 슬롯 코드로 된 바이트 — 번역이다."""
    import json

    import common

    syl = json.load(open(os.path.join(common.GAME_DIR, "hangul_map_11kanji.json"), encoding="utf-8"))["syllables"]
    return b"".join(font.sjis_of_index(i) for i in list(syl.values())[:n])


class Overlap(unittest.TestCase):
    def kinds(self, rows):
        return [k for *_x, k in C.overlaps(rows)]

    def test_translation_overwritten_by_another_stage_is_a_defect(self):
        a = row("patch_ui.py", "/BIN/ED2MON04.BIN 시스템 메시지", 0x4D78, kr(4) + b"\x00")
        b = row("patch_scn.py", "/BIN/ED2MON04.BIN 이주 0x2574", 0x4D78, kr(3) + b"\x00")
        self.assertEqual(self.kinds([a, b]), ["over"])

    def test_japanese_remnant_replaced_is_allowed(self):
        jp = "は仲間を呼んだ。".encode("cp932") + b"\x00"
        a = row("patch_ui.py", "/BIN/ED2MON04.BIN 시스템 메시지", 0x100, jp)
        b = row("patch_scn.py", "/BIN/ED2MON04.BIN 씬 0x100", 0x100, kr(4) + b"\x00")
        self.assertEqual(self.kinds([a, b]), ["jp"])

    def test_pointer_retarget_is_allowed(self):
        a = row("patch_ui.py", "/ED2.BIN 아이템 포인터", 0x1430, bytes.fromhex("06028b78"))
        b = row("patch_scn.py", "/ED2.BIN 이주 포인터 0x1430", 0x1430, bytes.fromhex("060496c8"))
        self.assertEqual(self.kinds([a, b]), ["ptr"])

    def test_padding_and_same_value_and_directory_updates_are_ignored(self):
        z = row("patch_ui.py", "/BIN/ED2MON04.BIN 시스템 메시지", 0x200, bytes(8))
        w = row("patch_scn.py", "/BIN/ED2MON04.BIN 이주 0x200", 0x200, kr(2) + b"\x00")
        self.assertEqual(self.kinds([z, w]), ["pad"])
        a = row("expand_files.py", "/BIN/ED1SCN03.BIN 크기 30532→30720", 0xDC, bytes.fromhex("0078000000007800"))
        b = row("relocate_files.py", "/BIN/ED1SCN03.BIN 크기 30720→32768", 0xDC, bytes.fromhex("0080000000008000"))
        self.assertEqual(self.kinds([a, b]), [])  # 디렉터리 레코드 갱신은 뺀다

    def test_same_tool_and_other_files_do_not_collide(self):
        a = row("patch_ui.py", "/BIN/ED2MON04.BIN 시스템 메시지", 0x300, kr(2))
        b = row("patch_ui.py", "/BIN/ED2MON04.BIN 시스템 메시지", 0x300, kr(3))
        c = row("patch_scn.py", "/BIN/ED2MON05.BIN 이주 0x300", 0x300, kr(3))  # 다른 파일
        self.assertEqual(self.kinds([a, b, c]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
