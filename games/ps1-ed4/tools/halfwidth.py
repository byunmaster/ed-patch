"""반각 합성 훅 — 업로더(`0x80016320`) 안에서 글자를 **픽셀 위치에 합성**한다. 모델 = `tilecomp.Line`.

엔진은 줄을 「글리프 칸 수」로 세므로(줄당 24개) 이 훅은 **모양**(공백·숫자·부호가 반 칸으로 좁게 앉음)만 준다 — 줄당 글리프 수 한도는 그대로다(docs/wrap.md).
창마다 열 수·칸 기점(창 구조체 +6·+0x22)을 읽어 어느 창에서나 합성한다(열 수 0·칸 범위 밖은 원판 그대로).

두 지점:
- H1: `0x80016528`(`sll v1,v1,1`) 을 `jal H1` 로. 원래 `sll`·`addu s0` 를 H1 이 대신 하고, 합성한 18B 글리프(OUTA)를 `s0` 로 돌려준다.
  타일 칸의 VRAM 사각형(`sp+0x18/0x1a`)도 글리프 칸이 아니라 **타일 칸** 것으로 바꾼다. 복귀 주소 = `0x80016530`.
- H2: `0x800165d0`(`jal LoadImage`) 를 `jal H2` 로. 원래 호출을 한 뒤, 12px 글자가 칸 경계를 걸쳤으면 오른쪽 조각(SPB)을 전개해 **다음 타일**에도 올린다.

데이터(D): 0 TT 4 OO(0·6) 2 LC 6 PEND 8 SPX A SPY C 창 열 수(필요할 때 저장) 10 CUR[12] 58 OUTA 6C SPB 80 HALF(코드 목록, 0 끝) D8 RECT(8B).
"""

import common
from mipsasm import asm, verify

H1_SITE = 0x80016528  # sll v1,v1,1
H2_SITE = 0x800165D0  # jal LoadImage
LOADIMAGE = 0x8005DE50
H1_RET = 0x80016530

DATA_SIZE = 0xE0
JLAST = 0x30  # 직전에 그려진 글자의 코드(u16) — 조사 훅이 받침을 본다
JMK = 0x34  # 조사 표지 3 × (표지 코드, 받침 있을 때 코드, 없을 때 코드) u16
N_JMARK = 3
BT_BYTES = 208  # 받침 비트표(코드마다 1비트, 코드 < 1664 — 한글 배정은 모두 1653 미만) — 한글에서 뺀 글리프 슬롯 12칸(`slots.BT_SLOTS`)에 둔다
HALF_OFF = 0x80
HALF_MAX = 43  # 0 끝 제외


def _lo_hi(a):
    return (a >> 16) & 0xFFFF, a & 0xFFFF


def josa_text(data, bt):
    """H1 맨 앞에 붙는 조사 블록 — `a0` 가 표지면 직전 글자(`JLAST`)의 받침 비트로 조사 글리프 코드로 바꾸고 `v1`(=코드×9)을 다시 만든다. 끝에 `JLAST` 갱신.
    🔴 R3000 로드 지연 슬롯: `lhu` 바로 다음 명령은 새 값을 못 본다."""
    hi, lo = _lo_hi(data)
    bhi, blo = _lo_hi(bt)
    return f"""
    lui t9, {hi:#x}
    ori t9, t9, {lo:#x}
    lhu t0, {JLAST}(t9)
    addiu t1, t9, {JMK}
    li t2, {N_JMARK}
jl:
    lhu t3, 0(t1)
    nop
    beq t3, a0, jhit
    nop
    addiu t2, t2, -1
    bne t2, zero, jl
    addiu t1, t1, 6
    j jstore
    nop
jhit:
    lui t4, {bhi:#x}
    ori t4, t4, {blo:#x}
    srl t5, t0, 3
    addu t4, t4, t5
    lbu t4, 0(t4)
    andi t5, t0, 7
    srlv t4, t4, t5
    andi t4, t4, 1
    beq t4, zero, jno
    nop
    lhu a0, 2(t1)
    j jre
    nop
jno:
    lhu a0, 4(t1)
    nop
jre:
    sll v1, a0, 3
    addu v1, v1, a0
jstore:
    sh a0, {JLAST}(t9)
"""


