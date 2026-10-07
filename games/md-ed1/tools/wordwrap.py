"""어절 단위 줄넘김 — 창이 넘칠 때 **글자가 아니라 어절**을 다음 줄로 보낸다(마스터 최종 판정
2026-09-30, 전 기종).

    python3 tools/wordwrap.py --check    # 후킹 자리가 원본 그대로인가 · 기계어 크기
    python3 tools/wordwrap.py --asm      # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 경위 — 한 번 걷었다가 다시 심었다

09-27 낮에 처음 짰다가, 그날 밤 "PS1·새턴도 로그를 어절로 접는다는 걸 몰랐다"며 글자 단위로
되돌렸다(그때 지운 파일이 이 파일이다). 그런데 **09-30 에 마스터가 다시 번복** — 전 기종을
한 번 더 맞춰 보니 로그도 어절 단위가 맞다는 판정으로 돌아왔다. 아래 설계·기계어는 09-27 판과
같고(git 이력에서 복원), 라운드⑥ 산출물에 맞춰 docstring 만 다시 썼다.

## 왜 렌더러를 고치나

로그성 메시지(도구·주문 사용)는 **런타임에 조각을 이어 그린다** — 시전자 이름 · 「는」 · 대상 이름 · 「에게」 ·
주문 이름 · 꼬리가 `$60A0` 을 여러 번 불러 **`$FF2004`(그리기 포인터)를 이어받아** 한 줄에 쌓인다.
이름 길이를 빌드가 모르니 빌드 조판기(krwrap)로는 줄을 못 가른다. 그래서 박은 줄바꿈(「대상 뒤」)으로
버텼는데, 마스터가 「강제 개행을 없애고 넘칠 때만 어절로」로 정했다 ⇒ 렌더러가 넘칠 때 스스로 가른다.

## 원판 렌더러(실측)

    $978C       렌더러. 글자마다 `$A990`(들어가나?) → 넘치면 `bsr $A0A0`(줄바꿈) · `bsr $AA3A`(두루마리) 뒤 그린다
                넓은 글자 자리 0x986A · 좁은 글자 자리 0x98D2 — 둘 다 `6100 xxxx`(bsr.w $A0A0)
    $A9B8       넘침 = 커서 바이트 `$FF2018` > 행 폭 d7 − 13
    버퍼        RAM **선형 4bpp** 비트맵. a6 = 현재 줄 첫 행 · d7 = 행 폭(바이트) · 줄 높이 `$FF2015`(16행)
    $AD24       글자마다 **커서 주변 타일 2×2 만** VRAM 으로 — 옮긴 어절은 따로 올려야 한다
    $A706       창 **전체**를 VRAM 으로(두루마리 `$AA8A` 끝이 부른다) — 옮긴 뒤 이걸 부른다
    바탕 니블    `$FF2012` 상위 니블(0 이면 `$E4C4` 판정 뒤 D) — 두루마리가 빈 줄을 칠하는 규칙 그대로

## 공백을 어떻게 찾나 — RAM 을 새로 안 쓴다

넘친 순간 **현재 줄 비트맵을 커서에서 왼쪽으로 니블 단위로 훑어** 「바탕색뿐인 세로줄 4px 연속」을 공백으로 본다.
빌드 롬 글꼴(채움+테두리)로 잰 값(2026-09-27): 글자 **사이** 빈 틈은 최대 3px(좁은 「.」 뒤), **공백**이 만드는
틈은 최소 4px(넓은 글자 잉크가 칸 밖으로 2px 번진다), 글자 **안** 틈은 최대 1px ⇒ 4px 에서 정확히 갈린다.
⚠ 바이트(2px) 단위로는 안 갈린다(3px 틈과 4px 틈이 둘 다 빈 바이트 하나로 보인다) — 니블로 훑는 이유다.
🔴 **빌드가 새로 구운 글꼴로 매번 다시 잰다**(`gap_gate`) — 글꼴을 바꿔 문턱이 무너지면 빌드가 실패한다.

- 찾으면: 공백 뒤 어절(칸 원점 바이트 W ~ 커서 k, 잉크 번짐 1바이트 포함)을 줄바꿈 **뒤** 새 줄 첫머리로 옮기고
  옛 자리를 바탕으로 지운 뒤 `$A706` 으로 창을 다시 올린다. 새 줄 = 옛 줄 + 줄 높이(두루마리가 났어도 같다 —
  두루마리는 옛 줄을 한 줄 위로 올린다).
- 넘친 글자가 공백이면: 줄만 바꾸고 공백은 새 줄 **앞**(a2 − 3)에 그려 흘린다(공백 글리프는 잉크가 없어 흔적이
  안 남는다) ⇒ 새 줄이 공백으로 시작하지 않는다.
- 못 찾으면(한 어절이 한 줄보다 김) · 피치가 12 가 아니면: 원래대로 글자 단위(`$A0A0`).

## 어디에 무엇을 쓰나

    0x986A · 0x98D2   `bsr.w $A0A0` → `bsr.w 트램펄린`
    josa.DEAD_HANDLER + 12   `jmp <꼬리>.l` (조사 훅 트램펄린 둘 뒤, 코드 EE 의 죽은 핸들러 자리)
    꼬리(WRAP_RESERVE)       본체
"""

