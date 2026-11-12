"""장 끝 항해 연출(`*V0` 맵)의 **지명 라벨**을 한글로 — 라벨 글자 타일(시트 `B_xxx.TI3`)을 새로 그리고 맵 AM3 의 라벨 칸 워드를 필요한 만큼 다시 가리킨다.

🔴 배경(10-24 실측):
 - 라벨 글자는 시트의 **투명 바탕(색 255) 16×16 글자 타일**이다. 한 타일을 여러 라벨이 나눠 쓴다(서장 「ラ」「グ」 · 「ー」 세 라벨, 제1장 「テ」·「ッ」 …).
 - AM3(압축 해제 20,544B)의 라벨 칸 워드는 (라벨, 칸 번호)마다 하나이고 **지형 바탕을 함께 가리킨다** — 다른 라벨 칸의 워드를 빌리면 그 자리의 바탕(성벽·연못)이
   비친다. 워드를 다른 칸의 것으로 바꾸면 그 칸이 그 타일을 그린다 · 워드 0 은 검은 칸.
 방식(`plan_map`): **제 칸 워드·타일을 그대로 두고 제 타일에 글자를 그린다**(바탕 보존). 한글이 일본어보다 짧으니 남는 칸은 제 타일을 투명으로 비운다.
 타일을 다른 라벨과 나눠 쓰는데 글자가 다르면(충돌) 그 칸만 **같은 라벨 안의 자유 타일 워드**로 돌린다(그래도 칸이 없으면 다른 라벨 것).
 한자 칸(타일을 못 알아낸 칸)은 늘 빈 칸으로 돌린다.

설정(`LABELS`)의 칸 → 워드·타일 대응은 램의 맵 창(20×12 칸)과 화면을 맞춰 얻었다(워드 → 타일 식은 아직 모른다 —
`.local/work/inbox/ps1-ed3/chapter-end-impl/lab/label_probe2.py`). 워드는 AM3 안에서 **모든 출현**을 바꾼다(링 버퍼 이음매 때문에 한 칸이 두 곳에 있다).
지명 표기는 정본(`shared/canon` 지명)에서 읽고 없으면 빌드가 선다.
"""

import os
import struct
import sys

import common
import gmfz
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
TILE = 16