def h1_text(data, bt=None):
    hi, lo = _lo_hi(data)
    pre = josa_text(data, bt) if bt else ""
    return pre + f"""
    sll v1, v1, 1
    addu s0, v1, v0
    lui t9, {hi:#x}
    ori t9, t9, {lo:#x}
    sh zero, 6(t9)
    lui t0, 0x801f
    lh t0, 0x3452(t0)
    move t3, zero
    bgez t0, win
    sll t1, t0, 5
    j next
    nop
win:
    sll t2, t0, 3
    addu t1, t1, t2
    sll t2, t0, 1
    addu t1, t1, t2
    lui t2, 0x801f
    addiu t2, t2, -0x638
    addu t1, t1, t2
    lhu t2, 6(t1)
    nop
    beq t2, zero, next
    lhu t4, 8(t1)
    lhu t5, 0x22(t1)
    sh t2, 0xc(t9)
    move t6, zero
    move t7, t4
mul:
    beq t7, zero, muldone
    nop
    addu t6, t6, t2
    j mul
    addiu t7, t7, -1
muldone:
    move t4, t6
    addiu t6, s3, -1
    andi t6, t6, 0xffff
    subu t6, t6, t5
    sltu t7, t6, t4
    beq t7, zero, next
    move t7, zero
rowloop:
    sltu t8, t6, t2
    bne t8, zero, rowdone
    nop
    subu t6, t6, t2
    addu t5, t5, t2
    j rowloop
    addiu t7, t7, 1
rowdone:
    addiu t0, s3, -1
    andi t0, t0, 0xffff
    lhu t8, 2(t9)
    beq t6, zero, reset
    nop
    beq t8, t0, cont
    nop
reset:
    sh t6, 0(t9)
    sh zero, 4(t9)
    sw zero, 0x10(t9)
    sw zero, 0x14(t9)
    sw zero, 0x18(t9)
    sw zero, 0x1c(t9)
    sw zero, 0x20(t9)
    sw zero, 0x24(t9)
cont:
    li t0, 12
    addiu t1, t9, {HALF_OFF:#x}
hl:
    lhu t2, 0(t1)
    nop
    beq t2, zero, hdone
    nop
    bne t2, a0, hl
    addiu t1, t1, 2
    li t0, 6
hdone:
    lhu t8, 0(t9)
    lhu t4, 4(t9)
    nop
    addu t8, t8, t5
    sh t8, 0x2c(t9)
    sh t0, 0x2e(t9)
    li t8, 6
    bne t0, t8, notf
    move a3, zero
    bne t4, zero, notf
    nop
    li a3, 1
notf:
    li t8, 12
    subu v1, t8, t4
    move t1, s0
    addiu t6, t1, 18
    addiu t2, t9, 0x58
    addiu t3, t9, 0x6c
    addiu t4, t9, 0x10
    lhu t8, 4(t9)
    nop
pair:
    lbu v0, 0(t1)
    lbu t0, 1(t1)
    lbu t5, 2(t1)
    sll t7, v0, 4
    srl a0, t0, 4
    or t7, t7, a0
    andi t0, t0, 15
    sll t0, t0, 8
    or t0, t0, t5
    lhu v0, 0(t4)
    srlv a0, t7, t8
    or a0, a0, v0
    lhu v0, 2(t4)
    srlv t5, t0, t8
    or t5, t5, v0
    sllv t7, t7, v1
    andi t7, t7, 0xfff
    sllv t0, t0, v1
    andi t0, t0, 0xfff
    beq a3, zero, usesp
    nop
    sh a0, 0(t4)
    j packed
    sh t5, 2(t4)
usesp:
    sh t7, 0(t4)
    sh t0, 2(t4)
packed:
    srl v0, a0, 4
    sb v0, 0(t2)
    andi a0, a0, 15
    sll a0, a0, 4
    srl v0, t5, 8
    or v0, v0, a0
    sb v0, 1(t2)
    andi v0, t5, 0xff
    sb v0, 2(t2)
    srl v0, t7, 4
    sb v0, 0(t3)
    andi t7, t7, 15
    sll t7, t7, 4
    srl v0, t0, 8
    or v0, v0, t7
    sb v0, 1(t3)
    andi v0, t0, 0xff
    sb v0, 2(t3)
    addiu t1, t1, 3
    addiu t2, t2, 3
    addiu t3, t3, 3
    bne t1, t6, pair
    addiu t4, t4, 4
    addiu s0, t9, 0x58
    lhu t0, 0x2e(t9)
    lhu t1, 0x2c(t9)
    lhu t2, 0(t9)
    lhu t3, 4(t9)
    sll t4, t1, 1
    addu t4, t4, s7
    lhu t4, 0(t4)
    nop
    andi t5, t4, 0xff
    srl t5, t5, 2
    addiu t5, t5, 0x140
    sh t5, 0x18(sp)
    srl t4, t4, 8
    sh t4, 0x1a(sp)
    li t5, 12
    bne t0, t5, nopend
    nop
    li t5, 6
    bne t3, t5, nopend
    nop
    lhu t5, 0xc(t9)
    nop
    addiu t5, t5, -1
    sltu t5, t2, t5
    beq t5, zero, nopend
    nop
    sll t4, t1, 1
    addu t4, t4, s7
    lhu t4, 2(t4)
    nop
    andi t5, t4, 0xff
    srl t5, t5, 2
    addiu t5, t5, 0x140
    sh t5, 8(t9)
    srl t4, t4, 8
    sh t4, 0xa(t9)
    li t5, 1
    sh t5, 6(t9)
nopend:
    li t5, 12
    bne t0, t5, half
    nop
    addiu t2, t2, 1
    j upd2
    sh t2, 0(t9)
half:
    bne t3, zero, half6
    li t3, 6
    j upd2
    sh t2, 0(t9)
half6:
    move t3, zero
    addiu t2, t2, 1
upd:
    sh t2, 0(t9)
upd2:
    sh t3, 4(t9)
    sh s3, 2(t9)
done:
    jr ra
    nop
next:
    bne t3, zero, adv
    nop
    li t3, 1
    move t0, zero
    j win
    move t1, zero
adv:
    addiu t0, t0, 1
    sltiu t8, t0, 16
    bne t8, zero, win
    sll t1, t0, 5
    jr ra
    nop
"""


