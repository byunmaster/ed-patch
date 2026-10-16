"""build.DEBUG_VIEW_* — 디버그 롬 「대사 보기」 스텁의 구조 검사(원본 없이 도는 합성 검사).

스텁은 `jsr $A64` 를 대신 부르고(덮어쓴 원래 명령), 우편함이 차 있으면 엔진 메시지 함수를 부른 뒤 rts 한다.
분기 변위가 어긋나면 디버그 롬이 필드에서 조용히 굳으니, 분기 도착점이 정확히 우리가 의도한 명령인지 바이트로 센다.
"""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build as b


class DebugViewStub(unittest.TestCase):
    def test_patch_is_one_jsr_same_length_as_original(self):
        self.assertEqual(len(b.DEBUG_VIEW_PATCH), 6)
        self.assertEqual(b.DEBUG_VIEW_PATCH[:2], bytes.fromhex("4eb9"))
        self.assertEqual(int.from_bytes(b.DEBUG_VIEW_PATCH[2:], "big"), b.DEBUG_VIEW_AT)

    def test_stub_starts_with_original_pad_read_and_ends_with_rts(self):
        st = b.DEBUG_VIEW_STUB
        self.assertEqual(st[:6], bytes.fromhex("4eb900000a64"))
        self.assertEqual(st[-2:], bytes.fromhex("4e75"))

    def test_branches_land_on_the_final_rts(self):
        st = b.DEBUG_VIEW_STUB
        end = len(st) - 2  # rts 의 위치
        # cmpi.b #$62,$FF01B2 (8B) 다음의 bne.s
        i = 6 + 8
        self.assertEqual(st[i], 0x66)
        self.assertEqual(i + 2 + st[i + 1], end)
        # tst.l $FFE800 (6B) 다음의 beq.s
        j = i + 2 + 6
        self.assertEqual(st[j], 0x67)
        self.assertEqual(j + 2 + st[j + 1], end)

    def test_mailbox_addresses(self):
        st = b.DEBUG_VIEW_STUB
        self.assertIn(struct.pack(">I", b.DEBUG_VIEW_BOX), st)
        self.assertIn(struct.pack(">I", b.DEBUG_VIEW_BOX + 4), st)
        self.assertIn(struct.pack(">I", b.DEBUG_VIEW_BOX + 6), st)  # 끝 표식

    def test_stub_sits_below_the_skip_stub(self):
        self.assertLessEqual(b.DEBUG_VIEW_AT + len(b.DEBUG_VIEW_STUB), b.DEBUG_SKIP_STUB_AT)


if __name__ == "__main__":
    unittest.main()
