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
          (전각 14×5)을 넘기면 조판 자체가 실패해 「칸을 넘는다」에 닿지도 못한다.
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

    def test_a_block_that_stays_keeps_its_cell(self):
        """🔴 **못 옮긴 블록의 칸은 풀이 아니다**(2026-09-03).

        「참조를 옮기면 그 칸은 아무도 안 본다」는 **옮겨졌을 때만** 참이다. 자리를 못 얻은
        블록은 포인터가 제자리를 가리킨 채 남는데, 그 칸을 남에게 내주면 화면에 **딴 문장**이
        뜬다. 증상이 「일본어가 남았다」가 아니라 「한국어인데 다른 대사」라 스캐너가 못 본다 —
        실측으로 **32블록**이 그 상태였다(ED2 프롤로그·아이템 이름).
        """
        big = {"ptr_at": ["10"], "raw_hex": "00" * 20}  # 20B 칸
        small = {"ptr_at": ["20"], "raw_hex": "00" * 20}
        over = [
            (0x100, "칸을 넘는다", "못 옮길 것", big, b"x" * 100),  # 어디에도 안 들어간다
            (0x200, "칸을 넘는다", "옮길 것", small, b"y" * 19),  # 0x100 의 칸이면 들어간다
        ]
        puts, _ptrs, left = S.migrate(over, 0, 0, 0)  # 꼬리 없음 · spare 없음
        stay = {o for o, _jp in left}
        self.assertIn(0x100, stay, "못 옮긴 블록이 left 에 없다")
        for at, blob in puts:
            for o in stay:
                self.assertFalse(at <= o < at + len(blob), f"제자리에 남는 0x{o:X} 를 덮었다")

    def test_run_is_repacked_only_when_a_cell_overflows(self):
        """🔴 **넘치는 구간만 통째로 다시 깐다**(2026-09-04).

        블록을 제 칸에 두면 남는 자리가 **칸마다 조각**으로 갈려, 총량이 남는데도 큰 문안이
        갈 데가 없다 — 실측: ED2 프롤로그 구간(145블록)은 우리 문안이 원본보다 **1,007B
        작은데도** 넷이 못 들어갔다. ⚠ 반대로 **안 넘치는 구간은 손대지 않는다** — 옮길
        이유가 없는데 옮기면 포인터만 흔든다.
        """
        run = [(0x10, 8, {"ptr_at": ["1"], "raw_hex": "00" * 8, "text": "가"})]
        # 저본이 없으면 넘칠 일도 없다
        self.assertFalse(S._needs_pack(run, {}, b"", frozenset(), None, None))

    def test_a_stride_table_is_never_moved(self):
        """🔴 **같은 간격으로 이어지는 블록은 표다** — 코드가 색인으로 집는다.

        실측 2026-08-28: `/ED.BIN` 0x44BC8 의 HUD 접미 표는 포인터가 있는데도 조립 루틴이
        그 자리에서 4B 를 직접 집었다. 비워 내줬더니 화면에 `メ§電 リ…처` 가 떴다.
        잘기까지 해서 `VACATE_MIN` 이 먼저 걸렀지만, **길고 규칙적인 표**도 있을 수 있다.
        """
        run = [(0x10 + 0x20 * i, 16, {"ptr_at": ["1"], "raw_hex": "00" * 16}) for i in range(5)]
        table = S._stride_table(run)
        self.assertEqual(len(table), 5, "같은 간격 다섯이 표로 안 잡힌다")
        for off, n, e in run:
            self.assertFalse(S._movable(off, n, e, table), f"0x{off:X} 를 옮기려 한다")
        # 간격이 들쭉날쭉하면 표가 아니다
        run2 = [(0x10, 16, {}), (0x40, 16, {}), (0x58, 16, {}), (0xA0, 16, {})]
        self.assertEqual(S._stride_table(run2), set())

    def test_a_name_table_entry_is_never_moved(self):
        """🔴 **마크업이 없으면 표다** — 코드가 색인으로 집는다(2026-09-04 실기).

        구간 압축을 넣자 `/ED.BIN` 의 아이템·몬스터 **이름 칸**이 통째로 밀려 인벤토리에
        「디논A」가 떴다 — 「오디논A」를 **두 바이트 뒤부터** 읽은 것이다. 대사 블록은 창
        종단 `%c` 를 갖는데 이름 칸은 맨 이름뿐이라, 그걸로 가른다.
        ⚠ 08-28 의 「표는 잘고 산문은 길다」(`VACATE_MIN`)로는 안 걸린다 — 이름 칸이 8~14B 다.
        """
        name = {"ptr_at": ["1"], "raw_hex": "00" * 12, "text": "革のたて"}
        talk = {"ptr_at": ["2"], "raw_hex": "00" * 12, "text": "%c마을 사람%c\n어서 오게.%c"}
        self.assertFalse(S._movable(0x10, 12, name), "이름 칸을 옮기려 한다")
        self.assertTrue(S._movable(0x20, 12, talk), "대사 블록을 안 옮긴다")

    def test_pool_uses_the_cell_tail(self):
        """🔴 **칸 꼬리도 풀이다**(2026-09-04). 꼬리(NUL + 0 채움 + 이따금 `0x09`)를 빼고 세면
        조각이 1~4B 씩 잘려 나가 **총량이 남는데도 못 넣는** 상태가 된다.

        `0x09` 가 무엇인지 실기로 쳤다 — `ED1SCN01` 의 꼬리 `09` 열둘을 0 으로 지우고 오프닝을
        끝까지 돌렸더니 **그 바로 뒤 블록 다섯이 전부 정상**이었다(병사·퍼거슨 포함).
        본문에 `0x09` 가 든 블록도, `0x09` 를 가리키는 포인터도 **하나도 없다**(전수).
        """
        e = {"ptr_at": ["100"], "raw_hex": "00" * 8}  # 글자 자리 8B
        over = [(0x10, "칸을 넘는다", "jp", e, b"x" * 9)]  # 10B 필요 — 꼬리를 써야 들어간다
        puts, _p, left = S.migrate(over, 0, 0, 0, spans={0x10: 12})
        self.assertEqual(left, [], "꼬리를 안 쓰면 갈 데가 없다")
        self.assertEqual(puts, [(0x10, b"x" * 9 + b"\x00")])

    def test_touching_chunks_merge(self):
        """🔴 **맞닿은 조각은 합친다** — 안 합치면 총량이 남는데도 큰 문안이 갈 데가 없다.

        꼬리를 풀에 넣으면 칸들이 실제로 맞닿으므로 여기서 비로소 효과가 난다
        (`patch_ui.sys_pack` 이 먼저 물린 함정이다).
        """
        e = {"ptr_at": [], "raw_hex": "00" * 8}
        over = [(0x10, "칸을 넘는다", "jp", e, b"z" * 14)]  # 15B 필요
        # 비우는 칸 8B(0x10~) 과 짧아져 남은 칸 8B(0x18~) 가 **맞닿아 있다**
        puts, _p, left = S.migrate(over, 0, 0, 0, spare=[(0x18, 8)], spans={0x10: 8})
        self.assertEqual(left, [], "합쳐진 16B 에 15B 가 안 들어갔다")
        self.assertEqual(puts, [(0x10, b"z" * 14 + b"\x00")])

    def test_migrate_never_runs_past_the_tail(self):
        """자리가 모자라면 **남긴다** — 넘겨 쓰면 다음 파일을 밟는다."""
        mk = lambda o, n: (o, "칸을 넘는다", "jp", {"ptr_at": [], "raw_hex": ""}, b"x" * n)
        puts, _p, left = S.migrate([mk(1, 8), mk(2, 8)], 0, 0x100, 0x100 + 10)
        self.assertEqual(len(puts), 1)
        self.assertEqual(len(left), 1)

    def test_silence_dots_rule_1_3(self):
        """규칙 1-3 — 점 14개 침묵 줄은 「…」 5개. 다른 길이·이미 「…」 인 줄은 그대로."""
        self.assertEqual(S.silence_dots("." * 14), "…" * 5)
        self.assertEqual(S.silence_dots("%c병사%c\n" + "." * 14 + "%c"), "%c병사%c\n" + "…" * 5 + "%c")
        self.assertEqual(S.silence_dots("두 달 남짓" + "." * 12), "두 달 남짓" + "." * 12)  # 열쇠 없으면 그대로
        self.assertEqual(S.silence_dots("딸이" + "." * 12, "b9ed32bfb0b41137"), "딸이……")  # 원문 7점 → 2
        self.assertEqual(S.silence_dots("남짓" + "." * 12, "e0553b61c5a084dd"), "남짓………")  # 원문 9점 → 3
        self.assertEqual(S.silence_dots("…" * 5), "…" * 5)

    def test_comma_rule_2_13(self):
        """규칙 2-13 ⑨ — 연결어미 `는데·지만·만` 뒤 쉼표: 앞 절 11음절 이하면 빼고 12음절 이상이면 남긴다."""
        self.assertEqual(S.comma_rule("찾아왔는데, 없었다."), "찾아왔는데 없었다.")  # 5음절
        self.assertEqual(S.comma_rule("죄송합니다만, 부탁드립니다."), "죄송합니다만 부탁드립니다.")
        long_ = "이렇게나 오랫동안 기다리고 있었는데, 정말 늦었군."  # 앞 절 12음절 이상
        self.assertEqual(S.comma_rule(long_), long_)
        self.assertEqual(S.comma_rule("가만, 기다려."), "가만, 기다려.")  # 부사 `가만` 은 안 본다
        # 문장 경계 뒤에서 다시 센다
        self.assertEqual(S.comma_rule("아주 길게 오랫동안 이야기했다. 그런데, 좋다."), "아주 길게 오랫동안 이야기했다. 그런데, 좋다.")
        self.assertEqual(S.comma_rule("아주 길게 오랫동안 이야기했다.{p}가는데, 왔다."), "아주 길게 오랫동안 이야기했다.{p}가는데 왔다.")

    def test_migrate_is_deterministic(self):
        """오프셋 순으로 깐다 — 입력 순서가 달라도 같은 배치가 나와야 한다(제1원칙)."""
        mk = lambda o: (o, "칸을 넘는다", "jp", {"ptr_at": [], "raw_hex": ""}, b"y" * 4)
        a = S.migrate([mk(3), mk(1), mk(2)], 0, 0, 0x100)[0]
        b = S.migrate([mk(1), mk(2), mk(3)], 0, 0, 0x100)[0]
        self.assertEqual(a, b)

    def test_scene_never_shares_the_hook_run(self):
        """🔴 **조사 훅과 같은 0런을 나눠 쓰면 게임이 죽는다** (2026-08-30 사고).

        훅 루틴이 2,045B → 2,051B 로 자라며 `(0x07EF45, 451)` 과 **6B 겹쳤고**(ED2 는 9B)
        ED1·ED2 둘 다 오프닝 뒤에 **널로 점프해 죽었다**(PC=0). 두 도구가 같은 0런을
        **각자 표로** 들고 있었던 것이 뿌리다 — 훅이 자라도 이쪽 표는 그대로였다.
        ⚠ 게이트는 하나도 안 울었다. 되읽기·포인터·계약·조판 지문 전부 통과한다 —
          **각자 자기가 쓴 것만** 되읽으니까.
        """
        for path in S._MEASURED_RAW:
            span = S._hook_span(path)
            assert span, f"{path}: 훅 자리를 못 읽었다 — 그러면 겹침을 못 막는다"
            for a, n in S._measured_free(path):
                assert not (max(a, span[0]) < min(a + n, span[1])), (
                    f"{path} 0x{a:X}+{n} 이 훅 자리 0x{span[0]:X}~0x{span[1]:X} 와 겹친다"
                )

    def test_no_measured_free_runs(self):
        """🔴 **본체 파일 안의 0런을 「계측했으니 빈 자리」로 쓰지 않는다** (2026-08-30).

        2026-08-28 에 「필드 이동 + 전투 내내 쓰기 0건」을 근거로 셋을 자리로 삼았는데,
        그 셋이 **프롤로그·타이틀 국면에서 살아 있었다** — 시작 메뉴에 선 채로 workramh 를
        되읽으니 0x7AA83 뒤쪽에 SH-2 오버레이 코드, 0x87300 에 포인터 표가 있었다.
        우리 문안이 그 위에 깔려 ED1·ED2 둘 다 **프롤로그 뒤 화면이 검게 죽었다**.

        ⚠ 뿌리는 「국면이 좁았다」가 아니라 **「계측으로는 못 센다」**다 — 안 밟은 국면이
          하나라도 있으면 초록불이 「없다」가 아니라 「아직 안 봤다」다(체크리스트 4-B).
          국면을 넓혀도 다음 사고를 못 막으므로 **표 자체를 닫는다.**
        ⇒ 자리는 「안 쓰는 걸 봤다」가 아니라 **「구조가 우리 것이다」**로만 얻는다 —
          ISO 꼬리 섹터·비워진 칸·짧아져 남은 칸.
        """
        assert not S._MEASURED_RAW, (
            "본체 0런을 다시 자리로 넣었다 — 계측은 근거가 못 된다. "
            "자리가 더 필요하면 파일 확장·LBA 재배치로 얻는다"
        )
        for path in ("/ED.BIN", "/ED2.BIN"):
            assert S._measured_free(path) == []

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