def h2_text(data):
    hi, lo = _lo_hi(data)
    return f"""
    addiu sp, sp, -16
    sw ra, 0(sp)
    jal {LOADIMAGE:#x}
    nop
    lui t0, {hi:#x}
    ori t0, t0, {lo:#x}
    lhu v0, 6(t0)
    nop
    beq v0, zero, out
    nop
    sh zero, 6(t0)
    addiu s4, s4, 1
    andi s4, s4, 7
    sll a1, s4, 6
    sll v1, s4, 4
    addu a1, a1, v1
    sll v1, s4, 2
    addu a1, a1, v1
    addu a1, a1, s6
    addiu a0, t0, 0x6c
    addiu v1, a0, 18
    move a2, a1
el:
    lbu v0, 0(a0)
    addiu a0, a0, 1
    sll v0, v0, 2
    addu v0, v0, s5
    lbu a3, 0(v0)
    lbu t1, 1(v0)
    lbu t2, 2(v0)
    lbu t3, 3(v0)
    sb a3, 0(a2)
    sb t1, 1(a2)
    sb t2, 2(a2)
    sb t3, 3(a2)
    bne a0, v1, el
    addiu a2, a2, 4
    sb zero, 0(a2)
    sb zero, 1(a2)
    sb zero, 2(a2)
    sb zero, 3(a2)
    sb zero, 4(a2)
    sb zero, 5(a2)
    lhu v0, 8(t0)
    lhu v1, 0xa(t0)
    li a3, 3
    sh v0, 0xd8(t0)
    sh v1, 0xda(t0)
    sh a3, 0xdc(t0)
    li a3, 13
    sh a3, 0xde(t0)
    addiu a0, t0, 0xd8
    jal {LOADIMAGE:#x}
    nop
out:
    lw ra, 0(sp)
    addiu sp, sp, 16
    jr ra
    nop
"""


