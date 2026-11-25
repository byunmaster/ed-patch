"""QA 전용 디버그 빌드 — `ED_DEBUG_QA=1` + 꼬리표 `qa-debug` 에서만 `build.py` 가 부른다(마스터 11-18).

🔴 제품·시험 빌드에는 안 들어간다 — 스위치 없이 구운 이미지는 바이트 불변이다(제품 롬 sha1 대조).
원판엔 쓸 만한 디버그가 없다(`status.md` 「디버그·개발 기능 분석」) — 그래서 패드 갱신 함수에 **핫키 훅**을 건다.

진입키: **Select+L2+R2 를 누른 채**(원판은 Select 단독·0x200/0x400 을 안 읽고 이 세 키 조합을 쓰지 않는다) 다음 키.
  △ 돈 +10000 Pia · □ 경험치 +1000(파티 전원) · ○ 아이템 줌(현재 번호) · L1 아이템 번호 +1 · R1 아이템 번호 −1
기능은 훅 안에서 **RAM 에 직접 쓴다**(이벤트 핸들러를 부르면 멎는다 — 10-18 실측).

자리: `0x8008D03C~`(SDK 오류 문자열 꼬리 280B, 원판 그대로 남던 죽은 자료 — 제품 빌드도 안 건드린다) 앞 12B 는 레지스터 보관, 상태 8B 는 `0x8008A2AC`(정렬 패딩). 스택은 안 쓴다(메뉴 안에서 훅이 터졌다).
"""

import os
import struct

import engine_patch as E

HOOK = 0x80085CF0  # lui v0,0x801d ; lw v0,0x6da8(v0) — 패드 갱신 함수 안, 눌림 워드를 읽는 자리
RET = 0x80085CF8
SPACE = 0x8008D03C
SPACE_LEN = 280
STATE = (
    0x80008400 if os.environ.get("ED_QA_WARP") == "1" else 0x800BE800
)  # 실행파일 끝~파티 변수 사이 bss(실측 0·안 변함) — u32 직전 눌림 · u32 마지막 준 아이템 번호 · 12B 레지스터 보관. 🔴 코드와 같은 쪽에 쓰면 재컴파일러가 터진다
PREV = STATE
ITEM = STATE + 4
SV = STATE + 8  # t0~t2 보관
CODE = SPACE
HOOK_ORIG = (0x3C02801D, 0x8C426DA8)
CHORD = 0x103  # Select 0x100 + R2 0x2 + L2 0x1
MONEY_ADDR = 0x800C11D0
MONEY_ADD = 10000
EXP_ADD = 1000
PARTY = 0x800C05F0  # 레코드 간격 0x48, +0 0x8000 = 사용 중, +0x20 u32 경험치
PARTY_SLOTS = 8