class NameRules(unittest.TestCase):
    """🔴 **이름 규칙은 `names.py` 한 곳이다** — 사본이 생기면 조용히 갈린다.

    실측 2026-08-29에 셋이 갈려 있었다:
      · 개체 접미 표가 셋(`Ｇ`~`Ｊ` 를 한쪽만 알았다) → 한 화면만 이름이 붙었다
      · 대조 정규화가 셋(`＝` 를 한쪽만 뗐다)
      · `internal_key` 가 `patch_ui` 에만 있어 `patch_scn` 이 **내부 키 19곳을 번역했다**

    ⚠ 「두 구현이 같은 답인가」로 묶으면 **두 곳이 다 보여야** 돌고, 한쪽이 사라지면
      테스트가 무의미해진다(오늘 main 에서 같은 실패를 고쳤다). 그래서 **사본의 존재
      자체**를 막는다 — 이건 한 곳만 보여도 돈다.
    """

    def test_nobody_keeps_a_private_copy(self):
        import glob
        import os
        import re

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 정본이 든 이름과, 「사본이면 반드시 나오는」 표식
        # ⚠ 표식은 **사본이면 반드시 나오는 관용**으로 잡는다. 처음에 `\\uff66` 로 쟀더니
        #   `check_glossary` 의 **가타카나 범위 정규식**에 걸렸다 — 그건 사본이 아니다.
        SIGN = {
            "MARKS = ": "개체 접미 표",
            "plan[c][0]": "문안 인코딩 규칙",
            '<= c <= "\\uff9f"': "내부 키 판정",
        }
        bad = []
        for f in glob.glob(os.path.join(here, "*.py")):
            if os.path.basename(f) in ("names.py", "font.py"):
                continue
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            body = re.sub(r'"""(?:.|\n)*?"""', "", src)  # 주석·독스트링은 뺀다
            for sign, what in SIGN.items():
                if sign in body:
                    bad.append(f"{os.path.basename(f)}: {what}")
        assert not bad, "이름 규칙 사본이 있다 — `names.py` 에 위임해라: " + str(bad)

    def test_encoders_agree(self):
        """⚠ 인코더 넷이 같은 답을 내는가 — 감싸는 규칙은 달라도 **글자 하나**는 같다.

        실측 2026-08-29: `plan[c][0] if c in plan else c.encode("cp932")` 가 **일곱 곳**에
        손으로 적혀 있었다. 지금은 같은 답이지만 한 곳만 바뀌면 표가 다른 인코딩으로
        깔리고, 그건 **화면에서만** 드러난다.
        """
        import font
        import patch_mon_names

        plan = {"가": (b"\x88\x9f", 0), "나": (b"\x88\xa0", 0)}
        for t in ("가나", "가A1 나", "ABC"):
            assert patch_mon_names.encode(t, plan) == font.to_bytes(t, plan), t
            assert font.byte_len(t) == len(font.to_bytes(t, plan)), t

    def test_delegates_agree(self):
        """⚠ 위임이 실제로 같은 답을 내는가 — 얇은 껍데기라도 오타는 난다."""
        import names
        import patch_scn
        import patch_ui

        for t in ("ｴﾙｱｽﾀ", "ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝＢ", "ｳｲﾙ～城", "くぐつ戦士Ｇ", "エルアスタ", "竜の卵"):
            assert patch_scn._internal_key(t) == names.internal_key(t), t
            assert patch_ui._internal_key(t) == names.internal_key(t), t
            assert patch_ui._nname(t) == names.bare(t), t