# ── 커서 줄 경로(HX) — 둘째 동굴 ───────────────────────────────────────────────
# 선택(커서) 줄은 글리프 루프(H1·H2)가 아니라 창 칸 코드 배열을 `0x800177C0` 이 칸마다 한 타일로 풀어(`0x800171A0` → `0x80016268`, 한 글자 = 12px 한 칸) 테두리 색을 굽고 통째로 올린다.
# 그래서 커서 줄만 공백이 전각이 됐다(10-25 마스터 관찰). HX1 이 그 호출 앞에서 **같은 코드 배열을 H1 로 합성**해 타일 캐시 자리에 미리 채우고, HX2 가 타일 풀기를 건너뛰게 한다.
HX1_SITE = 0x800179DC  # jal 0x800177c0 (선택 줄 타일 만들기 — 호출자 `0x800178C4`)
HX1_WORD = 0x0C005DF0
HX2_SITE = 0x800171C0  # jal 0x80016268 (한 글리프 → 타일 풀기)
HX2_WORD = 0x0C00589A
TILEROW_FN = 0x800177C0
EXPAND_FN = 0x80016268
EXPAND_TILE_FN = 0x800171A0  # 코드 하나 → 캐시 타일(HX2 가 부르는 `0x80016268` 의 바깥 틀)
HXQ_SITE = 0x80017D64  # jal 0x800171a0 — 로드/세이브 목록 줄(`0x80017BEC`)의 첫 칸 풀기(타이틀 불러오기 목록)
HXQ_WORD = 0x0C005C68
CACHE_PTR_HI, CACHE_PTR_LO = 0x8009, 0x7BBC  # 타일 캐시 포인터(`lw s0,0x7bbc(s1)`, s1 = 0x80090000)
CAVE2 = 0x80060308  # 호출자 없는 라이브러리 함수(디버그 문자열을 찍는 꼴) — 🔴 처음 잡은 0x800274F4 는 **죽은 함수가 아니었다**(10-25: 장비 메뉴가 `jal 0x800274EC` 로 부르는 함수의 몸통 — 시작 8B 앞을 못 봤다). 구간은 `jr ra` 경계 단위로 외부 참조 0 을 확인하고 덫(`ED_HOOK_TRAP2`)을 메뉴 전 항목·전투에서 돌려 0회여야 한다
CAVE2_SIZE = 1088  # 0x80060308~0x80060747
CAVE2_SHA1 = "f72b6cc81e69e327cd27907f613a43fdabe2f0f3"
HX_FLAG_SIZE = 4
# 🔴 아이템 메뉴 구조체(표 0xA38) 사용처 패치 — 함수 `0x800256BC` 가 원판 `0x80010238` 의 0x52B 를 스택(sp+0x60)에 복사해 두고 `s5`·`a1` 로 가리켜 읽는다(표 항목 = 그 구조체 시작 기준 u16 오프셋).
#    번역이 70B 칸을 넘으니 구조체를 둘째 동굴(`ITEM_STRUCT`)로 통째로 옮기고 ① 복사 원본 ② 읽는 기준 둘(`s5`·`a1`)을 새 자리로 돌린다. 복사본(앞 0x52B)은 표 u16 만 읽히고 문자열은 새 자리에서 읽는다.
ITEM_STRUCT = CAVE2 + 0x370
ITEM_STRUCT_MAX = CAVE2_SIZE - 0x370
ITEM_STUBS = CAVE2 + 0x350
ITEM_COPY_LUI, ITEM_COPY_ADD = 0x800256C4, 0x800256C8  # lui v0,0x8001 · addiu a2,v0,0x238 (복사 원본)
ITEM_SITE_A, ITEM_SITE_B = 0x80025BA0, 0x80026618  # addiu s5,sp,0x60 · addiu a1,sp,0x60
# 아이템 사용 결과 메시지 창(`0x80015B20(x, y, 열, 줄)`)의 열 수·x — 원문 길이에 맞춘 값이라 번역이 길면 잘린다. 창의 **가운데 x 는 원판 그대로**(A 158 · B 152, 폭 = 열×12+16)이고,
# 글자는 줄 끝 부호(`.`)를 뺀 폭이 창 안 좌우 여백(8px)에 같게 놓이도록 열을 정한다(번역 규칙 2-8 — 공백·부호 반각 6px).
#   A 「 지금은 못 쓴다.」(앞 반각 공백 하나 — 몸통 84px+앞 6 = 90, 닫는 `.` 6 포함 96 = 8열) → 8열·x 0x66 · 좌 여백 14 = 우 여백 14.
#   B 「아무 일도 일어나지 않았다.」(몸통 150px, `.` 포함 156 = 13열) → 13열·x 0x42 · 좌 8 · 우 14(`.` 포함 8) — 반각 단위(6px)로는 몸통 150px 이 12px 열에 홀수 반이라 6px 차가 남는다.
ITEM_MSG_PATCH = [  # (주소, 원판 명령, 새 명령) — `addiu a0/a2,zero,imm`
    (0x80026578, 0x2404006C, 0x24040066),  # 창 A(「今は使えない。」) x 0x6c → 0x66
    (0x800265A8, 0x2404006C, 0x24040066),  # 창 A 재시도
    (0x80026580, 0x24060007, 0x24060008),  # 창 A 열 7 → 8
    (0x800265AC, 0x24040054, 0x24040042),  # 창 B(「何も起こらなかった。」) x 0x54 → 0x42
    (0x800265DC, 0x24040054, 0x24040042),  # 창 B 재시도
    (0x800265B4, 0x2406000A, 0x2406000D),  # 창 B 열 10 → 13
]
ITEM_WORDS = {ITEM_COPY_LUI: 0x3C028001, ITEM_COPY_ADD: 0x24460238, ITEM_SITE_A: 0x27B50060, ITEM_SITE_B: 0x27A50060}


