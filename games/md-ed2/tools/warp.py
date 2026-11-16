"""디버그 이동 — RAM 만으로 월드맵 문 이벤트 표를 바꿔치기해 24개 마을 어디든 들어가고, 마을 안에서는 순간이동한다(제품 롬 그대로, 헤드리스).

    python3 tools/warp.py STATE.st --town 7110 [--out OUT.st] [--shot OUT.png]     # 월드맵 「루디아 문」 앞 상태에서 그 마을로
    python3 tools/warp.py STATE.st --tp 0x35,0x1d [--shot OUT.png]                  # 같은 맵 안 순간이동(마을·던전 안)

원리(devlog 「⑥ 디버그 이동 3차」):
  · 월드맵(맵 3000)의 씬 모듈은 블록 37 모듈 1. 헤더 뒤 12B 항목 `[0x2200 따위][좌표 워드 둘][문 레코드 오프셋][명령 id 0x2000+n][이름 오프셋]` 이
    마을 입구마다 있고, 문 레코드(35B, +0xC 워드 = 목적 맵 id)가 모듈 안 0x14ec~0x1d08 에 24개 있다.
  · 모듈은 RAM `$FF6650` 에 올라와 있으므로 「루디아 문」 항목(모듈 0x2a)의 레코드 오프셋 워드를 다른 마을 레코드로 바꾸고 문을 걸어 지나면 그 마을이 열린다.
  · 같은 맵 안 순간이동: 타일 `$FF1CBE/BF`(x,y)와 그 두 배 `$FF34BA/BB`(2x, 2y+1)를 함께 쓴다(월드맵은 스크롤이 어긋나 입구가 안 걸린다 — 마을 안에서만).
상태 파일은 `headless.Core.save_state()` 것이다(메가드라이브 코어). 제품 롬·세이브는 건드리지 않는다.
"""

import argparse
import ctypes as C
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import dialog
import headless

BASE = 0xFF6650  # 씬 모듈이 올라오는 RAM
WORLD_MOD = (37, 1)  # 맵 3000
RUDIA_ENTRY_REC = 0x15AA  # 「루디아 문」 항목이 가리키는 레코드(맵 7010)
MAP_ID = 0xFF1AC5
TOWN_RECORDS = {  # 목적 맵 id → 월드 모듈 안 문 레코드 오프셋
    0x7000: 0x14EC,
    0x7001: 0x150E,
    0x7010: 0x15AA,
    0x7020: 0x161E,
    0x7030: 0x165C,
    0x7040: 0x16EC,
    0x7100: 0x17A5,
    0x7110: 0x1818,
    0x7120: 0x1856,
    0x7130: 0x188A,
    0x7140: 0x1902,
    0x7200: 0x1940,
    0x7210: 0x19BA,
    0x7220: 0x19EE,
    0x7240: 0x1ADC,
    0x7250: 0x1B1A,
    0x7260: 0x1B8C,
    0x7300: 0x1BCA,
    0x7310: 0x1BEC,
    0x7320: 0x1C0E,
    0x7400: 0x1C52,
    0x7410: 0x1C9C,
    0x7420: 0x1CE6,
    0x7430: 0x1D08,
}


def load(rom: str, sav: str, state: str) -> headless.Core:
    """롬 + 세이브(SRAM) 위에 상태를 올린다."""
    c = headless.Core(rom)
    d = Path(sav).read_bytes()
    C.memmove(c.lib.retro_get_memory_data(0), d, len(d))
    c.run(10)
    c.load_state(Path(state).read_bytes())
    c.run(2)
    return c


def map_id(c: headless.Core) -> int:
    return int.from_bytes(c.ram(MAP_ID, 2), "big")


def entry_word_offset(rec: int = RUDIA_ENTRY_REC) -> int:
    """월드 모듈 항목 표에서 레코드 오프셋 워드가 `rec` 인 항목의 워드 자리(모듈 안 오프셋)."""
    d = dialog.module(*WORLD_MOD).data
    pat = rec.to_bytes(2, "big")
    for o in range(0x10, 0x200, 2):
        if (
            d[o : o + 2] == pat and 0x20 <= d[o + 2] <= 0x2F and d[o + 3] < 0x40
        ):  # 뒤 워드 = 명령 id 0x20nn
            return o
    raise SystemExit(f"문 항목({rec:#x})을 못 찾았다")


SCRATCH_REC = 0x14EC  # 합성 문 레코드를 덮어쓰는 칸 — 월드 모듈 안 첫 레코드(맵 7000, 쓸 일 없음). 모듈 밖 빈 RAM 은 맵 로드가 지워서 안 된다(실측)


def enter_town(c: headless.Core, dest: int, max_steps: int = 8) -> bool:
    """월드맵 「루디아 문」 앞 상태에서 항목을 `dest` 마을 레코드로 바꾸고 아래로 걸어 들어간다. 성공하면 True.
    표에 없는 맵 id(같은 마을의 이야기 단계판 7011·7013·7014 따위)는 같은 마을 레코드(`dest & 0xFFF0`)를 베껴 +0xC 워드만 바꾼 합성 레코드를 모듈 안 스크래치 칸(`SCRATCH_REC`)에 덮어쓰고 가리킨다."""
    if dest in TOWN_RECORDS:
        off = TOWN_RECORDS[dest]
    else:
        base = TOWN_RECORDS[dest & 0xFFF0]
        rec = bytearray(dialog.module(*WORLD_MOD).data[base : base + 35])
        rec[0xC:0xE] = dest.to_bytes(2, "big")
        c.poke(BASE + SCRATCH_REC, bytes(rec))
        off = SCRATCH_REC
    c.poke(BASE + entry_word_offset(), off.to_bytes(2, "big"))
    for _ in range(max_steps):
        c.press("down", 10, 6)
        c.run(10)
        if map_id(c) != 0x3000:
            c.run(120)
            return map_id(c) == dest
    return False


def teleport(c: headless.Core, x: int, y: int, frames: int = 30) -> None:
    c.poke(0xFF1CBE, bytes([x, y]))
    c.poke(0xFF34BA, bytes([2 * x, 2 * y + 1]))
    c.run(frames)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("state")
    ap.add_argument("--rom", default=str(common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"))
    ap.add_argument("--sav", required=True, help="세이브(.sav) — SRAM 에 올린다")
    ap.add_argument("--town", type=lambda s: int(s, 16), help="들어갈 마을 맵 id(16진, 예 7110)")
    ap.add_argument("--tp", help="순간이동 x,y(타일, 0x 허용)")
    ap.add_argument("--out", help="결과 상태 저장")
    ap.add_argument("--shot", help="결과 화면 PNG")
    a = ap.parse_args()
    c = load(a.rom, a.sav, a.state)
    if a.town:
        ok = enter_town(c, a.town)
        print(f"마을 {a.town:x} → 지금 맵 {map_id(c):x} {'✅' if ok else '✗'}")
    if a.tp:
        x, y = (int(v, 0) for v in a.tp.split(","))
        teleport(c, x, y)
        print(f"순간이동 ({x},{y}) 맵 {map_id(c):x}")
    if a.shot:
        c.shot(a.shot)
    if a.out:
        Path(a.out).write_bytes(c.save_state())
    return 0


if __name__ == "__main__":
    sys.exit(main())
