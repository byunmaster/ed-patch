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
LOAD_BASE = 0x06028000  # `ED.BIN`·`ED2.BIN` 적재 주소

# 🔴 **자리를 손으로 안 적는다** — 편마다 주소가 다르다(ED 0x0607D504 · ED2 0x060648F8).
#    한 번 손으로 적었다가 ED2 에 **참조 0곳**으로 조용히 통과할 뻔했다(2026-08-24).
#    그리기 루프의 시그니처로 찾는다: `mov.b @r8,r1 · shll8 r6 · extu.b r1,r1 · mov.l r11,@-r15`
#    — 두 바이트씩 SJIS 를 조립하는 자리라 파일 안에서 유일하다.
DRAW_SIG = bytes.fromhex("61804618611c2fb6")
DRAW_REFS_EXPECTED = 6  # 두 편 다 여섯 곳에서 부른다(실측)
IMAGE_END = 0x060B0000  # 적재 이미지 끝(0x060AF560) 위로 올림 — 이 위면 워크 버퍼다

PAREN_L, PAREN_R = 0x28, 0x29


def routine(base, table_at, draw, pairs):
    """훅 루틴 어셈블리. `base` 에 놓이고 `table_at` 의 받침 표를 읽는다."""
    a, b, c = pairs  # 각각 (조사A, 조사B)
    src = f"""
        ; ── 들어올 때: r4~r7 = 원 함수 인자, r6 = 문자열 포인터
        mov.l r8,@-r15
        mov.l r9,@-r15
        mov.l r10,@-r15
        mov.l r11,@-r15
        mov   r6,r8                 ; p
        mov.l @(L_END,pc),r0
        cmp/hs r0,r8                ; p >= 적재 이미지 끝?
        bf    done                  ; 아니면 원본이다 — 손대지 않는다
        mov   #0,r9                 ; prev = 0
        mov.l @(L_TAB,pc),r10
    loop:
        mov.b @r8,r0
        extu.b r0,r0
        tst   r0,r0
        bt    done                  ; NUL
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
        bf    picked
        mov.l @(L_HI,pc),r1
        cmp/hs r0,r1                ; prev <= HI
        bf    picked
        mov.l @(L_LO,pc),r1
        sub   r1,r0
        mov.b @(r0,r10),r3          ; 받침 표
        extu.b r3,r3
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
        mov   #0,r0                 ; 당긴 만큼(4B) 꼬리를 지운다 — 옛 일본어가 남지 않게
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        add   #1,r1
        mov.b r0,@r1
        mov   r2,r9                 ; prev = 고른 조사
        add   #2,r8
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
    single:
        add   #1,r8
        bra   loop
        nop
    done:
        mov.l @r15+,r11
        mov.l @r15+,r10
        mov.l @r15+,r9
        mov.l @r15+,r8
        mov.l @(L_DRAW,pc),r0
        jmp   @r0                   ; 꼬리 점프 — PR 그대로라 호출자로 바로 돌아간다
        nop

        .long L_END  {IMAGE_END}
        .long L_TAB  {table_at}
        .long L_81   0x81
        .long L_9F   0x9F
        .long L_E0   0xE0
        .long L_EF   0xEF
        .long L_LO   {josa.code_span()[0]}
        .long L_HI   {josa.code_span()[1]}
        .long L_P1   {(a[0] << 16) | a[1]}
        .long L_P2   {(b[0] << 16) | b[1]}
        .long L_P3   {(c[0] << 16) | c[1]}
        .long L_DRAW {draw}
    """
    return sh2.assemble(src.splitlines(), base)


def find_draw(d):
    """`(그리기 루틴 주소, [리터럴 참조 파일오프셋])` — 시그니처로 찾는다."""
    import struct

    i = d.find(DRAW_SIG)
    assert i >= 0, "그리기 루프 시그니처를 못 찾았다"
    assert d.find(DRAW_SIG, i + 1) < 0, "시그니처가 둘 이상이다 — 더 좁혀야 한다"
    ent = None
    for k in range(i, i - 0x400, -2):  # 함수 시작 = `mov.l Rm,@-r15` 연속의 첫 줄
        w = struct.unpack(">H", d[k : k + 2])[0]
        if (w & 0xFF0F) == 0x2F06 and (struct.unpack(">H", d[k - 2 : k])[0] & 0xFF0F) != 0x2F06:
            ent = LOAD_BASE + k
            break
    assert ent, "그리기 루틴 시작을 못 찾았다"
    pat = ent.to_bytes(4, "big")
    refs, j = [], 0
    while (k := d.find(pat, j)) >= 0:
        refs.append(k)
        j = k + 1
    assert len(refs) == DRAW_REFS_EXPECTED, f"참조가 {len(refs)}곳이다 (기대 {DRAW_REFS_EXPECTED})"
    return ent, refs


