"""장 끝 항해 연출의 **띠 제목**(「…おわり」·「次章…」)을 한글로 다시 그린다 — 띠 글자 시트(`C_nnn.TI3`)의 타일을 갈아 끼운다.

🔴 배경(10-24, 마스터 「장 끝 일본어도 이번 라운드에」). 띠 글자는 8bpp 시트(256폭)의 **16×16 타일**로 나뉘어 화면에 놓인다(ANM 의 타일 표).
화면에 어디 놓이나(타일 → 화면 오프셋 `dx,dy`)는 ANM 을 읽는 대신 **원판을 돌려 찍은 화면에서 타일을 찾아(`chapter_end_layout.json`)** 얻었다
(`tools/chapter_end_capture.py` + 템플릿 매칭 — 색이 시트 팔레트 그대로 나오므로 정확히 맞는다).

방식(10-24 실측 — ANM 타일 표를 **다시 쓴다**, 시트·ANM 크기는 그대로):
 ANM 은 [헤더][위치 스크립트][타일 표]로 되어 있고, 타일 표의 한 줄(8워드 = 부분 하나)은 **4칸(칸 = 16×32, 워드 = (윗 타일<<8)|아랫 타일)**이
 화면에 가로로 이어 붙는다. 띠 줄은 A(「…おわり」) 부분 5개(x 0~319) · B(「次章…」) 부분 4개(x 32~287)로 서로 **다른 워드**다(워드를 비워 가며 확인 —
 `word_probe`). 같은 **타일 번호**를 두 줄이 나눠 쓰는 것뿐이라, 새 타일을 받아 워드를 다시 가리키게 하면 공유가 사라진다.
 1. 상태마다 한글 줄을 **화면 좌표**(띠 캔버스)에 그린다(미래로 24px 굵게 + 오른쪽 그림자, 낫표는 원판 조각의 픽셀을 그대로).
 2. 잉크가 닿는 칸마다 시트의 **쓰지 않는 타일 둘**(위·아래)을 받아 픽셀을 쓰고 워드를 갱신한다 — 잉크 없는 칸은 워드 0.
 3. 타일 풀 = 띠가 아닌 부분(배 그림 등)이 안 쓰는 타일 전부. 모자라면 빌드가 선다.
 4. 시트(TIM → gmfz)·ANM 멤버를 다시 쓴다.

글꼴 `MiraeroNormal-24.bdf`(MIT, Damheo Lee)는 공용 `shared/fonts` 에 있다(고지 `LICENSE-Miraero.txt`).
"""

import json
import os
import struct

import common
import gmfz
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT_PATH = os.path.join(HERE, "chapter_end_layout.json")
BODY = (168, 96, 48)  # 원판 띠 글자 몸
SHADOW = (96, 16, 0)  # 그림자
BAND_Y0, BAND_Y1 = 192, 240  # 화면 아래 띠 영역(행)
SCREEN_W = 320
TILE = 16


FONT_SIZE = 26  # 고운바탕 Bold 픽셀 크기 — 띠 타일 높이(32)·원판 글자 잉크 높이에 맞춘다(마스터 10-24 「고운바탕 볼드가 나아보이네」)


def font_path():
    """고운바탕 Bold — 공용 `shared/fonts/GowunBatang-Bold.ttf`(OFL, 마스터 10-24 판정). 미래로 24 BDF(`MiraeroNormal-24.bdf`)는 이전 선택.

    후보 글꼴 시험용: 환경변수 `CE_FONT=<BDF 경로>`(또는 `chapter_end.py --font`)가 있으면 그 글꼴로 굽는다 — 시험 빌드(`ED_BUILD_TAG=test-…`)에서만 쓴다.
    """
    env = os.environ.get("CE_FONT")
    if env:
        if not os.path.exists(env):
            raise SystemExit(f"🔴 CE_FONT={env} 가 없다")
        return env
    p = os.path.join(
        os.path.dirname(os.path.dirname(HERE)), "shared", "fonts", "GowunBatang-Bold.ttf"
    )
    if not os.path.exists(p):
        raise SystemExit(f"🔴 {p} 가 없다 — main 에서 `git rebase main` 으로 받는다")
    return p


