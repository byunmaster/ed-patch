"""화면 그래픽 — `.PAK` 안의 **셀맵 + 타일 + 팔레트**를 그림으로 되돌린다.

    python3 games/ss-ed3/tools/gfx.py                  # 전 PAK → work/review/gfx/*.png
    python3 games/ss-ed3/tools/gfx.py --list           # 항목 구성만 본다
    python3 games/ss-ed3/tools/gfx.py --check a.png    # 우리 그림이 들어가나 (되넣기 전)
    python3 games/ss-ed3/tools/gfx.py --fit a.png      # 안 들어가면 형식에 맞춰 준다

🔴 **통이미지가 아니다.** 새턴 VDP2 의 셀 방식이라 세 조각으로 나뉘어 있다:

    셀맵   4,800B = 40×30 셀 × 4바이트(2word PND) — 각 셀의 **문자 번호**
    타일   8bpp 8×8 = 64바이트/셀, `charno × 32` 가 오프셋(4bpp 기준 단위라 ×32 다)
    팔레트 512B = 256색 × 2바이트, 새턴 15bit `0BBBBBGGGGGRRRRR`

⚠ **순서가 (맵 → 타일 → 팔레트)** 다. 팔레트가 뒤에 온다 — 앞에 있는 512B 를 그 세트의
   팔레트로 잘못 쓰면 색이 통째로 어긋난다(처음에 그렇게 헤맸다).

🔬 **어떻게 알았나 — 실기에서 역추적했다.** 파일만 보고 맞히려다 세 번 어긋났고,
   에뮬로 타이틀을 띄운 뒤 `debug.resolve_tile(nbg=2, x=160, y=60)` 로 그 좌표의
   `char_data_addr` 을 얻어 **VDP2 VRAM 을 디스크에서 검색**하니 한 번에 나왔다
   (`LDDATA.PAK` +42,884 = 항목 7 의 +19,456 — VRAM 주소와 정확히 일치). 셀맵·팔레트도
   같은 수법으로 확정했다. 🔑 **포맷을 추측하지 말고 화면에서 되짚는다.**

⚠ 산출물은 `work/review/gfx/` 다 — 원저작물이므로 커밋하지 않는다.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CW, CH = 40, 30  # 화면 = 40×30 셀 (320×240)
MAP_SIZE, PAL_SIZE = CW * CH * 4, 512
CHAR_UNIT = 32  # 문자 번호의 단위(4bpp 기준) — 8bpp 셀은 64바이트라 번호가 2씩 뛴다


def items(b):
    """PAK → `[bytes]`. 머리가 `항목 수 + BE32 오프셋 표` 다."""
    n = struct.unpack(">I", b[:4])[0]
    offs = [struct.unpack(">I", b[4 + i * 4 : 8 + i * 4])[0] for i in range(n)] + [len(b)]
    return [b[offs[i] : offs[i + 1]] for i in range(n)]


def palette(raw):
    """새턴 15bit → PIL 팔레트."""
    out = []
    for i in range(0, min(len(raw), PAL_SIZE), 2):
        v = struct.unpack(">H", raw[i : i + 2])[0]
        out += [(v & 0x1F) << 3, ((v >> 5) & 0x1F) << 3, ((v >> 10) & 0x1F) << 3]
    return (out + [0] * 768)[:768]


def render(cmap, tiles, pal):
    from PIL import Image

    img = Image.new("P", (CW * 8, CH * 8))
    img.putpalette(palette(pal))
    for i in range(CW * CH):
        if i * 4 + 4 > len(cmap):
            break
        o = (struct.unpack(">I", cmap[i * 4 : i * 4 + 4])[0] & 0xFFFF) * CHAR_UNIT
        if o + 64 <= len(tiles):
            img.paste(
                Image.frombytes("P", (8, 8), tiles[o : o + 64]), ((i % CW) * 8, (i // CW) * 8)
            )
    return img.convert("RGB")


def sets(segs):
    """`(맵, 타일, 팔레트)` 세트 — 4,800B 맵 뒤의 큰 조각과 그 뒤 512B 팔레트."""
    out = []
    for i, s in enumerate(segs):
        if len(s) != MAP_SIZE or i + 2 >= len(segs):
            continue
        tile, pal = segs[i + 1], segs[i + 2]
        if len(pal) == PAL_SIZE and len(tile) > PAL_SIZE:
            out.append((i, i + 1, i + 2))
    return out


def check(path, tile_budget=1024):
    """우리가 그린 화면이 **이 형식에 들어가나** — 크기 · 색 수 · 고유 타일 수.

    🔴 셋 중 **고유 타일 수는 눈으로 알 수 없다.** 8×8 로 쪼갠 조각이 몇 가지인지가
    자리를 정하는데, 그림이 조금만 「사진 같아지면」(그라데이션 · 노이즈) 폭발한다.
    원본 타이틀은 222 개였고 칸은 1,024 개분이다.
    """
    from PIL import Image

    im = Image.open(path).convert("RGB")
    ok = True
    if im.size != (CW * 8, CH * 8):
        print(f"  ❌ 크기 {im.size} — {CW * 8}×{CH * 8} 이어야 한다")
        ok = False
        im = im.resize((CW * 8, CH * 8))
    colors = {im.getpixel((x, y)) for y in range(im.height) for x in range(im.width)}
    print(f"  {'✅' if len(colors) <= 256 else '❌'} 색 {len(colors)} 가지 (256 이하)")
    ok &= len(colors) <= 256
    seen = set()
    for cy in range(CH):
        for cx in range(CW):
            seen.add(im.crop((cx * 8, cy * 8, cx * 8 + 8, cy * 8 + 8)).tobytes())
    print(
        f"  {'✅' if len(seen) <= tile_budget else '❌'} 고유 8×8 타일 {len(seen)} 개 (칸 {tile_budget})"
    )
    ok &= len(seen) <= tile_budget
    print("  →", "들어간다" if ok else "아직 안 들어간다")
    return ok


def fit(path, out, bg=(248, 248, 248), snap=2, colors=256):
    """그린 그림을 이 형식에 **맞춰 준다** — 배경 평탄화 → 256색 양자화.

    🔴 **막는 것은 색이 아니라 배경 노이즈다**(실측 2026-08-27). 편집 도구를 거치면 흰
    배경이 `(249,249,249)`·`(248,249,249)` 처럼 1~2 씩 흔들리는데, 눈에는 안 보여도
    **8×8 조각이 전부 달라져** 고유 타일이 폭발한다 — 받은 그림이 1,192 개(칸은 1,024)였고
    **색을 32 까지 줄여도 그대로**였다. 배경을 한 색으로 스냅하니 **250 개**가 됐다.

    ⚠ 양자화는 **디더링 없이** 한다 — 디더는 픽셀을 흩뿌려 타일을 다시 늘린다.
    """
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if im.size != (CW * 8, CH * 8):
        im = im.resize((CW * 8, CH * 8), Image.LANCZOS)
    p = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = p[x, y]
            if abs(r - bg[0]) <= snap and abs(g - bg[1]) <= snap and abs(b - bg[2]) <= snap:
                p[x, y] = bg
    im.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE).save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="이 PNG 가 형식에 들어가나 본다")
    ap.add_argument("--fit", help="안 들어가는 PNG 를 형식에 맞춰 준다")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--disc", type=int, default=1)
    a = ap.parse_args()

    if a.fit:
        out = os.path.join(C.REVIEW_DIR, "gfx", os.path.basename(a.fit).replace(".png", "_fit.png"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        fit(a.fit, out)
        print(f"── {out}")
        raise SystemExit(0 if check(out) else 1)

    if a.check:
        print(f"── {a.check}")
        raise SystemExit(0 if check(a.check) else 1)

    outdir = os.path.join(C.REVIEW_DIR, "gfx")
    os.makedirs(outdir, exist_ok=True)
    with C.open_disc(a.disc) as d:
        paks = {n: d.read_extent(l, s) for n, l, s in sorted(d.files()) if n.endswith(".PAK")}

    for name, b in paks.items():
        segs = items(b)
        stem = os.path.basename(name)[:-4]
        if a.list:
            print(f"── {name}  항목 {len(segs)}")
            for i, s in enumerate(segs):
                tag = {MAP_SIZE: "셀맵", PAL_SIZE: "팔레트"}.get(len(s), "")
                print(f"   {i:>2}  {len(s):>8,}B  {tag}")
            continue
        got = sets(segs)
        print(f"── {name}  세트 {len(got)}")
        for m, t, p in got:
            out = os.path.join(outdir, f"{stem}_{m}.png")
            render(segs[m], segs[t], segs[p]).save(out)
            print(f"   맵{m} 타일{t}({len(segs[t]):,}B) 팔{p} → {os.path.basename(out)}")


if __name__ == "__main__":
    main()
