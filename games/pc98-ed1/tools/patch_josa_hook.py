#!/usr/bin/env python3
"""조사 훅 — **그리는 순간** 직전 글자의 받침으로 은/는·을/를·이/가·과/와를 고른다.

## 왜 그리는 순간인가

메시지가 어떻게 조립되든(이름을 끼워 넣고 찍든, 조각마다 따로 찍든) 화면에는 **한 글자씩
차례로** 나간다. 2바이트 글자는 전부 `0x7d70`, 1바이트는 `0x7d8d` 를 지난다(program,
메시지 창 `0x79e2`/`0x79fd` · 보통 출력기 `0x7d06`). 그 두 입구에서

    ⑴ 지금 글자가 **자리표시(SJIS 0x8540~)** 이면 → 직전 받침에 따라 진짜 조사로 바꾼다
    ⑵ 그리고 지금 글자의 받침을 **한 바이트(FLAG)** 에 적는다

만 하면 시스템·전투·씬 어디서든 같은 장치가 된다(마스터 09-27: 이름 뒤 조사가 오는 전 자리).
⚠ 좁은 출력기(`0x7d3c`, HUD 지명)는 이 두 입구를 안 지난다 — 거기엔 조사가 없다.
⚠ 자리표시는 **SJIS 단계에서** 갈아 끼운다. JIS 로 바꾼 뒤엔 구 9 가 반각 글자(`ah=0x29`)와
   코드가 겹쳐 못 가른다(`0x8540`→JIS `0x2921` = 반각 `!`).

## 자리 — 🔴 **코드 속 죽은 자리 + 폰트 트랙의 남는 꼬리**

처음엔 program 0 런 `0x2c36~0x2ffc`(실행 `0x3836~`)에 통째로 뒀다 — 머리 1바이트에 BPM 을
걸어 부팅~SAVE 동안 쓰기 0 을 봤던 자리다. **게임이 첫 글자에서 멈췄다.** 「통과만 하는 훅」
으로 바꿔 구워도 똑같이 멈춰, 논리가 아니라 **자리**가 범인임을 갈랐다(2026-09-27). 그 끝이
`0x3c00` 에 딱 맞는 걸 보면 **스택**이다 — 깊은 쪽부터 자라 내려오니 머리 1바이트만 본 BPM
으로는 안 잡힌다. ⇒ 「디스크에서 0 이고 머리가 안 써진다」는 **빈 자리의 증거가 아니다.**

그래서 둘로 나눴다:

- **가까운 발판**(14B) — 캐시 뱅크 등록 블록 `0x5a5b~0x5aa2`(72B). 폰트 훅이 `and cx,3` 을
  `xor cx,cx` 로 바꿔 **언제나 건너뛰는 코드**가 됐다. 데이터가 아니라 **코드 한복판**이라
  게임이 버퍼로 쓸 일이 없고, 들어오는 분기가 없음을 전수 해독으로 확인했다.
  ⇒ 이 훅은 **폰트 그룹 없이 못 굽는다**(그 패치가 있어야 죽은 자리다).
- **먼 몸통**(코드+짝표+받침표) — 폰트 표 바로 뒤. 로더가 **트랙 통째로** 13트랙을 올리는데
  표는 100섹터라 **4섹터가 남아 해마다 같이 올라온다**(`0x5900:0000`). 두 부팅 경로 모두
  그 로더를 거치므로(event·program 다 표를 싣는다) 어느 쪽으로 켜도 있다.

## 규율(폰트 훅과 같다)

🔴 손인코딩·손계산 없음 — nasm 이 짜고 capstone 이 되읽는다. near Jcc(386 전용) 금지.
"""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import josa_tables
import patch_font_hook as H
import patch_scn
from patch_font_hook import _no_near_jcc

LOAD = 0xC00  # 실행 주소 = 플랫 + 0xC00 (program, status 「로드 베이스 확정」)

# 먼 몸통 — 폰트 표(ku128) 바로 뒤. 표 크기가 16B 배수라 오프셋 0 인 세그먼트가 나온다
TABLE_BYTES = H.KU_COUNT * H.SLOTS_PER_KU * 32
assert TABLE_BYTES % 16 == 0
FAR_SEG = H.FONT_SEG + TABLE_BYTES // 16