# ── 글꼴 ─────────────────────────────────────────────────────────────────────
class Bdf:
    def __init__(self, path):
        self.g = {}
        cur = None
        bitmap = False
        rows = []
        with open(path, encoding="latin-1") as f:
            for line in f:
                p = line.split()
                if not p:
                    continue
                if p[0] == "ENCODING":
                    cur = {"enc": int(p[1])}
                elif p[0] == "DWIDTH" and cur is not None:
                    cur["dw"] = int(p[1])
                elif p[0] == "BBX" and cur is not None:
                    cur["w"], cur["h"], cur["xo"], cur["yo"] = (int(x) for x in p[1:5])
                elif p[0] == "BITMAP":
                    bitmap, rows = True, []
                elif p[0] == "ENDCHAR":
                    bitmap = False
                    if cur is not None and cur["enc"] >= 0:
                        cur["rows"] = rows
                        self.g[cur["enc"]] = cur
                    cur = None
                elif bitmap:
                    rows.append(int(p[0], 16))
                    cur["bits"] = len(p[0]) * 4

    def glyph(self, ch):
        g = self.g.get(ord(ch))
        if g is None:
            raise SystemExit(f"🔴 글꼴에 {ch!r}(U+{ord(ch):04X}) 가 없다")
        return g


class TtfFont:
    """TTF 글꼴 — `Bdf.glyph` 와 같은 꼴(비트맵 행·박스)로 한 글자씩 그린다. 이미 굵은 글꼴이라 `text_masks` 가 따로 굵게 하지 않는다."""

    pre_bold = True

    def __init__(self, path, size=FONT_SIZE):
        from PIL import ImageFont

        self.f = ImageFont.truetype(path, size)
        self.cache = {}

    def glyph(self, ch):
        g = self.cache.get(ch)
        if g is not None:
            return g
        from PIL import Image, ImageDraw

        l, t, r, b = self.f.getbbox(ch, anchor="ls")
        w, h = max(1, r - l), max(1, b - t)
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((-l, -t), ch, font=self.f, fill=255, anchor="ls")
        a = np.asarray(img) >= 90
        bits = 8 * ((w + 7) // 8)
        rows = [sum(int(v) << (bits - 1 - x) for x, v in enumerate(row)) for row in a]
        g = {"enc": ord(ch), "w": w, "h": h, "xo": l, "yo": -b, "rows": rows, "bits": bits}
        self.cache[ch] = g
        return g


def load_font(path):
    return TtfFont(path) if path.lower().endswith(".ttf") else Bdf(path)


def render_glyph_mask(g, ascent=21):
    """(마스크 h×w, 왼쪽 오프셋, 위 오프셋) — 기준선 위 `ascent` 행을 맨 위로 잡는다."""
    bits = len(f"{g['rows'][0]:0x}") * 4 if False else g.get("bits", 8 * ((g["w"] + 7) // 8))
    m = np.zeros((g["h"], g["w"]), bool)
    for y, v in enumerate(g["rows"]):
        for x in range(g["w"]):
            if v >> (bits - 1 - x) & 1:
                m[y, x] = True
    top = ascent - (g["yo"] + g["h"])  # 기준선 y=ascent
    return m, g["xo"], top


def text_masks(font, text, gap=2):
    """낱말(공백 없음) → (몸 마스크, 그림자 마스크) — 글자마다 잉크 폭 + `gap` 만큼 나아가는 **비례 자간**(타일 영역이 좁다).

    굵게(가로 1px 겹침) + 오른쪽 그림자 1px — 마스터 10-16 5차(몸 168,96,48 · 그림자 96,16,0).
    """
    H = 30
    adv = 0
    items = []
    for ch in text:
        g = font.glyph(ch)
        m, xo, top = render_glyph_mask(g)
        cols = np.where(m.any(axis=0))[0]
        if not len(cols):
            adv += 8
            continue
        items.append((adv - cols.min(), top, m))
        adv += int(cols.max() - cols.min() + 1) + gap
    W = adv + 4
    body = np.zeros((H, W), bool)
    for x0, top, m in items:
        h, w = m.shape
        for y in range(h):
            for x in range(w):
                if m[y, x] and 0 <= top + y < H and 0 <= x0 + x < W:
                    body[top + y, x0 + x] = True
    bold = body.copy()
    if not getattr(font, "pre_bold", False):
        bold[:, 1:] |= body[:, :-1]  # 가로 1px 겹침
    shadow = np.zeros_like(bold)
    shadow[:, 1:] = bold[:, :-1]
    shadow &= ~bold
    cols = np.where((bold | shadow).any(axis=0))[0]
    rows = np.where((bold | shadow).any(axis=1))[0]
    x0, x1, y0, y1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
    return bold[y0:y1, x0:x1], shadow[y0:y1, x0:x1]


# ── 시트 ─────────────────────────────────────────────────────────────────────
def load_layout():
    with open(LAYOUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def split_sheet(raw):
    """TIM 바이트 → (팔레트 u16×256, 픽셀 h×256 uint8, 픽셀 시작 오프셋)."""
    blk = struct.unpack_from("<I", raw, 8)[0]
    pal = np.frombuffer(raw[20 : 20 + 512], dtype="<u2")
    p = 8 + blk
    _, _, w, h = struct.unpack_from("<4H", raw, p + 4)
    off = p + 12
    pix = np.frombuffer(raw[off : off + w * 2 * h], dtype=np.uint8).reshape(h, w * 2).copy()
    return pal, pix, off


def pal_rgb(pal):
    return np.array(
        [
            [round(c * 255 / 31) for c in (int(v) & 31, (int(v) >> 5) & 31, (int(v) >> 10) & 31)]
            for v in pal
        ]
    )


def nearest(P, rgb):
    return int(np.abs(P - np.array(rgb)).max(axis=1).argmin())


def tile_ink(pix, r, c, transparent):
    t = pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE]
    return ~np.isin(t, transparent)


def read_anm(L, name, disc="ed3"):
    """(ANM 바이트, 멤버 키, 타일 표 시작 워드 번호)."""
    v = L[name]
    lba, size = common.iso_files(disc)[v["pack"]]
    arc = common.read_lba(disc, lba, size)
    mem = common.arc_members(arc)
    key = f"..\\ANM\\P_{v['sheet']:03d}.ANM"
    o, ln = mem[key]
    anm = bytearray(arc[o : o + ln])
    w0 = struct.unpack_from("<H", anm, 0)[0]
    return anm, key, (w0 - 4) // 2


class PlanError(Exception):
    pass


def find_quote_bitmaps(pix, transparent, shapes, L, name):
    """{낫표: (색인 배열 크롭, 마스크 크롭, 화면 y)} — 시트 안 낫표 타일을 모양으로 찾고, 원판 화면 y 는 레이아웃의 타일 위치로."""
    out = {}
    tiles = L[name]["states"]["A"]["tiles"]
    for key, off in tiles.items():
        r, c = (int(x) for x in key.split(","))
        ink = tile_ink(pix, r, c, transparent)
        for q, sh in shapes.items():
            if (ink == sh).all() and q not in out:
                ys, xs = np.where(ink)
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                idx = pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE][y0:y1, x0:x1].copy()
                out[q] = (idx, ink[y0:y1, x0:x1], r * TILE + off[1] + y0)
    return out


def quote_shapes_from(pix0, tr0, L0):
    """서장 시트의 「 (5,0) · 」 (3,13) 잉크 모양."""
    return {"「": tile_ink(pix0, 5, 0, tr0), "」": tile_ink(pix0, 3, 13, tr0)}


def build_line(
    font,
    parts,
    quotes,
    body_idx,
    shadow_idx,
    tr_idx,
    y_center,
    x_lo,
    x_hi,
    gap=2,
    center=160,
    shrink=0,
):
    """줄 조각 [(종류, 값)] → 색인 캔버스(띠 높이 × 320) + 조각 x 목록. 값: ('text', 낱말) · ('q', '「'|'」') · ('gap', 폭)."""
    items = []  # (kind, mask_body, mask_shadow, idx, y)
    for kind, val in parts:
        if kind == "gap":
            items.append(
                ("gap", max(1, val - shrink) if val >= 7 else val)
            )  # 낱말 사이 빈칸만 줄인다(낫표 옆 1px 은 그대로)
        elif kind == "text":
            body, shadow = text_masks(font, val, gap=gap)
            y = int(round(y_center - body.shape[0] / 2))
            items.append(("text", body, shadow, None, y))
        else:
            idx, mask, qy = quotes[val]
            items.append(("q", mask, np.zeros_like(mask), idx, qy))
    W = sum(it[1] if it[0] == "gap" else it[1].shape[1] for it in items)
    x0 = int(round(center - W / 2))
    if x0 < x_lo or x0 + W > x_hi:
        raise PlanError(f"줄 폭 {W}px 가 띠 부분 [{x_lo},{x_hi}) 안에 안 든다")
    k = np.full((BAND_Y1 - BAND_Y0, SCREEN_W), tr_idx, np.uint8)
    x = x0
    for it in items:
        if it[0] == "gap":
            x += it[1]
            continue
        _kind, body, shadow, idx, y = it
        h, w = body.shape
        y0 = y - BAND_Y0
        sub = k[y0 : y0 + h, x : x + w]
        if idx is not None:
            sub[body] = idx[body]
        else:
            sub[shadow] = shadow_idx
            sub[body] = body_idx
        x += w
    return k, x0, W


def strip_cells(strips, anm, base, claimed, ignore_zero=False):
    """조각(strip)들의 칸 [(워드 번호, 화면 x)] — 양 끝에서 0 워드가 이어지면 최대 2칸씩 늘린다(다른 조각이 안 쓰는 칸만)."""
    cells = {}
    for sp in strips:
        lo, hi, x0 = sp["lo"], sp["hi"], sp["x0"]
        for wi in range(lo, hi + 1, 2):
            cells[wi] = x0 + 8 * (wi - lo)
        for step in (-2, 2):
            wi = lo - 2 if step < 0 else hi + 2
            for _ in range(2):
                x = x0 + 8 * (wi - lo)
                if (base + wi) * 2 + 2 > len(anm) or base + wi < 0:
                    break
                val = struct.unpack_from("<H", anm, (base + wi) * 2)[0]
                if (val == 0 or ignore_zero) and wi not in claimed and -16 <= x < SCREEN_W + 16:
                    cells[wi] = x
                    wi += step
                else:
                    break
    return sorted(cells.items())


def apply_state(pix, anm, base, cells, K, ytop, pool, tr_idx, cache):
    """상태 하나의 칸을 다시 쓴다 — 잉크 있는 반쪽마다 타일을 받아 칠하고 워드를 갱신(잉크 없으면 0).

    🔴 워드 = (윗 타일 << 8) | 아랫 타일 — **높은 바이트가 위, 낮은 바이트가 아래**, 같은 열이다(10-24 원판 램의 워드 바이트를 하나씩 0 으로 만들어
       어느 화면 영역이 바뀌는지 쟀다: 높은 바이트 = y 200~215, 낮은 바이트 = y 216~231).
    """
    used = []
    for wi, x in cells:
        strip = np.full((2 * TILE, TILE), tr_idx, np.uint8)
        for yy in range(2 * TILE):
            Y = ytop - BAND_Y0 + yy
            if not (0 <= Y < K.shape[0]):
                continue
            for xx in range(TILE):
                X = x + xx
                if 0 <= X < SCREEN_W:
                    strip[yy, xx] = K[Y, X]
        off = (base + wi) * 2
        if (strip == tr_idx).all():
            struct.pack_into("<H", anm, off, 0)
            continue
        ids = []
        for half in (strip[:TILE], strip[TILE:]):
            if (half == tr_idx).all():
                ids.append(0)
                continue
            key = half.tobytes()
            t = cache.get(key)
            if t is None:
                if not pool:
                    raise PlanError(
                        f"타일 풀이 모자란다 (이미 {len(cache)}개 썼다, 아직 {len(cells) - cells.index((wi, x))}칸 남음)"
                    )
                t = pool.pop(0)
                r, c = divmod(t, TILE)
                pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] = half
                cache[key] = t
                used.append(t)
            ids.append(
                t + 1
            )  # 🔴 워드의 타일 번호는 1부터다 — 번호 N 이 시트의 N−1 번째 타일(r*16+c)을 그린다(0 = 빈 칸)
        struct.pack_into("<H", anm, off, (ids[0] << 8) | ids[1])
    return used


# ── 장 제목(정본) ────────────────────────────────────────────────────────────
def chapter_titles():
    """{n: 한글 제목} n=0(서장)~7 — `shared/canon/ed3.json` 「ui」(키 `第N章　제목`)."""
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
    import canon

    tab = canon.table("ui", "ed3")
    out = {}
    for jp, kr in tab.items():
        if jp.startswith("序章　") and "〜" not in jp:
            out[0] = kr.split("　")[-1]
        elif (
            jp.startswith("第")
            and jp[1] in "１２３４５６７"
            and jp[2] == "章"
            and jp[3] == "　"
            and "〜" not in jp
        ):
            out["１２３４５６７".index(jp[1]) + 1] = kr.split("　")[-1]
    return out


SHRINKS = (0, 2, 4, 6, 1, 3, 5, 7)
SHIFTS = (0, -4, 4, -8, 8, -2, 2, -6, 6, -10, 10, -1, 1, -3, 3, -5, 5, -7, 7, -12, 12)
GROW_MAX = 300  # 시트 압축이 원본 멤버보다 커도 되는 바이트(아카이브 마지막 섹터 여유 안 — 최소 여유 324B 에서 잡았다)
CHAPTERS = ["MT70V0", "MR43V0", "AT09V0", "CT22V0", "OT12V0", "ST12V0", "GT42V0"]  # 서장~제6장 끝


def line_parts(n, titles, teaser="다음 장"):
    """(A 조각, B 조각) — A = 「서장/제N장 「제목」 끝」, B = 「다음 장 「다음 제목」」(예고)."""
    pre = "서장" if n == 0 else f"제{n}장"
    a = [("text", pre), ("gap", 8), ("q", "「"), ("gap", 1)]
    a += _words(titles[n]) + [("gap", 1), ("q", "」"), ("gap", 8), ("text", "끝")]
    b = [("text", teaser.split(" ")[0]), ("gap", 7)]
    if " " in teaser:
        b += [("text", teaser.split(" ")[1]), ("gap", 8)]
    b += [("q", "「"), ("gap", 1)] + _words(titles[n + 1]) + [("gap", 1), ("q", "」")]
    return a, b


def _words(title):
    out = []
    for i, w in enumerate(title.split(" ")):
        if i:
            out.append(("gap", 7))
        out.append(("text", w))
    return out


def read_sheet(L, name, disc="ed3"):
    v = L[name]
    lba, size = common.iso_files(disc)[v["pack"]]
    arc = common.read_lba(disc, lba, size)
    mem = common.arc_members(arc)
    key = f"..\\TIM\\C_{v['sheet']:03d}.TI3"
    o, ln = mem[key]
    raw, short = gmfz.decompress(arc[o : o + ln])
    assert short == 0, f"{name}: 시트가 모자라게 풀렸다"
    pal, pix, off = split_sheet(raw)
    return v, key, raw, pal, pix, off


def _lines(
    L,
    name,
    v,
    font,
    pa,
    pb,
    pix,
    anm,
    base,
    cells,
    strips,
    quotes,
    tr,
    tr_idx,
    body_idx,
    shadow_idx,
    pool,
    gap,
    shrink,
    shift,
):
    """A·B 두 줄을 그려 시트(pix)·ANM 에 쓴다 → (보고, 캔버스)."""
    report = {}
    canv = {}
    cache = {}
    for st, lp in (("A", pa), ("B", pb)):
        x_lo = max(0, min(x for _w, x in cells[st]))
        x_hi = min(SCREEN_W, max(x for _w, x in cells[st]) + 16)
        yt = strips[st][0]["y"]
        # 원판 잉크 세로 중심(레이아웃의 타일 위치로)
        ys = []
        for kk, (dx, dy) in v["states"][st]["tiles"].items():
            r, c = (int(x) for x in kk.split(","))
            ink = tile_ink(pix_orig(L, name), r, c, tr)
            if ink.any():
                yy = np.where(ink.any(axis=1))[0]
                ys += [r * TILE + dy + yy.min(), r * TILE + dy + yy.max()]
        y_center = (min(ys) + max(ys)) / 2
        K, x0, W = build_line(
            font,
            lp,
            quotes,
            body_idx,
            shadow_idx,
            tr_idx,
            y_center,
            x_lo,
            x_hi,
            gap=gap,
            center=(x_lo + x_hi) / 2 + shift,
            shrink=shrink,
        )
        canv[st] = K
        report[f"{st}_x"] = (x0, W)
        apply_state(pix, anm, base, cells[st], K, yt, pool, tr_idx, cache)
    return report, canv


def plan_chapter(L, name, font, n, titles, shapes, teaser="다음 장", gap=1, max_len=None):
    """챕터 하나 → (새 시트 TIM 바이트, 새 ANM 바이트, 보고, 캔버스)."""
    v, key, raw, pal, pix, off = read_sheet(L, name)
    tr = v["transparent"]
    P = pal_rgb(pal)
    used = np.bincount(pix.reshape(-1), minlength=256)
    tr_idx = max(tr, key=lambda i: used[i])
    cand = [i for i in range(256) if used[i] and i not in tr]
    body_idx = min(cand, key=lambda i: int(np.abs(P[i] - np.array(BODY)).max()))
    shadow_idx = min(cand, key=lambda i: int(np.abs(P[i] - np.array(SHADOW)).max()))
    anm, anm_key, base = read_anm(L, name)
    quotes = find_quote_bitmaps(pix, tr, shapes, L, name)
    if set(quotes) != {"「", "」"}:
        raise PlanError(f"{name}: 낫표 타일을 못 찾았다 {list(quotes)}")
    strips = v["strips"]
    claimed = {wi for st in "AB" for sp in strips[st] for wi in range(sp["lo"], sp["hi"] + 1, 2)}
    cells = {st: strip_cells(strips[st], anm, base, claimed) for st in "AB"}
    text_words = {base + wi for st in "AB" for wi, _x in cells[st]}
    h = pix.shape[0] // TILE
    referenced = set()
    text_tiles = set()
    for wi in range(base, len(anm) // 2):
        val = struct.unpack_from("<H", anm, wi * 2)[0]
        if not val:
            continue
        tiles = {(val >> 8) - 1, (val & 0xFF) - 1} - {-1}  # 번호 → 시트 타일 색인(번호 − 1)
        (text_tiles if wi in text_words else referenced).update(tiles)
    pool = [
        t for t in range(min(h * TILE, 255)) if t not in referenced
    ]  # 번호는 1~255 → 색인 0~254
    # 비운다: 띠 글자가 쓰던 타일은 투명으로(안 쓰는 JP 잔재 제거)
    for t in text_tiles - referenced:
        r, c = divmod(t, TILE)
        pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] = tr_idx
    pa, pb = line_parts(n, titles, teaser)
    pix0, anm0, pool0 = pix.copy(), bytearray(anm), list(pool)
    # 🔴 칸이 모자라면(타일 풀 60~72개 · 줄 폭 256px) 줄 모양을 바꿔 가며 다시 시도한다 — 낱말 빈칸 줄이기 → 글자 간격 0 → 줄 가운데 옮기기.
    #    첫 시도(shrink 0·gap 그대로·가운데)는 이전과 같다. 줄 모양이 타일 경계에 어떻게 얹히느냐로 쓰는 타일 수가 갈린다(같은 글자도 다른 타일).
    err = None
    for shrink in SHRINKS:
        for g in dict.fromkeys((gap, 0)):
            for shift in SHIFTS:
                pix[:] = pix0
                anm = bytearray(anm0)
                pool = list(pool0)
                try:
                    report, canv = _lines(
                        L,
                        name,
                        v,
                        font,
                        pa,
                        pb,
                        pix,
                        anm,
                        base,
                        cells,
                        strips,
                        quotes,
                        tr,
                        tr_idx,
                        body_idx,
                        shadow_idx,
                        pool,
                        g,
                        shrink,
                        shift,
                    )
                    if (
                        max_len is not None
                    ):  # 🔴 압축이 멤버 + 여유를 넘으면 아카이브가 섹터를 넘는다 — 다른 줄 모양으로 다시
                        raw2 = bytearray(raw)
                        raw2[off : off + pix.size] = pix.tobytes()
                        if len(gmfz.wrap(bytes(raw2))) > max_len:
                            raise PlanError(
                                f"압축 {len(gmfz.wrap(bytes(raw2)))}B 가 상한 {max_len}B 를 넘는다"
                            )
                except PlanError as e:
                    err = e
                    continue
                report.update(
                    name=name,
                    pool=len(pool0),
                    body_idx=body_idx,
                    shadow_idx=shadow_idx,
                    pool_left=len(pool),
                    tried=(shrink, g, shift),
                )
                break
            else:
                continue
            break
        else:
            continue
        break
    else:
        raise err
    new_raw = bytearray(raw)
    new_raw[off : off + pix.size] = pix.tobytes()
    return bytes(new_raw), bytes(anm), report, canv


_ORIG = {}


def pix_orig(L, name):
    if name not in _ORIG:
        _ORIG[name] = read_sheet(L, name)[4].copy()
    return _ORIG[name]


def preview(L, name, new_raw, new_anm, out_dir):
    """플랫 양피지 위에 두 상태를 그려 PNG — ANM 워드(칸 위치)대로 칸을 놓는다."""
    from PIL import Image

    v = L[name]
    pal, pix, off = split_sheet(new_raw)
    P = pal_rgb(pal)
    tr = v["transparent"]
    base = (struct.unpack_from("<H", new_anm, 0)[0] - 4) // 2
    bg = np.array([238, 161, 65])
    for st in "AB":
        img = np.tile(bg, (BAND_Y1 - BAND_Y0, SCREEN_W, 1)).astype(np.uint8)
        claimed = {
            wi for s2 in "AB" for sp in v["strips"][s2] for wi in range(sp["lo"], sp["hi"] + 1, 2)
        }
        for wi, x in strip_cells(v["strips"][st], new_anm, base, claimed, ignore_zero=True):
            val = struct.unpack_from("<H", new_anm, (base + wi) * 2)[0]
            yt = v["strips"][st][0]["y"]
            for half, t in enumerate((val >> 8, val & 0xFF)):
                if not t:
                    continue
                r, c = divmod(t - 1, TILE)  # 워드 번호는 1부터
                tile = pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE]
                for yy in range(TILE):
                    for xx in range(TILE):
                        X, Y = x + xx, yt + half * TILE + yy - BAND_Y0
                        if 0 <= X < SCREEN_W and 0 <= Y < img.shape[0] and tile[yy, xx] not in tr:
                            img[Y, X] = P[tile[yy, xx]]
        Image.fromarray(img).resize((SCREEN_W * 3, img.shape[0] * 3), Image.NEAREST).save(
            os.path.join(out_dir, f"{name}_{st}.png")
        )


