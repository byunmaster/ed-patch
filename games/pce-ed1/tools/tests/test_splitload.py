"""씬 열기 짝 교체 루틴(`splitload.check`)의 논리를 작은 HuC6280 흉내로 돈다 — 한쪽 · 반대쪽 · 왕복 · 두 쌍 · 어느 쪽에도 없는 id.

흉내가 아는 옵코드는 이 루틴이 쓰는 것뿐이다(모르면 죽는다). 로더(`$5597` 내림 · `$56D8` 올림)는 가짜로 갈아 끼워
「내리고 → 올림」 순서와 동시 점유 없음을 직접 센다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook
import splitload

REV = {v: k for k, v in hook.OPS.items()}
LEN = {"imp": 1, "imm": 2, "zp": 2, "izp": 2, "izpy": 2, "rel": 2, "abs": 3, "absx": 3, "absy": 3, "tma": 2, "tam": 2}


class Cpu:
    def __init__(self, containers, partner):
        """containers = {rel: [id…]} · partner = {rel: (짝 rel, 짝 섹터수)} — 나눈 컨테이너는 디렉터리 끝에 가짜 항목을 갖는다."""
        self.mem = bytearray(0x10000)
        self.mem[0x4B] = 0x80  # 곡 명령 — 기본은 멈춤(곡 다시 걸기 없음). 곡 시험은 아래 `test_music_restart_*`
        code = splitload._asm().bytes()
        self.mem[splitload.ORG : splitload.ORG + len(code)] = code
        lay = splitload.layout()
        self.partner = partner
        self.flag = lay["flag"]
        self.containers = containers
        self.log = []  # ("release", rel) · ("load", rel)
        self.loaded: dict[int, int] = {}  # 핸들 → rel
        self.next_handle = 0
        self.slot_of = {}  # 핸들 → 칸
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.stack = []

    def load_container(self, rel, handle=None):
        h = self.next_handle if handle is None else handle
        self.next_handle = max(self.next_handle, h + 1)
        slot = h  # 핸들 = 칸 번호로 단순화
        self.loaded[h] = rel
        self.mem[0x378D + h] = slot
        self.mem[0x376C + slot] = (rel) & 0xFF
        self.mem[0x377C + slot] = rel >> 8
        self.mem[0x61] = h
        self.dir_to_mem(rel)
        return h

    def dir_to_mem(self, rel):
        ids = self.containers[rel]
        base = 0xA000
        d = bytearray()
        for i in ids:
            d += bytes([i, 0, 0, 0, 0])
        if rel in self.partner:
            prel, secs = self.partner[rel]
            d += bytes([0xFE, (prel - 34) & 0xFF, (prel - 34) >> 8, secs, 0])
        d.append(0xFF)
        self.mem[base : base + len(d)] = d
        self.mem[0x12], self.mem[0x13] = 0, 0xA0

    def setflags(self, v):
        self.z = int(v & 0xFF == 0)
        self.n = v >> 7 & 1

    def run(self, ident):
        self.mem[0xC009] = ident
        self.mem[0x12], self.mem[0x13] = 0, 0xA0
        pc = splitload._asm().labels["check"]  # 입구는 디렉터리 훑기(10-31 배치 바꿈 — 짝 찾기가 앞에 있다)
        steps = 0
        while True:
            steps += 1
            assert steps < 5000, "무한 루프"
            op = self.mem[pc]
            if op == 0x73:  # TII 원본, 목적지, 길이
                src, dst, ln = (self.mem[pc + k] | self.mem[pc + k + 1] << 8 for k in (1, 3, 5))
                for k in range(ln):
                    self.mem[dst + k] = self.mem[src + k]
                pc += 7
                continue
            mn, mode = REV[op]
            arg = None
            if LEN[mode] == 2:
                arg = self.mem[pc + 1]
            elif LEN[mode] == 3:
                arg = self.mem[pc + 1] | self.mem[pc + 2] << 8
            nxt = pc + LEN[mode]
            m = self.mem
            if mn == "LDA":
                if mode == "imm":
                    self.a = arg
                elif mode == "zp":
                    self.a = m[arg]
                elif mode == "abs":
                    self.a = m[arg]
                elif mode == "izp":
                    self.a = m[m[arg] | m[arg + 1] << 8]
                elif mode == "izpy":
                    self.a = m[(m[arg] | m[arg + 1] << 8) + self.y]
                elif mode == "absx":
                    self.a = m[arg + self.x]
                elif mode == "absy":
                    self.a = m[arg + self.y]
                else:
                    raise AssertionError((mn, mode))
                self.setflags(self.a)
            elif mn == "LDY":
                self.y = m[arg] if mode == "zp" else arg
                self.setflags(self.y)
            elif mn == "DEY":
                self.y = (self.y - 1) & 0xFF
                self.setflags(self.y)
            elif mn == "PLY":
                self.y = self.stack.pop()
                self.setflags(self.y)
            elif mn == "SBC":
                v = arg if mode == "imm" else m[arg]
                t = self.a - v - (1 - self.c)
                self.c = int(t >= 0)
                self.a = t & 0xFF
                self.setflags(self.a)
            elif mn == "INY":
                self.y = (self.y + 1) & 0xFF
                self.setflags(self.y)
            elif mn == "CPY":
                v = arg if mode == "imm" else m[arg]
                self.c = int(self.y >= v)
                self.setflags((self.y - v) & 0xFF)
            elif mn == "CLY":
                self.y = 0
            elif mn in ("PHP", "SEI", "PLP"):
                pass
            elif mn == "STA":
                m[arg + (self.x if mode == "absx" else 0)] = self.a
            elif mn == "STY":
                m[arg] = self.y
            elif mn == "STZ":
                m[arg] = 0
            elif mn == "CMP":
                v = arg if mode == "imm" else m[arg + (self.x if mode == "absx" else 0)]
                self.c = int(self.a >= v)
                self.setflags((self.a - v) & 0xFF)
            elif mn == "ADC":
                t = self.a + arg + self.c
                self.c = t >> 8
                self.a = t & 0xFF
                self.setflags(self.a)
            elif mn == "CLC":
                self.c = 0
            elif mn == "SEC":
                self.c = 1
            elif mn == "INC":
                m[arg] = (m[arg] + 1) & 0xFF
            elif mn in ("BEQ", "BNE", "BCC", "BCS", "BRA"):
                off = arg - 256 if arg > 127 else arg
                take = {"BEQ": self.z, "BNE": not self.z, "BCC": not self.c, "BCS": self.c, "BRA": 1}[mn]
                if take:
                    nxt = nxt + off
            elif mn == "TAY":
                self.y = self.a
                self.setflags(self.a)
            elif mn == "TAX":
                self.x = self.a
                self.setflags(self.a)
            elif mn == "TXA":
                self.a = self.x
                self.setflags(self.a)
            elif mn == "TYA":
                self.a = self.y
                self.setflags(self.a)
            elif mn == "CLX":
                self.x = 0
            elif mn == "PHA":
                self.stack.append(self.a)
            elif mn == "PLA":
                self.a = self.stack.pop()
                self.setflags(self.a)
            elif mn == "TAM":
                pass  # MPR 은 흉내 안 낸다(번호만 본다)
            elif mn == "JSR":
                if arg == 0x5597:  # 내림
                    h = self.a
                    self.log.append(("release", self.loaded.pop(h)))
                elif arg == 0x56D8:  # 올림(X Y = rec, A = 섹터수)
                    rel = (self.x | self.y << 8) + 34
                    assert not self.loaded, "두 컨테이너가 동시에 올라간다"
                    self.log.append(("load", rel))
                    h = self.load_container(rel)
                    self.y = h
                    self.c = 0
                elif arg == 0x4FD8:  # 먼 호출(곡 다시 걸기: 뱅크 0x69 `$6856`) — 뒤 인라인 3B 를 건너뛴다
                    self.log.append(("music",))
                    nxt += 3
                else:
                    raise AssertionError(hex(arg))
            elif mn == "JMP":
                nxt = arg
            elif mn == "RTS":
                return self.c
            else:
                raise AssertionError((mn, mode))
            pc = nxt


class SplitLoadTest(unittest.TestCase):
    def setUp(self):
        self.partner = {9812: (9823, 11), 9823: (9812, 11), 9845: (9857, 11), 9857: (9845, 12), 9786: (9797, 11), 9797: (9786, 11), 9900: (9910, 14), 9910: (9900, 8), 9920: (9934, 14), 9934: (9920, 14),
                        1252: (10000, 7), 10000: (1252, 16)}  # 제자리 쪽(1252, rec 상위 ≠ 0x26)과 풀 쪽 — 키·rec 상위 바이트 제약이 없다
        self.cont = {
            9812: [0, 1, 4, 72, 73],
            9823: [0, 1, 4, 80, 81],
            9845: [0, 1, 4, 95, 96],
            9857: [0, 1, 4, 102, 106],
            9786: [0, 1, 4, 6, 7],
            9797: [0, 1, 4, 31, 32],
            9900: [0, 1, 4, 200],
            9910: [0, 1, 4, 201],
            9920: [0, 1, 4, 210],
            9934: [0, 1, 4, 211],
            1252: [0, 1, 4, 6, 32],
            10000: [0, 1, 4, 41],
        }

    def cpu(self, start):
        c = Cpu(self.cont, self.partner)
        c.load_container(start)
        return c

    def test_found_in_current(self):
        c = self.cpu(9812)
        self.assertEqual(c.run(73), 0)
        self.assertEqual(c.log, [])
        self.assertEqual(c.run(0), 0)

    def test_switch_both_directions_both_pairs(self):
        for a, b, ia, ib in ((9812, 9823, 72, 81), (9845, 9857, 96, 106), (9786, 9797, 6, 32), (9797, 9786, 31, 7)):
            c = self.cpu(a)
            self.assertEqual(c.run(ib), 0)
            self.assertEqual(c.log, [("release", a), ("load", b)])
            self.assertEqual(c.mem[c.flag], 0)  # 찾았으니 표지를 지운다
            self.assertEqual(c.run(ia), 0)  # 왕복
            self.assertEqual(c.log[2:], [("release", b), ("load", a)])
            self.assertEqual(c.run(ib), 0)
            self.assertEqual(len(c.log), 6)

    def test_missing_id_tries_other_side_once_then_fails(self):
        c = self.cpu(9812)
        self.assertEqual(c.run(200), 1)  # C=1 = 실패(사이트가 제자리에서 돈다)
        self.assertEqual(c.log, [("release", 9812), ("load", 9823)])  # 반대쪽을 한 번만 찾았다

    def test_music_restart_only_when_track_command_pending(self):
        """🔴 11-11 짝을 읽으면 CD-DA 가 멈춘다 — 곡 명령 `$4B`<`$10` · 재생 모드 `$4C`=0 이면 곡 루틴을 다시 부른다(원판 순서: 구역 전환이 곡을 건 뒤 씬 열기)."""
        c = self.cpu(9812)
        c.mem[0x4B], c.mem[0x4C] = 0x0A, 0
        c.run(200)
        self.assertEqual(c.log, [("release", 9812), ("load", 9823), ("music",)])
        c = self.cpu(9812)
        c.mem[0x4B], c.mem[0x4C] = 0x0A, 1  # 재생 모드가 아니다
        c.run(200)
        self.assertEqual(c.log, [("release", 9812), ("load", 9823)])
        c = self.cpu(9812)
        c.mem[0x4B], c.mem[0x4C] = 0x81, 0  # 멈춤·페이드 명령
        c.run(200)
        self.assertEqual(c.log, [("release", 9812), ("load", 9823)])

    def test_unpaired_container_fails_without_touching_cache(self):
        c = Cpu({1300: [0, 1, 4, 7]}, {})
        c.load_container(1300)
        self.assertEqual(c.run(99), 1)
        self.assertEqual(c.log, [])

    def test_tick_install_once_on_found(self):
        c = self.cpu(9812)
        c.mem[0x4155] = 0xA5
        self.assertEqual(c.run(73), 0)
        self.assertEqual((c.mem[0x4155], c.mem[0x4156]), (0x00, 0x24))  # JSR $2400
        c.mem[0x4156] = 0x77
        self.assertEqual(c.run(72), 0)
        self.assertEqual(c.mem[0x4156], 0x77)  # 이미 바꿨으면(하위 ≠ A5) 안 건드린다

    def test_five_pairs_both_ways_and_unrestricted_rel(self):
        """다섯 쌍 양방향 전부 + 제자리 쪽(rel 1252 — 상위 바이트 0x04)·풀 쪽(rel 10000 — 상위 0x27)도 짝 표 제약 없이 오간다."""
        for a, b, ib in ((9900, 9910, 201), (9910, 9900, 200), (9920, 9934, 211), (9934, 9920, 210), (1252, 10000, 41), (10000, 1252, 32)):
            c = self.cpu(a)
            self.assertEqual(c.run(ib), 0)
            self.assertEqual(c.log, [("release", a), ("load", b)])

    def test_partner_entry_across_page_boundary(self):
        """FF 가 페이지 머리 가까이(하위 < 5)에 있어도 FF − 5 의 빌림이 상위로 올라간다 — 51 블록 + 가짜 항목 = FF 가 +0x104."""
        ids = list(range(1, 52))
        c = Cpu({20000: ids, 20100: [0, 1]}, {20000: (20100, 3), 20100: (20000, 16)})
        c.load_container(20000)
        self.assertEqual(c.run(51), 0)
        self.assertEqual(c.log, [])
        self.assertEqual(c.run(0), 0)  # 없는 id → 짝(FF 가 +0x104 라 빌림이 상위로 올라가야 가짜 항목을 읽는다)
        self.assertEqual(c.log, [("release", 20000), ("load", 20100)])
        c2 = Cpu({20000: ids[:-1] + [77], 20100: [0, 1, 99]}, {20000: (20100, 3), 20100: (20000, 16)})
        c2.load_container(20000)
        self.assertEqual(c2.run(99), 0)
        self.assertEqual(c2.log, [("release", 20000), ("load", 20100)])

    def test_site_and_layout(self):
        old, new = splitload.site_patch()
        self.assertEqual(len(old), len(new))
        self.assertEqual(old[0], 0xB2)
        self.assertLessEqual(splitload.layout()["len"], splitload.ROOM)


if __name__ == "__main__":
    unittest.main()
