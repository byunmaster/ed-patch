"""글리프 뱅크 경계 — 훅의 24B 복사가 뱅크를 넘어도 온전한가. 원본 없이 돈다(합성 뱅크).

🔴 **이 검사가 없어서 「십」이 조용히 깨져 있었다**(2026-09-16, 마스터 캡처에서 발각).
글리프 24B · 뱅크 8,192B 라 **8192 ÷ 24 = 341.33** 로 안 떨어진다 ⇒ 순번 341 은 뱅크 안에
**8B 뿐**이고 나머지 16B 가 다음 뱅크다. 훅은 MPR3 창 하나만 걸고 24B 를 **연속으로** 읽어
창 밖(MPR4)을 긁었고, 화면에는 **윗 4행(8B)만 맞고 아래 8행(16B)이 쓰레기**로 나왔다.

⚠ 지금은 걸치는 자리가 341 하나지만 **글리프 수나 크기가 바뀌면 자리가 옮겨 간다** — 그때
이 검사가 없으면 **다른 글자가 조용히 깨진다.** 그래서 「341 을 확인」하지 않고 **상한까지
전부** 돌린다. 글자→코드 순서는 세이브에 남아 못 바꾸므로(`glyph_order.json`) 「걸치는
순번을 건너뛴다」는 해법이 아니고, **읽는 쪽이 경계를 넘을 줄 알아야** 한다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook

BANK = 0x2000
WIN_LO = hook.GLYPH_WINDOW_HI << 8  # $6000
WIN_HI = WIN_LO + BANK  # $8000


def fetch(banks: bytes, idx: int) -> bytes:
    """훅의 복사 루프를 그대로 흉내 낸다($EC/$ED 포인터 + MPR3 창 + 경계에서 뱅크 교체)."""
    off = idx * font.GLYPH_BYTES
    ec = off & 0xFF
    ed = ((off >> 8) & 0x1F) | hook.GLYPH_WINDOW_HI
    bank = off >> 13
    out = bytearray()
    y = 0
    while True:
        addr = ((ed << 8) | ec) + y
        if not WIN_LO <= addr < WIN_HI:
            raise AssertionError(f"순번 {idx}: 창 밖을 읽는다 ${addr:04X} (Y={y})")
        out.append(banks[bank * BANK + (addr - WIN_LO)])
        y += 1
        if y == font.GLYPH_BYTES:
            return bytes(out)
        if ((y + ec) & 0xFF) == 0 and ed == (hook.GLYPH_WINDOW_HI | 0x1F):
            bank += 1  # 창 끝 → 다음 글리프 뱅크
            ed = hook.GLYPH_WINDOW_HI - 1


class GlyphBankBoundary(unittest.TestCase):
    def setUp(self):
        # 합성 뱅크 — 바이트마다 값이 달라 한 바이트만 어긋나도 걸린다
        self.banks = bytes((i * 7 + (i >> 8) * 13) & 0xFF for i in range(font.GLYPH_NBANKS * BANK))

    def test_every_glyph_reads_whole(self):
        """상한(font.MAX_GLYPHS — 2뱅크 682자)까지 **모든** 순번이 자기 24B 를 그대로 받아야 한다."""
        for idx in range(font.MAX_GLYPHS):
            off = idx * font.GLYPH_BYTES
            want = self.banks[off : off + font.GLYPH_BYTES]
            self.assertEqual(fetch(self.banks, idx), want, f"순번 {idx} 가 어긋난다")

    def test_boundary_case_actually_exists(self):
        """⚠ 경계를 걸치는 순번이 **정말 있는지** 확인한다 — 없으면 위 검사가 헛돈다."""
        straddling = [
            i
            for i in range(font.MAX_GLYPHS)
            if (i * font.GLYPH_BYTES) % BANK > BANK - font.GLYPH_BYTES
        ]
        self.assertTrue(straddling, "걸치는 순번이 없다 — 이 검사가 경계 경로를 안 밟는다")
        # 2026-09-16: 341(=「십」)·682(3뱅크). 2026-09-25 2뱅크로 줄여 341 하나. 값이 바뀌면 글리프
        # 크기/뱅크 수가 바뀐 것이다.
        self.assertEqual(straddling, [341], "걸치는 자리가 옮겨 갔다 — 훅을 다시 보라")

    def test_hook_routine_fits(self):
        """경계 처리를 넣고도 루틴이 제 칸에 들어가야 한다(넘치면 뒤 표를 덮어쓴다)."""
        self.assertLessEqual(len(hook.hook_routine()), hook.JOSA_OFF_ADDR - hook.HOOK_ADDR)


if __name__ == "__main__":
    unittest.main()
