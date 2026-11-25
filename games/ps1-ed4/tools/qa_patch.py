"""QA 디버그 메뉴를 실행파일에 얹는다 — **빌드 스위치 `ED_DEBUG_QA=1` 일 때만**(제품 빌드는 이 파일을 안 부른다 → 제품 롬 바이트 불변).

얹는 자리: 죽은 코드 구간(도달성 분석으로 찾았다 — 진입점·점프표·주소 상수에서 닿지 않는 명령 런, 같은 분석이 반각 동굴 둘을 정확히 되찾았다 → 검증됨.
헤드리스 덫 시험(필드 걷기·△ 메뉴·시스템 메뉴)에서 적중 0). 원판 바이트 sha1 을 핀으로 박아 둔다.
메뉴 진입 = L2+R2+SELECT 동시(원판이 안 읽는 조합) · 위/아래 = 커서 · ○ = 실행 · ✕ = 닫기. 코드는 `qa_debug.py`.
"""

import hashlib
import os

import halfwidth
import qa_debug as Q
import uitext

REGION = (
    0x8006107C,
    1404,
    "534540bdbf27fc1c462e5712618ab8c94acca81f",
)  # 메뉴 코드·데이터(죽은 구간)
REGION2 = (
    0x8005D4A4,
    900,
    "1cbcbdc252d92f1ed3efeffe13fb9ffd13339e3a",
)  # 몬스터 무시 스텁 + 줄 글 덩이(죽은 구간)
REGION3 = (
    0x8005C790,
    796,
    "9706250aead8f54df39f471a80de0d0007c80a9e",
)  # 벽 뚫기 스텁(죽은 구간)
WALL_SITE, WALL_FN = (
    0x8001C564,
    0x8001AE68,
)  # 이동 한 칸 검사(`0x8001c4dc`) 안 `jal 0x8001ae68`(지형 높이 조회 — 0xFFFF 면 막힘)
WALL_SITE_ORIG = 0x0C006B9A
WALL_OFF = 29  # ctl+29 = 벽 뚫기(1 이면 지형 조회 대신 제 높이를 돌려줘 늘 평지로 보이게 한다)
SPEED_SITE, SPEED_ORIG = 0x8003BB30, 0x27BDFFB0  # 보간 함수 `0x8003bb30` 첫 줄 `addiu sp,sp,-0x50` — j 로 바꾸면 지연 칸에 다음 줄 `move $a2,$a1`(a1 = 프레임당 진행량)이 실린다
SPEED_RET = 0x8003BB38
SPEED_OFF = 30  # ctl+30 = 이동 속도 2배(1 이면 플레이어(개체 0) 걸음의 프레임당 진행량을 두 배로)
PAD_SITE_ORIG = 0x0C019365  # jal 0x80064d94 — 원판
FIELD_SITE, FIELD_FN = (
    0x80057280,
    0x80041458,
)  # 필드 메인 루프의 `jal 0x80041458`(필드 접촉 → 전투 시작 판정, 마을은 `0x800975E8`=0 이라 통째로 건너뜀)
FIELD_SITE_ORIG = 0x0C010516
SKIP_OFF = 28  # ctl+28 = 몬스터 무시(1 이면 접촉 판정을 안 부른다)

ROWS = [
    "경험치 추가",
    "돈 추가",
    "아이템 추가",
    "워프",
    "몬스터 무시",
    "무시 해제",
    "벽 뚫기",
    "벽 해제",
    "속도 2배",
    "속도 해제",
    "닫기",
]


def enabled():
    return os.environ.get("ED_DEBUG_QA") == "1"


def chars():
    return "".join(ROWS)


def _exp(label):
    return f"""
    lui $t1, {Q.hi(Q.EXP1):#x}
    ori $t1, $t1, {Q.lo(Q.EXP1):#x}
    lhu $t2, 0($t1)
    nop
    addiu $t2, $t2, 200
    slti $t3, $t2, 1000
    bne $t3, $zero, {label}
    nop
    addiu $t2, $zero, 999
{label}:
    sh $t2, 0($t1)
    sh $t2, 4($t1)
"""


