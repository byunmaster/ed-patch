import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_center as K


class Center(unittest.TestCase):
    def test_centered_title_row_has_equal_margins(self):
        # 폭 320 칸에 글자 덩이 200px + 끝 부호 8px — 부호를 뺀 192px 가 가운데
        lm, rm = K.title_margins(64, 200, 8, 320)
        self.assertLessEqual(abs(lm - rm), 1)

    def test_clamped_row_is_found(self):
        # 줄이 칸을 다 채워 x 가 밀리면(끝 부호까지 합쳐 320px) 부호를 뺀 가운데에서 어긋난다
        lm, rm = K.title_margins(0, 320, 8, 320)
        self.assertGreater(abs(lm - rm), 1)

    def test_card_pad_one_cell_off_is_found(self):
        jp = "\t     第１章　王子の旅立ち\n\n            完%c"
        ok = "\t     제１장　왕자의 여행\n\n            끝%c"
        off = "\t    제１장　왕자의 여행\n\n            끝%c"
        self.assertFalse(K.card_verdict(jp, ok)[0])
        self.assertTrue(K.card_verdict(jp, off)[0])

    def test_card_pad_beyond_byte_room_is_not_blamed(self):
        jp = "\t    第５章　妖しき光の塔\n\n完%c"  # 바이트 칸이 빠듯해 공백을 더 못 넣는다
        kr = "\t   제５장　요사한 빛의 탑\n\n끝%c"
        self.assertFalse(K.card_verdict(jp, kr)[0])


if __name__ == "__main__":
    unittest.main()
