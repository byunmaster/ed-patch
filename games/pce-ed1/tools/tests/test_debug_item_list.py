"""디버그 I·W 목록(`debug_item_list`) — 손으로 짠 기계어를 (1) 디코드·분기 검산 (2) 시뮬레이터로 조작 순서를 돌려 상태·그린 줄을 대조(위·아래는 다시 그리지 않고 두 줄만)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import debug_item as DI
import debug_item_list as L
import debug_warp as W
import huc6280_dis as D

NAME_CONV, FULLCHK, ADD, DBGDRAW = 0x864B, 0x9B41, 0x9B5F, 0x6541


def blob():
    org, b, entry, entry_w = L.assemble()
    return org, b, entry, entry_w


NAME_CONV, FULLCHK, ADD, DBGDRAW, BUILD_ADDR = 0x864B, 0x9B41, 0x9B5F, 0x6541, 0x85FD


class Sim:
    """FAR 호출·그리기·대기를 가짜로 — 이름 변환은 `$F8`(번호)를 `$CFF1` 에 14B(앞 `20` 채움 + 글자 하나 `F1 번호`)로 쓴다.
    W 모드는 빌더(`$85FD`)가 `$CF43` 에 장소 번호를 쓰고 이름 루틴(`$9505`)이 `$C07D` 에 12B 이름(앞 `81 40` + 글자 + `06 00`)을 쓴다고 흉내 낸다."""

    def __init__(self, pads, full=False, mode="i", places=(1, 2, 3, 48)):
        self.org, self.b, self.entry, self.entry_w = blob()
        mem = bytearray(0x10000)
        mem[self.org : self.org + len(self.b)] = self.b
        worg, wblob, _p, _d = (
            W.assemble()
        )  # 「W」 라벨 빨강 루틴(`wdraw`)이 W 코드 뭉치에 있다 — I 닫기가 부른다
        mem[worg : worg + len(wblob)] = wblob
        for a in (L.WAIT, L.DRAW, L.TILE_RESET, L.SOUND):
            mem[a] = 0x60
        self.m = mem
        self.mode = mode
        self.places = places
        self.cpu = cpu65.CPU(mem)
        self.cpu.sp = 0xF0
        self.pads = list(pads)
        self.draws, self.resets = [], 0  # 그리기 기록(그린 줄 · 팔레트 · BAT) · 타일 되돌리기 횟수
        self.given, self.sounds, self.exits = [], [], 0
        self.full = full
        orig = self.cpu.step
        c = self.cpu

        def step():
            pc = c.pc
            if mem[pc] in (
                0x62,
                0xC2,
                0x82,
            ):  # CLA · CLY · CLX(HuC6280 — 시뮬레이터에 없다, 플래그 안 건드림)
                setattr(c, {0x62: "a", 0xC2: "y", 0x82: "x"}[mem[pc]], 0)
                c.pc += 1
                return None
            if pc == L.WAIT:
                mem[L.PAD] = self.pads.pop(0) if self.pads else 0x02  # 다 쓰면 II(닫기)
            elif pc == L.TILE_RESET:
                self.resets += 1
                mem[L.TILE_NO], mem[L.TILE_NO + 1] = 0xD8, 0x05  # 타일 번호 0x05D8 에서 시작
            elif pc == L.DRAW:
                src = mem[0x10] | mem[0x11] << 8
                bat = mem[0x12] | mem[0x13] << 8
                tile = mem[L.TILE_NO] | mem[L.TILE_NO + 1] << 8
                self.draws.append((mem[L.ROW], mem[0x8A], bat, bytes(mem[src : src + 15]), tile))
                for ci in range(
                    11
                ):  # 글자 여섯 칸은 타일 번호가 차례로 늘고(칸당 2, 둘째 줄 +1) 나머지 다섯은 빈 칸(`$9240`)
                    for tr in range(2):
                        w = (0x8000 | (tile + 2 * ci + tr)) if ci < 6 else 0x9240
                        self.cpu.vram[(bat + 0x40 * tr + ci) & 0x7FFF] = w
                nt = tile + 12  # 글자 타일 열둘이 소비된다
                mem[L.TILE_NO], mem[L.TILE_NO + 1] = nt & 0xFF, nt >> 8
            elif pc == L.SOUND:
                self.sounds.append(c.a)
            elif pc == L.FAR:
                lo = c.pull()
                hi = c.pull()
                a0 = ((hi << 8) | lo) + 1
                al, ah = mem[a0 + 1], mem[a0 + 2]
                addr = al | ah << 8
                if addr == NAME_CONV:
                    n = mem[0xF8]
                    mem[DI.BUF : DI.BUF + 15] = b"\x20" * 12 + bytes([0xF1, n]) + b"\x06"
                elif addr == BUILD_ADDR:
                    mem[L.PLACE_ARR : L.PLACE_ARR + len(self.places)] = bytes(self.places)
                    mem[L.PLACE_N] = len(self.places)
                elif addr == L.PLACE_NAME:
                    n = mem[0xF8]
                    mem[L.PLACE_BUF : L.PLACE_BUF + 14] = (
                        b"\x81\x40" + bytes([0xF1, n]) + b"\x06\x00" + b"\x00" * 8
                    )
                elif addr == FULLCHK:
                    c.c = int(self.full)
                elif addr == ADD:
                    self.given.append(mem[0xF8])
                elif addr == DBGDRAW:
                    self.exits += 1
                c.pc = a0 + 3
                return None
            return orig()

        c.step = step

    def run(self):
        self.cpu.run(self.entry if self.mode == "i" else self.entry_w, ret=0xFFFF)
        return self


class DecodeTest(unittest.TestCase):
    def test_decodes_and_branches(self):
        """연속 디코드(먼 호출 `JSR $4FD8` 뒤 인자 3B 는 건너뛴다) — 분기 목표는 전부 명령 시작이어야 한다. 데이터(공백 줄 · 제목 · 정렬 코드) 앞까지만 본다."""
        org, b, _e, _w = blob()
        labels = L.code(org).labels
        end = labels["BLANK"] - org
        starts, branches = set(), []
        i = 0
        sizes = {
            "imp": 0,
            "imm": 1,
            "zp": 1,
            "zpx": 1,
            "zpy": 1,
            "abs": 2,
            "abx": 2,
            "aby": 2,
            "ind": 2,
            "ain": 2,
            "inx": 1,
            "iny": 1,
            "rel": 1,
            "zpi": 1,
            "bbr": 2,
        }
        while i < end:
            starts.add(org + i)
            mn, mode = D.ops[b[i]]
            n = sizes[mode]
            if mn == "JSR" and b[i + 1] | b[i + 2] << 8 == L.FAR:
                n += 3
            if mode == "rel":
                t = org + i + 2 + (b[i + 1] - 256 if b[i + 1] > 127 else b[i + 1])
                branches.append((org + i, t))
            i += 1 + n
        self.assertEqual(i, end)
        for at, t in branches:
            self.assertIn(t, starts, f"{at:04X} → {t:04X}")
        self.assertLessEqual(org + len(b), 0x7B00)
        self.assertGreaterEqual(org, 0x7450)  # 워프 핸들러 뒤

    def test_first_screen_and_navigation(self):
        """제목 아래 7줄 한 쪽 — 쪽 맨 앞(1·8·15…)부터, 좌우 ±7(끝에 붙음), 위·아래 ±1(돌아 감김)."""
        up, down, left, right = 0x10, 0x40, 0x80, 0x20
        s = Sim([]).run()
        rows = [
            d for d in s.draws[1:] if d[1] == 7
        ]  # 보통(흰색 7) 그리기 일곱 번(제목 뒤) — 줄마다 하늘색(5) 그리기가 하나씩 더 있다
        self.assertEqual(s.draws[0][2], L.TITLE_BAT)
        self.assertEqual(s.draws[0][1], 6)  # 제목은 노란색(6)
        self.assertEqual([r[0] for r in rows], list(range(7)))
        self.assertEqual([r[2] for r in rows], [self.bat(i) for i in range(7)])
        self.assertEqual(sum(1 for d in s.draws if d[1] == 5), 7)  # 하늘색 한 벌씩
        self.assertEqual(s.exits, 1)
        self.assertEqual(s.m[L.TOP], 0)
        s = Sim([down] * 7).run()
        self.assertEqual(s.m[L.POS], 7)
        self.assertEqual(s.m[L.TOP], 7)
        s = Sim([down] * 6).run()
        self.assertEqual((s.m[L.POS], s.m[L.TOP]), (6, 0))
        s = Sim([up]).run()  # 처음에서 위 → 마지막(115)
        self.assertEqual((s.m[L.POS], s.m[L.TOP]), (115, 112))
        s = Sim([right]).run()
        self.assertEqual(s.m[L.POS], 7)
        s = Sim([left]).run()
        self.assertEqual(s.m[L.POS], 0)
        s = Sim([right] * 16).run()
        self.assertEqual(s.m[L.POS], 112)
        s = Sim([right] * 17).run()
        self.assertEqual(s.m[L.POS], 115)
        s = Sim([right] * 17 + [left]).run()
        self.assertEqual(s.m[L.POS], 108)
        s = Sim([up, down]).run()
        self.assertEqual(s.m[L.POS], 0)

    @staticmethod
    def bat(i):
        base = L.BAT_LIST
        return base + 0x80 * i

    def test_up_down_only_flips_bat(self):
        """같은 쪽 안 위·아래는 목록을 다시 그리지 않는다 — 그리기 0번 · 타일 되돌리기 없이 두 줄의 BAT 글자 칸만 한 번에 바꾼다(옛 줄 → 보통 타일 · 새 줄 → 하늘색 타일).
        쪽이 넘어가면 전체를 다시 그린다. 효과음: 이동 0x14 · 닫기 0x16."""
        down = 0x40
        s0 = Sim([]).run()
        s = Sim([down]).run()
        self.assertEqual(s.resets, 1)  # 처음 그리기 한 번뿐
        self.assertEqual(len(s.draws), len(s0.draws))  # 다시 그리지 않았다
        # 처음: 0번 줄이 하늘색 타일(TILE 뒤쪽) · 1번 줄은 보통 타일(앞쪽) — 한 번 내리면 반대
        row0_first = s0.cpu.vram[L.BAT_LIST]
        row1_first = s0.cpu.vram[L.BAT_LIST + 0x80]
        row0_after = s.cpu.vram[L.BAT_LIST]
        row1_after = s.cpu.vram[L.BAT_LIST + 0x80]
        self.assertEqual(
            row0_first - row0_after, 12
        )  # 하늘색 → 보통: 타일 번호가 줄 타일 수(12)만큼 앞으로
        self.assertEqual(row1_after - row1_first, 12)  # 보통 → 하늘색
        self.assertEqual(
            s.cpu.vram[L.BAT_LIST + 6] if False else s.cpu.vram[L.BAT_LIST + 8], 0x9240
        )  # 빈 칸은 그대로
        self.assertEqual(s.sounds, [L.CUE_MOVE, L.CUE_CANCEL])
        s = Sim([down] * 7).run()  # 쪽 넘김 — 다시 그린다
        self.assertEqual(s.resets, 2)

    def test_give_and_full(self):
        i_btn = 0x01
        s = Sim([0x40, 0x40, i_btn]).run()  # 위치 2 = 3번 지급
        self.assertEqual(s.given, [3])
        self.assertEqual(s.sounds.count(0x23), 1)
        s = Sim([0x40, i_btn], full=True).run()
        self.assertEqual(s.given, [])
        self.assertNotIn(0x23, s.sounds)

    def test_warp_list(self):
        """W — 빌더가 모은 장소 번호를 고르면 C=0 · `$F8`=장소 번호, 취소는 C=1. 이름은 왼쪽으로 당겨 공백을 채운다."""
        s = Sim([0x40, 0x40, 0x01], mode="w").run()
        self.assertEqual((s.cpu.c, s.m[0xF8]), (0, 3))
        s = Sim([], mode="w").run()  # II = 취소
        self.assertEqual(s.cpu.c, 1)
        self.assertEqual(s.exits, 0)  # 다시 그리기는 호출부(`wmain`)가 한다
        s = Sim([0x10, 0x01], mode="w").run()  # 처음에서 위 → 마지막
        self.assertEqual(s.m[0xF8], 48)
        names = Sim([], mode="w").run().draws[1:5]
        self.assertEqual(
            names[0][3][:4], bytes([0xF1, 1, 0x81, 0x40])
        )  # 앞 `81 40` 을 뗐다 — 글자부터 · 남은 칸은 `81 40`
        s = Sim([], mode="w", places=()).run()  # 갈 곳이 없으면 곧 취소
        self.assertEqual(s.cpu.c, 1)

    def test_stubs(self):
        """뱅크 0x6F 꼬리 스텁 — W 모드 암호가 있으면 창 열기(`$5CD5`)를 건너뛰고 우리 목록으로, 없으면 원래 날개 경로(`$5CD5` · `$855B`)로 간다."""
        _o, _b, _e, entry_w = blob()
        code, list_at, open_at = L.stub_code(entry_w)
        for keyed in (True, False):
            for name, at, orig in (
                ("open", open_at, L.WIN_OPEN_ORIG),
                ("list", list_at, L.LIST_BUILDER),
            ):
                mem = bytearray(0x10000)
                mem[L.STUB_AT : L.STUB_AT + len(code)] = code
                mem[orig] = 0x60
                mem[L.FAR] = 0x60  # 먼 호출은 가짜 — 인자 3B 를 건너뛰는 건 이 시험 밖
                if keyed:
                    mem[L.W.WMODE], mem[L.W.WMODE + 1] = L.W.WMODE_KEY
                cpu = cpu65.CPU(mem)
                cpu.sp = 0xF0
                seen = []
                step0 = cpu.step

                def step(cpu=cpu, seen=seen, step0=step0):
                    seen.append(cpu.pc)
                    return step0()

                cpu.step = step
                if (
                    name == "list" and keyed
                ):  # 먼 호출 인자 3B 를 건너뛰게 FAR 자리에서 스택의 돌아갈 주소만 3 올린다

                    def step2(cpu=cpu, seen=seen, step0=step0):
                        seen.append(cpu.pc)
                        if cpu.pc == L.FAR:
                            lo, hi = cpu.pull(), cpu.pull()
                            ret = ((hi << 8) | lo) + 1 + 3
                            cpu.push((ret - 1) >> 8)
                            cpu.push((ret - 1) & 0xFF)
                        return step0()

                    cpu.step = step2
                cpu.run(at, ret=0xFFFF)
                self.assertEqual(orig in seen, not keyed, (name, keyed))

    def test_patches(self):
        ps = L.patches()
        self.assertEqual(ps[-1][0], "debug item list entry")
        self.assertEqual(ps[-1][3], (0x629D).to_bytes(2, "little"))
        self.assertTrue(all(len(p[3]) == len(p[4]) for p in ps))
        stub = [p for p in ps if p[0] == "debug W list stub site"]
        self.assertEqual(stub[0][4][0], 0x20)


if __name__ == "__main__":
    unittest.main()