import itertools
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import josa

SITES = (0x986A, 0x98D2)  # bsr.w $A0A0 — 넓은 글자 · 좁은 글자 넘침
NEWLINE, SCROLL, REFRESH, BG_TEST = 0xA0A0, 0xAA3A, 0xA706, 0xE4C4
TRAMP = josa.DEAD_HANDLER + 12
PITCH, CURSOR, PTR, LINE_H, BG = 0xFF2014, 0xFF2018, 0xFF2004, 0xFF2015, 0xFF2012
SPACE_PX = 4  # 공백으로 치는 빈 세로줄 수(px) — 위 docstring 의 실측


class Asm:
    """68000 손인코딩 — 라벨과 분기 변위만 계산한다(명령 인코딩은 워드로 직접 적는다)."""

    def __init__(self, at: int):
        self.at, self.b, self.labels, self.fix = at, bytearray(), {}, []

    def w(self, *vals):
        for v in vals:
            self.b += struct.pack(">H", v & 0xFFFF)

    def l(self, v):
        self.b += struct.pack(">I", v)

    def label(self, name):
        self.labels[name] = len(self.b)

    def br(self, op, name):
        """bcc.w — op = 상위 바이트(0x60 bra · 0x66 bne · 0x67 beq · 0x64 bcc · 0x6B bmi)."""
        self.w(op << 8)
        self.fix.append((len(self.b), name, "w"))
        self.w(0)

    def dbra(self, reg, name):
        self.w(0x51C8 | reg)
        self.fix.append((len(self.b), name, "w"))
        self.w(0)

    def done(self) -> bytes:
        for pos, name, _ in self.fix:
            disp = self.labels[name] - pos
            assert -0x8000 <= disp < 0x8000
            self.b[pos : pos + 2] = struct.pack(">h", disp)
        return bytes(self.b)


