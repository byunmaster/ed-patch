"""오프닝 나레이션 자막 — 페이지 조판 · 사건 표 · 코드 조립 불변식(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import opening_sub as o


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = o.build_pages()

    def test_페이지는_두_줄_이하이고_슬롯_안에_든다(self):
        for p in self.pages:
            self.assertLessEqual(len(p["lines"]), 5)
            self.assertLessEqual(len(p["cells"]), o.BUF_CELLS)
            self.assertLessEqual(len(p["cells"]) // 2, o.SLOTS)

    def test_셀_x_는_한_바이트_안이다(self):
        for p in self.pages:
            for i, (x, yoff, cb) in enumerate(p["cells"]):
                if i % 2 == 0:  # 32 폭 스프라이트의 시작 셀만 SAT x 가 된다
                    self.assertTrue(0 <= x + 32 <= 255, (p["lines"], x))
                self.assertEqual(yoff % (o.LINE_ACC if p["group"] else o.LINE_3 if len(p["lines"]) > 2 else o.LINE_H), 0)
                self.assertEqual(len(cb), 64)

    def test_줄은_폭_상한_안이다(self):
        for p in self.pages:
            for line in p["lines"]:
                self.assertLessEqual(o.text_w(line) + 2, o.LINE_CAP, line)

    def test_시각은_순서대로_겹치지_않는다(self):
        for a, b in zip(self.pages, self.pages[1:]):
            self.assertLessEqual(a["t1"], b["t0"] + 1e-6)


class StarBG(unittest.TestCase):
    """별하늘은 BG 타일 자막 — 한 화면에 이어 붙고, 타일·행이 자리 안이다."""

    @classmethod
    def setUpClass(cls):
        cls.bg = [p for p in o.build_pages() if "bg" in p]

    def test_별하늘_쪽은_전부_한_그룹이다(self):
        self.assertGreaterEqual(len(self.bg), 2)
        self.assertEqual(len({p["group"] for p in self.bg}), 1)

    def test_타일_수와_BAT_행이_자리_안이다(self):
        total = sum(p["bg"]["ntiles"] for p in self.bg)
        self.assertLessEqual(total, o.BG_TILES_MAX)
        rows = [r for p in self.bg for r in p["bg"]["rows"]]
        self.assertEqual(len(rows), len(set(rows)))  # 같은 BAT 행을 두 번 안 쓴다(이어 붙이기)
        for r in rows:
            self.assertEqual(r % 64, 0)
            self.assertTrue(o.BG_ROW0 <= r // 64 < o.BG_ROW0 + o.BG_CLEAR_ROWS)

    def test_쪽은_gap_말고는_빈_행_없이_이어_붙는다(self):
        gaps = [0 for _ in self.bg]
        for i, (a, b) in enumerate(zip(self.bg, self.bg[1:])):
            gaps[i + 1] = min(b["bg"]["rows"]) // 64 - max(a["bg"]["rows"]) // 64 - 1
        self.assertEqual([g for g in gaps if g], [2])  # 빈 줄은 한 곳(16px)뿐

    def test_마지막_단계_전체가_화면_세로_가운데다(self):
        """두 덩이가 다 보인 마지막 단계의 세로 중심이 화면 가운데(H/2)에서 8px(한 BAT 행) 안이다 — 마스터 10-16 「우주 장면 아래쪽으로 치우친 것 같다」."""
        rows = [r // 64 for p in self.bg for r in p["bg"]["rows"]]
        top, bot = min(rows) * 8 + o.BG_SHIFT_Y, (max(rows) + 1) * 8
        self.assertLessEqual(abs((top + bot) / 2 - o.H / 2), 8)

    def test_BAT_항목은_빈칸이거나_새_타일이다(self):
        import struct

        for p in self.bg:
            nt = p["bg"]["ntiles"]
            body = p["blob"][nt * 32 :]
            for k in range(len(p["bg"]["rows"])):
                for e in struct.unpack("<32H", body[k * 64 : k * 64 + 64]):
                    self.assertTrue(e == o.BG_BLANK or (e >> 12 == o.BG_PAL and e & 0xFFF >= o.BG_TILE0), hex(e))

    def test_글_줄은_격자_안이다(self):
        for p in self.bg:
            for line in p["lines"]:
                self.assertLessEqual(len(o.line_tiles(line)), 32, line)  # 줄마다 화면 가운데(마스터 10-15)라 시작 열은 줄마다 다르다 — 줄 폭이 32 타일 안이면 된다


class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = o.build_pages()
        cls.ev = o.events(cls.pages)

    def test_사건은_시각순이고_끝이_하나다(self):
        ts = [e[0] for e in self.ev]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual([e for e in self.ev if e[1] == 0xFF], [self.ev[-1]])

    def test_올리기는_보이기보다_먼저이고_버퍼가_번갈아_간다(self):
        up = {e[2]: e for e in self.ev if e[1] == 1}
        show = {e[2]: e for e in self.ev if e[1] == 2}
        self.assertEqual(set(up), {i for i in show if "bg" not in self.pages[i]})
        for i in up:
            self.assertLess(up[i][0], show[i][0])
            self.assertEqual(up[i][3], o.buf_of(self.pages)[i])
            self.assertEqual(show[i][3], o.buf_of(self.pages)[i])
            if i:
                self.assertNotEqual(up[i][3], up[i - 1][3])
            if len(self.pages[i]["cells"]) > o.BUF1_CELLS:
                self.assertEqual(up[i][3], 0)

    def test_올리기가_서로_겹치지_않는다(self):
        ups = sorted(e[0] for e in self.ev if e[1] == 1)
        need = (o.SLOTS // o.CELLS_PER_TICK) + 2  # 한 페이지를 올리는 데 걸리는 틱
        for a, b in zip(ups, ups[1:]):
            self.assertGreaterEqual(b - a, need)


class Assemble(unittest.TestCase):
    def test_조립이_들어맞고_크기_상한_안이다(self):
        pages = o.build_pages()
        blob, where = o.pack_data(pages)
        module, L = o.build_module(pages, where, len(blob) // 2048)
        self.assertLessEqual(len(module), o.CODE_MAX)
        self.assertEqual(L["stub"], o.CODE_ADDR)
        # 스텁은 TII 둘 + JMP — 첫 바이트가 TII
        self.assertEqual(module[0], 0x73)

    def test_페이지_데이터는_뱅크_경계를_안_넘는다(self):
        pages = o.build_pages()
        _blob, where = o.pack_data(pages)
        for p, (_bank, win) in zip(pages, where):
            self.assertLessEqual(win - 0xA000 + len(p["blob"]), o.BANK)

    def test_램_init_은_자리_안이다(self):
        pages = o.build_pages()
        blob, where = o.pack_data(pages)
        _m, L = o.build_module(pages, where, len(blob) // 2048)
        self.assertLessEqual(L["rinit_len"], o.RAM_INIT_MAX)
        self.assertEqual(len(o.tramp_code(L["tick"])), o.TRAMP_LEN)


if __name__ == "__main__":
    unittest.main()