# 가까운 발판 — 죽은 캐시 뱅크 등록 블록(폰트 훅 `BANK_AT` 뒤의 `je` 가 늘 건너뛴다)
NEAR_AT = 0x5A5B
NEAR_END = 0x5AA3
# 블록 머리 14B(`mov al,[0x501] / and ax,7 / dec ax / je / js / cmp cx,ax / jb`) — 발판 길이만큼
NEAR_EXPECT = bytes.fromhex("a0010525070048743f783d3bc872")
# 발판 뒤 남는 꼬리는 `patch_sys` 의 조각 이주 자리다 — 둘이 겹치면 build.py 의 겹침 검사가 죽인다
import patch_sys

assert patch_sys.MOVE_POOL == (NEAR_AT + len(NEAR_EXPECT), NEAR_END)

# 2바이트 입구 — `push ax / call 0x7da0` 의 call 만 우리 발판으로
WIDE_AT = 0x7D71
WIDE_EXPECT = bytes.fromhex("e82c00")
SJIS2JIS = 0x7DA0
# 1바이트 입구 — `mov ah,0x29 / cmp ax,0x297f / jb / add ax,0x80` (10B) 를 먼 호출 하나로
NARROW_AT = 0x7D8E
NARROW_EXPECT = bytes.fromhex("b4293d7f297203058000")

# 줄 끝 판정 — 메시지 창 출력기(`0x79c8~`)는 글자마다 `ch`(칸)를 세고 `ch ≥ 34` 면 접는다.
#   원판은 `ch == 34` 에서 다음 글자가 `!`·`。` 일 때만 줄 끝에 매단다(금칙). 우리 문장 끝은 반각
#   `.` 라 그 목록에 없어 **혼자 다음 줄로** 떨어졌다(조판 규칙 ①). 그 판정 26B 를 먼 호출로 바꿔
#   ① 딱 34칸에서 `. , ? !` 도 매달고(원판의 매단 `。` 와 같은 칸 — 35칸째는 테두리다)
#   ② 다음 바이트가 명시 줄바꿈(`01`)이면 먼저 접지 않고(빈 줄 방지) ③ 접는 자리의 반각 공백은
#   먹고 접는다(다음 줄 머리 공백 방지). ⚠ 넓은 글자가 33~34칸을 채워 `ch=35` 가 된 뒤의 부호는
#   이걸로 못 살린다 — 낱말 단위로 미리 접어야 하는 자리다(조판 검사기가 센다).
#   ④ **어절 접기** — 원판은 글자 단위로만 접어 대본까지 「공부 / 가」처럼 낱말 한가운데서
#   끊겼다(2026-09-27 새 게임 첫 장면 실측 — 정책 문서의 「공백에서 접는다」는 우연히 맞은 한 줄을
#   일반화한 오진이었다). 그래서 판정을 `cmp ch,34` **앞**(0x7a13)에서 가로채 글자마다 부르고,
#   방금 그린 게 반각 공백이면 다음 어절을 미리 재서 안 들어가면 공백 뒤에서 접는다.
#   ⚠ 어절은 **제어 바이트에서 끝난다고 본다** — 조각 호출(`10`)·이름 끼움(`0e`) 너머는 못 잰다.
HANG_AT = 0x7A13
HANG_END = 0x7A32  # `ret` — 안 접고 돌아가는 자리
HANG_EXPECT = bytes.fromhex("80fd22721a7403e9e8018b043c21740f86e03d42817403e9d801c6065540ff")
WRAP = 0x7C05  # 줄바꿈(`01` 과 같은 루틴): ch=0 · cl++
HANG_NARROW = b"!.,?"

PH_LEAD = patch_scn.JOSA_LEAD  # SJIS 선행 — 구 9
PAIRS = patch_scn.JOSA_PAIRS  # (자리표시, 받침 있을 때, 없을 때) — 순서가 곧 코드


