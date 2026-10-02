#!/usr/bin/env python3
"""런타임 줄넘김(prewrap) 조판 검사 — **빌드 이미지의 prewrap 을 통째로 실행**해 ③·④ 를 센다.

왜: 런타임 조립 문장(시전자·대상·주문/도구 이름 + 조각)은 빌드 조판(krwrap)을 못 탄다 —
엔진 prewrap 이 29열에서 끊는다. 원판은 글자 단위라 줄을 딱 채우면 **다음 글자 앞**에서
끊어 ③ 줄머리 공백(「레스를 / ␣외웠다」)·④ 낱말 절단(「외 / 웠다」)이 났다(마스터 09-27).
`patch_hang_punct` 의 ③·④ 스텁이 고친다 — 이 도구는 그 결과를 **실행으로** 잰다(모델이 아니다).

방법: 원본·빌드 EXE 를 메모리로 올리고 prewrap 함수(ED1 0x800ACE18 · ED2 0x800836FC)를 작은
MIPS 인터프리터로 끝까지 돈다(BIOS A0 문자열 함수는 HLE). 조사 병기는 훅과 같은 `fix_buffer`
로 먼저 접는다(훅이 prewrap 앞에서 돈다). 이름은 **가장 긴 것**(ED1 세리오스 · ED2 아트라스),
수치는 4자리, 주문·도구 이름은 전량.

  python3 tools/check_prewrap_rules.py      # 원판 대비 위반 수 — 새 빌드가 0 이어야 한다
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import hangul_map as H
import patch_ed2_sys as PS
import patch_items as PI
import patch_josa_hook as J
from patch_josa_hook import site

PREWRAP_FN = {"ED1": 0x800ACE18, "ED2": 0x800836FC}
LONGEST = {"ED1": "세리오스", "ED2": "아트라스"}
FRAME = 29


def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


class CPU:
    def __init__(self, exe, base=0x80010000):
        self.exe = exe
        self.base = base
        self.mem = {}
        self.r = [0] * 32
        self.hi = self.lo = 0

    def rb(self, a):
        a &= 0xFFFFFFFF
        if a in self.mem:
            return self.mem[a]
        o = a - self.base + 0x800
        if 0x800 <= o < len(self.exe) and a >= self.base:
            return self.exe[o]
        return 0

    def wb(self, a, v):
        self.mem[a & 0xFFFFFFFF] = v & 0xFF

    def rw(self, a):
        return self.rb(a) | self.rb(a + 1) << 8 | self.rb(a + 2) << 16 | self.rb(a + 3) << 24

    def rh(self, a):
        return self.rb(a) | self.rb(a + 1) << 8

    def call(self, pc, regs, max_steps=2_000_000):
        r = self.r = [0] * 32
        for k, v in regs.items():
            r[k] = v & 0xFFFFFFFF
        RA = 0xDEADBEE0
        r[31] = RA
        pending = None
        steps = 0
        while True:
            if pc == RA and pending is None:
                return r
            if pc in (0xA0, 0xB0, 0xC0) and pending is None:
                self.hle(pc, r[9])
                pc = r[31]
                continue
            steps += 1
            if steps > max_steps:
                raise RuntimeError("steps")
            w = self.rw(pc)
            op = w >> 26
            rs = (w >> 21) & 31
            rt = (w >> 16) & 31
            rd = (w >> 11) & 31
            sh = (w >> 6) & 31
            fn = w & 63
            imm = w & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            nxt = pc + 4
            tgt = None
            R = lambda i: r[i] & 0xFFFFFFFF
            if op == 0:
                if fn == 0:
                    v = R(rt) << sh
                elif fn == 2:
                    v = R(rt) >> sh
                elif fn == 3:
                    v = s32(R(rt)) >> sh
                elif fn == 4:
                    v = R(rt) << (R(rs) & 31)
                elif fn == 6:
                    v = R(rt) >> (R(rs) & 31)
                elif fn == 7:
                    v = s32(R(rt)) >> (R(rs) & 31)
                elif fn == 8:
                    tgt = R(rs)
                    v = None
                elif fn == 9:
                    tgt = R(rs)
                    v = None
                    r[rd] = pc + 8
                elif fn in (0x20, 0x21):
                    v = R(rs) + R(rt)
                elif fn in (0x22, 0x23):
                    v = R(rs) - R(rt)
                elif fn == 0x24:
                    v = R(rs) & R(rt)
                elif fn == 0x25:
                    v = R(rs) | R(rt)
                elif fn == 0x26:
                    v = R(rs) ^ R(rt)
                elif fn == 0x27:
                    v = ~(R(rs) | R(rt))
                elif fn == 0x2A:
                    v = int(s32(R(rs)) < s32(R(rt)))
                elif fn == 0x2B:
                    v = int(R(rs) < R(rt))
                elif fn == 0x10:
                    v = self.hi
                elif fn == 0x12:
                    v = self.lo
                elif fn in (0x18, 0x19):
                    p = (s32(R(rs)) * s32(R(rt))) if fn == 0x18 else R(rs) * R(rt)
                    self.lo = p & 0xFFFFFFFF
                    self.hi = (p >> 32) & 0xFFFFFFFF
                    v = None
                elif fn in (0x1A, 0x1B):
                    a_, b_ = (s32(R(rs)), s32(R(rt))) if fn == 0x1A else (R(rs), R(rt))
                    if b_:
                        q = int(a_ / b_)
                        self.lo = q & 0xFFFFFFFF
                        self.hi = (a_ - q * b_) & 0xFFFFFFFF
                    v = None
                else:
                    raise RuntimeError(f"special {fn:#x} @{pc:#x}")
                if v is not None and fn not in (8, 9):
                    r[rd] = v & 0xFFFFFFFF
            elif op == 1:
                c = s32(R(rs))
                if rt in (0, 16):
                    cond = c < 0
                else:
                    cond = c >= 0
                if rt in (16, 17):
                    r[31] = pc + 8
                if cond:
                    tgt = pc + 4 + simm * 4
            elif op == 2:
                tgt = (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
            elif op == 3:
                tgt = (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
                r[31] = pc + 8
            elif op == 4:
                tgt = pc + 4 + simm * 4 if R(rs) == R(rt) else None
            elif op == 5:
                tgt = pc + 4 + simm * 4 if R(rs) != R(rt) else None
            elif op == 6:
                tgt = pc + 4 + simm * 4 if s32(R(rs)) <= 0 else None
            elif op == 7:
                tgt = pc + 4 + simm * 4 if s32(R(rs)) > 0 else None
            elif op in (8, 9):
                r[rt] = (R(rs) + simm) & 0xFFFFFFFF
            elif op == 0xA:
                r[rt] = int(s32(R(rs)) < simm)
            elif op == 0xB:
                r[rt] = int(R(rs) < (simm & 0xFFFFFFFF))
            elif op == 0xC:
                r[rt] = R(rs) & imm
            elif op == 0xD:
                r[rt] = R(rs) | imm
            elif op == 0xE:
                r[rt] = R(rs) ^ imm
            elif op == 0xF:
                r[rt] = (imm << 16) & 0xFFFFFFFF
            elif op == 0x20:
                v = self.rb(R(rs) + simm)
                r[rt] = (v - 256 if v & 0x80 else v) & 0xFFFFFFFF
            elif op == 0x21:
                v = self.rh(R(rs) + simm)
                r[rt] = (v - 65536 if v & 0x8000 else v) & 0xFFFFFFFF
            elif op == 0x23:
                r[rt] = self.rw(R(rs) + simm)
            elif op == 0x24:
                r[rt] = self.rb(R(rs) + simm)
            elif op == 0x25:
                r[rt] = self.rh(R(rs) + simm)
            elif op == 0x28:
                self.wb(R(rs) + simm, R(rt))
            elif op == 0x29:
                a = R(rs) + simm
                self.wb(a, R(rt))
                self.wb(a + 1, R(rt) >> 8)
            elif op == 0x2B:
                a = R(rs) + simm
                for k in range(4):
                    self.wb(a + k, R(rt) >> (8 * k))
            else:
                raise RuntimeError(f"op {op:#x} @{pc:#x}")
            r[0] = 0
            if pending is not None:
                nxt, pending = pending, None
            elif tgt is not None:
                pending = tgt
            pc = nxt


def _hle(self, vec, fn):
    r = self.r

    def cstr(a):
        o = bytearray()
        while True:
            b = self.rb(a + len(o))
            if not b:
                return bytes(o)
            o.append(b)

    if vec == 0xA0 and fn == 0x1B:
        r[2] = len(cstr(r[4]))
    elif vec == 0xA0 and fn == 0x19:
        s = cstr(r[5])
        for i, b in enumerate(s + b"\0"):
            self.wb(r[4] + i, b)
        r[2] = r[4]
    elif vec == 0xA0 and fn == 0x2B:
        for i in range(r[6]):
            self.wb(r[4] + i, r[5])
        r[2] = r[4]
    elif vec == 0xA0 and fn == 0x2A:
        for i in range(r[6]):
            self.wb(r[4] + i, self.rb(r[5] + i))
        r[2] = r[4]
    elif vec == 0xA0 and fn == 0x15:
        d = r[4]
        n = len(cstr(d))
        s = cstr(r[5])
        for i, b in enumerate(s + b"\0"):
            self.wb(d + n + i, b)
        r[2] = d
    elif vec == 0xA0 and fn == 0x27:
        tmp = [self.rb(r[4] + i) for i in range(r[6])]
        for i, v in enumerate(tmp):
            self.wb(r[5] + i, v)
    elif vec == 0xA0 and fn == 0x28:
        for i in range(r[5]):
            self.wb(r[4] + i, 0)
    else:
        raise RuntimeError(f"HLE {vec:#x}:{fn:#x}")


CPU.hle = _hle


def enc(s):
    return b"".join(H.encode_kr(c) if "가" <= c <= "힣" else c.encode("cp932") for c in s)


def _half(b):
    return 0x20 <= b <= 0x7E or 0xA1 <= b <= 0xDF


def width(line):
    c = i = 0
    while i < len(line):
        b = line[i]
        if b < 4:
            i += 1
        elif _half(b):
            c, i = c + 1, i + 1
        else:
            c, i = c + 2, i + 2
    return c


def prewrap(exe, game, s):
    c = CPU(exe)
    buf = 0x801F0000
    for i, b in enumerate(s + b"\x00"):
        c.wb(buf + i, b)
    c.call(PREWRAP_FN[game], {4: buf, 29: 0x801FFF00})
    out, i = bytearray(), 0
    while c.rb(buf + i):
        out.append(c.rb(buf + i))
        i += 1
    return bytes(out)


def violations(src, out):
    """①·②·③·④·⑦(이름 구간 절단)·⑧(글 소실)·폭 — 자동으로 끼운 개행만 본다(입력에 있던 개행은 문안 몫)."""
    v = []
    lines = out.split(b"\n")
    flat = src.replace(b"\x01", b"").replace(b"\x02", b"")
    for k, ln in enumerate(lines):
        body = bytes(b for b in ln if b >= 4)
        if width(ln) > FRAME:
            v.append("폭")
        if k and body.startswith(b" "):
            v.append("③")
        if k and body and all(ch in b".,!?" for ch in body):
            v.append("①")
        if k and body and not body.startswith(b" "):
            prev = bytes(b for b in lines[k - 1] if b >= 4)
            joined = prev[-2:] + body[:2]
            if (
                prev
                and b" " in prev.strip()
                and not prev.endswith((b" ", b".", b"!", b"?"))
                and joined in flat
            ):
                v.append("④")
    if b"\n\n" in out and b"\n\n" not in src:
        v.append("②")
    # ⑧ 글 소실 — prewrap 이 하는 일은 개행 끼우기와 줄머리 공백 삼키기뿐이다. 그 둘을 걷으면
    #   입력과 **바이트까지 같아야** 한다(마스터 QA 112 「ＨＰ를 112 / 빼앗았다!!」 꼬리 소실, 09-27).
    if out.replace(b"\n", b"").replace(b" ", b"") != src.replace(b"\n", b"").replace(b" ", b""):
        v.append("⑧")
    # ⑦ 이름 구간(`\x02…\x01`/`\x03`) 안의 자동 개행 — 「불꽃의 / 창」(09-27). 한 줄보다 긴 이름은 뺀다.
    inside, seg, cut = False, bytearray(), False
    for b in out:
        if b == 0x02:
            inside, seg, cut = True, bytearray(), False
        elif b in (0x01, 0x03) and inside:
            if cut and width(bytes(seg)) < FRAME:
                v.append("⑦")
            inside = False
        elif inside:
            if b == 0x0A:
                cut = cut or bool(seg)  # 색 시작 바로 뒤 개행 = 이름을 통째로 넘긴 것(정상)
            else:
                seg.append(b)
    return v


# 마스터 QA(4장, 09-27) 캡처 넷 — 원판 prewrap 이 글자 단위로 끊던 자리. 빌드에서 ④·① 이 0 이어야 한다.
REGRESSION_ED2 = (
    "20년 전 왕가를 빼앗은 것일세!! 황제란 이름뿐인 독재자지.",  # 것일세 / !!
    "무기라면 썩어 넘칠 만큼 있네.",  # 있네 / .
    "자네들 무기는 여기 두겠네. 성문에서 기다리겠네.",  # 성 / 문에서
    "그리고 마스터를 제외한 모든 사람들의 기억을 지우고 지상 일은 일절 비밀에 부쳤다.",  # 사람 / 의
)


def _runtime(kr, p):
    """ED2 전투 표 문안 → 런타임 모습. `%c` 는 색 켜고 끄기를 번갈아, `%s` 는 최장 이름, `%d` 는 4자리."""
    out, on = [], False
    for part in kr.split("%c"):
        out.append(part)
        out.append("\x01" if on else "\x02")
        on = not on
    t = "".join(out[:-1]).replace("%s", p).replace("%d", "1234")
    return t


def _battle_table(tbl):
    """🔴 ED2 전투 표(`battle_ed2.json` — 전투 로그 + 성 안 컷신 대사)도 prewrap 을 탄다(09-27 실측).

    원판 prewrap 은 글자 단위라 「성 / 문에서」·「것일세 / !!」·「있네 / .」를 냈다(4장 마스터 캡처).
    ED1 전용 `check_battle_wrap` 이 이 표를 안 봐서 캡처로만 걸렸다 — 여기서 전량을 실행으로 잰다.
    """
    import patch_ed2_battle as B

    st = site("ED2")
    orig = bytes(common.extract(st["lba"], st["size"]))
    new = bytes(
        common.extract(
            st["lba"], st["size"], path=os.path.join(common.BUILD_DIR, "Eiyuu Densetsu (KR).bin")
        )
    )
    fit, over, _none = B.plan()
    texts = [kr for _fo, _jp, kr, _slot in fit + over] + list(REGRESSION_ED2)
    tally = {"원판": {}, "빌드": {}}
    bad = []
    for kr in texts:
        s = bytearray(enc(_runtime(kr, LONGEST["ED2"])) + b"\x00" * 8)
        J.fix_buffer(s, tbl, cross=None, limit=128)
        s = bytes(s).split(b"\x00")[0]
        # ⚠ 입력에 이미 있던 개행·들여쓰기(장 카드 가운데 맞춤 · 「…」만 있는 줄)는 문안 몫이다 —
        #   prewrap 이 아무것도 안 바꿔도 걸리므로 입력 자체의 판정을 뺀다.
        base = violations(s, s)
        for lab, exe in (("원판", orig), ("빌드", new)):
            out = prewrap(exe, "ED2", s)
            v = [x for x in violations(s, out) if x not in base]
            # ⑨(폭에 꼭 찬 줄 뒤의 개행 → 빈 줄)는 **엔진을 고쳐 없앴다**(10-03 `stub_eager_nl`, 에뮬 A/B).
            #   종장 배 안내(09-28)에서 발견해 검사기에 넣었던 규칙인데 문안이 아니라 드로어가 원인이었다.
            for x in v:
                tally[lab][x] = tally[lab].get(x, 0) + 1
            if lab == "빌드" and v:
                bad.append((v, kr))
    for v, kr in bad[:5]:
        print(f"      {''.join(v)} {kr!r}")
    print(f"  ED2 전투 표: {len(texts)}종 — 원판 {tally['원판'] or 0} → 빌드 {tally['빌드'] or 0}")
    return sum(tally["빌드"].values())


def main():
    img = os.path.join(common.BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    tbl = J.build_bit_table()
    names = {n for n in set(PI.NAMES.values()) | set(PS.NAMES_ED2.values()) if n and len(n) <= 10}
    worst = 0
    for game in ("ED1", "ED2"):
        st = site(game)
        orig = bytes(common.extract(st["lba"], st["size"]))
        new = bytes(common.extract(st["lba"], st["size"], path=img))
        p = LONGEST[game]
        tally = {"원판": {}, "빌드": {}}
        n = 0
        for obj in sorted(names):
            for tgt in (p, "자기 자신"):
                for verb in ("을(를) 외웠다.", "을(를) 사용했다."):
                    t = (
                        f"\x02{p}\x01은(는) \x02{tgt}\x01에게 \x02{obj}\x01{verb}\n"
                        f"\x02{p}\x01의 ＨＰ가 1234 회복되었다."
                    )
                    if verb.endswith("외웠다."):  # 흡수 주문 꼴(112) — 30열 줄이 어절에서 물러난다
                        t += f"\n\x02{tgt}\x01의 ＨＰ를 1234 빼앗았다!!\n\x02{p}\x01의 ＨＰ를 112 빼앗았다!!"
                    s = bytearray(enc(t) + b"\x00" * 8)
                    J.fix_buffer(s, tbl, cross=None, limit=128)
                    s = bytes(s).split(b"\x00")[0]
                    n += 1
                    for lab, exe in (("원판", orig), ("빌드", new)):
                        for x in violations(s, prewrap(exe, game, s)):
                            tally[lab][x] = tally[lab].get(x, 0) + 1
        worst = max(worst, sum(tally["빌드"].values()))
        print(f"  {game}: 조립 문장 {n}종 — 원판 {tally['원판'] or 0} → 빌드 {tally['빌드'] or 0}")
    worst = max(worst, _battle_table(tbl))
    print(f"  {'✅' if not worst else '❌'} 런타임 줄넘김 ①~④·⑦~⑨: 빌드 {worst}건")
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
