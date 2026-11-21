"""아이템 값 ×10 고리 교체(`pricefast`) — 새 고리를 시뮬레이터로 돌려 24비트 곱과 대조하고, 원판 고리(진짜 곱셈 루틴째)를 돌려 파이썬 모델·아이템 표와 대조한다.
원본 디스크가 필요한 검사는 원본이 없으면 건너뛴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cpu65
import pricefast as P


def run_loop(mem: bytearray, mant: int, exp: int, limit: int) -> tuple[int, int, int]:
    """고리 진입(`$86AE`) 상태를 만들고 고리 끝(`$86E1`)까지 — (값, 남은 지수, 걸린 명령 수)."""
    mem[P.LO], mem[P.MID], mem[P.HI], mem[P.EXP] = mant, 0, 0, exp
    c = cpu65.CPU(mem)
    c.sp = 0xF0
    c.pc = P.ORG
    n = 0
    while c.pc != P.END:
        c.step()
        n += 1
        assert n < limit, (mant, exp)
    return mem[P.LO] | mem[P.MID] << 8 | mem[P.HI] << 16, mem[P.EXP], n


class NewLoopTest(unittest.TestCase):
    def setUp(self):
        self.code = P.code()

    def test_same_site_length(self):
        self.assertEqual(len(self.code), len(P.OLD))
        self.assertEqual(P.ORG + len(P.OLD), P.END)

    def test_full_space_is_24bit_product(self):
        """가수 0~255 × 지수 1~7 전부 — 24비트로 자른 진짜 곱, 지수는 0 으로 끝난다."""
        for m in range(256):
            for e in range(1, 8):
                mem = bytearray(0x10000)
                mem[P.ORG : P.ORG + len(self.code)] = self.code
                v, left, _n = run_loop(mem, m, e, 2000)
                self.assertEqual((v, left), (P.price_new(m, e), 0), (m, e))

    def test_touches_only_loop_cells(self):
        """고리가 쓰는 영 페이지는 값 3칸 · 지수 · `$F8` 뿐(원판이 고리 뒤에 다시 채우는 칸) — 원판 고리가 쓰던 `$F9·$7F·$80·$EC~$ED·$FE~$FF` 도 안 건드린다."""
        mem = bytearray(0x10000)
        mem[P.ORG : P.ORG + len(self.code)] = self.code
        before = bytes(mem[:0x100])
        run_loop(mem, 0xC8, 6, 2000)
        changed = {i for i in range(0x100) if mem[i] != before[i]}
        self.assertLessEqual(changed, {P.LO, P.MID, P.HI, P.EXP, P.TMP})

    def test_model_differs_somewhere(self):
        """원판 고리는 진짜 곱이 아니다 — 모델이 그 차이(60쌍)를 담고 있어야 `check_items` 가 뜻이 있다."""
        diff = [
            (m, e) for m in range(256) for e in range(8) if P.price_orig(m, e) != P.price_new(m, e)
        ]
        self.assertEqual(len(diff), 60)
        with self.assertRaises(AssertionError):
            P.check_items([bytes(diff[0]) + b"\0\0\0\0"])


class OriginalLoopTest(unittest.TestCase):
    """원판 뱅크를 읽어 원판 고리를 곱셈 루틴(`$59C1`·`$5962`)째 돌린다."""

    @classmethod
    def setUpClass(cls):
        try:
            import sysstrings as S

            cls.b68, cls.b6f = S.bank_bytes(0x68), S.bank_bytes(P.BANK)
            cls.tails = [bytes.fromhex(x["tail"]) for x in S.read_fixed("items")]
        except Exception as e:  # 원본 디스크 없음
            raise unittest.SkipTest(str(e)) from e

    def _mem(self) -> bytearray:
        mem = bytearray(0x10000)
        mem[0x4000:0x6000] = self.b68
        mem[0x8000:0xA000] = self.b6f
        return mem

    def test_site_bytes(self):
        self.assertEqual(self.b6f[P.OFF : P.OFF + len(P.OLD)], P.OLD)

    def test_model_matches_original_code(self):
        """파이썬 모델(`price_orig`) = 원판 기계어 — 가수 전부 × 지수 1~7."""
        for m in range(256):
            for e in range(1, 8):
                v, _left, _n = run_loop(self._mem(), m, e, 200000)
                self.assertEqual(v, P.price_orig(m, e), (m, e))

    def test_items_same_price_and_faster(self):
        """아이템 표 117종 — 원판 고리와 새 고리의 값이 같고, 새 고리가 훨씬 적은 명령으로 끝난다."""
        P.check_items(self.tails)
        code = P.code()
        for i, t in enumerate(self.tails):
            if not t[1]:
                continue  # 지수 0 은 고리를 안 탄다
            old, _l, n_old = run_loop(self._mem(), t[0], t[1], 200000)
            mem = self._mem()
            mem[P.ORG : P.ORG + len(code)] = code
            new, _l, n_new = run_loop(mem, t[0], t[1], 2000)
            self.assertEqual(old, new, i)
            self.assertLess(n_new * 8, n_old, i)


if __name__ == "__main__":
    unittest.main()
