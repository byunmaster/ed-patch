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
#   ⚠ 한글은 같은 크기라도 가나보다 **잉크가 높다**(em 을 꽉 채운다) — 원본 줄 높이가
#     11 행인 자리가 있어 12px 로도 넘친다. 그래서 아래로 더 열어 둔다.
SIZES = (24, 22, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9)  # ⚠ 한 칸씩 촘촘해야 한다 —
#   16 이 안 들어가면 곧장 14 로 떨어져 원판보다 한눈에 작아 보였다(유저 지적 2026-09-02)
LINE_GAP = 3  # 줄 사이 여백 (유저 확정 2026-09-02 — 붙으면 답답하다)
RIGHT_PAD = 2  # 우측정렬의 오른쪽 여백
SPACE_EM = 0.60  # 낱말 사이 공백이 먹는 자리 (글자 크기 대비)
SLANT = 0.22  # 이탤릭 기울기 (원판이 기운 권만 — 문안 끝 `i`)
LINE_MIN_GAP = 2  # 줄과 줄 사이에 남길 최소 여백
ANCHOR_EPS = 6  # 원판 줄의 좌우 여백 차가 이만큼 안이면 「가운데」로 본다
ANCHOR_INSET = 8  # 다만 양쪽이 이만큼은 비어 있어야 「가운데」다
#   🔴 **커버리지를 계조 사다리에 그대로 태우면 한글이 원판보다 흐리다** —
#     원판 글자는 밝은 색이 두툼한데, 안티에일리어싱 커버리지를 선형으로 태우면
#     얇은 획이 죄다 어두운 칸으로 떨어진다(유저 지적 2026-09-03: 저자가 안 보인다).
#     ⇒ 감마로 **부분 커버리지를 밝은 쪽으로** 민다. 0.7 이 원판 무게에 가깝다.
GAMMA = 0.7
#   🔴 **흐린 원인은 두께가 아니라 「가장자리」다**(유저 지적 2026-09-06: 「여전히 흐릿하다」).
#     원판과 겹쳐 보니 우리 글자가 **더 굵은데도** 흐렸다 — 원판은 밝은 속과 어두운 테두리로
#     딱 갈리는데, 우리는 안티에일리어싱이 중간 계조를 넓게 깔아 **속이 안 밝다.**
#     ⇒ 커버리지에 **대비**를 준다(0.5 를 중심으로 기울기 `CONTRAST`). 굵기는 그대로 두고
#     반쯤 덮인 칸만 밝은 쪽/빈 쪽으로 민다. 1.0 이면 예전 그대로, 클수록 또렷하고 계단진다.
#     ⚠ 굵히기(stem darkening)로 가면 **반대로 뭉갠다** — 작은 글자(BOOK13 부제)가 먼저 무너진다.
CONTRAST = 3.5


def sharpen(cov, s=None):
    """커버리지 대비 — 0.5 를 중심으로 기울기 `s`. 굵기는 그대로, 가장자리만 갈라진다.

    ⚠ **반쯤 덮인 칸이 빈 칸이 되기도 한다** — 부르는 쪽은 `cov > 0` 으로 쓸 자리를 다시 잡는다
      (원본 마스크 `a > 0` 을 쓰면 지워진 가장자리에 옛 계조가 남아 테두리가 두 겹이 된다).
    """
    import numpy as np

    s = CONTRAST if s is None else s
    if s == 1.0:
        return cov
    return np.clip((cov - 0.5) * s + 0.5, 0.0, 1.0)


