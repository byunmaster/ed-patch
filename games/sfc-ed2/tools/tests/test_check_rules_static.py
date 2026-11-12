"""check_rules_static 양성 대조 — 가운데 맞춤·한 줄 문장·쉼표 축마다 일부러 깨뜨린 줄이 걸리는지, 정상은 안 걸리는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_rules_static as C


def hits(addr: str, kr: str) -> dict[str, list[str]]:
    return C.scan([f"{addr}\tあ\t{kr}\t"])


class T(unittest.TestCase):
    def test_center_fix(self):
        # 같은 줄을 패딩만 다르게: 가운데에 가까운 쪽은 안 걸리고, 한쪽으로 쏠린 쪽(패딩으로 줄일 수 있음)은 걸린다
        core = "왕자가 태어났다."
        offs = {p: C.center_off(" " * p + core, 24) for p in range(0, 14)}
        good = min(offs, key=lambda p: abs(offs[p]))
        bad = 0 if good else 13
        self.assertEqual(hits("D7E248", " " * good + core)["C8_fix"], [])
        self.assertEqual(len(hits("D7E248", " " * bad + core)["C8_fix"]), 1)
        self.assertEqual(hits("C20000", " " * bad + core)["C8_fix"], [])  # 가운데 맞춤 구간 밖

    def test_sentence(self):
        self.assertEqual(len(hits("C20000", "표가 없잖아. 저쪽에서↵사 오라고.")["S10"]), 1)
        self.assertEqual(hits("C20000", "표가 없잖아.↵저쪽에서 사 오라고.")["S10"], [])
        self.assertEqual(hits("C20000", "아주 긴 문장이 한 줄에 들어가지 않아서 두 줄로↵나뉘는 경우라면 정상이다. 정말로.")["S10"], [])

    def test_comma(self):
        self.assertEqual(len(hits("C20000", "아니. 그건 몰랐는데, 그때 알았다.")["K13_9"]), 1)
        self.assertEqual(hits("C20000", "아니. 그건 정말 오래전부터 계속 몰랐던 일인데, 그때 알았다.")["K13_9"], [])
        self.assertEqual(len(hits("C20000", "일행은 크게 다치시고, 쓰러졌다.")["K13_conn"]), 1)
        self.assertEqual(hits("C20000", "아트라스, 일행은 쓰러졌다.")["K13_conn"], [])

    def test_hud(self):
        # 합성 롬 — 지명 64칸이 전부 같은 문자열을 가리킨다: 글자 4자(48px) 앞에 전각 공백 하나(12px)면 가운데(24px 여백), 패딩 없으면 어긋남
        def rom_with(entry: bytes) -> bytes:
            rom = bytearray(0x190000)
            base = C.common.snes2off(C.HUD_TABLE)
            for i in range(C.HUD_COUNT):
                rom[base + 2 * i : base + 2 * i + 2] = (0xF980).to_bytes(2, "little")
            rom[base + 0x80 : base + 0x80 + len(entry) + 1] = entry + b"\x00"
            return bytes(rom)

        word = bytes.fromhex("83c28398836b84f7")  # 글자 4자(2B씩)
        self.assertEqual(C.scan_hud(rom_with(b"\x80\x00" + word + b"  ")), [])
        self.assertEqual(len(C.scan_hud(rom_with(word + b"    "))), C.HUD_COUNT)
        self.assertEqual(C.scan_hud(rom_with(bytes.fromhex("83c2") * 7)), [])  # 박스보다 넓은 이름은 센 대상이 아니다


if __name__ == "__main__":
    unittest.main()
