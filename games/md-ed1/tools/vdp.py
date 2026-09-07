"""화면 재구성 — emucap 덤프(`debug dump_memory`)의 VRAM/CRAM 을 PNG 로 편다.

그래픽 문자를 찾을 때 「화면에 뭐가 떠 있나」와 「그 타일이 롬 어디서 왔나」를 같이 봐야 하는데,
스크린샷은 확대·팔레트 대조가 어렵고 타일 시트는 배치를 잃는다. 이 도구는 네임테이블을 따라
**화면 그대로** 다시 그리고, 원하면 타일이 어느 롬 블록에서 왔는지도 대조한다.

🔴 **mednafen 의 VRAM 덤프는 바이트 스왑이다**(2026-09-05 실측). 스왑을 안 하면 타일이 롬과
하나도 안 맞고(920 중 32) 네임테이블도 안 잡힌다. 스왑하면 429/920 이 타이틀 블록에서 나온다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def load(dump: Path) -> dict:
    """덤프 폴더 → {vram(스왑 완료), cram, vsram, reg}."""
    v = (dump / "vram.bin").read_bytes()
    return {
        "vram": bytes(v[i ^ 1] for i in range(len(v))),  # 🔴 바이트 스왑
        "cram": (dump / "cram.bin").read_bytes(),
        "vsram": (dump / "vsram.bin").read_bytes(),
        "reg": (dump / "vdpreg.bin").read_bytes(),
    }


def palette(cram: bytes) -> list[int]:
    out = []
    for i in range(64):
        c = struct.unpack(">H", cram[i * 2 : i * 2 + 2])[0]
        out += [((c >> 1) & 7) * 36, ((c >> 5) & 7) * 36, ((c >> 9) & 7) * 36]
    return out + [0] * (768 - 192)


def tile_px(vram: bytes, idx: int) -> list[list[int]]:
    t = vram[idx * 32 : idx * 32 + 32]
    return [
        [(t[y * 4 + x // 2] >> 4) if x % 2 == 0 else (t[y * 4 + x // 2] & 0xF) for x in range(8)]
        for y in range(8)
    ]


def plane(dump: dict, base: int, width: int, cols: int = 40, rows: int = 28):
    """네임테이블 → PIL 이미지. base·width 는 VDP 레지스터가 아니라 **실측**으로 준다(레지스터 덤프가
    어댑터마다 다르게 실린다)."""
    from PIL import Image

    vram = dump["vram"]
    img = Image.new("P", (cols * 8, rows * 8))
    img.putpalette(palette(dump["cram"]))
    px = img.load()
    for ty in range(rows):
        for tx in range(cols):
            off = base + (ty * width + tx) * 2
            if off + 2 > len(vram):
                continue
            e = struct.unpack(">H", vram[off : off + 2])[0]
            g = tile_px(vram, e & 0x7FF)
            hf, vf, pal = (e >> 11) & 1, (e >> 12) & 1, (e >> 13) & 3
            for y in range(8):
                for x in range(8):
                    c = g[7 - y if vf else y][7 - x if hf else x]
                    if c:
                        px[tx * 8 + x, ty * 8 + y] = pal * 16 + c
    return img


def guess_plane(dump: dict) -> list[tuple[float, int, int]]:
    """(점수, base, width) — 화면 한 판의 항목이 비어 있지 않은 타일을 얼마나 가리키나."""
    vram = dump["vram"]
    live = [any(vram[i * 32 : (i + 1) * 32]) for i in range(2048)]
    out = []
    for width in (32, 64, 128):
        for base in range(0, 0x10000 - 2 * width * 28, 0x400):
            good = tot = 0
            for ty in range(28):
                for tx in range(40):
                    off = base + (ty * width + tx) * 2
                    if off + 2 > len(vram):
                        break
                    e = struct.unpack(">H", vram[off : off + 2])[0]
                    tot += 1
                    good += live[e & 0x7FF]
            if tot:
                out.append((good / tot, base, width))
    return sorted(out, reverse=True)


def sources(dump: dict, blocks: dict[str, bytes]) -> dict[str, int]:
    """화면에 뜬 타일이 어느 블록에서 왔나 — {이름: 타일 수}. blocks = {이름: 푼 바이트}."""
    vram = dump["vram"]
    idx = {}
    for name, blob in blocks.items():
        for p in range(len(blob) - 31):
            idx.setdefault(blob[p : p + 32], name)
    hit: dict[str, int] = {}
    for i in range(2048):
        t = vram[i * 32 : (i + 1) * 32]
        if not any(t):
            continue
        n = idx.get(t)
        if n:
            hit[n] = hit.get(n, 0) + 1
    return dict(sorted(hit.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    d = load(Path(sys.argv[1]))
    if "--guess" in sys.argv:
        for sc, base, w in guess_plane(d)[:5]:
            print(f"  {sc:.2f}  base {base:#x} width {w}")
    else:
        base = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0xC000
        width = int(sys.argv[4]) if len(sys.argv) > 4 else 128
        plane(d, base, width).resize((640, 448)).save(sys.argv[2])
        print(f"  {sys.argv[2]} — base {base:#x} width {width}")
    _ = common