def _mid(a, b):
    """두 줄 사이 여백의 **경계 행** — 이 행은 늘 비운다(위는 앞, 아래는 다음 줄)."""
    return a + max(LINE_MIN_GAP // 2, (b - a) // 2)


def line_boxes(px, w, h):
    """원본 그림의 **줄별 잉크 상자** `[(y0, y1, x0, x1)]` — 빈 행으로 줄을 가른다.

    🔴 **원본은 줄마다 배치가 다르다** — 계단(『大魔導師/オルテガの/竜退治』)·우측 들여쓰기
       (『海賊王ラモンの/隠し財宝』)·좌측(『キャプテン/トーマスの大航海』). 규칙을 짐작하지
       말고 **원본이 쓴 상자를 그대로 따라간다.**
    """
    import numpy as np

    a = np.frombuffer(px, dtype=np.uint8).reshape(h, w) > 0
    on = a.any(1)
    out, i = [], 0
    while i < h:
        if not on[i]:
            i += 1
            continue
        j = i
        while j + 1 < h and on[j + 1]:
            j += 1
        xs = np.where(a[i : j + 1].any(0))[0]
        if len(xs):
            out.append((i, j, int(xs.min()), int(xs.max())))
        i = j + 1
    return out


def last_ink(px, w, box, gap=1, side="right"):
    """원본 줄의 **맨 끝 잉크 덩어리**(`side`)를 색인째 오려 낸다 → `(색인 배열, x 시작)`.

    🔴 **권 번호(Ⅰ Ⅱ Ⅲ …)를 폰트로 못 그린다** — `U+2160` 은 서브셋에 없고 아스키
       `I·II·VIII` 은 폭이 제각각이라 권마다 글자 크기가 달라진다(유저 지적 2026-09-02).
       ⇒ **원판 픽셀을 그대로 오려 붙인다.**
    ⚠ **색인을 그대로 들고 온다** — 이진 마스크로 바꾸면 원판의 계조가 죽어 **획이 굵고
      납작해진다**(유저 지적: 「로마자가 너무 두껍다」).
    ⚠ **덩어리를 열 틈으로 가른다** — 안 그러면 앞 글자의 장음부호(`ー`)까지 물어 온다
      (실측: 9 권이 `ーIX` 로 나왔다). 빈 열이 `gap` 이상 이어지면 거기서 끊는다.
      ⚠ `gap=1` 이어야 한다 — 2 로 두면 `ー` 와 번호 사이의 한 칸 틈을 못 보고
        붙여 온다(Ⅳ·Ⅸ 가 27px 로 잡혔다). 1 이면 아홉 권 다 6~14px 로 맞는다.
    """
    import numpy as np

    y0, y1, x0, x1 = box
    a = np.frombuffer(px, dtype=np.uint8).reshape(-1, w)[y0 : y1 + 1, x0 : x1 + 1]
    cols = (a > 0).any(0)
    runs, st = [], None
    blank = 0
    for i, v in enumerate(cols):
        if v:
            if st is None:
                st = i
            blank = 0
        elif st is not None:
            blank += 1
            if blank >= gap:
                runs.append((st, i - blank))
                st = None
    if st is not None:
        runs.append((st, len(cols) - 1))
    if not runs:
        return None, x1
    a0, a1 = runs[0] if side == "left" else runs[-1]
    return a[:, a0 : a1 + 1].copy(), x0 + a0


def _wave(px, w, box, side):
    """그 줄 끝의 덩어리가 **물결로 보이면** 오려 준다 — 아니면 `None`(폰트로 그린다).

    ⚠ 확인 없이 오려 붙이면 원판의 한자를 물결 자리에 박는다. 물결은 **줄 가운데
      절반**에만 잉크가 있고 폭이 한 칸 남짓이다 — 그 둘로 거른다.
    """
    a, _ = last_ink(px, w, box, side=side)
    if a is None or not (6 <= a.shape[1] <= 16):
        return None
    ys = (a > 0).any(1).nonzero()[0]
    hgt = a.shape[0]
    if len(ys) == 0 or ys.min() < hgt * 0.2 or ys.max() > hgt * 0.85:
        return None
    return a


def render(text, w, h, fill, edge=None, want_h=None, boxes=None, keep=None, waves=None):
    """`text` 를 `w×h` 색인 픽셀로 → `bytes` (0 = 투명).

    ⚠ **칸을 못 바꾼다** — 헤더의 W·H 를 고치면 뒤 오프셋이 전부 밀린다.
    🔴 **안티에일리어스를 팔레트 계조로 옮긴다** — 원본이 그렇게 반짝인다.
      그 그림이 실제로 쓰는 색인을 밝기순으로 세워 사다리로 삼는다(없는 색은 안 쓴다).
    🔴 **원본의 줄 상자를 그대로 따라간다**(`boxes`) — 줄마다 크기·자리·폭을 원본에 맞춘다.
      원본은 **자간을 벌려 칸을 꽉 채운다**(폭 채움 평균 96%). 자연 자간으로 그리면 73%
      밖에 안 차서 원본과 결이 다르다(유저 지적 2026-09-02).
      ⇒ 글자를 하나씩 찍고 **남는 폭을 글자 사이에 고르게 나눠** 원본 폭에 맞춘다.
      ⓘ 줄 수가 원본과 다르면 이 맞춤을 포기하고 가운데로 앉힌다.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    text = text.replace("|", "\n")
    #   🔴 **글리프가 없는 글자는 조용히 빈칸이 된다** — 그러면 표지에서 그 글자만 사라지고
    #     아무도 못 알아챈다(2026-09-02 실측: 부제의 물결표 `〜`(U+301C)·`～`(U+FF5E)가
    #     서브셋 나눔명조에 없어 통째로 지워졌다. 아스키 `~` 는 있다).
    #     ⇒ 여기서 **바로 실패시킨다.** 서브셋을 넓히거나 있는 글자로 바꾼다.
    probe = ImageFont.truetype(FONT, 20)
    miss = sorted({c for c in text if c not in " \n" and not probe.getmask(c).getbbox()})
    if miss:
        raise SystemExit(
            f"표지 문안에 글리프가 없는 글자: {miss} — {text[:24]!r}\n"
            f"  {os.path.basename(FONT)} 서브셋에 없다. 있는 글자로 바꾸거나 서브셋을 넓힌다."
        )

    #   `{}` = 원판 그 줄의 맨 오른쪽 잉크 덩어리를 그 자리에 그대로 쓴다(권 번호 등)
    #   ⓘ 꼬리표 `#크기[/부제크기][i][c]` — `i` 이탤릭 · `c` 는 **원판 배치 무시하고 가운데**
    #   ⓘ `#N` 을 붙이면 **그 크기로 못 박는다** — 같은 계열 여러 권이 권 번호 폭 때문에
    #     크기가 갈리는 걸 막는다(『여검사 사피』 아홉 권, 유저 지적 2026-09-02).
    force = force_sub = None
    italic = center = False
    if "#" in text:
        head, _, tail = text.rpartition("#")
        #   꼬리표는 `#크기[/부제크기][i]` — 크기 없이 `#i` 만으로 기울이기도 된다
        ital = "i" in tail
        cen = "c" in tail
        body = tail.rstrip("ic")
        parts = body.split("/") if body else []
        if (ital or cen or parts) and all(x.isdigit() and x for x in parts) and len(parts) <= 2:
            text = head
            italic, center = ital, cen
            if parts:
                force = int(parts[0])
                force_sub = int(parts[1]) if len(parts) > 1 else None
    #   ⚠ **못 읽은 꼬리표는 글자로 박힌다** — `#i` 를 안 받던 때 『마녀의 순례#』 가
    #     그대로 그려졌고 검사기도 못 봤다(`#` 는 폰트에 있는 글자다). 여기서 막는다.
    if "#" in text:
        raise SystemExit(f"표지 문안의 `#` 꼬리표를 못 읽었다: {text[:32]!r}")
    lines = [x for x in text.split("\n") if x != ""]

    def glyphs(ln, sz):
        """글자 하나씩 → `[(잉크, 폭, 윗머리, 왼쪽여백)]`.

        ⚠ **윗머리(원점 대비 잉크 시작 행)를 같이 들고 다닌다** — 안 그러면 자간을 벌릴 때
          글자를 전부 0 행에 붙이게 되어 **베이스라인이 무너진다**(`~` 는 위에, 한글은
          아래에 앉는다).
        🔴 **왼쪽여백(사이드베어링)도 들고 다닌다** — 잉크를 칸 가운데에 다시 앉히면
          폰트가 정해 둔 좌우 여백을 뭉개서 **자간이 들쭉날쭉해 보인다**(유저 지적
          2026-09-02: 『라몬의』·『올테가의』·『호수의』). 칸(=어드밴스)은 우리가 정하고,
          칸 안에서의 자리는 **폰트가 정한 그대로** 둔다.
        """
        f = ImageFont.truetype(FONT, sz)
        oy = sz * 2
        out = []
        for c in ln:
            img = Image.new("L", (sz * 4, sz * 4), 0)
            ImageDraw.Draw(img).text((sz, oy), c, font=f, fill=255)
            a = np.asarray(img)
            ys, xs = (a > 0).nonzero()
            out.append(
                None
                if not len(ys)
                else (
                    a[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1],
                    float(f.getlength(c)),
                    int(ys.min()) - oy,
                    int(xs.min()) - sz,
                )
            )
        return out

    def slant(a):
        """잉크를 **위로 갈수록 오른쪽으로** 민다 — 원판이 기운 권을 따라간다."""
        hh, ww = a.shape
        pad = round(SLANT * (hh - 1))
        out = np.zeros((hh, ww + pad), a.dtype)
        for y in range(hh):
            dx = round(SLANT * (hh - 1 - y))
            out[y, dx : dx + ww] = a[y]
        return out

    def wave_pair():
        """그 줄의 `~` 를 대신할 **원판 물결** `(왼쪽, 오른쪽)` — 폰트 물결보다 굵다.

        🔴 **아스키 `~` 는 원판 `〜` 보다 가늘다**(유저 지적 2026-09-02). 서브셋에 `〜`
           (U+301C) 가 없어 아스키로 썼는데, 원판이 그 자리에 이미 그려 둔 물결이 있다.
           ⇒ 권 번호와 같은 수법으로 **픽셀째 오려 온다.**
        ⚠ 색인을 **커버리지로 되돌려** 넣는다 — `blit` 이 다시 사다리에 태우므로,
          `(순위+0.5)/칸수*256` 으로 넣어야 원판 색인이 그대로 나온다.
        """
        rank = {v: i for i, v in enumerate(ramp)}
        out = []
        for arr in wave or (None, None):
            if arr is None:
                out.append(None)
                continue
            cov = np.zeros(arr.shape, np.uint8)
            for v, i in rank.items():
                cov[arr == v] = min(255, int((i + 0.5) / len(ramp) * 256))
            ys, xs = (cov > 0).nonzero()
            out.append(cov[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1])
        return out

    def lay(ln, sz, target_w=None):
        """한 줄 → 잉크 배열. **글자를 고정폭 격자에 하나씩 앉힌다.**

        🔴 **원판은 전각 고정폭이라 자간이 균일하다**(일본어라 당연하다). 글자마다 잉크 폭이
           다른 걸 그대로 이어 붙이면 **간격이 들쭉날쭉해진다**(유저 지적 2026-09-02).
           ⇒ 칸 하나를 정하고 글자를 그 **가운데**에 앉힌다. 늘릴 때는 칸을 넓힌다.
        ⚠ 공백도 칸으로 센다 — 종전엔 잉크가 없다고 걸러서 띄어쓰기가 사라졌다.
        """
        gs = glyphs(ln, sz)
        if wave:
            wl, wr = wave_pair()
            for i, arr in ((0, wl), (len(gs) - 1, wr)):
                if arr is None or not (0 <= i < len(gs)) or ln[i] != "~" or gs[i] is None:
                    continue
                a0, adv, top, lft = gs[i]
                #   세로 가운데를 폰트 물결과 맞춘다 — 안 그러면 물결만 떠 보인다
                #   가로는 칸 가운데에 — 원판 조각이라 폰트 여백이 없다
                gs[i] = (arr, adv, top + (a0.shape[0] - arr.shape[0]) // 2, None)
        vis = [g for g in gs if g is not None]
        if not vis:
            return None
        #   🔴 **칸 폭은 글자 크기만으로 정한다** — 그 줄에서 가장 넓은 잉크로 잡으면
        #     `사`(11px 에서 잉크 12) 하나가 낀 줄만 자간이 넓어진다(유저 지적 2026-09-02:
        #     3·9 권 부제만 벌어 보인다). 원판이 전각 고정폭인 것과 같은 이치다.
        f_ = ImageFont.truetype(FONT, sz)
        em = f_.getlength("한")  # 전각 어드밴스 — 한글·한자는 다 이 값이다
        cell = max(sz, round(em))
        ref = min((g[3] for g in vis if g[3] is not None), default=0)  # 가장 왼쪽 사이드베어링
        sp = max(1, round(cell * SPACE_EM))
        #   ⚠ **숫자·로마자는 전각 칸을 안 쓴다** — 『4세』가 한 칸 띄운 것처럼 보였다
        #     (유저 지적 2026-09-03). 한글끼리는 어드밴스가 같아 균일하고, 좁은 글자만
        #     제 어드밴스를 쓴다. 원판 조각(물결)은 폰트 여백이 없으니 전각 칸 그대로.
        units = []
        for c, g in zip(ln, gs, strict=True):
            if g is None:
                units.append(sp)
            elif g[3] is None or f_.getlength(c) >= em * 0.85:
                units.append(cell)
            else:
                units.append(max(1, round(f_.getlength(c)), g[0].shape[1]))
        nat = sum(units)
        extra = 0.0
        if target_w and len(units) > 1 and target_w > nat:
            extra = (target_w - nat) / (len(units) - 1)
        top = min(g[2] for g in vis)
        hgt = max(g[2] + g[0].shape[0] for g in vis) - top
        wid = int(nat + extra * (len(units) - 1) + 0.5)
        #   ⚠ **왼쪽에도 여백을 둔다** — 칸보다 넓은 잉크를 칸 가운데에 앉히면 첫 칸에서
        #     x 가 음수가 되고, 음수 슬라이스는 **빈 조각**이라 그 글자가 조용히 사라진다
        #     (실측 2026-09-02: 원판 물결을 넣자 왼쪽 것만 안 그려졌다).
        pad = cell
        buf = np.zeros((hgt, max(wid, 1) + cell + pad), np.uint8)
        x = 0.0
        for i, g in enumerate(gs):
            if g is not None:
                a_, _, ty, lft = g
                #   폰트가 정한 여백대로 앉힌다(`None` 인 원판 조각만 칸 가운데)
                off = (units[i] - a_.shape[1]) // 2 if lft is None else lft - ref
                xi = pad + round(x) + off
                yi = ty - top
                sl = buf[yi : yi + a_.shape[0], xi : xi + a_.shape[1]]
                buf[yi : yi + a_.shape[0], xi : xi + a_.shape[1]] = np.maximum(
                    sl, a_[: sl.shape[0], : sl.shape[1]]
                )
            x += units[i] + (extra if i < len(units) - 1 else 0)
        ys, xs = (buf > 0).nonzero()
        buf = buf[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        return slant(buf) if italic else buf

    wave = None  # 지금 그리는 줄의 원판 물결 (`lay` 가 본다)
    ramp = list(edge) if isinstance(edge, (list, tuple)) else [fill]
    arr = np.array(ramp)
    px = np.zeros((h, w), np.uint8)

    def blit(a, x, y):
        y0, x0 = max(0, y), max(0, x)
        a = a[: h - y0, : w - x0]
        cov = sharpen(a.astype(float) / 255.0)
        if GAMMA != 1.0:
            cov = cov**GAMMA
        idx = np.clip((cov * len(ramp)).astype(int), 0, len(ramp) - 1)
        ink = cov > 0
        px[y0 : y0 + a.shape[0], x0 : x0 + a.shape[1]] = np.where(
            ink, arr[idx], px[y0 : y0 + a.shape[0], x0 : x0 + a.shape[1]]
        )

    #   ── 원본 줄 상자에 맞춰 앉힌다 ──────────────────────────────────────────
    if boxes and len(boxes) == len(lines):
        #   🔴 **크기는 그림 하나에 하나다** — 줄마다 따로 고르면 둘째 줄만 작아진다
        #     (유저 지적 2026-09-02: 『요술사/겟페우스의 보물』·『해적왕 라몬의/숨겨진 보물』
        #     은 원본이 모든 줄 같은 크기다). 부제(`~…~`)만 한 단계 작게 — 그것도 원본이다.
        #   `{}` 로 붙일 원판 조각이 먹는 폭을 **미리 뺀다** — 안 그러면 글자와 겹친다
        #   ⓘ 조각 앞 여백은 **낱말 사이 공백과 같은 폭**이다 — 「여검사 사피 Ⅴ」 의 공백
        #     둘이 달라 보이면 안 된다(유저 지적 2026-09-02). 그래서 크기가 정해져야 안다.
        frag_w = [
            keep[b[0]].shape[1] if ("{}" in ln and keep and b[0] in keep) else 0
            for ln, b in zip(lines, boxes, strict=True)
        ]

        def gap_for(sz):
            return max(1, round(sz * SPACE_EM))

        bare = [ln.replace("{}", "").rstrip() for ln in lines]
        #   🔴 **원판 잉크 상자에 갇히지 않는다** — 한글은 같은 크기에서 가나보다 잉크가
        #     높아 상자에 딱 맞추면 글자가 작아진다(유저 지적: 「폰트가 작다」).
        #     ⇒ **옆 줄까지의 여백**을 쓴다. 위아래로 최소 `LINE_MIN_GAP` 은 남긴다.
        #   🔴 **가로도 그 줄의 원판 잉크에 갇히지 않는다** — 일본어 부제가 짧았던 줄은
        #     상자도 짧아서, 한국어가 한 글자만 길어도 「칸을 넘는다」가 된다(BOOK10 실측).
        #     ⇒ 그 그림에서 **글자가 실제로 사는 폭**(모든 줄 상자의 합집합)을 쓴다.
        #     책 표지 가운데도 이 폭으로 잡는다 — 유저가 말한 「책 중앙」이 이것이다.
        sx0 = min(b[2] for b in boxes)
        sx1 = max(b[3] for b in boxes)
        #   ⚠ 두 줄이 **같은 여백을 서로 다 쓰면 붙어 한 줄이 된다**(BOOK13 실측).
        #     ⇒ 줄 사이 여백은 **반씩 나눠 갖는다** — 경계 한 행은 반드시 비운다.
        lohi = []
        for i in range(len(boxes)):
            lo = 0 if i == 0 else _mid(boxes[i - 1][1], boxes[i][0]) + 1
            hi = (h - 1) if i == len(boxes) - 1 else _mid(boxes[i][1], boxes[i + 1][0]) - 1
            lohi.append((lo, hi))
        band = [hi - lo + 1 for lo, hi in lohi]
        pick = None
        for sz in SIZES if force is None else [force]:
            sub = force_sub or (
                SIZES[min(SIZES.index(sz) + 1, len(SIZES) - 1)] if sz in SIZES else sz
            )
            drawn = []
            for ln, b in zip(bare, boxes, strict=True):
                wave = (waves or {}).get(b[0])
                drawn.append(lay(ln, sub if ln.startswith("~") else sz))
            if any(a is None for a in drawn):
                continue
            reserve = [(fw + gap_for(sz)) if fw else 0 for fw in frag_w]
            fit = all(
                a.shape[0] <= bd and a.shape[1] + rv <= (sx1 - sx0 + 1)
                for a, rv, bd in zip(drawn, reserve, band, strict=True)
            )
            if fit:
                #   🔴 **가장 큰 크기가 아니라 「원판 잉크 높이에 가장 가까운」 크기**를
                #     고른다(유저 지적 2026-09-02: 저자 줄이 원판보다 훨씬 컸다).
                #     칸을 꽉 채우면 제목과 저자의 크기 관계가 원판과 달라진다.
                gap = sum(
                    abs(a.shape[0] - (b[1] - b[0] + 1)) for a, b in zip(drawn, boxes, strict=True)
                )
                if pick is None or gap < pick[0]:
                    pick = (gap, sz, sub)
        if pick is None:
            raise SystemExit(f"표지 문안이 칸을 넘는다: {text!r} ({w}x{h})")
        _, sz, sub = pick
        reserve = [(fw + gap_for(sz)) if fw else 0 for fw in frag_w]
        first = None
        plan = []
        has_sub = any(x.startswith("~") for x in bare)
        for (y0, y1, bx0, bx1), ln, rv, (lo, hi) in zip(boxes, bare, reserve, lohi, strict=True):
            bh = y1 - y0 + 1
            size = sub if ln.startswith("~") else sz
            wave = (waves or {}).get(y0)
            frag = keep.get(y0) if (rv and keep) else None
            nat = lay(ln, size)
            is_sub = ln.startswith("~")
            #   🔴 **칸 폭에 맞춰 늘리지 않는다**(유저 확정 2026-09-02). 세 번 물렸다 —
            #     『대항해』가 벌어지고, 부제 3·9 권만 넓어지고, 『라몬의』가 흩어졌다.
            #     자간은 **언제나 일정**하고, 모자란 폭은 **글자 크기로** 메운다.
            a = nat
            if is_sub and first is not None:
                #   🔴 **부제는 제목의 오른쪽 끝에 맞춘다**(유저 확정 2026-09-02)
                a = nat
                x = max(0, min(first - a.shape[1], w - a.shape[1]))
            elif len(boxes) > 1 and not has_sub:
                #   🔴 **여러 줄이면 원판의 줄별 배치를 따라간다**(유저 확정 2026-09-02) —
                #     『キャプテン / トーマスの大航海』처럼 **계단**으로 짠 표지가 있어서,
                #     줄마다 가운데로 모으면 원판의 짜임이 통째로 없어진다.
                #     ⚠ 한 줄짜리는 그대로 **책 한가운데**다(맞출 상대가 없다).
                lg, rg = bx0 - sx0, sx1 - bx1
                #   ⚠ **양쪽이 다 비어 있을 때만 「가운데」**다. 폭을 꽉 채운 줄은 어느
                #     쪽인지 알 수 없는데, 그런 줄을 가운데로 두면 왼쪽 기둥이 무너진다
                #     (『怪傑 / ワイルドキャット』 실측) — 그럴 땐 왼쪽이다.
                if lg <= ANCHOR_INSET and rg <= ANCHOR_INSET:
                    #   폭을 꽉 채운 줄 — 어느 쪽인지 알 수 없다. **왼쪽**이다
                    #   (『怪傑 / ワイルドキャット』 실측: lg 1 · rg 0 이라 1px 차로
                    #    오른쪽으로 튕겨 나가 왼쪽 기둥이 무너졌다).
                    x = bx0
                elif min(lg, rg) >= ANCHOR_INSET and abs(lg - rg) <= ANCHOR_EPS:
                    x = bx0 + ((bx1 - bx0 + 1) - (a.shape[1] + rv)) // 2
                elif lg < rg:  # 왼쪽에 붙은 줄
                    x = bx0
                else:  # 오른쪽에 붙은 줄
                    x = bx1 - (a.shape[1] + rv) + 1
                x = max(0, min(x, w - a.shape[1] - rv))
            else:
                #   🔴 **줄마다 책 한가운데에 놓는다**(유저 확정 2026-09-02) — 원판은
                #     우측정렬에 가깝지만, 번역하면 폭이 줄어 한쪽으로 쏠려 보인다.
                #     ⚠ 기준은 원판 잉크 폭이 아니라 **그림 한가운데**(`w/2`)다 — 그림이
                #     표지 앞면 가운데에 놓이므로(실측: 그림 중심 = 표지 중심 ±0.5px)
                #     그래야 책 가운데가 된다.
                #     ⚠ 조각 자리(`rv`)까지 폭에 넣고 가운데를 잡아야 조각과 안 겹친다.
                total = a.shape[1] + rv
                x = max(0, (w - total) // 2)
            if first is None:
                first = x + a.shape[1] + rv  # 제목 줄의 오른쪽 끝 (부제가 여기 맞춘다)
            #   세로는 **원판 줄의 가운데**를 지키되, 자기 띠(`lo`~`hi`) 밖으로는 못 나간다
            #   — 넘기면 옆 줄과 붙어 한 줄로 뭉친다(BOOK13·14 실측 2026-09-02)
            ty = min(max(y0 + (bh - a.shape[0]) // 2, lo), max(lo, hi - a.shape[0] + 1))
            plan.append((a, x, ty, rv, size, frag, y0, bh, lo, hi))
        #   🔴 `c` = **줄 사이 배치는 원판 그대로 두고, 덩어리째 책 가운데로** 옮긴다
        #     (유저 확정 2026-09-02: 『쾌걸/와일드캣』). 줄마다 가운데로 모으면 원판이
        #     짜 놓은 왼쪽 기둥이 무너지므로, **상대 위치는 지키고 평행이동만** 한다.
        if center and plan:
            x0b = min(q[1] for q in plan)
            x1b = max(q[1] + q[0].shape[1] + q[3] for q in plan)
            d = (w - (x1b - x0b)) // 2 - x0b
            d = max(-x0b, min(d, w - x1b))
            plan = [
                (a, x + d, ty, rv, size, frag, y0, bh, lo, hi)
                for a, x, ty, rv, size, frag, y0, bh, lo, hi in plan
            ]
            first = None if first is None else first + d
        for a, x, ty, _rv, size, frag, y0, bh, lo, hi in plan:
            blit(a, x, ty)
            if frag is not None:
                fx = min(w - frag.shape[1], x + a.shape[1] + gap_for(size))
                fy = min(max(y0 + (bh - frag.shape[0]) // 2, lo), max(lo, hi - frag.shape[0] + 1))
                #   🔴 **글자와 겹치면 실패시킨다** — 눈으로 보고 잡을 일이 아니다
                hit = px[fy : fy + frag.shape[0], fx : fx + frag.shape[1]]
                if (hit > 0).any() and (frag[: hit.shape[0], : hit.shape[1]] > 0).any():
                    both = (hit > 0) & (frag[: hit.shape[0], : hit.shape[1]] > 0)
                    if both.sum() > 0:
                        raise SystemExit(
                            f"오려 붙인 조각이 글자와 겹친다({both.sum()} 화소): {text[:24]!r}"
                        )
                #   ⚠ 색인을 **그대로** 옮긴다 — 계조 사다리를 다시 태우면 굵어진다
                sub_ = px[fy : fy + frag.shape[0], fx : fx + frag.shape[1]]
                np.copyto(
                    sub_,
                    frag[: sub_.shape[0], : sub_.shape[1]],
                    where=frag[: sub_.shape[0], : sub_.shape[1]] > 0,
                )
        return px.tobytes()

    #   ── 상자를 못 쓰면 가운데로 ────────────────────────────────────────────
    best = None
    for sz in SIZES:
        cut = [lay(ln, sz) for ln in lines]
        if any(c is None for c in cut):
            continue
        gh = LINE_GAP if len(cut) > 1 else 0
        th = sum(c.shape[0] for c in cut) + gh * (len(cut) - 1)
        tw = max(c.shape[1] for c in cut)
        if th > h or tw > w:
            continue
        score = abs(th - want_h) if want_h else -th
        if best is None or score < best[0]:
            best = (score, cut, th)
    if best is None:
        raise SystemExit(f"표지 문안이 칸을 넘는다: {text!r} ({w}x{h})")
    _, cut, th = best
    y = (h - th) // 2
    for c in cut:
        blit(c, (w - c.shape[1]) // 2, y)
        y += c.shape[0] + (LINE_GAP if len(cut) > 1 else 0)
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
        bx = line_boxes(px, w, h)
        #   `{}` 가 있는 줄은 원판의 맨 오른쪽 잉크 덩어리를 오려 둔다
        keep, waves = {}, {}
        for bi, ln in enumerate(text.replace("|", "\n").split("\n")):
            if bi >= len(bx):
                continue
            if "{}" in ln:
                keep[bx[bi][0]] = last_ink(px, w, bx[bi])[0]
            #   `~…` · `…~` 는 원판이 그 줄 끝에 그려 둔 물결을 그대로 오려 쓴다
            #   ⚠ **한쪽만 있는 줄도 있다**(BOOK25 『〜その成り立ち』) — 양쪽을 따로 본다
            body = ln.split("#")[0].replace("{}", "").strip()
            if len(body) > 1 and (body.startswith("~") or body.endswith("~")):
                waves[bx[bi][0]] = (
                    _wave(px, w, bx[bi], "left") if body.startswith("~") else None,
                    _wave(px, w, bx[bi], "right") if body.endswith("~") else None,
                )
        new = render(text, w, h, fill, edge=ramp, want_h=want_h, boxes=bx, keep=keep, waves=waves)
        assert len(new) == w * h, (len(new), w * h)
        out[off + 4 : off + 4 + w * h] = new
        done += 1
    assert len(out) == len(data)
    return bytes(out), done


def audit(disc=1):
    """구운 표지를 **원판과 대조해 수치로 본다** → `[(책, 그림, 문제…)]`.

    🔴 **눈으로 보고 잡을 일이 아니다**(유저 지적 2026-09-02 — 겹침을 두 번 놓쳤다).
      확인하는 것:
        · 줄 수가 원판과 같은가
        · 각 줄의 잉크가 원판 줄 상자 **안에** 있는가 (넘치면 옆 줄·조각을 침범한다)
        · 폭 채움이 원판과 크게 다르지 않은가 (원판 96% 가 기준)
    """
    import numpy as np

    tbl = table()
    out = []
    for stem, b in books(disc):
        want = tbl.get(stem)
        if not want:
            continue
        nb, _ = patch(bytes(b), stem, tbl)
        for off, w, h in images(b):
            key = f"{off:#x}"
            if key not in {k.lower() for k in want} or w > 200:
                continue
            o_px = b[off + 4 : off + 4 + w * h]
            n_px = nb[off + 4 : off + 4 + w * h]
            ob, nbx = line_boxes(o_px, w, h), line_boxes(n_px, w, h)
            msg = []
            if len(ob) != len(nbx):
                msg.append(f"줄 수 {len(ob)}→{len(nbx)}")
            else:
                #   가로는 **그림의 글자 폭**(줄 상자 합집합)으로 본다 — 줄마다 원판 상자에
                #   가두면 일본어가 짧았던 줄이 늘 빨간불이 된다(render 와 같은 기준)
                sx0, sx1 = min(x[2] for x in ob), max(x[3] for x in ob)
                for i, ((_y0, _y1, _x0, _x1), (a0, a1, b0, b1)) in enumerate(
                    zip(ob, nbx, strict=True)
                ):
                    lo = 0 if i == 0 else _mid(ob[i - 1][1], ob[i][0]) + 1
                    hi = (h - 1) if i == len(ob) - 1 else _mid(ob[i][1], ob[i + 1][0]) - 1
                    if a0 < lo or a1 > hi:
                        msg.append(f"{i}줄이 세로로 넘친다 {a0}~{a1} ⊄ {lo}~{hi}")
                    #   가로는 **폭**으로 본다 — 자리는 그림 한가운데로 옮겼으므로
                    #   원판 잉크 자리와 겹치는지가 아니라 「원판보다 넓어졌나」가 문제다
                    if b1 - b0 > sx1 - sx0 + 2 or b0 < 0 or b1 > w - 1:
                        msg.append(f"{i}줄이 가로로 넘친다 {b0}~{b1} (원판 폭 {sx1 - sx0 + 1})")

            def fill(px, _w=w, _h=h):
                a = np.frombuffer(px, dtype=np.uint8).reshape(_h, _w) > 0
                xs = np.where(a.any(0))[0]
                return (xs.max() - xs.min() + 1) / _w if len(xs) else 0.0

            fo, fn = fill(o_px), fill(n_px)
            #   ⓘ 폭 채움은 **경고**다 — 크기를 못 박은 계열(`#N`)은 일부러 덜 채운다
            note = [f"ⓘ 폭 채움 {fo:.0%}→{fn:.0%}"] if fo - fn > 0.25 else []
            if msg or note:
                out.append((stem, key, msg, note))
    return out


def books(disc=1):
    with C.open_disc(disc) as d:
        for n, lba, size in d.files():
            if n.startswith("/SYSTEM/BOOK") and "DAT" not in n:
                yield os.path.basename(n)[:-4], d.read_extent(lba, size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="어느 책에 그림이 몇 장인가")
    ap.add_argument("--audit", action="store_true", help="구운 표지를 원판과 대조한다")
    ap.add_argument("--dump", metavar="BOOKnn", help="그 책의 그림을 PNG 로")
    ap.add_argument("--out", default=None, help="PNG 낼 자리 (기본 work/review/cover)")
    a = ap.parse_args()

    if a.audit:
        bad = audit()
        hard = [x for x in bad if x[2]]
        for stem, key, msg, note in bad:
            tag = "⚠" if msg else " "
            print(f"  {tag} {stem} {key}  " + " · ".join(msg + note))
        print(f"→ 표지 점검 — 문제 {len(hard)} · 참고 {len(bad) - len(hard)}")
        return 1 if hard else 0

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
