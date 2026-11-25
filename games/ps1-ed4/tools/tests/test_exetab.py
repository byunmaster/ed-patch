"""실행파일 낱말 표 재구축 회귀 — **원본 없이 돈다**(합성 표)."""

import struct
import unittest

import _path  # noqa: F401
import exetab

TERM = 0x8000


def make(strings, gap_after=None):
    """[u16 표 N][문자열…] — 표[0] = 표 자신의 길이(N*2). 반환 (바이트열, 표 주소, base, N)."""
    n = len(strings)
    pool, offs, cur = b"", [], n * 2
    for s in strings:
        offs.append(cur)
        body = struct.pack(f"<{len(s) + 1}H", *s, TERM)
        pool += body
        cur += len(body)
    return struct.pack(f"<{n}H", *offs) + pool, 0, 0, n


CM = {c: chr(0x3041 + c) for c in range(1, 60)}


class TestRebuild(unittest.TestCase):
    def test_표를_규격으로_찾는다(self):
        data, *_ = make([[1, 2, 3], [4, 5], [6, 7, 8, 9]])
        self.assertEqual(exetab.scan_tables(data, CM, min_n=3), [{"table": 0, "base": 0, "n": 3}])

    def test_항등_재구축은_바이트_같다(self):
        data, tbl, base, n = make([[1, 2, 3], [4, 5], [6, 7, 8, 9]])
        cur = [
            exetab.raw_string(data, base + x)[0] for x in struct.unpack_from(f"<{n}H", data, tbl)
        ]
        out, _ = exetab.rebuild(data, tbl, base, n, cur)
        self.assertEqual(out, data)

    def test_짧은_쪽에서_빌려_긴_쪽을_늘린다(self):
        data, tbl, base, n = make([[1, 2, 3, 4, 5], [6], [7, 8, 9]])
        new = [[1, 2, 3, 4, 5, 10, 11], [6], [7]]  # 총량 안 — 둘째·셋째가 줄어 첫째가 늘었다
        out, _slack = exetab.rebuild(data, tbl, base, n, new, pad_code=40)
        for i, x in enumerate(struct.unpack_from(f"<{n}H", out, tbl)):
            got, term = exetab.raw_string(out, base + x)
            self.assertEqual(got[: len(new[i])], new[i])
            self.assertEqual(term, TERM)
        self.assertEqual(len(out), len(data))

    def test_예산을_넘으면_운다(self):
        data, tbl, base, n = make([[1], [2], [3]])
        with self.assertRaises(exetab.ExeTextError):
            exetab.rebuild(data, tbl, base, n, [[1] * 9, [2], [3]])

    def test_남는_칸은_종결_앞을_채움_글자로_채운다(self):
        data, tbl, base, n = make([[1, 2, 3, 4], [5, 6, 7, 8]])
        out, _ = exetab.rebuild(data, tbl, base, n, [[1], [5]], pad_code=40)
        ents = struct.unpack_from(f"<{n}H", out, tbl)
        got, term = exetab.raw_string(out, base + ents[-1])
        self.assertEqual(term, TERM)
        self.assertIn(
            40, got
        )  # 마지막 조각에 채움 글자 — 종결 워드로 채우면 순차 스캔 목록이 끊긴다


class TestRelocate(unittest.TestCase):
    """표 옮기기 — 합성 실행파일(코드 몇 줄 + 표 + 풀 + 빈 자리). 파일 오프셋 = RAM - 0x80010000 + 0x800."""

    BASE_OFF = (
        0x18000  # 합성 표 파일 오프셋(RAM 0x80027800 → lui 0x8002, 범위 0x80018000~0x8002FFFF)
    )
    ARENA_OFF = 0x9000  # 범위 안(RAM 0x80018800) · 옛 표보다 아래(오프셋이 양수)

    def build(self):
        n_words = 8
        strings = [[1, 2, 3], [4, 5], [6, 7, 8, 9]]
        tbl, _, _, n = make(strings)
        exe = bytearray(0x20000)
        exe[self.BASE_OFF : self.BASE_OFF + len(tbl)] = tbl
        ram = self.BASE_OFF - 0x800 + 0x80010000
        hi = (ram >> 16) + (1 if (ram & 0xFFFF) >= 0x8000 else 0)
        # 코드: lui v0,hi ; addiu a1,v0,lo ; (같은 lui 를 다른 명령이 또 읽는다)
        code = [0x3C020000 | hi, 0x24450000 | (ram & 0xFFFF), 0x8C430000 | 0x10]
        struct.pack_into(f"<{len(code)}I", exe, 0x100, *code)
        _ = n_words
        return bytes(exe), n

    def test_기준_상수를_찾고_공유를_알린다(self):
        exe, _ = self.build()
        refs = exetab.find_base_refs(exe, self.BASE_OFF - 0x800 + 0x80010000)
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0]["shared"])  # 셋째 명령이 같은 lui 값을 읽는다

    def test_옮기면_기준_상수와_표가_새_자리를_가리킨다(self):
        exe, n = self.build()
        new, _end, moved = exetab.relocate_units(
            exe,
            self.BASE_OFF,
            self.BASE_OFF,
            n,
            {self.BASE_OFF + 2 * n: [1, 2, 3, 4, 5, 6]},
            self.ARENA_OFF,
        )
        self.assertEqual(moved, 1)
        # 코드: addiu 의 imm 이 새 주소 - lui 값
        ram_new = self.ARENA_OFF - 0x800 + 0x80010000
        w = struct.unpack_from("<I", new, 0x104)[0]
        hi = struct.unpack_from("<I", new, 0x100)[0] & 0xFFFF
        imm = struct.unpack("<h", struct.pack("<H", w & 0xFFFF))[0]
        self.assertEqual((hi << 16) + imm, ram_new)
        # 새 표: 첫 항목은 옮긴 새 문자열(표 바로 뒤), 안 고친 단위는 옛 자리(양수 오프셋)
        ents = struct.unpack_from(f"<{n}H", new, self.ARENA_OFF)
        self.assertEqual(exetab.raw_string(new, self.ARENA_OFF + ents[0])[0], [1, 2, 3, 4, 5, 6])
        self.assertEqual(exetab.raw_string(new, self.ARENA_OFF + ents[1])[0], [4, 5])
        # 옛 표·풀은 그대로(닻)
        self.assertEqual(
            new[self.BASE_OFF : self.BASE_OFF + 2 * n], exe[self.BASE_OFF : self.BASE_OFF + 2 * n]
        )

    def test_lui_범위_밖이면_운다(self):
        exe, n = self.build()
        with self.assertRaises(exetab.ExeTextError):
            exetab.relocate_units(
                exe, self.BASE_OFF, self.BASE_OFF, n, {self.BASE_OFF + 2 * n: [1]}, 0x1F000
            )


if __name__ == "__main__":
    unittest.main()
