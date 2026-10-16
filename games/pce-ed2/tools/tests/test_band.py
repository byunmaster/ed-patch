"""검은 띠 패치 — 손인코딩 기계어의 분기 거리·크기·자리 검산(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import band


LEN = {}  # 옵코드 → 바이트 수(이 코드에 쓰인 것만)
for _op in (0x62, 0xDA, 0xFA, 0x60, 0x18, 0xEA):
    LEN[_op] = 1
for _op in (0xF0, 0xD0, 0x80, 0x90, 0x03, 0x29, 0x09, 0x05, 0xA9, 0xA2, 0xC9, 0xE0, 0xA5, 0x85, 0x69):
    LEN[_op] = 2
for _op in (0xAD, 0x8D, 0xAE, 0x8E, 0x9C, 0x4C, 0x20, 0xCD, 0xCE, 0x2D):
    LEN[_op] = 3


def _starts(code: bytes):
    out, i = [], 0
    while i < len(code):
        out.append(i)
        i += LEN[code[i]]
    return out


def _decode_branches(code: bytes):
    """분기(BEQ F0 · BNE D0 · BRA 80)의 (자리, 도착) — 선형 디코드(이 코드엔 데이터가 없다)."""
    out = []
    for i in _starts(code):
        if code[i] in (0xF0, 0xD0, 0x80, 0x90):
            d = code[i + 1] - 256 if code[i + 1] >= 128 else code[i + 1]
            out.append((i, i + 2 + d))
    return out


class Band(unittest.TestCase):
    def test_래스터_핸들러_분기는_명령_경계에_닿는다(self):
        hook, ras, spr = band.gen(0x9F00)
        starts = set(_starts(ras)) | {len(ras)}
        for at, to in _decode_branches(ras):
            self.assertIn(to, starts, (at, to))

    def test_훅_분기는_세피아_갈래_끝_다음에_닿는다(self):
        hook, _ras, _spr = band.gen(0x9F00)
        m = hook.index(bytes.fromhex("ade626c980d0"))
        n = hook[m + 6]
        # BNE 는 세피아 갈래(마지막 RTS 로 끝) 바로 뒤 = 보통 갈래 시작
        self.assertEqual(hook[m + 7 + n - 1], 0x60)
        self.assertEqual(hook[m + 7 + n :][:3], bytes.fromhex("ad1222"))

    def test_훅과_도우미는_끝까지_디코드된다(self):
        hook, _ras, spr = band.gen(0x9F00)
        for code in (hook, spr, band.HEIGHT_HELPER):
            self.assertEqual(sum(1 for _ in _starts(code)) > 0, True)
            self.assertEqual(_starts(code)[-1] + LEN[code[_starts(code)[-1]]], len(code))
        for at, to in _decode_branches(hook) + _decode_branches(spr) + _decode_branches(band.HEIGHT_HELPER):
            self.assertIn(to, set(_starts(hook)) | set(_starts(spr)) | set(_starts(band.HEIGHT_HELPER)) | {len(hook), len(spr), len(band.HEIGHT_HELPER)})

    def test_크기와_원본_자리(self):
        hook, ras, spr = band.gen(0x9F00)
        run2 = len(ras) + len(spr) + len(band.HEIGHT_HELPER) + 5
        self.assertLessEqual(run2, band.RUN2_MAX)
        self.assertLessEqual(200 + len(hook), 374, len(hook))  # 첫 0xFF 런(스텁 포함)
        self.assertEqual(len(band.OLD_BYR), 12)
        self.assertGreaterEqual(len(band.OLD_IRQ), 8)

    def test_경계_줄은_원판_표시창과_같다(self):
        # 줄 = RCR − 60: 원판 세피아 표시창 55~182 → 55 에 켜고 183 에 끈다
        self.assertEqual(band.RCR_TOP - 60, 55)
        self.assertEqual(band.RCR_BOT - 60, 183)
        self.assertEqual(band.RCR_SBON - 60, 186)


if __name__ == "__main__":
    unittest.main()
