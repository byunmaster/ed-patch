"""디버그 아이템 이름 줄 왼쪽 정렬(`debug_item`) — 손으로 짠 기계어를 (1) 디스어셈블로 검산하고 (2) 시뮬레이터로 돌려 버퍼 바이트를 대조한다."""

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import band_fallback
import cpu65
import debug_item as DI
import huc6280_dis as D


def listing() -> list[str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D.dis(DI.code(), DI.ORG, 0, len(DI.code()))
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


def run(name: bytes) -> tuple[bytes, list[tuple[int, int, int]]]:
    """이름 14B(앞 `20` 채움) + `06` 을 버퍼에 놓고 꼬리를 돌린다. (버퍼 15B, 그리기 호출들[(원본, BAT 하위, BAT 상위)])."""
    mem = bytearray(0x10000)
    mem[DI.BUF : DI.BUF + 15] = name + b"\x06"
    code = DI.code()
    mem[DI.ORG : DI.ORG + len(code)] = code
    mem[DI.DRAW] = 0x60  # RTS — 그리기는 가짜
    cpu = cpu65.CPU(mem)
    calls: list[tuple[int, int, int]] = []
    orig_step = cpu.step

    def step():
        if cpu.pc == DI.DRAW:
            calls.append((mem[0x10] | mem[0x11] << 8, mem[0x12], mem[0x13]))
        return orig_step()

    cpu.step = step
    cpu.sp = 0xF0
    mem[0x1F1] = 0xFF  # 복귀 주소(스택 `$21`xx 쪽이 아니라 이 단순 모델의 `$01` 페이지)
    cpu.run(DI.ORG, ret=0xFFFF)
    return bytes(mem[DI.BUF : DI.BUF + 15]), calls


class DebugItemTest(unittest.TestCase):
    def test_decodes_and_branches(self):
        ls = listing()
        self.assertFalse([ln for ln in ls if ".db" in ln], "디코드되지 않는 바이트")
        starts = {int(ln[:4], 16) for ln in ls}
        for ln in ls:
            m = re.search(r"\b(?:BCC|BCS|BNE|BEQ|BRA)\s+\$([0-9A-F]{4})", ln)
            if m:
                self.assertIn(int(m.group(1), 16), starts, ln)
        self.assertEqual(sum(1 for ln in ls if "JSR $5BB1" in ln), 1)

    def test_pocket_and_site(self):
        code = DI.code()
        self.assertGreaterEqual(
            DI.ORG, band_fallback.LOAD_ORG + len(band_fallback.code()[0])
        )  # 띠 폴백 뒤
        self.assertLessEqual(DI.ORG + len(code), 0x8000)  # 뱅크 0x70 안
        self.assertEqual(len(DI.SITE_OLD), 39)
        self.assertEqual(len(DI.site_new()), len(DI.SITE_OLD))
        self.assertEqual(DI.site_new()[:3], bytes([0x4C, DI.ORG & 0xFF, DI.ORG >> 8]))
        self.assertTrue(
            DI.SITE_OLD.endswith(bytes([0x20, 0xB1, 0x5B, 0x60]))
        )  # 원래도 `JSR $5BB1 / RTS` 로 끝났다

    def test_left_align_and_clear(self):
        pad = b"\x81\x40"
        for n_chars in range(
            8
        ):  # 0~7 글자(전부 2바이트 코드 — 이름 글자 첫 바이트는 `20` 이 아니다)
            name = b"".join(bytes([0xF1, 0x80 + i]) for i in range(n_chars))
            field = b"\x20" * (14 - len(name)) + name
            out, calls = run(field)
            self.assertEqual(
                out, name + pad * (7 - n_chars) + b"\x06", n_chars
            )  # 왼쪽 정렬 + 꼬리 전각 공백 + 종결자 그대로
            self.assertEqual(
                calls, [(DI.BUF, DI.BAT_LO, DI.BAT_HI)]
            )  # 그리기는 한 번, 원판과 같은 BAT 주소


if __name__ == "__main__":
    unittest.main()