def code(at: int) -> bytes:
    a = Asm(at)
    SAVE, REST = (0x48E7, 0xFFDC), (0x4CDF, 0x3BFF)  # d0-d7/a0-a1/a3-a5 (a2·a6 는 돌려준다)
    a.w(*SAVE)
    a.w(0x0C39, 0x000C), a.l(PITCH)  # cmpi.b #12,$FF2014
    a.br(0x66, "orig")
    # ── 바탕 니블 → d5 (두루마리 $AAF0 과 같은 규칙) ──
    a.w(0x1039), a.l(BG)  # move.b $FF2012,d0
    a.w(0x1200)  # move.b d0,d1
    a.w(0x0201, 0x00F0)  # andi.b #$F0,d1
    a.br(0x66, "have")
    a.w(0x4EB9), a.l(BG_TEST)  # jsr $E4C4
    a.br(0x66, "have")
    a.w(0x103C, 0x00DD)  # move.b #$DD,d0
    a.w(0x123C, 0x00DD)  # move.b #$DD,d1
    a.label("have")
    a.w(0xE808)  # lsr.b #4,d0
    a.w(0x8001)  # or.b d1,d0
    a.w(0x7A00)  # moveq #0,d5
    a.w(0x1A00)  # move.b d0,d5
    a.w(0x0205, 0x000F)  # andi.b #$0F,d5
    # ── 넘친 글자가 공백이면 줄만 바꾼다 ──
    a.w(0x322F, 0x0002)  # move.w 2(a7),d1   저장한 d0 의 아래 워드 = 글자
    a.w(0x0C41, 0x0020)  # cmpi.w #$20,d1
    a.br(0x67, "space")
    a.w(0x0C41, 0x8140)  # cmpi.w #$8140,d1
    a.br(0x67, "space")
    # ── 현재 줄을 오른쪽에서 왼쪽으로 니블 단위로 훑는다 ──
    a.w(0x7C00)  # moveq #0,d6
    a.w(0x1C39), a.l(CURSOR)  # move.b $FF2018,d6        k
    a.w(0x7800)  # moveq #0,d4
    a.w(0x1839), a.l(LINE_H)  # move.b $FF2015,d4        줄 높이
    a.w(0x3606)  # move.w d6,d3
    a.w(0xD643)  # add.w d3,d3
    a.w(0x5343)  # subq.w #1,d3                  px = 2k − 1
    a.w(0x7400)  # moveq #0,d2                    빈 줄 길이
    a.label("loop")
    a.w(0x4A43)  # tst.w d3
    a.br(0x6B, "orig")  # 줄 머리까지 공백이 없다 → 글자 단위
    a.w(0x3003)  # move.w d3,d0
    a.w(0xE248)  # lsr.w #1,d0
    a.w(0x41F6, 0x0000)  # lea 0(a6,d0.w),a0
    a.w(0x3204)  # move.w d4,d1
    a.w(0x5341)  # subq.w #1,d1
    a.label("col")
    a.w(0x1010)  # move.b (a0),d0
    a.w(0x0803, 0x0000)  # btst #0,d3
    a.br(0x66, "low")
    a.w(0xE808)  # lsr.b #4,d0                   짝수 px = 상위 니블
    a.label("low")
    a.w(0x0200, 0x000F)  # andi.b #$0F,d0
    a.w(0xB005)  # cmp.b d5,d0
    a.br(0x66, "ink")
    a.w(0xD1C7)  # adda.l d7,a0
    a.dbra(1, "col")
    a.w(0x5242)  # addq.w #1,d2
    a.w(0x0C42, SPACE_PX)  # cmpi.w #4,d2
    a.br(0x64, "found")
    a.w(0x5343)  # subq.w #1,d3
    a.br(0x60, "loop")
    a.label("ink")
    a.w(0x7400)  # moveq #0,d2
    a.w(0x5343)  # subq.w #1,d3
    a.br(0x60, "loop")
    # ── 공백 뒤 어절: W = (px+4)/2, n = k − W ──
    a.label("found")
    a.w(0x5843)  # addq.w #4,d3
    a.w(0xE24B)  # lsr.w #1,d3                   W
    a.w(0x3406)  # move.w d6,d2
    a.w(0x9443)  # sub.w d3,d2                   n
    a.w(0x48E7, 0x3000)  # movem.l d2-d3,-(a7)
    a.w(0x4EB9), a.l(NEWLINE)
    a.w(0x4EB9), a.l(SCROLL)
    a.w(0x4CDF, 0x000C)  # movem.l (a7)+,d2-d3
    a.w(0x3204)  # move.w d4,d1
    a.w(0xC2C7)  # mulu.w d7,d1                  줄 높이 × 행 폭
    a.w(0x204E)  # movea.l a6,a0
    a.w(0x91C1)  # suba.l d1,a0                  옛 줄
    a.w(0xD0C3)  # adda.w d3,a0                  + W
    a.w(0x224E)  # movea.l a6,a1                 새 줄 첫머리
    a.w(0x4A42)  # tst.w d2
    a.br(0x67, "moved")
    a.w(0x1C05)  # move.b d5,d6
    a.w(0xE90E)  # lsl.b #4,d6
    a.w(0x8C05)  # or.b d5,d6                    바탕 바이트
    a.w(0x3204)  # move.w d4,d1
    a.w(0x5341)  # subq.w #1,d1
    a.label("row")
    a.w(0x48E7, 0x00C0)  # movem.l a0-a1,-(a7)
    a.w(0x3002)  # move.w d2,d0                  n+1 바이트(잉크 번짐 1바이트 포함)
    a.label("cp")
    a.w(0x12D0)  # move.b (a0),(a1)+
    a.w(0x10C6)  # move.b d6,(a0)+
    a.dbra(0, "cp")
    a.w(0x4CDF, 0x0300)  # movem.l (a7)+,a0-a1
    a.w(0xD1C7)  # adda.l d7,a0
    a.w(0xD3C7)  # adda.l d7,a1
    a.dbra(1, "row")
    a.label("moved")
    a.w(0x244E)  # movea.l a6,a2
    a.w(0xD4C2)  # adda.w d2,a2
    a.w(0x13C2), a.l(CURSOR)  # move.b d2,$FF2018
    a.w(0x23CA), a.l(PTR)  # move.l a2,$FF2004
    a.w(0x4EB9), a.l(REFRESH)  # jsr $A706 — 창 전체를 VRAM 으로
    a.br(0x60, "exit")
    # ── 넘친 글자가 공백 ──
    a.label("space")
    a.w(0x4EB9), a.l(NEWLINE)
    a.w(0x4EB9), a.l(SCROLL)
    a.w(0x578A)  # subq.l #3,a2                  공백은 새 줄 앞(잉크 없음)에 그려 흘린다
    a.w(0x13FC, 0x00FD), a.l(CURSOR)  # move.b #-3,$FF2018
    a.br(0x60, "exit")
    a.label("orig")
    a.w(*REST)
    a.w(0x4EF9), a.l(NEWLINE)  # jmp $A0A0 — 원래 동작
    a.label("exit")
    a.w(*REST)
    a.w(0x4E75)
    return a.done()


