"""SRAM 세이브(2KB) — 슬롯 레코드 파싱 · 체크섬 · **씬 점프 세이브 굽기**(엔딩 확인용).

구조(2026-09-25 실측 — `$00:9F80~$00:A19C` 디스어셈블 + 인게임 대조):
- `$70:0000~0013` 고정 시그니처 `00 01 … 13`(배터리 초기화 검사).
- `$70:0014~0016` 슬롯 사용 비트(bit i = 슬롯 i), 3중 다수결.
- `$70:0017+i` · `001A+i` · `001D+i` 슬롯 i 체크섬(3중 다수결) = (레코드 XOR + `$2E`) & $FF
  (`$1B04`=레코드 길이 하위 바이트를 더한다 — `$00:A15C`).
- 슬롯 i 레코드 = `$0020 + i*$32E`, 길이 `$32E`. 로드하면 WRAM `$7E:1154` 로 통째로 복사된다.

레코드 안(오프셋은 레코드 기준 = WRAM `$1154` 기준):
- `+0DD` 현재 맵 ID(`$1231`). 스폰 좌표는 맵이 정한다 — 이것만 바꿔도 그 맵에 선다.
- `+270` 캐릭터 4칸 × `$27`. 칸 안: `+08` 레벨 · `+09/0B/0D/0F` HP·HP최대·MP·MP최대(2B LE) ·
  `+15` 공격력 · `+17` 힘 · `+19` 방어력 · `+1A~1C` 지혜·민첩·행운 ·
  `+1D~20` 무기·갑옷·방패·장신구(`$D2` 아이템 사전 인덱스).
- 칸 `+00` 상태 · `+07` 파티 자리($FF = 미합류).
- `+103` 맵 인물 1번의 적 그룹(`$1257`) · `+30D~` 파티 순서(칸 번호) · `+312` 파티 인원수 ·
  `+313` 이벤트 모듈 번호(`$1467` — 맵 이벤트 코드는 맵ID 가 아니라 이걸로 고른다).

⚠ 1바이트 능력치(+19~1C)는 127 이하(pce 교훈 — 255 는 부호 계산에서 음수가 된다).
  공격력 `+15`·방어력 `+17` 은 **2바이트**(상한 9999 — `$02:CBEB`)라 그 함정이 없다.

    python3 tools/savefile.py dump <srm>
    python3 tools/savefile.py set <srm> --out <srm2> [--slot 2] [--src-slot 1] [--map 0x7D] [--stage 15] [--boost]
    python3 tools/savefile.py set <srm> --out <srm2> --src-slot 1 --ending   # 아그니쟈 직전
"""

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common

SIG_LEN = 0x14
USED = 0x14  # 3바이트 다수결
SUM = 0x17  # 슬롯 i → SUM+i, SUM+3+i, SUM+6+i
REC_BASE = 0x20
REC_LEN = 0x32E
MAP = 0x0DD
CHAR_BASE = 0x270
CHAR_LEN = 0x27
N_CHAR = 4
ORDER = 0x30D
COUNT = 0x312
STAGE = 0x313  # 이벤트 모듈 번호($1467) — 맵 이벤트 코드는 맵ID 가 아니라 이걸로 고른다(`$00:93D9` ×3 → `$00:8461` 표)
NAME_TABLE = 0x02A8B1  # 맵 ID → 지명 포인터(뱅크 $02) — 로드 메뉴가 쓰는 표(`$02:A6DB`)

# $1257 = 맵 인물 1번의 적 그룹 — 맵 진입 훅($19:A25C)이 채우는데 세이브 로드로는 안 돈다
ENTITY1_GROUP = 0x103

# 엔딩 직전 — 바니스성 안쪽 방($88) 진짜 아그니쟈. 이벤트 모듈 15 = `$19:9EA7`, 적 그룹 $67.
ENDING_MAP, ENDING_STAGE, ENDING_GROUP = 0x88, 15, 0x67
# 아그니쟈(방어 ~670, 한 번에 2500 회복)는 드래곤슬레이어가 안 통하고 빛의 검(31)이 통한다 —
# 롬 대사 「빛의 검을 얻었으니 이제 쓰러뜨릴 수 있다」와 같다. 데미지 ≈ 공격력 − 670(실측 1000 → 330).
LIGHT_SWORD = 31
ENDING_ATK = 3000
ENDING_SWORDS = (0, 3)  # 세리오스 · 게일

# pce-ed1 과 같은 장비(아이템 ID 가 기종 간 같다 — `$D2` 사전 대조 확인, devlog 09-25(4))
BEST_GEAR = [(31, 49, 63, 73), (25, 49, 63, 73), (28, 49, 63, 73), (25, 49, 63, 73)]


def rec_off(slot: int) -> int:
    return REC_BASE + slot * REC_LEN


def checksum(rec: bytes) -> int:
    x = 0
    for b in rec:
        x ^= b
    return (x + (REC_LEN & 0xFF)) & 0xFF


