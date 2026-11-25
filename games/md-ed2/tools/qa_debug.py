"""QA 디버그 롬 — 제품 롬 위에 편의 기능 후크를 얹는다. 꼬리표 `qa-debug` 에서만 굽는다(제품 롬은 한 바이트도 안 바꾼다).

    ED_BUILD_TAG=qa-debug python3 tools/qa_debug.py     # work/build/qa-debug/ed2-kr (QA-DEBUG).bin

마스터 11-18 「제품판에 넣기보단 내 qa용으로 … 최대한 원본에 들어있는 디버그 기능을 살리면서 편의성을」.
이 모듈은 빌드(`build.py`)와 따로 돈다 — 이미 구운 제품 롬(`work/build/md-ed2/ed2-kr.bin`)을 읽어 후크만 얹어 다른 칸에 쓴다.
제품 롬·제품 빌드 경로는 이 모듈을 모르고, 출력 칸이 `qa-debug` 가 아니면 거부한다.

진입: 제품에 있는 디버그 진입키(필드에서 Start+A+B 약 1초, `debug_key.py`)로 디버그 레벨 `$FF01B2`=0x62 가 켜져 있을 때만 아래 조합이 듣는다.
조합은 원판이 필드에서 읽지 않는 **Start + 방향**(필드의 Start 는 단독으로도 반응하지 않는다 — status.md 「디버그 진입키」). 누르는 순간 한 번(변화 감지).
  Start+위   돈 +10,000 (상한 999,999)
  Start+아래 경험치 +1,000 (파티 4칸 전부, 상한 9,999,999) — 레벨업은 다음 전투 승리 때(원판 레벨 검사 `0x412C` 가 전투 뒤에 돈다 — 필드에서 부르면 메시지창이 안 그려져 쓰지 않는다, 실측 11-18)
  Start+왼쪽 몬스터 무시 켜기/끄기 — 켜진 동안 몬스터가 닿아도 전투가 안 열린다(보스·고정 전투 객체와 이벤트 전투는 그대로). 효과음 한 번.
  Start+오른쪽 아이템 한 개 — 눌러 올 때마다 다음 번호(0~136) 아이템이 아트리스의 빈 칸에 들어간다(꽉 차면 마지막 칸 덮어쓰기). 이름·사용 문구 확인용
  Start+C    워프 — 누를 때마다 다음 목적지(월드 문 레코드 22곳: 루디아·크루즈·네리아·리젤 … 7430)로 문 이동(조건 없이)
Start+조합은 원판 일시정지에 Start 가 안 보이게 지운다(진입키 뒤 정지가 남으면 Start 단독으로 한 번 눌러 푼다).
후크는 VBlank 의 패드 갱신 호출(`0xD530`)을 가로채는 제품 진입키 후크 앞에 한 겹 더 얹는다 — 먼저 제품 후크를 그대로 부른 뒤 조합을 본다.
자리: 제품 롬의 `0x1790E~0x17D04`(1,014B, 원판 오프닝 자막 옛 영역 — 제품에서 전부 0).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import debug_key

TAG = "qa-debug"
SRC = common.WORK / "build" / "md-ed2" / "ed2-kr.bin"
OUT = common.WORK / "build" / TAG / "ed2-kr (QA-DEBUG).bin"
HOOK_AT = 0x1790E
HOOK_ROOM = debug_key.HOOK_AT - HOOK_AT  # 1014B
ENTRY = debug_key.ENTRY  # 0xD530 — `jsr 후크`(6B)

PAD = 0xFF0058
LEVEL = 0xFF01B2
PREV = 0xFF1A32  # 직전 패드 바이트(코드 어디서도 안 쓰는 칸 — 진입키 카운터 `$FF1A30` 바로 뒤)
SND = 0xFF2024
MONEY = 0xFF1B2C  # 돈(BE 롱) — 전투 보상 +10 이 `$FF1B2F` 로 들어간다(실측 10-24)
MONEY_STEP = 10_000
MONEY_MAX = 999_999

COMBO_MONEY = 0x81  # Start(0x80) + 위(0x01)
COMBO_EXP = 0x82  # Start + 아래(0x02)
PARTY = 0xFF1DBC  # 파티 레코드 4칸 × 0x40 — +2 레벨 워드 · +4 HP · +0xC 경험치(롱, 전투 보상 가산 `0x24A42` 의 `add.l d1,$c(a1)`)
EXP_STEP = 1000
EXP_MAX = 9_999_999
COMBO_IGN = 0x84  # Start + 왼쪽 — 몬스터 무시 토글
COMBO_ITEM = 0x88  # Start + 오른쪽 — 아이템 한 개 받기(번호가 눌러 올 때마다 하나씩 오른다)
ITEM_SLOT0 = 30  # 파티 레코드 안 소지품 6칸(+30~+35, 0xEF = 빈 칸) — 「사용」 메뉴에 넣은 번호가 그대로 뜬다(실측 11-18: 0x05 = 횃불)
ITEM_COUNT = 137  # 아이템 표 139 중 뒤 둘은 빈 칸(tables.py)
ITEMCTR = 0xFF1A34  # 다음에 줄 아이템 번호(바이트, 리셋하면 0)
IGN = 0xFF1A33  # 몬스터 무시 플래그(바이트, 코드 어디서도 안 쓰는 칸 — PREV 바로 뒤)
BATTLE_START = 0x6734  # 전투 시작: `$FF3474`/`$FF2076` = 적 객체, `$FF3606` = 조우 번호, `$FF1852` |= 0x40 (호출처 0x1030·0x10DA·0x641E + 씬 스크립트)
BATTLE_HEAD = bytes.fromhex("23c9" "00ff3474")  # move.l a1,$ff3474.l
CHASE_RESUME = 0x673A
COMBO_WARP = 0xA0  # Start + C — 다음 목적지로 워프
WCTR = 0xFF1A35  # 다음 워프 목적지 색인(바이트)
DOOR_BUF = 0xFF208C  # 문 이동 처리기(0x195DC)가 읽는 35B 목적지 기록 — 워프 = 여기에 쓰고 $FF1851=0 · $FF1852(워드) |= 4 = 바이트 $FF1853 |= 4 (devlog 「워프 해결」)
WARP_REC_AT = 0x1F7400  # 제품 롬 꼬리 0xFF 채움 구간(0x1F7302~, 13,700B) — 기록 표 22 × 35B


WARP_DESTS = [0x7010, 0x7020, 0x7030, 0x7040, 0x7100, 0x7110, 0x7120, 0x7130, 0x7140, 0x7200,
              0x7210, 0x7220, 0x7240, 0x7250, 0x7260, 0x7300, 0x7310, 0x7320, 0x7400, 0x7410, 0x7420, 0x7430]  # 월드맵 문 레코드 22(warp.TOWN_RECORDS 중 7000·7001 은 열어 보면 문 이동이 안 끝나 뺐다)


def warp_table() -> bytes:
    """목적지 35B 기록 22개 — 월드맵 씬 모듈(블록 37 모듈 1)에서 뽑는다."""
    import dialog
    import warp

    d = dialog.module(*warp.WORLD_MOD).data
    return b"".join(bytes(d[warp.TOWN_RECORDS[m] : warp.TOWN_RECORDS[m] + 35]) for m in WARP_DESTS)


def _assemble() -> tuple[bytes, int]:
    """(후크 바이트, 몬스터 무시 스텁 오프셋)."""
    L: dict[str, int] = {}
    out = bytearray()
    fix: list[tuple[int, str, int]] = []  # (위치, 라벨, 크기 1|2)

    def emit(hexs: str):
        out.extend(bytes.fromhex(hexs.replace(" ", "")))

    def br(op: str, label: str):  # 짧은 분기
        fix.append((len(out), label, 1))
        emit(op + "00")

    def brw(op: str, label: str):  # 워드 분기(멀리)
        emit(op + "00")
        fix.append((len(out), label, 2))
        emit("0000")

    def lab(n: str):
        L[n] = len(out)

    emit("4eb9" + f"{debug_key.HOOK_AT:08x}")  # jsr 제품 진입키 후크 (패드 갱신 + Start+A+B 1초)
    emit("48e7e0c0")  # movem.l d0-d2/a0-a1,-(a7)
    emit("0c39" "0062" f"{LEVEL:08x}")  # cmpi.b #$62,LEVEL
    brw("66", "out")  # bne — 디버그 레벨이 꺼져 있으면 아무것도 안 한다
    emit("4239" "00ff0057")  # clr.b $FF0057 — 원판 일시정지 플래그(Start 가 켜고 끈다)를 늘 내린다: 진입키 Start+A+B 가 남긴 정지도 풀린다
    emit("103900" + f"{PAD & 0xFFFFFF:06x}")  # move.b PAD,d0
    emit("0c000080")  # cmpi.b #$80,d0
    br("63", "nm")  # bls — Start 단독(또는 Start 없음)이면 그대로 둔다(일시정지는 원판대로)
    emit("0239007f" + f"00{PAD & 0xFFFFFF:06x}")  # andi.b #$7f,PAD — Start+무언가는 조합 키: 원판 일시정지 판정이 Start 를 못 보게 지운다
    lab("nm")
    emit("123900" + f"{PREV & 0xFFFFFF:06x}")  # move.b PREV,d1
    emit("13c0" "00" + f"{PREV & 0xFFFFFF:06x}")  # move.b d0,PREV
    emit("b200")  # cmp.b d0,d1
    brw("67", "out")  # beq — 변화 없음(누르고 있는 동안 반복 안 함)
    # 돈
    emit("0c00" f"00{COMBO_MONEY:02x}")  # cmpi.b #COMBO_MONEY,d0
    br("66", "exp")
    emit("243900" + f"{MONEY & 0xFFFFFF:06x}")  # move.l MONEY,d2
    emit("0682" f"{MONEY_STEP:08x}")  # addi.l #STEP,d2
    emit("0c82" f"{MONEY_MAX:08x}")  # cmpi.l #MAX,d2
    br("63", "mok")  # bls
    emit("243c" f"{MONEY_MAX:08x}")  # move.l #MAX,d2
    lab("mok")
    emit("23c2" "00" + f"{MONEY & 0xFFFFFF:06x}")  # move.l d2,MONEY
    br("60", "snd")  # bra
    # 경험치 — 파티 4칸 전부
    lab("exp")
    emit("0c00" f"00{COMBO_EXP:02x}")  # cmpi.b #COMBO_EXP,d0
    brw("66", "ign")
    emit("41f9" f"{PARTY:08x}")  # lea PARTY,a0
    emit("7403")  # moveq #3,d2
    lab("eloop")
    emit("2228000c")  # move.l $c(a0),d1
    emit("0681" f"{EXP_STEP:08x}")  # addi.l #STEP,d1
    emit("0c81" f"{EXP_MAX:08x}")  # cmpi.l #MAX,d1
    br("63", "eok")  # bls
    emit("223c" f"{EXP_MAX:08x}")  # move.l #MAX,d1
    lab("eok")
    emit("2141000c")  # move.l d1,$c(a0)
    emit("d1fc00000040")  # adda.l #$40,a0
    emit("51ca")  # dbra d2,eloop — 워드 변위(확장 워드 자리 기준)
    fix.append((len(out), "eloop", 2))
    emit("0000")
    lab("snd")
    emit("13fc001b00" + f"{SND & 0xFFFFFF:06x}")  # move.b #$1B,SND
    lab("out")
    emit("4cdf0307")  # movem.l (a7)+,d0-d2/a0-a1
    emit("4e75")  # rts
    # 몬스터 무시 켜기/끄기 — Start+왼쪽
    lab("ign")
    emit("0c00" f"00{COMBO_IGN:02x}")  # cmpi.b #COMBO_IGN,d0
    brw("66", "itm")
    emit("0a39" "0001" "00" + f"{IGN & 0xFFFFFF:06x}")  # eori.b #1,IGN
    brw("60", "snd")
    # 아이템 — Start+오른쪽: 다음 번호 아이템을 아트리스(파티 첫 칸)의 첫 빈 소지품 칸에 넣는다(꽉 찼으면 마지막 칸을 덮는다)
    lab("itm")
    emit("0c00" f"00{COMBO_ITEM:02x}")  # cmpi.b #COMBO_ITEM,d0
    brw("66", "wrp")
    emit("41f9" f"{PARTY + ITEM_SLOT0:08x}")  # lea 첫 소지품 칸,a0
    emit("7405")  # moveq #5,d2
    lab("iloop")
    emit("0c1000ef")  # cmpi.b #$ef,(a0) — 0xEF = 빈 칸
    br("67", "ifound")  # beq
    emit("5288")  # addq.l #1,a0
    emit("51ca")  # dbra d2,iloop
    fix.append((len(out), "iloop", 2))
    emit("0000")
    emit("5388")  # subq.l #1,a0 — 꽉 참: 마지막 칸을 덮는다
    lab("ifound")
    emit("1239" "00" + f"{ITEMCTR & 0xFFFFFF:06x}")  # move.b ITEMCTR,d1
    emit("1081")  # move.b d1,(a0)
    emit("5201")  # addq.b #1,d1
    emit("0c01" f"00{ITEM_COUNT:02x}")  # cmpi.b #COUNT,d1
    br("65", "iok")  # bcs
    emit("7200")  # moveq #0,d1
    lab("iok")
    emit("13c1" "00" + f"{ITEMCTR & 0xFFFFFF:06x}")  # move.b d1,ITEMCTR
    brw("60", "snd")
    # 워프 — Start+C: 다음 목적지의 35B 기록을 문 기록 칸에 쓰고 문 이동을 요청한다(조건 없이)
    lab("wrp")
    emit("0c00" f"00{COMBO_WARP:02x}")  # cmpi.b #COMBO_WARP,d0
    brw("66", "out")
    emit("1239" "00" + f"{WCTR & 0xFFFFFF:06x}")  # move.b WCTR,d1
    emit("0281000000ff")  # andi.l #$ff,d1
    emit("c2fc0023")  # mulu #35,d1
    emit("41f9" f"{WARP_REC_AT:08x}")  # lea 기록 표,a0
    emit("d1c1")  # adda.l d1,a0
    emit("43f9" f"{DOOR_BUF:08x}")  # lea DOOR_BUF,a1
    emit("7422")  # moveq #34,d2
    lab("wloop")
    emit("12d8")  # move.b (a0)+,(a1)+
    emit("51ca")  # dbra d2,wloop
    fix.append((len(out), "wloop", 2))
    emit("0000")
    emit("4239" "00ff1851")  # clr.b $FF1851
    emit("0039" "0004" "00ff1853")  # ori.b #4,$FF1853 — 워드 `$FF1852` 의 비트 2(문 이동 요청)는 낮은 바이트 `$FF1853` 에 있다
    emit("1239" "00" + f"{WCTR & 0xFFFFFF:06x}")  # move.b WCTR,d1
    emit("5201")  # addq.b #1,d1
    emit("0c01" f"00{len(WARP_DESTS):02x}")  # cmpi.b #N,d1
    br("65", "wok")
    emit("7200")
    lab("wok")
    emit("13c1" "00" + f"{WCTR & 0xFFFFFF:06x}")  # move.b d1,WCTR
    brw("60", "snd")
    # 전투 시작 루틴 `0x6734`(a1 = 적 객체)의 머리를 대신하는 스텁 — 접촉·추격·씬 스크립트가 전부 이 문으로 들어온다
    if len(out) & 1:
        emit("00")
    lab("stub")
    emit("0c39" "0062" f"{LEVEL:08x}")  # cmpi.b #$62,LEVEL
    br("66", "go")  # 디버그 레벨이 꺼져 있으면 원판 그대로
    emit("4a39" "00" + f"{IGN & 0xFFFFFF:06x}")  # tst.b IGN
    br("67", "go")
    for bit in (3, 4, 5):  # 객체 종류 `$1(a1) & 0x38 == 0x38` = 몬스터 — 아니면 원판 그대로
        emit("0829" f"{bit:04x}" "0001")  # btst #bit,1(a1)
        br("67", "go")
    emit("08290007" "0001")  # btst #7,1(a1) — 보스 표지(원판 접촉 판정이 따로 보는 비트)는 무시하지 않는다
    br("66", "go")
    emit("4e75")  # rts — 전투 시작 안 함(객체도 안 건드린다)
    lab("go")
    emit("23c9" "00ff3474")  # move.l a1,$ff3474.l — 덮어쓴 원판 첫 명령
    emit("4ef9" f"{CHASE_RESUME:08x}")  # jmp $673A
    for at, name, sz in fix:
        if sz == 2:
            out[at : at + 2] = struct.pack(">h", L[name] - at)
            continue
        d = L[name] - (at + 2)
        assert 0 <= d < 128, name
        out[at + 1] = d
    return bytes(out), L["stub"]


def code() -> bytes:
    return _assemble()[0]


def build(src: bytes) -> bytes:
    rom = bytearray(src)
    if bytes(rom[ENTRY : ENTRY + 6]) != debug_key.patch_entry():
        raise SystemExit("[qa-debug] 입구가 제품 진입키 후크가 아니다 — 제품 롬이 맞나")
    if any(rom[HOOK_AT : HOOK_AT + HOOK_ROOM]):
        raise SystemExit("[qa-debug] 후크 칸이 0 이 아니다")
    c = code()
    if len(c) > HOOK_ROOM:
        raise SystemExit(f"[qa-debug] 후크 {len(c)}B > 칸 {HOOK_ROOM}B")
    if bytes(rom[BATTLE_START : BATTLE_START + 6]) != BATTLE_HEAD:
        raise SystemExit("[qa-debug] 0x6734 가 전투 시작 루틴 머리가 아니다")
    rom[HOOK_AT : HOOK_AT + len(c)] = c
    wt = warp_table()
    if any(b != 0xFF for b in rom[WARP_REC_AT : WARP_REC_AT + len(wt)]):
        raise SystemExit("[qa-debug] 워프 표 칸이 0xFF 채움이 아니다")
    rom[WARP_REC_AT : WARP_REC_AT + len(wt)] = wt
    rom[BATTLE_START : BATTLE_START + 6] = bytes.fromhex("4ef9") + struct.pack(">I", HOOK_AT + _assemble()[1])
    rom[ENTRY : ENTRY + 6] = bytes.fromhex("4eb9") + struct.pack(">I", HOOK_AT)
    # 메가드라이브 헤더 체크섬(0x18E) — 0x200 이후 워드 합
    s = sum(struct.unpack(f">{(len(rom) - 0x200) // 2}H", bytes(rom[0x200:]))) & 0xFFFF
    rom[0x18E:0x190] = struct.pack(">H", s)
    return bytes(rom)


def main() -> None:
    if common.BUILD_TAG != TAG:
        raise SystemExit(f"꼬리표 {TAG} 에서만 굽는다(지금 {common.BUILD_TAG!r})")
    src = SRC.read_bytes()
    out = build(src)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(out)
    print(f"  qa-debug: {OUT.name} · 후크 {len(code())}B · 제품 롬 변경 0 (원본 {SRC.name} 읽기 전용)")


if __name__ == "__main__":
    main()
