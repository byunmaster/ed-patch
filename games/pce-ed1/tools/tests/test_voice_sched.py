"""음성 장면 시각표 — 게이트 스텁·force_off·표 바이트를 가짜 블록으로 검산한다(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import narration_gates as G
import voice_sched as V

GATE = b"\xad\x4c\xc0"
VOICE = b"\x20\x15\x58\x1e\x0e\x1c\x01"


class T(unittest.TestCase):
    def setUp(self):
        self._load, self._val = V.load, V.validate
        V.load = lambda: {"9": [{"voice_gate": 1, "force_off": [0], "msgs": [{"key": "k", "ends": [4.2, 11.4]}]}]}
        V.validate = lambda sid, orig: []
        self.blk = b"\xea\xea" + GATE + b"\xf0\x05" + b"\x60" * 5 + GATE + b"\xf0\x0a" + VOICE + b"\x60\x60\x60" + b"\xea"
        self.out, self.n = V.patch_block(9, b"", self.blk)

    def tearDown(self):
        V.load, V.validate = self._load, self._val

    def test_force_off_gate_loads_zero(self):
        self.assertEqual(self.out[2:5], b"\xa9\x00\xea")  # LDA #0 · NOP — Z 가 서서 BEQ 가 OFF 경로로
        self.assertEqual(self.out[5:7], b"\xf0\x05")  # BEQ 그대로

    def test_voice_gate_calls_stub_and_keeps_beq(self):
        g = 2 + 3 + 2 + 5
        self.assertEqual(self.out[g], 0x20)
        stub = (self.out[g + 1] | self.out[g + 2] << 8) - G.BASE
        self.assertEqual(self.out[g + 3 : g + 5], b"\xf0\x0a")
        s = self.out[stub : stub + 22]
        self.assertEqual(s[:5], b"\xad\x4c\xc0\xf0\x0e")  # LDA $C04C · BEQ → LDA #0
        self.assertEqual(s[5:12], VOICE)  # 원래 음성 호출(인라인 4B 포함)
        self.assertEqual((s[12], s[14]), (0xA9, 0xA2))  # LDA #표 하위 · LDX #표 상위
        self.assertEqual(s[16:19], b"\x20" + G.SCHED.to_bytes(2, "little"))
        self.assertEqual(s[19:22], b"\xa9\x00\x60")  # LDA #0 · RTS
        t_at = (s[13] | s[15] << 8) - G.BASE
        self.assertEqual(self.out[t_at], 2)  # 쪽 둘
        self.assertEqual(self.out[t_at + 1 : t_at + 3], round(4.2 * G.FPS).to_bytes(2, "little"))

    def test_gate_count(self):
        self.assertEqual(self.n, 2)


class VoiceFrom(unittest.TestCase):
    """`voice_from` — 음성 호출이 다른 게이트의 ON 경로에 있을 때(씬 18): 앞 게이트에 스텁을 달고 ON 경로 앞부분(플래그)을 옮긴다."""

    def setUp(self):
        self._load, self._val = V.load, V.validate
        V.load = lambda: {
            "9": [{"voice_gate": 0, "voice_from": 1, "copy_prefix": True, "force_off": [1], "msgs": [{"key": "k", "ends": [4.0]}]}]
        }
        V.validate = lambda sid, orig: []
        # 게이트0: ON = `LDA $C103 · ORA #4 · STA $C103 · BRA +5`(플래그만) / 게이트1: ON = 음성 호출 + `RTS`류
        on0 = b"\xad\x03\xc1\x09\x04\x8d\x03\xc1" + b"\x80\x05"
        self.blk = b"\xea" + GATE + bytes([0xF0, len(on0)]) + on0 + b"\x60" * 5 + GATE + b"\xf0\x0a" + VOICE + b"\x60\x60\x60" + b"\xea"
        self.out, self.n = V.patch_block(9, b"", self.blk)

    def tearDown(self):
        V.load, V.validate = self._load, self._val

    def test_stub_on_first_gate_carries_prefix_and_voice(self):
        self.assertEqual(self.out[1], 0x20)  # 앞 게이트가 스텁 호출로
        stub = (self.out[2] | self.out[3] << 8) - G.BASE
        s = self.out[stub : stub + 24]
        self.assertEqual(s[:3], b"\xad\x4c\xc0")
        self.assertEqual(s[5:13], b"\xad\x03\xc1\x09\x04\x8d\x03\xc1")  # 플래그 옮김(끝의 BRA 는 뺐다)
        self.assertEqual(s[13:20], VOICE)  # 음성 호출도 앞 게이트 스텁으로

    def test_voice_gate_is_forced_off(self):
        g1 = 1 + 3 + 2 + 10 + 5  # 게이트 1 자리
        self.assertEqual(self.out[g1 : g1 + 3], b"\xa9\x00\xea")

    def test_voice_from_must_be_force_off(self):
        V.load = lambda: {"9": [{"voice_gate": 0, "voice_from": 1, "copy_prefix": True, "force_off": [], "msgs": [{"key": "k", "ends": [4.0]}]}]}
        with self.assertRaises(V.SchedError):
            V.patch_block(9, b"", self.blk)


if __name__ == "__main__":
    unittest.main()