def _money(label):
    return f"""
    lui $t1, {Q.hi(Q.MONEY):#x}
    ori $t1, $t1, {Q.lo(Q.MONEY):#x}
    lw $t2, 0($t1)
    nop
    addiu $t2, $t2, 1000
    sw $t2, 0($t1)
"""


# 가방: 개수 바이트 · 항목 = (품목 번호, 개수) 2바이트 × 최대 32(원판 저장 루틴이 32 로 복사) · 이름 표 `0x8007EFF0`(u16 오프셋 256개 —
# 다음 오프셋과의 차가 2 이하면 이름 없는 빈 번호)
BAG_N, BAG = 0x801EFC68, 0x801F33F8
NAMETAB = 0x8007EFF0
ITEM_MAX = 220  # 이름 표에서 이름 있는 번호는 219 까지


def _item(p):
    """○ 마다 다음 품목 번호(ctl+20 에 기억, 이름 없는 번호는 건너뜀)를 가방에 하나 더한다 — 이미 있으면 개수 +1(상한 99), 없으면 끝에 덧붙임(가방 32 칸)."""
    return f"""
    lw $t0, 20($s1)
    nop
{p}NEXT:
    addiu $t0, $t0, 1
    slti $t1, $t0, {ITEM_MAX}
    bne $t1, $zero, {p}CHK
    nop
    addiu $t0, $zero, 1
{p}CHK:
    lui $t2, {Q.hi(NAMETAB):#x}
    ori $t2, $t2, {Q.lo(NAMETAB):#x}
    sll $t3, $t0, 1
    addu $t3, $t3, $t2
    lhu $t4, 0($t3)
    lhu $t5, 2($t3)
    nop
    subu $t4, $t5, $t4
    slti $t4, $t4, 3
    bne $t4, $zero, {p}NEXT
    nop
    sw $t0, 20($s1)
    lui $t1, {Q.hi(BAG_N):#x}
    ori $t1, $t1, {Q.lo(BAG_N):#x}
    lbu $t2, 0($t1)
    lui $t3, {Q.hi(BAG):#x}
    ori $t3, $t3, {Q.lo(BAG):#x}
    move $t4, $zero
{p}FIND:
    slt $t5, $t4, $t2
    beq $t5, $zero, {p}APP
    nop
    sll $t5, $t4, 1
    addu $t5, $t5, $t3
    lbu $t6, 0($t5)
    nop
    bne $t6, $t0, {p}FNX
    nop
    lbu $t6, 1($t5)
    nop
    addiu $t6, $t6, 1
    slti $t7, $t6, 100
    beq $t7, $zero, {p}DONE
    nop
    sb $t6, 1($t5)
    j {p}DONE
    nop
{p}FNX:
    addiu $t4, $t4, 1
    j {p}FIND
    nop
{p}APP:
    slti $t5, $t2, 32
    beq $t5, $zero, {p}DONE
    nop
    sll $t5, $t2, 1
    addu $t5, $t5, $t3
    sb $t0, 0($t5)
    addiu $t6, $zero, 1
    sb $t6, 1($t5)
    addiu $t2, $t2, 1
    sb $t2, 0($t1)
{p}DONE:
"""


MAPTAB, NMAPS = 0x80087808, 371  # 8B 항목(이름 7자 + 1) — 끝 항목은 `ZZZZZZZ`
VM_PC, OP14 = (
    0x800C65E8,
    0x80046F88,
)  # 이벤트 VM 프로그램 카운터 · 맵 이동 연산(0x14) 핸들러 — 연산 바이트 다음부터 읽는다