def member_keys():
    """{「경로!멤버」} — 이 모듈이 다시 쓰는 시트·ANM 멤버(구조 대조가 이 멤버들의 변화를 허용한다)."""
    L = load_layout()
    out = set()
    for name in CHAPTERS:
        v = L[name]
        out.add(f"{v['pack']}!..\\TIM\\C_{v['sheet']:03d}.TI3")
        out.add(f"{v['pack']}!..\\ANM\\P_{v['sheet']:03d}.ANM")
    return out


def member_problems(key, orig, built):
    """구운 멤버가 원본과 **타일 표·픽셀만** 다른가 — 시트는 헤더·팔레트 그대로 + 같은 크기, ANM 은 같은 길이 + 타일 표 앞(헤더·위치 스크립트)이 그대로."""
    out = []
    if key.upper().endswith(".TI3"):
        ro, so = gmfz.decompress(orig)
        rb, sb = gmfz.decompress(built)
        if so or sb:
            out.append(f"{key}: 압축이 모자라게 풀린다")
        elif len(ro) != len(rb):
            out.append(f"{key}: 풀린 크기가 다르다 {len(ro)} → {len(rb)}")
        else:
            _p, _x, off = split_sheet(ro)
            if ro[:off] != rb[:off]:
                out.append(f"{key}: TIM 헤더·팔레트가 바뀜")
    else:
        if len(orig) != len(built):
            out.append(f"{key}: ANM 길이가 다르다 {len(orig)} → {len(built)}")
        else:
            w0 = struct.unpack_from("<H", orig, 0)[0]
            if orig[: w0 - 4] != built[: w0 - 4]:
                out.append(f"{key}: ANM 타일 표 앞(헤더·위치 스크립트)이 바뀜")
    return out


