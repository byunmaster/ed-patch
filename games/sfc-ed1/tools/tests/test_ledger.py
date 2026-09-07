"""단계 원장 — **원본 없이** 돈다.

`build.Ledger` 는 「어느 단계가 어느 바이트를 썼나」를 적어 두고 **다른 단계가 그 자리를
덮으면 운다**. 게이트 셋(되읽기·라운드트립·무변경 구간)이 다 못 보는 자리다.
⚠ 여기서 꼭 보는 것: **덩이 경계를 걸친 쓰기**. `_written` 이 4KB 덩이로 훑으므로 경계에서
틀리면 **가드가 조용히 죽는다**(다른 트랙이 같은 자리에서 한 번 틀렸다 — 관리자 중계).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001
import build

CHUNK = 4096


class Written(unittest.TestCase):
    def test_덩이_경계를_걸친_쓰기(self):
        a = bytearray(3 * CHUNK)
        b = bytearray(a)
        b[CHUNK - 2 : CHUNK + 2] = b"\x01\x02\x03\x04"  # 경계를 넘어간다
        self.assertEqual(
            build._written(bytes(a), bytes(b)), {CHUNK - 2, CHUNK - 1, CHUNK, CHUNK + 1}
        )

    def test_덩이_전체가_바뀐다(self):
        a = bytearray(2 * CHUNK)
        b = bytearray(a)
        b[CHUNK : 2 * CHUNK] = b"\xff" * CHUNK
        self.assertEqual(len(build._written(bytes(a), bytes(b))), CHUNK)

    def test_안_바뀌면_빈_집합(self):
        a = bytes(2 * CHUNK)
        self.assertEqual(build._written(a, a), set())


class LedgerGuard(unittest.TestCase):
    def test_겹치면_운다(self):
        out = bytearray(2 * CHUNK)
        led = build.Ledger(out)
        out[100] = 1
        led.snap(out, "앞")
        out[100] = 2  # 같은 자리를 다른 단계가 덮는다
        with self.assertRaises(SystemExit) as cm:
            led.snap(out, "뒤")
        self.assertIn("앞", str(cm.exception))

    def test_경계를_걸쳐_겹쳐도_운다(self):
        out = bytearray(2 * CHUNK)
        led = build.Ledger(out)
        out[CHUNK - 1 : CHUNK + 1] = b"\x01\x01"
        led.snap(out, "앞")
        out[CHUNK] = 2  # 뒤쪽 덩이의 첫 바이트만 덮는다
        with self.assertRaises(SystemExit):
            led.snap(out, "뒤")

    def test_안_겹치면_통과(self):
        out = bytearray(2 * CHUNK)
        led = build.Ledger(out)
        out[10] = 1
        led.snap(out, "앞")
        out[20] = 1
        led.snap(out, "뒤")
        self.assertEqual(led.report(), {"앞": 1, "뒤": 1})


if __name__ == "__main__":
    unittest.main()
