"""파일 확장 회귀 — ⚠ **원본이 있어야 돈다**(ISO 를 파싱한다).

🔴 여기서 못 박는 건 **안전 조건 셋**이다. 셋 다 「조용히 틀리는」 종류라 코드로 검산한다
(`docs/patcher-checklist.md` 2·10).

    ① 디스크에서 안 겹친다  — 늘린 섹터가 다음 파일을 침범하면 남의 자료를 덮는다
    ② 적재해도 안 밟는다    — 같은 주소에 올라가는 파일군의 최대 원본 크기가 상한이다
    ③ 크기가 코드에 없다    — 박혀 있으면 늘려도 그만큼만 읽는다(늘린 의미가 없다)
"""

import itertools
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import common
import expand_files as E


def has_original():
    try:
        common.verify_source()
        return True
    except SystemExit:
        return False


@unittest.skipUnless(has_original(), "원본이 없다")
class Expand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._f, cls.mm = common.open_image()
        cls.rows = E.plan(cls.mm)
        cls.files = common.iso_files(cls.mm)

    @classmethod
    def tearDownClass(cls):
        cls.mm.close()
        cls._f.close()

    def test_lba_never_moves(self):
        """🔴 **LBA 는 안 바꾼다** — 바꾸면 뒤 파일을 전부 밀어야 하고 그게 ISO 재빌드다."""
        cur = {p: lba for p, lba, _s in self.files}
        for p, _at, _d, lba, _old, _new in self.rows:
            self.assertEqual(lba, cur[p], p)

    def test_never_overlaps_the_next_file(self):
        """① 늘린 섹터가 다음 파일을 침범하면 안 된다."""
        lbas = sorted({lba for _p, lba, _s in self.files})
        nxt = dict(itertools.pairwise(lbas))
        for p, _at, _d, lba, _old, new in self.rows:
            sectors = -(-new // E.USER)
            after = nxt.get(lba)
            if after is not None:
                self.assertLessEqual(lba + sectors, after, p)

    def test_never_exceeds_what_the_original_already_loads(self):
        """② 원판이 이미 올리는 크기를 넘지 않는다 — 그게 「뒤가 비었다」는 기본 증거다.

        ⚠ **실기로 잰 군만 예외**다(`E.MEASURED_CAP`). 조건 ②를 그대로 두면 그 파일군의
          **최대 파일 자신은 한 바이트도 못 는다** — `ED2MON06` 이 그 경우였다. 재서 연
          자리는 상한을 그 값으로 올린다. 재지 않은 군은 예외가 없다(아래 시험이 지킨다).
        """
        for pat in E.GROUPS:
            cap = max(s for p, _l, s in self.files if pat.match(p))
            key = next((k for k in E.MEASURED_CAP if k in pat.pattern), None)
            if key:
                cap = max(cap, E.MEASURED_CAP[key])
            for p, _at, _d, _lba, _old, new in self.rows:
                if pat.match(p):
                    self.assertLessEqual(new, cap, f"{p}: {new} > 상한 {cap}")

    def test_measured_cap_only_where_it_was_measured(self):
        """🔴 **잰 자리에만 예외를 준다.** 예외를 추측으로 넓히면 조건 ②가 무의미해진다.

        지금 잰 것은 `ED2MON` 하나뿐이다(2026-08-27 실기: 936B 표식이 ED2 전투 내내
        무사, 쓰기 감시 0건 — devlog 20). 새 군을 넣으려면 **그 군에서 다시 재야** 한다.
        """
        self.assertEqual(set(E.MEASURED_CAP), {"ED2MON"})
        # 잰 값은 그 군이 실제로 올라가는 주소 위에 있어야 한다
        self.assertGreater(
            E.MEASURED_CAP["ED2MON"], max(s for p, _l, s in self.files if "ED2MON" in p)
        )

    def test_size_is_not_hardcoded(self):
        """③ 크기·섹터 수가 코드에 박혀 있으면 늘려도 소용없다."""
        E.check_not_hardcoded()  # 걸리면 assert 로 죽는다

    def test_only_grows_and_stays_in_its_sector(self):
        """늘리기만 한다(줄이면 자료가 날아간다) · 섹터 경계를 안 넘는다."""
        for p, _at, _d, _lba, old, new in self.rows:
            self.assertGreater(new, old, p)
            self.assertLessEqual(new, -(-old // E.USER) * E.USER, f"{p}: 섹터를 넘었다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
