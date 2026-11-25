"""QA 디버그 메뉴(빌드 스위치 `ED_DEBUG_QA=1` 전용 — 제품 롬 불변) — 원판 창 엔진(`0x80015B20` 열기 · `0x80017334` 글 그리기)을 재사용한 작은 목록 메뉴.

원리(11-18 실측): 프레임마다 도는 패드 갱신 함수(`0x80057E50`)의 `jal 0x80064D94`(패드 읽기, 반환 = 버튼 비트)를 이 훅(`HOOK`)으로 돌려, 원판이 안 읽는
조합(L2+R2+SELECT)이면 메뉴를 열고 열려 있는 동안 게임에는 **버튼 0** 을 돌려준다(이동·대화 안 됨). 닫을 땐 버튼이 다 떼어질 때까지 0 을 돌려
○·✕ 가 게임에 새는 걸 막는다. 패드 비트: L2 1 · R2 2 · L1 4 · R1 8 · △ 0x10 · ○ 0x20 · ✕ 0x40 · □ 0x80 · SELECT 0x100 · START 0x800 · 위 0x1000 · 오른 0x2000 · 아래 0x4000 · 왼 0x8000.
창 글은 한 번 그리면 남는다(타일 캐시) — 커서가 움직이면 창을 닫고(첫 u16 = 0) 다시 연다. 줄은 열 수만큼 채워 써 줄바꿈 없이 다음 줄로 넘어간다.
이 파일은 코드 생성만 한다 — 얹는 자리·패치는 `qa_patch` 가 맡는다(제품 빌드에서 안 부른다).
"""

import struct

from mipsasm import asm, verify

PAD_CALL = 0x80064D94  # 패드 읽기(반환 = 버튼 비트)
PAD_SITE = 0x80057E68  # `jal 0x80064d94` — 패드 갱신 함수 안, 이 훅으로 돌린다(지연 슬롯 `sw v0,0x288(s0)` 은 그대로)
FN_OPEN, FN_DRAW = 0x80015B20, 0x80017334
WIN_TAB = 0x801EF9C8  # 창 표(42B × 번호)
EXP1, EXP2, MONEY = 0x8007BA44, 0x8007BA48, 0x80095C58
COMBO = 0x103  # L2+R2+SELECT
COLS, X, Y = 9, 8, 8
SPACE = 610


def hi(a):
    return (a >> 16) & 0xFFFF


def lo(a):
    return a & 0xFFFF