def hx_text(h1, data, flag):
    hi, lo = _lo_hi(data)
    fhi, flo = _lo_hi(flag)
    return f"""
    addiu sp, sp, -0x58
    sw ra, 0x20(sp)
    sw s0, 0x24(sp)
    sw s1, 0x28(sp)
    sw s2, 0x2c(sp)
    sw s3, 0x30(sp)
    sw s4, 0x34(sp)
    sw s5, 0x38(sp)
    sw s6, 0x3c(sp)
    sw s7, 0x40(sp)
    sw a0, 0x44(sp)
    sw a1, 0x48(sp)
    sw a2, 0x4c(sp)
    sw a3, 0x50(sp)
    j cmp
    move k1, zero
hxq:
    addiu sp, sp, -0x58
    sw ra, 0x20(sp)
    sw s0, 0x24(sp)
    sw s1, 0x28(sp)
    sw s2, 0x2c(sp)
    sw s3, 0x30(sp)
    sw s4, 0x34(sp)
    sw s5, 0x38(sp)
    sw s6, 0x3c(sp)
    sw s7, 0x40(sp)
    sw a0, 0x44(sp)
    sll a1, s2, 16
    sra a1, a1, 16
    sw a1, 0x48(sp)
    addiu a0, sp, 0x68
    move s3, s7
    lhu s4, 0xa8(sp)
    j cmp
    li k1, 1
cmp:
    lhu t0, 0x22(s3)
    nop
    addu s6, t0, s4
    addiu s3, s6, 1
    move s1, a0
    move s2, a1
    blez s2, fin
    nop
    lui t0, {CACHE_PTR_HI:#x}
    lw s4, {CACHE_PTR_LO:#x}(t0)
    lui s5, 0x8007
    addiu s5, s5, 0x524
    lui s7, 0x800c
    addiu s7, s7, 0x6f20
    sll t2, s2, 4
    sll t3, s2, 2
    addu t2, t2, t3
    addu t2, t2, s2
    move t3, s4
zl:
    sw zero, 0(t3)
    addiu t2, t2, -1
    bgtz t2, zl
    addiu t3, t3, 4
loop:
    lhu a0, 0(s1)
    nop
    sll v1, a0, 3
    addu v1, v1, a0
    lui v0, 0x8007
    addiu v0, v0, 0xbd4
    lui t0, {hi:#x}
    ori t0, t0, {lo:#x}
    lhu t1, 2(t0)
    nop
    bne t1, s3, noclr
    nop
    sh zero, 2(t0)
noclr:
    jal {h1:#x}
    addu s0, v1, v0
    lui t0, {hi:#x}
    ori t0, t0, {lo:#x}
    lhu t1, 2(t0)
    subu t2, s3, s6
    addiu t2, t2, -1
    bne t1, s3, havek
    nop
    lhu t1, 0x2c(t0)
    nop
    subu t2, t1, s6
    lw t3, 0x48(sp)
    nop
    sltu t3, t2, t3
    bne t3, zero, havek
    nop
    subu t2, s3, s6
    addiu t2, t2, -1
havek:
    sll t3, t2, 2
    sll t4, t2, 4
    addu t3, t3, t4
    sll t4, t2, 6
    addu t3, t3, t4
    addu t7, s4, t3
    move t0, s0
    addiu t1, s0, 18
    move t2, t7
el1:
    lbu v0, 0(t0)
    addiu t0, t0, 1
    sll v0, v0, 2
    addu v0, v0, s5
    lbu a0, 0(v0)
    lbu a1, 1(v0)
    lbu a2, 2(v0)
    lbu a3, 3(v0)
    sb a0, 0(t2)
    sb a1, 1(t2)
    sb a2, 2(t2)
    sb a3, 3(t2)
    bne t0, t1, el1
    addiu t2, t2, 4
    sb zero, 0(t2)
    sb zero, 1(t2)
    sb zero, 2(t2)
    sb zero, 3(t2)
    sb zero, 4(t2)
    sb zero, 5(t2)
    lui t0, {hi:#x}
    ori t0, t0, {lo:#x}
    lhu v0, 6(t0)
    nop
    beq v0, zero, nospill
    nop
    sh zero, 6(t0)
    addiu t0, t0, 0x6c
    addiu t1, t0, 18
    addiu t2, t7, 84
el2:
    lbu v0, 0(t0)
    addiu t0, t0, 1
    sll v0, v0, 2
    addu v0, v0, s5
    lbu a0, 0(v0)
    lbu a1, 1(v0)
    lbu a2, 2(v0)
    lbu a3, 3(v0)
    sb a0, 0(t2)
    sb a1, 1(t2)
    sb a2, 2(t2)
    sb a3, 3(t2)
    bne t0, t1, el2
    addiu t2, t2, 4
    sb zero, 0(t2)
    sb zero, 1(t2)
    sb zero, 2(t2)
    sb zero, 3(t2)
    sb zero, 4(t2)
    sb zero, 5(t2)
nospill:
    addiu s3, s3, 1
    addiu s1, s1, 2
    addiu s2, s2, -1
    bgtz s2, loop
    nop
    lui t0, {fhi:#x}
    ori t0, t0, {flo:#x}
    lw t1, 0x48(sp)
    nop
    sh t1, 0(t0)
fin:
    bne k1, zero, qend
    nop
    lw a0, 0x44(sp)
    lw a1, 0x48(sp)
    lw a2, 0x4c(sp)
    lw a3, 0x50(sp)
    jal {TILEROW_FN:#x}
    nop
    lui t0, {fhi:#x}
    ori t0, t0, {flo:#x}
    sh zero, 0(t0)
    lw ra, 0x20(sp)
    lw s0, 0x24(sp)
    lw s1, 0x28(sp)
    lw s2, 0x2c(sp)
    lw s3, 0x30(sp)
    lw s4, 0x34(sp)
    lw s5, 0x38(sp)
    lw s6, 0x3c(sp)
    lw s7, 0x40(sp)
    addiu sp, sp, 0x58
    jr ra
    nop
qend:
    lw a0, 0x44(sp)
    lw ra, 0x20(sp)
    lw s0, 0x24(sp)
    lw s1, 0x28(sp)
    lw s2, 0x2c(sp)
    lw s3, 0x30(sp)
    lw s4, 0x34(sp)
    lw s5, 0x38(sp)
    lw s6, 0x3c(sp)
    lw s7, 0x40(sp)
    addiu sp, sp, 0x58
    j {EXPAND_TILE_FN:#x}
    nop
hx2:
    lui t0, {fhi:#x}
    ori t0, t0, {flo:#x}
    lhu t1, 0(t0)
    nop
    beq t1, zero, orig
    addiu t1, t1, -1
    sh t1, 0(t0)
    jr ra
    addiu v0, a1, 78
orig:
    j {EXPAND_FN:#x}
    nop
"""