def _warp():
    """○ 마다 맵 표의 다음 맵(ctl+24 에 번호 기억)으로 게임 자신의 이동 연산(0x14) 핸들러를 직접 불러 이동한다(조건 없음).
    핸들러는 VM PC 에서 [방향, 길이 7, 이름 7자, 인자 3] 을 읽는다 — 스택에 지어 PC 를 꽂고, 불러 뒤 PC 를 되돌린다(이름은 워드 정렬 복사)."""
    return f"""
    lw $t0, 24($s1)
    nop
    addiu $t0, $t0, 1
    slti $t1, $t0, {NMAPS}
    bne $t1, $zero, WP1
    nop
    move $t0, $zero
WP1:
    sw $t0, 24($s1)
    addiu $sp, $sp, -16
    lui $t4, {Q.hi(MAPTAB):#x}
    ori $t4, $t4, {Q.lo(MAPTAB):#x}
    sll $t5, $t0, 3
    addu $t4, $t4, $t5
    lw $t6, 0($t4)
    lw $t7, 4($t4)
    sw $t6, 4($sp)
    sw $t7, 8($sp)
    sb $zero, 11($sp)
    sb $zero, 12($sp)
    sb $zero, 13($sp)
    sb $zero, 2($sp)
    addiu $t3, $zero, 7
    sb $t3, 3($sp)
    lui $t7, {Q.hi(VM_PC):#x}
    lw $s2, {Q.lo(VM_PC):#x}($t7)
    addiu $t3, $sp, 2
    sw $t3, {Q.lo(VM_PC):#x}($t7)
    jal {OP14:#x}
    nop
    lui $t7, {Q.hi(VM_PC):#x}
    sw $s2, {Q.lo(VM_PC):#x}($t7)
    addiu $sp, $sp, 16
"""


def _stub(ctl):
    """필드 접촉 판정 호출 자리의 대리인 — ctl+28 이 0 이면 원래 함수로 점프(ra 그대로), 아니면 그냥 돌아온다."""
    return f"""
STUB:
    lui $t0, {Q.hi(ctl + SKIP_OFF):#x}
    lbu $t0, {Q.lo(ctl + SKIP_OFF):#x}($t0)
    nop
    beq $t0, $zero, GO
    nop
    jr $ra
    nop
GO:
    j {FIELD_FN:#x}
    nop
"""


def _wall_stub(ctl):
    """지형 높이 조회 호출 자리의 대리인 — ctl+29 가 1 이고 이 개체의 높이(+0xa)가 2 이상이면 그 높이를 그대로 돌려줘 「같은 높이의 평지」로 보이게 한다.
    아니면 원래 함수로 점프(ra·스택 인자 그대로). 호출자(`0x8001c4dc`)의 s0 = 움직이는 개체."""
    return f"""
WSTUB:
    lui $t0, {Q.hi(ctl + WALL_OFF):#x}
    lbu $t0, {Q.lo(ctl + WALL_OFF):#x}($t0)
    nop
    beq $t0, $zero, WGO
    nop
    lhu $v0, 0xa($s0)
    nop
    sltiu $t1, $v0, 2
    bne $t1, $zero, WGO
    nop
    jr $ra
    nop
WGO:
    j {WALL_FN:#x}
    nop
"""


def _speed_stub(ctl):
    """보간 함수 입구의 대리인 — ctl+30 이 1 이고 a0(개체 번호) 가 0(플레이어)이면 a2(= a1, 지연 칸에서 복사됨)를 두 배로 한다."""
    return f"""
SSTUB:
    addiu $sp, $sp, -0x50
    lui $t0, {Q.hi(ctl + SPEED_OFF):#x}
    lbu $t0, {Q.lo(ctl + SPEED_OFF):#x}($t0)
    nop
    beq $t0, $zero, SGO
    nop
    bne $a0, $zero, SGO
    nop
    sll $a2, $a2, 1
SGO:
    j {SPEED_RET:#x}
    nop
"""


def _skip(v):
    return _flag(SKIP_OFF, v)


def _flag(off, v):
    return f"""
    addiu $t2, $zero, {v}
    sb $t2, {off}($s1)
"""


