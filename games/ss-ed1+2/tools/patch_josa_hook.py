"""동적 조사 훅 — 표시 직전에 병기(`은(는)`)를 앞말의 받침으로 하나로 접는다.

    python3 tools/patch_josa_hook.py            # 조립·검산만 (넣기 전 안전판)
    python3 tools/patch_josa_hook.py --apply    # 빌드 이미지에 넣는다

⚠ 순서상 **맨 마지막**이다 — 다른 패처가 만든 빌드 사본을 고친다.

## 왜 훅이 필요한가

`%s` 가 런타임 이름이라 빌드 시점엔 앞말의 받침을 모른다. 그래서 정본(`script/system.json`)
은 **병기**로 두고, 화면에 나가기 직전에 버퍼를 한 번 훑어 접는다. PS1 과 같은 설계
(`ps1-ed1+2/tools/patch_josa_hook.py`) — 다른 건 CPU 와 붙이는 방식뿐이다.

## 붙이는 방식 — 코드를 안 고치고 **포인터만 바꾼다**

문자열 그리기(`0x0607D504`)를 부르는 자리는 전부 **리터럴 풀에 그 주소를 담아 `jsr`** 한다
(실측 6곳). 그 여섯 개를 우리 루틴 주소로 바꾸면 끝이다 — 원 명령을 한 바이트도 안 건드리고,
루틴은 일을 마친 뒤 원래 함수로 **꼬리 점프**한다(PR 이 그대로라 호출자에게 바로 돌아간다).
🔴 트램폴린을 안 심으니 「원 명령 보존·복원」이라는 사고 자리가 통째로 없다.

## 안전 조건 둘

1. **적재 이미지 안이면 무동작.** `r6` 이 원본 문자열을 직접 가리키는 호출이 있다
   (실측 `r6 = 0x060A5FE8`). 거기서 제자리로 접으면 **원본이 영구히 망가진다** —
   다음 회차엔 이미 접힌 걸 또 접는다. 그래서 `r6 >= IMAGE_END` 일 때만 돈다.
2. **병기가 없으면 무동작.** 패턴이 안 맞으면 아무것도 안 쓴다 — 멱등이라 같은 버퍼를
   여러 번 그려도 안전하다.

## 놓을 자리

`ED.BIN` 0x7E708 / `ED2.BIN` 0x63CC8 의 2,560B 0런. **가리키는 리터럴도 pc 상대 로드도
0곳**이고(전량 스캔) 실기에서 읽기·쓰기 브레이크포인트로 2,000프레임을 돌려도 안 걸렸다.
⚠ 계산으로 만든 주소까지는 못 배제하므로 **앞뒤로 여유를 두고 가운데**를 쓴다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import josa
import sh2

# ── 자리 (실측: docs/devlog.md 2026-08-24 (15)) ──────────────────────────────
FREE = {  # 파일 → (0런 시작 오프셋, 크기)
    "/ED.BIN": (0x7E708, 2560),
    "/ED2.BIN": (0x63CC8, 2560),
}
MARGIN = 0x40  # 양 끝 여유 — 계산 주소가 가장자리를 스치더라도 안 물리게
STUB_SPACE = 64  # 🔴 0런 끝쪽에 `patch_msgwrap` 의 드로어 훅 스텁(56B)이 앉는 몫 — 이 훅은 그 앞까지만 쓴다
LOAD_BASE = 0x06028000  # `ED.BIN`·`ED2.BIN` 적재 주소

# 🔴 **자리를 손으로 안 적는다** — 편마다 주소가 다르다(ED 0x0607D504 · ED2 0x060648F8).
#    한 번 손으로 적었다가 ED2 에 **참조 0곳**으로 조용히 통과할 뻔했다(2026-08-24).
#    그리기 루프의 시그니처로 찾는다: `mov.b @r8,r1 · shll8 r6 · extu.b r1,r1 · mov.l r11,@-r15`
#    — 두 바이트씩 SJIS 를 조립하는 자리라 파일 안에서 유일하다.
DRAW_SIG = bytes.fromhex("61804618611c2fb6")
DRAW_REFS_EXPECTED = 6  # 두 편 다 여섯 곳에서 부른다(실측)

# 🔴 **줄 나누기**(ED 0x0607CD64 · ED2 0x06064158) — **그리기보다 앞이다.**
#    ⚠ **여기엔 안 건다**(`SKIP_SITES`, 2026-09-01). 찾기만 하고 시그니처 검산에 쓴다.
#    시그니처: `mov r4,r11 · mov.l r5,@r14 · mov #29,r12 · mov #0,r8`
#    (`#29` 가 곧 한 줄 예산이라 이 함수가 「나누는 자리」라는 증거다)
#    💡 안 걸어서 이 함수는 **병기를 그대로** 재는데, 그게 오히려 맞다 — 우리 조판기
#    (`typeset_scn.COLS = 14` 전각 = 28B ≤ 29B)도 병기를 그대로 세기 때문이다. 걸었을
#    때가 불일치였다(엔진은 접힌 2B, 우리는 6B ⇒ 우리 쪽이 늘 보수적).
SPLIT_SIG = bytes.fromhex("6b432e52ec1de800")
SPLIT_REFS_EXPECTED = 1  # 두 편 다 한 곳에서만 부른다(실측)

# 🔴 **접기**(prewrap — ED 0x0607CE74 · ED2 0x06064268, 2026-09-27) — 메시지 창의 줄 나누기.
#    **나누기보다 앞**이다: 메시지 루틴이 `strcpy → prewrap → … → 스플리터(→ 나누기)` 로 돈다.
#    병기를 여기서 접어야 줄 나누기가 **접힌 길이**로 잰다 — 안 그러면 병기마다 4B 를 헛셈해
#    일찍 넘기고, 29B 경계에 걸친 병기는 반쪽이 다음 줄로 샜다(마스터 캡처 「요슈아의 눈」).
#    ⚠ 이 진입점은 **나누기와 달리 안전하다** — `r4` 가 늘 메시지 루틴의 스택 버퍼(128B,
#      방금 `strcpy` 로 채운 것)라 「아직 안 채워진 회차」가 없다. 부르는 곳도 한 곳뿐이다.
#    꼬리 점프 목적지는 원 prewrap 주소 그대로 — 그 본체는 `patch_msgwrap` 이 어절 단위
#    루틴으로 덮어쓴다(규칙 정본 `msgwrap.py`).
from patch_msgwrap import SIG as WRAP_SIG

WRAP_REFS_EXPECTED = 1

DRY_SITES = set(os.environ.get("JOSA_DRY", "나누기").split(",")) - {""}  # 🔴 나누기는 무동작 (위)
SCAN_LIMIT = 256  # 한 버퍼에서 훑을 최대 바이트 — 한 창이 29B×6줄이라 넉넉하다
WORKRAM_TOP = 0x06100000  # 워크램 하이의 끝 — 이 위는 유효한 버퍼가 아니다


# 🔴 **적재 이미지 끝은 편마다 다르다 — 상수로 박지 않는다.**
#    ED.BIN 0x875E4 → 0x060AF5E4 · ED2.BIN 0x6CFC8 → **0x06094FC8**. ED1 기준 상수
#    (0x060B0000)를 두 편에 같이 쓰는 바람에 **ED2 는 훅이 통째로 무동작**했다
#    — 메시지 버퍼가 그 상수 아래라 「원본이다」로 걸러졌다(2026-08-27 유저 캡처:
#    「아트라스은(는)」·「레스을(를)」이 병기 그대로 화면에 떴다).
#    파일 크기에서 유도하고 4KB 로 올린다.
def image_end(d):
    """`d`(그 편의 본체 파일) 가 적재됐을 때의 끝 — 이 위면 워크 버퍼다."""
    return (LOAD_BASE + len(d) + 0xFFF) & ~0xFFF


PAREN_L, PAREN_R = 0x28, 0x29


def routine(base, table_at, half_at, back, pairs, *, arg="r6", pad=True, dry=False, end=None):
    """훅 루틴 어셈블리. `base` 에 놓이고 `table_at` 의 받침 표를 읽는다.

    `back` 은 일을 마친 뒤 꼬리 점프할 원 함수, `arg` 는 그 함수가 문자열을 받는 레지스터.
    ⚠ **두 자리에 건다** — 그리기(`r6`)와 줄 나누기(`r4`). 인자 레지스터도 돌아갈 곳도
      다르므로 루틴을 둘 굽는다(표는 하나를 같이 본다).

    `pad` 는 접고 남은 네 바이트를 반각 공백으로 채울지다.
      · 나누기 진입점(`pad=False`): 나누기가 **접힌 길이**를 보므로 채울 이유가 없다.
      · 그리기 진입점(`pad=True`): 나누기를 안 거치고 바로 그려지는 경로의 안전망.
        여기까지 병기가 살아 왔다면 이미 옛 길이로 자리가 잡힌 뒤라 폭을 되돌려야 한다.
    """
    if dry:
        # 🔴 **무동작 진입점은 되돌림 세 줄이다**(2026-09-27). 예전엔 루틴 전체(424B)를 굽고
        #    맨 앞에 `bra done` 만 넣었는데, 그 몸통은 **한 번도 안 도는 자리 차지**였다 —
        #    `접기` 진입점을 넣을 자리가 그 424B 였다. 동작은 같다(버퍼를 안 보고 꼬리 점프).
        return sh2.assemble(
            ["mov.l @(L_BACK,pc),r0", "jmp @r0", "nop", f".long L_BACK {back}"], base
        )
    a, b, c = pairs  # 각각 (조사A, 조사B)
    PAD = (
        """        ; 🔴 **꼬리를 NUL 이 아니라 반각 공백 넷으로 채운다.** r1 은 방금 옮겨 적은 종단이다.
        ;    여기까지 병기가 살아 왔다면 자리는 **접기 전 길이**로 잡힌 뒤다 — 줄어든 두 칸에
        ;    글리프 0 이 찍혀 화면에 **흰 네모**가 남았다(2026-08-26 실기, 원판엔 없다).
        ;    공백 넷(=전각 두 칸)으로 폭을 되돌리고 **종단은 원래 자리**에 둔다.
        mov   #0x20,r0
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov   #0,r0
        mov.b r0,@r1                ; 원래 종단 자리에 NUL — 길이가 그대로다