def build_hx(code2, h1, data):
    """(워드, 라벨) — 둘째 동굴. 깃발(2B)은 코드 바로 뒤(4 정렬)."""
    n = len(asm(hx_text(h1, data, code2), code2)[0])
    flag = code2 + 4 * n
    w, lab = asm(hx_text(h1, data, flag), code2)
    verify(w, code2)
    assert len(w) == n
    return w, {"hx1": code2, "hxq": lab["hxq"], "hx2": lab["hx2"], "flag": flag, "end": flag + HX_FLAG_SIZE}


def build(code, data, bt=None):
    """(워드, 라벨 모음) — H1 다음에 H2 가 이어진다. 라벨: `h1` `h2`. `bt` = 받침 비트표 주소(있으면 조사 블록을 H1 앞에 붙인다)."""
    w1, _ = asm(h1_text(data, bt), code)
    verify(w1, code)
    code2 = code + 4 * len(w1)
    w2, _ = asm(h2_text(data), code2)
    verify(w2, code2)
    labels = {"h1": code, "h2": code2, "end": code2 + 4 * len(w2)}
    return w1 + w2, labels


def jal(target):
    return 0x0C000000 | ((target >> 2) & 0x3FFFFFF)


def _put_josa(blob, d0, josa):
    """자료 블록에 표지 표를 쓴다(`josa` = {"markers": [(표지, 있을 때, 없을 때)×3]})."""
    import struct

    for k, (mk, w, wo) in enumerate(josa["markers"]):
        struct.pack_into("<3H", blob, d0 + JMK + 6 * k, mk, w, wo)


def install(ram, code, data, half_codes, josa=None):
    """RAM 덤프(bytearray, 0 번지=물리 0)에 훅을 얹는다 — 시험용. 바꾼 자리를 돌려준다. `josa` = {"markers", "bt_addr", "bt"}(받침 비트표를 `bt_addr` 에 둔다)."""
    words, lab = build(code, data, josa["bt_addr"] if josa else None)
    assert len(half_codes) <= HALF_MAX
    blob = b"".join(w.to_bytes(4, "little") for w in words)
    ph = code & 0x1FFFFF
    ram[ph : ph + len(blob)] = blob
    dp = data & 0x1FFFFF
    ram[dp : dp + DATA_SIZE] = bytes(DATA_SIZE)
    for k, c in enumerate(half_codes):
        ram[dp + HALF_OFF + 2 * k : dp + HALF_OFF + 2 * k + 2] = c.to_bytes(2, "little")
    if josa:
        blob = bytearray(DATA_SIZE)
        _put_josa(blob, 0, josa)
        ram[dp + JMK : dp + JMK + 6 * N_JMARK] = blob[JMK : JMK + 6 * N_JMARK]
        bp = josa["bt_addr"] & 0x1FFFFF
        ram[bp : bp + len(josa["bt"])] = josa["bt"]
    for site, tgt in ((H1_SITE, lab["h1"]), (H2_SITE, lab["h2"])):
        o = site & 0x1FFFFF
        ram[o : o + 4] = jal(tgt).to_bytes(4, "little")
    return lab


def install_hx(ram, code2, h1, data):
    """RAM 덤프에 커서 줄 경로(HX1·HX2)를 얹는다 — 시험용. 깃발은 0 으로 둔다."""
    words, lab = build_hx(code2, h1, data)
    blob = b"".join(w.to_bytes(4, "little") for w in words) + bytes(HX_FLAG_SIZE)
    ph = code2 & 0x1FFFFF
    ram[ph : ph + len(blob)] = blob
    for site, tgt in ((HX1_SITE, lab["hx1"]), (HX2_SITE, lab["hx2"]), (HXQ_SITE, lab["hxq"])):
        o = site & 0x1FFFFF
        ram[o : o + 4] = jal(tgt).to_bytes(4, "little")
    return lab


