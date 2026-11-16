"""디버그 진입키 — 필드(어디서든)에서 **Start+A+B 를 약 1초(VBlank 52번) 함께** 누르면 원판에 남은 디버그 레벨 `$FF01B2` 가 한 단계 넘어간다(마스터 10-24 「제품에 넣자」).

  0 ↔ 0x62 (C 를 누른 채 걷기 = 벽 통과 · C 단독+방향 = 고속 이동) — 같은 키로 다시 누르면 꺼진다. 다시 켜도 리셋하면 0 으로 돌아간다.

엔딩 직행(타이틀 뒤 숨은 조합 A+B+C ~2초 → B 떼기)은 원판에선 `$FF01B2 == 0x63` 이어야 열렸는데, 이 변수는 리셋으로 지워져 **필드에서 무장해도 타이틀까지 못 간다**(실측 10-24 —
0x63 으로 올린 뒤 리셋하면 0). 그래서 그 비교(`0x127BA`)를 항상 참으로 바꿔 조합 자체가 키다 — A+B+C 를 100틱 눌러야 하니 우연히 열리지 않는다. 엔딩은 SRAM 을 건드리지 않는다(실측 10-16).

새 기능이 아니라 **원판에 죽어 있던 조건을 여는 것**이다 — 소비자는 `0x188A6`(==0x62) · `0x1B3C2`(0x61/0x62) · `0x2D0C0`(==0x62) · `0x127BA`(==0x63).
키를 놓기 전 다른 버튼이 섞이면(패드 바이트 ≠ 0xD0) 세기가 0 으로 돌아간다. 열릴 때 메뉴 열기 효과음(0x1B)이 한 번 난다.

기전: VBlank 핸들러 안의 패드 갱신 호출 `0xD530`(`jsr $AFEE.l`)을 `jsr 후크` 로 바꾸고, 후크가 그 호출을 대신 실행해 패드가 **갱신된 뒤** 패드 바이트 `$FF0058` 을 본다
(핸들러 맨 앞에서 읽으면 메인 루프가 만진 낡은 값이라 방향키가 섞여도 못 알아챘다 — 실측 10-24).
세기는 `$FF1A30`(워드, 코드 어디서도 안 쓰는 칸). 후크는 오프닝 자막 옛 영역(`0x1790E`~`0x17D7A`, 자막은 꼬리로 옮겨 가 비었다) 뒤 118B 에 놓는다 — 앞쪽은 `test_battle.py` 후크 몫.
"""

import struct

ENTRY = 0xD530
ENTRY_OLD = bytes.fromhex("4eb90000afee")  # jsr $AFEE.l — 패드 갱신
SERVICE = 0xAFEE
HOOK_AT = 0x17D04
HOOK_ROOM = 0x17D7A - HOOK_AT  # 0x17D7A~ 은 오프닝 자막 자료 표 몫(captions.py)
PAD = 0xFF0058  # 패드 원 상태 바이트 — 방향 0x0F · B 0x10 · C 0x20 · A 0x40 · Start 0x80 (VBlank 마다 갱신, 실측 10-24). `$FF1854` 는 메인 루프가 읽을 때만 갱신돼 늦다
COUNT = 0xFF1A30
LEVEL = 0xFF01B2
SND = 0xFF2024
COMBO = 0xD0 # Start(0x80)+A(0x40)+B(0x10) — 정확히 이 셋만
HOLD = 52  # 핸들러가 프레임당 0.83~1.0번 돈다(실측 10-24: 헤드리스 24프레임에 20~23번) — 52번 = 약 1초(0.87~1.05초)


