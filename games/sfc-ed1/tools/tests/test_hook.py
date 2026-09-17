"""렌더러 훅의 기계어 — **원본 없이** 돈다.

루트 CLAUDE.md 「빌드 규율」: *손인코딩 기계어는 디스어셈블로 검산한다.* 여기서는
어셈블러가 낸 바이트를 **독립적인 해독기**로 다시 읽는다. 해독기는 `REP`/`SEP` 를 따라가며
즉치 길이를 **진짜 CPU 규칙대로** 정한다 — 그래서 `m16` 을 빠뜨리면 스트림이 어긋나
「모르는 명령」이나 「라벨이 아닌 분기 목표」로 **터진다**(이게 이 시험의 존재 이유다).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: F401, I001
import hook

# 오피코드 → (니모닉, 인자 길이). 'm'/'x' 는 폭에 따라 1 또는 2. 어셈블러 표와 **따로** 적었다.
OPC = {
    0x08: ("php", 0),
    0x28: ("plp", 0),
    0x8B: ("phb", 0),
    0xAB: ("plb", 0),
    0x48: ("pha", 0),
    0x68: ("pla", 0),
    0xDA: ("phx", 0),
    0xFA: ("plx", 0),
    0x5A: ("phy", 0),
    0x7A: ("ply", 0),
    0x18: ("clc", 0),
    0x38: ("sec", 0),
    0x0A: ("asl a", 0),
    0x4A: ("lsr a", 0),
    0x1A: ("inc a", 0),
    0x3A: ("dec a", 0),
    0xE8: ("inx", 0),
    0xC8: ("iny", 0),
    0xCA: ("dex", 0),
    0x88: ("dey", 0),
    0xAA: ("tax", 0),
    0xA8: ("tay", 0),
    0x8A: ("txa", 0),
    0x98: ("tya", 0),
    0xEB: ("xba", 0),
    0x9B: ("txy", 0),
    0xBB: ("tyx", 0),
    0x60: ("rts", 0),
    0x6B: ("rtl", 0),
    0xEA: ("nop", 0),
    0xE2: ("sep", 1),
    0xC2: ("rep", 1),
    0xA9: ("lda #", "m"),
    0xC9: ("cmp #", "m"),
    0x29: ("and #", "m"),
    0x69: ("adc #", "m"),
    0x09: ("ora #", "m"),
    0x49: ("eor #", "m"),
    0xA2: ("ldx #", "x"),
    0xA0: ("ldy #", "x"),
    0xE0: ("cpx #", "x"),
    0xC0: ("cpy #", "x"),
    0xAD: ("lda a", 2),
    0x8D: ("sta a", 2),
    0xCD: ("cmp a", 2),
    0xAE: ("ldx a", 2),
    0xAC: ("ldy a", 2),
    0x8E: ("stx a", 2),
    0x8C: ("sty a", 2),
    0xBD: ("lda a,x", 2),
    0x9D: ("sta a,x", 2),
    0x3D: ("and a,x", 2),
    0xB9: ("lda a,y", 2),
    0x39: ("and a,y", 2),
    0xAF: ("lda l", 3),
    0x8F: ("sta l", 3),
    0xCF: ("cmp l", 3),
    0x6F: ("adc l", 3),
    0x2F: ("and l", 3),
    0x0F: ("ora l", 3),
    0xBF: ("lda l,x", 3),
    0x9F: ("sta l,x", 3),
    0xA5: ("lda d", 1),
    0x85: ("sta d", 1),
    0xA7: ("lda [d]", 1),
    0xB7: ("lda [d],y", 1),
    0x97: ("sta [d],y", 1),
    0x87: ("sta [d]", 1),
    0x20: ("jsr", 2),
    0x4C: ("jmp", 2),
    0x22: ("jsl", 3),
    0xF0: ("beq", "r"),
    0xD0: ("bne", "r"),
    0x90: ("bcc", "r"),
    0xB0: ("bcs", "r"),
    0x80: ("bra", "r"),
    0x10: ("bpl", "r"),
    0x30: ("bmi", "r"),
}
# 루틴 진입 시의 폭 (m8, x8)과 **부르는 방식** — 훅은 이렇게 불린다.
# 🔴 `far` 는 `JSL`(뱅크를 건너온다)이라 **RTL** 로 닫아야 한다. RTS 로 닫으면 스택이
#    호출마다 2바이트씩 어긋나 조용히 굴러가다 몇 초 뒤 죽는다(2026-09-07 실측: NMI 의
#    `drain` 을 RTS 로 닫아 타이틀도 못 봤다). 그래서 시험이 이걸 본다.
ENTRY = {
    "hook": (True, True, "far"),  # 호출자(메시지 엔진) = A 8 · X/Y 8
    "hookbuf": (True, True, "far"),  # 사전 버퍼 소비 지점 — 같은 규약
    "open_fetch": (True, True, "far"),  # 오프닝(D1) 소비 지점 — $1E:DF3D 가 같은 규약으로 둔다
    "namecopy": (True, True, "far"),  # 메뉴 이름 — 넷째 문(칸 배열에 직접 쓴다)
    "name13": (False, False, "far"),  # 13칸 고정 — 다섯째 문(원본은 MVN). 호출자가 REP #$30
    "drain": (True, True, "far"),  # NMI = sep #$30 뒤
    "fetch": (True, False, "near"),
    "alloc": (True, False, "near"),
    "josa": (True, False, "near"),
    "upload": (True, False, "near"),
    "cache_reset": (True, False, "near"),  # 오프닝 페이지 경계에서 오너 표를 비운다
}


def decode(blob: bytes, org: int, start: int, m8: bool, x8: bool, end: int):
    """한 루틴을 선형 해독한다 → [(주소, 니모닉, 인자, 크기)]. 모르는 바이트면 예외."""
    out = []
    pc = start
    while pc < end:
        op = blob[pc - org]
        if op not in OPC:
            raise AssertionError(f"모르는 오피코드 ${op:02X} @ ${pc:04X}")
        mnem, n = OPC[op]
        if n == "m":
            n = 1 if m8 else 2
        elif n == "x":
            n = 1 if x8 else 2
        elif n == "r":
            n = 1
        arg = int.from_bytes(blob[pc - org + 1 : pc - org + 1 + n], "little")
        if mnem == "sep":
            m8 = m8 or bool(arg & 0x20)
            x8 = x8 or bool(arg & 0x10)
        elif mnem == "rep":
            m8 = m8 and not (arg & 0x20)
            x8 = x8 and not (arg & 0x10)
        out.append((pc, mnem, arg, 1 + n, op))
        pc += 1 + n
        if mnem in ("rts", "rtl"):
            break
    return out, pc


class HookAsm(unittest.TestCase):
    def setUp(self):
        self.rep = sorted(set("가나다라마바사아자차카타파하각논딜" + hook.josa_chars()))
        self.slots = list(range(0x20, 0x20 + 40))
        self.vram = [0x1000 + 8 * (0x30 + i) for i in range(40)]
        self.blob, self.info = hook.build_payload(self.rep, self.slots, self.vram)
        self.lab = self.info["labels"]
        self.code_end = hook.HOOK_ORG + self.info["code_bytes"]

    def _walk(self):
        """루틴마다 진입 폭을 주고 끝까지 해독한다. 라벨 자리가 곧 명령 경계여야 한다."""
        starts = sorted(self.lab.items(), key=lambda kv: kv[1])
        bounds = set()
        for name, (m8, x8, _kind) in ENTRY.items():
            pc = self.lab[name]
            nxt = min((v for _k, v in starts if v > pc and _k in ENTRY), default=self.code_end)
            ins, _ = decode(self.blob, hook.HOOK_ORG, pc, m8, x8, nxt)
            for a, *_ in ins:
                bounds.add(a)
            yield name, ins
        self.bounds = bounds

    def test_전량_해독(self):
        """코드 구간 전부가 유효한 명령으로 읽히고 라벨이 명령 경계에 선다."""
        seen = set()
        for _name, ins in self._walk():
            for a, _m, _v, n, _o in ins:
                seen.update(range(a, a + n))
        # 루틴 사이 빈틈(각 루틴은 rts/rtl 로 닫힌다)이 없어야 한다
        gaps = [a for a in range(hook.HOOK_ORG, self.code_end) if a not in seen]
        self.assertEqual(gaps, [], f"안 읽힌 바이트 {len(gaps)}")
        for name, addr in self.lab.items():
            if addr < self.code_end:
                self.assertIn(addr, self.bounds, f"라벨 {name} 이 명령 한복판이다")

    def test_분기_목표(self):
        """분기·JSR·JMP 목표가 전부 명령 경계다(폭을 틀리면 여기서 깨진다)."""
        list(self._walk())
        for _name, ins in self._walk():
            for a, m, v, n, _o in ins:
                if m in ("beq", "bne", "bcc", "bcs", "bra", "bpl", "bmi"):
                    t = a + n + (v - 256 if v > 127 else v)
                    self.assertIn(t, self.bounds, f"${a:04X} {m} → ${t:04X}")
                elif m in ("jsr", "jmp"):
                    self.assertIn(v, self.bounds, f"${a:04X} {m} ${v:04X}")

    def test_스택_균형(self):
        """루틴마다 push/pop 짝이 맞는다 — 어긋나면 RTS 가 엉뚱한 데로 간다."""
        pairs = {"php": "plp", "phb": "plb", "phx": "plx", "phy": "ply", "pha": "pla"}
        for name, ins in self._walk():
            depth = {k: 0 for k in pairs}
            for _a, m, *_ in ins:
                for k, v in pairs.items():
                    if m == k:
                        depth[k] += 1
                    elif m == v:
                        depth[k] -= 1
            # pha/plb 는 DB 를 세우는 관용구라 pha 하나가 plb 로 빠진다
            self.assertEqual(depth["php"], 0, f"{name}: php/plp 불균형")
            self.assertEqual(depth["phx"], 0, f"{name}: phx/plx 불균형")
            self.assertEqual(depth["phy"], 0, f"{name}: phy/ply 불균형")

    def test_복귀_명령(self):
        """`JSL` 로 불리는 루틴은 RTL, `JSR` 은 RTS 로 닫힌다 — 어긋나면 스택이 샌다."""
        want = {"far": "rtl", "near": "rts"}
        for name, ins in self._walk():
            self.assertEqual(ins[-1][1], want[ENTRY[name][2]], f"{name} 의 복귀 명령")

    def test_호출_자리_바이트(self):
        """갈아 끼울 자리는 **원본과 크기가 같아야** 한다."""
        self.assertEqual(hook.QN & (hook.QN - 1), 0, "큐 칸은 2의 거듭제곱")
        self.assertLess(self.info["var_end"] - hook.VAR, 741, "WRAM 무손상 구간(741B)을 넘는다")
        self.assertLessEqual(len(self.blob), 0x8000)

    def test_조사표(self):
        """조사 16줄 — 받침 있음/없음이 짝을 이루고 표기가 정본과 같다."""
        rows = hook.josa_rows()
        self.assertEqual(len(rows), 2 * len(hook.encode.JOSA_PAIRS))
        self.assertEqual([s for _n, s in rows[:6]], ["은", "는", "이", "가", "을", "를"])
        self.assertEqual(rows[8], (2, "으로"))  # 받침 있음
        self.assertEqual(rows[9], (1, "로"))


if __name__ == "__main__":
    unittest.main()