# 맵별 — 라벨마다 (원문, 칸별 AM3 워드, 칸별 시트 타일 번호). 워드·타일은 램의 맵 창(20×12 칸)과 화면을 맞춰 얻었다
# (`.local/work/inbox/ps1-ed3/chapter-end-impl/lab/label_probe2.py`) — 빌드는 워드 서열을 AM3 에서 찾아 그 칸들을 다시 쓴다.
LABELS = {
    "MT70V0": {
        "pack": "/SCE0/SC009.DAT",
        "am3": "..\\MAP\\MT700.AM3",
        "sheet": "..\\MAP\\B_500.TI3",
        "labels": [
            ("ラグーナ", [35650, 36674, 37698, 38722], [99, 100, 123, 89]),
            ("ディーネ", [35714, 36738, 37762, 38786], [121, 122, 123, 105]),
            ("ニーリ", [35522, 36546, 37570], [87, 123, 73]),
            ("ラグピック", [35778, 36802, 37826, 38850, 39874], [99, 100, 101, 102, 103]),
            ("アルデ", [38658, 39682, 35714], [71, 72, 121]),
            ("テグラ", [39746, 36802, 39810], [104, 100, 99]),
        ],
    },
    "AT09V0": {
        "pack": "/SCE2/SC206.DAT",
        "am3": "..\\MAP\\AT090.AM3",
        "sheet": "..\\MAP\\B_550.TI3",
        "labels": [
            ("ダイス", [53058, 53122, 53186], [192, 193, 194]),
            ("ダーツ", [54082, 54146, 54210], [192, 208, 224]),
            ("ボルト", [55106, 55170, 55234], [195, 211, 227]),
        ],
    },
    "CT22V0": {
        "pack": "/SCE3/SC309.DAT",
        "am3": "..\\MAP\\CT220.AM3",
        "sheet": "..\\MAP\\B_560.TI3",
        "labels": [
            ("ボルト", [53954, 54018, 54082], [176, 112, 115]),
            ("イグニス", [58050, 55106, 56130, 56194], [144, 145, 146, 113]),
            ("アンデラ", [56065, 54978, 56002, 57026], [128, 129, 130, 177]),
        ],
    },
    "OT12V0": {
        "pack": "/SCE4/SC410.DAT",
        "am3": "..\\MAP\\OT120.AM3",
        "sheet": "..\\MAP\\B_570.TI3",
        "labels": [
            ("トネリコ", [57281, 57217, 57153, 57090], [115, 146, 134, 99]),
            ("シフール", [62914, 62978, 63042, 63106], [119, 135, 150, 136]),
            ("オルドス", [61890, 61954, 62018, 62082], [120, 136, 152, 151]),
            ("ハイゼン", [63938, 64002, 64065, 64130], [132, 148, 131, 147]),
            ("リズの家", [64962, 65026, 65090, 65154], [134, 130, 133, 149]),
        ],
    },
    "ST12V0": {
        "pack": "/SCE5/SC505.DAT",
        "am3": "..\\MAP\\ST120.AM3",
        "sheet": "..\\MAP\\B_580.TI3",
        "labels": [
            ("オルドス", [57090, 62274, 62338, 62402], [192, 242, 193, 243]),
            ("ハイゼン", [61185, 61250, 61314, 61377], [224, 240, 225, 241]),
            ("リズの家", [59138, 59202, 59266, 59330], [209, 208, 211, 210]),
            ("ホルク", [60225, 60289, 60353], [226, 242, 227]),
        ],
    },
    "MR43V0": {
        "pack": "/SCE1/SC105.DAT",
        "am3": "..\\MAP\\MR430.AM3",
        "sheet": "..\\MAP\\B_510.TI3",
        "labels": [
            ("テグラ", [36802, 35778, 35714], [100, 105, 88]),
            ("ネルバ城", [37442, 37506, 37570, 37634], [87, 104, 89, 99]),
            ("チッタ", [34754, 33730, 33666], [71, 72, 73]),
            ("テュエール", [36609, 36673, 34498, 35522, 36546], [100, 101, 102, 103, 104]),
            ("ロップ島", [35458, 38530, 38594, 38658], [121, 72, 122, 123]),
        ],
    },
    "GT42V0": {
        "pack": "/SCE6/SC606.DAT",
        "am3": "..\\MAP\\GT420.AM3",
        "sheet": "..\\MAP\\B_590.TI3",
        "labels": [
            ("ギドネル", [57858, 60226, 60290, 58050], [208, 209, 210, 225]),
            ("バラカ", [59202, 59266, 59330], [240, 241, 242]),
        ],
    },
}


def korean(jp, cells=None):
    """정본(`shared/canon` 지명)에서 한글 표기 — 없으면 SystemExit(조용히 일본어로 두지 않는다).

    🔴 ED3 는 지명을 **띄어 쓴다**(마스터 10-29 「일본어 원문은 원래 띄어쓰기가 없어서 한국어로는 띄어쓰는 게 맞아. ed1,2 는 HUD 에 공간이 부족해서
    어쩔 수 없었던 거고」 — 칸·대사·월드맵 패널 모두). 라벨 칸은 칸 하나에 글자 하나라 **공백도 한 칸**을 먹는다 — 띄운 꼴이 칸 수에 들면 그대로,
    안 들면(「리즈의 집」 5자 > 4칸) 붙여 쓴다(10-07 「칸만 붙여쓰기」의 남은 자리)."""
    import canon

    kr = canon.lookup(jp, "place", "ed3")
    if not kr:
        raise SystemExit(f"🔴 지명 라벨 {jp!r} 의 정본 표기가 없다 — 관리자에게 후보를 올린다")
    if cells is not None and len(kr) > cells:
        return kr.replace(" ", "")
    return kr