def code() -> bytes:
    L: dict[str, int] = {}
    out = bytearray()
    fix: list[tuple[int, str]] = []

    def emit(hexs: str):
        out.extend(bytes.fromhex(hexs.replace(" ", "")))

    def br(op: str, label: str):  # 짧은 분기(바이트 변위)
        fix.append((len(out), label))
        emit(op + "00")

    def lab(n: str):
        L[n] = len(out)

    emit(ENTRY_OLD.hex())  # jsr $AFEE.l (대신 실행)
    emit("48e7c000")  # movem.l d0-d1,-(a7)
    emit("103900ff0058")  # move.b PAD,d0
    emit("0c00" f"00{COMBO:02x}")  # cmpi.b #COMBO,d0
    br("66", "rst")  # bne
    emit("323900ff1a30")  # move.w COUNT,d1
    emit("0c41" f"{HOLD + 1:04x}")  # cmpi.w #HOLD+1,d1
    br("64", "out")  # bcc (이미 열었다 — 놓을 때까지 그대로)
    emit("5241")  # addq.w #1,d1
    emit("33c100ff1a30")  # move.w d1,COUNT
    emit("0c41" f"{HOLD:04x}")  # cmpi.w #HOLD,d1
    br("66", "out")  # bne
    emit("103900ff01b2")  # move.b LEVEL,d0
    emit("0c000062")  # cmpi.b #$62,d0
    br("67", "to0")  # beq — 이미 열려 있으면 닫는다
    emit("13fc006200ff01b2")  # move.b #$62,LEVEL
    br("60", "snd")  # bra
    lab("to0")
    emit("13fc000000ff01b2")  # move.b #0,LEVEL
    lab("snd")
    emit("13fc001b00ff2024")  # move.b #$1B,SND (메뉴 열기 효과음)
    br("60", "out")
    lab("rst")
    emit("427900ff1a30")  # clr.w COUNT
    lab("out")
    emit("4cdf0003")  # movem.l (a7)+,d0-d1
    emit("4e75")  # rts
    for at, name in fix:
        d = L[name] - (at + 2)
        assert 0 <= d < 128, name
        out[at + 1] = d
    return bytes(out)


CMP_AT = 0x127BA  # cmpi.b #$63,$FF01B2 (0C39 0063 00FF 01B2) → cmp.b d0,d0 ; nop ×3 — 항상 같다
CMP_OLD = bytes.fromhex("0c39006300ff01b2")
CMP_NEW = bytes.fromhex("b0004e714e714e71")


def patch_entry() -> bytes:
    return bytes.fromhex("4eb9") + struct.pack(">I", HOOK_AT)  # jsr HOOK


def apply(rom) -> int:
    """제품 롬에 늘 쓴다. 입구 12B 가 원본 그대로이고 후크 칸이 0 일 때만."""
    old = bytes(rom.buf[ENTRY : ENTRY + len(ENTRY_OLD)])
    if old != ENTRY_OLD:
        raise SystemExit(f"[debug-key] {ENTRY:#x} 의 원본 바이트가 기대와 다르다 — 엔진 주소가 밀렸나")
    c = code()
    if len(c) > HOOK_ROOM:
        raise SystemExit(f"[debug-key] 후크 {len(c)}B > 칸 {HOOK_ROOM}B")
    # 칸 = 원판 오프닝 자막 영역의 뒤 끝(`captions.CLEAR_UNTIL` 가 지우지 않고 남긴 곳) — 원본 글이 그대로 있다. 후크가 칸을 0 으로 채워 덮는다.
    rom.write("debug-key-hook", HOOK_AT, c + bytes(HOOK_ROOM - len(c)))
    rom.write("debug-key-entry", ENTRY, patch_entry())
    if bytes(rom.buf[CMP_AT : CMP_AT + len(CMP_OLD)]) != CMP_OLD:
        raise SystemExit(f"[debug-key] {CMP_AT:#x} 의 원본 바이트가 기대와 다르다 — 엔진 주소가 밀렸나")
    rom.write("debug-key-combo", CMP_AT, CMP_NEW)
    return 3


def allowed() -> dict[str, tuple[int, int]]:
    return {
        "debug-key-hook": (HOOK_AT, HOOK_AT + HOOK_ROOM),
        "debug-key-entry": (ENTRY, ENTRY + len(ENTRY_OLD)),
        "debug-key-combo": (CMP_AT, CMP_AT + len(CMP_OLD)),
    }
