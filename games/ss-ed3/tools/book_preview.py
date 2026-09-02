"""읽을거리 **본문을 책 화면 그대로** 그린다 — 인게임에 안 가고 조판을 본다.

🔴 **책 화면은 12 열 글리프를 8 열로 줄여 그린다 — 두 열을 「더해서」 3 단계 농담으로.**
   (2026-09-02 실측: 검사교본 6 줄·72 글자·**5,808 화소 전부 일치**. 종전 문서의
   「3 열을 2 열로(83/88)」·「여덟 열만 남긴다」는 둘 다 오진이었다.)

       농담 = c_p + c_q     0 = 종이 · 1 = 옅은 먹 · 2 = 진한 먹

       (p,q) = (0,1) (1,2) (3,4) (4,5) (6,7) (7,8) (9,10) (10,11)

   ⇒ 버리는 게 아니라 **폭 1.5 열을 평균**한다. 한쪽만 잉크면 반톤으로 나와서, 획이
     굵어 보이되 완전히 사라지지는 않는다. 한자는 획이 듬성해 견디는데 **한글은
     ㅇ·ㅁ 같은 닫힌 자모가 반톤으로 메워진다.** 원판도 같은 구조다.
   💡 책 전용 글리프를 판다면 기준이 이것이다 — **더해지는 짝**(1·2 / 3·4 / 4·5 …)
     안에서는 틈이 반톤으로 메워지므로, 틈은 `2|3`·`5|6`·`8|9` 경계에 두어야 살아남는다.

⚠ 원본을 읽는다 — 구운 이미지의 `BOOK*.BIN` 은 이미 우리 문안이라 다시 태우면 깨진다.
  폰트만 구운 이미지에서 가져온다(한글 글리프가 거기 있다).

    python3 games/ss-ed3/tools/book_preview.py BOOK04 [BOOK05 …] [--out DIR] [--scale 3]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import book as B
import common as C
import font as F
import hangul_map as H
import reinsert_book as RB
import strtab as S

SQ = ((0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (7, 8), (9, 10), (10, 11))
CELL, LINE = 8, 24  # 화면 칸 폭 · 줄 간격
TONE = ((184, 176, 152), (120, 112, 88), (0, 0, 0))  # 종이 · 옅은 먹 · 진한 먹 (실측)

#   ── 책 화면 기하 (352×240 캡처 실측 2026-09-02) ─────────────────────────────
PAGE_X = (60, 196)  # 왼쪽·오른쪽 쪽의 글자 시작 열
TOP = 55  # 첫 줄 잉크 윗머리
PARA_GAP = 12  # 문단 사이에 더 벌어지는 px
SLOTS = 7  # 한 쪽에 들어가는 줄 수
IDX_OF = {F.sjis_of_index(i): i for i in range(94 * 94)}


def final_lines(stem, data):
    """그 책의 **최종 줄**(재삽입이 실제로 쓰는 것) — 번역이 없으면 원문 줄."""
    tbl = RB.table(stem)
    lines = [
        dict(s, text=S.text_of(s["raw"]))
        for s in S.strings(data, S.load_base(f"/SYSTEM/{stem}.BIN"))
    ]
    out = []
    for pi, (at, rows) in enumerate(B.paragraphs(lines)):
        widths = [len(x["raw"]) for x in lines[at : at + len(rows)]]
        kr = tbl.get(str(pi))
        if kr is None:
            out.append([x["text"] for x in lines[at : at + len(rows)]])
            continue
        base = B.tidy_spaces(B.to_fullwidth(kr))
        kr2, _ = B.fit_spaces(base, widths)
        if not B.split_to(kr2, widths)[1] and "|" in base:
            kr2, _ = B.fit_spaces(B.tidy_spaces(base.replace("|", "　")), widths)
        new, ok = B.split_to(kr2, widths)
        out.append(new if ok else [x["text"] for x in lines[at : at + len(rows)]])
    return out


def squeeze(g):
    """폰트 글리프 `(12, 12)` → 화면 글리프 `(12, 8)`."""
    return np.stack([g[:, p] | g[:, q] for p, q in SQ], axis=1)


def page(rows, fon, hg, cols=13):
    """줄 목록 → 농담 배열(0·1·2) (칸 8px · 줄 간격 24px)."""
    img = np.zeros((LINE * len(rows), cols * CELL), np.uint8)
    for r, s in enumerate(rows):
        raw = H.encode_kr(s, hg)
        for k in range(0, min(len(raw) - 1, cols * 2), 2):
            i = IDX_OF.get(bytes(raw[k : k + 2]))
            if i is None:
                continue
            o = squeeze(F.unpack(fon, i))
            y = r * LINE + 6
            img[y : y + o.shape[0], (k // 2) * CELL : (k // 2) * CELL + CELL] = o
    return img


def paginate(paras):
    """문단 목록 → 쪽 목록. 한 쪽은 `SLOTS` 줄, 문단 사이는 반 줄 더 벌린다."""
    pages, cur, used = [], [], 0
    todo = list(paras)
    while todo:
        p = todo.pop(0)
        #   ⚠ **한 쪽보다 긴 문단은 잘라 넘긴다** — 안 그러면 쪽 밖으로 그린다
        if len(p) > SLOTS:
            todo.insert(0, p[SLOTS:])
            p = p[:SLOTS]
        need = LINE * len(p) + (PARA_GAP if cur else 0)
        if cur and used + need > LINE * SLOTS:
            pages.append(cur)
            cur, used, need = [], 0, LINE * len(p)
        cur.append(p)
        used += need
    if cur:
        pages.append(cur)
    return pages


def spread(left, right, fon, hg):
    """두 쪽을 **책 모양 그대로** 그린다 → 352×240 RGB 배열."""
    rnd = np.random.RandomState(20260902)  # 종이 결 — 결정적이어야 한다
    im = np.zeros((240, 352, 3), np.uint8)
    paper = np.array([(176, 168, 152), (184, 176, 152), (192, 184, 160)], np.uint8)
    im[28:212, 33:319] = paper[rnd.choice(3, (184, 286), p=[0.15, 0.6, 0.25])]
    #   가죽 테두리 · 책배(하이라이트) · 가운데 접힘 그늘 — 캡처에서 잰 자리 그대로
    for x0, x1, c in ((33, 34, (56, 16, 0)), (34, 40, (248, 248, 248)), (40, 48, (48, 28, 4))):
        im[28:212, x0:x1] = c
    for x0, x1, c in (
        (304, 310, (176, 168, 148)),
        (310, 312, (64, 32, 0)),
        (312, 318, (248, 248, 248)),
    ):
        im[28:212, x0:x1] = c
    for x in range(169, 183):
        t = 1 - abs(x - 176) / 8
        im[28:212, x] = (np.array((184, 176, 152)) * (1 - 0.65 * t)).astype(np.uint8)
    for side, paras in ((0, left), (1, right)):
        y = TOP
        for p in paras:
            g = page(p, fon, hg)
            for r in range(len(p)):
                band = g[r * LINE + 6 : r * LINE + 18]
                for lv in (1, 2):
                    ys, xs = (band == lv).nonzero()
                    ok = (y + ys < 211) & (PAGE_X[side] + xs < 352)
                    im[y + ys[ok], PAGE_X[side] + xs[ok]] = TONE[lv]
                y += LINE
            y += PARA_GAP
    return im


def font_of_build():
    """구운 이미지의 `KANJI12.FON` — 한글 글리프가 든 쪽이다."""
    p = os.path.join(C.BUILD_DIR, "Shiroki Majo (KR) (Disc 1).bin")
    if not os.path.exists(p):
        raise SystemExit(f"구운 이미지가 없다: {p}\n  먼저 `python3 games/ss-ed3/tools/build.py`")
    d = C.Disc(p, user_off=C.USER_OFF)
    for n, lba, size in d.files():
        if n == "/SYSTEM/KANJI12.FON":
            return d.read_extent(lba, size)
    raise SystemExit("구운 이미지에 KANJI12.FON 이 없다")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="+", help="BOOK04 …")
    ap.add_argument("--out", default=None, help="PNG 낼 자리 (기본 work/review/book)")
    ap.add_argument("--scale", type=int, default=3)
    a = ap.parse_args()
    fon, hg = font_of_build(), H.load()
    out = a.out or os.path.join(C.REVIEW_DIR, "book")
    os.makedirs(out, exist_ok=True)
    with C.open_disc(1) as d:
        fs = {n: (lba, size) for n, lba, size in d.files()}
        for stem in a.stems:
            key = f"/SYSTEM/{stem}.BIN"
            if key not in fs:
                raise SystemExit(f"그런 책이 없다: {stem}")
            lba, size = fs[key]
            paras = final_lines(stem, d.read_extent(lba, size))
            pages = paginate(paras)
            #   ⓘ **책은 두 쪽씩 펼쳐진다** — 쪽을 둘씩 묶어 한 장으로 낸다
            sheets = []
            for k in range(0, len(pages), 2):
                sheets.append(spread(pages[k], pages[k + 1] if k + 1 < len(pages) else [], fon, hg))
            im = Image.fromarray(np.concatenate(sheets, axis=0))
            p = os.path.join(out, f"{stem}.png")
            im.resize((im.width * a.scale, im.height * a.scale), Image.NEAREST).save(p)
            print(f"  {p}  ({sum(len(x) for x in paras)}줄 · {len(pages)}쪽)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