# ── 워프(11-18) — 코드 자리: 정적으로 아무도 안 읽고 원판 동적 덫(접촉·전투·메뉴·상점, 양성 대조 0x8008D90C 살아 있음)에서 0회인 SDK 함수 자리
# 0x8008D634(320B). 이름 표는 게임 자신의 맵 표(RAM 0x800A9C8C, 10B × 443)를 그대로 읽는다.
# 워프 코드는 **EXE 뒤에 붙인다**(11-18 — d634 등 「죽은 SDK 함수」 자리는 부팅에서 데이터로 읽혀 안 된다, status.md).
# `ED_QA_WARP=1` 일 때만: 빌드 뒤 `qa_relocate.py` 가 이미지 끝으로 ED3.EXE 를 옮기고 적재 크기를 늘려 `WARP` 자리에 코드를 싣는다(QA 빌드 전용 — 제품 게이트는 그대로).
WARP_ON = os.environ.get("ED_QA_WARP") == "1"
WARP = 0x80008000  # (낮은 RAM — ED3.EXE 가 도는 동안 아무도 안 쓴다: 접촉·전투·메뉴·상점 덫 스텁이 이 자리에서 멀쩡히 돌았다. 시작 코드가 복사해 온다) 옛 설명: 원래 EXE 끝(0x800BE800) 바로 뒤 — 적재 크기를 늘려 얻는다. STATE(0x800BF000)도 늘린 구간 안이라 0 으로 시작한다
PAYLOAD_SRC = 0x800BE840  # 늘린 적재 구간 안 — 복사기(0x800BE800)가 시작 직후 이 자리에서 WARP 로 옮긴다. ⚠ 이 구간은 게임 bss 가 나중에 쓴다(실측) — 시작 때 한 번만 읽는다
COPIER = 0x800BE800
BASE = 0x80010000 if WARP_ON else 0x800C0000
BASE_HI = "0x8001" if WARP_ON else "0x800c"
EXTRA = 0x1000  # 늘리는 적재 크기(2섹터)
WARP_BLOB = b""
MAP_TABLE_RAM = 0x800A9C8C
MAP_COUNT = 443
PTR = 0x800DD6F8  # 이벤트 스크립트 포인터 — 우리 버퍼를 가리키면 엔진이 제 문맥에서 돌린다(워프 실측 10-18)
RAS = STATE + 0x14  # 호출자 ra 보관
IDX = STATE + 0x18  # 고른 맵 번호(표 인덱스)
LASTCH = (
    STATE + 0x1C
)  # 마지막으로 장 시작 점프를 한 장 + 1(0 = 모름 → 첫 이동은 늘 장 시작으로 간다)
SVR = STATE + 0x20  # a0~a3 보관
BUF = STATE + 0x30  # 스크립트 버퍼 16B(0 으로 끝난다)
TOG = STATE + 0x40  # 조우 끄기 토글(0/1) — Select+L2+R2 + ✕
WALL = STATE + 0x44  # 모드(0~3): bit0 벽 뚫기 · bit1 이동 속도 ×2 — Select+L2+R2 + Start 를 누를 때마다 0→1→2→3→0
SPEED_HOOKS = (0x8003CA4C, 0x8007CF10, 0x80081448)  #  # 엔티티 프레임 이동 jal 0x8003abec(a0=번호, a1=속도 — 한 걸음 16 을 2×속도씩 깎는다)
SPEED_FN = 0x8003ABEC
WALL_HOOK = 0x8003BC2C  # 플레이어 이동의 충돌 판정 호출 jal 0x80036ec8 (막힘=-1)
WALL_FN = 0x80036EC8
LOG = (
    STATE + 0x50
)  # 조우 기록 링(16B × 16 + 앞 4B 카운터) — 이벤트 VM 전투 연산(0x30/0x5B) 핸들러가 지날 때마다 한 줄
ENC_HOOK = 0x80070498  # 전투 핸들러 안 「이미 치른 지점이면 건너뜀」 분기(beqz v1) — 피연산자를 다 읽은 뒤라 건너뛰어도 스크립트 커서가 맞는다
ENC_TEMP_LO = int(
    os.environ.get("ED_QA_ENC_LO", "0x70"), 0
)  # 첫 피연산자(플래그 번호)가 LO~LO+15 인 조우만 끈다 — 기본 0x70~0x7F(맵마다 되쓰는 임시 플래그 칸, 정적 통계 466건). ED_QA_ENC_LO 는 시험용(0x40 이면 튜토리얼 멧돼지 칸)
ENC_SKIP = 0x800712D4  # 핸들러 끝(에필로그)
ENC_CONT = 0x800704A8  # 원판 분기가 안 건너뛸 때 가는 곳
CH_FIRST = [
    67,
    110,
    168,
    216,
    264,
    311,
    361,
    384,
]  # 장 1~8 이 시작하는 표 인덱스 — apply() 가 맵 표로 다시 확인한다


def _o(a):
    return a - BASE  # BASE 기준 부호 있는 오프셋


