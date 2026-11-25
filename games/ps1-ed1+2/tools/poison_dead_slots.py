#!/usr/bin/env python3
"""**죽은 잔재 독약 시험** — 정적으로 「아무도 안 읽는다」고 본 원판 문자열 칸 넷을 눈에 띄는 한글(「독독」)로 채운 **시험 이미지**를 만든다.

왜. 정적 판정은 틀릴 수 있다(SFC·PCE II: 정적으로 죽었다던 것이 실제로 읽혔다). 읽히는 칸이면 화면에 「독독」이 뜬다 —
제품과 나란히 보아 차이가 없으면 증명, 있으면 결함. 읽는 화면 후보: 058 이벤트(ED2 아이템 지급 연출) · 아이템 메뉴 · 전투 몬스터 이름 · 상점.

  python3 tools/poison_dead_slots.py <원본 시험 이미지.bin>      # test-* 칸의 이미지를 **사본** `test-poison` 칸으로 복사해 칸을 채운다

대상(최종 이미지의 파일 오프셋 — 문서 `status.md` 11-07 점검):
  ED.EXE   0xA8D0  「ニージャ」(몬스터 이름 칸 꼬리, 8B)       ED2.EXE  0xD4880 「光の杖」(8B 고정칸) · 0xD48A0 「氷の杖」 · 0xD48A8 「竜の涙」
⚠ 제품·핫픽스 칸은 안 건드린다 — 사본에만 쓴다.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, extract, write_user_data

EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}
SLOTS = (("ED.EXE", 0xA8D0, 8), ("ED2.EXE", 0xD4880, 8), ("ED2.EXE", 0xD48A0, 8), ("ED2.EXE", 0xD48A8, 8))
POISON = "독독"


def main():
    src = sys.argv[1]
    dst_dir = os.path.join(os.path.dirname(BUILD_DIR.rstrip("/")), "test-poison")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "Eiyuu Densetsu (KR).bin")
    shutil.copyfile(src, dst)
    shutil.copyfile(src[:-4] + ".cue", os.path.join(dst_dir, "Eiyuu Densetsu (KR).cue"))
    kb = H.encode_kr(POISON) + b"\x00"
    bufs = {n: bytearray(extract(lba, size, path=dst)) for n, (lba, size) in EXES.items()}
    for name, off, width in SLOTS:
        buf = bufs[name]
        assert len(kb) <= width
        buf[off : off + width] = kb.ljust(width, b"\x00")
    with open(dst, "r+b") as f:
        for name, (lba, _size) in EXES.items():
            write_user_data(f, lba, bytes(bufs[name]), label=f"독약 시험 {name}")
    for name, off, width in SLOTS:
        lba, size = EXES[name]
        got = bytes(extract(lba, size, path=dst))[off : off + width]
        assert got.startswith(kb), (name, hex(off), got.hex())
    print(f"독약 시험 이미지: {dst} — 네 칸을 「{POISON}」으로 채움")


if __name__ == "__main__":
    main()
