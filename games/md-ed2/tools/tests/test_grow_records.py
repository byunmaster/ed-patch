"""`battle.grow_records` — 레코드 구역 끝에 4B 를 끼울 때 구역 2~3 의 오프셋 표 전부가 같이 밀려야 한다(블록 11 이 전투 시작 때 죽은 결함, 10-24)."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle


def fake_block() -> bytes:
    """헤더 6워드(구역 시작) + 레코드 구역 + 표(구역 2~3: 스트림 시작 `T`·자료 `D1~D3` 를 가리키는 절대 오프셋) + 뒤 구역."""
    t1, t2, t3, t4 = 0x20, 0x30, 0x40, 0x60
    end = 0x90
    b = bytearray(end)
    b[:12] = struct.pack(">6H", 0x0C, t1, t2, t3, t4, end)
    # 구역 2·3 표: 스트림 시작(0x70) · 스트림 밖 자료(0x84·0x86 — 스트림 시작이 아니다) · 작은 값(밀면 안 된다)
    for i, v in enumerate((0x70, 0x84, 0x86, 0x0A03, t3)):
        b[t1 + 2 * i : t1 + 2 * i + 2] = struct.pack(">H", v)
    return bytes(b)


class GrowRecords(unittest.TestCase):
    def test_table_words_inside_block_shift(self):
        b = fake_block()
        # refs() 는 실제 스트림 문법을 읽으므로 시험은 스트림 시작 후보를 직접 준다
        orig_refs = battle.refs
        battle.refs = lambda blk: {0x70: None}
        try:
            n = battle.grow_records(b, 4)
        finally:
            battle.refs = orig_refs
        w = lambda blk, at: struct.unpack(">H", blk[at : at + 2])[0]
        t1 = 0x20
        self.assertEqual(len(n), len(b) + 4)
        self.assertEqual([w(n, t1 + 4 + 2 * i) for i in range(5)], [0x74, 0x88, 0x8A, 0x0A03, 0x44])
        self.assertEqual(w(n, 2), t1 + 4)  # 헤더 구역 경계는 밀린다


if __name__ == "__main__":
    unittest.main()
