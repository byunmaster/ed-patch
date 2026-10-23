"""분모에서 뺀 죽은 문안(`names_corpus.DEAD_STREAMS`)이 정말 참조 0 인지 — 원본 롬이 있을 때만 돈다."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import names_corpus

LEA_PEA = (0x41FA, 0x43FA, 0x45FA, 0x47FA, 0x49FA, 0x4BFA, 0x4DFA, 0x4FFA, 0x487A)


class DeadStreams(unittest.TestCase):
    def test_no_reference_anywhere(self):
        try:
            import common

            rom = common.rom()
        except (SystemExit, FileNotFoundError, ImportError):
            self.skipTest("원본 롬 없음")
        for t in names_corpus.DEAD_STREAMS:
            abs32 = struct.pack(">I", t)
            hits = [p for p in range(len(rom) - 4) if rom[p : p + 4] == abs32]
            for p in range(0, len(rom) - 4, 2):
                if struct.unpack(">H", rom[p : p + 2])[0] in LEA_PEA:
                    if p + 2 + struct.unpack(">h", rom[p + 2 : p + 4])[0] == t:
                        hits.append(p)
            for p in range(0, len(rom) - 2, 2):
                if p + struct.unpack(">h", rom[p : p + 2])[0] == t:
                    hits.append(p)
            self.assertEqual(hits, [], f"{t:#x} 에 참조가 생겼다 — DEAD_STREAMS 에서 빼고 분모에 되돌린다")


if __name__ == "__main__":
    unittest.main()
