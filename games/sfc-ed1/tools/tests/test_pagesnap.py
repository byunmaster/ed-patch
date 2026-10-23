"""쪽 지우기 직전 스냅(빠름·멈춤에서 앞 쪽이 새 글자 타일에 덮이던 것) — 엔진 문맥 손인코딩 바이트의 모양(원본 롬 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hook


class PageSnap(unittest.TestCase):
    def test_사이트는_LDA_1777_세_바이트(self):
        self.assertEqual(hook.SNAP_SITE_ORIG, bytes([0xAD, 0x77, 0x17]))  # 뒤따르는 BNE 가 이 LDA 의 Z 를 본다

    def test_스텁은_훅_뒤_LDA_1777_RTS(self):
        # 스텁(8B) = JSL pagesnap(4) + LDA $1777(3) + RTS(1) — 사이트가 돌려주던 Z 플래그를 그대로 돌려준다
        self.assertEqual(hook.SNAP_STUB, 0x02FE80)
        self.assertGreaterEqual(hook.SNAP_STUB, 0x02FE80 + 0)  # 다른 트램펄린(FE52~FE7F)과 안 겹친다

    def test_개행_스텁은_FF_면_0(self):
        # 쪽 첫머리 개행(`$173B`=$FF)이 줄 15 로 읽혀 이름 첫 글자가 윗줄 끝에 떨어지던 것(10-18) — LDA $173B / CMP #$FF / BNE +2 / LDA #$00 / RTS
        self.assertEqual(hook.NL_SITE_ORIG, bytes([0xAD, 0x3B, 0x17]))
        self.assertEqual(len(hook.NL_STUB_BYTES), 10)
        self.assertEqual(hook.NL_STUB_BYTES[:3], hook.NL_SITE_ORIG)  # 원래 LDA 를 그대로 앞에 둔다
        self.assertEqual(hook.NL_STUB_BYTES[3:], bytes([0xC9, 0xFF, 0xD0, 0x02, 0xA9, 0x00, 0x60]))
        self.assertGreater(hook.NL_STUB, hook.SNAP_STUB + 7)  # 쪽 스냅 스텁(8B)과 안 겹친다

    def test_플러시는_걷었다(self):
        self.assertFalse(hasattr(hook, "FLUSH_SITE"))  # 첫 글자 플러시 안은 폐기(devlog 10-17)


if __name__ == "__main__":
    unittest.main()
