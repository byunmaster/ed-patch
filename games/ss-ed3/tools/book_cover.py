"""읽을거리 **표지 그림** — `/SYSTEM/BOOK*.BIN` 안에 들어 있다.

    python3 games/ss-ed3/tools/book_cover.py --list          # 어느 책에 무엇이 있나
    python3 games/ss-ed3/tools/book_cover.py --dump BOOK21   # PNG 로 뽑는다

🔴 **표지는 글자가 아니라 그림이다**(유저 짐작이 맞았다 2026-08-31). 속장은 12×12 폰트로
   그리는 우리 문안이지만, 표지의 제목·저자는 **큰 세리프체로 미리 그려 둔 비트맵**이다.
   그래서 폰트를 아무리 고쳐도 안 바뀐다.

## 자리 (BOOK21 실측)

    0x0324  팔레트 — BGR555 BE, `0x2d60` 으로 시작해 `0x53ff` 로 끝난다
    0x0536  헤더   — BE16 폭(0x78=120) · BE16 높이(0x18=24)
    0x053A  픽셀   — **8bpp 색인**, 값 0~31 (팔레트 칸)
    0x107A  팔레트 (둘째 그림 몫)
    0x127A  헤더   — 96×16  → 저자 「バンカーフック４世」
    0x127E  픽셀

⇒ 규칙: **`BE16 W · BE16 H · W*H 바이트`**, 값이 전부 0x20 미만이면 그림이다.
  같은 파일 안에 여러 장이 들어가고, 각 장 앞쪽에 팔레트가 있다.

⚠ **크기를 바꾸지 않는다** — 헤더의 W·H 를 고치면 뒤 오프셋이 전부 밀린다.
  한국어로 다시 그릴 때도 **같은 칸 안에** 그린다.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

PAL_HEAD = 0x2D60  # 팔레트 첫 색 (실측 — 40 권이 같다)
PAL_TAIL = 0x53FF  # 팔레트 끝 색


def images(data):
    """`[(헤더오프셋, 폭, 높이)]` — 값이 전부 0x20 미만인 W×H 덩어리를 그림으로 본다."""
    out = []
    i = 0
    while i < len(data) - 4:
        w, h = struct.unpack_from(">HH", data, i)
        if 32 <= w <= 320 and 8 <= h <= 64 and i + 4 + w * h <= len(data):
            px = data[i + 4 : i + 4 + w * h]
            #   ⚠ 「값이 작다」만으로는 0 벌판이 다 걸린다 — **채워진 비율**도 본다.
            nz = sum(1 for v in px if v)
            if max(px) < 0x20 and 0.08 < nz / len(px) < 0.75:
                out.append((i, w, h))
                i += 4 + w * h
                continue
        i += 2
    return out


def palette(data, before):
    """그 그림 **앞쪽**의 팔레트 → `[(r,g,b)]`. 못 찾으면 회색조."""
    head = struct.pack(">H", PAL_HEAD)
    at = data.rfind(head, 0, before)
    if at < 0:
        return [(i * 8, i * 8, i * 8) for i in range(32)]
    tail = data.find(struct.pack(">H", PAL_TAIL), at)
    end = tail + 2 if 0 <= tail < before else at + 64
    pal = []
    for i in range(at, end, 2):
        w = struct.unpack_from(">H", data, i)[0]
        #   ⚠ 새턴 CRAM 은 **BGR555** — 빨강이 **하위 5 비트**다(거꾸로 읽으면 청록/올리브가 된다).
        pal.append(((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8))
    return pal


def ink_indices(px, pal):
    """그 그림이 실제로 쓰는 **획 색인**과 **테두리 색인** → `(fill, edge)`.

    원본을 흉내 내는 게 목적이라 **가장 밝은 칸**을 획으로, 그 절반쯤 밝기를 테두리로 쓴다.
    """
    used = sorted({v for v in px if v})
    if not used:
        return 1, 1
    lum = {v: sum(pal[v]) if v < len(pal) else 0 for v in used}
    fill = max(used, key=lambda v: lum[v])
    #   🔴 테두리는 **그 그림이 실제로 쓰는 가장 어두운 칸**이다 — 원본이 그렇다
    #     (실측: 어두운 화소가 잉크의 35%). 중간 밝기로 두르면 획이 뭉툭해 보인다.
    edge = min(used, key=lambda v: lum[v])
    return fill, edge


#   🔴 **명조로 그린다 — 원본이 명조다**(유저 확인 2026-09-01).
#     원본은 **획이 1 px 인 얇은 세리프에 어두운 테두리**이고 팔레트로 **계조**를 준다
#     (실측: 밝은 획의 가로 길이가 168 회 중 대부분 1 px · 어두운 화소가 잉크의 35% ·
#     팔레트 41 색이 금색 그러데이션). 픽셀 고딕(neodgm·갈무리)으로는 그 결이 안 난다.
#     ⚠ Apple SD Gothic Neo 가 이 머신에 있지만 **독점 서체라 안 쓴다**(레포는 공개다).
#     ✅ 나눔명조는 **OFL 1.1** 이라 임베딩·재배포가 자유롭다 — KSC 2350 자로 서브셋해
#        `assets/fonts/NanumMyeongjo-KSC.ttf` 로 넣었다(3.0MB → 948KB, `pyftsubset`).
#     ⓘ `shared/fonts/` 가 아니라 **게임 아래**다 — 지금 쓰는 데가 이 게임의 표지뿐이라
#       「둘째 소비자가 생길 때 공용으로」(루트 CLAUDE.md 「설계 원칙」 YAGNI).
FONT = os.path.join(C.GAME_DIR, "assets", "fonts", "NanumMyeongjo-KSC.ttf")
SIZES = (24, 22, 20, 18, 16, 14, 12)


def render(text, w, h, fill, edge=None, want_h=None):
    """`text` 를 `w×h` 색인 픽셀로 → `bytes` (0 = 투명).

    ⚠ **칸을 못 바꾼다** — 헤더의 W·H 를 고치면 뒤 오프셋이 전부 밀린다.
    🔴 **안티에일리어스를 팔레트 계조로 옮긴다** — 원본이 그렇게 반짝인다.
      그 그림이 실제로 쓰는 색인을 밝기순으로 세워 사다리로 삼는다(없는 색은 안 쓴다).
    🔴 크기는 **원본 잉크 높이(`want_h`)에 가장 가까운 것**. 칸이 아니라 원본이 기준이다.
    ⓘ `edge` 는 안 쓴다 — 계조 자체가 어두운 가장자리를 만든다.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    text = text.replace("|", "\n")
    best = None
    for sz in SIZES:
        img = Image.new("L", (w * 3, h * 3), 0)
        dr = ImageDraw.Draw(img)
        f = ImageFont.truetype(FONT, sz)
        dr.multiline_text((w, h), text, font=f, fill=255, align="center", spacing=1)
        a = np.asarray(img)
        ys, xs = (a > 0).nonzero()
        if not len(ys):
            continue
        sub = a[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        if sub.shape[0] > h or sub.shape[1] > w:
            continue
        score = abs(sub.shape[0] - want_h) if want_h else -sub.shape[0]
        if best is None or score < best[0]:
            best = (score, sub)
    if best is None:
        raise SystemExit(f"표지 문안이 칸을 넘는다: {text!r} ({w}x{h})")
    sub = best[1]

    ramp = list(edge) if isinstance(edge, (list, tuple)) else [fill]
    px = np.zeros((h, w), np.uint8)
    oy, ox = (h - sub.shape[0]) // 2, (w - sub.shape[1]) // 2
    idx = np.clip((sub.astype(int) * len(ramp)) // 256, 0, len(ramp) - 1)
    px[oy : oy + sub.shape[0], ox : ox + sub.shape[1]] = np.where(sub > 0, np.array(ramp)[idx], 0)
    return px.tobytes()


COVERS = os.path.join(C.GAME_DIR, "script", "book", "covers.json")


def table():
    """`{BOOKnn: {"0x536": "검사교본 1", …}}` — **손으로 확정한 것만** 담는다.

    🔴 표지는 40 권 55 장이라 자동으로 밀어 넣으면 **틀린 제목이 40 개** 나온다.
      정본에 적힌 것만 바꾸고 나머지는 원문 그대로 둔다(일본어로 남아도 안 틀린다).
    """
    if not os.path.exists(COVERS):
        return {}
    import json

    with open(COVERS, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def patch(data, stem, tbl):
    """그 책의 표지 그림을 한국어로 다시 그린다 → `(새 bytes, 넣은 수)`. **크기 불변**."""
    want = tbl.get(stem)
    if not want:
        return data, 0
    out = bytearray(data)
    done = 0
    for off, w, h in images(data):
        text = want.get(f"{off:#x}") or want.get(f"0x{off:x}")
        if not text:
            continue
        pal = palette(data, off)
        px = data[off + 4 : off + 4 + w * h]
        #   그 그림이 실제로 쓰는 색인을 **밝기순 사다리**로 — 계조를 원본에서 빌린다
        ramp = sorted({v for v in px if v}, key=lambda v: sum(pal[v]) if v < len(pal) else 0)
        fill, _ = ink_indices(px, pal)
        ys = [i // w for i, v in enumerate(px) if v]
        want_h = (max(ys) - min(ys) + 1) if ys else None
        new = render(text, w, h, fill, edge=ramp, want_h=want_h)
        assert len(new) == w * h, (len(new), w * h)
        out[off + 4 : off + 4 + w * h] = new
        done += 1
    assert len(out) == len(data)
    return bytes(out), done


def books(disc=1):
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if n.startswith("/SYSTEM/BOOK") and "DAT" not in n:
                yield os.path.basename(n)[:-4], d.read_extent(lba, size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="어느 책에 그림이 몇 장인가")
    ap.add_argument("--dump", metavar="BOOKnn", help="그 책의 그림을 PNG 로")
    ap.add_argument("--out", default=None, help="PNG 낼 자리 (기본 work/review/cover)")
    a = ap.parse_args()

    if a.list:
        tot = 0
        for stem, b in books():
            im = images(b)
            tot += len(im)
            if im:
                print(f"  {stem}  " + " · ".join(f"{o:#07x} {w}x{h}" for o, w, h in im))
        print(f"→ 그림 {tot} 장")
        return 0

    if a.dump:
        from PIL import Image

        out = a.out or os.path.join(C.REVIEW_DIR, "cover")
        os.makedirs(out, exist_ok=True)
        for stem, b in books():
            if stem != a.dump:
                continue
            for o, w, h in images(b):
                pal = palette(b, o)
                px = b[o + 4 : o + 4 + w * h]
                #   ⓘ 색인 0 은 **투명**이다 — 화면에선 가죽 표지가 비친다.
                img = Image.new("RGBA", (w, h))
                img.putdata(
                    [
                        (0, 0, 0, 0)
                        if v == 0
                        else (*(pal[v] if v < len(pal) else (255, 0, 255)), 255)
                        for v in px
                    ]
                )
                p = os.path.join(out, f"{stem}_{o:06x}_{w}x{h}.png")
                img.resize((w * 4, h * 4), Image.NEAREST).save(p)
                print(f"  {p}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
