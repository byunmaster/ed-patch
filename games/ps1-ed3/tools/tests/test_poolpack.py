"""읽을거리 풀 사전 압축(`poolpack`) — 합성 풀로 **구조·결정성·펼침 훅(기계어)** 을 시험한다. 원본 없이 돈다.

- 파이썬 기준 구현(`expand_codes`)과 **기계어(미니 MIPS 해석기)** 가 모든 표 항목에서 같은 코드열을 낸다.
- 같은 입력 → 같은 사전·같은 바이트(결정성).
- 되읽은 코드열 = 정본에서 직접 만든 기대값(`verify`), 제어 항목·표 크기 보존.
- 훅 자리가 원본과 다르면 쓰기 전에 선다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_patch
import poolpack
from mips_cpu import RA_END, Cpu

DISC = "ed3"
L = poolpack.LAYOUT[DISC]
REAL_POOLS = [dict(p) for p in L["pools"]]
SIZE = 0xB0000


def _w(buf, off, codes):
    struct.pack_into(f"<{len(codes)}H", buf, off, *codes)
    return off + 2 * len(codes)


def synthetic_exe():
    """원본 풀 구조를 흉내 낸 합성 이미지 — 풀 둘(표 + 조각열) · 제어 항목 · 숫자 이어 읽기(0xEEEE) · 0 빈 글리프 · 훅 자리 원본 워드."""
    exe = bytearray(SIZE)
    # 훅 자리(원본)
    struct.pack_into("<2I", exe, poolpack._fileoff(L["hook_player"]), *L["hook_player_orig"])
    for site, target in L["draw_sites"]:
        struct.pack_into("<I", exe, poolpack._fileoff(site), (3 << 26) | ((target >> 2) & 0x3FFFFFF))
    # 글자 코드 — 반복이 많은 문장(사전이 일을 하도록)
    A, B, C, D, E, F = 0x100, 0x101, 0x102, 0x103, 0x104, 0x105
    streams = {
        0: [
            [A, B, C, A, B, C, D, TERM := 0xFFFF],
            [A, B, A, B, A, B, C, C, 0xFFFF],
            [D, E, F, D, E, F, D, E, F, 0xEEEE, 0x1388, A, B, A, B, 0xFFFF],  # 숫자 이어 읽기(한 흐름)
            [0, A, B, C, A, B, C, 0xFFFF],  # 앞 빈 글리프
        ],
        1: [
            [C, C, C, C, C, C, 0xFFFF],
            [A, B, C, D, E, F, A, B, C, D, E, F, 0xFFFF],
            [A, 0, B, 0, A, 0, B, 0xFFFF],
            [F, E, D, F, E, D, 0xFFFF],
        ],
    }
    pools = []
    for pi, real in enumerate(REAL_POOLS):
        pool = dict(real)
        base = pool["base"]
        pos = base
        entries = []
        for st in streams[pi]:
            entries.append(pos - base)
            pos = _w(exe, pos, st)
        while pos - base < 900:  # 꼬리(코드·사전·버퍼 약 500B)가 앉을 여유 — 글리프 100 + 종결
            pos = _w(exe, pos, [0x1FF] * 100 + [0xFFFF])
        pool["end"] = pos
        pools.append(pool)
        # 표(제어 항목 섞기) — 처음 두 줄 항목 + 제어 + 나머지, 나머지 칸은 제어(0x8002)
        ent = [entries[0], 0x8001, entries[1], entries[2], 0x8002, entries[3]]
        ent += [0x8002] * (pool["n"] - len(ent))
        struct.pack_into(f"<{pool['n']}H", exe, pool["table"], *ent)
    L["pools"] = pools  # 합성 영역(원본보다 작다) — tearDown 이 되돌린다
    return bytes(exe)


class T(unittest.TestCase):
    def tearDown(self):
        L["pools"] = [dict(p) for p in REAL_POOLS]

    def test_roundtrip_and_hook_matches_reference(self):
        orig = synthetic_exe()
        exe = bytearray(orig)
        pl = poolpack.apply(exe, DISC, {}, lambda kr: [])
        self.assertEqual(poolpack.verify(bytes(exe), orig, DISC, {}, lambda kr: [], pl), [])
        # 기계어 — 모든 표 항목에서 펼침 훅이 기준 구현과 같은 코드열을 낸다
        want = poolpack.expected_streams(orig, DISC, {}, lambda kr: [])
        cpu = Cpu({})
        words = pl["words"]
        cb = poolpack.ram(pl["code_off"])
        cpu.prog = {cb + 4 * i: w for i, w in enumerate(words)}
        # 메모리 = 새 이미지(파일 오프셋 → RAM)
        for off in range(0x9D000, 0xA2000):
            cpu.mem[poolpack.ram(off)] = exe[off]
        for pi, pool in enumerate(poolpack.LAYOUT[DISC]["pools"]):
            base_ram = poolpack.ram(pool["base"])
            tab = poolpack.table_entries(bytes(exe), pool)
            for i, v in enumerate(tab):
                if v >= 0x8000:
                    continue
                cpu.regs = [0] * 32
                R = engine_patch._R
                cpu.regs[R["a0"]] = base_ram
                cpu.regs[R["a1"]] = v
                cpu.regs[R["fp"]] = 0x801F0000
                cpu.regs[R["sp"]] = 0x801FFF00
                cpu.regs[R["ra"]] = RA_END
                cpu.run(pl["labels"]["hook_player"])
                got_ptr = cpu.r32(0x801F0000 + 0x1C)
                self.assertEqual(got_ptr, poolpack.ram(pl["buf_off"]), f"풀{pi} 항목 {i}")
                out = []
                p = got_ptr
                while True:
                    w = cpu.r16(p)
                    out.append(w)
                    p += 2
                    if w == 0xFFFF:
                        break
                self.assertEqual(out, want[(pi, i)], f"풀{pi} 항목 {i}")

    def test_hook_leaves_other_bases_alone(self):
        orig = synthetic_exe()
        exe = bytearray(orig)
        pl = poolpack.apply(exe, DISC, {}, lambda kr: [])
        cpu = Cpu({})
        cb = poolpack.ram(pl["code_off"])
        cpu.prog = {cb + 4 * i: w for i, w in enumerate(pl["words"])}
        R = engine_patch._R
        cpu.regs[R["a0"]] = 0x800B1000  # 다른 기준 주소(다른 UI 표)
        cpu.regs[R["a1"]] = 0x20
        cpu.regs[R["fp"]] = 0x801F0000
        cpu.regs[R["sp"]] = 0x801FFF00
        cpu.regs[R["ra"]] = RA_END
        cpu.run(pl["labels"]["hook_player"])
        self.assertEqual(cpu.r32(0x801F0000 + 0x1C), 0x800B1020)  # 원래 계산(a0 + a1) 그대로

    def test_wrapper_expands_a1_and_tailcalls_drawer(self):
        orig = synthetic_exe()
        exe = bytearray(orig)
        pl = poolpack.apply(exe, DISC, {}, lambda kr: [])
        want = poolpack.expected_streams(orig, DISC, {}, lambda kr: [])
        cpu = Cpu({})
        cb = poolpack.ram(pl["code_off"])
        cpu.prog = {cb + 4 * i: w for i, w in enumerate(pl["words"])}
        # 그리개 자리에 `jr ra · nop` — 래퍼가 꼬리 점프한 곳에서 a1 을 본다
        for target in (0x8001A7E8, 0x8001A40C):
            cpu.prog[target] = (8 << 21) | (31 << 11) * 0 | 8  # jr ra (rs=31)
            cpu.prog[target] = 0x03E00008
            cpu.prog[target + 4] = 0
        for off in range(0x9D000, 0xA2000):
            cpu.mem[poolpack.ram(off)] = exe[off]
        pool = L["pools"][0]
        tab = poolpack.table_entries(bytes(exe), pool)
        R = engine_patch._R
        for name in ("wrap_a", "wrap_b"):
            i = next(k for k, v in enumerate(tab) if v < 0x8000)
            cpu.regs = [0] * 32
            cpu.regs[R["a1"]] = poolpack.ram(pool["base"] + tab[i])
            cpu.regs[R["a0"]] = 0x1234
            cpu.regs[R["a2"]] = 0x55
            cpu.regs[R["sp"]] = 0x801FFF00
            cpu.regs[R["ra"]] = RA_END
            cpu.run(pl["labels"][name])
            self.assertEqual(cpu.regs[R["a1"]], poolpack.ram(pl["buf_off"]))
            self.assertEqual((cpu.regs[R["a0"]], cpu.regs[R["a2"]], cpu.regs[R["sp"]]), (0x1234, 0x55, 0x801FFF00))
            out = []
            p = cpu.regs[R["a1"]]
            while True:
                w = cpu.r16(p)
                out.append(w)
                p += 2
                if w == 0xFFFF:
                    break
            self.assertEqual(out, want[(0, i)])

    def test_translation_rows_replace_segments_and_deterministic(self):
        orig = synthetic_exe()
        segs = poolpack.segments(orig, L["pools"][0])
        off = segs[0][0]
        rows = {off: "ab"}  # 합성 encode 가 두 코드로
        enc = lambda kr: [0x100 + (ord(c) - 97) for c in kr]
        a = bytearray(orig)
        b = bytearray(orig)
        pa = poolpack.apply(a, DISC, rows, enc)
        pb = poolpack.apply(b, DISC, rows, enc)
        self.assertEqual(bytes(a), bytes(b))
        self.assertEqual(pa["merges"], pb["merges"])
        self.assertEqual(poolpack.verify(bytes(a), orig, DISC, rows, enc, pa), [])
        got = poolpack.read_streams(bytes(a), DISC, pa["merges"])
        self.assertEqual(got[(0, 0)][:-1], enc("ab"))

    def test_line_too_long_is_refused(self):
        orig = synthetic_exe()
        off = poolpack.segments(orig, L["pools"][0])[0][0]
        with self.assertRaises(poolpack.PoolPackError):
            poolpack.plan(orig, DISC, {off: "x" * 25}, lambda kr: [0x100] * len(kr))

    def test_hook_site_original_is_checked(self):
        orig = bytearray(synthetic_exe())
        struct.pack_into("<I", orig, poolpack._fileoff(L["hook_player"]), 0)
        with self.assertRaises(poolpack.PoolPackError):
            poolpack.apply(orig, DISC, {}, lambda kr: [])

    def test_dictionary_depth_and_codes_below_8000(self):
        seq = [[1, 2] * 40 + [0xFFFF]]
        merges, comp = poolpack.build_dict(seq)
        self.assertTrue(all(poolpack.DICT_BASE <= poolpack.DICT_BASE + k < 0x8000 for k in range(len(merges))))
        out = poolpack.expand_codes(comp[0], merges)
        self.assertEqual(out, seq[0])

    def test_machine_code_has_no_load_delay_violation(self):
        pl = poolpack.plan(synthetic_exe(), DISC, {}, lambda kr: [])
        engine_patch.verify(pl["words"], poolpack.ram(pl["code_off"]))


if __name__ == "__main__":
    unittest.main()
