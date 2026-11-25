"""맵 모듈 머리(워드 표 + NPC 항목) 영역은 3단계 절대 오프셋 표 탐색에서 빠진다 — 060-3 사고(11-08).

머리 `0x14~0x18` 의 바이트 쌍이 홀수 위치(`06 10`·`07 00`)에서 우연히 문안 시작으로 읽혀 가짜 표가 서고, 번역 재배치가 NPC 항목의 조건 바이트(0x00→0x96)를 고쳤다.
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scene


def kana(n: int) -> bytes:
    return b"".join(bytes([0x82, 0x9F + i % 20]) for i in range(n))


def build() -> bytes:
    b = bytearray(0x100)
    hdr = [0x12, 0x16, 0x18, 0x40, 0x40, 0x46, 0x80, 0x80, 0xC0, 0x100]
    for i, w in enumerate(hdr):
        b[2 * i : 2 * i + 2] = struct.pack(">H", w)
    t1, t2 = kana(10) + b"\x00", kana(12) + b"\x00"
    b[0x80 : 0x80 + len(t1)] = t1
    b[0xA0 : 0xA0 + len(t2)] = t2
    # 홀수 위치 0x15·0x17 의 워드가 우연히 두 문안 시작을 가리킨다
    b[0x15:0x17] = struct.pack(">H", 0x80)
    b[0x17:0x19] = struct.pack(">H", 0xA0)
    return bytes(b)


class HeaderTable(unittest.TestCase):
    def test_no_table_inside_header(self):
        m = scene.parse_module(build())
        bad = [hex(t.word) for t in m.tables if t.word < 0x40]
        self.assertEqual(bad, [], "머리·NPC 항목 영역에서 표가 잡혔다")

    def test_text_outside_header_still_found(self):
        m = scene.parse_module(build())
        self.assertTrue(
            any(a in m.streams for a in (0x80, 0xA0)), "머리 밖 가나 글줄은 계속 찾아야 한다"
        )


if __name__ == "__main__":
    unittest.main()