WARP_SRC = f"""
 lui t0,{BASE_HI}
 sw ra,{_o(RAS)}(t0)
 sw a0,{_o(SVR)}(t0)
 sw a1,{_o(SVR) + 4}(t0)
 sw a2,{_o(SVR) + 8}(t0)
 sw a3,{_o(SVR) + 12}(t0)
 lw a0,{_o(IDX)}(t0)
 andi a1,v0,0x1000
 beq a1,zero,k1
 nop
 addiu a0,a0,1
k1:
 andi a1,v0,0x4000
 beq a1,zero,k2
 nop
 addiu a0,a0,-1
k2:
 andi a1,v0,0x2000
 beq a1,zero,k3
 nop
 addiu a0,a0,10
k3:
 andi a1,v0,0x8000
 beq a1,zero,k4
 nop
 addiu a0,a0,-10
k4:
 andi a1,v0,0x4
 beq a1,zero,k5
 nop
 addiu a0,a0,100
k5:
 andi a1,v0,0x40
 beq a1,zero,k6
 nop
 lw a2,{_o(TOG)}(t0)
 nop
 xori a2,a2,1
 sw a2,{_o(TOG)}(t0)
k6:
 andi a1,v0,0x800
 beq a1,zero,k7
 nop
 lw a2,{_o(WALL)}(t0)
 nop
 addiu a2,a2,1
 andi a2,a2,3
 sw a2,{_o(WALL)}(t0)
k7:
 bgez a0,w1
 nop
 addiu a0,a0,{MAP_COUNT}
w1:
 slti a1,a0,{MAP_COUNT}
 bne a1,zero,w2
 nop
 addiu a0,a0,-{MAP_COUNT}
w2:
 sw a0,{_o(IDX)}(t0)
 andi a1,v0,0x8
 beq a1,zero,fin
 nop
 li a1,0
 lui a2,{{TBL_HI}}
 ori a2,a2,{{TBL_LO}}
 li a3,{len(CH_FIRST)}
lp:
 lhu t1,0(a2)
 nop
 sltu t1,a0,t1
 bne t1,zero,got
 nop
 addiu a1,a1,1
 addiu a3,a3,-1
 bne a3,zero,lp
 addiu a2,a2,2
got:
 lw a2,{_o(LASTCH)}(t0)
 addiu a3,a1,1
 sw a3,{_o(LASTCH)}(t0)
 sw zero,{_o(BUF)}(t0)
 sw zero,{_o(BUF) + 4}(t0)
 sw zero,{_o(BUF) + 8}(t0)
 sw zero,{_o(BUF) + 12}(t0)
 beq a2,a3,same
 nop
 sll a1,a1,24
 lui t1,0xff
 ori t1,t1,0x214
 or a3,a1,t1
 beq zero,zero,setp
 sw a3,{_o(BUF)}(t0)
same:
 li a3,0x214
 sh a3,{_o(BUF)}(t0)
 li a3,6
 sb a3,{_o(BUF) + 2}(t0)
 sll a1,a0,3
 sll a2,a0,1
 addu a1,a1,a2
 lui a2,{MAP_TABLE_RAM >> 16:#x}
 ori a2,a2,{MAP_TABLE_RAM & 0xFFFF:#x}
 addu a1,a1,a2
 addiu a2,t0,{_o(BUF) + 3}
cp:
 lbu t1,0(a1)
 addiu a1,a1,1
 sb t1,0(a2)
 addiu a3,a3,-1
 bne a3,zero,cp
 addiu a2,a2,1
setp:
 lui a1,{BASE_HI}
 addiu a1,a1,{_o(BUF)}
 lui a2,0x800e
 sw a1,{PTR - 0x800E0000}(a2)
fin:
 lw a0,{_o(SVR)}(t0)
 lw a1,{_o(SVR) + 4}(t0)
 lw a2,{_o(SVR) + 8}(t0)
 lw a3,{_o(SVR) + 12}(t0)
 lw ra,{_o(RAS)}(t0)
 nop
 jr ra
 nop
tbl:
 nop
 nop
 nop
 nop
"""

