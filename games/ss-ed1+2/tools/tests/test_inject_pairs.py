"""주입 `%c` 쌍 — **원본 없이** 도는 회귀. 함정마다 하나씩(체크리스트 7).

여기서 지키는 것은 넷이다:
  ① 쌍은 **콜사이트 인자에서 읽는다** — 텍스트 모양으로 찍지 않는다
  ② 되돌릴 창 번호는 **지워 가는 중간 결과**에서 센다 (실제로 틀렸던 자리)
  ③ 되돌리면 구조 계약(`%c` 개수·순서)이 원본과 같아진다
  🔴 ④ **모르면 안 건드린다** — 인자를 못 읽었거나 명령이 공유되면 아무 것도 안 한다
"""

import json
import os
import struct
import sys
import unittest

_T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _T)

import inject_pairs as I


def callsite(lead=0x83, low=0x5C):
    """합성 콜사이트 — 「`ソ` 를 인자 둘로 주입하는」 실제 꼴을 그대로 흉내 낸다.

    mov.w @(9,pc),r7   ; r7 = lead      (0x16 의 워드)
    mov.l @(5,pc),r5   ; r5 = 서식      (0x18 의 롱)
    mov #6,r1 · push · mov #1,r1 · push · mov #low,r1 · push
    mov #2,r6
    jsr @r11 · nop
    """
    w = [
        0x9709,
        0xD505,
        0xE106,
        0x2F16,
        0xE101,
        0x2F16,
        0xE100 | low,
        0x2F16,
        0xE602,
        0x4B0B,
        0x0009,
    ]
    d = b"".join(struct.pack(">H", x) for x in w)
    d += struct.pack(">H", lead)  # 0x16 워드 리터럴
    d += struct.pack(">I", 0x060D3F40)  # 0x18 서식 포인터
    return d, 0x18


class Args(unittest.TestCase):
    def test_args_come_from_the_callsite(self):
        """① 인자열은 `[r6, r7] + reversed(푸시)` 다 — 마크업 수와 같아야 한다."""
        d, ptr = callsite()
        got = [v for v, _o in I.args_of(d, ptr)]
        self.assertEqual(got, [2, 0x83, 0x5C, 1, 6])

    def test_pair_is_read_not_guessed(self):
        """`%c%c` 둘의 인자가 (선두바이트, 0x5C) 일 때만 주입 쌍이다."""
        d, ptr = callsite()
        text = "%c%c%cニア%c\nテスト%c"
        pairs = I.pairs_of(text, I.args_of(d, ptr))
        self.assertEqual([(i, ch) for i, ch, _a, _b in pairs], [(1, "ソ")])

    def test_color_pair_is_not_an_escape(self):
        """🔴 이름칸 색코드도 `%c%c` 꼴이다 — 인자가 제어코드면 쌍이 아니다."""
        args = [(2, 0x10), (2, 0x12), (1, 0x14), (8, 0x16), (6, 0x18)]
        self.assertEqual(I.pairs_of("%c%c%cニア%c\nテスト%c", args), [])

    def test_digit_injection_is_not_an_escape(self):
        """🔴 수치 두 자리도 `%c%c` 로 주입된다(`いまのところ%c%c連勝`). 뒷바이트가 0x5C 가 아니다."""
        args = [(0x82, 0x10), (0x53, 0x12)]
        self.assertEqual(I.pairs_of("%c%c連勝", args), [])

    def test_unreadable_arg_never_becomes_a_pair(self):
        """④ 못 읽은 인자(분기 목적지 콜사이트)는 쌍이 안 된다 — 추측하지 않는다."""
        args = [(0x82, 0x10), (None, None)]
        self.assertEqual(I.pairs_of("%c%c連勝", args), [])

    def test_arg_count_must_match_markup(self):
        """인자 수가 마크업과 다르면 우리가 잘못 읽은 것이다 — 전부 포기한다."""
        d, ptr = callsite()
        self.assertEqual(I.pairs_of("%c%cニア%c", I.args_of(d, ptr)), [])

    def test_pointer_arg_on_a_c_marker_is_refused(self):
        """`%c` 자리에 포인터가 오면 인자가 밀린 것이다 — 아무 것도 안 한다."""
        args = [(0x060D0000, 0x10), (0x83, 0x12), (0x5C, 0x14)]
        self.assertEqual(I.pairs_of("%c%c%cニア", args), [])


