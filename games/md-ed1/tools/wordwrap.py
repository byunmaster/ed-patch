"""로그성 메시지 줄넘김 — **글자 단위**로 두고 최소 가드 둘만 막는다(마스터 최종 확정 2026-09-27 밤, 기종 공통).

    python3 tools/wordwrap.py --check    # 후킹 자리가 원본 그대로인가 · 기계어 크기
    python3 tools/wordwrap.py --asm      # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 경위 — 어절 접기를 넣었다가 도로 걷었다

낮에 「강제 개행을 없애고 넘칠 때만 어절로」 판정을 받아 렌더러가 공백 뒤 어절을 통째로 다음 줄로
옮기게 짰다(326B, 니블 단위로 화면 비트맵을 훑어 공백을 찾는 방식). 그런데 PS1·새턴이 로그에도 이미
어절 줄넘김을 쓰고 있어 「기종 다르게 갈 것 없다」는 재검토가 나왔고, 결국 **로그는 어절이 아니라
글자 단위가 낫다**(「어절 개행이 오히려 가독성이 떨어진다」)로 최종 확정됐다. 밤 새 뒤집힌 판정이라
옛 어절 접기 코드는 전부 버리고 이 파일을 다시 짰다.

## 막는 것 둘만 — 나머지는 원판 그대로

로그성 메시지는 런타임에 조각을 이어 그려(시전자 이름 + 「는」 + 대상 이름 + 「에게」 + 주문 이름 + 꼬리가
`$60A0` 을 여러 번 불러 `$FF2004` 를 이어받는다) 빌드가 이름 길이를 모른다 — 그래서 **글자 단위 줄넘김
자체는 원판 그대로** 두고(강제 개행만 걷었다, 09-27 낮 커밋), 렌더러에는 아래 둘만 심는다:

    ① 고아 부호 금지  — 마침표·느낌표·물음표(.!?, 「!!」·「!?」 연쇄 포함)가 혼자 줄 첫머리로 못 간다.
                        넘쳐도 줄을 안 바꾸고 **앞줄 끝에 매단다**(그대로 그리게 둔다 — 살짝 넘쳐도 된다).
    ② 줄 첫 칸 공백 금지 — 넘친 글자가 공백이면 **그 공백은 버리고** 줄만 바꾼다(다음 글자가 새 줄 머리).

## 원판 렌더러(실측)

    $978C       렌더러. 글자마다 `$A990`(들어가나?) → 넘치면 `bsr $A0A0`(줄바꿈) · `bsr $AA3A`(두루마리) 뒤 그린다
                넓은 글자 자리 0x986A(한글·전각, `bsr.w $A0A0`) · 좁은 글자 자리 0x98D2(반각, `bsr.w $A0A0`)
    $A9B8       넘침 = 커서 바이트 `$FF2018` > 행 폭 d7 − 13

공백·마침표·느낌표·물음표는 **전부 반각**이라 넓은 글자 자리(0x986A, 한글 전용)는 안 건드린다 — **좁은
글자 자리(0x98D2) 하나만** 후킹한다. 거기서 넘친 글자(저장된 d0 의 낮은 워드)를 보고:
  - 공백(반각 `$20` · 전각 `$8140`)이면 `$A0A0`(줄바꿈)만 부르고 **`rts`** — 공백 자신은 그대로
    돌아가 원래 자리(옛 줄 자리)에 그려지는데, `$A0A0` 이 이미 커서·포인터를 새 줄 머리로 옮겨 둔 뒤라
    **공백을 새 줄 머리보다 3바이트 앞(옛 줄 쪽)으로** 되돌려 그린다(잉크가 없어 안 보인다) — 그리고
    나면 커서를 다시 원위치로 세워 다음 글자가 진짜 줄 머리에 온다.
  - 마침표·느낌표·물음표면 `$A0A0` 을 **아예 안 부르고 `rts`** — 커서가 이미 넘친 채라 글자가 옛
    줄 끝에 그대로 그려진다(줄 폭을 살짝 넘긴다). 다음 글자가 또 같은 부류면(「!!」·「!?」) 같은
    경로를 또 타 **연쇄로 매달린다**.
  - 그 외엔 원판 그대로: `$A0A0` 을 부르고 글자를 새 줄에 그린다.

## 어디에 무엇을 쓰나

    0x98D2                    `bsr.w $A0A0` → `bsr.w 트램펄린`(0x986A 는 원본 그대로 안 건드린다)
    josa.DEAD_HANDLER + 12    `jmp <꼬리>.l` (조사 훅 트램펄린 둘 뒤, 코드 EE 의 죽은 핸들러 자리)
    꼬리(WRAP_RESERVE)        본체 92B
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import josa

SITES = (0x98D2,)  # bsr.w $A0A0 — 좁은(반각) 글자 넘침만 후킹한다. 0x986A(넓은 글자)는 원본 그대로
NEWLINE = 0xA0A0
TRAMP = josa.DEAD_HANDLER + 12

# 넘친 글자가 이것이면 줄을 안 바꾸고 그대로 그린다(부호는 앞줄 끝에 매단다)
ORPHAN = (0x2E, 0x21, 0x3F)  # . ! ?
CURSOR = 0xFF2018


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
        """bcc.w — op = 상위 바이트(0x60 bra · 0x66 bne · 0x67 beq)."""
        self.w(op << 8)
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
    a.w(0x322F, 0x0002)  # move.w 2(a7),d1   저장한 d0 의 아래 워드 = 넘친 글자
    a.w(0x0C41, 0x0020)  # cmpi.w #$20,d1        반각 공백
    a.br(0x67, "space")
    a.w(0x0C41, 0x8140)  # cmpi.w #$8140,d1      전각 공백
    a.br(0x67, "space")
    for code_pt in ORPHAN:
        a.w(0x0C41, code_pt)  # cmpi.w #부호,d1
        a.br(0x67, "punct")
    # ── 그 외: 원판 그대로 줄바꿈 ──
    a.w(*REST)
    a.w(0x4EF9), a.l(NEWLINE)  # jmp $A0A0
    # ── 부호: 줄바꿈 없이 그대로 그린다(앞줄 끝에 매단다) ──
    a.label("punct")
    a.w(*REST)
    a.w(0x4E75)  # rts
    # ── 공백: 줄바꿈만 하고 공백 자신은 옛 줄 쪽(안 보이는 자리)에 흘린다 ──
    a.label("space")
    a.w(0x4EB9), a.l(NEWLINE)  # jsr $A0A0
    a.w(0x578A)  # subq.l #3,a2          공백은 새 줄 앞(잉크 없음)에 그려 흘린다
    a.w(0x13FC, 0x00FD), a.l(CURSOR)  # move.b #-3,$FF2018
    a.w(*REST)
    a.w(0x4E75)  # rts
    return a.done()


def plan(rom: bytes, at: int) -> list[tuple[str, int, bytes]]:
    out = [("wrap-code", at, code(at))]
    out.append(("wrap-tramp", TRAMP, b"\x4e\xf9" + struct.pack(">I", at)))
    for s in SITES:
        disp = TRAMP - (s + 2)
        assert -0x8000 <= disp < 0x8000
        out.append((f"wrap-site:{s:x}", s, b"\x61\x00" + struct.pack(">h", disp)))
    return out


ORIG_SITES = (0x986A, 0x98D2)  # 원본 검산은 둘 다(0x986A 는 안 건드리지만 원본 값은 확인해 둔다)


def check(d: bytes) -> None:
    for s in ORIG_SITES:
        disp = struct.unpack(">h", d[s + 2 : s + 4])[0]
        if d[s : s + 2] != b"\x61\x00" or s + 2 + disp != NEWLINE:
            raise SystemExit(f"후킹 자리 {s:#x} 가 `bsr.w $A0A0` 이 아니다")
    if d[TRAMP : TRAMP + 6] != d[josa.DEAD_HANDLER + 12 : josa.DEAD_HANDLER + 18]:
        raise SystemExit("트램펄린 자리 계산이 어긋났다")
    print(f"  로그 줄넘김 가드 — 후킹 {len(SITES)}(반각만) · 기계어 {len(code(0x1F0000))}B")


def verify(body: bytes, at: int) -> list[str]:
    return josa.verify(body, at)


if __name__ == "__main__":
    d = common.rom()
    if "--asm" in sys.argv:
        print("\n".join(verify(code(0x1F0000), 0x1F0000)))
    else:
        check(d)