ENC_STUB = 0
# 조우 기록 + 끄기 스텁 — 핸들러가 0x80070498 에서 여기로 온다(v1 = 「이미 치른」 비트, fp = 핸들러 프레임). v1·fp·s0·s1 은 건드리지 않는다.
ENC_SRC = f"""
 lui t0,0x8000
 ori t0,t0,{LOG & 0xFFFF:#x}
 lw t1,0(t0)
 nop
 andi t2,t1,15
 sll t2,t2,4
 addu t2,t2,t0
 addiu t2,t2,16
 addiu t1,t1,1
 sw t1,0(t0)
 lui t3,0x801e
 lbu t3,-0x7a24(t3)
 nop
 sb t3,0(t2)
 lh t3,0x38(fp)
 nop
 sb t3,1(t2)
 lh t3,0x18(fp)
 nop
 sh t3,2(t2)
 lh t3,0x1a(fp)
 nop
 sh t3,4(t2)
 lui t3,0x800c
 lbu t1,0x15e4(t3)
 lbu t3,0x15e5(t3)
 sb t1,8(t2)
 sb t3,9(t2)
 lbu t1,0x28(fp)
 lbu t3,0x29(fp)
 sb t1,10(t2)
 sb t3,11(t2)
 lbu t1,0x2a(fp)
 lbu t3,0x2b(fp)
 sb t1,12(t2)
 sb t3,13(t2)
 lw t1,{TOG - LOG}(t0)
 nop
 beq t1,zero,orig
 nop
 lh t1,0x18(fp)
 nop
 addiu t1,t1,-{ENC_TEMP_LO}
 sltiu t1,t1,16
 beq t1,zero,orig
 nop
 j {ENC_SKIP:#x}
 nop
orig:
 beq v1,zero,go
 nop
 j {ENC_SKIP:#x}
 nop
go:
 j {ENC_CONT:#x}
 nop
"""

WALL_STUB = 0
# 벽 뚫기 스텁 — 플레이어 충돌 판정 호출을 대신 부른다. 켜짐이고 판정이 이동량을 비워 둔 채(막힘: 반환 0 또는 -1) 끝났으면, 판정 함수가 비워 둔 이동량(엔티티 +0x12/+0x14/+0x16)을 방향표(0x800B45C4)로 채우고 0(통과)을 돌려준다.
WALL_SRC = f"""
 addiu sp,sp,-8
 sw ra,0(sp)
 jal {WALL_FN:#x}
 nop
 lw ra,0(sp)
 addiu sp,sp,8
 lui t0,0x8000
 ori t0,t0,{WALL & 0xFFFF:#x}
 lw t1,0(t0)
 nop
 andi t1,t1,1
 beq t1,zero,wout
 nop
 lw t3,0x38(fp)
 nop
 lhu t5,0x12(t3)
 lhu t6,0x14(t3)
 nop
 or t5,t5,t6
 bne t5,zero,wout
 nop
 lh t2,0x20(fp)
 nop
 andi t2,t2,7
 sll t2,t2,2
 lui t4,0x800b
 addiu t4,t4,0x45c4
 addu t4,t4,t2
 lhu t5,0(t4)
 lhu t6,2(t4)
 sh t5,0x12(t3)
 sh t6,0x14(t3)
 sh zero,0x16(t3)
 move v0,zero
wout:
 jr ra
 nop
"""

SPEED_STUB = 0
SPEED_SRC = f"""
 lui t0,0x8000
 ori t0,t0,{WALL & 0xFFFF:#x}
 lw t1,0(t0)
 nop
 andi t1,t1,2
 beq t1,zero,sout
 nop
 sll a1,a1,1
sout:
 j {SPEED_FN:#x}
 nop
"""

