"""씬 블록별 동적 글리프 — 스텁 바이트를 **흉내 실행**해 효과를 못 박는다(손인코딩 기계어 검산)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import glyphdyn as G
import messages as M


def fake_block(head=0x4C, target=0xA010, size=64):
    b = bytearray(size)
    b[0] = head
    b[1:3] = target.to_bytes(2, "little")
    return bytes(b)


class DynGlyph(unittest.TestCase):
    def test_스텁은_정확히_복사하고_다_돌려놓는다(self):
        dyn = ["굉", "꼴", "랍"]
        blk = G.attach(fake_block(), dyn)
        self.assertEqual(len(blk), 64 + G.STUB_LEN + 3 * 18 + 6)
        win, has, rieul, end, depth = G.simulate(blk)
        self.assertEqual(end, 0xA010)  # 원래 점프 목적지로 이어진다
        self.assertEqual(depth, 0)  # 스택 균형
        off = font.glyph_at(font.DYN0) % 0x2000
        for k, ch in enumerate(dyn):
            self.assertEqual(bytes(win[off + 18 * k : off + 18 * k + 18]), font.pack(font.glyph(ch)))
        a = font.DYN0 >> 3
        # 굉(받침 ㅇ)·꼴(ㄹ)·랍(ㅂ) — 셋 다 받침 있음, ㄹ 은 꼴 하나
        self.assertEqual(has[a], 0b111)
        self.assertEqual(rieul[a], 0b010)

    def test_JSR_머리도_꼬리_점프로_돌아간다(self):
        blk = G.attach(fake_block(head=0x20, target=0x5D32), ["굉"])
        self.assertEqual(blk[0], 0x20)
        _, _, _, end, depth = G.simulate(blk)
        self.assertEqual((end, depth), (0x5D32, 0))

    def test_동적이_없으면_블록은_그대로(self):
        b = fake_block()
        self.assertEqual(G.attach(b, []), b)

    def test_머리가_점프가_아니면_죽는다(self):
        with self.assertRaises(G.DynError):
            G.attach(b"\xea" * 8, ["굉"])

    def test_동적_칸은_같은_리드_안에서_이어지고_코드_자리_앞이다(self):
        first, last = font.glyph_at(font.DYN0), font.glyph_at(font.MAX_GLYPHS - 1)
        self.assertEqual(last - first, (font.DYN_SLOTS - 1) * font.PACKED_BYTES)
        self.assertEqual(first // 0x2000, last // 0x2000)  # 한 뱅크
        self.assertEqual(font.code_of(font.DYN0)[0], font.code_of(font.MAX_GLYPHS - 1)[0])  # 한 리드

    def test_블록_표는_코드_순으로_동적_칸을_배정한다(self):
        table = {ch: font.code_of(i) for i, ch in enumerate(font._order_canon())}
        t, dyn = G.block_table(table, 89)
        self.assertEqual(dyn, sorted(dyn))
        for k, ch in enumerate(dyn):
            self.assertEqual(t[ch], font.code_of(font.DYN0 + k))

    def test_실제_정본_블록_모두_동적_칸에_든다(self):
        """🔴 한 블록이 동적 칸(24)을 넘으면 빌드가 죽는다 — 번역을 고칠 때 먼저 여기서 걸린다."""
        canon = set(font._order_canon())
        table = {ch: font.code_of(i) for i, ch in enumerate(font._order_canon())}
        for i in G.body_scene_ids():
            _, dyn = G.block_table(table, i)
            self.assertLessEqual(len(dyn), font.DYN_SLOTS, i)
            self.assertFalse(set(dyn) & canon)

    def test_늘_상주할_글자는_정본에_다_있다(self):
        import common

        # 상주 이름은 이 게임 원문 파생물로 고른다 — 원본이 없는 트리(main)에선 잴 수 없다(게임 트리에서 돈다)
        if not any((common.OUT_DIR / d).is_dir() for d in ("messages", "sys", "battle")):
            self.skipTest("원문 파생물이 없다(원본 없는 트리)")
        self.assertFalse(G.forced_chars() - set(font._order_canon()))


if __name__ == "__main__":
    unittest.main()
