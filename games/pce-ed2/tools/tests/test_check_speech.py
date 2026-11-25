"""말투 경보 — 양성·음성 대조."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_speech as cs


class Alarms(unittest.TestCase):
    def test_geudae(self):
        self.assertTrue(cs.geudae("그대 덕분에 살았네."))
        self.assertTrue(cs.geudae("그대와 둘이서."))
        self.assertFalse(cs.geudae("있는 그대로 말하게."))

    def test_shrunk(self):
        jp = "".join(chr(0x3042 + i * 2) for i in range(24))  # 가짜 문장 24자
        self.assertTrue(cs.shrunk(jp, "응."))
        self.assertFalse(cs.shrunk(jp, "가나다라마바사아자차카타파"))
        self.assertFalse(cs.shrunk(chr(0x3042) * 3, ""))  # 짧은 원문은 안 본다

    def test_plain_si(self):
        self.assertTrue(cs.plain_si("아저씨는 빠지시지."))
        self.assertTrue(cs.plain_si("돈이 모자라시네."))
        self.assertFalse(cs.plain_si("돈이 모자라십니다."))
        self.assertFalse(cs.plain_si("어서 오세요."))

    def test_lost(self):
        dot = "\u3002"
        q = "\uff1f"
        self.assertEqual(cs.lost("\u3042" + q, "응."), ["?"])
        self.assertEqual(cs.lost("\u3042" + q, "응?"), [])
        self.assertEqual(cs.lost("\u3042" + dot + "\u3042" + dot, "응, 응."), ["."])
        self.assertEqual(cs.lost("\u3042" + dot + "\u3042" + dot, "응. 응."), [])
        self.assertEqual(cs.lost("\u30fb\u30fb\u30fb\u30fb\u30fb\u30fb", "응."), ["…"])


if __name__ == "__main__":
    unittest.main()