def hook_source(ctl, nrows, actions):
    """훅 어셈블리 — ctl = 상태 구역 주소. `actions` = [(줄 번호, 어셈블리 조각)] — 조각은 t0~t3 만 쓰고 끝에 `j ACT_DONE` 가 붙는다."""
    act = []
    for i, body in actions:
        act.append(
            f"    addiu $t0, $zero, {i}\n    bne $t9, $t0, ACT{i}_N\n    nop\n{body}\n    j ACT_DONE\n    nop\nACT{i}_N:"
        )
    return f"""
HOOK:
    addiu $sp, $sp, -32
    sw $ra, 28($sp)
    sw $s0, 24($sp)
    sw $s1, 20($sp)
    sw $s2, 16($sp)
    jal {PAD_CALL:#x}
    move $a0, $zero
    andi $s0, $v0, 0xffff
    lui $s1, {hi(ctl):#x}
    ori $s1, $s1, {lo(ctl):#x}
    lw $t0, 0($s1)
    nop
    beq $t0, $zero, CLOSED
    nop
    addiu $t1, $zero, 2
    beq $t0, $t1, WAITREL
    nop
    lw $t2, 4($s1)
    sw $s0, 4($s1)
    nor $t3, $t2, $zero
    and $s2, $s0, $t3
    andi $t4, $s2, 0x40
    bne $t4, $zero, DOCLOSE
    nop
    andi $t4, $s2, 0x1000
    beq $t4, $zero, NOUP
    nop
    lw $t5, 12($s1)
    nop
    addiu $t5, $t5, -1
    bgez $t5, UPOK
    nop
    addiu $t5, $zero, {nrows - 1}
UPOK:
    sw $t5, 12($s1)
    jal REDRAW
    nop
NOUP:
    andi $t4, $s2, 0x4000
    beq $t4, $zero, NODN
    nop
    lw $t5, 12($s1)
    nop
    addiu $t5, $t5, 1
    slti $t6, $t5, {nrows}
    bne $t6, $zero, DNOK
    nop
    move $t5, $zero
DNOK:
    sw $t5, 12($s1)
    jal REDRAW
    nop
NODN:
    andi $t4, $s2, 0x20
    beq $t4, $zero, RETZERO
    nop
    lw $t9, 12($s1)
    nop
{chr(10).join(act)}
ACT_DONE:
    jal REDRAW
    nop
    j RETZERO
    nop
CLOSED:
    andi $t1, $s0, {COMBO:#x}
    addiu $t2, $zero, {COMBO:#x}
    bne $t1, $t2, RETRAW
    nop
    addiu $t0, $zero, 1
    sw $t0, 0($s1)
    sw $s0, 4($s1)
    sw $zero, 12($s1)
    jal REDRAW
    nop
    j RETZERO
    nop
WAITREL:
    bne $s0, $zero, RETZERO
    nop
    sw $zero, 0($s1)
    j RETZERO
    nop
DOCLOSE:
    lw $t0, 8($s1)
    nop
    beq $t0, $zero, DCL2
    nop
    sh $zero, 0($t0)
DCL2:
    sw $zero, 8($s1)
    addiu $t0, $zero, 2
    sw $t0, 0($s1)
RETZERO:
    move $v0, $zero
    j RET
    nop
RETRAW:
    move $v0, $s0
RET:
    lw $ra, 28($sp)
    lw $s0, 24($sp)
    lw $s1, 20($sp)
    lw $s2, 16($sp)
    jr $ra
    addiu $sp, $sp, 32

REDRAW:
    addiu $sp, $sp, -24
    sw $ra, 20($sp)
    lui $t8, {hi(ctl):#x}
    ori $t8, $t8, {lo(ctl):#x}
    lw $t0, 8($t8)
    nop
    beq $t0, $zero, RD1
    nop
    sh $zero, 0($t0)
RD1:
    addiu $a0, $zero, {X}
    addiu $a1, $zero, {Y}
    addiu $a2, $zero, {COLS}
    addiu $a3, $zero, {nrows}
    jal {FN_OPEN:#x}
    nop
    sll $v0, $v0, 16
    sra $v0, $v0, 16
    sll $t2, $v0, 4
    sll $t3, $v0, 2
    addu $t2, $t2, $t3
    addu $t2, $t2, $v0
    sll $t2, $t2, 1
    lui $t4, {hi(WIN_TAB):#x}
    ori $t4, $t4, {lo(WIN_TAB):#x}
    addu $t4, $t4, $t2
    lui $t8, {hi(ctl):#x}
    ori $t8, $t8, {lo(ctl):#x}
    sw $t4, 8($t8)
    sw $zero, 16($t8)
RD2:
    lw $t0, 16($t8)
    lw $t1, 12($t8)
    sll $t2, $t0, 3
    addu $t2, $t2, $t8
    lw $a1, 32($t2)
    bne $t0, $t1, RD3
    nop
    lw $a1, 36($t2)
RD3:
    lw $a0, 8($t8)
    move $a2, $zero
    jal {FN_DRAW:#x}
    move $a3, $zero
    lui $t8, {hi(ctl):#x}
    ori $t8, $t8, {lo(ctl):#x}
    lw $t0, 16($t8)
    nop
    addiu $t0, $t0, 1
    sw $t0, 16($t8)
    slti $t1, $t0, {nrows}
    bne $t1, $zero, RD2
    nop
    lw $ra, 20($sp)
    nop
    jr $ra
    addiu $sp, $sp, 24
"""


def row_codes(text, cursor, kr_codes):
    """한 줄 = 열 수만큼의 코드(앞 두 칸 = 커서 표시 `○`+공백 또는 공백 둘) + 0xFFFF 끝."""
    body = kr_codes(text)
    head = [24, SPACE] if cursor else [SPACE, SPACE]
    codes = (head + body)[:COLS]
    codes += [SPACE] * (COLS - len(codes))
    return codes + [0xFFFF]


def build(base, rows, actions, kr_codes, pool_at=None):
    """(바이트, 진입 주소, 상태구역 주소, 라벨) — `base` 에 놓일 코드+데이터. rows = [줄 문안], actions = [(줄 번호, 어셈블리)]."""
    n = len(rows)
    ctl_dummy = 0x80000000
    words, labels = asm(hook_source(ctl_dummy, n, actions), base)
    code_len = 4 * len(words)
    ctl = base + code_len
    words, labels = asm(hook_source(ctl, n, actions), base)
    assert 4 * len(words) == code_len
    verify(words, base)
    data = bytearray(32 + 8 * n)
    pool = (
        ctl + len(data) if pool_at is None else pool_at
    )  # 줄 글 덩이는 다른 죽은 구간에 둘 수도 있다
    blob = bytearray()
    for i, t in enumerate(rows):
        for k, cur in enumerate((False, True)):
            c = row_codes(t, cur, kr_codes)
            struct.pack_into("<I", data, 32 + 8 * i + 4 * k, pool + len(blob))
            blob += struct.pack(f"<{len(c)}H", *c)
            blob += b"\0\0" if len(blob) % 4 else b""
    out = b"".join(struct.pack("<I", w) for w in words) + bytes(data)
    if pool_at is None:
        return out + bytes(blob), base + 0, ctl, labels
    return out, base + 0, ctl, labels, bytes(blob)


def site_word(entry):
    return 0x0C000000 | ((entry >> 2) & 0x3FFFFFF)
