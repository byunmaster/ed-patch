"""분열·소환 접미 상수(`battle.SUFFIX_SITES`) — 블록 → 템플릿 이름 길이 → 접미 자리 상수 짝을 박는다(10-24, sfc-ed2 test_name_ai_sites 꼴).

원문 코드는 접미 바이트를 이름 칸 +(원문 이름 길이−1)에 읽고 쓴다. 우리 이름은 길이가 달라 그 상수가 종결 06 을 덮거나 칸 밖을 가리켰다.
여기선 원본 롬 없이 (a) 표의 원본 바이트가 명령 꼴과 맞는지 (b) 새 바이트가 우리 접미 자리를 가리키는지 (c) 디스어셈블 검산을 본다.
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle

try:
    from capstone import CS_ARCH_M68K, CS_MODE_M68K_000, Cs

    MD = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
except ImportError:  # capstone 없으면 디스어셈 검산만 건너뛴다
    MD = None

# 블록 → (원문 템플릿 이름 길이, 우리 템플릿 이름 길이(접미 1B 포함), 이름 칸 기준 주소)
ORIG_LEN = {24: 10, 35: 10, 40: 15, 48: 12, 53: 8}
KR_LEN = {24: 7, 35: 9, 40: 9, 48: 9, 53: 5}
ADDR = {
    24: 0xFF1F75,
    35: 0xFF1FB5,
    40: 0xFF1FBA,
    48: 0xFF1FB7,
    53: 0xFF1FB3,
}  # 원문 접미 자리(절대 주소)


def dis(b: bytes) -> str:
    ins = next(MD.disasm(b, 0))
    return f"{ins.mnemonic} {ins.op_str}"


class SuffixSites(unittest.TestCase):
    def test_table_shape(self):
        self.assertEqual(sorted(battle.SUFFIX_SITES), [24, 35, 40, 48, 53])
        for n, (t, sites) in battle.SUFFIX_SITES.items():
            self.assertEqual(t, 3, n)
            for kind, _at, old_hex in sites:
                self.assertIn(kind, ("addr", "disp", "imm", "cmp"))
                self.assertGreater(len(old_hex), 0)

    def test_addr_moves_to_our_suffix(self):
        for n, orig in ADDR.items():
            p_o, p_k = ORIG_LEN[n] - 1, KR_LEN[n] - 1
            new = battle.suffix_new("addr", struct.pack(">H", orig & 0xFFFF), p_o, p_k, 0x44)
            self.assertEqual(struct.unpack(">H", new)[0], (orig & 0xFFFF) - p_o + p_k, n)
            # 새 자리 = 우리 이름의 끝 글자(종결 06 바로 앞)
            base = (orig & 0xFFFF) - p_o
            self.assertEqual(struct.unpack(">H", new)[0] - base, KR_LEN[n] - 1, n)

    def test_values_become_ascii(self):
        self.assertEqual(battle.suffix_new("imm", b"\x60", 9, 6, 0x41), b"\x41")  # Ａ
        self.assertEqual(battle.suffix_new("imm", b"\x63", 9, 8, 0x44), b"\x44")  # Ｄ
        self.assertEqual(battle.suffix_new("cmp", b"\x66", 9, 8, 0x44), b"\x47")  # 한계 Ｇ → G
        self.assertEqual(battle.suffix_new("cmp", b"\x68", 7, 4, 0x44), b"\x49")
        self.assertEqual(battle.suffix_new("disp", b"\x00\x39", 9, 8, 0x44), b"\x00\x38")
        self.assertEqual(battle.suffix_new("disp", b"\x00\x3e", 14, 8, 0x44), b"\x00\x38")

    @unittest.skipIf(MD is None, "capstone 없음")
    def test_rebuilt_instructions_decode(self):
        # block 35 초기화: move.b #$44,$FF1FB4.l
        new_imm = battle.suffix_new("imm", b"\x63", 9, 8, 0x44)
        new_addr = battle.suffix_new("addr", b"\x1f\xb5", 9, 8, 0x44)
        self.assertEqual(
            dis(b"\x13\xfc\x00" + new_imm + b"\x00\xff" + new_addr), "move.b #$44, $ff1fb4.l"
        )
        # lea / move.b abs,d0 / cmpi / disp
        self.assertEqual(dis(b"\x47\xf9\x00\xff" + new_addr), "lea.l $ff1fb4.l, a3")
        self.assertEqual(dis(b"\x10\x39\x00\xff" + new_addr), "move.b $ff1fb4.l, d0")
        self.assertEqual(
            dis(b"\x0c\x00\x00" + battle.suffix_new("cmp", b"\x66", 9, 8, 0x44)), "cmpi.b #$47, d0"
        )
        self.assertEqual(
            dis(b"\x15\x40" + battle.suffix_new("disp", b"\x00\x39", 9, 8, 0x44)),
            "move.b d0, $38(a2)",
        )

    @unittest.skipIf(MD is None, "capstone 없음")
    def test_block62_rebuild(self):
        base5 = 0xFF1DBC + 5 * 0x40 + 0x30
        new = battle.suffix_62(base5, base5 + 0x40, 6)  # 카자즘 6B
        self.assertEqual(len(new), 18)
        self.assertEqual(len(bytes.fromhex(battle.SUFFIX_62[3])), 18)
        out = [dis(new[i : i + 8]) for i in (0, 8)] + [dis(new[16:])]
        self.assertEqual(out, ["move.w #$4106, $ff1f32.l", "move.w #$4206, $ff1f72.l", "nop "])


if __name__ == "__main__":
    unittest.main()