def _word(ch: str) -> int:
    b = patch_scn.encode(ch)
    return (b[0] << 8) | b[1]  # ah = 선행 · al = 후행 — 게임이 ax 에 담는 꼴


def bitmap_ku128() -> bytes:
    """폰트 표처럼 **구당 128비트(16B)** 로 깐다 — 훅이 곱셈 없이 찾는다."""
    bm = josa_tables.batchim_bitmap()
    out = bytearray(H.KU_COUNT * 16)
    for i in range(len(bm) * 8):
        if bm[i >> 3] >> (7 - (i & 7)) & 1:
            ku, ten = divmod(i, 94)
            j = ku * 128 + ten
            out[j >> 3] |= 0x80 >> (j & 7)
    return bytes(out)


def far_asm() -> str:
    pairs = "\n".join(f"    dw 0x{_word(a):04x}, 0x{_word(b):04x}" for _t, a, b in PAIRS)
    return f"""
BITS 16
org 0
flag:   db 0                ; 0 이면 직전 글자 받침 없음

pre:                        ; ax = SJIS(ah 선행). 자리표시면 진짜 조사로 바꾼다
    cmp ah, 0x{PH_LEAD:x}
    jne short .r
    cmp al, 0x40
    jb  short .r
    cmp al, 0x{0x40 + len(PAIRS) - 1:x}
    ja  short .r
    push bx
    mov bl, al
    sub bl, 0x40
    xor bh, bh
    shl bx, 1
    shl bx, 1               ; 짝 하나 = 4B
    test byte [cs:flag], 0xff
    jnz short .has
    add bx, 2
.has:
    mov ax, [cs:bx + pairs]
    pop bx
.r: retf

post:                       ; ax = JIS(0x7da0 결과). 이 글자의 받침을 적는다
    cmp ax, 0x2121          ; 전각 공백은 받침을 안 바꾼다
    je  short .r
    push bx
    push cx
    push ax
    xor bl, bl
    cmp ah, 0x{H.KU_LO:x}
    jb  short .notk
    cmp ah, 0x{H.KU_HI:x}
    ja  short .notk
    mov cl, al
    sub cl, 0x21            ; 점 0..93
    mov bl, ah
    sub bl, 0x{H.KU_LO:x}
    xor bh, bh
    mov ax, bx
    mov bl, cl
    shr bl, 1
    shr bl, 1
    shr bl, 1
    mov bh, 0
    shl ax, 1
    shl ax, 1
    shl ax, 1
    shl ax, 1               ; 구 × 16B
    add bx, ax
    mov bl, [cs:bx + bitmap]
    and cl, 7
    shl bl, cl
    and bl, 0x80
    jmp short .store
.notk:
    cmp ah, 0x23            ; 전각 숫자 ０~９
    jne short .store
    sub al, 0x30
    cmp al, 9
    ja  short .store
    call digit
.store:
    mov [cs:flag], bl
    pop ax
    pop cx
    pop bx
.r: retf

narrow:                     ; al = 1바이트 글자. 끝나면 0x7d8e~0x7d97 이 하던 일을 한다
    cmp al, 0x20
    je  short .orig         ; 공백은 받침을 안 바꾼다
    push bx
    xor bl, bl
    cmp al, 0x30
    jb  short .st
    cmp al, 0x39
    ja  short .st
    push ax
    sub al, 0x30
    call digit
    pop ax
.st:
    mov [cs:flag], bl
    pop bx
.orig:
    mov ah, 0x29
    cmp ax, 0x297f
    jb  short .x
    add ax, 0x80
.x: retf

hang:                       ; 글자마다 불린다. ch = 지금 칸 · DS:SI = 다음 바이트. CF=0 둔다 · CF=1 접는다
    cmp ch, 0x22
    jae short .end
    cmp byte [si-1], 0x20   ; ④ 방금 그린 게 반각 공백인가(2바이트 글자 후행은 0x40 이상이라 안 겹친다)
    jne short .keep
    push si
    push dx
    mov dl, ch
.w: mov dh, dl              ; dh = 이 글자 앞 칸
    lodsb
    cmp al, 0x21
    jb  short .fit          ; 공백·제어 = 어절 끝
    mov ah, al
    cmp al, 0x80
    jb  short .n
    cmp al, 0xa0
    jb  short .wd
    cmp al, 0xe0
    jb  short .n
.wd:
    lodsb
    inc dl
.n: inc dl
    cmp dh, 0x22
    jb  short .w            ; 34칸 앞에서 시작하면 이 줄에 든다
    ja  short .nofit
    cmp byte [si], 0x21     ; 딱 34칸 — 어절 **마지막** 글자가 매다는 부호일 때만 든다
    jae short .nofit        ;   (`!!` 는 하나만 매달리고 둘째가 고아가 된다)
    cmp ah, 0x81            ; 아래 ① 과 같은 목록
    jne short .nar
    cmp al, 0x42
    je  short .fit
    jmp short .nofit
.nar:
    cmp ah, 0x21
    je  short .fit
    cmp ah, 0x2e
    je  short .fit
    cmp ah, 0x2c
    je  short .fit
    cmp ah, 0x3f
    je  short .fit
.nofit:
    pop dx
    pop si
    stc                     ; 공백은 이 줄 끝에 이미 그렸다 — 어절을 다음 줄로
    retf
.fit:
    pop dx
    pop si
    clc
    retf
.end:                       ; ch ≥ 34 — 줄 끝 판정
    mov ax, [si]
    cmp al, 0x01            ; ② 명시 줄바꿈이 곧 온다 — 먼저 접으면 빈 줄이 된다(그리는 것 없음)
    je  short .keep
    cmp al, 0x20            ; ③ 접을 자리의 반각 공백은 **먹고** 접는다 — 다음 줄 머리 공백 방지
    jne short .punct
    inc si
    jmp short .wrap
.punct:
    cmp ch, 0x22            ; ① 매달기는 딱 34칸에서만 — 35칸째는 창 테두리다(실측: 테두리를 긁었다)
    jne short .wrap
    cmp al, 0x21
    je  short .keep
    cmp al, 0x2e
    je  short .keep
    cmp al, 0x2c
    je  short .keep
    cmp al, 0x3f
    je  short .keep
    xchg al, ah             ; 원판 그대로 — 전각 `。` 는 좁은 마무리(0x4055)로 34칸에 매단다
    cmp ax, 0x8142
    jne short .wrap
    mov byte [0x4055], 0xff
.keep:
    clc
    retf
.wrap:
    stc
    retf

digit:                      ; al = 0..9 → bl = 받침(0/1). 숫자는 읽는 소리대로(마스터 09-26)
    push cx
    mov cl, al
    mov bx, 0x{josa_tables.digit_mask():04x}
    shr bx, cl
    and bl, 1
    pop cx
    ret

pairs:
{pairs}
bitmap:
    incbin "bitmap.bin"
"""


