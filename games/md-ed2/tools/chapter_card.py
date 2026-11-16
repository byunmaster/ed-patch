"""장 카드(장 끝 「제N장 …／끝」) 화면 촬영 — 시험 롬 + 헤드리스, 제품 롬은 그대로.

    python3 tools/chapter_card.py --sav SAV --state STATE.st --out DIR      # 1~4장 카드 넷

원리(devlog 「⑥ 장 카드」): 필드 루프 입구 `0x18560`(`cmpi.w #0,$FF1852`)을 `jsr 0x1790E` 로 바꾸고, 0 런 `0x1790E` 에 붙이는 스텁이
RAM 깃발 `$FF1920` 이 켜져 있을 때 한 번만 장 끝 루틴(`ENTRIES`)을 부른다. 루틴 앞쪽 `lea 카드문안,a1` 이 카드 스트림(0x37686·37964·38000·3831A)을 그린다.
시험 롬은 `work/build/test-chapter/` 에만 쓴다(꼬리표 `test-`).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import warp
from PIL import Image

ENTRIES = {
    1: 0x365E8,
    2: 0x367EE,
    3: 0x368FE,
    4: 0x36A50,
}  # 장 번호 → 카드 루틴(첫 명령 lea 카드문안)
STUB_AT = 0x1790E
HOOK_AT = 0x18560
FLAG = 0xFF1920
STUB = "4a3900ff1920 6714 423900ff1920 48e7fffe 4eb9{entry:08x} 4cdf7fff 0c79000000ff1852 4e75"


def make_rom(src: bytes, entry: int) -> bytes:
    b = bytearray(src)
    stub = bytes.fromhex(STUB.format(entry=entry).replace(" ", ""))
    assert bytes(b[STUB_AT : STUB_AT + len(stub)]) == b"\0" * len(stub), "스텁 자리가 0 런이 아니다"
    assert bytes(b[HOOK_AT : HOOK_AT + 8]) == bytes.fromhex("0c79000000ff1852"), "후크 자리 불일치"
    b[STUB_AT : STUB_AT + len(stub)] = stub
    b[HOOK_AT : HOOK_AT + 8] = bytes.fromhex("4eb9") + STUB_AT.to_bytes(4, "big") + b"\x4e\x71"
    return bytes(b)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--sav", required=True)
    ap.add_argument("--state", required=True, help="필드 상태(.st) — 마을 어디든")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=360)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    src = (common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin").read_bytes()
    tdir = common.BUILD_DIR / "test-chapter"
    tdir.mkdir(parents=True, exist_ok=True)
    for ch, entry in ENTRIES.items():
        rom = tdir / "ed2-kr.bin"
        rom.write_bytes(make_rom(src, entry))
        c = warp.load(str(rom), a.sav, a.state)
        c.poke(FLAG, b"\x01")
        c.run(a.frames)
        p = out / f"chapter{ch}.png"
        c.shot(str(p))
        print(f"{ch}장 → {p}", Image.open(p).size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