class Restore(unittest.TestCase):
    def test_tail_index_counts_on_the_stripped_text(self):
        """🔴 두 쌍짜리 블록 — 창 번호를 **원본에서** 세면 뒤 쌍이 다른 창에 붙는다.

        실측(2026-09-03): 2·6 이 나왔는데 옳은 값은 2·4 였다. 6 으로 붙이면 이름칸 쌍이
        본문 창으로 가서 인자 순서가 어긋난다.
        """
        t = "%c%s%c\nねえ、ファーガ%c%cン。%c%cファーガ%c%cン%c\nふむ%c"
        jp, tails = I.restore(t, [(3, "ソ"), (7, "ソ")])
        self.assertEqual(tails, [2, 4])
        self.assertEqual(jp.count("%c"), t.count("%c") - 4)
        # ⚠ 되살린 뒤에도 `%c%c` 는 남는다 — **창 끝 + 이름칸 시작**이 붙은 정상 꼴이다.
        #   그래서 「글자 사이에 낀 `%c%c`」 같은 텍스트 규칙으로는 쌍을 못 가른다.
        self.assertIn("%c%cファーガソン", jp)

    def test_reinsert_restores_the_contract(self):
        """③ 되돌리면 `%c` 개수가 원본과 같아진다 — 창 수 계약(소프트락 방지)."""
        t = "%c%c%cニア%c\nテスト%c"
        jp, tails = I.restore(t, [(1, "ソ")])
        self.assertEqual(jp.count("%c"), t.count("%c") - 2)
        built = I.reinsert("%c소니아%c\n테스트%c", tails)
        self.assertEqual(built.count("%c"), t.count("%c"))
        self.assertEqual(built, "%c소니아%c%c%c\n테스트%c")

    def test_pair_stays_inside_its_own_window(self):
        """🔴 창을 넘겨 되돌리면 **뒤 인자가 전부 밀린다** — 같은 창 꼬리여야 한다."""
        t = "%c%c%cニア%c\nテスト%c"
        _jp, tails = I.restore(t, [(1, "ソ")])
        built = I.reinsert("%c소니아%c\n테스트%c", tails)
        # 되돌린 쌍 앞의 `%c` 수 = 원본에서 그 쌍 앞의 `%c` 수
        self.assertEqual(built.index("%c%c%c"), built.index("%c소니아") + len("%c소니아"))

    def test_lost_window_refuses(self):
        """조판이 창을 잃으면 넣지 않는다 — 억지로 붙이면 계약이 깨진다."""
        self.assertIsNone(I.reinsert("소니아", [3]))

    def test_no_pairs_is_identity(self):
        self.assertEqual(I.restore("%cソニア%c", []), ("%cソニア%c", []))
        self.assertEqual(I.reinsert("%c소니아%c", []), "%c소니아%c")


class Words(unittest.TestCase):
    def test_patch_is_mov_imm_space_in_place(self):
        """즉치도 워드 리터럴 적재도 **2바이트**라 `mov #0x20,Rn` 으로 제자리 교체다."""
        d, ptr = callsite()
        args = I.args_of(d, ptr)
        pairs = I.pairs_of("%c%c%cニア%c\nテスト%c", args)
        got = I.arg_words(d, args, pairs)
        self.assertEqual(got, [(0x00, 0x9709, 0xE720), (0x0C, 0xE15C, 0xE120)])
        for _off, old, new in got:
            self.assertEqual(len(struct.pack(">H", old)), len(struct.pack(">H", new)))

    def test_shared_producer_is_refused(self):
        """🔴 한 명령이 **제어코드도 만들면** 안 고친다 — 공백이 창 전환을 먹는다."""
        args = [(2, 0x10), (0x83, 0x20), (0x5C, 0x22), (2, 0x22)]
        pairs = [(1, "ソ", 0x20, 0x22)]
        self.assertIsNone(I.arg_words(b"\0" * 0x40, args, pairs))

    def test_unknown_producer_is_refused(self):
        args = [(2, 0x10), (0x83, None), (0x5C, 0x22)]
        pairs = [(1, "ソ", None, 0x22)]
        self.assertIsNone(I.arg_words(b"\0" * 0x40, args, pairs))


class Canon(unittest.TestCase):
    """얼린 정본 — 🔴 **발견을 못 박는다.** 되돌리려면 실기 근거가 있어야 한다."""

    def setUp(self):
        p = os.path.join(os.path.dirname(_T), "inject_pairs.json")
        with open(p, encoding="utf-8") as f:
            self.canon = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    def test_five_sites_all_so(self):
        """실측 2026-09-03: 새턴 전체에 다섯 자리, 전부 `ソ`(0x835C) 다."""
        self.assertEqual(len(self.canon), 5)
        for k, v in self.canon.items():
            self.assertTrue(v["glyphs"], k)
            for ch in v["glyphs"].values():
                self.assertEqual(ch, "ソ", k)
                self.assertEqual(ch.encode("cp932")[1], 0x5C, k)

    def test_new_words_are_mov_space(self):
        """새 워드는 전부 `mov #0x20,Rn` 이고 **레지스터가 안 바뀐다.**"""
        for k, v in self.canon.items():
            for a, (old, new) in v["words"].items():
                o, n = int(old, 16), int(new, 16)
                self.assertEqual(n & 0xF0FF, 0xE020, f"{k} {a}")
                if o >> 12 == 0xE:  # mov #imm,Rn → 레지스터가 같아야 한다
                    self.assertEqual(o >> 8, n >> 8, f"{k} {a}")

    def test_words_cover_both_bytes_of_every_pair(self):
        """쌍 하나 = 인자 둘. 하나만 고치면 **반쪽 글자**가 남는다.

        ⚠ 명령 수가 `2 × 쌍` 은 아니다 — 한 블록의 두 쌍이 **같은 명령 둘**을 나눠 쓰는
          자리가 실재한다(ED1SCN01 0xC58: `mov #92,r3` · `mov.w …,r2` 를 각각 두 번 푸시).
          그래서 상한만 본다.
        """
        for k, v in self.canon.items():
            n = len(v["words"])
            self.assertGreaterEqual(n, 2, k)
            self.assertEqual(n % 2, 0, k)
            self.assertLessEqual(n, 2 * len(v["glyphs"]), k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
