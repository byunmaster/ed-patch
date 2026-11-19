"""보스 전투 음성 자동 넘김(11-19) — 전투 블록이 대사 엔진의 전역 시각표(`sched`)를 부르는 꼴. 원본 없이 돈다.
상수 셋이 상주부·엔진과 같은 값이어야 하고(다르면 조용히 엉뚱한 자리를 부른다), 스텁·표 바이트가 정해진 꼴이어야 한다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle
import narration_gates as G


class BattleVoiceSched(unittest.TestCase):
    def test_constants_match_resident(self):
        labels = G._resident_asm().labels
        self.assertEqual(battle.SCHED_ENTRY, labels["sched"])
        self.assertEqual(battle.AUTO_FLAG_ADDR, G.AUTO_FLAG)
        self.assertEqual(battle.WAIT_FRAMES, G.WAIT_FRAMES)

    def test_tail_layout(self):
        orig = battle.voice_timing
        battle.voice_timing = lambda rel: (138, [522, 840])
        try:
            tail, s1, s2 = battle.voice_tail(170, 0xCA28)
        finally:
            battle.voice_timing = orig
        self.assertEqual(s1, 0xCA28)
        self.assertEqual(s2, 0xCA28 + 27)  # 스텁1 = 20B + 열림 대기 7B
        self.assertEqual(tail[:2], bytes([0x08, 0x78]))  # PHP · SEI
        self.assertEqual(tail[13:16], bytes([0x20, *battle.SCHED_ENTRY.to_bytes(2, "little")]))  # JSR sched
        self.assertEqual(tail[27:33], bytes([0x9C, 0xFD, 0x5F, 0x4C, 0x5E, 0x5F]))  # STZ 자막 모드 · JMP $5F5E
        tbl = tail[33:]
        self.assertEqual(tbl, bytes([2, 0x0A, 0x02, 0x48, 0x03]))  # 쪽 2 · 522 · 840 프레임
        self.assertEqual(tail[10] | tail[12] << 8, s2 + 6)  # 표 주소

    def test_no_open_wait(self):
        orig = battle.voice_timing
        battle.voice_timing = lambda rel: (0, [300])
        try:
            tail, s1, s2 = battle.voice_tail(186, 0xC800)
        finally:
            battle.voice_timing = orig
        self.assertEqual(tail[20], 0x60)  # 열림 대기 없으면 RTS
        self.assertEqual(s2, 0xC800 + 21)


if __name__ == "__main__":
    unittest.main()