def glyph_tile(font, ch, white, outline, transparent=255):
    """16×16 타일(색인) — 글자 흰색 + 1px 외곽선, 바탕 투명."""
    from chapter_end import render_glyph_mask

    g = font.glyph(ch)
    m, _xo, top = render_glyph_mask(g, ascent=13)  # 14px 글꼴: 기준선 위 13행
    h, w = m.shape
    body = np.zeros((TILE, TILE), bool)
    ox = (TILE - w - 1) // 2
    oy = 1 + top
    for y in range(h):
        for x in range(w):
            if m[y, x] and 0 <= oy + y < TILE and 0 <= ox + x < TILE:
                body[oy + y, ox + x] = True
    body[:, 1:] |= body[:, :-1].copy()  # 굵게 — 가로 1px 겹침(원판 라벨 획이 굵다)
    ring = np.zeros_like(body)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sh = np.zeros_like(body)
            ys = slice(max(dy, 0), TILE + min(dy, 0))
            yd = slice(max(-dy, 0), TILE + min(-dy, 0))
            xs = slice(max(dx, 0), TILE + min(dx, 0))
            xd = slice(max(-dx, 0), TILE + min(-dx, 0))
            sh[ys, xs] = body[yd, xd]
            ring |= sh
    ring &= ~body
    t = np.full((TILE, TILE), transparent, np.uint8)
    t[ring] = outline
    t[body] = white
    return t


def label_colors(pal_rgb, pix, tiles):
    """시트 팔레트에서 글자 흰색·외곽선(진한 초록) 색인 — 라벨 타일에서 가장 많이 쓰인 것."""
    white = outline = None
    cw = {}
    co = {}
    for t in tiles:
        r, c = divmod(t, TILE)
        for i in np.unique(pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE]):
            rgb = pal_rgb[int(i)]
            n = int((pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] == i).sum())
            if np.abs(rgb - np.array([230, 239, 239])).max() <= 9:
                cw[int(i)] = cw.get(int(i), 0) + n
            elif rgb[0] < 24 and 70 <= rgb[1] <= 115 and rgb[2] < 70:
                co[int(i)] = co.get(int(i), 0) + n
    if cw:
        white = max(cw, key=cw.get)
    if co:
        outline = max(co, key=co.get)
    if white is None or outline is None:
        raise SystemExit("🔴 라벨 타일에서 글자색·외곽선색을 못 찾았다")
    return white, outline