# ── 실행파일에 얹기 ────────────────────────────────────────────────────────────
CAVE = (
    0x8001842C  # 호출자 없는 죽은 함수(정적 확인) — 🔴 실행 BP 로 동적 확인 전엔 시험 빌드에만 쓴다
)
CAVE_SIZE = 1420  # 0x8001842C~0x800189B7 — 🔴 뒤 0x800189B8 부터는 살아 있는 함수다(0x80018AAC 가 꼬리 점프로 들어온다). 처음엔 1588 로 덮어 필드 로드에서 죽었다(10-25)
H1_WORD = 0x00031840  # sll v1,v1,1
H2_WORD = 0x0C017794  # jal 0x8005de50
CAVE_SHA1 = "72bf3814bf69708a156117bf9904961f5c310035"  # 원판 동굴 구간(죽은 함수)


def bt_addr():
    """받침 비트표의 RAM 주소 — 한글에서 뺀 글리프 슬롯 12칸(`slots.BT_SLOTS`, 코드 101~112 — 후보 자리 중 연속 구간).
    🔴 처음엔 글리프 arena 끝 256B 에 뒀다가 장비 화면 화살표가 잡음이 됐다(arena 끝 1922~1935 는 엔진이 그리는 그림 조각) — 원본 문안이 쓰는 마지막 코드는 1872 라 그 뒤 슬롯(1873~)은 한자가 아니다."""
    import font
    import slots

    return common.EXE_TADDR + font.font_off() + slots.BT_SLOTS[0] * font.GLYPH_BYTES - common.EXE_HDR


def plan(josa=False):
    """(코드 주소, 데이터 주소, 워드, 라벨) — 데이터는 코드 바로 뒤(4 정렬)."""
    bt = bt_addr() if josa else None
    n = len(build(CAVE, CAVE, bt)[0])
    data = CAVE + 4 * n
    words, lab = build(CAVE, data, bt)
    assert len(words) == n
    assert data + DATA_SIZE <= CAVE + CAVE_SIZE, "훅이 동굴보다 크다"
    return CAVE, data, words, lab


def _off(addr):
    return addr - common.EXE_TADDR + common.EXE_HDR


def patch_exe(exe, half_codes, josa=None, item_blob=b""):
    """실행파일 버퍼(`bytearray`)에 훅을 얹는다 — 원판 자리를 확인(`expect`)하고 쓴다. 동굴 안은 원판이 죽은 함수라 통째로 덮는다.
    `josa` = {"markers": [(표지, 있을 때, 없을 때)×3], "bt": 받침 비트표 바이트(`BT_BYTES`)} — 있으면 조사 블록을 넣고 비트표를 글리프 arena 끝에 쓴다."""
    _, data, words, lab = plan(josa=bool(josa))
    if len(half_codes) > HALF_MAX:
        raise ValueError(f"반각 목록이 {HALF_MAX} 을 넘는다")
    for site, want in ((H1_SITE, H1_WORD), (H2_SITE, H2_WORD)):
        got = int.from_bytes(exe[_off(site) : _off(site) + 4], "little")
        if got != want:
            raise SystemExit(f"🔴 훅 자리 {site:#x} 가 원판이 아니다({got:#010x}≠{want:#010x})")
    import hashlib

    if hashlib.sha1(exe[_off(CAVE) : _off(CAVE) + CAVE_SIZE]).hexdigest() != CAVE_SHA1:
        raise SystemExit("🔴 동굴 구간이 원판이 아니다(이미 무언가 얹혔다)")
    import os

    part = os.environ.get("ED_HOOK_PARTIAL", "")  # 분해 시험용 — code 면 코드만, data 면 자료만
    blob = bytearray(exe[_off(CAVE) : _off(CAVE) + CAVE_SIZE]) if part else bytearray(CAVE_SIZE)
    if part != "data":
        blob[: 4 * len(words)] = b"".join(w.to_bytes(4, "little") for w in words)
    d0 = data - CAVE
    for k, c in enumerate(half_codes if part != "code" else []):
        blob[d0 + HALF_OFF + 2 * k : d0 + HALF_OFF + 2 * k + 2] = c.to_bytes(2, "little")
    if josa:
        assert len(josa["bt"]) <= BT_BYTES
        _put_josa(blob, d0, josa)
        bo = _off(bt_addr())
        exe[bo : bo + len(josa["bt"])] = josa["bt"]
    exe[_off(CAVE) : _off(CAVE) + CAVE_SIZE] = blob
    patch_hx(exe, lab["h1"], data, item_blob)
    import os

    use = os.environ.get("ED_HOOK_SITES", "h1,h2").split(",")  # 분해 시험용 — 어느 자리를 jal 로 바꿀지
    for name, site, tgt in (("h1", H1_SITE, lab["h1"]), ("h2", H2_SITE, lab["h2"])):
        if name in use:
            exe[_off(site) : _off(site) + 4] = jal(tgt).to_bytes(4, "little")