class KeyContFix(unittest.TestCase):
    """키 대기 뒤 이어 그려지는 블록의 첫 줄을 남은 폭에 맞춘다(10-19) — 낱말 한가운데 접힘 방지."""

    def setUp(self):
        import patch_scn as S

        self.S = S
        S._KEY_CONT = {"ED2": {S.line_key("JPA"): 9.0}}

    def tearDown(self):
        self.S._KEY_CONT = None

    def test_first_word_that_does_not_fit_goes_to_a_new_line(self):
        # 남은 폭 14 − 9 = 5.0 — 「죄수번호」(4.0)는 들어가고 「죄수번호 893번이군.」(첫 줄 전체)은 안 들어간다 → 어절 경계에서 끊는다
        got = self.S.key_cont_fix("JPA", "죄수번호 893번이군.%c", "/BIN/ED2SCN32.BIN")
        self.assertEqual(got, " 죄수번호\n893번이군.%c")

    def test_long_first_word_gets_a_leading_newline(self):
        got = self.S.key_cont_fix("JPA", "어마어마하게큰낱말이다.%c", "/BIN/ED2SCN32.BIN")
        self.assertEqual(got, "\n어마어마하게큰낱말이다.%c")

    def test_unknown_key_or_fitting_line_is_left_alone(self):
        self.assertEqual(self.S.key_cont_fix("JPB", "죄수번호 893번이군.%c", "/BIN/ED2SCN32.BIN"), "죄수번호 893번이군.%c")
        self.assertEqual(self.S.key_cont_fix("JPA", "응!?%c", "/BIN/ED2SCN32.BIN"), " 응!?%c")  # 들어가면 앞 공백 하나

    def test_new_speaker_window_after_text_breaks_the_line(self):
        self.S._KEY_CONT = {"nl": {"ED2": [self.S.line_key("JPN")]}}
        self.assertEqual(self.S.key_cont_fix("JPN", "%c플로라%c\n란도 씨.%c", "/BIN/ED2SCN35.BIN"), "\n%c플로라%c\n란도 씨.%c")