"""
        if pad
        else ""
    )
    DRY = "        bra   done\n        nop\n" if dry else ""
    src = f"""
        ; ── 들어올 때: r4~r7 = 원 함수 인자
        mov.l r8,@-r15
        mov.l r9,@-r15
        mov.l r10,@-r15
        mov.l r11,@-r15
        mov.l r12,@-r15
        mov   {arg},r8              ; p
{DRY}        ; 🔴 **순회 상한.** 버퍼가 NUL 종단이라는 보장이 없는 자리에도 건다 — 없으면
        ;    워크램을 끝까지 훑다가 게임이 선다(2026-08-26 실측: 나누기 진입점에서 물렸다).
        mov   r8,r12
        mov.l @(L_LIM,pc),r1
        add   r1,r12                ; r12 = 훑기 끝
        mov.l @(L_END,pc),r0
        cmp/hs r0,r8                ; p >= 적재 이미지 끝?
        bt    chk_top               ; 아니면 원본이다 — 손대지 않는다
        bra   done                  ; (`bf done` 은 8비트 변위 밖이라 못 쓴다)
        nop
    chk_top:
        ; 🔴 **위쪽 경계도 막는다.** 가드가 아래쪽 하나뿐이면 **워크램 밖 쓰레기 포인터가
        ;    그대로 통과한다**(unsigned 비교라 0x25A32A40 같은 값이 「더 크다」로 잡힌다).
        ;    나누기 진입점의 `r4` 는 아직 안 채워진 회차가 있어 실제로 물렸다(2026-08-26).
        mov.l @(L_TOP,pc),r0
        cmp/hs r0,r8                ; p >= 워크램 끝?
        bf    inrange                ; (`bt done` 은 8비트 변위 밖이라 못 쓴다)
        bra   done
        nop
    inrange:
        mov   #0,r9                 ; prev = 0
        mov.l @(L_TAB,pc),r10
    loop:
        cmp/hs r12,r8               ; 상한을 넘었나
        bt    out
        mov.b @r8,r0
        extu.b r0,r0
        tst   r0,r0
        bt    out                   ; NUL
        mov.l @(L_81,pc),r1
        cmp/hs r1,r0                ; r0 >= 0x81
        bf    single
        mov.l @(L_9F,pc),r1
        cmp/hs r0,r1                ; r0 <= 0x9F
        bt    two
        mov.l @(L_E0,pc),r1
        cmp/hs r1,r0                ; r0 >= 0xE0
        bf    single
        mov.l @(L_EF,pc),r1
        cmp/hs r0,r1                ; r0 <= 0xEF
        bf    single
    two:
        shll8 r0
        mov   r8,r1
        add   #1,r1
        mov.b @r1,r1
        extu.b r1,r1
        or    r1,r0                 ; r0 = 앞 두 바이트(조사A 후보)
        mov   r0,r11
        mov   r8,r1
        add   #2,r1
        mov.b @r1,r1
        extu.b r1,r1
        mov   #{PAREN_L},r2
        cmp/eq r2,r1
        bf    notpair
        mov   r8,r1
        add   #5,r1
        mov.b @r1,r1
        extu.b r1,r1
        mov   #{PAREN_R},r2
        cmp/eq r2,r1
        bf    notpair
        mov   r8,r1
        add   #3,r1
        mov.b @r1,r2
        extu.b r2,r2
        shll8 r2
        add   #1,r1
        mov.b @r1,r1
        extu.b r1,r1
        or    r1,r2                 ; r2 = 괄호 안(조사B 후보)
        mov   r11,r3
        shll16 r3
        or    r2,r3                 ; r3 = (A<<16)|B
        mov.l @(L_P1,pc),r1
        cmp/eq r1,r3
        bt    match
        mov.l @(L_P2,pc),r1
        cmp/eq r1,r3
        bt    match
        mov.l @(L_P3,pc),r1
        cmp/eq r1,r3
        bt    match
        bra   notpair
        nop
    match:
        mov   #0,r3                 ; 기본값 = 무받침
        mov.l @(L_LO,pc),r1
        mov   r9,r0
        cmp/hs r1,r0                ; prev >= LO
        bf    half                  ; 우리 슬롯 구간 밖 — 반각 표를 본다
        mov.l @(L_HI,pc),r1
        cmp/hs r0,r1                ; prev <= HI
        bf    half
        mov.l @(L_LO,pc),r1
        sub   r1,r0
        ; 🔴 **받침 표는 니블이다** — 한 바이트에 두 글자(짝수 자리 = 하위 4비트).
        ;    바이트 하나씩 쓰다 씬 대사가 들어오며 자리를 넘겼다(2026-08-27).
        ;    ⚠ SH-2 엔 가변 시프트가 없어 비트맵(1/8)은 8분기가 붙는다 — 니블이 값싸다.
        mov   r0,r1                 ; r1 = 자리 번호(홀짝 판정용)
        shlr  r0                    ; r0 = 자리 >> 1  (바이트 색인)
        mov.b @(r0,r10),r3
        extu.b r3,r3
        mov   r1,r0
        tst   #1,r0                 ; 짝수면 T=1 → 하위 니블 그대로
        bt    lownib
        shlr2 r3
        shlr2 r3                    ; 홀수 → 상위 니블을 내린다
    lownib:
        mov   r3,r0
        and   #1,r0
        mov   r0,r3
        bra   picked
        nop
        ; ⚠ 반각 표 조회는 **루틴 끝**에 뒀다 — 여기 두면 `loop` 의 `bt out` 이 8비트 변위를
        ;   넘는다(실측 d=131). 중계 한 칸이 싸다.
    half:
        bra   halftab
        nop
    picked:
        tst   r3,r3
        bt    write                 ; 무받침 → r2(조사B) 그대로
        mov   r11,r2                ; 받침 → 조사A
    write:
        mov   r2,r0
        shlr8 r0
        mov.b r0,@r8
        mov   r8,r1
        add   #1,r1
        mov.b r2,@r1
        mov   r8,r1
        add   #2,r1                 ; dst
        mov   r8,r3
        add   #6,r3                 ; src — 네 바이트를 왼쪽으로 당긴다
    shift:
        mov.b @r3,r0
        mov.b r0,@r1
        extu.b r0,r0
        tst   r0,r0
        bt    shifted
        add   #1,r1
        add   #1,r3
        bra   shift
        nop
    shifted:
{PAD}        mov   r2,r9                 ; prev = 고른 조사
        add   #2,r8
        bra   loop
        nop
    out:                            ; ⚠ `bt` 는 8비트 변위뿐이라 끝까지 못 간다 — 중계한다
        bra   done
        nop
    single:
        ; ⚠ **숫자·대문자만** prev 를 갱신한다. 나머지 반각·제어는 **건드리지 않는다** —
        ;   이름과 조사 사이엔 `%c` 색 코드가 늘 껴서(`%c%s%c은(는)`), 지우면 이름을 못 보고
        ;   전부 무받침이 된다. 색 코드는 이 구간 밖이라 안 걸린다.
        mov   #{josa.HALF_LO},r1
        cmp/hs r1,r0
        bf    adv1
        mov   #{josa.HALF_HI},r1
        cmp/hs r0,r1
        bf    adv1
        mov   r0,r9                 ; prev = 이 반각 한 글자
    adv1:
        add   #1,r8
        bra   loop
        nop
    notpair:
        mov.l @(L_LO,pc),r1
        mov   r11,r0
        cmp/hs r1,r0
        bf    adv2
        mov.l @(L_HI,pc),r1
        cmp/hs r0,r1
        bf    adv2
        mov   r11,r9                ; prev = 이 음절
    adv2:
        add   #2,r8
        bra   loop
        nop
        ; 🔴 **반각으로 끝나는 이름** — 개체 접미(`슬라임A`)가 그렇다. 한글 표는 우리 슬롯
        ;    코드 구간만 덮으므로 여기서 따로 본다. 한 바이트에 한 글자(43B) — 니블로 접어도
        ;    21B 를 아낄 뿐인데 홀짝 분기가 붙는다(**명령 수가 공간보다 비싸다**).
    halftab:
        mov   #{josa.HALF_LO},r1
        cmp/hs r1,r0                ; prev >= '0'
        bf    hdone
        mov   #{josa.HALF_HI},r1
        cmp/hs r0,r1                ; prev <= 'Z'
        bf    hdone
        mov   #{josa.HALF_LO},r1
        sub   r1,r0                 ; r0 = 표 자리
        mov.l @(L_HTAB,pc),r1
        mov.b @(r0,r1),r3
        extu.b r3,r3
    hdone:
        bra   picked
        nop
    done:
        mov.l @r15+,r12
        mov.l @r15+,r11
        mov.l @r15+,r10
        mov.l @r15+,r9
        mov.l @r15+,r8
        mov.l @(L_BACK,pc),r0
        jmp   @r0                   ; 꼬리 점프 — PR 그대로라 호출자로 바로 돌아간다
        nop

        .long L_END  {end}
        .long L_TAB  {table_at}
        .long L_HTAB {half_at}
        .long L_81   0x81
        .long L_9F   0x9F
        .long L_E0   0xE0
        .long L_EF   0xEF
        .long L_TOP  {WORKRAM_TOP}
        .long L_LIM  {SCAN_LIMIT}
        .long L_LO   {josa.code_span()[0]}
        .long L_HI   {josa.code_span()[1]}
        .long L_P1   {(a[0] << 16) | a[1]}
        .long L_P2   {(b[0] << 16) | b[1]}
        .long L_P3   {(c[0] << 16) | c[1]}
        .long L_BACK {back}
    """
    return sh2.assemble(src.splitlines(), base)


def find_fn(d, sig, expect, what):
    """`(함수 주소, [리터럴 참조 파일오프셋])` — 시그니처로 찾는다."""
    import struct

    i = d.find(sig)
    assert i >= 0, f"{what} 시그니처를 못 찾았다"
    assert d.find(sig, i + 1) < 0, f"{what} 시그니처가 둘 이상이다 — 더 좁혀야 한다"
    ent = None
    for k in range(i, i - 0x400, -2):  # 함수 시작 = `mov.l Rm,@-r15` 연속의 첫 줄
        w = struct.unpack(">H", d[k : k + 2])[0]
        if (w & 0xFF0F) == 0x2F06 and (struct.unpack(">H", d[k - 2 : k])[0] & 0xFF0F) != 0x2F06:
            ent = LOAD_BASE + k
            break
    assert ent, f"{what} 시작을 못 찾았다"
    pat = ent.to_bytes(4, "big")
    refs, j = [], 0
    while (k := d.find(pat, j)) >= 0:
        refs.append(k)
        j = k + 1
    assert len(refs) == expect, f"{what} 참조가 {len(refs)}곳이다 (기대 {expect})"
    return ent, refs


# 🔴 **나누기 진입점에는 안 건다** (2026-09-01 확정) — **같은 자리에서 두 번 물렸다.**
#    이 자리의 `r4` 는 **아직 안 채워진 회차가 있다**. 그래서 「워크램 안이고 적재 이미지
#    위」라는 범위 가드를 세워도 **남의 버퍼가 그대로 통과한다** — 가드는 주소가 유효한지만
#    보지 그게 우리 문안인지는 못 본다.
#      · 2026-08-26 — 워크램을 끝까지 훑다가 게임이 섰다 (상한 256B 로 막았다)
#      · 2026-09-01 — 본편 BGM 이 통째로 안 나왔다 (사운드 자료를 밟은 것으로 본다)
#    빌드 이분으로 범인을 좁혔다: 훅 없음 ✅ · 설치만 하고 무동작 ✅ · 나누기만 무동작 ✅ ·
#    둘 다 동작 ❌ ⇒ **나누기 진입점의 동작**이 유일한 차이였다.
#    ⇒ 상한을 더 줄이는 건 확률을 낮출 뿐 성질을 안 바꾼다. **이 자리에서 훑지 않는다.**
#
# ✅ **그리기 진입점만으로 기능은 산다.** 조사는 화면에 나가기 직전에 접히고, `pad` 가 줄어든
#    두 칸을 반각 공백 넷으로 되돌려 폭을 지킨다. 나누기를 안 거치면 줄 나눔이 **병기 길이**
#    (`은(는)` = 접힌 뒤보다 길다) 기준이 되는데, 이건 **보수적**이라 줄이 넘치지 않는다 —
#    일찍 넘길 뿐이다. 병기가 남는 자리는 `%s` 뒤뿐이라(이름이 런타임에 들어와 조사를 미리
#    못 정하는 자리) 영향 범위도 거기까지다.
#
# 🔴 **그런데 「안 건다」가 아니라 「걸되 즉시 되돌린다」여야 한다**(2026-09-01 실기, 유저 확인).
#    설치 자체를 빼면 BGM 이 **다시** 죽는다 — 원본에 더 가까운 쪽이 죽으므로 설명이 안 된다:
#
#        나누기 설치 안 함   c998b0452638 · 1ec7dfcfe3b9   BGM ❌
#        나누기 설치 + 무동작 2c0ee330b3ef                  BGM ✅   (다른 건 전부 같다)
#
#    ⚠ 빌드는 결정적이다 — 전체 체인과 「훅만 덧씌움」이 **같은 해시**를 냈다. 즉 변수는
#      이 하나뿐이었다. 아직 **왜인지 모른다.** 가설은 훅 자리(0런 2,560B)가 진짜 빈 공간이
#      아니라는 것이다(`docs/reference/our-findings.md` 「빈 공간의 VAB 함정」) — 설치하면
#      루틴이 424B 더 차서 그 자리를 덮는데, 그 차이가 소리를 가른다.
#    ⇒ 모르는 채로 두지 말고 **실측을 따른다.** 되돌리려면 BGM 을 실기로 보이고 함께 지운다.
SKIP_SITES = set(os.environ.get("JOSA_SKIP", "").split(",")) - {""}  # 진단용 — 기본은 안 뺀다


def find_sites(d):
    """`{이름: (원 함수 주소, [참조 오프셋], 인자 레지스터, 꼬리 채움)}`.

    ⚠ **찾기는 둘 다 한다** — 시그니처가 그대로인지가 이미지 검산이라, 안 거는 자리도 찾아
      두면 원본이 바뀌었을 때 여기서 먼저 운다. 거는 자리만 `SKIP_SITES` 로 거른다.
    """
    draw, dref = find_fn(d, DRAW_SIG, DRAW_REFS_EXPECTED, "그리기")
    split, sref = find_fn(d, SPLIT_SIG, SPLIT_REFS_EXPECTED, "줄 나누기")
    wrap, wref = find_fn(d, WRAP_SIG, WRAP_REFS_EXPECTED, "접기")
    sites = {
        "나누기": (split, sref, "r4", False),
        "그리기": (draw, dref, "r6", True),
        "접기": (wrap, wref, "r4", False),
    }
    return {k: v for k, v in sites.items() if k not in SKIP_SITES}


def build(fname, table, sites, end):
    """`(코드+표 바이트, 파일 오프셋, {이름: (루틴 주소, 디스어셈블)})`.

    ⚠ 루틴을 **둘** 굽는다(나누기·그리기). 인자 레지스터도 돌아갈 곳도 다르다.
      표는 하나를 같이 본다 — 1,319B 라 두 벌 뜨면 자리가 모자란다.
    """
    off, size = FREE[fname]
    at = off + MARGIN
    order = list(sites)
    # 표는 루틴들 뒤에 붙는다 — 길이를 알아야 하니 주소가 안 바뀔 때까지 다시 조립한다.
    tab_at = LOAD_BASE + at
    half = josa.build_half_table()
    for _ in range(4):
        blobs, ram, cur = {}, {}, LOAD_BASE + at
        for name in order:
            back, _refs, arg, pad = sites[name]
            code, body = routine(
                cur,
                tab_at,
                tab_at + len(table),  # 반각 표는 한글 표 바로 뒤
                back,
                josa.pairs(),
                arg=arg,
                pad=pad,
                dry=(name in DRY_SITES),
                end=end,
            )
            blobs[name] = (code, body)
            ram[name] = cur
            cur += len(code)
        if cur == tab_at:
            break
        tab_at = cur
    else:
        raise SystemExit("루틴/표 배치가 안 수렴한다")
    blob = b"".join(blobs[n][0] for n in order) + table + half
    assert len(blob) + 2 * MARGIN + STUB_SPACE <= size, (
        f"{fname}: {len(blob)}B > 자리 {size - 2 * MARGIN - STUB_SPACE}B (끝쪽 {STUB_SPACE}B 는 훅 스텁 몫)"
    )
    dis = {n: (ram[n], sh2.verify(blobs[n][0], ram[n], blobs[n][1])) for n in order}
    return blob, at, dis


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    table = josa.build_table()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    # 🔴 **쓰기 자리는 빌드 이미지가 정한다** — 규칙은 `common.dst_files` 가 정본이다.
    files = common.dst_files(dst, mm)
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")

    for fname, (off, size) in FREE.items():
        d = common.read_extent(mm, *files[fname])
        assert not any(d[off : off + size]), f"{fname} 0x{off:X}: 0런이 아니다"
        sites = find_sites(d)
        end = image_end(d)
        blob, at, dis = build(fname, table, sites, end)
        print(f"{fname}: 루틴 {len(sites)}벌 {len(blob)}B (표 {len(table)}B · 적재 끝 0x{end:08X})")
        for name, (back, refs, arg, pad) in sites.items():
            ram, lines = dis[name]
            print(
                f"   {name}: 원 함수 0x{back:08X}({arg}) · 참조 {len(refs)}곳 · "
                f"루틴 0x{ram:08X} 명령 {len(lines)}{' · 꼬리 채움' if pad else ''}"
            )
            if "--dis" in sys.argv:
                for ln in lines:
                    print("      ", ln)
        if not apply:
            continue
        lba, fsize = files[fname]
        # ⚠ **다시 돌려도 돌아야 한다** — 게이트(`games/ss-ed1+2/check.sh`)가 체인을 통째로
        #   돌리므로 이미 넣은 이미지 위에서 또 실행된다. 참조는 그때 이미 우리 것이라
        #   `expect=원본` 으로 박아 두면 **두 번째 실행이 죽는다**(2026-08-24).
        #   그래서 사전조건을 「원본이거나 이미 우리 것」으로 둔다 — 챕터 판·HUD 와 같은 규칙.
        _fd, mmd = common.open_image(dst)
        cur = {}
        for _back, refs, _arg, _pad in sites.values():
            for pp in refs:
                cur[pp] = bytes(common.read_extent(mmd, lba, fsize)[pp : pp + 4])
        mmd.close()
        _fd.close()
        lo_ram, hi_ram = LOAD_BASE + off, LOAD_BASE + off + size
        with open(dst, "r+b") as f:
            common.write_at(f, lba, fsize, at, blob, label=f"{fname} 조사 훅")
            for name, (back, refs, _arg, _pad) in sites.items():
                ram = dis[name][0]
                want, was = ram.to_bytes(4, "big"), back.to_bytes(4, "big")
                for pp in refs:
                    # ⚠ 사전조건은 「원본이거나 **우리 자리 안**」이다 — 「원본이거나 지금 이
                    #   루틴 주소」로 박으면 **루틴 배치를 바꾼 날 재실행이 죽는다**(실측
                    #   2026-08-26: 진입점을 둘로 늘렸더니 옛 주소가 남아 있어 막혔다).
                    got = int.from_bytes(cur[pp], "big")
                    assert cur[pp] == was or lo_ram <= got < hi_ram, (
                        f"{fname} {name} 참조 0x{LOAD_BASE + pp:X}: "
                        f"원본도 우리 자리도 아니다 (0x{cur[pp].hex()})"
                    )
                    common.write_at(
                        f,
                        lba,
                        fsize,
                        pp,
                        want,
                        label=f"{fname} {name} 참조 0x{LOAD_BASE + pp:X}",
                        expect=cur[pp],
                    )
        n = sum(len(v[1]) for v in sites.values())
        print(f"   → 넣음 · 참조 {n}곳")
    if apply:
        verify(dst, files, table)
    else:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")


def verify(dst, files, table):
    """되읽기 — 루틴 바이트와 바꾼 참조가 그대로 들어갔나."""
    _f2, mm2 = common.open_image(dst)
    for fname in FREE:
        d = common.extract(fname)  # 원본에서 원래 주소를 얻는다
        sites = find_sites(d)
        blob, at, dis = build(fname, table, sites, image_end(d))
        d = common.read_extent(mm2, *files[fname])
        assert d[at : at + len(blob)] == blob, f"{fname}: 루틴 되읽기 불일치"
        n = 0
        for name, (_back, refs, _arg, _pad) in sites.items():
            ram = dis[name][0]
            for pp in refs:
                got = int.from_bytes(d[pp : pp + 4], "big")
                assert got == ram, (
                    f"{fname} {name} 참조 0x{LOAD_BASE + pp:X}: 0x{got:08X} ≠ 0x{ram:08X}"
                )
                n += 1
        print(f"  ✅ 되읽기 {fname} — 루틴 {len(blob)}B · 참조 {n}곳")
    mm2.close()
    _f2.close()


if __name__ == "__main__":
    main()