def apply(disc, arcs, teaser="다음 장", gap=1):
    """장 끝 띠 시트·ANM 멤버를 새로 써서 `arcs`({아카이브 경로: 바이트})에 반영한다 — 시험·정식 빌드 공용. 글꼴이 없으면 SystemExit(조용히 건너뛰지 않는다)."""
    import arcpack

    assert disc == "ed3"
    L = load_layout()
    font = load_font(font_path())
    titles = chapter_titles()
    shapes = quote_shapes_from(pix_orig(L, "MT70V0"), L["MT70V0"]["transparent"], L)
    done = []
    for i, name in enumerate(CHAPTERS):
        v = L[name]
        lba0, size0 = common.iso_files(disc)[v["pack"]]
        arc0 = common.read_lba(disc, lba0, size0)
        o0, n0 = common.arc_members(arc0)[f"..\\TIM\\C_{v['sheet']:03d}.TI3"]
        try:
            raw, anm, rep, _canv = plan_chapter(
                L, name, font, i, titles, shapes, teaser, gap, max_len=n0 + GROW_MAX
            )
        except PlanError as e:
            raise SystemExit(f"🔴 장 끝 띠 {name}: {e}") from e
        # 🔴 스트림 길이 = 멤버 길이 — 게임은 멤버 끝까지 스트림을 읽는다(`gmfz.compress_to`). 압축이 원본보다 길면 멤버가 늘고,
        #    `arcpack` 이 마지막 섹터 여유 안에서 뒤 멤버를 민다(모자라면 거기서 선다).
        blob = gmfz.wrap(raw)
        if len(blob) <= n0:
            blob = gmfz.wrap_to(raw, n0)
        back, short = gmfz.decompress(blob)
        assert back == raw and short == 0, f"{name}: 시트 압축 되읽기가 다르다"
        base = arcs.get(v["pack"])
        if base is None:
            lba, size = common.iso_files(disc)[v["pack"]]
            base = common.read_lba(disc, lba, size)
        repl = {f"..\\TIM\\C_{v['sheet']:03d}.TI3": blob, f"..\\ANM\\P_{v['sheet']:03d}.ANM": anm}
        packed, _plan = arcpack.repack(bytes(base), repl)
        arcs[v["pack"]] = packed
        done.append((name, rep["pool"] - rep["pool_left"], rep["pool"]))
    return done


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--maps", default=",".join(CHAPTERS))
    ap.add_argument("--teaser", default="다음 장")
    ap.add_argument("--gap", type=int, default=1)
    ap.add_argument("--font", default=None, help="후보 글꼴 BDF(기본 미래로 24)")
    a = ap.parse_args()
    if a.font:
        os.environ["CE_FONT"] = a.font
    L = load_layout()
    font = load_font(font_path())
    titles = chapter_titles()
    p0 = pix_orig(L, "MT70V0")
    shapes = quote_shapes_from(p0, L["MT70V0"]["transparent"], L)
    bad = 0
    for i, name in enumerate(CHAPTERS):
        if name not in a.maps.split(",") or "strips" not in L[name]:
            continue
        try:
            raw, anm, rep, canv = plan_chapter(L, name, font, i, titles, shapes, a.teaser, a.gap)
            print(name, "ok", rep)
            if a.out:
                os.makedirs(a.out, exist_ok=True)
                preview(L, name, raw, anm, a.out)
        except PlanError as e:
            bad += 1
            print(name, "문제", e)
    return 1 if bad else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