def near_asm(labels: dict[str, int]) -> str:
    return f"""
BITS 16
org 0x{NEAR_AT:x}
    call 0x{FAR_SEG:x}:0x{labels["pre"]:x}
    call 0x{SJIS2JIS:x}
    call 0x{FAR_SEG:x}:0x{labels["post"]:x}
    ret
"""


FAR_LABELS = ("pre", "post", "narrow", "hang", "digit", "pairs", "bitmap")


def _nasm(src: str, d: Path, name: str, labels: tuple[str, ...] = ()) -> tuple[bytes, dict]:
    """짜고, 라벨 주소는 **nasm 에 묻는다** — 끝에 `dw 라벨…` 을 붙여 한 번 더 짜고 꼬리를 읽는다."""
    (d / "bitmap.bin").write_bytes(bitmap_ku128())
    out = {}
    for tag, text in (("", src), ("l", src + "\n    dw " + ", ".join(labels) + "\n")):
        if tag and not labels:
            continue
        p = d / f"{name}{tag}.asm"
        p.write_text(text, encoding="utf-8")
        r = subprocess.run(
            ["nasm", "-f", "bin", str(p), "-o", str(p.with_suffix(".bin"))],
            capture_output=True,
            check=False,
            cwd=d,
        )
        if r.returncode:
            raise SystemExit("🔴 nasm 실패:\n" + r.stderr.decode())
        out[tag] = p.with_suffix(".bin").read_bytes()
    lab = {}
    if labels:
        lab = dict(
            zip(
                labels, struct.unpack(f"<{len(labels)}H", out["l"][-2 * len(labels) :]), strict=True
            )
        )
    return out[""], lab


