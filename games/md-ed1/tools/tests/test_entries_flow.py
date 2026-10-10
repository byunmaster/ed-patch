"""표 항목(절대 오프셋 BE16)·흐름 이음 — 상점/NPC 대사 사슬이 재조립을 따라가는가. 원본 없이 도는 합성 모듈.

물린 사고(2026-10-11): 숨은 텍스트 800여 건이 `lea` 뿌리 밖이었다. 상점 구조체는 문안 바로 앞에
절대 오프셋 BE16 을 늘어놓고(뒤에 4E71), 스트림은 06·07 로 끝나도 **물리적으로 다음 스트림으로 이어진다**.
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene


def module() -> bytes:
    sj = lambda s: s.encode("cp932")  # noqa: E731
    code = bytes(16) + b"\x4e\x75"  # 코드 자리(문안 아님)
    t1 = sj("おはようございます") + b"\x01\x07"  # 07 로 끝 — 다음 스트림으로 이어진다
    t2 = sj("今日もいい天気ですね") + b"\x01\x07"
    t3 = sj("またどうぞいらしてください") + b"\x00"
    head = len(code) + 6 + 2  # 표 3칸 + 4E71
    a = head
    b = a + len(t1)
    c = b + len(t2)
    table = struct.pack(">HHH", a, b, c) + b"\x4e\x71"
    return code + table + t1 + t2 + t3 + b"\x00\x00"


class EntriesFlow(unittest.TestCase):
    def test_discovered(self):
        mod = scene.parse_module(module())
        self.assertEqual(len(mod.streams), 3)
        self.assertEqual(len(mod.entries), 3)

    def test_rewritten(self):
        orig = scene.parse_module(module())
        new_bytes = scene.reassemble(orig)
        scene.verify_reassembly(orig, new_bytes)
        new = scene.parse_module(new_bytes, orig)
        self.assertEqual(
            sorted(st.text() for st in new.streams.values()),
            sorted(st.text() for st in orig.streams.values()),
        )
        for p, v in new.entries.items():
            self.assertGreater(v, max(orig.streams))  # 표가 새 자리를 가리킨다
        # 흐름 이음: 첫 둘은 새 자리에서도 바로 이어 붙어 있다
        starts = sorted(new.streams)
        self.assertEqual(new.streams[starts[0]].end, starts[1])
        self.assertEqual(new.streams[starts[1]].end, starts[2])


if __name__ == "__main__":
    unittest.main()
