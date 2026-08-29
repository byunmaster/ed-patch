"""
no$psx 비압축 스냅샷(.SNA)에서 MRAM/VRAM을 추출하고 VRAM을 PNG로 렌더한다.
청크 구조: 0x40부터 [ID(4) + ver(4) + size(4) + data] 반복, STOP에서 끝.
VRAM은 1024x512 BGR555.
"""

import os
import sys

import numpy as np
from common import OUT_DIR, ROOT
from PIL import Image

# 기본값: 리포 내 no$psx 스테이트 폴더의 font.SNA (vendor/는 gitignore 대상)
DEFAULT_SNA = os.path.join(ROOT, "..", "..", "vendor", "nopsx", "SLOT", "font.SNA")
SNA = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SNA


def parse(path):
    data = open(path, "rb").read()
    assert data[:15] == b"NO$PSX SNAPSHOT", "시그니처 불일치"
    chunks = {}
    pos = 0x40
    while pos + 12 <= len(data):
        cid = data[pos : pos + 4].decode("ascii", "replace")
        size = int.from_bytes(data[pos + 8 : pos + 12], "little")
        if cid == "STOP":
            break
        chunks[cid] = data[pos + 12 : pos + 12 + size]
        pos += 12 + size
    return chunks


def main():
    chunks = parse(SNA)
    print({k: hex(len(v)) for k, v in chunks.items()})

    mram = chunks["MRAM"]
    vram = chunks["VRAM"]
    open(os.path.join(OUT_DIR, "mram.bin"), "wb").write(mram)
    open(os.path.join(OUT_DIR, "vram.bin"), "wb").write(vram)

    # VRAM → PNG (BGR555 → RGB888)
    px = np.frombuffer(vram, dtype=np.uint16).reshape(512, 1024)
    r = ((px & 0x1F) << 3).astype(np.uint8)
    g = (((px >> 5) & 0x1F) << 3).astype(np.uint8)
    b = (((px >> 10) & 0x1F) << 3).astype(np.uint8)
    img = Image.fromarray(np.dstack([r, g, b]))
    out = os.path.join(OUT_DIR, "vram.png")
    img.save(out)
    print(f"저장: mram.bin, vram.bin, {out}")


if __name__ == "__main__":
    main()
