"""전 씬 대사 쪽을 **제품 이미지의 글리프로 그려** 번호 붙은 시트와 짝 표(pairs.tsv)로 낸다 — 에뮬레이터 없이(촬영 칸 불필요).

    python3 tools/dialog_render.py [--image 경로] [--out 폴더] [--chapters ABCDEFGO] [--pairs]

왜 에뮬이 아닌가: 대사는 **번역 단계에서 이미 24칸 줄로 미리 접혀 패딩된 조각**이라(`typeset.page_segments`) 엔진이 하는 일은 쪽 넘김과 글리프 그리기뿐이다.
그 둘을 글리프 배열(`font.read_glyph`)과 반각 목록(`hangul.half_codes` — 훅이 6px 로 앉히는 글리프)으로 그대로 재현한다.
🔴 이건 **게임이 그린 화면이 아니라 그 재현**이다 — 이름창 자리·창 틀·변수(아이템 이름·숫자) 삽입은 흉내(회색 칸)뿐이고, 훅·창 폭 문제는 못 잡는다. 그건 에뮬 확인 몫(`docs/status.md`).
산출: `<out>/<장>/<아카이브>_<멤버>.png`(쪽을 두 열로 쌓은 시트, 쪽마다 번호) + `<out>/index.tsv` + (--pairs) `<out>/pairs.tsv`(멤버·쪽·조각 색인·화자·원문·우리 — ⚠ 원문 포함, 저장소 밖에만).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import hangul
import josa_build
import reinsert
import speakers
import typeset
from PIL import Image, ImageDraw

from shared.ps1 import gmf_arc

COLS, ROWS_PER_PAGE = 24, 3
BG, FG, BOX = (16, 20, 48), (255, 255, 255), (96, 96, 128)
W, H = COLS * 12 + 16, 3 * 13 + 14 + 14  # 창 폭 · 이름칸 14 + 본문 3줄


class Renderer:
    def __init__(self, exe):
        self.exe = exe
        self.half = set(hangul.half_codes())
        self.cache = {}

    def bits(self, code):
        if code not in self.cache:
            try:
                self.cache[code] = font.read_glyph(self.exe, code)
            except Exception:
                self.cache[code] = None
        return self.cache[code]

    def draw_row(self, img, y, cells):
        x = 8
        px = img.load()
        for c in cells:
            if c == "BOX":
                for dx in range(4 * 12 - 2):
                    for dy in range(10):
                        if dx in (0, 4 * 12 - 3) or dy in (0, 9):
                            px[x + dx, y + 1 + dy] = BOX
                x += 4 * 12
                continue
            b = self.bits(c)
            adv = 6 if c in self.half else 12
            if b is not None:
                for r in range(12):
                    for k in range(12):
                        if b[r][k] and 0 <= x + k < W and y + r < H:
                            px[x + k, y + r] = FG
            x += adv

    def page_image(self, rows, name):
        img = Image.new("RGB", (W, H), BG)
        if name:
            self.draw_row(img, 1, name)
        for i, r in enumerate(rows[:ROWS_PER_PAGE]):
            self.draw_row(img, 15 + 13 * i, r)
        return img


def _wrap(cells):
    out = []
    for i in range(0, max(len(cells), 1), COLS):
        out.append(cells[i : i + COLS])
    return out


def pages_of(mem, st, segs):
    """[(조각 색인들, 줄들)…] — 스트림 하나를 쪽으로. 줄 = 글리프 코드(또는 'BOX')의 목록."""
    prints = st["prints"]
    pages, cur_rows, cur_cells, idxs = [], [], [], []

    def newline():
        nonlocal cur_cells
        cur_rows.extend(_wrap(cur_cells))
        cur_cells = []

    def flip():
        nonlocal cur_rows, idxs
        newline()
        for k in range(0, max(len(cur_rows), 1), ROWS_PER_PAGE):
            pages.append((list(idxs), cur_rows[k : k + ROWS_PER_PAGE]))
        cur_rows, idxs = [], []

    for n, (q, v) in enumerate(prints):
        cur_cells += list(segs[v]) if v < len(segs) else []
        idxs.append(v)
        nxt = prints[n + 1][0] if n + 1 < len(prints) else None
        ops = set(typeset._gap_ops(mem, q, nxt)) if nxt is not None else set()
        if nxt is None:
            flip()
        elif 2 in ops:
            flip()
        elif 1 in ops:
            newline()
        elif ops & {5, 6, 7, 8}:
            cur_cells.append("BOX")
    return pages


def name_cells(mem, st, ents, segs, table):
    sp = speakers.speaker_of(mem, st, ents)
    if not sp:
        return None, ""
    if sp[0] == "n" and sp[1] < len(segs):
        return list(segs[sp[1]]), "n"
    if sp[0] == "p" and sp[1] < len(speakers.PARTY):
        from shared import canon

        kr = canon.lookup(speakers.PARTY[sp[1]], "person", "ed4")
        if kr:
            try:
                return hangul.encode(kr, table), "p"
            except KeyError:
                return None, ""
    return None, ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chapters", default="ABCDEFGO")
    ap.add_argument("--pairs", action="store_true")
    a = ap.parse_args(argv)
    img_path = a.image or os.path.join(
        common.BUILD_DIR, "Eiyuu Densetsu IV (KR).bin"
    )
    import script_kr

    common.verify_source()
    table = hangul.load()
    orig = {}
    if a.pairs:
        import check_jp_left

        orig = check_jp_left.original_codes()
    os.makedirs(a.out, exist_ok=True)
    idx_f = open(os.path.join(a.out, "index.tsv"), "w", encoding="utf-8")
    idx_f.write("멤버\t쪽\t조각\t화자\n")
    pairs_f = open(os.path.join(a.out, "pairs.tsv"), "w", encoding="utf-8") if a.pairs else None
    if pairs_f:
        pairs_f.write("멤버\t쪽\t조각\t화자\t원문\t우리\n")
    with common.open_disc(img_path) as d:
        exe_lba, exe_size = common.iso_files(img_path)[common.EXE_PATH]
        rd = Renderer(bytes(d.read_extent(exe_lba, exe_size)))
        total = 0
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            ch = path[1]
            if ch not in a.chapters:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents_ = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents_:
                if "\\BIN\\" not in nm or not nm.endswith(".BIN") or sz < 8:
                    continue
                mem = data[off : off + sz]
                try:
                    segs = reinsert.member_segments(mem)
                    streams = typeset.message_streams(mem)
                except Exception:
                    continue
                ents = speakers.entities(mem)
                short = nm.split("\\")[-1][:-4]
                tag = f"{path.split('/')[-1][:-4]}_{short}"
                pages = []
                for si, st in enumerate(streams):
                    nc, _k = name_cells(mem, st, ents, segs, table)
                    for ids, rows in pages_of(mem, st, segs):
                        pages.append((si, ids, rows, nc))
                if not pages:
                    continue
                os.makedirs(os.path.join(a.out, ch), exist_ok=True)
                cols = 2
                nrows = (len(pages) + cols - 1) // cols
                sheet = Image.new("RGB", (cols * (W + 6), nrows * (H + 14)), (0, 0, 0))
                dr = ImageDraw.Draw(sheet)
                for n, (si, ids, rows, nc) in enumerate(pages, 1):
                    x, y = (n - 1) % cols * (W + 6), (n - 1) // cols * (H + 14)
                    dr.text((x + 2, y), f"{n:03d} m{si} #{','.join(map(str, ids))}"[:60], fill=(200, 200, 120))
                    sheet.paste(rd.page_image(rows, nc), (x, y + 12))
                    sp = ""
                    if nc:
                        sp = "".join(
                            (table_rev(table, c)) for c in nc
                        )
                    idx_f.write(f"{tag}\t{n}\t{','.join(map(str, ids))}\t{sp}\n")
                    if pairs_f:
                        base = orig.get((path, nm), [])
                        jp = " / ".join(script_kr.view_text(base[i]) for i in ids if i < len(base))
                        kr = " / ".join(
                            "".join(table_rev(table, c) for c in segs[i]).rstrip() for i in ids if i < len(segs)
                        )
                        pairs_f.write(f"{tag}\t{n}\t{','.join(map(str, ids))}\t{sp}\t{jp}\t{kr}\n")
                    total += 1
                sheet.save(os.path.join(a.out, ch, f"{tag}.png"), optimize=True)
        print(f"쪽 {total}")
    return 0


_REV = {}


def table_rev(table, code):
    if not _REV:
        import textenc

        for c, ch in textenc.charmap().items():
            _REV[c] = ch
        for ch, c in table.items():
            _REV[c] = ch
    return _REV.get(code, "?") if isinstance(code, int) else "□"


if __name__ == "__main__":
    sys.exit(main())
