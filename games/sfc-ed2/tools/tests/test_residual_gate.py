"""롬 전체 일본어 잔존 게이트 — 분모(`segs.segments`)가 놓친 문안(두 종 등장 첫 메시지 둘, 10-18)이 다시 빠지면 운다. 원본이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common

HOLES = (0xD434F0, 0xD43513, 0xD489AD, 0xD489CC)
# 단독·두 종 「…が現れた。」 첫 메시지(이름이 문장 안에 박힘) — 겹치는 런 때문에 게이트가 놓쳤던 것(10-18 메탈스팀 군)
HOLES2 = (0xD43DBB, 0xD44964, 0xD4519A, 0xD4567D, 0xD45D96, 0xD48890, 0xD49189, 0xD4BCCE, 0xD4BEEE, 0xD4C131, 0xD4C984, 0xD4CCA1, 0xD5D2AF, 0xD5D7A3, 0xD5DAC6)


@unittest.skipUnless(common.ORIG_ROM.exists(), "원본 롬 없음")
class ResidualGate(unittest.TestCase):
    def setUp(self):
        import build
        import segs

        self.build, self.segs = build, segs
        self.src = common.rom_bytes()

    def test_holes_are_segments(self):
        starts = {common.off2snes(a) for a, _b in self.segs.segments(self.src)}
        for h in HOLES + HOLES2:
            self.assertIn(h, starts)

    def _kr(self):
        p = common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
        if not p.exists():
            self.skipTest("제품 롬 없음")
        return bytearray(p.read_bytes())

    def test_gate_passes_on_product_rom(self):
        self.build.residual_jp_gate(self.src, bytes(self._kr()), True)

    def test_gate_fails_if_holes_reopen(self):
        rom = self._kr()
        for a, b in ((0xD434F0, 0xD43532), (0xD489AD, 0xD489DF)):  # 번역된 두 군 첫 메시지를 원문으로 되돌린다
            o, e = common.snes2off(a), common.snes2off(b)
            rom[o:e] = self.src[o:e]
        old = self.segs.EXTRA
        self.segs.EXTRA = tuple(x for x in old if x[0] not in HOLES)
        try:
            with self.assertRaises(SystemExit):
                self.build.residual_jp_gate(self.src, bytes(rom), True)
        finally:
            self.segs.EXTRA = old

    def test_gate_fails_if_overlapping_head_reopens(self):
        """이름이 박힌 첫 메시지가 뒤따르는 구간과 한 런으로 이어진 꼴 — 겹침만 보던 옛 게이트는 통과시켰다."""
        rom = self._kr()
        o, e = common.snes2off(0xD5D2AF), common.snes2off(0xD5D2C8)
        rom[o:e] = self.src[o:e]
        old = self.segs.EXTRA
        self.segs.EXTRA = tuple(x for x in old if x[0] != 0xD5D2AF)
        try:
            with self.assertRaises(SystemExit):
                self.build.residual_jp_gate(self.src, bytes(rom), True)
        finally:
            self.segs.EXTRA = old

    def test_gate_catches_short_sentence(self):
        """5자짜리 짧은 문장(「…が現れた。」 꼴)이 알려진 구간 밖에 새로 생기면 잡는다 — 런 최소 길이가 길면(12자) 샌다(md-ed1 발견)."""
        src = bytearray(self.src)
        lo, hi = common.snes2off(0xD50000), common.snes2off(0xD5FFFF)
        pos = next((i for i in range(lo, hi - 16) if not any(src[i : i + 16])), None)
        if pos is None:
            self.skipTest("$D5 에 빈 자리 없음")
        sent = bytes.fromhex("8059" "81e1" "8096" "806c" "8002")  # 5자
        src[pos : pos + 10] = sent
        rom = bytearray(self._kr())
        rom[pos : pos + 10] = sent
        with self.assertRaises(SystemExit):
            self.build.residual_jp_gate(bytes(src), bytes(rom), True)

    def test_pointer_gate_passes_on_product_rom(self):
        self.build.pointer_target_gate(self.src, bytes(self._kr()), True)

    def test_pointer_gate_fails_if_a6_target_left_out(self):
        """`$A6` 즉치가 가리키는 한 글자 조각($C0:F031 `は`)을 구간 목록에서 빼면 — 구간 안 가리킴 + 롬에서 안 바뀜 — 잡는다."""
        rom = self._kr()
        o = common.snes2off(0xC0F032)
        rom[o : o + 2] = self.src[o : o + 2]
        old = self.segs.EXTRA
        self.segs.EXTRA = tuple(x for x in old if x[0] != 0xC0F032)
        try:
            with self.assertRaises(SystemExit):
                self.build.pointer_target_gate(self.src, bytes(rom), True)
        finally:
            self.segs.EXTRA = old

    def test_pointer_gate_fails_on_synthetic_jump_target(self):
        """점프 목표가 목록 밖 일본어를 가리키는 합성 사례 — 번역 안 된 $CB3869(사전 항목 꼴)를 목표로 넣으면 실패."""
        extra = common.snes2off(0xCB3869)
        orig = self.build.message_targets
        self.build.message_targets = lambda s: {**orig(s), "jump": orig(s)["jump"] | {extra}}
        try:
            with self.assertRaises(SystemExit):
                self.build.pointer_target_gate(self.src, bytes(self._kr()), True)
        finally:
            self.build.message_targets = orig


if __name__ == "__main__":
    unittest.main()
