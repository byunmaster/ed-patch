"""FC 중계 조각·FD 중계가 엔진의 호출 틀(복귀 주소 스택)을 지키는가 — `$02:E53F`/`E609`/`E6D2`/`E7A0`/`E7C0` 해독을 모형으로.

엔진: FC = 틀을 쌓고(`E7A0`) 복귀 = 다음 바이트 · F9 = 틀을 **안 쌓고** 복귀 칸(`$173C`)만 덮어쓴다 · FE = 복귀하고 틀을 내린다(`E7C0`).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(mem: bytearray, pc: int, frames: list, limit: int = 100):
    """pc 부터 FC/F9/FA/FE 와 글자(0x01~0x7F, 방문 기록)를 돌려 (방문한 글자들, 남은 틀)을 낸다."""
    seen = []
    for _ in range(limit):
        op = mem[pc]
        if op == 0xFC:
            rel = int.from_bytes(mem[pc + 1 : pc + 3], "little")
            frames.insert(0, pc + 3)  # E7A0 로 밀고 $173C = 다음 바이트
            pc += rel
        elif op == 0xF9:
            if not frames:
                frames.append(None)
            frames[0] = pc + 4  # 틀을 안 쌓고 덮어쓴다
            pc = int.from_bytes(mem[pc + 1 : pc + 4], "little")
        elif op == 0xFA:
            pc += int.from_bytes(mem[pc + 1 : pc + 3], "little")
        elif op == 0xFE:
            pc = frames.pop(0)
        elif op == 0xE0:
            return seen, frames
        else:
            seen.append(op)
            pc += 1
    raise AssertionError("끝나지 않는다")


class FcStub(unittest.TestCase):
    def test_중계는_호출자_복귀를_지킨다(self):
        # 0x00: 호출자 `FC 중계` 'C' END · 0x20: 중계 `FC +3 · F9 목표 · FE` · 0x40: 목표 'T' FE
        mem = bytearray(0x60)
        mem[0:3] = bytes([0xFC, 0x20, 0x00])
        mem[3] = ord("C")
        mem[4] = 0xE0
        mem[0x20:0x28] = bytes([0xFC, 3, 0, 0xF9, 0x40, 0, 0, 0xFE])
        mem[0x40:0x42] = bytes([ord("T"), 0xFE])
        seen, frames = run(mem, 0, [0x50])  # 바깥 틀 하나를 미리 둔다
        self.assertEqual(bytes(seen), b"TC")
        self.assertEqual(frames, [0x50])  # 바깥 틀이 그대로다

    def test_F9_단독은_복귀를_덮어쓴다(self):
        mem = bytearray(0x60)
        mem[0:4] = bytes([0xF9, 0x40, 0, 0])  # 호출자: 그냥 F9 (복귀 = 다음 칸)
        mem[0x40:0x42] = bytes([ord("T"), 0xFE])
        mem[4] = ord("C")
        mem[5] = 0xE0
        # 바깥 틀(0x50)이 있으면 F9 가 그걸 덮어쓴다 — 그래서 단순 FC→F9 변환은 쓰지 않는다
        _seen, frames = run(mem, 0, [0x50])
        self.assertNotEqual(frames, [0x50])


if __name__ == "__main__":
    unittest.main()
