"""**입장 배너·HUD 지명 가운데 — 전 지명의 좌·우 잉크 여백(px) 표** (번역 규칙 2-8, 마스터 11-08).

    python3 tools/center_all.py --out <폴더>     # tsv + 종류별 시트(PNG)

엔진(`0x0607968C`)은 지명 바이트 길이 n 으로 좌우 반각(6px) 패딩 (16−n)//2 칸씩을 만든다. 여기서는 그 산수에 **빌드 이미지의 글리프**(11KANJI/11ASCII)로
첫·끝 글자의 잉크 여백을 더해 좌·우 여백을 잰다(계산 렌더 — 실화면과 같은 산수라는 건 banner-1104 실측으로 맞췄다).
규칙: 딱 가운데가 안 되면 **왼쪽 여백 ≤ 오른쪽 여백**(남는 여백은 오른쪽), 차 ≤ 한 단위(6px).
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_place_fields as P
import common
import font
from check_name_tables import _decode, _inv_map

CELLS, HALF = 16, 6


def glyphs():
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    try:
        files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
        return common.read_extent(mm, *files["/11KANJI.FON"]), common.read_extent(
            mm, *files["/11ASCII.FON"]
        )
    finally:
        mm.close()
        f.close()


def ink_cols(rows16, width):
    """글리프 행들(정수, 폭 width 비트) → (왼쪽 빈 열, 오른쪽 빈 열) — 글자 칸 안에서."""
    cols = [c for c in range(width) if any(r >> (width - 1 - c) & 1 for r in rows16)]
    if not cols:
        return width, width
    return cols[0], width - 1 - cols[-1]


def parts(raw, kanji, ascii_):
    """이름 바이트 → [(칸 폭 px, 왼쪽 빈 px, 오른쪽 빈 px, 글자)]."""
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            idx = font.game_index(raw[i : i + 2])
            g = kanji[idx * 22 : (idx + 1) * 22]
            rows = [int.from_bytes(g[r * 2 : r * 2 + 2], "big") >> 4 for r in range(11)]
            l, r = ink_cols(rows, 12)
            out.append((12, l, r, raw[i : i + 2]))
            i += 2
        else:
            g = ascii_[b * 11 : b * 11 + 11]
            l, r = ink_cols(list(g), 8)
            out.append((6, min(l, 6), max(0, r - 2), raw[i : i + 1]))
            i += 1
    return out


def margins(raw, kanji, ascii_):
    """→ (좌 px, 우 px, 바이트 길이). 넘치면 None."""
    n = len(raw)
    if n > CELLS:
        return None
    ps = parts(raw, kanji, ascii_)
    if not ps:
        return None
    padl = (CELLS - n) // 2
    padr = CELLS - n - padl
    # 앞뒤 빈 칸(공백 글자)은 잉크가 없으니 다음 잉크 글자까지 센다
    ink = [k for k, p in enumerate(ps) if p[1] < p[0]]
    if not ink:
        return None
    a, z = ink[0], ink[-1]
    left = padl * HALF + sum(p[0] for p in ps[:a]) + ps[a][1]
    right = padr * HALF + sum(p[0] for p in ps[z + 1 :]) + ps[z][2]
    return left, right, n


def render(raw, kanji, ascii_, label):
    """16칸(96px) 틀에 엔진 산수로 놓은 이름 한 줄 → PIL 그림(x3). 좌·우 여백 수치를 글자로 붙인다."""
    from PIL import Image, ImageDraw

    n = len(raw)
    W, H = CELLS * HALF, 13
    im = Image.new("RGB", (W, H), (0, 0, 120))
    px = im.load()
    x = (CELLS - n) // 2 * HALF
    for w, _l, _r, b in parts(raw, kanji, ascii_):
        if w == 12:
            idx = font.game_index(b)
            g = kanji[idx * 22 : (idx + 1) * 22]
            for r in range(11):
                v = int.from_bytes(g[r * 2 : r * 2 + 2], "big") >> 4
                for c in range(12):
                    if v >> (11 - c) & 1 and 0 <= x + c < W:
                        px[x + c, r + 1] = (255, 255, 255)
        else:
            g = ascii_[b[0] * 11 : b[0] * 11 + 11]
            for r in range(11):
                for c in range(8):
                    if g[r] >> (7 - c) & 1 and 0 <= x + c < W:
                        px[x + c, r + 1] = (255, 255, 255)
        x += w
    im = im.resize((W * 3, H * 3), Image.NEAREST)
    out = Image.new("RGB", (W * 3 + 230, H * 3), (30, 30, 30))
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((W * 3 + 6, 8), label, fill=(255, 255, 160))
    return out


def sheet(items, path, cols=2):
    from PIL import Image

    if not items:
        return
    w, h = items[0].size
    rows = -(-len(items) // cols)
    sh = Image.new("RGB", (cols * (w + 6), rows * (h + 4)), (10, 10, 10))
    for k, it in enumerate(items):
        sh.paste(it, (k % cols * (w + 6), k // cols * (h + 4)))
    sh.save(path)


def collect():
    kanji, ascii_ = glyphs()
    inv = _inv_map()
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))[0]
    f, mm = common.open_image(img)
    rows = P.targets()
    out, cache = [], {}
    try:
        files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}
        for path, at, room, kr, where in rows:  # noqa: B007
            if path not in cache:
                cache[path] = common.read_extent(mm, *files[path])
            d = cache[path]
            z = d.find(b"\x00", at, at + room)
            raw = d[at : z if z >= 0 else at + room]
            kind = (
                "입장배너·HUD(씬 헤더)"
                if "헤더" in where
                else "HUD 표(" + where.split("/")[1].split("[")[0] + ")"
            )
            m = margins(raw, kanji, ascii_)
            out.append((kind, where, _decode(raw, inv), raw, m))
    finally:
        mm.close()
        f.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = collect()
    worst = [r for r in rows if r[4] and r[4][0] > r[4][1]]
    with open(os.path.join(a.out, "center-all.tsv"), "w", encoding="utf-8") as f:
        f.write("종류\t자리\t이름\t바이트\t좌px\t우px\t차(우-좌)\t판정\n")
        for kind, where, name, raw, m in rows:
            if m is None:
                f.write(f"{kind}\t{where}\t{name}\t{len(raw)}\t-\t-\t-\t잴 수 없음\n")
                continue
            l, r, n = m
            f.write(
                f"{kind}\t{where}\t{name}\t{n}\t{l}\t{r}\t{r - l}\t{'왼쪽 큼' if l > r else 'ok'}\n"
            )
    kanji, ascii_ = glyphs()
    by, seen = {}, set()
    for kind, _where, _name, raw, m in rows:
        if m and (kind, raw) not in seen:  # 같은 바이트는 한 칸만 — 전체 목록은 tsv
            seen.add((kind, raw))
            by.setdefault(kind, []).append(
                render(
                    raw,
                    kanji,
                    ascii_,
                    f"#{len(by.get(kind, []))} {len(raw)}B L{m[0]} R{m[1]} d{m[1] - m[0]}",
                )
            )
    for kind, items in by.items():
        for k in range(0, len(items), 120):
            sheet(
                items[k : k + 120],
                os.path.join(
                    a.out,
                    f"{kind.split('(')[0]}-{kind.split('(')[-1].strip(')')}-{k // 120 + 1}.png".replace(
                        "/", "_"
                    ),
                ),
            )
    print(f"지명 {len(rows)} · 왼쪽이 더 큰 줄 {len(worst)}")
    for kind, where, name, _raw, m in worst[:40]:
        print(kind, where, repr(name), m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
