"""가게 대사 문자열 포인터 표 — 번역이 표 바이트를 덮으면 가게 코드가 읽는 포인터가 깨진다(10-24 실측: `$C49552`·`$C5BF71`·`$C6AAA0`).
구운 롬의 표 머리 바이트가 원판과 같은지 본다. 원본·구운 롬이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common

# (표 머리 주소, 표 바이트 수) — 머리 주소는 가게 코드가 `lda #lo / #hi / #bank` 로 읽는다
TABLES = (
    (0xC2D63E, 8),
    (0xC494E1, 6),
    (0xC49552, 8),
    (0xC5A640, 8),
    (0xC5BF71, 6),
    (0xC6AAA0, 6),
)
KR_ROM = common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"


@unittest.skipUnless(common.ORIG_ROM.exists() and KR_ROM.exists(), "원본 또는 구운 롬 없음")
class TablePrefix(unittest.TestCase):
    def test_pointer_tables_untouched(self):
        src, kr = common.rom_bytes(), KR_ROM.read_bytes()
        for a, n in TABLES:
            o = common.snes2off(a)
            self.assertEqual(kr[o : o + n], src[o : o + n], f"${a:06X} 표가 원판과 다르다")
            # 첫 포인터는 표 바로 뒤 문자열을 가리킨다(이 표가 진짜 표라는 근거)
            self.assertEqual(src[o] | src[o + 1] << 8, (a & 0xFFFF) + n)

    def test_build_prefix_table_matches(self):
        import build

        self.assertEqual(build.TABLE_PREFIX, {"$C49552": 8, "$C5BF71": 6, "$C6AAA0": 6})


if __name__ == "__main__":
    unittest.main()