WARP_CALL = f"jal {WARP:#x}" if WARP_ON else "nop"
WARP_NOP = "nop"
SRC = f"""
 lui v1,{BASE_HI}
 sw t0,{SV - BASE}(v1)
 sw t1,{SV + 4 - BASE}(v1)
 sw t2,{SV + 8 - BASE}(v1)
 lui t0,0x801d
 lw t1,0x6da8(t0)
 lui t2,{BASE_HI}
 lw v0,{PREV - BASE}(t2)
 sw t1,{PREV - BASE}(t2)
 and v0,t1,v0
 subu v0,t1,v0
 andi t0,t1,{CHORD:#x}
 li v1,{CHORD:#x}
 bne t0,v1,done
 nop
 {WARP_CALL}
 {WARP_NOP}
 andi t0,v0,0x10
 beq t0,zero,n_sq
 nop
 lui t0,{MONEY_ADDR >> 16:#x}
 lw v1,{MONEY_ADDR & 0xFFFF:#x}(t0)
 nop
 addiu v1,v1,{MONEY_ADD}
 sw v1,{MONEY_ADDR & 0xFFFF:#x}(t0)
n_sq:
 andi t0,v0,0x80
 beq t0,zero,n_ci
 nop
 lui t0,{PARTY >> 16:#x}
 ori t0,t0,{PARTY & 0xFFFF:#x}
 li v1,{PARTY_SLOTS}
exp_lp:
 lh t1,0(t0)
 nop
 bgez t1,exp_nx
 nop
 lw t1,0x20(t0)
 nop
 addiu t1,t1,{EXP_ADD}
 sw t1,0x20(t0)
exp_nx:
 addiu v1,v1,-1
 bne v1,zero,exp_lp
 addiu t0,t0,0x48
n_ci:
 andi t0,v0,0x20
 beq t0,zero,done
 nop
 lui t0,0x801d
 lhu t1,0x65d0(t0)
 ori t0,t0,0xab40
 sltiu v1,t1,0x20
 beq v1,zero,done
 nop
 sll v1,t1,1
 addu v1,v1,t0
 lw t0,{ITEM - BASE}(t2)
 nop
 addiu t0,t0,1
 sh t0,0(v1)
 sw t0,{ITEM - BASE}(t2)
 lui t0,0x801d
 addiu t1,t1,1
 sh t1,0x65d0(t0)
done:
 lui v1,{BASE_HI}
 lw t0,{SV - BASE}(v1)
 lw t1,{SV + 4 - BASE}(v1)
 lw t2,{SV + 8 - BASE}(v1)
 lui v0,0x801d
 j {RET:#x}
 lw v0,0x6da8(v0)
"""