def _build() -> tuple[bytes, dict, bytes]:
    with tempfile.TemporaryDirectory() as d:
        far, lab = _nasm(far_asm(), Path(d), "far", FAR_LABELS)
        near, _ = _nasm(near_asm(lab), Path(d), "near")
    _no_near_jcc(far[: lab["pairs"]], 0)
    _no_near_jcc(near, NEAR_AT)
    if NEAR_AT + len(near) > NEAR_END:
        raise SystemExit(f"🔴 발판이 죽은 자리를 넘는다: {len(near)}B > {NEAR_END - NEAR_AT}B")
    room = (H.TRACKS * 8 * 1024) - TABLE_BYTES
    if len(far) > room:
        raise SystemExit(f"🔴 몸통이 로더가 올리는 꼬리를 넘는다: {len(far)}B > {room}B")
    return far, lab, near


def hang_patch(hang: int) -> bytes:
    """`0x7a13~0x7a31` — `call far hang / jnc 돌아가기 / jmp 줄바꿈`, 남는 자리는 nop."""
    with tempfile.TemporaryDirectory() as d:
        src = f"""
BITS 16
org 0x{HANG_AT:x}
    call 0x{FAR_SEG:x}:0x{hang:x}
    jnc short 0x{HANG_END:x}
    jmp near 0x{WRAP:x}
"""
        code, _ = _nasm(src, Path(d), "hang")
    _no_near_jcc(code, HANG_AT)
    room = HANG_END - HANG_AT
    if len(code) > room:
        raise SystemExit(f"🔴 줄 끝 판정이 자리를 넘는다: {len(code)}B > {room}B")
    return code + b"\x90" * (room - len(code))


def far_blob() -> bytes:
    """폰트 표 뒤에 붙일 몸통 — build.py 가 두 폰트 디스크에 같이 싣는다."""
    return _build()[0]


def build_patch() -> list[tuple[int, bytes, bytes]]:
    """→ [(플랫 오프셋, 원본이어야 할 바이트, 새 바이트)] — program 디스크."""
    _far, lab, near = _build()

    def call_near(at: int, to: int) -> bytes:
        rel = to - (at + 3)
        return bytes([0xE8, rel & 0xFF, (rel >> 8) & 0xFF])

    call_far_narrow = bytes([0x9A]) + struct.pack("<HH", lab["narrow"], FAR_SEG)
    if len(near) != len(NEAR_EXPECT):
        raise SystemExit(f"🔴 발판 {len(near)}B 인데 사전조건은 {len(NEAR_EXPECT)}B 만 본다")
    return [
        (NEAR_AT, NEAR_EXPECT, near),
        (WIDE_AT, WIDE_EXPECT, call_near(WIDE_AT, NEAR_AT)),
        (NARROW_AT, NARROW_EXPECT, call_far_narrow + b"\x90" * (10 - 5)),
        (HANG_AT, HANG_EXPECT, hang_patch(lab["hang"])),
    ]


def disasm() -> None:
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs

    far, lab, _near = _build()
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    print(
        f"== 몸통 {FAR_SEG:04x}:0000 — {len(far)}B (FLAG 1 · 코드 {lab['pairs'] - 1} · "
        f"짝 {4 * len(PAIRS)} · 받침 {len(far) - lab['bitmap']})"
    )
    for i in md.disasm(far[1 : lab["pairs"]], 1):
        print(f"  {i.address:04x}: {i.bytes.hex():14s} {i.mnemonic} {i.op_str}")
    for off, _e, new in build_patch():
        print(f"== {off:#07x} (실행 {off + LOAD:#07x})")
        for i in md.disasm(new, off):
            print(f"  {i.address:06x}: {i.bytes.hex():14s} {i.mnemonic} {i.op_str}")


if __name__ == "__main__":
    disasm()
