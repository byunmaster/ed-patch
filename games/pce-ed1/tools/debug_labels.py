"""디버그 화면 행 이름·ON/OFF 값·Gold 증가량(마스터 11-25 「⑤」).

- 행 이름: 원판 전각 한 글자(Ｐ Ｍ Ｇ Ｅ Ｗ Ｉ — 뱅크 0x77 `+1FE3`) → 영어 단어 PATH · MONSTER · GOLD · EXP · WARP · ITEM.
  새 줄 문자열은 뱅크 0x6D 끝 FF 패딩(`LABEL_OFF` — 라벨 글 뱅크는 디버그 화면에서 MPR4 에 걸려 있다)에 두고, `$656F` 의 포인터(`LDA #$E3`·`#$BF`)만 돌린다.
- ON/OFF: 원판 P·M 행은 값 0 = 「ＯＦＦ」 · 1 = 「ＯＮ」(`$96B6 + 7·값`). 마스터 「PCE II 와 같은 방향 — ON 평소 · OFF 치트」(PATH OFF = 벽 통과 · MONSTER OFF = 조우 없음)
  이라 표시만 뒤집는다: 새 쌍 [ＯＮ, ＯＦＦ] 을 같은 간격 7B 로 `PAIR_OFF` 에 두고 두 행의 포인터(`LDA #$B6 / #$96` 둘씩)만 돌린다 — 값 바이트(`$37A6/7`)의 뜻은 그대로(1 = 효과).
  원판 「ＯＦＦ」·「ＯＮ」 문자열은 다른 설정 화면과 같이 쓰이므로 건드리지 않는다.
- Gold: G 행이 한 번에 올리는 양(32비트 리틀엔디언, 뱅크 0x77 `+1FF5`) 1000 → 10000(마스터 「1000씩 올리니까 찔끔찔끔」). EXP(E) 는 +1000 그대로(`debug_warp.E_ADD`).
"""

import common
import hud_half
import list_strip

ROWS = ("PATH", "MON", "GOLD", "EXP", "WARP", "ITEM")  # 마스터 11-25 「MONSTER → MON」
ONOFF = ("ON", "OFF")
LABEL_BANK = 0x6D
LABEL_OFF = 0x1F20 + hud_half.CODE_LEN + list_strip.CODE_LEN  # 뱅크 0x6D 끝 FF 구역에서 `hud_half`·`list_strip` 바로 뒤 — `freespace.BANK6D_TAIL` 이 이 길이만큼 비켜 준다
ROWS_LEN = sum(len("".join(chr(ord(c) + 0xFEE0) for c in t).encode("shift_jis")) for t in ROWS) + len(ROWS)  # 전각 SJIS + 00
ROW_NAMES = False  # 마스터 11-25 「디버그 라벨은 원래대로」(이름 라벨은 OFF 때 창 끝이 깨진다) — 설계만 남김
CODE_LEN = ROWS_LEN if ROW_NAMES else 0  # freespace 가 비켜 줄 길이
# [ON, OFF] 쌍은 새로 안 쓴다 — 라벨 구역에 이미 `ＯＮ`($96BD) 바로 뒤 7B 에 `ＯＦＦ`($96C4)가 있다(다른 설정 화면의 둘째 OFF). 기준 $96BD + 7·값 = [ON, OFF]
LABEL_ADDR = 0x8000 + LABEL_OFF
PAIR_ADDR = 0x96BD
GOLD_ADD = 10000
FLIP_ONOFF = False  # 마스터 11-26 「원판동작으로 되돌려놓자. 기본값도 OFF라 헷갈려」 — P·M 표시 뒤집기를 걷었다(원판: 기본 OFF, ON = 효과 켜짐). 설계만 남김
GOLD_BANK, GOLD_OFF = 0x77, 0x1FF5
GOLD_OLD = (1000).to_bytes(4, "little")
# 뱅크 0x6E 코드 — 포인터를 싣는 immediate 바이트(`LDA #lo / STA $10 / LDA #hi / STA $11` 의 즉치 자리)
PTR_LABEL = 0x056F  # `A9 E3 85 10 A9 BF 85 11` — 행 이름 줄 문자열
PTR_P = 0x0588  # `A9 B6 85 FE A9 96 85 FF`(P 행 값 문자열 쌍)
PTR_M = 0x0598  # (M 행)
PTR_BAT_LO = 0x0578  # `A9 88 85 12`(행 이름 BAT 시작 `$0188`) 의 즉치 — 한 칸 왼쪽으로(마스터 11-25 「좌측 공백도 제거」)
# 뒤쪽 값 칸 간격(`ADC #$05`, `$6607`) — 이름이 길어져 값을 오른쪽으로 민다. 0x0607+1 이 즉치
VALUE_GAP_OFF = 0x0608
VALUE_GAP_OLD = 0x05
ROW_ADV_OFF = 0x061D  # `69 7B`(`$661C`) 의 즉치 — 값 그린 뒤 BAT 되돌림(+0x7B). 합계 0x05 + 0x7B = 0x80
ROW_ADV_OLD = 0x7B
VALUE_GAP = 0x05  # 원판 값


