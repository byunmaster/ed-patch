"""챕터 판 한글화 — `SCR*.2D` 안의 **그림 글자**를 다시 그린다 (192×40 · 8bpp · 12장).

    python3 tools/patch_gfx_cards.py            # 미리보기만 → work/review/scr/
    python3 tools/patch_gfx_cards.py --apply    # 빌드 이미지에 넣는다

⚠ **자막(`patch_title.py --apply`)을 먼저** 넣는다 — 빌드 사본을 그쪽이 만든다.

🔴 **판은 글자까지 구워진 한 장의 그림이다.** 엔진이 폰트로 찍는 게 아니라 24×5 셀짜리
   완성 이미지를 VDP2 로 올린다(실기 VRAM 대조로 확정 — `dump_scr.py` 머리말).
   그래서 문자열을 아무리 고쳐도 안 바뀐다. 그림을 갈아 끼우는 수밖에 없다.

## 깨끗한 바탕을 어떻게 얻나

원본엔 「글자 없는 판」이 없다. 대신 **판 열둘이 바탕을 공유한다** — 글자 자리만 다르다.
그래서 화소마다 **글자가 아닌 값들의 최빈값**을 고르면 바탕이 복원된다(SCR1·SCR2 를 함께
푼다 — 팔레트가 같고 글자 자리가 더 어긋나 구멍이 준다). 남는 구멍은 27화소뿐이고
(모든 판이 `第`·`章` 을 같은 자리에 쓴다) 최근접 채우기로 메운다.
⚠ 최빈값 동점은 **작은 색인**으로 깬다 — 안 그러면 사전 순서가 결과를 바꾼다(결정성).

## 글자 자리 (열두 장 실측, 흔들림 없음)

    1행 잉크 y 4~18 · 2행 잉크 y 21~35 · 가운데 x 96 · 최대 폭 168 (`終章` 줄이 163)
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_scr

NEODGM = os.path.join(common.ROOT, "shared", "fonts", "neodgm.ttf")
CANON = os.path.join(common.GAME_DIR, "script", "ui.json")
REVIEW = os.path.join(common.REVIEW_DIR, "scr")

# 판 순서 = `dump_scr.PLATE_STARTS` 순서. 정본(`ui.json:cards`)도 이 순서로 열둘이다.
PLATE_FILES = ("/SCR1.2D", "/SCR2.2D")

# 🔴 **잉크 색인을 손으로 적지 않는다.** 76~83 으로 적었다가 75 를 놓쳐 흰 점 넷을,
#    다시 46(글자 그림자)을 놓쳐 잡티를 내보냈다(유저 QA 2026-08-24, 두 번). 경계를 눈으로
#    긋는 한 또 샌다. 그래서 **데이터에서 뽑는다** — 흰 램프(1~11)를 확실한 잉크로 두고,
#    「그 둘레 2px 안에서만 나오는 색」을 잉크 부속(그림자·안티에일리어스·금색과의 혼색)으로
#    친다. 열두 장 실측에서 이 비율은 0.9 위(잉크)와 0.37 아래(바탕)로 깨끗이 갈린다.
CORE_IDX = frozenset(range(1, 12))  # 흰~회색 램프 — 이견 없는 글자 본색
INK_NEAR = 2  # 잉크 둘레 몇 px 까지를 「곁」으로 보나
INK_RATIO = 0.9  # 그 안에서만 나오면 잉크 부속
# 위 규칙이 뽑아낸 집합 — **결과를 못 박아 둔다**(값이 흔들리면 게이트가 운다).
INK_IDX = frozenset({1, 2, 3, 4, 5, 6, 7, 9, 11, 44, 45, 46, 58, 64, 65} | set(range(75, 85)))

WHITE = np.float32([248, 248, 248])  # 팔레트 1번 — 글자 본색

LINES = ((4, 18), (21, 35))  # (위, 아래) 잉크 행 — 원본과 같은 자리에 앉힌다
CENTER_X = 96
MAX_W = 168  # x 12~179. 원본 최장(`そして英雄たちの伝説`)이 163
MAX_SIZE = 16  # 원본 글자가 16px 격자다


def load_canon():
    """카드 `[JP, 번호 라벨, 제목]` — 제목은 정본(`shared/canon` chapter)이 채운다(`patch_ui.load_canon`)."""
    import patch_ui

    return patch_ui.load_canon()[0]


def plates(mm, files):
    """`[(파일, 판번호, 시작셀, (40,192) 색인배열)]` + 팔레트 — 원본에서만 읽는다."""
    out, pal = [], None
    for path in PLATE_FILES:
        lba, size = files[path]
        d = common.read_extent(mm, lba, size)
        r = dump_scr.parse(d)
        if pal is None:
            pal = r["pal"]
        else:
            assert np.array_equal(pal, r["pal"]), f"{path}: 팔레트가 SCR1 과 다르다"
        for i, s in enumerate(dump_scr.PLATE_STARTS):
            out.append((path, i, s, dump_scr.plate_px(r["cells"], s)))
    return out, pal


def ink_indices(px_list):
    """잉크 색인을 **데이터에서** 뽑는다. 못 박아 둔 `INK_IDX` 와 다르면 실패한다."""
    from scipy.ndimage import binary_dilation

    stack = np.stack(px_list)
    core = np.isin(stack, sorted(CORE_IDX))
    near = np.stack([binary_dilation(m, iterations=INK_NEAR) for m in core])
    got = set()
    for v in np.unique(stack):
        m = stack == v
        if (m & near).sum() / m.sum() >= INK_RATIO:
            got.add(int(v))
    assert got == set(INK_IDX), f"잉크 색인이 달라졌다 — 뽑힌 것 {sorted(got)}"
    return stack, np.isin(stack, sorted(got))


def clean_bg(px_list):
    """판 열둘 → 글자 없는 바탕 하나. 반환: (40,192) 색인배열, 단계별 화소 수.

    ⚠ 잉크만 빼고 최빈값을 잡으면 **글자 둘레의 흐린 자국이 남는다** — 같은 글자를 같은
      자리에 쓰는 판이 많아(`第`·`章`) 그 자국이 다수결을 이긴다. 그래서 마스크를 2px
      부풀려 잡고, 그러고도 표본이 없으면 부풀리기 전 마스크로 물러선다(금색 테두리가
      글자에 닿는 자리가 그렇다 — 여기서 물러서지 않으면 테두리가 파인다).
    """
    from scipy.ndimage import binary_dilation, distance_transform_edt

    stack, ink = ink_indices(px_list)
    grown = np.stack([binary_dilation(m, iterations=INK_NEAR) for m in ink])
    h, w = stack.shape[1:]
    bg = np.zeros((h, w), np.uint8)
    tier = np.zeros((h, w), np.uint8)

    def mode(v):
        val, cnt = np.unique(v, return_counts=True)
        return val[np.lexsort((val, -cnt))[0]]  # 동점은 작은 색인 — 결정성

    for y in range(h):
        for x in range(w):
            for t, m in ((1, grown), (2, ink)):
                v = stack[~m[:, y, x], y, x]
                if v.size:
                    bg[y, x], tier[y, x] = mode(v), t
                    break
            else:
                tier[y, x] = 3
    hole = tier == 3
    if hole.any():
        _, idx = distance_transform_edt(hole, return_indices=True)
        bg[hole] = bg[idx[0][hole], idx[1][hole]]
    assert_no_ink(bg)
    return bg, int((tier == 2).sum()), int(hole.sum())


def assert_no_ink(bg):
    """복원한 바탕에 **잉크 색인이 하나도 없어야 한다.**

    잉크 집합에서 한 칸이라도 빠지면 그 색인의 화소가 바탕으로 살아남고, 열두 장에
    그대로 복사돼 화면엔 점·잡티로 뜬다 — 축소한 미리보기로는 사람이 못 잡는다.
    """
    left = sorted({int(v) for v in np.unique(bg)} & set(INK_IDX))
    if left:
        where = [(int(x), int(y)) for y, x in np.argwhere(np.isin(bg, left))]
        raise SystemExit(f"바탕에 잉크 색인이 남았다 — 색인 {left} · 자리 {where[:8]}")


def _fit(text):
    """폭 `MAX_W` 에 들어가는 최대 글자 크기 → (폰트, 잉크상자)."""
    from PIL import ImageFont

    for size in range(MAX_SIZE, 7, -1):
        f = ImageFont.truetype(NEODGM, size, layout_engine=ImageFont.Layout.BASIC)
        bb = f.getbbox(text)
        if bb[2] - bb[0] <= MAX_W:
            return f, bb
    raise SystemExit(f"판에 안 들어간다: {text!r}")


def draw(bg, pal, line1, line2):
    """바탕 + 두 줄 → 새 색인배열. 글자가 닿은 화소만 다시 고른다(바탕은 무손실)."""
    from PIL import Image, ImageDraw

    h, w = bg.shape
    px = bg.copy()
    rgb = pal[px].astype(np.float32)
    palf = pal.astype(np.float32)
    for (y0, y1), text in zip(LINES, (line1, line2), strict=True):
        f, bb = _fit(text)
        im = Image.new("L", (w, h), 0)
        # ⚠ 안티에일리어스를 살린다 — 문턱으로 자르면 16px 획이 계단진다(원본도 AA 다).
        ImageDraw.Draw(im).text(
            (
                CENTER_X - (bb[2] - bb[0]) // 2 - bb[0],
                y0 + ((y1 - y0 + 1) - (bb[3] - bb[1])) // 2 - bb[1],
            ),
            text,
            255,
            font=f,
        )
        a = np.asarray(im)
        al = (a.astype(np.float32) / 255)[..., None]
        rgb = rgb * (1 - al) + WHITE * al
        m = a > 0
        if m.any():
            d2 = ((palf[None, None] - rgb[:, :, None]) ** 2).sum(3)
            px[m] = d2.argmin(2).astype(np.uint8)[m]
    return px


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    canon = load_canon()
    ps, pal = plates(mm, files)
    assert len(canon) == len(ps), f"정본 {len(canon)}장 · 판 {len(ps)}장 — 순서가 어긋났다"

    bg, fell, filled = clean_bg([p[3] for p in ps])
    print(f"바탕 복원 — 판 {len(ps)}장 최빈값 · 부풀리기 물러섬 {fell} · 최근접 {filled}")

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")

    made = []
    for (path, i, start, old), (jp, ch, title) in zip(ps, canon, strict=True):
        new = draw(bg, pal, ch, title)
        made.append(new)
        n = int((new != old).sum())
        print(f"  {path} #{i} 셀{start:4d}  {ch} {title}  ({jp}) · 화소 {n} 변경")
        if not apply:
            continue
        lba, size = files[path]
        off = dump_scr.cell_base(common.read_extent(mm, lba, size)) + start * 64
        want, was = dump_scr.px_to_cells(new), dump_scr.px_to_cells(old)
        with open(dst, "r+b") as f:
            # ⚠ 사전조건은 **원본 JP 이거나 이미 우리 판**이어야 한다. 대상은 제자리 갱신
            #   사본이라 두 번 돌리면 원본 바이트가 아니다 — 그렇다고 사전조건을 빼면
            #   「배치가 밀렸는데 그냥 쓰는」 사고를 못 막는다. 둘 다 허용하고 나머지는 막는다.
            cur = common.read_extent(common.open_image(dst)[1], lba, size)[off : off + len(want)]
            if cur not in (was, want):
                raise SystemExit(f"{path} #{i}: 판 자리가 원본도 우리 것도 아니다 @0x{off:X}")
            ns = common.write_at(f, lba, size, off, want, label=f"{path} 챕터 판 #{i}", expect=cur)
        print(f"      → 0x{off:X} · 섹터 {ns}")
    preview(made, pal)
    if apply:
        verify(dst, files, made)
    else:
        print("  (미리보기만 — 실제로 넣으려면 `--apply`)")


def preview(made, pal):
    from PIL import Image

    os.makedirs(REVIEW, exist_ok=True)
    sheet = np.concatenate(made, 0)
    im = Image.fromarray(pal[sheet])
    p = os.path.join(REVIEW, "chapter_plates_kr.png")
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(p)
    print(f"미리보기 → {p}")


def verify(dst, files, made):
    """되읽기 — 넣은 이미지에서 판 열둘을 다시 뜯어 우리가 그린 것과 대조한다."""
    _f2, mm2 = common.open_image(dst)
    k = 0
    for path in PLATE_FILES:
        lba, size = files[path]
        r = dump_scr.parse(common.read_extent(mm2, lba, size))
        for s in dump_scr.PLATE_STARTS:
            got = dump_scr.plate_px(r["cells"], s)
            assert np.array_equal(got, made[k]), f"{path} 셀{s}: 되읽기 불일치"
            k += 1
    mm2.close()
    print(f"되읽기 확인 — 챕터 판 {k}장")


if __name__ == "__main__":
    main()
