"""고정 길이 복사 검출기 회귀 — **원본이 있어야 돈다**(자리를 원본에서 찾는다).

🔴 이 검출기는 **오탐이 나면 못 쓴다**. 처음 만들었을 때 두 번 헛짚었다(2026-08-27):
  ① 「우리 것이 짧다」를 실패로 쳐서 **9곳**이 붉게 떴다 — 짧으면 NUL 이 함께 복사돼
     목적지가 거기서 끊기니 **오히려 안전**하다.
  ② 소스 후보를 앞 범위의 pc 상대 로드 전부로 봐서 남의 인자가 딸려 왔다
     (「원본 61B 인데 칸 5B」). 언롤이 읽는 레지스터는 **r1** 하나다.
늘 빨간불인 게이트는 아무도 안 본다 — 그래서 판정을 여기 못 박는다.
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import check_fixed_copy as C
import common


def has_original():
    try:
        common.verify_source()
        return True
    except SystemExit:
        return False


@unittest.skipUnless(has_original(), "원본이 없다")
class Sites(unittest.TestCase):
    def test_every_source_fits_its_slot(self):
        """🔴 원본 문자열은 **정의상** 그 칸에 맞는다 — 안 맞으면 소스를 잘못 짚은 것이다."""
        for fname in C.FILES:
            d = common.extract(fname)
            for at, cap, srcs in C.sites(d):
                for lit, v, ln in srcs:
                    self.assertLessEqual(
                        ln, cap, f"{fname} 0x{C.LOAD_BASE + at:X}: 0x{v:X} {ln}B > 칸 {cap}B"
                    )
                    self.assertGreater(lit, C.LOAD_BASE)

    def test_the_crit_site_is_found_in_both(self):
        """회심/통한 자리(14B)는 두 편 다 있고, 우리가 루프로 바꾼 그 자리다."""
        import patch_crit_copy

        for fname in C.FILES:
            d = common.extract(fname)
            at, _size = patch_crit_copy.find_copy(d)
            hit = [s for s in C.sites(d) if at <= s[0] <= at + 0x80]
            self.assertEqual(len(hit), 1, fname)
            self.assertEqual(hit[0][1], 14, f"{fname}: 회심 칸이 14B 가 아니다")

    def test_shorter_is_not_a_failure(self):
        """⚠ 우리 것이 짧은 건 결함이 아니다 — NUL 이 함께 복사돼 목적지가 끊긴다."""
        # (원본 8B · 칸 8B) 자리에 4B 를 넣어도 통과해야 한다
        orig = bytearray(16)
        bad, unread = C.check("x", orig, orig, skip=set())
        self.assertEqual(bad, [])
        self.assertEqual(unread, [])

    def test_unmeasurable_is_reported_not_skipped(self):
        """🔴 **「못 쟀다」와 「볼 게 없다」를 가른다**(2026-09-05).

        `MAXLEN` 안에 NUL 이 없어 길이를 못 재면 예전엔 **조용히 건너뛰었다** — 초록불이
        「없다」가 아니라 「안 봤다」가 되는 자리다(`scan_untranslated` 에서 실제로 물렸다).
        지금은 0건이라 실패로 안 치고 **세어 보고**한다.
        """
        # 계약: `check` 는 **둘**을 돌려준다 — 어긋난 것과 **못 잰 것**
        got = C.check("x", bytearray(16), bytearray(16), skip=set())
        self.assertEqual(len(got), 2, "못 잰 자리를 안 돌려준다")
        # `_strlen` 은 상한 안에 NUL 이 없으면 None 이다 — 그게 「못 쟀다」의 신호다
        d = bytearray(b"\xff" * (C.MAXLEN + 8))
        self.assertIsNone(C._strlen(d, C.LOAD_BASE))
        d[C.MAXLEN - 1] = 0
        self.assertEqual(C._strlen(d, C.LOAD_BASE), C.MAXLEN - 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