def _pad(t: str) -> bytes:
    b = _sj(t)
    while len(b) < 2 * ROW_CELLS:
        b += b"\x81\x40"  # 전각 공백
    return b


def _sj(t: str) -> bytes:
    """영문 → 원판과 같은 전각 SJIS(`ＰＡＴＨ` — 글리프 표 밖, 시스템 카드 BIOS 글꼴). 우리 글리프 표엔 대문자 일부가 없다."""
    return "".join(chr(ord(c) + 0xFEE0) for c in t).encode("shift_jis")


ROW_CELLS = 4  # 행마다 전각 4자(8B)로 패딩 — 렌더러가 다음 행 시작을 앞 줄 길이만큼 옮겨, 길이가 다르면 줄이 계단처럼 어긋난다(11-25 실측)


def blocks(table=None):
    rows = b"".join(_sj(t) + b"\x00" for t in ROWS)  # 원판과 같은 꼴(이름마다 00)
    return rows, b""


def patches(table):
    rows, _ = blocks(table)
    assert len(rows) == ROWS_LEN, (len(rows), ROWS_LEN)
    out = []

    def put(label, bank, off, old, new):
        pos = 0
        while pos < len(new):
            at = off + pos
            rel = 34 + (bank - 0x68) * 4 + at // common.USER
            o = at % common.USER
            n = min(len(new) - pos, common.USER - o)
            out.append((label, rel, o, old[pos : pos + n], new[pos : pos + n]))
            pos += n

    if ROW_NAMES:
        put("debug label rows", LABEL_BANK, LABEL_OFF, b"\xff" * len(rows), rows)
    if ROW_NAMES:
        put("debug label row ptr", 0x6E, PTR_LABEL, bytes([0xA9, 0xE3, 0x85, 0x10, 0xA9, 0xBF]), bytes([0xA9, LABEL_ADDR & 0xFF, 0x85, 0x10, 0xA9, LABEL_ADDR >> 8]))
    if ROW_NAMES:
        put("debug label start col", 0x6E, PTR_BAT_LO, bytes([0x88]), bytes([0x87]))
    for nm, off in (("P", PTR_P), ("M", PTR_M)) if FLIP_ONOFF else ():
        put(f"debug {nm} value ptr", 0x6E, off, bytes([0xA9, 0xB6, 0x85, 0xFE, 0xA9, 0x96]), bytes([0xA9, PAIR_ADDR & 0xFF, 0x85, 0xFE, 0xA9, PAIR_ADDR >> 8]))
    put("debug gold add", GOLD_BANK, GOLD_OFF, GOLD_OLD, GOLD_ADD.to_bytes(4, "little"))
    if VALUE_GAP != VALUE_GAP_OLD:
        # 🔴 값 칸 간격(`ADC #$05`)만 늘리면 행마다 BAT 가 그만큼 더 내려가 줄이 계단이 된다(11-25 실측) — 같은 함수 끝의 `ADC #$7B` 로 합계(0x80)를 지킨다
        put("debug value gap", 0x6E, VALUE_GAP_OFF, bytes([VALUE_GAP_OLD]), bytes([VALUE_GAP]))
        put("debug row advance", 0x6E, ROW_ADV_OFF, bytes([ROW_ADV_OLD]), bytes([ROW_ADV_OLD - (VALUE_GAP - VALUE_GAP_OLD)]))
    return out


if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")
    print(blocks({}) if False else "needs table")