class UntouchedTail(unittest.TestCase):
    """꼬리(확장 영역)는 `patch_ui` 가 먼저 깐 문안 위에 덮어쓰면 안 된다 — 0 으로 비어 있는 구간만 자리다(ED2MON04 0x4D78, 10-19)."""

    def test_tail_skips_bytes_already_written_by_another_patcher(self):
        import patch_scn as S

        orig = bytes(8)  # 원본 8B
        built = bytes(8) + b"\x41\x42\x43\x00" + bytes(6)  # 꼬리 8.. : 먼저 깐 3자 + NUL, 그 뒤 6B 는 빔
        got = S._untouched([[8, 10]], built, orig)
        self.assertEqual(got, [[12, 6]])  # 3자(8~10)를 건너뛰고, 그 문자열의 종단 NUL(11)도 앞 문자열 몫이라 12 부터

    def test_empty_tail_is_still_free(self):
        import patch_scn as S

        self.assertEqual(S._untouched([[4, 6]], bytes(10), bytes(4)), [[4, 6]])


class ContinuationFix(unittest.TestCase):
    """키 대기 뒤 이어 그려지는 글의 첫 줄 — 낱말이 끊기거나 앞 글에 붙지 않게(2026-10-19 qa r6)."""

    def test_inner_key_wait_gets_space_and_word_boundary(self):
        """블록 안쪽 키 대기(`%c`=9) 뒤: 앞 글 바로 뒤에 이어지므로 공백 하나, 안 들어가는 어절은 다음 줄로(「미안 미안.나도 한 번 / 쯤」)."""
        import patch_scn as S

        got = S.key_cont_fix("x", "%c%s%c\n아니 뭐, 미안 미안.%c나도 한 번쯤\n해 보고 싶었거든.%c", "/BIN/ED1SCN24.BIN", [2, "?", 1, 9, 8])
        self.assertEqual(got, "%c%s%c\n아니 뭐, 미안 미안.%c 나도 한\n번쯤 해 보고 싶었거든.%c")

    def test_cursor_at_line_start_adds_no_space(self):
        """커서가 줄 맨 앞(폭 0)이면 앞 글이 없다 — 이음 공백을 넣지 않는다(SCN08 id075 「 그렇게 많이는」)."""
        import patch_scn as S

        S.key_cont_fix("x", "y", "/BIN/ED1SCN08.BIN")  # 표 적재
        S._KEY_CONT["ED1"]["zz-zero"] = 0
        orig = S.line_key
        S.line_key = lambda jp: "zz-zero"
        try:
            got = S.key_cont_fix("x", "그렇게 많이는\n못 지니시겠지요!!%c", "/BIN/ED1SCN08.BIN")
        finally:
            S.line_key = orig
            del S._KEY_CONT["ED1"]["zz-zero"]
        self.assertEqual(got, "그렇게 많이는\n못 지니시겠지요!!%c")

    def test_best_cut_never_follows_a_speaker_header(self):
        import patch_scn as S

        lines = ["가나다.", "라마바.", "류난", "모, 몸이", "않습니다."]
        self.assertEqual(S.best_cut(lines, 2, 4, hdr={2}), 2)  # 머리 줄(2) 앞 — 화자 교대
        self.assertNotEqual(S.best_cut(lines, 2, 4, hdr={1}), 2)  # 머리 줄 바로 뒤는 건너뛴다