def plan_map(name, am3_raw, pix, font, pal_rgb=None):
    """→ (새 AM3 바이트, 보고) — 시트 픽셀 `pix` 는 제자리 수정.

    🔴 칸 워드는 **지형 바탕을 함께 가리킨다**(10-24 실측: 다른 라벨 칸의 워드를 빌리면 그 라벨 자리의 바탕 — 성벽·연못 — 이 비친다). 그래서
    **제 칸의 워드·타일을 그대로 쓰는 것이 먼저**다 — 글자는 제 칸 타일에 그린다. 타일을 다른 라벨과 나눠 쓰는데 글자가 다르면(충돌) 그 칸만
    **같은 라벨 안의 다른 칸 워드**(바탕이 비슷하다), 그것도 없으면 다른 라벨의 것을 빌린다. 빈 칸은 제 워드 그대로 두고 타일을 투명으로 비운다
    (그 타일을 다른 라벨이 글자로 쓰면 비운 칸의 워드를 자유 타일의 워드로 돌린다).
    """
    cfg = LABELS[name]
    labels = cfg["labels"]
    w = np.frombuffer(am3_raw, "<u2").copy()
    kr = {jp: korean(jp, len(t)) for jp, _w, t in labels}
    # 타일 → [(워드, 라벨 원문)] — 그 타일을 가리키는 칸들
    cells_of = {}
    for jp, words, tiles in labels:
        for k, t in enumerate(tiles):
            if t is not None:  # None = 타일을 못 알아낸 칸(한자 등) — 글자를 못 받고 늘 빈 칸으로 돌린다
                cells_of.setdefault(t, []).append((int(words[k]), jp))
    all_tiles = sorted(cells_of)
    word_users = {}  # 워드 → {(라벨, 칸 번호)} — 🔴 한 워드를 두 라벨이 나눠 쓰면(같은 글자 칸: 「アルデ」의 デ = 「ディーネ」의 ディ) 전역 치환이 못 쓴다
    for jp, words, tiles in labels:
        for k in range(len(tiles)):
            word_users.setdefault(int(words[k]), set()).add((jp, k))
    pos_remap = []  # (라벨, 칸 번호, 새 워드) — 그 라벨 런이 있는 자리만 바꾼다

    def word_of(t, prefer=None):
        for wd, jp in cells_of[t]:
            if jp == prefer:
                return wd
        return cells_of[t][0][0]

    # 글자색·외곽선색 색인 — 🔴 타일마다 제 것(한 맵 라벨들이 서로 다른 흰색 색인을 쓴다)
    colors = {}
    for t in all_tiles:
        if "white" in cfg:  # 시험용 고정값
            colors[t] = (cfg["white"], cfg["outline"])
            continue
        try:
            colors[t] = label_colors(pal_rgb, pix, [t])
        except SystemExit:
            colors[t] = label_colors(pal_rgb, pix, all_tiles)
    tile_glyph = {}  # 타일 → 글자
    remap = {}  # 옛 워드 → 새 워드
    pending = []  # (라벨, 칸 번호, 글자) — 제 타일이 남의 글자로 찬 칸
    glyph_cells = {}  # 라벨 → {칸 번호}
    for jp, words, tiles in labels:
        s = kr[jp]
        n, m = len(tiles), len(s)
        if m > n:
            raise SystemExit(f"🔴 {name}: {jp} → {s} 가 칸({n})보다 길다")
        offs = sorted(range(n - m + 1), key=lambda o: (abs(o - (n - m) / 2), o))
        o = min(
            offs,
            key=lambda o: sum(
                1000 if tiles[o + i] is None else int(tile_glyph.get(tiles[o + i], ch) != ch)
                for i, ch in enumerate(s)
                if ch != " "
            ),
        )
        glyph_cells[jp] = {o + i for i, ch in enumerate(s) if ch != " "}  # 공백 칸은 글자 없이 빈 칸으로 둔다
        for i, ch in enumerate(s):
            if ch == " ":
                continue
            t = tiles[o + i]
            if t is None:
                raise SystemExit(f"🔴 {name}: {jp} 의 글자 칸 {o + i} 에 타일을 모른다 — 칸이 모자라다")
            if tile_glyph.get(t, ch) == ch:
                tile_glyph[t] = ch
                remap[int(words[o + i])] = int(words[o + i])
            else:
                pending.append((jp, o + i, ch))
    # 충돌 칸 — 같은 글자를 이미 가진 타일(같은 라벨 것 먼저), 없으면 자유 타일을 새로 쓴다
    for jp, k, ch in pending:
        holders = [t for t, g in tile_glyph.items() if g == ch]
        if holders:
            holders.sort(key=lambda t: (0 if any(j == jp for _w, j in cells_of[t]) else 1, t))
            t = holders[0]
        else:
            free = [t for t in all_tiles if t not in tile_glyph]
            free.sort(key=lambda t: (0 if any(j == jp for _w, j in cells_of[t]) else 1, t))
            if not free:
                raise SystemExit(f"🔴 {name}: {jp} 충돌 칸에 줄 자유 타일이 없다")
            t = free[0]
            tile_glyph[t] = ch
        words = dict((j, ws) for j, ws, _t in labels)[jp]
        if len(word_users[int(words[k])]) > 1:
            pos_remap.append((jp, k, word_of(t, jp)))
        else:
            remap[int(words[k])] = word_of(t, jp)
    # 빈 칸 — 제 타일이 비어 있으면 제 워드 그대로, 남의 글자가 찼으면 자유 타일의 워드로(같은 라벨 것 먼저)
    blank_fix = []
    for jp, words, tiles in labels:
        for k, t in enumerate(tiles):
            if k in glyph_cells[jp] and int(words[k]) in remap:
                continue
            if any(p[0] == jp and p[1] == k for p in pending):
                continue
            if t is None or t in tile_glyph:
                blank_fix.append((jp, k))
            else:
                remap[int(words[k])] = int(words[k])
    # 🔴 빈 칸 지형 — 비운 칸에 **다른 라벨의 워드**를 빌리면 그 라벨의 바탕(바다)이 비쳐 육지 위에 바다색 사각형이 남는다(10-24 마스터 지적:
    #    제1장 「치타」 오른쪽 · 「튜엘」 왼쪽). 그 칸의 **위·아래 이웃 칸 워드**(라벨이 아닌 지형 워드)를 그 자리에서만 빌린다.
    label_words = {int(x) for _j, ws, _t in labels for x in ws}
    idx_remap = {}  # AM3 색인 → 새 워드(그 자리만)
    for jp, k in list(blank_fix):
        words = [int(x) for x in dict((j, ws) for j, ws, _t in labels)[jp]]
        n = len(words)
        hits = [i for i in range(len(w) - n + 1) if all(int(w[i + q]) == words[q] for q in range(n))]
        ok = bool(hits)
        picks = {}
        for i in hits:
            cand = [int(w[i + k + d]) for d in (-128, 128, -256, 256) if 0 <= i + k + d < len(w)]
            cand = [c for c in cand if 0 < c < 0x8000 and c not in label_words]
            if not cand:
                ok = False
                break
            picks[i + k] = cand[0]
        if ok:
            idx_remap.update(picks)
            blank_fix.remove((jp, k))
    for jp, k in blank_fix:
        words = dict((j, ws) for j, ws, _t in labels)[jp]
        free = [t for t in all_tiles if t not in tile_glyph]
        free.sort(key=lambda t: (0 if any(j == jp for _w, j in cells_of[t]) else 1, t))
        if not free:
            raise SystemExit(f"🔴 {name}: {jp} 빈 칸에 줄 자유 타일이 없다")
        if len(word_users[int(words[k])]) > 1:
            pos_remap.append((jp, k, word_of(free[0], jp)))
        else:
            remap[int(words[k])] = word_of(free[0], jp)
    # 시트 — 라벨 타일을 모두 투명으로 비우고 글자 타일만 그린다
    for t in all_tiles:
        r, c = divmod(t, TILE)
        pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] = 255
    for t, ch in tile_glyph.items():
        r, c = divmod(t, TILE)
        pix[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] = glyph_tile(font, ch, *colors[t])
    # AM3 — 워드는 (라벨, 칸 번호)마다 하나라 **모든 출현**을 같은 값으로 바꾼다
    # (🔴 10-24 실측: 라벨이 링 버퍼 이음매에 걸려 첫 칸이 서열 밖 다른 색인에도 있었다)
    orig = w.copy()
    places = {}
    for old, new in remap.items():
        idx = np.nonzero(orig == old)[0]
        if not len(idx):
            raise SystemExit(f"🔴 {name}: 라벨 칸 워드 {old} 를 AM3 에서 못 찾았다")
        w[idx] = new
        places[old] = len(idx)
    for i, nw in idx_remap.items():  # 비운 칸 — 이웃 지형 워드(그 자리만)
        w[i] = nw
    for jp, k, new in pos_remap:  # 나눠 쓰는 워드 — 그 라벨의 런(이어진 워드 서열)이 있는 자리만
        words = [int(x) for x in dict((j, ws) for j, ws, _t in labels)[jp]]
        n = len(words)
        hits = [i for i in range(len(orig) - n + 1) if all(int(orig[i + q]) == words[q] for q in range(n))]
        if not hits:
            raise SystemExit(f"🔴 {name}: {jp} 의 워드 서열을 AM3 에서 못 찾았다")
        for i in hits:
            w[i + k] = new
        places[(jp, k)] = len(hits)
    report = {
        "labels": {jp: kr[jp] for jp in kr},
        "tiles": len(all_tiles),
        "glyph_tiles": len(tile_glyph),
        "conflicts": len(pending),
        "blank_moved": len(blank_fix),
        "places": places,
    }
    return w.tobytes(), report