def build(fname, table, draw):
    """`(코드+표 바이트, 파일 오프셋, 루틴 RAM 주소, 디스어셈블)`."""
    off, size = FREE[fname]
    at = off + MARGIN
    code_ram = LOAD_BASE + at
    # 표는 루틴 뒤에 붙인다 — 길이를 알아야 하니 두 번 조립한다(주소가 안 바뀔 때까지).
    tab_at = code_ram
    for _ in range(4):
        code, body = routine(code_ram, tab_at, draw, josa.pairs())
        new = code_ram + len(code)
        if new == tab_at:
            break
        tab_at = new
    else:
        raise SystemExit("루틴/표 배치가 안 수렴한다")
    blob = code + table
    assert len(blob) + 2 * MARGIN <= size, f"{fname}: {len(blob)}B > 자리 {size - 2 * MARGIN}B"
    return blob, at, code_ram, sh2.verify(code, code_ram, body)


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    table = josa.build_table()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")

    for fname, (off, size) in FREE.items():
        d = common.read_extent(mm, *files[fname])
        assert not any(d[off : off + size]), f"{fname} 0x{off:X}: 0런이 아니다"
        draw, refs = find_draw(d)
        blob, at, ram, dis = build(fname, table, draw)
        print(
            f"{fname}: 그리기 0x{draw:08X} · 참조 {len(refs)}곳 · "
            f"루틴 0x{ram:08X} {len(blob)}B (표 {len(table)}B · 명령 {len(dis)})"
        )
        if "--dis" in sys.argv:
            for ln in dis:
                print("   ", ln)
        if not apply:
            continue
        lba, fsize = files[fname]
        # ⚠ **다시 돌려도 돌아야 한다** — 게이트(`games/ss-ed1+2/check.sh`)가 체인을 통째로
        #   돌리므로 이미 넣은 이미지 위에서 또 실행된다. 참조는 그때 이미 우리 것이라
        #   `expect=원본` 으로 박아 두면 **두 번째 실행이 죽는다**(2026-08-24).
        #   그래서 사전조건을 「원본이거나 이미 우리 것」으로 둔다 — 챕터 판·HUD 와 같은 규칙.
        _fd, mmd = common.open_image(dst)
        cur = {p: bytes(common.read_extent(mmd, lba, fsize)[p : p + 4]) for p in refs}
        mmd.close()
        _fd.close()
        want, was = ram.to_bytes(4, "big"), draw.to_bytes(4, "big")
        for p, c in cur.items():
            assert c in (was, want), (
                f"{fname} 참조 0x{LOAD_BASE + p:X}: 원본도 우리 것도 아니다 (0x{c.hex()})"
            )
        with open(dst, "r+b") as f:
            common.write_at(f, lba, fsize, at, blob, label=f"{fname} 조사 훅")
            for p in refs:
                common.write_at(
                    f,
                    lba,
                    fsize,
                    p,
                    want,
                    label=f"{fname} 그리기 참조 0x{LOAD_BASE + p:X}",
                    expect=cur[p],
                )
        print(f"   → 넣음 · 참조 {len(refs)}곳을 0x{ram:08X} 로")
    if apply:
        verify(dst, files, table)
    else:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")


def verify(dst, files, table):
    """되읽기 — 루틴 바이트와 바꾼 참조가 그대로 들어갔나."""
    _f2, mm2 = common.open_image(dst)
    for fname in FREE:
        draw, refs = find_draw(common.extract(fname))  # 원본에서 원래 주소를 얻는다
        blob, at, ram, _dis = build(fname, table, draw)
        d = common.read_extent(mm2, *files[fname])
        assert d[at : at + len(blob)] == blob, f"{fname}: 루틴 되읽기 불일치"
        for p in refs:
            got = int.from_bytes(d[p : p + 4], "big")
            assert got == ram, f"{fname} 참조 0x{LOAD_BASE + p:X}: 0x{got:08X} ≠ 0x{ram:08X}"
        print(f"  ✅ 되읽기 {fname} — 루틴 {len(blob)}B · 참조 {len(refs)}곳")
    mm2.close()
    _f2.close()


if __name__ == "__main__":
    main()
