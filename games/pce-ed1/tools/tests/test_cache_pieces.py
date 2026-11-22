"""캐시 15칸 씬 조각 게이트의 양성 대조 — 4뱅크 조각에 든 15칸 씬을 잡는가(11-22 rel 1476 제자리 쪽 14섹터)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_cache_pieces as C
import common


class CachePieces(unittest.TestCase):
    def test_four_bank_piece_with_peak15_scene_is_caught(self):
        iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
        if not iso.exists():
            self.skipTest("구운 이미지 없음")
        track = C.built_track(iso)
        real = C.sectors_of
        try:
            C.sectors_of = lambda t: {**real(t), 1476: 14}  # 옛 상태 — 제자리 쪽 참조표 섹터 수 14
            bad, _n = C.scan(track)
        finally:
            C.sectors_of = real
        self.assertTrue(any("씬 166" in b and "rel 1476" in b for b in bad), bad)

    def test_current_image_is_clean(self):
        iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
        if not iso.exists():
            self.skipTest("구운 이미지 없음")
        bad, n = C.scan()
        self.assertEqual(bad, [])
        self.assertGreater(n, 10)


if __name__ == "__main__":
    unittest.main()