class AutoSplit(unittest.TestCase):
    """5행 넘는 쪽을 창 끝(08)으로 가른다 — 문안은 안 바뀐다(10-19)."""

    def test_header_plus_five_lines_is_split_at_a_sentence_end(self):
        import patch_scn as S

        kr = "%c남자%c\n가나다.\n라마바.\n사아자.\n차카타.\n파하."
        got = S.auto_split(kr, 5)
        self.assertEqual(got.replace("\x08", "\n"), kr)  # 글은 그대로
        self.assertIn("\x08", got)
        self.assertEqual(S.auto_split("%c남자%c\n가.\n나.\n다.", 5), "%c남자%c\n가.\n나.\n다.")  # 한도 이내는 손 안 댐

    def test_cut_after_speaker_header_moves_before_it(self):
        """표 컷이 머리 줄 뒤(1)여도 머리 앞(0)으로 — 머리 바로 뒤 창 끝은 안 갈려 본문이 창 아래로 넘쳤다(ED1SCN23 m2, 10-19 qa r6)."""
        import patch_scn as S

        S.key_cont_fix("x", "y", "/BIN/ED1SCN23.BIN")  # 표 적재
        S._KEY_CONT.setdefault("pages", {}).setdefault("ED1", {})["zz-test"] = [1]
        orig = S.line_key
        S.line_key = lambda jp: "zz-test"
        try:
            got = S.page_split("x", "%c류난%c\n모, 몸이 말을\n않습니다!!%c", "/BIN/ED1SCN23.BIN")
        finally:
            S.line_key = orig
            del S._KEY_CONT["pages"]["ED1"]["zz-test"]
        self.assertTrue(got.startswith("\x08%c류난%c"))
        self.assertNotRegex(got, r"%c[^%\n]+%c\x08")

    def test_new_speaker_row_is_the_preferred_cut(self):
        import patch_scn as S

        kr = "%c세리오스%c\n있다!!\n알이야!!\n%c게일%c\n어디 어디,\n좀 보여 줘.%c"
        got = S.auto_split(kr, 5)
        self.assertIn("알이야!!\x08%c게일%c", got)

    def test_ed1_six_rows_need_a_short_last_line(self):
        """ED1 은 6행까지 — 단 꽉 찬 쪽의 마지막 줄이 ▽ 칸(7.5)을 넘으면 그 쪽만 가른다(원판 ▽ 는 아래 가운데, 10-19)."""
        import patch_scn as S

        short = "%c남자%c\n가나다.\n라마바.\n사아자.\n차카타.\n파하."  # 머리 + 5줄 = 6행, 마지막 줄 짧음
        self.assertNotIn("\x08", S.auto_split(short, 6, 7.5))
        long_last = "%c남자%c\n가나다.\n라마바.\n사아자.\n차카타.\n파하파하파하파하파하."  # 마지막 줄 5.5칸이면 통과, 더 길면 가른다
        long_last = long_last.replace("파하파하파하파하파하.", "파하파하파하파하파하파하파하파하.")
        self.assertIn("\x08", S.auto_split(long_last, 6, 7.5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