def _ink_cols(rom: bytes, r: dict, i: int) -> set[int]:
    """글리프 하나의 잉크 세로줄(채움 + 테두리 두 면)."""
    h, nb = r["h"], r["nbytes"]
    bpr = nb // h
    base = r["glyphs"] + i * r["stride"]
    cols = set()
    for plane in (0, nb):
        for y in range(h):
            v = int.from_bytes(rom[base + plane + y * bpr : base + plane + (y + 1) * bpr], "big")
            cols.update(x for x in range(bpr * 8) if v >> (bpr * 8 - 1 - x) & 1)
    return cols


def gap_gate(rom: bytes, wide_codes: set[int]) -> tuple[int, int]:
    """(글자 사이·안 최대 빈 틈, 공백 틈 최소) px — 앞이 SPACE_PX 보다 작고 뒤가 SPACE_PX 이상이어야 한다.

    넓은 글자 = 리소스 0(피치 12, 전진 12px) · 좁은 글자 = 리소스 1(전진 6px). 빌드가 쓰는 글자만 본다.
    """
    import font

    res = font.resources(rom)
    ext = []  # (전진 px, 왼쪽 잉크, 오른쪽 잉크, 안쪽 최대 틈)
    for ri, adv, pick in ((0, 12, wide_codes), (1, 6, None)):
        r = res[ri]
        for i, c in enumerate(font.codes(rom, r)):
            if pick is not None and c not in pick:
                continue
            cols = sorted(_ink_cols(rom, r, i))
            if not cols:
                continue
            inner = max((b - a - 1 for a, b in itertools.pairwise(cols)), default=0)
            ext.append((adv, cols[0], cols[-1], inner))
    max_l = max(e[1] for e in ext)
    min_l = min(e[1] for e in ext)
    between = max(adv + max_l - r_ - 1 for adv, _l, r_, _i in ext)  # 공백 없이 이웃할 때
    inner = max(e[3] for e in ext)
    space = min(adv + 6 + min_l - r_ - 1 for adv, _l, r_, _i in ext)  # 사이에 공백 하나
    worst = max(between, inner)
    if not worst < SPACE_PX <= space:
        raise SystemExit(
            f"어절 줄넘김 문턱이 무너졌다 — 글자 틈 최대 {worst}px · 공백 틈 최소 {space}px · 문턱 {SPACE_PX}px"
        )
    return worst, space


def plan(rom: bytes, at: int) -> list[tuple[str, int, bytes]]:
    out = [("wrap-code", at, code(at))]
    out.append(("wrap-tramp", TRAMP, b"\x4e\xf9" + struct.pack(">I", at)))
    for s in SITES:
        disp = TRAMP - (s + 2)
        assert -0x8000 <= disp < 0x8000
        out.append((f"wrap-site:{s:x}", s, b"\x61\x00" + struct.pack(">h", disp)))
    return out


def check(d: bytes) -> None:
    for s in SITES:
        disp = struct.unpack(">h", d[s + 2 : s + 4])[0]
        if d[s : s + 2] != b"\x61\x00" or s + 2 + disp != NEWLINE:
            raise SystemExit(f"후킹 자리 {s:#x} 가 `bsr.w $A0A0` 이 아니다")
    if d[TRAMP : TRAMP + 6] != d[josa.DEAD_HANDLER + 12 : josa.DEAD_HANDLER + 18]:
        raise SystemExit("트램펄린 자리 계산이 어긋났다")
    print(f"  어절 줄넘김 — 후킹 {len(SITES)} · 기계어 {len(code(0x1F0000))}B")


def verify(body: bytes, at: int) -> list[str]:
    return josa.verify(body, at)


if __name__ == "__main__":
    d = common.rom()
    if "--asm" in sys.argv:
        print("\n".join(verify(code(0x1F0000), 0x1F0000)))
    else:
        check(d)