def patch_hx(exe, h1, data, item_blob=b""):
    """둘째 동굴(커서 줄 경로)과 두 호출 자리를 실행파일에 얹는다 — 원판 자리·구간을 확인하고 쓴다. `ED_NO_HX=1` 이면 건너뛴다(분해 시험용)."""
    import hashlib
    import os

    if os.environ.get("ED_NO_HX") == "1":
        return
    for site, want in ((HX1_SITE, HX1_WORD), (HX2_SITE, HX2_WORD), (HXQ_SITE, HXQ_WORD)):
        got = int.from_bytes(exe[_off(site) : _off(site) + 4], "little")
        if got != want:
            raise SystemExit(f"🔴 커서 줄 훅 자리 {site:#x} 가 원판이 아니다({got:#010x}≠{want:#010x})")
    if hashlib.sha1(exe[_off(CAVE2) : _off(CAVE2) + CAVE2_SIZE]).hexdigest() != CAVE2_SHA1:
        raise SystemExit("🔴 둘째 동굴 구간이 원판이 아니다(이미 무언가 얹혔다)")
    words, lab = build_hx(CAVE2, h1, data)
    assert lab["end"] <= CAVE2 + CAVE2_SIZE, "커서 줄 훅이 둘째 동굴보다 크다"
    blob = bytearray(CAVE2_SIZE)
    blob[: 4 * len(words)] = b"".join(w.to_bytes(4, "little") for w in words)
    exe[_off(CAVE2) : _off(CAVE2) + CAVE2_SIZE] = blob
    for site, tgt in ((HX1_SITE, lab["hx1"]), (HX2_SITE, lab["hx2"]), (HXQ_SITE, lab["hxq"])):
        exe[_off(site) : _off(site) + 4] = jal(tgt).to_bytes(4, "little")
    if item_blob:
        patch_item(exe, item_blob, lab["end"])


def patch_item(exe, blob, hx_end):
    """아이템 메뉴 구조체를 둘째 동굴에 쓰고 사용처 셋을 돌린다(위 `ITEM_*`)."""
    for a, want in ITEM_WORDS.items():
        got = int.from_bytes(exe[_off(a) : _off(a) + 4], "little")
        if got != want:
            raise SystemExit(f"🔴 아이템 구조체 사용처 {a:#x} 가 원판이 아니다({got:#010x}≠{want:#010x})")
    assert hx_end <= ITEM_STUBS and ITEM_STUBS + 32 <= ITEM_STRUCT
    assert len(blob) <= ITEM_STRUCT_MAX
    hi, lo = _lo_hi(ITEM_STRUCT)
    words, _ = asm(
        f"""
    lui s5, {hi:#x}
    jr ra
    ori s5, s5, {lo:#x}
    lui a1, {hi:#x}
    jr ra
    ori a1, a1, {lo:#x}
""",
        ITEM_STUBS,
    )
    verify(words, ITEM_STUBS)
    exe[_off(ITEM_STUBS) : _off(ITEM_STUBS) + 4 * len(words)] = b"".join(w.to_bytes(4, "little") for w in words)
    exe[_off(ITEM_STRUCT) : _off(ITEM_STRUCT) + len(blob)] = blob
    for site, k in ((ITEM_SITE_A, 0), (ITEM_SITE_B, 3)):
        exe[_off(site) : _off(site) + 4] = jal(ITEM_STUBS + 4 * k).to_bytes(4, "little")
    for a, want, new in ITEM_MSG_PATCH:
        got = int.from_bytes(exe[_off(a) : _off(a) + 4], "little")
        if got != want:
            raise SystemExit(f"🔴 아이템 메시지 창 {a:#x} 가 원판이 아니다({got:#010x}≠{want:#010x})")
        exe[_off(a) : _off(a) + 4] = new.to_bytes(4, "little")
    # 복사 원본 — `lui v0,hi` / `addiu a2,v0,lo`(부호 보정)
    ahi = ((ITEM_STRUCT >> 16) + (1 if (ITEM_STRUCT & 0xFFFF) >= 0x8000 else 0)) & 0xFFFF
    exe[_off(ITEM_COPY_LUI) : _off(ITEM_COPY_LUI) + 4] = (0x3C020000 | ahi).to_bytes(4, "little")
    exe[_off(ITEM_COPY_ADD) : _off(ITEM_COPY_ADD) + 4] = (0x24460000 | (ITEM_STRUCT & 0xFFFF)).to_bytes(4, "little")