def apply(exe):
    """exe(bytearray)에 훅을 얹는다 — 구간이 원판이 아니면 중단한다."""
    base, size, sha = REGION
    o = halfwidth._off(base)
    if hashlib.sha1(bytes(exe[o : o + size])).hexdigest() != sha:
        raise SystemExit(f"🔴 QA 디버그 자리 {base:#x} 가 원판이 아니다(다른 패치가 먼저 썼다)")
    so = halfwidth._off(Q.PAD_SITE)
    if int.from_bytes(exe[so : so + 4], "little") != PAD_SITE_ORIG:
        raise SystemExit("🔴 패드 읽기 호출 자리가 원판이 아니다")
    b2, s2, sha2 = REGION2
    o2 = halfwidth._off(b2)
    if hashlib.sha1(bytes(exe[o2 : o2 + s2])).hexdigest() != sha2:
        raise SystemExit(f"🔴 QA 디버그 둘째 자리 {b2:#x} 가 원판이 아니다")
    fo = halfwidth._off(FIELD_SITE)
    if int.from_bytes(exe[fo : fo + 4], "little") != FIELD_SITE_ORIG:
        raise SystemExit("🔴 필드 접촉 판정 호출 자리가 원판이 아니다")
    b3, s3, sha3 = REGION3
    o3 = halfwidth._off(b3)
    if hashlib.sha1(bytes(exe[o3 : o3 + s3])).hexdigest() != sha3:
        raise SystemExit(f"🔴 QA 디버그 셋째 자리 {b3:#x} 가 원판이 아니다")
    wo = halfwidth._off(WALL_SITE)
    if int.from_bytes(exe[wo : wo + 4], "little") != WALL_SITE_ORIG:
        raise SystemExit("🔴 지형 높이 조회 호출 자리가 원판이 아니다")
    so2 = halfwidth._off(SPEED_SITE)
    if int.from_bytes(exe[so2 : so2 + 4], "little") != SPEED_ORIG:
        raise SystemExit("🔴 이동 보간 함수 입구가 원판이 아니다")
    codes = {t: uitext.kr_codes(t) for t in ROWS}
    acts = [
        (0, _exp("EXPOK")),
        (1, _money("MNY")),
        (2, _item("IT")),
        (3, _warp()),
        (4, _skip(1)),
        (5, _skip(0)),
        (6, _flag(WALL_OFF, 1)),
        (7, _flag(WALL_OFF, 0)),
        (8, _flag(SPEED_OFF, 1)),
        (9, _flag(SPEED_OFF, 0)),
        (10, "    j DOCLOSE\n    nop"),
    ]
    pool_at = b2 + 64
    blob, entry, ctl, _lab, pool = Q.build(base, ROWS, acts, lambda t: codes[t], pool_at)
    stub, _slab = Q.asm(_stub(ctl), b2)
    Q.verify(stub, b2)
    stub_b = b"".join(w.to_bytes(4, "little") for w in stub)
    if len(blob) > size or 64 < len(stub_b) or 64 + len(pool) > s2:
        raise SystemExit(
            f"🔴 QA 디버그 자리 초과 — 본체 {len(blob)}/{size} · 스텁 {len(stub_b)}/64 · 글 {len(pool)}/{s2 - 64}"
        )
    exe[o : o + size] = blob + bytes(size - len(blob))
    exe[o2 : o2 + s2] = stub_b.ljust(64, b"\0") + pool + bytes(s2 - 64 - len(pool))
    ws, _wl = Q.asm(_wall_stub(ctl), b3)
    Q.verify(ws, b3)
    wblob = b"".join(w.to_bytes(4, "little") for w in ws)
    sb3 = b3 + len(wblob)
    ss, _sl = Q.asm(_speed_stub(ctl), sb3)
    Q.verify(ss, sb3)
    sblob = b"".join(w.to_bytes(4, "little") for w in ss)
    if len(wblob) + len(sblob) > s3:
        raise SystemExit("🔴 QA 디버그 셋째 자리 초과")
    exe[o3 : o3 + s3] = (wblob + sblob).ljust(s3, b"\0")
    exe[so2 : so2 + 4] = (0x08000000 | ((sb3 >> 2) & 0x3FFFFFF)).to_bytes(4, "little")  # j(ra 보존)
    exe[wo : wo + 4] = Q.site_word(b3).to_bytes(4, "little")
    exe[so : so + 4] = Q.site_word(entry).to_bytes(4, "little")
    exe[fo : fo + 4] = Q.site_word(b2).to_bytes(4, "little")
