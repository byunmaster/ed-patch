#!/usr/bin/env python3
"""번호표에 없는 씬 본문(표 목표)의 **새 롬 안 SNES 주소** — 대사 보기 하네스가 표 항목을 덮어써 부를 때 쓴다.

    python3 games/sfc-ed1/tools/msg_addr.py 0BB66B          # 번역 정본 주소(SNES `$bb:aaaa` 24비트 hex) → 새 롬 SNES 주소
    MV_ADDR=<위 값> python3 games/sfc-ed1/tools/headless.py --lua msg_viewer MV_IDS=0x0001 …

`work/derived/place_map[_dbg].json`(빌드가 쓴다 — 원문 파일 오프셋 → 새 롬 파일 오프셋)을 읽는다. 빌드 뒤에만 맞는다(낡은 롬은 가드가 막는다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def off2snes(off: int) -> int:
    return ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)


def kr_snes_addr(seg_addr: int, debug: bool = True) -> int:
    pm = json.loads((common.OUT_DIR / f"place_map{'_dbg' if debug else ''}.json").read_text(encoding="utf-8"))
    return off2snes(int(pm[f"{common.snes2off(seg_addr):06X}"], 16))


if __name__ == "__main__":
    print(f"{kr_snes_addr(int(sys.argv[1], 16)):06X}")
