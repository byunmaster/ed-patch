"""md-ed1 글꼴 — 롬 안 폰트 리소스 6개(색인 0x1A54D2). 14×14 1bpp, 글리프당 **채움 + 테두리** 두 면.

    python3 tools/font.py --check      # 리소스별 표 크기·글리프 수·자리
    python3 tools/font.py --png <out>  # 리소스 0(SJIS 전각 1,459자)을 한 장으로

리소스 헤더(12B, 자기 기준 오프셋): [표 시작][표 끝][글리프 서술자]. 서술자 4B = [플래그][폭][높이]
[글리프 바이트] 이고 글리프 데이터는 그 바로 뒤. 플래그 비트0 = 면이 둘(스트라이드 ×2).
게임의 조회(`$9BA0`): 표에서 코드를 찾아(표 항목 2B, 0x40B 보폭 조탐색 후 역방향 32항목 정탐색)
색인 × 스트라이드 + 글리프 시작 = 글리프 주소(`$9C36~$9C86`).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FONT_INDEX = 0x1A54D2
FONT_COUNT = 6
FONT_DATA_END = 0x1BC68E  # 마지막(빈) 리소스의 자리 = 글리프 데이터 끝


def resources(d: bytes) -> list[dict]:
    out = []
    for i in range(FONT_COUNT):
        h = FONT_INDEX + 12 * i
        t, e, g = struct.unpack(">III", d[h : h + 12])
        tbl, tbl_end, desc = h + t, h + e + 4, h + g + 8
        flags, w, hgt, nbytes = d[desc : desc + 4]
        stride = nbytes * (2 if flags & 1 else 1)
        wide = i == 0  # 리소스 0 만 SJIS 2B 표, 나머지는 00 xx 1B 코드
        n = (tbl_end - tbl) // 2
        out.append(
            {
                "idx": i,
                "hdr": h,
                "table": tbl,
                "table_end": tbl_end,
                "entries": n,
                "desc": desc,
                "glyphs": desc + 4,
                "w": w,
                "h": hgt,
                "nbytes": nbytes,
                "stride": stride,
                "wide": wide,
            }
        )
    return out


def codes(d: bytes, r: dict) -> list[int]:
    return [struct.unpack(">H", d[p : p + 2])[0] for p in range(r["table"], r["table_end"], 2)]


def glyph(d: bytes, r: dict, i: int, plane: int = 0) -> list[list[int]]:
    """plane 0 = 채움, 1 = 테두리. 행마다 2B, MSB 가 왼쪽."""
    base = r["glyphs"] + i * r["stride"] + plane * r["nbytes"]
    rows = []
    for y in range(r["h"]):
        v = struct.unpack(">H", d[base + 2 * y : base + 2 * y + 2])[0]
        rows.append([(v >> (15 - x)) & 1 for x in range(r["w"])])
    return rows


def check(d: bytes) -> None:
    rs = resources(d)
    for r in rs:
        if r["idx"] == FONT_COUNT - 1:
            print(f"  #{r['idx']} (빈 리소스) 글리프 자리 {r['glyphs'] - 4:#x}")
            continue
        cs = codes(d, r)
        print(
            f"  #{r['idx']} 표 {r['table']:#x}~{r['table_end']:#x} {r['entries']:4d}자 "
            f"{'SJIS' if r['wide'] else '1B  '} · {r['w']}×{r['h']} {r['nbytes']}B×{2 if r['stride'] > r['nbytes'] else 1}면 "
            f"· 글리프 {r['glyphs']:#x}~{r['glyphs'] + r['entries'] * r['stride']:#x} · 첫 {cs[0]:04x} 끝 {cs[-1]:04x}"
        )
    r0 = rs[0]
    if r0["entries"] != 1459 or r0["w"] != 14 or r0["stride"] != 56:
        raise SystemExit("글꼴 리소스 0 의 형상이 갈렸다")
    if rs[-1]["glyphs"] - 4 != FONT_DATA_END:
        raise SystemExit("글리프 데이터 끝이 갈렸다")


def png(d: bytes, out: Path, plane: int = 0, per_row: int = 48) -> None:
    from PIL import Image

    r = resources(d)[0]
    n = r["entries"]
    rows = (n + per_row - 1) // per_row
    im = Image.new("1", (per_row * (r["w"] + 1), rows * (r["h"] + 1)), 1)
    px = im.load()
    for i in range(n):
        gx, gy = (i % per_row) * (r["w"] + 1), (i // per_row) * (r["h"] + 1)
        for y, row in enumerate(glyph(d, r, i, plane)):
            for x, v in enumerate(row):
                if v:
                    px[gx + x, gy + y] = 0
    im.save(out)
    print(f"  {out} ({n} 글리프, 면 {plane})")


if __name__ == "__main__":
    d = common.rom()
    if "--png" in sys.argv:
        png(
            d,
            Path(sys.argv[sys.argv.index("--png") + 1]),
            plane=1 if "--outline" in sys.argv else 0,
        )
    else:
        check(d)