def _apply_warp(exe):
    import warp_table

    ch = [r[1][0] for r in warp_table.table("ed3")]
    assert len(ch) == MAP_COUNT and all(a <= b for a, b in zip(ch, ch[1:])), (
        "맵 표가 장 단조가 아니다"
    )
    first = [i for i in range(1, MAP_COUNT) if ch[i] != ch[i - 1]]
    assert first == CH_FIRST, f"장 경계가 바뀌었다 {first}"
    _w, lab = E.asm(WARP_SRC.replace("{TBL_HI}", "0").replace("{TBL_LO}", "0"), WARP)
    tbl = lab["tbl"]
    words, _ = E.asm(
        WARP_SRC.replace("{TBL_HI}", f"{tbl >> 16:#x}").replace("{TBL_LO}", f"{tbl & 0xFFFF:#x}"),
        WARP,
    )
    n = len(words) - 4
    data = struct.pack("<8H", *CH_FIRST)
    payload = b"".join(struct.pack("<I", w) for w in words[:n]) + data
    stub_at = WARP + len(payload)
    sw, _ = E.asm(ENC_SRC, stub_at)
    E.verify(sw, stub_at)
    payload += b"".join(struct.pack("<I", w) for w in sw)
    global ENC_STUB, WALL_STUB
    ENC_STUB = stub_at
    wat = stub_at + len(sw) * 4
    ww, _ = E.asm(WALL_SRC, wat)
    E.verify(ww, wat)
    payload += b"".join(struct.pack("<I", w) for w in ww)
    WALL_STUB = wat
    sat = wat + len(ww) * 4
    spw, _ = E.asm(SPEED_SRC, sat)
    E.verify(spw, sat)
    payload += b"".join(struct.pack("<I", w) for w in spw)
    global SPEED_STUB
    SPEED_STUB = sat
    payload = payload.ljust((len(payload) + 3) // 4 * 4, b"\0")
    if len(payload) > STATE - WARP:
        raise SystemExit(f"🔴 워프 코드가 자리를 넘었다 — {len(payload)}B > {STATE - WARP}B")
    E.verify(words[:n], WARP)
    # 복사기 — 늘린 구간(PAYLOAD_SRC)의 코드를 낮은 RAM(WARP)으로 옮긴다. 시작 코드(0x80011BC0)가 부른다. v0 은 안 건드린다(시작 코드가 곧 쓴다).
    copier, _ = E.asm(
        f"""
 lui t0,{PAYLOAD_SRC >> 16:#x}
 ori t0,t0,{PAYLOAD_SRC & 0xFFFF:#x}
 lui t1,{WARP >> 16:#x}
 ori t1,t1,{WARP & 0xFFFF:#x}
 li t2,{len(payload) // 4}
cp:
 lw t3,0(t0)
 addiu t0,t0,4
 sw t3,0(t1)
 addiu t2,t2,-1
 bne t2,zero,cp
 addiu t1,t1,4
 j 0x80011bc8
 nop
""",
        COPIER,
    )
    E.verify(copier, COPIER)
    head = b"".join(struct.pack("<I", w) for w in copier)
    assert len(head) <= PAYLOAD_SRC - COPIER
    global WARP_BLOB
    WARP_BLOB = head.ljust(PAYLOAD_SRC - COPIER, b"\0") + payload
    return f"워프 {len(payload)}B(낮은 RAM {WARP:#x}) · 복사기 {len(head)}B @ 늘린 구간 {COPIER:#x}"


def _apply_bss_skip(exe):
    """시작 코드(0x80011B98)가 0x800B79F0~0x801F8CB8 을 0 으로 민다 — 늘린 적재 구간(0x800BE800~)의 코드도 지워진다(11-18 실측).
    그 구간 중 파일에 든 0x800B79F0~0x800BE800(28,176B)은 **원판에서 전부 0** 이라 시작을 0x800BF800 으로 미뤄도 시작 직후 RAM 이 바이트까지 같다."""
    E._expect(exe, 0x80011B98, (0x3C02800B, 0x244279F0), "시작 코드 bss 지우기 시작")
    words, _ = E.asm("lui v0,0x800c\naddiu v0,v0,-0x800", 0x80011B98)
    for k, w in enumerate(words):
        struct.pack_into("<I", exe, E._off(0x80011B98) + 4 * k, w)
    E._expect(exe, 0x80011BC0, (0, 0), "시작 코드 빈 자리(복사기 호출)")
    jw, _ = E.asm(f"j {COPIER:#x}", 0x80011BC0)
    struct.pack_into("<I", exe, E._off(0x80011BC0), jw[0])


def apply(exe):
    E._expect(exe, HOOK, HOOK_ORIG, "패드 갱신 훅 자리")
    words, _lab = E.asm(SRC, CODE)
    if len(words) * 4 > SPACE_LEN:
        raise SystemExit(f"🔴 QA 훅이 자리를 넘었다 — {len(words) * 4}B > {SPACE_LEN}B")
    E.verify(words, CODE)
    blob = b"" + b"".join(struct.pack("<I", w) for w in words)
    o = E._off(SPACE)
    exe[o : o + SPACE_LEN] = blob + bytes(SPACE_LEN - len(blob))
    if WARP_ON:
        _apply_bss_skip(exe)
    wnote = _apply_warp(exe) if WARP_ON else "워프 꺼짐(ED_QA_WARP=1 로 켠다 — 자리 미해결)"
    if WARP_ON:
        E._expect(exe, ENC_HOOK, (0x10600003, 0), "전투 핸들러 건너뜀 분기")
        ew, _ = E.asm(f"j {ENC_STUB:#x}", ENC_HOOK)
        struct.pack_into("<I", exe, E._off(ENC_HOOK), ew[0])
        E._expect(exe, WALL_HOOK, (0x0C000000 | ((WALL_FN >> 2) & 0x3FFFFFF),), "충돌 판정 호출")
        ww, _ = E.asm(f"jal {WALL_STUB:#x}", WALL_HOOK)
        struct.pack_into("<I", exe, E._off(WALL_HOOK), ww[0])
        for sh_ in SPEED_HOOKS:
            E._expect(exe, sh_, (0x0C000000 | ((SPEED_FN >> 2) & 0x3FFFFFF),), "엔티티 이동 호출")
            spw, _ = E.asm(f"jal {SPEED_STUB:#x}", sh_)
            struct.pack_into("<I", exe, E._off(sh_), spw[0])
    hook, _ = E.asm(f"j {CODE:#x}\nnop", HOOK)
    for k, w in enumerate(hook):
        struct.pack_into("<I", exe, E._off(HOOK) + 4 * k, w)
    return f"QA 핫키 훅 {len(words) * 4}B · {wnote}"
