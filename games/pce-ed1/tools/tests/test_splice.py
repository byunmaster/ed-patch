"""메시지 파싱·합성·splice — 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M

SJ = lambda s: s.encode("cp932")  # noqa: E731


class Parse(unittest.TestCase):
    def block(self):
        # 머리 표(포인터 둘) + 코드 흉내 + 메시지 셋
        a = b"\x4c\x10\xa0" + b"\x00" * 13
        m1 = (
            b"\x1f"
            + SJ("侍女")
            + b"\x04\x01"
            + SJ("おはよう。")
            + b"\x01"
            + SJ("王子さま。")
            + b"\x00"
        )
        m2 = SJ("お出かけ？") + b"\x05\x09\x00\x01" + SJ("そうか。") + b"\x00"
        m3 = SJ("警告！") + b"\x12\x34\xa0" + SJ("つづき。") + b"\x00"
        return a + m1 + m2 + m3

    def test_경계와_화자(self):
        msgs = M.parse(self.block())
        self.assertEqual([m.speaker for m in msgs], ["侍女", None, None, None, None])
        self.assertEqual(msgs[0].jp, "\nおはよう。\n王子さま。")
        self.assertTrue(msgs[0].terminated)
        self.assertFalse(msgs[1].terminated)  # 09 00 에서 갈린다
        self.assertEqual(msgs[2].common, 0)
        self.assertTrue(msgs[3].complex)  # 12 옵코드 앞에서 끊긴다
        self.assertEqual(msgs[3].jp, "警告！")

    def test_splice_제자리와_넘침(self):
        blk = self.block()
        msgs = M.parse(blk)
        short = b"\x1f" + SJ("女") + b"\x04\x01" + b"\xf0\x24" + b"\x00"  # F0 24 = 한글 코드
        out = M.splice(blk, [(msgs[0], short)])
        self.assertEqual(len(out), len(blk))
        self.assertEqual(out[msgs[0].start : msgs[0].start + len(short)], short)
        long = b"\x1f" + SJ("侍女") + b"\x04\x01" + b"\xf0\x24" * 60 + b"\x00"
        out2 = M.splice(blk, [(msgs[0], long)])
        self.assertGreater(len(out2), len(blk))
        cut = out2[msgs[0].start :].index(b"\x0f")
        tail = out2[msgs[0].start + cut + 1] | out2[msgs[0].start + cut + 2] << 8
        self.assertEqual(tail, M.BASE + len(blk))  # 블록 끝으로 잇는다
        self.assertEqual(out2[len(blk) :], long[cut:])
        # 되풀어 읽으면 같은 문안
        again = M.parse(out2)
        self.assertTrue(again[0].complex)  # 앞 조각은 0F 에서 끊긴다

    def test_종료없는_조각은_0F로_잇는다(self):
        blk = self.block()
        msgs = M.parse(blk)
        m = msgs[1]  # 'お出かけ？' — 09 앞에서 끊긴 조각
        new = b"\xf0\x25\xf0\x26" + SJ("？")  # 종료 없음
        out = M.splice(blk, [(m, new)])
        j = m.start + len(new)
        self.assertEqual(out[j], 0x0F)
        self.assertEqual(out[j + 1] | out[j + 2] << 8, M.BASE + m.end)

    def test_꼬리_페이지_옵코드_보존(self):
        import translate

        blk = self.block()
        m = M.parse(blk)[1]  # 'お出かけ？' + 05, 09 앞에서 끊긴 조각
        out = translate.compose(
            m, {"t": "외출?"}, {"외": b"\xf0\x24", "출": b"\xf0\x25", "?": b"\xf0\x26"}, {}
        )
        self.assertEqual(out[-1], 0x05)

    def test_pinned는_거부(self):
        blk = self.block()
        msgs = M.parse(blk)
        msgs[0].pinned = True
        with self.assertRaises(ValueError):
            M.splice(blk, [(msgs[0], b"\x00")])


if __name__ == "__main__":
    unittest.main()
