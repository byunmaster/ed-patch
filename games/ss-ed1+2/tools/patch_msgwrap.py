"""메시지 창 줄 나누기 — 원 prewrap 본체를 어절 단위 루틴으로 덮어쓴다.

    python3 tools/patch_msgwrap.py            # 조립·검산만
    python3 tools/patch_msgwrap.py --dis      # + 디스어셈블
    python3 tools/patch_msgwrap.py --apply    # 빌드 이미지에 넣는다

규칙의 정본은 `msgwrap.wrap` 이다 — 여기는 그걸 **한 줄씩 옮긴 것**이고,
`tests/test_msgwrap.py` 가 작은 SH-2 해석기로 이 바이트를 돌려 `wrap` 과 대조한다.

## 붙이는 자리 — **원 함수 자리 그대로**

prewrap(ED `0x0607CE74` · ED2 `0x06064268`)을 부르는 곳은 편마다 **한 곳**(메시지 루틴의
리터럴)뿐이고, 함수는 자기 리터럴 풀까지 556B 로 닫혀 있다. 그래서 새 자리를 찾지 않고
**본체를 덮어쓴다** — 빈 자리(0런)는 조사 훅이 이미 거의 다 썼고, 남은 0런 둘은 가리키는
포인터가 있는 **버퍼**였다(2026-09-27 전수: `0x0609CA1C` · `0x060A2E44`).
병기 접기는 이 앞에서 조사 훅의 `접기` 진입점이 한다(리터럴을 거기로 돌리고, 거기서 이
주소로 꼬리 점프) — 그래서 여기 들어오는 버퍼엔 병기가 없다.

⚠ **잎 함수다** — 아무것도 부르지 않고 PR 을 안 건드린다(조사 훅이 PR 그대로 꼬리 점프해
  들어오므로 `rts` 가 곧 메시지 루틴으로 돌아간다). 스택에 출력 버퍼 128B 를 잡는다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import msgwrap
import sh2

LOAD_BASE = 0x06028000
# 시그니처 = 원 함수 본문 첫머리(스택 잡기 뒤) — 두 편이 같은 코드다(실측 2026-09-27)
SIG = bytes.fromhex("938d3f3c6ef36b43e901ea00e800e30792866083300c6183")
SIG_AT = 0x10  # 함수 시작에서 시그니처까지
SIZE = 0x22C  # 원 함수 = 본문 + 리터럴 풀 (0x0607CE74 ~ 0x0607D0A0)
FILES = ("/ED.BIN", "/ED2.BIN")


def source():
    """어셈블리 — `msgwrap.wrap` 과 같은 순서. 레지스터:

    r4 원 버퍼(끝에 되쓴다) · r8 src · r9 출력 시작 · r10 출력 커서 · r11 used ·
    r12 cand(0=없음) · r13 cused · r14 ls · r5 last(0=없음) · r6 auto · r7 멈춤 자리
    """
    L, S = msgwrap.LIMIT, msgwrap.STOP
    close_half = "\n".join(
        f"        cmp/eq #{c},r0\n        bt    close" for c in msgwrap.CLOSE_HALF
    )
    close_sjis = "\n".join(
        f"        cmp/eq #{c & 0xFF},r0\n        bt    close" for c in msgwrap.CLOSE_SJIS
    )
    close_half_back2 = "\n".join(
        f"        cmp/eq #{c},r0\n        bt    back2" for c in msgwrap.CLOSE_HALF
    )
    hang_tail = "\n".join(
        f"        cmp/eq #{c},r0\n        bt    hanglim" for c in msgwrap.HANG_TAIL
    )
    lead = msgwrap.CLOSE_SJIS[0] >> 8
    assert all(c >> 8 == lead for c in msgwrap.CLOSE_SJIS)
    return f"""
        mov.l r8,@-r15
        mov.l r9,@-r15
        mov.l r10,@-r15
        mov.l r11,@-r15
        mov.l r12,@-r15
        mov.l r13,@-r15
        mov.l r14,@-r15
        add   #-{msgwrap.BUF},r15
        mov   r4,r8
        mov   r15,r9
        mov   r9,r10
        mov   #0,r11
        mov   #0,r12
        mov   r9,r14
        mov   #0,r5
        mov   #0,r6
        mov   r9,r7
        add   #{S},r7
    loop:
        cmp/hs r7,r10               ; 출력이 멈춤 자리에 닿았나
        bt    fin_r
        mov.b @r8,r0
        extu.b r0,r0
        tst   r0,r0
        bt    fin_r
        cmp/eq #{msgwrap.NL},r0
        bf    not_nl
        add   #1,r8
        tst   r6,r6
        bf    loop                  ; 규칙 4 — 자동 개행 직후의 명시 개행은 버린다
        mov.b r0,@r10
        add   #1,r10
        mov   #0,r11
        mov   #0,r12
        mov   #0,r5
        bra   loop
        mov   r10,r14               ; (지연 슬롯) ls = 여기
    fin_r:
        bra   fin
        nop
    not_nl:
        mov   r0,r1
        add   #-1,r1
        mov   #3,r2
        cmp/hs r2,r1                ; c-1 >= 3 ?  (아니면 1..3 = 폭 없는 색)
        bf    zw
        cmp/eq #14,r0
        bt    zw
        cmp/eq #{msgwrap.SP},r0
        bt    space_r
        mov   #1,r3                 ; n = 1
        mov   r0,r1
        add   #-32,r1
        mov   #95,r2
        cmp/hs r2,r1                ; 0x20..0x7E ?
        bf    gotn
        mov   r0,r1
        add   #95,r1
        extu.b r1,r1
        mov   #63,r2
        cmp/hs r2,r1                ; 0xA1..0xDF ?
        bf    gotn
        mov   #2,r3
    gotn:
        mov   #{L},r2               ; lim = LIMIT
        mov   #1,r1
        cmp/eq r1,r3
        bf    gotlim                ; 반각만 29열 후보
{hang_tail}
        bra   gotlim
        nop
    hanglim:
        mov   #{L + 1},r2           ; 반각 꼬리 부호는 29열까지 (드로어 훅과 한 몸)
    gotlim:
        cmp/ge r2,r11               ; used >= lim ?
        bf    place
        ; 규칙 1(어절 후퇴, 마스터 09-30 번복 — 로그도 어절 단위): 마지막 공백에서 끊는다.
        ; 공백 경로(`묶음째 내린다`)와 같은 꼴 — `msgwrap.wrap` 의 `if retreat and cand >= 0`.
        tst   r12,r12
        bt    rule3                 ; 끊을 공백이 없다 → 규칙 3
        mov   #{msgwrap.NL},r1
        mov.b r1,@r12               ; out[cand] = NL
        sub   r13,r11
        add   #-1,r11               ; used -= cused + 1
        mov   r12,r14
        add   #1,r14                ; ls = cand + 1
        mov   #0,r12                ; cand = -1
        cmp/ge r2,r11               ; 접어도 여전히 넘치나
        bf    place
    rule3:
{close_half}
        mov   #{lead - 256},r1
        extu.b r1,r1
        cmp/eq r1,r0
        bf    plain
        mov   r8,r1
        add   #1,r1
        mov.b @r1,r0
        extu.b r0,r0
{close_sjis}
        bra   plain
        nop
    space_r:
        bra   space
        nop
    zw:
        mov.b r0,@r10
        add   #1,r10
        bra   loop
        add   #1,r8                 ; (지연 슬롯)
    close:
        cmp/hi r14,r5               ; last > ls ?  (앞 글자가 이 줄에 있나)
        bf    plain
        mov.b @r5,r0                ; 규칙 3 보강(2026-09-27) — `msgwrap.wrap` 의 2B 휴리스틱과
        ; 같다: last 자신도 반각 닫는 부호(「!!」·「!?」)면 2B 더 물러난다(그 앞은 실질적으로
        ; 늘 전각 한 글자라 통째로 온다). ⚠ 비교 상수가 전부 0x80 미만이라 `mov.b` 의 부호
        ; 확장을 그대로 써도 안전하다(`extu.b` 생략 — 자리 절약, 2026-09-27).
{close_half_back2}
        bra   do_shift
        nop
    back2:
        mov   r5,r1
        add   #-2,r1
        cmp/hi r14,r1
        bf    do_shift               ; 2B 물러나면 ls 를 넘는다 — 포기하고 원래 last 로
        mov   r1,r5
    do_shift:
        mov   r10,r1
    shift:
        cmp/hi r5,r1
        bf    shifted
        add   #-1,r1
        mov.b @r1,r0
        bra   shift
        mov.b r0,@(1,r1)            ; (지연 슬롯) 한 칸 뒤로
    shifted:
        mov   #{msgwrap.NL},r0
        mov.b r0,@r5                ; 앞 글자 앞에 개행
        add   #1,r10
        mov   r5,r14
        add   #1,r14                ; ls = last + 1
        mov   r10,r11
        bra   place
        sub   r14,r11               ; (지연 슬롯) used = 바이트 수
    plain:
        mov   #{msgwrap.NL},r0
        mov.b r0,@r10
        add   #1,r10
        mov   r10,r14
        mov   #0,r11
    place:
        mov   r10,r5                ; last = 여기
        mov.b @r8+,r0
        mov.b r0,@r10
        add   #1,r10
        add   r3,r11
        mov   r3,r0
        cmp/eq #2,r0
        bf    placed
        mov.b @r8+,r0
        mov.b r0,@r10
        add   #1,r10
    placed:
        bra   loop_r
        mov   #0,r6                 ; (지연 슬롯) auto = 0
    space:
        add   #1,r8
        tst   r11,r11
        bt    loop_r                ; 규칙 4 — 줄머리 공백은 버린다
        mov   r10,r1
        add   #-1,r1
        mov.b @r1,r0
        cmp/eq #{msgwrap.SP},r0
        bt    loop_r                ; 겹공백도 버린다
        mov.b @r8,r0
        extu.b r0,r0
        add   #-48,r0
        mov   #10,r1
        cmp/hs r1,r0                ; T = 다음이 숫자가 아니다 (규칙 2)
        movt  r3
        mov   #{L},r2
        cmp/ge r2,r11
        bf    sp_fit
        tst   r3,r3
        bf    sp_brk                ; 숫자 앞이 아니면 이 공백에서 끊는다
        tst   r12,r12
        bt    sp_brk
        mov   #{msgwrap.NL},r1      ; 묶음째 내린다 — 앞 공백을 개행으로
        mov.b r1,@r12
        sub   r13,r11
        add   #-1,r11
        mov   r12,r14
        add   #1,r14
        mov   #0,r12
        cmp/ge r2,r11
        bf    sp_fit
    sp_brk:
        mov   #{msgwrap.NL},r0      ; 공백 자체가 넘친다 — 거기서 끊는다
        mov.b r0,@r10
        add   #1,r10
        mov   #0,r11
        mov   #0,r12
        mov   #0,r5
        mov   r10,r14
        bra   loop_r
        mov   #1,r6                 ; (지연 슬롯) auto = 1
    sp_fit:
        tst   r3,r3
        bt    sp_nb                 ; 숫자 앞 공백은 끊는 자리가 아니다
        mov   r10,r12
        mov   r11,r13
    sp_nb:
        mov   #{msgwrap.SP},r0
        mov.b r0,@r10
        add   #1,r10
        add   #1,r11
    loop_r:
        bra   loop
        nop
    fin:
        mov   #0,r0
        mov.b r0,@r10
        mov   r9,r1
        mov   r4,r2
    copy:
        mov.b @r1+,r0
        mov.b r0,@r2
        add   #1,r2                 ; ⚠ `bf` 는 지연 슬롯이 없다 — 증가를 앞에 둔다
        tst   r0,r0
        bf    copy
        mov   r9,r15
        add   #{msgwrap.BUF // 2},r15
        add   #{msgwrap.BUF // 2},r15
        mov.l @r15+,r14
        mov.l @r15+,r13
        mov.l @r15+,r12
        mov.l @r15+,r11
        mov.l @r15+,r10
        mov.l @r15+,r9
        rts
        mov.l @r15+,r8              ; (지연 슬롯)
    """


def assemble(base):
    return sh2.assemble(source().splitlines(), base)


# ── 드로어 훅 — 반각 꼬리 부호에 29열을 연다 (마스터 판정 2026-09-27, PS1 `patch_hang_punct`) ──
# 드로어 둘(ED `0x0607D1DC` 메시지 줄 · `0x0607D3B0`)은 글자를 **그리기 전에** `열 > 폭-1` 이면
# 줄을 넘긴다(`mov r13,r1 · add #-1,r1 · cmp/gt r1,r8`, r8 = 1부터 세는 열 · r13 = 폭 29).
# 그래서 29열이 늘 비고 반각 온점이 혼자 다음 줄로 떨어진다(레벨업 「…회복되었다 / .」).
# 🔴 **반각 꼬리 부호일 때만** 29열을 연다 — 전각이나 보통 글자는 그대로 넘긴다(자동 줄바꿈에
#    기대는 화면이 틀 밖으로 삐지지 않게). 그 부호를 그린 뒤엔 드로어가 스스로 줄을 넘긴다.
# ⚠ 두 드로어 다 분기가 `add #-1,r1` 로 **들어온다**(`mov r13,r1` 은 지연 슬롯) — 그래서
#   `add`·`cmp` 두 명령(4B)을 `bsr 스텁 · nop` 으로 바꾼다. 스텁은 r0·r1 만 쓰고, 두 드로어 다
#   복귀 직후 그 둘을 다시 싣는다(정적 확인). r2 = 글자 바이트 - 1(드로어의 점프표 준비값).
HANG_SIG = bytes.fromhex("61d371ff3817")  # mov r13,r1 · add #-1,r1 · cmp/gt r1,r8
HANG_SITES_EXPECTED = 2


def hang_stub():
    tails = "\n".join(f"        cmp/eq #{c},r0\n        bt    h_clr" for c in msgwrap.HANG_TAIL)
    return f"""
        add   #-1,r1                ; 원 명령 — r1 = 폭-1
        cmp/gt r1,r8                ; T = 열 > 폭-1 (원 판정)
        bf    h_draw                ; 넘길 일이 없다 → T=0 그대로
        add   #1,r1                 ; r1 = 폭
        cmp/eq r1,r8                ; 딱 29열인가
        bf    h_wrap                ; 그보다 멀다 → 넘긴다
        mov   r2,r0
        add   #1,r0                 ; 글자 바이트
{tails}
    h_wrap:
        rts
        sett                        ; (지연 슬롯) T=1 → 드로어가 줄을 넘긴다
    h_clr:
        rts
        clrt                        ; (지연 슬롯) T=0 → 29열에 그린다
    h_draw:
        rts
        nop
    """


def find(d):
    """`(함수 주소, 파일 오프셋)` — 시그니처로 찾고 참조가 한 곳인지 본다."""
    i = d.find(SIG)
    assert i >= 0 and d.find(SIG, i + 1) < 0, "prewrap 시그니처가 없거나 둘 이상이다"
    off = i - SIG_AT
    ent = LOAD_BASE + off
    refs = [k for k in range(0, len(d) - 3, 2) if struct.unpack(">I", d[k : k + 4])[0] == ent]
    assert len(refs) == 1, f"prewrap 참조가 {len(refs)}곳이다 (기대 1)"
    return ent, off


def hang_sites(d):
    """드로어 훅 자리(파일 오프셋) — `add #-1,r1` 의 자리. 시그니처로 찾고 개수를 본다."""
    out, i = [], d.find(HANG_SIG)
    while i >= 0:
        out.append(i + 2)
        i = d.find(HANG_SIG, i + 1)
    assert len(out) == HANG_SITES_EXPECTED, f"드로어 훅 자리가 {len(out)}곳이다 (기대 2)"
    return out


def bsr(at, target):
    """`bsr target` 두 바이트 — `at` 는 명령 자리(주소)."""
    disp = (target - (at + 4)) // 2
    assert (target - at) % 2 == 0 and -2048 <= disp < 2048, f"bsr 범위 밖: {at:#x}→{target:#x}"
    return struct.pack(">H", 0xB000 | (disp & 0xFFF))


def trampoline_src(stub_ram):
    """원 함수 자리에 남는 **12B 징검다리** — 드로어의 `bsr` 이 닿는 곳(±4KB 안)에서 스텁(먼 0런)으로 뛴다.

    🔴 `jmp` 라 PR 이 그대로다 — 스텁이 `rts` 로 **드로어 훅의 `bsr` 자리**로 곧장 돌아간다. r0 는 스텁이
       어차피 먼저 덮는다(드로어 두 곳 다 복귀 뒤 r0·r1 을 다시 싣는다 — 위 「드로어 훅」 주석).
    """
    return f"""
        mov.l @(tp,pc),r0
        jmp   @r0
        nop
        .long tp {stub_ram}
    """


def stub_place(fname):
    """스텁이 앉을 자리 — 조사 훅 0런의 **끝쪽**(`patch_josa_hook.STUB_SPACE` 로 비워 둔 몫). → (오프셋, RAM)"""
    import patch_josa_hook as J  # ⚠ 늦게 — 조사 훅이 이 모듈의 `SIG` 를 임포트한다(순환)

    off, size = J.FREE[fname]
    at = off + size - J.MARGIN - J.STUB_SPACE
    return at, LOAD_BASE + at


def build(d, fname):
    """`(함수 주소, 오프셋, 자리 전체 바이트, 본문 길이, 징검다리 주소, 스텁 오프셋, 스텁 바이트, [훅])`.

    자리 = 줄 나누기 루틴 + 리터럴 풀 + **징검다리**. 드로어 훅 **스텁(56B)은 0런으로 옮겼다** — 어절 후퇴
    (+20B)를 넣으면 본체 516B + 스텁 56B = 572B 로 원 함수 556B 를 넘기 때문이다(2026-10-07 시도는
    8B 초과로 막혔다). 스텁은 조사 훅과 같은 0런(참조 0곳·실기 BP 2,000프레임 무접근)의 끝쪽에 둔다.
    """
    ent, off = find(d)
    code, body = assemble(ent)
    tramp_at = ent + len(code)
    stub_off, stub_ram = stub_place(fname)
    tramp, _n = sh2.assemble(trampoline_src(stub_ram).splitlines(), tramp_at)
    code = code + tramp
    assert len(code) <= SIZE, f"루틴+징검다리 {len(code)}B > 원 함수 {SIZE}B"
    code = code + bytes.fromhex("0009") * ((SIZE - len(code)) // 2)
    stub, _n = sh2.assemble(hang_stub().splitlines(), stub_ram)
    import patch_josa_hook as J

    assert len(stub) <= J.STUB_SPACE, f"스텁 {len(stub)}B > 자리 {J.STUB_SPACE}B"
    hooks = []
    for h in hang_sites(d):
        at = LOAD_BASE + h
        hooks.append((h, bytes(d[h : h + 4]), bsr(at, tramp_at) + bytes.fromhex("0009")))
    return ent, off, code, body, tramp_at, stub_off, stub, hooks


def verify(dst, files):
    """되읽기 — 줄 나누기 루틴·징검다리·**0런의 스텁**·드로어 훅 둘이 그대로 들어갔나 (게이트).

    🔴 스텁이 함수 밖(0런)으로 나갔으므로 **여기가 조용히 비면 드로어가 허공으로 뛴다** — 되읽기가 필수다.
    """
    _f2, mm2 = common.open_image(dst)
    for fname in FILES:
        orig = common.extract(fname)
        ent, off, code, _body, tramp_at, stub_off, stub, hooks = build(orig, fname)
        lba, fsize = files[fname]
        d = common.read_extent(mm2, lba, fsize)
        assert d[off : off + SIZE] == code, f"{fname}: 줄 나누기 되읽기 불일치"
        assert d[stub_off : stub_off + len(stub)] == stub, f"{fname}: 훅 스텁(0런) 되읽기 불일치"
        for h, _was, new4 in hooks:
            assert d[h : h + 4] == new4, f"{fname} 0x{LOAD_BASE + h:08X}: 드로어 훅 되읽기 불일치"
        print(
            f"  ✅ 되읽기 {fname} — 줄 나누기 {SIZE}B · 징검다리 0x{tramp_at:08X} → 스텁 {len(stub)}B"
            f"(0런 0x{LOAD_BASE + stub_off:08X}) · 드로어 훅 {len(hooks)}곳"
        )
    mm2.close()
    _f2.close()


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    files = common.dst_files(dst, mm)
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
    for fname in FILES:
        orig = common.extract(fname)
        ent, off, code, body, tramp_at, stub_off, stub, hooks = build(orig, fname)
        lines = sh2.verify(code, ent, body)
        sh2.verify(stub, LOAD_BASE + stub_off, len(stub))
        print(f"{fname}: prewrap 0x{ent:08X} → 루틴 {body}B (자리 {SIZE}B) · 명령 {len(lines)}")
        print(
            f"   징검다리 0x{tramp_at:08X} → 스텁 0x{LOAD_BASE + stub_off:08X}({len(stub)}B, 0런) · 자리 "
            + " · ".join(f"0x{LOAD_BASE + h:08X}" for h, _o, _n in hooks)
        )
        if "--dis" in sys.argv:
            for ln in lines:
                print("      ", ln)
        if not apply:
            continue
        lba, fsize = files[fname]
        _fd, mmd = common.open_image(dst)
        cur = bytes(common.read_extent(mmd, lba, fsize)[off : off + SIZE])
        mmd.close()
        _fd.close()
        # ⚠ 사전조건 = 「원본이거나 이미 우리 것」 — 게이트가 체인을 통째로 다시 돌린다.
        was = bytes(orig[off : off + SIZE])
        assert cur in (was, code), f"{fname} 0x{ent:08X}: 원본도 우리 루틴도 아니다"
        with open(dst, "r+b") as f:
            _fd, mmd = common.open_image(dst)
            cur_stub = bytes(common.read_extent(mmd, lba, fsize)[stub_off : stub_off + len(stub)])
            mmd.close()
            _fd.close()
            # ⚠ 스텁 자리 사전조건 = 「0런(비어 있음)이거나 이미 우리 스텁」 — 다시 돌려도 돈다
            assert cur_stub in (bytes(len(stub)), stub), f"{fname} 스텁 자리 0x{stub_off:X}: 0런도 우리 스텁도 아니다"
            common.write_at(f, lba, fsize, stub_off, stub, label=f"{fname} 훅 스텁(0런)", expect=cur_stub)
            common.write_at(f, lba, fsize, off, code, label=f"{fname} 줄 나누기", expect=cur)
            for h, was4, new4 in hooks:
                _fd, mmd = common.open_image(dst)
                cur4 = bytes(common.read_extent(mmd, lba, fsize)[h : h + 4])
                mmd.close()
                _fd.close()
                assert cur4 in (was4, new4), (
                    f"{fname} 0x{LOAD_BASE + h:08X}: 드로어가 원본이 아니다"
                )
                common.write_at(f, lba, fsize, h, new4, label=f"{fname} 드로어 훅", expect=cur4)
        print("   → 넣음")
    if apply:
        verify(dst, files)
    if not apply:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")


if __name__ == "__main__":
    main()