def map_name(mid: int, rom: bytes | None = None) -> str:
    rom = rom or common.rom_bytes()
    off = common.snes2off(NAME_TABLE) + mid * 2
    ptr = rom[off] | rom[off + 1] << 8
    s = common.snes2off(0x020000 | ptr)
    return text.decode(rom[s : rom.index(b"\xff", s)], text.resolver(rom)).strip("　")


def seal(sram: bytearray, slot: int) -> None:
    """슬롯 체크섬 3중 기록 + 사용 비트."""
    o = rec_off(slot)
    c = checksum(sram[o : o + REC_LEN])
    for k in range(3):
        sram[SUM + 3 * k + slot] = c
        sram[USED + k] |= 1 << slot


def boost(rec: bytearray, level: int = 50, hp: int = 999, stat: int = 120) -> None:
    for i in range(N_CHAR):
        c = CHAR_BASE + i * CHAR_LEN
        rec[c + 0x00] = 0x01  # 합류 상태 — $FF 면 순서표에 있어도 HUD 가 거기서 끊는다
        rec[c + 0x07] = i  # 파티 자리 — $FF 면 HUD·전투에서 빠진다(+00 만으론 안 된다)
        rec[c + 0x08] = level
        for f in (0x09, 0x0B, 0x0D, 0x0F):
            rec[c + f : c + f + 2] = struct.pack("<H", hp)
        for f in (0x15, 0x17, 0x19, 0x1A, 0x1B, 0x1C):
            rec[c + f] = stat
        rec[c + 0x1D : c + 0x21] = bytes(BEST_GEAR[i])
    rec[ORDER : ORDER + N_CHAR] = bytes(range(N_CHAR))
    rec[COUNT] = N_CHAR


def dump(sram: bytes) -> None:
    rom = common.rom_bytes()
    print(
        "시그니처",
        "OK" if sram[:SIG_LEN] == bytes(range(SIG_LEN)) else "깨짐",
        "· 사용",
        sram[USED : USED + 3].hex(),
    )
    for slot in range(2):
        if not sram[USED] >> slot & 1:
            print(f"슬롯{slot + 1}: 비었음")
            continue
        o = rec_off(slot)
        rec = sram[o : o + REC_LEN]
        stored = [sram[SUM + 3 * k + slot] for k in range(3)]
        print(
            f"슬롯{slot + 1}: 체크섬 {checksum(rec):02X} 저장 {bytes(stored).hex()} · 맵 ${rec[MAP]:02X} {map_name(rec[MAP], rom)}"
            f" · 모듈 {rec[STAGE]} · 인원 {rec[COUNT]} 순서 {rec[ORDER : ORDER + N_CHAR].hex()}"
        )
        for i in range(N_CHAR):
            c = rec[CHAR_BASE + i * CHAR_LEN : CHAR_BASE + (i + 1) * CHAR_LEN]
            hp, mp = struct.unpack_from("<H", c, 9)[0], struct.unpack_from("<H", c, 0x0D)[0]
            atk = struct.unpack_from("<H", c, 0x15)[0]
            print(f"   칸{i}: Lv{c[8]} HP{hp} MP{mp} 공격{atk} 장비{list(c[0x1D:0x21])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("srm")
    s = sub.add_parser("set")
    s.add_argument("srm")
    s.add_argument("--out", required=True)
    s.add_argument("--slot", type=int, default=2, help="1 또는 2")
    s.add_argument("--src-slot", type=int, default=None, help="이 슬롯 레코드를 복사해 온다")
    s.add_argument("--map", type=lambda v: int(v, 0))
    s.add_argument("--stage", type=lambda v: int(v, 0))
    s.add_argument("--boost", action="store_true")
    s.add_argument(
        "--ending",
        action="store_true",
        help="엔딩 직전 프리셋(맵·모듈·적 그룹·빛의 검 둘·공격력 3000, --boost 포함)",
    )
    a = ap.parse_args()
    sram = bytearray(Path(a.srm).read_bytes())
    assert len(sram) == 0x800, len(sram)
    if a.cmd == "dump":
        dump(sram)
        return
    slot = a.slot - 1
    o = rec_off(slot)
    if a.src_slot:
        so = rec_off(a.src_slot - 1)
        sram[o : o + REC_LEN] = sram[so : so + REC_LEN]
    rec = sram[o : o + REC_LEN]
    if a.ending:
        a.map, a.stage, a.boost = ENDING_MAP, ENDING_STAGE, True
        rec[ENTITY1_GROUP] = ENDING_GROUP
    if a.map is not None:
        rec[MAP] = a.map
    if a.stage is not None:
        rec[STAGE] = a.stage
    if a.boost:
        boost(rec)
    if a.ending:
        for i in ENDING_SWORDS:
            c = CHAR_BASE + i * CHAR_LEN
            rec[c + 0x1D] = LIGHT_SWORD
            rec[c + 0x15 : c + 0x17] = struct.pack("<H", ENDING_ATK)
    sram[o : o + REC_LEN] = rec
    seal(sram, slot)
    Path(a.out).write_bytes(sram)
    dump(sram)


if __name__ == "__main__":
    main()
