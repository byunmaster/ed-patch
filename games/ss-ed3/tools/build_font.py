"""폰트 두 벌을 굽는다 — `KANJI12.FON` 에 한글, `ASCII.FON` 에 반각 부호 여백.

크기는 둘 다 불변이고, 덮는 자리는 정본(`hangul_map.json`)과 아래 `ASCII_PAD` 뿐이다.

    python3 games/ss-ed3/tools/build_font.py            # work/derived/KANJI12.FON
    python3 games/ss-ed3/tools/build_font.py --preview 가한글

원본 잉크가 **0~10행**(실측: 1,638/1,833 글리프가 0행에서 시작, 1,589 가 10행에서 끝)이라
Galmuri11 을 `dy=-3` 으로 얹으면 베이스라인이 그대로 맞는다.

🔴 **크기를 안 바꾼다.** 파일 하나를 통째로 교체하지만 바이트 수가 같아야 ISO 배치가 안
   흔들린다(`write_at` 이 그걸 단언한다).
⚠ **덮는 자리는 `hangul_map.json` 정본만** — 「지금 계산한 빈 슬롯」이 아니다. 소재가 늘면
   빈 슬롯이 밀리는데, 정본을 읽으면 이미 넣은 문안이 안 깨진다.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common as C
import font as F
import hangul_map as H

from shared import fonts

OUT = os.path.join(C.OUT_DIR, "KANJI12.FON")
OUT_ASCII = os.path.join(C.OUT_DIR, "ASCII.FON")
DY = -3  # 🔴 **원판 한자와 같은 자리**(0~10 행)에 앉힌다.
#   ⚠ 창 하나가 **글리프의 0 행을 버린다** — 스탯 창이다(유저가 짚었다 2026-08-27).
#     원본도 같이 잘리는데 티가 안 난다: 실측 1,841 자 중 89% 가 0 행에 잉크가 있지만
#     **평균 3.0 · 중앙값 2 화소**뿐이다(攻 1 · 力 1 · 知 1). 한글은 초성 ㄱ·ㅁ·ㅂ·ㅍ·ㅈ 의
#     윗변이 **가로획**이라 공 9 · 구 9 · 마 8 · 지 8 화소가 통째로 날아간다.
#   ⓘ **종전에는 전역으로 한 행 내려**(`DY=-2`) 그 창을 피했다. 그러면 안 자르는 창
#     전부에서 1 px 씩 손해를 보는데, 메뉴 맨 위 **챕터 바**에서 글자가 아래 테두리에
#     붙는 것으로 드러났다(2026-09-03 실측: 흰 띠 14 행 · 잉크 11 행이 위 3 · 아래 0).
#   ⇒ 뒤집었다 — 기본은 원판 자리, **자르는 창에 나가는 문안만** 한 행 내린 판으로
#     인코딩한다(`hangul_map.LOW_PATH` · `bake_low`).
DX = 1  # 🔴 **왼쪽으로 한 칸 붙어 있던 걸 띄운다.**
#   Galmuri11 은 12 칸을 왼쪽부터 채워 **2,350 자 전부 왼쪽 여백이 0** 이었다(실측
#   2026-08-27). 원본 한자는 왼쪽에 한 칸을 비워 두므로, 창 안쪽 경계에 글자가 닿아
#   **잘린 것처럼 보인다**(유저가 스탯 창에서 짚었다). 오른쪽 여백은 1 칸이 46% ·
#   2 칸이 54% 라 **한 칸 밀어도 잘리지 않는다.**
#   ⚠ 슬롯 배정(`hangul_map.json`)은 안 건드리므로 이미 넣은 문안이 안 깨진다.


# 반각 부호에 **좌우 여백**을 준다 — 열 만큼 오른쪽으로 민다.
#   🔴 원본 반각은 전부 **열 0~4 왼쪽 붙임**이라(`font.ASCII_*` 주석) `.`·`,` 처럼 잉크가
#     열 0~1 인 글자는 **왼쪽 여백이 0** 이다. 원문 대사는 반각을 한 자도 안 써서
#     (`docs/status.md`) 이 자리가 여태 안 드러났는데, 우리는 문장부호를 한국식 반각으로
#     쓰기 시작하면서 「`.` 이 앞 글자에 붙는다」가 됐다(유저 실측 2026-08-27).
#   advance 가 6px 이니 2px 밀면 **좌 2 · 우 2** 로 대칭이 된다. 점 사이 간격(4px)은
#   셀 폭이 정하는 것이라 안 변한다 — `...` 의 모양은 그대로고 양 끝만 떨어진다.
ASCII_PAD = {".": 2, ",": 2}
#   ⚠ **몸통이 5px 인 글자는 1px 밖에 못 낸다.** `?`·숫자·`-` 는 잉크가 열 0~4 를 다 써서
#     advance 6px 중 여유가 **한 칸뿐**이다(`.` 은 2px 이라 좌 2·우 2 로 나눌 수 있었다).
#     그래도 0 보다는 낫다 — 한글 오른쪽 여백이 0(`DX=1` 이라 잉크가 열 1~11)이라
#     지금은 **딱 붙는다**(유저 지적 2026-08-28: 「?도 온점처럼 여백이 있으면」).
#   ⓘ `!`(열 2 하나) · `(`·`)`(열 1~3) · `'`(열 1~2)는 **이미 여백이 있다** — 안 건드린다.
ASCII_PAD.update({c: 1 for c in "?-%0123456789"})


def pad_ascii(asc, pad=None):
    """`(새 bytes, 민 글자 수)` — 크기 불변. 잉크가 advance 밖으로 나가면 단언에 걸린다."""
    pad = ASCII_PAD if pad is None else pad
    out = bytearray(asc)
    n = 0
    for ch, dx in pad.items():
        code = ord(ch)
        cols = F.ascii_cols(asc, code)
        assert cols, ch
        assert max(cols) + dx < F.ASCII_ADV, (ch, cols, dx)  # advance 밖으로 밀지 않는다
        g = asc[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE]
        out[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE] = shift_right(
            g, F.ASCII_CELL, F.ASCII_ROWS, F.ASCII_STRIDE, dx
        )
        n += 1
    assert len(out) == len(asc), (len(out), len(asc))
    return bytes(out), n


#   🔴 **반각을 두 행 내린다 — 한글과 기준선을 맞춘다**(유저 지적 2026-09-01).
#     실측: 원본 반각은 **1~9 행**, 원본 한자는 **0~10 행**, 우리 한글은 **1~11 행**이다
#     (한글은 창이 0 행을 잘라서 일부러 한 줄 내렸다 — `DY` 주석).
#     그래서 「10 Pia로」처럼 섞어 쓰면 숫자·알파벳만 **2 px 떠 보인다.**
#   ⇒ 반각을 2 행 내려 **3~11 행**에 앉힌다. 셀이 12 행이라 안 잘리고, 11 행은 원본 글자
#     146 개가 이미 쓰는 자리라 아래도 안 잘린다(`DY` 주석의 실측).
#   ⚠ 한글을 올리는 쪽은 안 된다 — 창이 첫 줄 0 행을 자르는데 한글은 초성 가로획이
#     통째로 날아간다(2026-08-27 에 그래서 내려 앉힌 것이다).
#   ⚠ **ASCII 는 원판 크기·자리 그대로다**(마스터 10-06). 숫자 도안으로 키우고 `ASCII_DY` 를 2 로 내려 봤더니 스탯 창은 맞았지만 장비·저장 목록·상점
#     (소지금·PRICE)이 다 어긋나 **되돌렸다**(`20f40247` 에 시험본이 남아 있다). 알파벳(`Pia`·`Goa`)이 원본 크기라 숫자만 키우면 창마다 기준선이 갈린다.
ASCII_DY = 1

#   🔴 **숫자는 반각으로 써도 전각 글리프로 그려진다**(실측 2026-09-01). 대사창에 반각
#     `1`(0x31)을 넣었는데 화면엔 `KANJI12` 의 전각 `１`(SJIS 0x8250)이 12px 칸을 먹고 나왔다
#     — 렌더러가 ASCII 숫자를 전각 자리로 옮겨 그린다. 그래서 `ASCII_DY` 는 숫자에 안 닿는다.
#   ⇒ 전각 숫자 열을 따로 내린다. 원본은 **행 0~9**(가나 1~9 · 한자 0~10)라 한글(1~11)보다
#     한 행 높고 두 행 짧아, 「１０피아」가 한글보다 떠 보였다(유저 지적 2026-09-01).
#     아래 두 행이 비어 있으니 **2 행 내려 2~11 행**에 앉히면 한글과 밑이 맞는다.
#   ⚠ HUD 의 `70 Pia / 0 Goa` 는 게임이 자기 `ASCII.FON` 으로 직접 그린다(실측: 행 3~11 =
#     `ASCII_DY` 가 먹은 자리) — 여기 안 걸린다.
FULLWIDTH_DIGITS = tuple(range(0x824F, 0x8259))  # ０~９


def digit_slots():
    """전각 숫자 열의 글리프 색인 — `font.sjis_of_index` 의 역을 훑어서 찾는다."""
    want = {v.to_bytes(2, "big") for v in FULLWIDTH_DIGITS}
    out = [i for i in range(F.GLYPHS) if F.sjis_of_index(i) in want]
    assert len(out) == 10, out
    return out


def shift_down(g, rows, stride, dy):
    """글리프 비트를 아래로 `dy` 행 민다 — 셀 높이는 그대로다."""
    bits = "".join(f"{b:08b}" for b in g)
    W = F.ASCII_CELL
    out = ["0" * W] * dy + [bits[r * W : (r + 1) * W] for r in range(rows - dy)]
    s = "".join(out)
    s += "0" * (stride * 8 - len(s))
    return bytes(int(s[i : i + 8], 2) for i in range(0, stride * 8, 8))


def shift_right(g, width, rows, stride, dx=DX):
    """글리프 비트를 오른쪽으로 `dx` 칸 민다 — 폭은 그대로다."""
    bits = "".join(f"{b:08b}" for b in g)
    out = []
    for r in range(rows):
        row = bits[r * width : (r + 1) * width]
        out.append("0" * dx + row[: width - dx])
    s = "".join(out)
    s += "0" * (stride * 8 - len(s))
    return bytes(int(s[i : i + 8], 2) for i in range(0, stride * 8, 8))


#   🔴 **글리프 여섯 칸이 사실은 「그림」이다**(2026-08-29). `KANJI12.FON` 의 α~ζ 자리
#     (**색인 502~507**, JIS 구6 점33~38)에 원판이 **「カートリッジRAM」 72×12 스트립**을
#     통째로 구워 뒀다. 기록 화면의 그 라벨은 문자열을 조판하는 게 아니라 **이 여섯 칸을
#     이어 찍는 것**이다 — `/0.BIN` 0x208D0 의 문자열이 `83bf…83c4`(= `αβγδεζ`)인 이유다.
#   ⚠ **그래서 SJIS `カートリッジ` 검색이 디스크·RAM·BIOS 어디서도 0 건이었다.**
#     글리프 검색으로도 못 찾았는데, `KANJI12` 가 **행마다 12 비트 밀착 패킹**이라
#     바이트 정렬 검색으로는 원리적으로 안 걸린다(행이 바이트 경계를 안 지킨다).
#   ⓘ 뒤 24px(`RAM` 석 자)은 **원본 그대로 둔다** — 픽셀이 그대로면 원판과 같아 보인다.
#   ⓘ 한글 넉 자 × 12px = 48 + 24 = **72px 로 정확히 맞는다.**
LABEL_STRIPS = {502: "카트리지"}


#   🔴 **「…」는 한국식 — 점 셋이 글자 아랫줄(마침표 높이)에 앉는다**(마스터 10-08, 전 기종). 원판 글리프는 일본식(글자 가운데 높이,
#     4·5 행)이라 음성 자막 등 SJIS 「…」를 쓰는 모든 글꼴 경로가 가운데 점으로 나갔다. 점을 마침표 행(9·10)까지 내려 굽는다.
#     대사 문안의 「...」(반각 점 셋)은 ASCII 글꼴 마침표라 원래 바닥이다. 무비 자막은 `movie_hardsub.ELLIPSIS_DROP` 이 같은 5 행.
ELLIPSIS_DROP = 5


def bake_ellipsis(out):
    """SJIS 「…」 글리프(`font.jis_index("…")`)의 점을 `ELLIPSIS_DROP` 행 내린다 — `(바꾼 글리프 수)`."""
    import numpy as np

    idx = F.jis_index("…")
    g = F.unpack(bytes(out), idx).copy()
    assert g[: F.ROWS - ELLIPSIS_DROP].any() and not g[F.ROWS - ELLIPSIS_DROP :].any(), (
        "원판 점이 가운데에 있어야 한다"
    )
    g = np.roll(g, ELLIPSIS_DROP, 0)
    #   🔴 **점은 원판 「?」「!」 의 점에 맞춘다**(마스터 11-16 「원판의 ? ! 에 맞춰서 마침표를 그리는게 맞을 것 같은데」, 규칙 1-3 — 11-16 의 「전 기종 2×2」를 대체).
    #     원판 롬 실화면 실측: `？！` 의 점은 **1×1**, 가나 바닥 행에 앉는다(`baseline-1115/orig`). 그래서 마침표 `.`(`bake_punct`)도 1×1 이고, 「…」 점 셋도 같은 1×1 —
    #     원판 2×2 점의 **아랫행·왼열만** 남긴다(바닥 행·점 간격 4px 그대로, 화면에서 마침표와 같은 행).
    low = [r for r in range(F.ROWS) if g[r].any()][-1]
    cols = [c for c in range(F.CELL) if g[low, c] and not (c and g[low, c - 1])]
    g[:] = 0
    for c in cols:
        g[low, c] = 1
    for c in cols:  # 점은 갈무리 `!` 의 점과 같은 1×2(바닥 행 + 윗행) — 마스터 11-17 「새턴3 은 변경안으로」
        g[low - 1, c] = 1
    out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = F.pack18(g)
    return 1


def bake_label_strips(out, base):
    """글리프 칸에 구워진 **그림 라벨**을 한글로 다시 굽는다 — `(갈아 낀 칸 수)`.

    ⚠ 칸 수·크기는 안 건드린다. 앞의 한글만 덮고 나머지 열은 원본 픽셀을 남긴다.
    """
    import numpy as np

    bdf = fonts.galmuri()
    n = 0
    for start, word in LABEL_STRIPS.items():
        span = -(-len(word) * F.CELL // F.CELL)  # 한글 한 자에 칸 하나
        cells = 6  # 스트립이 차지하는 칸 수 (72px / 12)
        strip = np.concatenate([F.unpack(base, start + i) for i in range(cells)], axis=1)
        for k, ch in enumerate(word):
            bits = bdf.bits(ch, dy=DY, rows=F.ROWS, width=F.CELL)
            cell = np.zeros((F.ROWS, F.CELL), np.uint8)
            cell[:, DX:] = bits[:, : F.CELL - DX]
            strip[:, k * F.CELL : (k + 1) * F.CELL] = cell
        #   🔴 **통째로 한 행 내린다**(마스터 10-01) — 말풍선 안쪽 14 행에서 일반 글자(본체RAM)는 위 2·아래 1 인데
        #     이 스트립은 위 1·아래 2 로 한 줄 높았다(실측: 잉크 34~44 vs 35~45). RAM 석 자(원본 픽셀)도 같이 내려야 한 몸이다.
        assert not strip[-1].any(), "마지막 행이 비어 있어야 한 행 내릴 수 있다"
        strip = np.vstack([np.zeros((1, strip.shape[1]), strip.dtype), strip[:-1]])
        for i in range(cells):
            g = fonts.pack18(strip[:, i * F.CELL : (i + 1) * F.CELL], rows=F.ROWS)
            assert len(g) == F.STRIDE, len(g)
            out[(start + i) * F.STRIDE : (start + i + 1) * F.STRIDE] = g
            n += 1
        assert span <= cells, (span, cells)
    return n


#   🔴 **0 행을 자르는 창에만 쓰는 한 벌** — 같은 글자를 **한 행 내려** 빈 슬롯에 굽는다.
#     기본 글리프는 원판 자리(0~10 행)라 그 창에서 초성 윗획이 날아간다. 그 창에 나가는
#     문안(`hangul_map.lowered_chars`)만 이 슬롯으로 인코딩한다.
#   ⚠ 숫자는 안 넣는다 — 원본 자리가 0~9 행이라 0 행을 버려도 잉크가 안 준다.
LOW_DY = DY + 1


def bake_low(out):
    """자르는 창 전용 글리프를 굽는다 — `(구운 칸 수)`. 배정이 없으면 아무것도 안 한다."""
    table = H.load_low()
    if not table:
        return 0
    import numpy as np

    bdf = fonts.galmuri()
    n = 0
    for ch, idx in table.items():
        bits = bdf.bits(ch, dy=LOW_DY, rows=F.ROWS, width=F.CELL)
        cell = np.zeros((F.ROWS, F.CELL), np.uint8)
        cell[:, DX:] = bits[:, : F.CELL - DX]
        g = fonts.pack18(cell, rows=F.ROWS)
        assert len(g) == F.STRIDE, (ch, len(g))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = g
        n += 1
    return n


#   🔴 **책 화면 전용 한 벌** — 읽을거리는 12 열을 8 열로 **더해서** 그린다. 칸을 꽉 채우는
#     글꼴은 획 사이 틈이 먼저 사라져 뭉갠다(실측: 원판 가나 잉크 폭 9 는 살고 한자 11 은
#     원문에서도 뭉갠다. 우리 Galmuri11 은 10 이라 한자 쪽이다).
#     ⇒ 같은 몸집의 **Galmuri9**(폭 9)를 책 문안에만 쓴다. 배정이 없으면 아무것도 안 한다.
BOOK_FONT, BOOK_DY, BOOK_DX = "Galmuri9", DY + 1, DX + 1


def bake_book(out):
    """책 화면 전용 글리프를 굽는다 — `(구운 칸 수)`."""
    if not os.path.exists(H.BOOK_PATH):
        return 0
    import numpy as np

    with open(H.BOOK_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    bdf = fonts.galmuri(BOOK_FONT)
    n = 0
    for ch, idx in zip(doc["chars"], doc["slots"], strict=True):
        bits = bdf.bits(ch, dy=BOOK_DY, rows=F.ROWS, width=F.CELL)
        cell = np.zeros((F.ROWS, F.CELL), np.uint8)
        cell[:, BOOK_DX:] = bits[:, : F.CELL - BOOK_DX]
        g = fonts.pack18(cell, rows=F.ROWS)
        assert len(g) == F.STRIDE, (ch, len(g))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = g
        n += 1
    return n


#   🔴 **크레딧 자막 전용 한 벌** — Galmuri9 를 **왼쪽 붙임**(DX 0)으로 굽는다. 그리는 쪽이 글자 폭을
#     10 으로 불러(`subtitle_stub.draw_line9`) 9 폭 글리프 + 1 간격이 된다. 배정이 없으면 아무것도 안 한다.
CRED_FONT, CRED_DY = "Galmuri9", -2


def bake_cred(out):
    """크레딧 자막 전용 글리프를 굽는다 — `(구운 칸 수)`."""
    table = H.load_cred()
    if not table:
        return 0
    bdf = fonts.galmuri(CRED_FONT)
    n = 0
    for ch, idx in table.items():
        cell = bdf.bits(ch, dy=CRED_DY, rows=F.ROWS, width=F.CELL)
        g = fonts.pack18(cell, rows=F.ROWS)
        assert len(g) == F.STRIDE, (ch, len(g))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = g
        n += 1
    return n


#   서책 반각 「」 · ' — 마스터 시안 B(10-27 「새턴3은 B가 낫다」): 대사 도안 그대로 1px 획. 6열 도안을 12 칸의 왼쪽 6 열에 앉힌다
#   (책 화면이 3 열씩 (c0+c1, c1+c2) 두 칸으로 줄여 4 열이 되고, `patch_book_half` 가 전진을 4px 로 줄인다). 정본 `inbox/ss-ed3/book-kagi-draft.txt`.
BOOKQ = {
    "｢": ["####..", "#.....", "#.....", "#....."] + ["......"] * 8,
    "｣": ["......"] * 4 + ["....#."] * 6 + [".####."] + ["......"],
    "＇": ["......"] + ["..#..."] * 3 + ["......"] * 8,
}


def bake_liga(out, asc):
    """합자 글리프(`⁉` = `!?`)를 굽는다 — **같은 ASCII.FON 의 `!`·`?`**(여백 조정·내림 반영 판)를 12px 칸 하나에 붙여 앉힌다. `(구운 칸 수)`.

    `!` 는 열 2 의 1px 막대, `?` 는 열 1~5 — `?` 칸을 4 열 오른쪽에 두면 `!`(열 2)와 `?`(열 5~9) 사이 틈이 2px 이고 잉크 8 열(2~9)이 12px 칸 가운데에 앉는다.
    ASCII 도 한글과 같은 12 행이라 행은 그대로 옮긴다(기준선 일치)."""
    table = H.load_liga()
    n = 0
    for ch, idx in table.items():
        if ch == "⁉":  # `!?` 합자는 안 쓴다(마스터 11-13 · 11-17 — 반각 두 글자). 배정 슬롯은 정본이라 남기되 굽지 않는다
            continue
        grid = np.zeros((F.ROWS, F.CELL), np.uint8)
        if ch in BOOKQ:
            for r, row in enumerate(BOOKQ[ch]):
                grid[r, :6] = [1 if x == "#" else 0 for x in row]
        else:
            grid[:, 0:8] |= F.ascii_unpack(asc, ord("!"))
            grid[:, 4:12] |= F.ascii_unpack(asc, ord("?"))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = F.pack18(grid)
        n += 1
    return n


def build(disc=1):
    """`(새 폰트 bytes, 못 찾은 글자)` — 원본과 크기가 같다."""
    base, _ = F.load(disc)
    table = H.load()
    glyphs, missing = fonts.convert_chars(
        list(table), dy=DY, rows=F.ROWS, packer=fonts.pack18, width=F.CELL
    )
    out = bytearray(base)
    for ch, idx in table.items():
        g = shift_right(glyphs[ch], F.CELL, F.ROWS, F.STRIDE)
        assert len(g) == F.STRIDE, (ch, len(g))
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = g
    #   🔴 **전각 숫자 `０`~`９`(KANJI12)는 원판 그대로 둔다**(마스터 10-27 「ss3 은 원본 그대로 쓰면 될듯」 — 규칙 1-8 라틴·숫자 글꼴 고르기). 종전엔 갈무리에서 뽑아
    #   열 3~9 에 앉혔다(10-06). 대사 숫자는 반각 ASCII 라 `ASCII.FON` 원판이고(`patch_ui_center.DIGIT_BR`), 이 열은 장 제목 · 서책 · 음성 자막의 전각 숫자가 쓴다.
    bake_low(out)
    bake_book(out)
    bake_cred(out)
    bake_label_strips(out, base)
    bake_ellipsis(out)
    bake_liga(out, build_ascii(disc)[0])
    assert len(out) == len(base), (len(out), len(base))
    return bytes(out), missing


#   🔴 반각 부호 새 모양(마스터 11-13 「다 권장으로 하고 캡쳐로 확인하자」) — 원판 **전각** 글리프(`KANJI12`)의 잉크 열만 잘라 6px 칸에 앉힌다(획 모양·행 그대로, 비례 축소 없음).
#   `.` 는 한국식 1px 점(행 9 — 원판 `！` 아래 점과 같은 굵기·높이), `-` 는 1px 가로획(원판에 전각 `－` 가 없다). 행은 전각 그대로라 `ASCII_DY` 를 먹이지 않는다.
#   값 = (전각 글자, 왼쪽 여백 열). 정본 그림: `.local/work/inbox/ss-ed3/glyph-1113/compare.png`.
PUNCT_FW = {"!": ("！", 2), "?": ("？", 0), ":": ("：", 1), ";": ("；", 1), "(": ("（", 2), ")": ("）", 0), "[": ("［", 2), "]": ("］", 0), "'": ("’", 1), "|": ("｜", 2), ",": ("，", 1)}  # fmt: skip


def punct_glyph(kanji, fw, left):
    g = F.unpack(kanji, F.jis_index(fw))
    cols = [c for c in range(F.CELL) if g[:, c].any()]
    seg = g[:, cols[0] : cols[-1] + 1]
    assert left + seg.shape[1] <= F.ASCII_ADV, (fw, left, seg.shape)
    return seg, left


def pack_ascii_rows(rows6):
    out = bytearray()
    for r in rows6:
        out.append(int("".join("1" if x else "0" for x in r) + "00", 2))
    return bytes(out)


def bake_punct(asc, kanji):
    buf = bytearray(asc)
    new = {}
    for ch, (fw, left) in PUNCT_FW.items():
        seg, left = punct_glyph(kanji, fw, left)
        grid = [[0] * 6 for _ in range(F.ASCII_ROWS)]
        dy = 1 if ch == "," else 0  # 쉼표: 머리를 마침표 점(1×1, 행 9)과 같게 — 꼬리(2행)는 그대로 한 행 내려간다
        for r in range(F.ASCII_ROWS - dy):
            for c in range(seg.shape[1]):
                grid[r + dy][left + c] = int(seg[r, c])
        if ch == ",":
            grid[8] = [0] * 6
            grid[9][left + 1] = 0
        new[ch] = grid
    grid = [[0] * 6 for _ in range(F.ASCII_ROWS)]
    grid[9][1] = 1  # 🔴 마침표 = 원판 `？！` 의 점과 같은 1×1(마스터 11-16, 원판 롬 실화면 실측) — 행 9 는 `？` 점과 같은 행(= 한글 세로획 끝 화면 행)
    new["."] = grid
    grid = [[0] * 6 for _ in range(F.ASCII_ROWS)]
    for c in range(4):
        grid[6][c] = 1
    new["-"] = grid
    #   🔴 갈무리 반각 부호(마스터 11-17 「새턴3 은 변경안으로」) — 한 행 내림 · 칸 가운데(+1열) · 점은 `!` 의 점(1×2)과 같게
    gb = fonts.galmuri()
    for ch in "?!":
        bits = gb.bits(ch, dy=-2, rows=F.ASCII_ROWS, width=6)
        new[ch] = [[0] + [int(v) for v in r[:5]] for r in bits]
    dot = [r for r in range(F.ASCII_ROWS) if new["!"][r][2]][-2:]  # `!` 점의 행(10·11)
    g = [[0] * 6 for _ in range(F.ASCII_ROWS)]
    for r in dot:
        g[r][2] = 1
    new["."] = g
    g = [[0] * 6 for _ in range(F.ASCII_ROWS)]
    for r in (dot[0] - 1, dot[0]):  # 쉼표 머리 1×2 — 꼬리를 둘 행이 칸 밑에 없어 한 행 올린다
        g[r][2] = 1
    g[dot[1]][1] = 1
    new[","] = g
    for ch, grid in new.items():
        buf[ord(ch) * F.ASCII_STRIDE : (ord(ch) + 1) * F.ASCII_STRIDE] = pack_ascii_rows(grid)
    return buf


def build_ascii(disc=1):
    """`(새 ASCII.FON bytes, 민 글자 수)` — 여백 조정 + **한글 기준선에 맞춰 2 행 내림**."""
    _, asc = F.load(disc)
    out, n = pad_ascii(asc)
    if ASCII_DY:
        buf = bytearray(out)
        for code in range(0x20, 0x80):
            g = out[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE]
            if not g.strip(b"\x00"):
                continue
            rows = [r for r in range(F.ASCII_ROWS) if F.ascii_unpack(out, code)[r].any()]
            #   ⚠ 아래로 밀다 셀 밖으로 나가면 그 글자는 그대로 둔다(잘리느니 안 맞는 게 낫다)
            if rows and max(rows) + ASCII_DY >= F.ASCII_ROWS:
                continue
            buf[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE] = shift_down(
                g, F.ASCII_ROWS, F.ASCII_STRIDE, ASCII_DY
            )
        out = bytes(buf)
    out = bytes(bake_punct(out, F.load(disc)[0]))
    #   🔴 대사 「」 반각(마스터 도안 B판) — **내리지 않는다**(도안이 전각 「」 와 같은 행 0~10 에 앉는다). 빈 코드 자리라 덮는 게 없다.
    buf = bytearray(out)
    for ch, code in F.KAGI_CODE.items():
        assert not buf[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE].strip(b"\x00"), hex(
            code
        )
        buf[code * F.ASCII_STRIDE : (code + 1) * F.ASCII_STRIDE] = F.kagi_glyph(ch)
    return bytes(buf), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=1, choices=C.DISCS)
    ap.add_argument("--preview", help="이 글자들을 원본 폰트 격자로 그려 본다")
    a = ap.parse_args()

    data, missing = build(a.disc)
    asc, npad = build_ascii(a.disc)
    if a.preview:
        table = H.load()
        rows = [F.unpack(data, table[ch]) for ch in a.preview]
        for r in range(F.ROWS):
            print("  " + "   ".join("".join("█" if v else "·" for v in b[r]) for b in rows))
        return
    os.makedirs(C.OUT_DIR, exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(data)
    with open(OUT_ASCII, "wb") as f:
        f.write(asc)
    print(f"한글 {len(H.load()):,}자 주입 · 크기 {len(data):,}B (불변) → {OUT}")
    print(f"반각 여백 {npad}자({''.join(ASCII_PAD)}) · 크기 {len(asc):,}B (불변) → {OUT_ASCII}")
    if missing:
        print(f"⚠ 글리프가 없는 글자 {len(missing)}: {''.join(missing[:20])}")
        raise SystemExit(1)
    print("✅ 빠진 글자 없음")


if __name__ == "__main__":
    main()