def member_keys():
    out = set()
    for cfg in LABELS.values():
        out.add(f"{cfg['pack']}!{cfg['sheet']}")
        out.add(f"{cfg['pack']}!{cfg['am3']}")
    return out


def member_problems(key, orig, built):
    """AM3 는 같은 풀린 크기, 시트는 헤더·팔레트 그대로(`chapter_end.member_problems` 와 같은 검사)."""
    out = []
    ro, so = gmfz.decompress(orig)
    rb, sb = gmfz.decompress(built)
    if so or sb:
        out.append(f"{key}: 압축이 모자라게 풀린다")
    elif len(ro) != len(rb):
        out.append(f"{key}: 풀린 크기가 다르다 {len(ro)} → {len(rb)}")
    elif key.upper().endswith(".TI3"):
        import chapter_end

        _p, _x, off = chapter_end.split_sheet(ro)
        if ro[:off] != rb[:off]:
            out.append(f"{key}: TIM 헤더·팔레트가 바뀜")
    return out


def apply(disc, arcs):
    """지명 라벨 시트·AM3 멤버를 새로 써서 `arcs` 에 반영 — 시험·정식 빌드 공용. 맵 이름 목록을 돌려준다."""
    import arcpack
    import chapter_end

    assert disc == "ed3"
    font = chapter_end.Bdf(os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared", "fonts", "Galmuri14.bdf"))
    done = []
    for name, cfg in LABELS.items():
        base = arcs.get(cfg["pack"])
        if base is None:
            lba, size = common.iso_files(disc)[cfg["pack"]]
            base = common.read_lba(disc, lba, size)
        base = bytes(base)
        mem = common.arc_members(base)
        repl = {}
        o, n = mem[cfg["sheet"]]
        sheet_raw, short = gmfz.decompress(base[o : o + n])
        assert short == 0
        pal, pix, soff = chapter_end.split_sheet(sheet_raw)
        oa, na = mem[cfg["am3"]]
        am3_raw, short = gmfz.decompress(base[oa : oa + na])
        assert short == 0
        new_am3, rep = plan_map(name, am3_raw, pix, font, chapter_end.pal_rgb(pal))
        new_sheet = bytearray(sheet_raw)
        new_sheet[soff : soff + pix.size] = pix.tobytes()
        for key, raw, (oo, nn) in ((cfg["sheet"], bytes(new_sheet), (o, n)), (cfg["am3"], new_am3, (oa, na))):
            kind = base[oo + 1]
            blob = gmfz.wrap(raw, kind)
            if len(blob) <= nn:
                blob = gmfz.wrap_to(raw, nn, kind)  # 🔴 스트림 길이 = 멤버 길이(`gmfz.compress_to`)
            back, short = gmfz.decompress(blob)
            assert back == raw and short == 0, f"{name}: {key} 압축 되읽기가 다르다"
            repl[key] = blob
        packed, _plan = arcpack.repack(base, repl)
        arcs[cfg["pack"]] = packed
        done.append((name, rep))
    return done
