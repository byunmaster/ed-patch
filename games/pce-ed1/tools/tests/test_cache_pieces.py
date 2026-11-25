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


class ChapterLimit(unittest.TestCase):
    """장별 한도 게이트(11-23) — 상주 6 + 그 장 묶음 + 조각 ≤ 14. 옛 꼴 셋을 실이미지 위에서 되살려 잡히는지 본다."""

    def setUp(self):
        iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
        if not iso.exists():
            self.skipTest("구운 이미지 없음")
        self.track = C.built_track(iso)

    def test_current_image_is_clean(self):
        bad, n = C.scan_chapters(self.track)
        self.assertEqual(bad, [])
        self.assertGreater(n, 40)

    def test_limits_are_per_chapter(self):
        self.assertEqual([C.CACHE_SLOTS - C.RESIDENT - b for b in C.bundle_banks(self.track)], [6, 4, 5, 3, 4, 4])

    def test_ref_table_four_bank_piece_is_caught(self):
        """1364 옛 꼴 — 참조표가 가리키는 조각이 4뱅크(4장 워프2 론도 검은 화면). 옛 PEAK15 검사는 이걸 못 봤다(1364 엔 15칸 씬이 없다)."""
        real = C.chapter_entries
        ents = real(self.track)
        hit = [(ch, k) for ch, es in enumerate(ents) for k, (rel, _ns) in enumerate(es) if ch == 3]
        self.assertTrue(hit)
        ch, k = hit[0]
        fake = [list(es) for es in ents]
        fake[ch][k] = (fake[ch][k][0], 16)
        try:
            C.chapter_entries = lambda t: fake
            bad, _n = C.scan_chapters(self.track)
            peak, _ = C.scan(self.track)
        finally:
            C.chapter_entries = real
        self.assertTrue(any(b.startswith("장 4:") and f"rel {fake[ch][k][0]} " in b and "참조표" in b for b in bad), bad)
        self.assertEqual(peak, [])  # 같은 입력에 옛 검사는 초록 — 장별 검사가 따로 있어야 하는 까닭

    def test_partner_only_four_bank_piece_is_caught(self):
        """1444 옛 꼴 — 참조표엔 3뱅크 풀 쪽만 있고 **짝으로만 올라오는 제자리 쪽**이 14섹터(4장 씬 114 검은 화면)."""
        real = C.partners
        seen = []

        def fake(track, rel):
            out = [(prel, 14 if prel == 1444 else pn) for prel, pn in real(track, rel)]
            seen.extend(p for p in out if p[0] == 1444)
            return out

        try:
            C.partners = fake
            bad, _n = C.scan_chapters(self.track)
        finally:
            C.partners = real
        self.assertTrue(seen, "rel 1444 가 어느 조각의 짝으로도 안 나온다 — 대조가 헛돈다")
        self.assertTrue(any(b.startswith("장 4:") and "rel 1444 " in b and "의 짝" in b for b in bad), bad)

    def test_four_bank_piece_fails_only_where_bundle_is_five(self):
        """한도는 장마다 다르다 — 4뱅크 조각은 1·3장(한도 6·5)·2·5·종장(한도 4)에선 통과하고 한도 3 인 4장에서만 걸린다."""
        real = C.chapter_entries
        fake = [[(9000 + ch, 16)] for ch in range(C.CHAPTERS)]
        realp = C.partners
        try:
            C.chapter_entries = lambda t: fake
            C.partners = lambda t, rel: []
            bad, n = C.scan_chapters(self.track)
        finally:
            C.chapter_entries = real
            C.partners = realp
        self.assertEqual(n, 6)
        self.assertEqual([b.split(":")[0] for b in bad], ["장 4"])  # 4뱅크는 한도 3 인 4장만 넘는다(2·5·종장은 한도 4)

    def test_bundle_table_misread_is_refused(self):
        """묶음 표를 엉뚱한 뱅크(0x76)에서 읽으면 한도가 조용히 틀린다 — 원판 값과 다르면 검사 자체를 거부한다."""
        real = C.BUNDLE_REL
        try:
            C.BUNDLE_REL = real - 4
            bad, n = C.scan_chapters(self.track)
        finally:
            C.BUNDLE_REL = real
        self.assertEqual(n, 0)
        self.assertTrue(bad and "묶음 표" in bad[0], bad)


if __name__ == "__main__":
    unittest.main()
