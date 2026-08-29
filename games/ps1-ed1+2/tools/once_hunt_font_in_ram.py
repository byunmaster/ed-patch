"""
스냅샷 프레임버퍼의 실제 렌더링된 글자 픽셀을 잘라(흰색 마스크),
MRAM 2MB에서 그 비트맵과 일치하는 바이트열을 다중 패킹으로 검색한다.
찾으면 RAM 주소 → 폰트 블록 렌더 → ISO 파일 역추적의 출발점이 된다.
"""

import os

import numpy as np
from common import OUT_DIR
from PIL import Image

MRAM = os.path.join(OUT_DIR, "mram.bin")
VRAM = os.path.join(OUT_DIR, "vram.bin")


def load_fb_mask():
    """프레임버퍼(0,0)-(320,240)에서 흰색 픽셀 마스크."""
    px = np.frombuffer(open(VRAM, "rb").read(), dtype=np.uint16).reshape(512, 1024)
    fb = px[:240, :320]
    r, g, b = fb & 0x1F, (fb >> 5) & 0x1F, (fb >> 10) & 0x1F
    return ((r >= 30) & (g >= 30) & (b >= 30)).astype(np.uint8)


def text_rows(mask, x0=8, x1=300, y0=10, y1=80):
    sub = mask[y0:y1, x0:x1]
    proj = sub.sum(axis=1)
    rows, start = [], None
    for i, v in enumerate(proj):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            rows.append((y0 + start, y0 + i))
            start = None
    if start is not None:
        rows.append((y0 + start, y0 + y1))
    return rows


def glyph_cells(mask, ry0, ry1, x0=8, x1=310):
    """세로 투영으로 글자 칸 분리 (1px 이상 공백이면 분리)."""
    sub = mask[ry0:ry1, x0:x1]
    proj = sub.sum(axis=0)
    cells, start = [], None
    for i, v in enumerate(proj):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            cells.append((x0 + start, x0 + i))
            start = None
    if start is not None:
        cells.append((x0 + start, x0 + x1))
    return cells


def pack_variants(g):
    """g: (h,w) 0/1 배열 → 후보 바이트 패킹들 [(label, bytes)]"""
    h, w = g.shape
    out = []
    for cell_w, cell_h in ((12, 12), (16, 12), (12, 16), (16, 16), (14, 14)):
        if w > cell_w or h > cell_h:
            continue
        for dx in range(cell_w - w + 1):
            for dy in range(cell_h - h + 1):
                cell = np.zeros((cell_h, cell_w), dtype=np.uint8)
                cell[dy : dy + h, dx : dx + w] = g
                flat = cell.reshape(-1)
                base = f"{cell_w}x{cell_h}+{dx}+{dy}"
                # 연속 비트 패킹 (행 구분 없음), MSB/LSB
                if len(flat) % 8 == 0:
                    out.append((f"{base} cont-msb", np.packbits(flat).tobytes()))
                    out.append((f"{base} cont-lsb", np.packbits(flat, bitorder="little").tobytes()))
                # 행당 2바이트 (cell_w<=16), MSB/LSB
                if cell_w <= 16:
                    padded = np.zeros((cell_h, 16), dtype=np.uint8)
                    padded[:, :cell_w] = cell
                    out.append((f"{base} row2B-msb", np.packbits(padded, axis=1).tobytes()))
                    out.append(
                        (
                            f"{base} row2B-lsb",
                            np.packbits(padded, axis=1, bitorder="little").tobytes(),
                        )
                    )
                # 2bpp (픽셀→2비트), 4bpp (픽셀→니블) 확장
                if cell_w == cell_h == 12 or cell_w == cell_h == 16:
                    two = np.repeat(flat, 2)
                    out.append((f"{base} 2bpp-msb", np.packbits(two).tobytes()))
                    nib = np.zeros(len(flat) // 2, dtype=np.uint8)
                    nib = (flat[0::2] * 0x0F) | (flat[1::2] * 0xF0)  # 리틀 니블 우선
                    out.append((f"{base} 4bpp-lo", nib.astype(np.uint8).tobytes()))
    return out


def main():
    mram = open(MRAM, "rb").read()
    mask = load_fb_mask()
    rows = [(29, 45), (45, 58), (58, 70), (70, 83)]  # 마스크 눈검증으로 고정
    print("텍스트 행:", rows)

    # 디버그: 각 행의 글자 칸과 잘린 글리프 저장
    found_any = []
    for ri, (ry0, ry1) in enumerate(rows[:4]):
        cells = glyph_cells(mask, ry0, ry1)
        print(f"행{ri} y={ry0}..{ry1} 칸 {len(cells)}개: {cells[:8]}")
        for ci, (cx0, cx1) in enumerate(cells[:6]):
            g = mask[ry0:ry1, cx0:cx1]
            # 내용 기준 바운딩박스로 다듬기
            ys, xs = np.nonzero(g)
            if len(ys) == 0:
                continue
            g = g[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
            if g.shape[1] < 6 or g.shape[0] < 8:  # 구두점 등 스킵
                continue
            hits = {}
            for label, pat in pack_variants(g):
                idx = mram.find(pat)
                if idx >= 0 and pat.count(b"\x00") < len(pat):  # 전부 0 방지
                    hits[label] = idx
            if hits:
                print(f"  행{ri}칸{ci} ({g.shape[1]}x{g.shape[0]}) 일치:")
                for label, idx in list(hits.items())[:5]:
                    print(f"    RAM 0x{0x80000000 + idx:08X}  [{label}]")
                found_any.append((ri, ci, hits))
            # 글리프 덤프 저장 (확대)
            im = Image.fromarray((g * 255).astype(np.uint8)).resize(
                (g.shape[1] * 8, g.shape[0] * 8), Image.NEAREST
            )
            im.save(os.path.join(OUT_DIR, f"glyph_r{ri}c{ci}.png"))
    if not found_any:
        print("\n1bpp 직접 일치 없음 — 2bpp/4bpp 저장이거나 렌더 시 변형 가능성")


if __name__ == "__main__":
    main()
