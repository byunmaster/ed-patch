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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "..", "shared"))

import common
import patch_scn as S
from text.line_key import key as line_key


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
        ⚠ **첫 구간을 붙잡지 않는다** — 조판기가 못 받는 꼴(이름 자리가 정본에 없는 등)이면
          바뀌는 게 없어 시험이 헛돈다. 실제로 바뀐 첫 구간을 찾을 때까지 넘긴다.
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
                blob, moves, skip = S.rebuild(run, {line_key(jp): short}, d)
                if skip:
                    continue
                start = run[0][0]
                base0 = d[start : start + len(blob)]
                if blob == base0:
                    continue  # 조판기가 이 꼴을 안 받는다 — 다음 구간으로
                # ① 구간 길이 불변 ② 둘째 블록부터는 자리도 내용도 그대로
                self.assertEqual(len(blob), len(base0))
                a = run[1][0] - start
                self.assertEqual(blob[a:], base0[a:], f"{path}: 뒤 블록이 바뀌었다")
                self.assertEqual(moves[1][1], run[1][0], f"{path}: 뒤 블록 자리가 움직였다")
                return
        self.skipTest("조건에 맞는 구간이 없다")

    def test_too_long_is_skipped_not_truncated(self):
        """칸을 넘는 문안은 **건너뛴다** — 조용히 자르면 화면이 깨진다.

        ⚠ **원문을 늘려 만들지 않는다** — 사전 문안은 `typeset_scn` 을 거치므로 창 총량
          (전각 15×5)을 넘기면 조판 자체가 실패해 「칸을 넘는다」에 닿지도 못한다.
          창에는 들어가되 **칸에는 안 들어가는** 길이(전각 70자)로 잰다.
        ⚠ 화자가 정본으로 번역되면 한글이라 `_encode` 가 cp932 로 못 싼다(빌드는 슬롯
          계획을 넘긴다) — 그런 구간은 이 시험의 대상이 아니라 건너뛴다.
        """
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
                long = "あ" * 70  # 창(75칸)엔 들되 칸엔 확실히 안 든다
                try:
                    blob, _m, skip = S.rebuild(run, {line_key(jp): long}, d)
                except UnicodeEncodeError:
                    continue  # 화자가 한글로 번역된 구간 — 슬롯 계획이 있어야 싼다
                if not skip:
                    continue
                self.assertIn("칸을 넘는다", skip[0][1])
                a = run[0][0]
                self.assertEqual(blob, d[a : a + len(blob)], "건너뛰었는데 바뀌었다")
                return
        self.skipTest("조건에 맞는 구간이 없다")

    def test_writes_only_the_changed_bytes(self):
        """🔴 **구간을 통째로 쓰면 남이 넣은 한국어가 원문으로 돌아간다.**

        같은 파일을 `patch_ui`(시스템 메시지) · `patch_mon_names`(이름 칸)와 나눠 갖는데,
        구간 전체를 쓰면 우리가 안 건드린 블록 자리에 **원문 JP 를 다시 깐다**.
        실측 2026-08-27: `/BIN/ED2MON*` 에서 69자리가 그렇게 되돌아가 있었고, 게이트는
        patch_ui 가 **먼저** 돌아 자기 되읽기를 통과한 뒤라 아무도 못 봤다.
        """
        self.assertEqual(S._diffs(b"abcd", b"abcd"), [])
        self.assertEqual(S._diffs(b"aXcd", b"abcd"), [(1, 2)])
        self.assertEqual(S._diffs(b"aXXd", b"abcd"), [(1, 3)])
        self.assertEqual(S._diffs(b"XbcX", b"abcd"), [(0, 1), (3, 4)])
        # 안 바뀐 자리는 **한 바이트도** 쓰지 않는다 — 그게 이 시험의 전부다
        new, old = b"\x01\x02\x03\x04\x05", b"\x01\xff\x03\xff\x05"
        touched = {i for a, b in S._diffs(new, old) for i in range(a, b)}
        self.assertEqual(touched, {1, 3})

    def test_migrate_leaves_the_original_cell_alone(self):
        """🔴 이주는 **참조만** 옮긴다 — 원본 칸을 앞으로 당기면 다음 블록의 마커가 어긋난다.

        ⚠ **비워진 칸 자체는 풀로 돌아간다**(2026-08-27) — 참조를 옮긴 순간 그 자리를
          가리키는 건 아무것도 없다. 여기서는 칸이 4B 라 자기 블록(9B)이 못 들어가므로
          꼬리로 간다. 「당기지 않는다」와 「비운 자리를 다시 쓴다」는 다른 얘기다.
        """
        e = {"ptr_at": ["100", "200"], "raw_hex": "00" * 4}
        over = [(0x10, "칸을 넘는다 9B > 4B", "jp", e, b"ABCDEFGH")]
        puts, ptrs, left = S.migrate(over, 0x06000000, 0x1000, 0x1400)
        self.assertEqual(puts, [(0x1000, b"ABCDEFGH\x00")])  # NUL 종단까지
        self.assertEqual(sorted(ptrs), [(0x100, 0x06001000), (0x200, 0x06001000)])
        self.assertEqual(left, [])
        # 🔴 원본 칸(0x10)은 어디에도 안 나온다 — 그게 이 시험의 전부다
        self.assertTrue(all(at >= 0x1000 for at, _b in puts))

    def test_migrate_never_runs_past_the_tail(self):
        """자리가 모자라면 **남긴다** — 넘겨 쓰면 다음 파일을 밟는다."""
        mk = lambda o, n: (o, "칸을 넘는다", "jp", {"ptr_at": [], "raw_hex": ""}, b"x" * n)
        puts, _p, left = S.migrate([mk(1, 8), mk(2, 8)], 0, 0x100, 0x100 + 10)
        self.assertEqual(len(puts), 1)
        self.assertEqual(len(left), 1)

    def test_migrate_is_deterministic(self):
        """오프셋 순으로 깐다 — 입력 순서가 달라도 같은 배치가 나와야 한다(제1원칙)."""
        mk = lambda o: (o, "칸을 넘는다", "jp", {"ptr_at": [], "raw_hex": ""}, b"y" * 4)
        a = S.migrate([mk(3), mk(1), mk(2)], 0, 0, 0x100)[0]
        b = S.migrate([mk(1), mk(2), mk(3)], 0, 0, 0x100)[0]
        self.assertEqual(a, b)

    def test_measured_free_only_where_it_was_measured(self):
        """🔴 **잰 자리에만 넣는다.** 본체의 0런은 「0 이라서」가 아니라 「재서」 쓰는 것이다.

        실측 2026-08-28: 두 본체 모두 **가장 큰 0런(1,301B)은 살아 있는 버퍼**였다 —
        필드·전투 중 쉬지 않고 쓰이고, 표식을 심었더니 게임이 그 자리에서 멎었다.
        그 다음 셋은 필드 이동 + 전투 내내 쓰기 0건이었다. 표를 넓히려면 다시 잰다.
        """
        self.assertEqual(set(S.MEASURED_FREE), {"/ED.BIN", "/ED2.BIN"})
        for path, runs in S.MEASURED_FREE.items():
            d = bytes(common.extract(path))
            for a, n in runs:
                self.assertEqual(d[a : a + n], b"\x00" * n, f"{path} 0x{a:X}: 원본이 0 이 아니다")
            # 🔴 살아 있는 버퍼(각 파일의 최대 0런)는 표에 들어오면 안 된다
            live = 0x074A13 if path == "/ED.BIN" else 0x05A70F
            self.assertNotIn(live, [a for a, _n in runs], f"{path}: 살아 있는 버퍼가 표에 있다")

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
