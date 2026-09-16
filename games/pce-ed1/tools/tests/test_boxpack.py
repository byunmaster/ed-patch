"""빈 슬롯 상자(`ファイルがありません`) 압축 그래픽 코덱 — 원본 없이 돈다.

디코더(`$479F`)는 이 세션에서 에뮬레이터 라이브 실측(뱅크 0x78/0x7A 원본 바이트 → 디코드 →
VRAM 에 실제로 편 타일·BAT 표와 바이트까지 비교)으로 검증했다 — devlog 2026-09-16 (10).
그 실측 전량을 여기 담으면 원본 그래픽 자산을 코드에 박는 꼴이라(루트 CLAUDE.md 저작권 절)
**map1 BAT 표 한 장(54B → 51워드)만** 회귀 고정값으로 남긴다 — 이건 문장이 아니라 좌표
표(어느 타일을 어디 놓는가)라 저작권 대상이 아니고, 실측 결과가 옮겨 갔는지 보는 최소 표본이다.

⚠ **인코더는 원본을 몰라도 검증된다** — 답을 아는 표본은 "우리 인코더로 감았다 푼 것"
자신이다(왕복 항등). 크기가 원본과 같은지는 **라이브에서만** 알 수 있어(원본 압축 스트림이
필요) 여기엔 없다 — devlog 09-16 (11)에 그 값(645B, 원본 641B 대비 +4B)이 있다.
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boxpack as bp

# 2026-09-16 라이브 실측: 뱅크 0x7A +0x1F08(msg1 BAT 표 스트림, 모드 바이트 0x02 는 별도)와
# 에뮬레이터가 실제로 편 VRAM 워드(행 12~14, 열 7~23) — devlog 09-16 (10) 대조표 그대로.
MAP1_STREAM = bytes.fromhex(
    "c14f01ed03f2010701b8e8f849010f01f36606f7e242037e023cf6390087"
    "16f13171701f221a272a3401219a37224408204b82474765"
)
MAP1_WORDS = [
    0x47B0, 0x47B1, 0x47B1, 0x47B1, 0x47B2, 0x47B3, 0x47B4, 0x47B5,
    0x47B6, 0x47B7, 0x47B8, 0x47B9, 0x47BA, 0x47BB, 0x47BC, 0x47BA,
    0x47BD, 0x47BE, 0x47C0, 0x47C1, 0x47C2, 0x47C3, 0x47C4, 0x47C5,
    0x47C6, 0x47C7, 0x47C8, 0x47C9, 0x47CA, 0x47CB, 0x47CC, 0x47CD,
    0x47CE, 0x47BF, 0x47CF, 0x47D0, 0x47D1, 0x47D2, 0x47D3, 0x47D4,
    0x47D5, 0x47D6, 0x47D7, 0x47D8, 0x47D9, 0x47DA, 0x47DB, 0x47DC,
    0x47DD, 0x47DE, 0x47DF,
]  # fmt: skip


class Decoder(unittest.TestCase):
    def test_실측_map1_바이트까지_재현(self):
        """🔴 이 값이 어긋나면 디코더를 다시 디스어셈블해서 대조한다 — 짐작으로 고치지 않는다."""
        _, used = bp.decode_stream(MAP1_STREAM, bp.map_nbytes(17, 3))
        self.assertEqual(used, len(MAP1_STREAM))
        out = bp.unpack(MAP1_STREAM, bp.map_nbytes(17, 3), 2)[0]  # unpack() 은 모드 바이트 뒤부터
        got = bp.words(out)[: len(MAP1_WORDS)]
        self.assertEqual([hex(x) for x in got], [hex(x) for x in MAP1_WORDS])


class RoundTrip(unittest.TestCase):
    """인코더·디코더가 서로 맞물리는지 — 답을 아는 표본은 "우리가 감은 것" 자신이다."""

    def test_빈_스트림(self):
        self.assertEqual(bp.decode_stream(bp.encode_stream(b""), 0)[0], b"")

    def test_반복_없는_리터럴(self):
        data = bytes(range(64))
        self.assertEqual(bp.decode_stream(bp.encode_stream(data), len(data))[0], data)

    def test_고도_반복(self):
        data = b"\xab" * 300
        enc = bp.encode_stream(data)
        self.assertEqual(bp.decode_stream(enc, len(data))[0], data)
        self.assertLess(len(enc), len(data) // 4, "많이 반복되는데 안 줄면 인코더가 잘못됐다")

    def test_난수_왕복(self):
        rng = random.Random(20260916)
        for _ in range(20):
            n = rng.randint(1, 500)
            data = bytes(rng.randrange(256) for _ in range(n))
            enc = bp.encode_stream(data)
            self.assertEqual(bp.decode_stream(enc, n)[0], data)

    def test_타일_4플레인_왕복(self):
        rng = random.Random(1)
        tiles = bytes(rng.randrange(256) for _ in range(32 * 5))
        enc = bp.pack(tiles, 4)
        out, used = bp.unpack(enc, len(tiles), 4)
        self.assertEqual(out, tiles)
        self.assertEqual(used, len(enc))

    def test_BAT_2플레인_왕복(self):
        rng = random.Random(2)
        words = bytes(rng.randrange(256) for _ in range(16 * 4))
        enc = bp.pack(words, 2)
        out, used = bp.unpack(enc, len(words), 2)
        self.assertEqual(out, words)
        self.assertEqual(used, len(enc))

    def test_실측_스트림_재인코드도_같은_바이트를_낸다(self):
        """원본이 감은 것을 우리가 풀고 다시 감으면 — 크기는 달라도(devlog 09-16 (11)) 풀면
        여전히 같은 내용이어야 한다(우리 인코더가 항등을 깨지 않는다)."""
        raw, _ = bp.decode_stream(MAP1_STREAM, bp.map_nbytes(17, 3))
        reenc = bp.encode_stream(raw)
        self.assertEqual(bp.decode_stream(reenc, len(raw))[0], raw)


class Geometry(unittest.TestCase):
    def test_map_nbytes_16B_줄_단위(self):
        self.assertEqual(bp.map_nbytes(17, 3), 112)  # 51워드=102B → 16B 줄로 올림 112
        self.assertEqual(bp.map_nbytes(18, 3), 112)  # 54워드=108B → 16B 줄로 올림 112

    def test_words_리틀엔디언(self):
        self.assertEqual(bp.words(b"\x00\x47\x01\x47"), [0x4700, 0x4701])


if __name__ == "__main__":
    unittest.main()
