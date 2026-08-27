"""씬 재삽입 회귀 — ⚠ **원본 + 덤프가 있어야 돈다**.

🔴 **항등이 이 층의 유일한 토대다.** 원문을 그대로 다시 깔아 바이트가 하나라도 다르면
   자르기·구간·패딩 중 뭔가 틀린 것이고, 그 위에 문안을 얹으면 **번역이 아니라 도구가**
   화면을 깨뜨린다. 그래서 여기서 못 박는다.

같이 못 박는 것 둘(`docs/reference/our-findings.md` 「구조 계약」):
   ② 구조 계약 — `%c`·`%s`·`%d` 의 **개수와 순서**가 계약이다(줄면 소프트락)
   ④ 위치     — 구간 **총 길이가 원본과 같아야** 한다(줄면 뒤가 당겨져 이벤트가 깨진다)
"""

import itertools
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import common
import patch_scn as S


def ready():
    try:
        common.verify_source()
    except SystemExit:
        return False
    return os.path.isdir(S.DUMP)


@unittest.skipUnless(ready(), "원본이나 덤프가 없다")
class Scn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._f, cls.mm = common.open_image()
        cls.files = [p for p, _l, _s in common.iso_files(cls.mm) if S.SCN_RE.match(p)]

    @classmethod
    def tearDownClass(cls):
        cls.mm.close()
        cls._f.close()

    def test_identity_rebuild_is_byte_exact(self):
        """🔴 원문을 그대로 다시 깔면 **바이트 동일**이어야 한다."""
        n = 0
        for path in self.files:
            got = S.load(path)
            if not got:
                continue
            _base, entries = got
            lba, size = next((l, s) for p, l, s in common.iso_files(self.mm) if p == path)
            d = bytes(common.read_extent(self.mm, lba, size))
            for run in S.runs(entries, size):
                blob, _m, _s = S.rebuild(run, {}, d)
                a = run[0][0]
                self.assertEqual(blob, d[a : a + len(blob)], f"{path} 0x{a:X}")
                n += 1
        self.assertGreater(n, 500, "구간이 너무 적다 — 자르기가 망가졌나?")

    def test_run_length_is_preserved(self):
        """④ 구간 총 길이는 원본 그대로다 — 줄면 뒤가 당겨져 이벤트가 깨진다."""
        for path in self.files[:12]:
            got = S.load(path)
            if not got:
                continue
            _base, entries = got
            lba, size = next((l, s) for p, l, s in common.iso_files(self.mm) if p == path)
            d = bytes(common.read_extent(self.mm, lba, size))
            for run in S.runs(entries, size):
                blob, _m, _s = S.rebuild(run, {}, d)
                self.assertEqual(len(blob), run[-1][0] + run[-1][1] - run[0][0], path)

    def test_contract_counts_order_not_just_number(self):
        """② **순서까지** 계약이다 — 개수만 세면 `%s…%d` 를 `%d…%s` 로 내도 통과한다."""
        self.assertEqual(S.contract("%c%s%c은(는)"), S.contract("%c%s%c다"))
        self.assertNotEqual(S.contract("%s와 %d"), S.contract("%d와 %s"))
        self.assertNotEqual(S.contract("%c%s%c"), S.contract("%c%c"))

    def test_changing_one_block_touches_only_its_cell(self):
        """🔴 **합성 시험** — 저본이 없어도 재삽입 경로를 검증할 수 있다.

        블록 하나를 짧게 바꾸면 **그 칸 안에서만** 바뀌어야 한다. 뒤 블록은 자리도
        내용도 그대로다.
        ⚠ 당기지 않는 이유: 칸 꼬리의 마지막 바이트가 **다음 블록의 시작 마커(`0x09`)** 인
          자리가 많다(`00 00 00 09` 182건). 당기면 그 마커가 통째로 어긋난다.
        ⚠ 이걸 안 보면 「항등은 통과하는데 문안을 얹으면 깨지는」 도구가 된다 — 항등은
          바뀌는 게 없어서 치환 경로를 한 번도 안 탄다.
        """
        for path in self.files:
            got = S.load(path)
            if not got:
                continue
            _base, entries = got
            lba, size = next((l, s) for p, l, s in common.iso_files(self.mm) if p == path)
            d = bytes(common.read_extent(self.mm, lba, size))
            for run in S.runs(entries, size):
                if len(run) < 3:
                    continue
                jp = run[0][2].get("text", "")
                short = jp[:-1] if len(jp) > 1 and jp[-1] not in "%csd" else jp
                if not jp or short == jp or S.contract(short) != S.contract(jp):
                    continue
                blob, moves, skip = S.rebuild(run, {jp: short}, d)
                if skip:
                    continue
                start = run[0][0]
                base0 = d[start : start + len(blob)]
                self.assertNotEqual(blob, base0, "아무것도 안 바뀌었다 — 시험이 무의미하다")
                # ① 구간 길이 불변 ② 둘째 블록부터는 자리도 내용도 그대로
                self.assertEqual(len(blob), len(base0))
                a = run[1][0] - start
                self.assertEqual(blob[a:], base0[a:], f"{path}: 뒤 블록이 바뀌었다")
                self.assertEqual(moves[1][1], run[1][0], f"{path}: 뒤 블록 자리가 움직였다")
                return
        self.skipTest("조건에 맞는 구간이 없다")

    def test_too_long_is_skipped_not_truncated(self):
        """칸을 넘는 문안은 **건너뛴다** — 조용히 자르면 화면이 깨진다."""
        for path in self.files:
            got = S.load(path)
            if not got:
                continue
            _base, entries = got
            lba, size = next((l, s) for p, l, s in common.iso_files(self.mm) if p == path)
            d = bytes(common.read_extent(self.mm, lba, size))
            for run in S.runs(entries, size):
                if len(run) < 2:
                    continue
                jp = run[0][2].get("text", "")
                if not jp:
                    continue
                long = jp + "あ" * 40  # 칸을 확실히 넘긴다 (⚠ `_encode` 가 아직 cp932 다)
                blob, _m, skip = S.rebuild(run, {jp: long}, d)
                self.assertTrue(skip, "칸을 넘는데 안 건너뛰었다")
                self.assertIn("칸을 넘는다", skip[0][1])
                a = run[0][0]
                self.assertEqual(blob, d[a : a + len(blob)], "건너뛰었는데 바뀌었다")
                return
        self.skipTest("조건에 맞는 구간이 없다")

    def test_runs_never_swallow_code(self):
        """구간이 코드를 삼키면 안 된다 — 빈틈이 `MAX_GAP` 을 넘으면 끊는다."""
        for path in self.files[:12]:
            got = S.load(path)
            if not got:
                continue
            _base, entries = got
            for run in S.runs(entries, 0):
                for (o1, n1, _e1), (o2, _n2, _e2) in itertools.pairwise(run):
                    self.assertLessEqual(o2 - (o1 + n1), S.MAX_GAP, f"{path} 0x{o1:X}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
