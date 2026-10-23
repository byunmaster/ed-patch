"""공용 중계(`systext.RELAY_CODE`)의 논리 — 시뮬레이터로 돈다(원본 없이).
호출부 `JSR 중계 · 뱅크 · 주소(lo hi)` 가 ① 그 뱅크를 MPR4 에 걸어 문자열을 `$7E/$7F` 버퍼로 복사하고 ② MPR4 를 되돌리고 ③ 인라인 3바이트를 건너뛰어 돌아가야 한다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sim6280
import systext

# 원본 `$5060~$5074` 복사 루프(`$5066` 진입) — 중계가 부르는 루틴(실측 바이트)
COPY = bytes.fromhex("e67ed002e67fb27ce67cd002e67d927ec900d0ec60")


class Relay(unittest.TestCase):
    def test_인라인_3바이트를_건너뛰고_문자열을_복사한다(self):
        b68 = bytearray(8192)
        b68[0x100 : 0x100 + len(systext.RELAY_CODE)] = systext.RELAY_CODE
        b68[0x1060 : 0x1060 + len(COPY)] = COPY  # `$5060`
        far = bytearray(8192)
        far[0x10:0x16] = bytes([0x91, 0x92, 0x93, 0x94, 0x95, 0x00])  # 문자열(0 끝) — 창 `$8010`
        near = bytearray(8192)
        near[0:3] = bytes([0x20, 0x00, 0x41])  # JSR $4100(중계)
        near[3:6] = bytes([0x6B, 0x10, 0x80])  # 인라인: 뱅크 0x6B · 주소 `$8010`
        near[6:9] = bytes([0xA9, 0x77, 0x8D])  # LDA #$77 ; STA $2200 ; RTS
        near[9:12] = bytes([0x00, 0x22, 0x60])
        ram = bytearray(8192)
        ram[0x7E], ram[0x7F] = 0xE5, 0x30  # 버퍼 `$30E5` — 중계는 `$5066`(루프 가운데)으로 들어가니 첫 바이트를 이 자리에 쓴다
        banks = {0x68: b68, 0x6A: near, 0x6B: far, 0x70: bytearray(b"\x55" * 8192)}
        sim = sim6280.Sim(banks, [0xFF, 0xF8, 0x68, 0x6A, 0x70, 0x00, 0x00, 0x00], ram)
        sim.run(0x6000)
        self.assertEqual(sim.mpr[4], 0x70)  # MPR4 복원
        self.assertEqual(sim.ram[0x200], 0x77)  # 인라인 3바이트를 건너뛰어 LDA #$77 이 실행됐다
        buf = bytes(sim.rd(0x30E5 + i) for i in range(6))
        self.assertEqual(buf, bytes([0x91, 0x92, 0x93, 0x94, 0x95, 0x00]))


if __name__ == "__main__":
    unittest.main()
