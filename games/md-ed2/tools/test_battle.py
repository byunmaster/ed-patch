"""전투 일괄 시험 롬 — 디버그 롬(`work/build/debug/`) 위에 메시지 렌더러 후크 하나를 얹는다. 시험 전용(꼬리표 `test-battle`).

    python3 tools/test_battle.py     # work/build/test-battle/ed2-kr (TESTBATTLE).bin

왜: 전 몬스터 전투를 에뮬로 일괄 돌릴 때 화면을 매번 찍으면 호출이 수천 번이다. 메시지 렌더러 `0xB738`(A1 = 스트림 시작)
입구에서 **처음 보는 문구(스트림 앞 10바이트 해시)** 일 때만 표식 주소(`MARK`)를 지나가게 해, 거기에 exec BP(pause)를 걸면 새 문구에서만 멈춘다.
 - 본 문구 해시 표: RAM `$FF1910`(워드 개수) + `$FF1912`~(롱 × 최대 60). 블록마다 에이전트가 개수를 0 으로 쓴다.
 - 같은 후크가 살아 있는 몬스터 HP 를 999 로 채워 전투가 끝나지 않게 한다(파티 공격력은 에이전트가 1 로 낮춘다).
 - 후크 코드는 디버그 롬 안의 0 런(`HOOK_AT`, 원본·번역 어느 쪽도 쓰지 않는 칸)에 놓는다 — 롬 꼬리는 4B 만 남았다.
 - 입구 6B(`movem.l` + `cmpi.l` 앞 2B)를 `jmp HOOK` 으로 바꾸고, 후크가 밀려난 두 명령을 대신 실행한 뒤 `0xB742` 로 돌아간다.
행동 난수 대체 — `$FF1A10` 을 1 로 쓰면 몬스터 행동 난수가 순열이 되어 기술이 고루 나온다(0 이면 원래 난수).
제품·`debug` 롬에는 넣지 않는다(출력 칸이 `test-battle` 이 아니면 거부). 헤더 체크섬을 다시 맞춘다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SRC = common.WORK / "build" / "debug" / "ed2-kr (DEBUG).bin"
OUT = common.WORK / "build" / "test-battle" / "ed2-kr (TESTBATTLE).bin"
ENTRY = 0xB738
RETURN_TO = 0xB742
HOOK_AT = 0x1790E
HOOK_ROOM = 1134
TABLE = 0xFF1910  # 전투 중에도 0 인 RAM 틈(0xFF1910~, 343B) — 0xFFBC59~ 의 큰 0 런은 전투 중 지워져 못 쓴다(실측)
CAP = 60
PENDING = 0xFF1A12  # 새 문구를 만났다(출구에서 캡처 카운터로 바뀐다)
CAPCNT = 0xFF1A14  # 캡처 카운터(워드)
EXIT_AT = 0xBAE4  # movem.l (a7)+,d0-d7/a3-a5 ; rts — 렌더러 출구
MONON = 0xFF1A16  # 0 이 아니면 몬스터 HP 고정을 켠다(에이전트가 조우를 열기 전에 1 로 쓴다)
MAIL = 0xFF1A18  # 워프 우편함(0x80~0x99) — 걸음마다 확인해 한 번 실행하고 비운다
SAY = 0xFF1A1C  # 대사 우편함(롱) — 0 이 아니면 그 주소를 a1(스트림)로 메시지 서비스 0x85E2 를 한 번 부르고 비운다(전 씬 대사 일괄 검수)
PRE = 0xFF1A26  # 롱(a5 값) — 0 이 아니면 대사 서비스 앞에 그 서비스(예 0x042D)를 먼저 부른다(d4 = $FF1CBE 워드 − 2, 실물 씬 코드와 같은 인자)
SAYTMP = 0xFF1A22  # 대사 주소 사본(앞 서비스가 a1 을 망가뜨린다)
FORCEMSG = 0xFF1A28  # 롱 — 0 이 아니면 렌더러가 **다음에** 그리는 문안 대신 이 스트림을 그린다(전투 중 조건부 문구를 실제 전투 창에서 직접 부른다)
BUSY = 0xFF1A20  # 대사 서비스가 도는 동안 1
WARP = 0x35E0  # 워프 실행기(d0 = 0x80 + 목록 색인)
TICK_AT = 0x188A2  # 필드 걸음 후크 자리(movem.l d0,-(a7) + cmpi.b #$62,$FF01B2 앞 6B)
TICK_RET = 0x188AE
FORCE = 0xFF1A10  # 0 이 아니면 난수 대체(+1 = 순열 상태)
RAND_AT = 0x1D620  # jsr $1D640.l (4EB9 0001 D640) — 행동 난수의 원시 호출
RAND_RAW = 0x1D640
MON_HP = 0xFF1EC0  # 몬스터 레코드(+0 현재 HP · +2 최대 HP), 0x40 간격 — 6칸


def hook_code(entry_old: bytes) -> tuple[bytes, int, int, int]:  # (코드, RNGF 오프셋, EXIT 오프셋)
    """후크 기계어와 MARK 오프셋(후크 시작 기준)을 돌려준다. 분기 변위는 라벨로 계산한다."""
    A = HOOK_AT
    pc = 0
    out = bytearray()
    labels: dict[str, int] = {}
    fix: list[tuple[int, str, str]] = []  # (위치, 라벨, 종류)

    def emit(b: bytes):
        nonlocal pc
        out.extend(b)
        pc += len(b)

    def label(n):
        labels[n] = pc

    def bra(op: int, n):
        fix.append((len(out), n, "b"))
        emit(bytes([op, 0]))

    emit(entry_old[:4])  # movem.l d0-d7/a3-a5,-(a7)
    emit(bytes.fromhex("48e70790"))  # movem.l d5-d7/a0/a3,-(a7)
    # 몬스터 HP 고정 — 렌더러가 불릴 때마다 살아 있는 몬스터(0 < HP < 999) 여섯 칸을 999(HUD 3자리)로 채운다(턴을 끌기 위해)
    emit(
        bytes.fromhex("4a39") + struct.pack(">I", MONON)
    )  # tst.b MONON — 전투가 아닐 때 필드 변수를 건드리지 않는다(GPGX 필드가 까맣게 죽었다)
    bra(0x67, "NOMON")
    emit(bytes.fromhex("41f9") + struct.pack(">I", MON_HP))  # lea MON_HP,a0
    emit(bytes.fromhex("7e03"))  # moveq #3,d7 (몬스터 최대 넷 — 그 뒤 칸은 다른 자료)
    label("MON")
    emit(bytes.fromhex("3c10"))  # move.w (a0),d6
    bra(0x67, "SKIP")  # beq.s SKIP
    emit(bytes.fromhex("0c4603e7"))  # cmpi.w #999,d6
    bra(0x64, "SKIP")  # bcc.s SKIP (999 이상은 그대로 — 보스는 원래 HP)
    emit(
        bytes.fromhex("3e280002")
    )  # move.w 2(a0),d7  — 최대 HP 도 999 미만이고 현재 ≤ 최대인 칸만(몬스터 뒤 칸은 포인터라 건드리면 죽는다 — 실측)
    emit(bytes.fromhex("0c4703e7"))  # cmpi.w #999,d7
    bra(0x64, "SKIP")
    emit(bytes.fromhex("bc47"))  # cmp.w d7,d6
    bra(0x62, "SKIP")  # bhi.s SKIP
    emit(bytes.fromhex("20bc03e703e7"))  # move.l #$03E703E7,(a0)
    label("SKIP")
    emit(bytes.fromhex("41e80040"))  # lea $40(a0),a0
    fix.append((len(out), "MON", "dbra"))
    emit(bytes.fromhex("51cf0000"))  # dbra d7,MON
    label("NOMON")
    # HUD 스크래치 버퍼(0xFFF000~, 숫자가 계속 바뀌어 매번 「새 문구」가 된다 — 실측)는 건너뛴다
    emit(bytes.fromhex("b3fc") + struct.pack(">I", 0xFFF000))  # cmpa.l #$FFF000,a1
    bra(0x64, "SEEN")  # bcc.s SEEN
    emit(bytes.fromhex("4ab9") + struct.pack(">I", FORCEMSG))  # tst.l FORCEMSG
    bra(0x67, "NOFORCE")
    emit(bytes.fromhex("2279") + struct.pack(">I", FORCEMSG))  # movea.l FORCEMSG,a1
    emit(bytes.fromhex("42b9") + struct.pack(">I", FORCEMSG))  # clr.l FORCEMSG
    label("NOFORCE")
    # 열쇠 = 스트림 앞 10바이트의 회전 xor 해시(주소로 보면 같은 문구가 버퍼마다 「새 것」이 된다 — 실측)
    emit(bytes.fromhex("2649"))  # movea.l a1,a3
    emit(bytes.fromhex("7c00"))  # moveq #0,d6
    emit(bytes.fromhex("7a09"))  # moveq #9,d5
    label("H")
    emit(bytes.fromhex("eb9e"))  # rol.l #5,d6
    emit(bytes.fromhex("7e00"))  # moveq #0,d7
    emit(bytes.fromhex("1e1b"))  # move.b (a3)+,d7
    emit(bytes.fromhex("bf86"))  # eor.l d7,d6
    fix.append((len(out), "H", "dbra"))
    emit(bytes.fromhex("51cd0000"))  # dbra d5,H
    emit(bytes.fromhex("41f9") + struct.pack(">I", TABLE + 2))  # lea table+2,a0
    emit(bytes.fromhex("3e39") + struct.pack(">I", TABLE))  # move.w table,d7
    bra(0x67, "NEW")  # beq.s NEW
    emit(bytes.fromhex("5347"))  # subq.w #1,d7
    label("L")
    emit(bytes.fromhex("bc98"))  # cmp.l (a0)+,d6
    bra(0x67, "SEEN")
    fix.append((len(out), "L", "dbra"))
    emit(bytes.fromhex("51cf0000"))  # dbra d7,L
    label("NEW")
    emit(bytes.fromhex("0c79") + struct.pack(">HI", CAP, TABLE))  # cmpi.w #CAP,table
    bra(0x64, "SEEN")  # bcc.s SEEN
    emit(bytes.fromhex("2086"))  # move.l d6,(a0)
    emit(bytes.fromhex("5279") + struct.pack(">I", TABLE))  # addq.w #1,table
    emit(
        bytes.fromhex("13fc0001") + struct.pack(">I", PENDING)
    )  # move.b #1,PENDING (렌더 끝에서 캡처 신호)
    label("SEEN")
    emit(bytes.fromhex("4cdf09e0"))  # movem.l (a7)+,d5-d7/a0/a3
    emit(bytes.fromhex("0c80fdecba98"))  # cmpi.l #$fdecba98,d0
    emit(bytes.fromhex("4ef9") + struct.pack(">I", RETURN_TO))  # jmp $B742
    label("MARK")
    emit(bytes.fromhex("4e714e75"))  # nop ; rts   (BP 자리 = MARK)
    # 몬스터 행동 난수 `0x1D618`(서비스 0x5C4)이 부르는 원시 난수 `0x1D640` 의 대체 — `$FFBF00` 이 0 이 아니면
    # 호출마다 `$FFBF01` 에 0x9D 를 더한 값(0..255)을 난수로 돌려준다(저불일치 순열 → 가중치 구간이 고루 나온다).
    label("RNGF")
    emit(bytes.fromhex("4a39") + struct.pack(">I", FORCE))  # tst.b FORCE
    bra(0x67, "ORIG")
    emit(bytes.fromhex("0639009d") + struct.pack(">I", FORCE + 1))  # addi.b #$9D,FORCE+1
    emit(bytes.fromhex("7000"))  # moveq #0,d0
    emit(bytes.fromhex("1039") + struct.pack(">I", FORCE + 1))  # move.b FORCE+1,d0
    emit(bytes.fromhex("4e75"))  # rts
    label("ORIG")
    emit(bytes.fromhex("4ef9") + struct.pack(">I", RAND_RAW))  # jmp $1D640
    # 렌더러 출구 `0xBAE4`(movem + rts)의 대체 — 새 문구를 그린 호출이 끝날 때만 캡처 카운터 `CAPCNT` 를 올린다.
    # 에이전트는 `hold_until(CAPCNT)` 로 「새 문구가 화면에 다 그려진 순간」에 멈춘다(BP 중복 이벤트 없이 호출 둘로 한 문구).
    label("EXIT")
    emit(bytes.fromhex("4a39") + struct.pack(">I", PENDING))  # tst.b PENDING
    bra(0x67, "EXDONE")
    emit(bytes.fromhex("4239") + struct.pack(">I", PENDING))  # clr.b PENDING
    emit(bytes.fromhex("5279") + struct.pack(">I", CAPCNT))  # addq.w #1,CAPCNT
    label("EXDONE")
    emit(bytes.fromhex("4cdf38ff4e75"))  # movem.l (a7)+,d0-d7/a3-a5 ; rts  (밀려난 원래 출구)
    # 필드 매 걸음 후크 `0x188A2`(디버그 C+방향 검사 바로 앞) — 우편함 `MAIL`($FF1A18)이 0 이 아니면 그 값을 d0 로 워프 실행기 `0x35E0` 을 한 번 부른다
    # (워프의 날개 목록 `0x32B3F` 의 항목 id 0x80~0x99 — 방문 플래그와 목록 검사를 거치지 않고 곧장 이동). 밀려난 `movem.l d0,-(a7)` + `cmpi.b #$62,$FF01B2` 는 여기서 대신 실행한다.
    label("TICK")
    emit(bytes.fromhex("4ab9") + struct.pack(">I", SAY))  # tst.l SAY
    bra(0x67, "NOSAY")
    emit(bytes.fromhex("48e7fffe"))  # movem.l d0-d7/a0-a6,-(a7)
    emit(bytes.fromhex("2279") + struct.pack(">I", SAY))  # movea.l SAY,a1
    emit(bytes.fromhex("23f9") + struct.pack(">II", SAY, SAYTMP))  # move.l SAY,SAYTMP
    emit(bytes.fromhex("42b9") + struct.pack(">I", SAY))  # clr.l SAY
    emit(bytes.fromhex("13fc0001") + struct.pack(">I", BUSY))  # move.b #1,BUSY
    emit(bytes.fromhex("4ab9") + struct.pack(">I", PRE))  # tst.l PRE
    bra(0x67, "NOPRE")
    emit(bytes.fromhex("3839") + struct.pack(">I", 0xFF1CBE))  # move.w $FF1CBE,d4
    emit(bytes.fromhex("5504"))  # subq.b #2,d4
    emit(bytes.fromhex("3a04"))  # move.w d4,d5
    emit(bytes.fromhex("e04d"))  # lsr.w #8,d5
    emit(bytes.fromhex("2a79") + struct.pack(">I", PRE))  # movea.l PRE,a5
    emit(bytes.fromhex("2c780200"))  # movea.l $200.w,a6
    emit(bytes.fromhex("4e96"))  # jsr (a6)
    emit(bytes.fromhex("2279") + struct.pack(">I", SAYTMP))  # movea.l SAYTMP,a1
    label("NOPRE")
    emit(bytes.fromhex("2a7c000085e2"))  # movea.l #$85E2,a5
    emit(bytes.fromhex("2c780200"))  # movea.l $200.w,a6
    emit(bytes.fromhex("4e96"))  # jsr (a6)
    emit(bytes.fromhex("4239") + struct.pack(">I", BUSY))  # clr.b BUSY
    emit(bytes.fromhex("4cdf7fff"))  # movem.l (a7)+,d0-d7/a0-a6
    label("NOSAY")
    emit(bytes.fromhex("4a39") + struct.pack(">I", MAIL))  # tst.b MAIL
    bra(0x67, "NOREQ")
    emit(bytes.fromhex("48e7fffe"))  # movem.l d0-d7/a0-a6,-(a7)
    emit(bytes.fromhex("7000"))  # moveq #0,d0
    emit(bytes.fromhex("1039") + struct.pack(">I", MAIL))  # move.b MAIL,d0
    emit(bytes.fromhex("4239") + struct.pack(">I", MAIL))  # clr.b MAIL
    emit(bytes.fromhex("4eb9") + struct.pack(">I", WARP))  # jsr $35E0
    emit(bytes.fromhex("4cdf7fff"))  # movem.l (a7)+,d0-d7/a0-a6
    label("NOREQ")
    emit(bytes.fromhex("48e78000"))  # movem.l d0,-(a7)   (밀려난 원래 명령)
    emit(
        bytes.fromhex("0c39006200ff01b2")
    )  # cmpi.b #$62,$FF01B2.l (밀려난 원래 명령 — 디버그 롬은 0x62)
    emit(bytes.fromhex("4ef9") + struct.pack(">I", TICK_RET))  # jmp $188AE
    for at, n, kind in fix:
        if kind == "b":
            d = labels[n] - (at + 2)
            assert 0 < d < 127, (n, d)
            out[at + 1] = d
        elif kind == "dbra":
            d = labels[n] - (at + 2)
            out[at + 2 : at + 4] = struct.pack(">h", d)
        else:
            out[at + 2 : at + 6] = struct.pack(">I", A + labels[n])
    return bytes(out), labels["RNGF"], labels["EXIT"], labels["TICK"]


def verify(code: bytes) -> None:
    """디스어셈블 연속 디코드로 검산(손인코딩 규율)."""
    from capstone import CS_ARCH_M68K, CS_MODE_M68K_000, Cs

    md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
    n = sum(1 for _ in md.disasm(code, HOOK_AT))
    last = list(md.disasm(code, HOOK_AT))[-1]
    if last.address + last.size != HOOK_AT + len(code):
        raise SystemExit("test_battle: 후크 디코드가 끝까지 이어지지 않는다")
    print(f"  후크 {len(code)}B · 명령 {n}")


def main() -> None:
    if common.BUILD_TAG != "test-battle":
        raise SystemExit(f"꼬리표 test-battle 에서만 굽는다(지금 {common.BUILD_TAG!r})")
    rom = bytearray(SRC.read_bytes())
    if rom[HOOK_AT : HOOK_AT + HOOK_ROOM] != bytes(HOOK_ROOM):
        raise SystemExit(f"{HOOK_AT:#x} 의 {HOOK_ROOM}B 가 0 이 아니다 — 후크 자리를 다시 찾는다")
    old = bytes(rom[ENTRY : ENTRY + 6])
    if old[:4] != bytes.fromhex("48e7ff1c") or old[4:] != bytes.fromhex("0c80"):
        raise SystemExit(f"{ENTRY:#x} 입구 바이트가 기대와 다르다: {old.hex()}")
    if bytes(rom[RAND_AT : RAND_AT + 6]) != bytes.fromhex("4eb90001d640"):
        raise SystemExit(f"{RAND_AT:#x} 가 jsr $1D640 이 아니다")
    if bytes(rom[EXIT_AT : EXIT_AT + 6]) != bytes.fromhex("4cdf38ff4e75"):
        raise SystemExit(f"{EXIT_AT:#x} 가 렌더러 출구가 아니다")
    if bytes(rom[TICK_AT : TICK_AT + 6]) != bytes.fromhex("48e780000c39"):
        raise SystemExit(f"{TICK_AT:#x} 가 필드 걸음 후크 자리가 아니다")
    code, rngf, exit_off, tick_off = hook_code(old)
    verify(code)
    rom[HOOK_AT : HOOK_AT + len(code)] = code
    rom[RAND_AT + 2 : RAND_AT + 6] = struct.pack(">I", HOOK_AT + rngf)
    rom[EXIT_AT : EXIT_AT + 6] = bytes.fromhex("4ef9") + struct.pack(">I", HOOK_AT + exit_off)
    rom[TICK_AT : TICK_AT + 6] = bytes.fromhex("4ef9") + struct.pack(">I", HOOK_AT + tick_off)
    rom[ENTRY : ENTRY + 6] = bytes.fromhex("4ef9") + struct.pack(">I", HOOK_AT)
    rom[0x18E:0x190] = struct.pack(">H", common.header_checksum(bytes(rom)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(rom))
    print(
        f"  RNGF = {HOOK_AT + rngf:#x} · EXIT = {HOOK_AT + exit_off:#x} · 캡처 카운터 ${CAPCNT:X} · 표 ${TABLE:X} · 출력 {OUT}"
    )


if __name__ == "__main__":
    main()
