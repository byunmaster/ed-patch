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
ASCII_DY = 1

#   🔴 **숫자는 반각으로 써도 전각 글리프로 그려진다**(실측 2026-09-01). 대사창에 반각
#     `1`(0x31)을 넣었는데 화면엔 `KANJI12` 의 전각 `１`(SJIS 0x8250)이 12px 칸을 먹고 나왔다
#     — 렌더러가 ASCII 숫자를 전각 자리로 옮겨 그린다. 그래서 `ASCII_DY` 는 숫자에 안 닿는다.
#   ⇒ 전각 숫자 열을 따로 내린다. 원본은 **행 0~9**(가나 1~9 · 한자 0~10)라 한글(1~11)보다
#     한 행 높고 두 행 짧아, 「１０피아」가 한글보다 떠 보였다(유저 지적 2026-09-01).
#     아래 두 행이 비어 있으니 **2 행 내려 2~11 행**에 앉히면 한글과 밑이 맞는다.
#   ⚠ HUD 의 `70 Pia / 0 Goa` 는 게임이 자기 `ASCII.FON` 으로 직접 그린다(실측: 행 3~11 =
#     `ASCII_DY` 가 먹은 자리) — 여기 안 걸린다.
DIGIT_DY = 1
FULLWIDTH_DIGITS = tuple(range(0x824F, 0x8259))  # ０~９


def digit_slots():
    """전각 숫자 열의 글리프 색인 — `font.sjis_of_index` 의 역을 훑어서 찾는다."""
    want = {v.to_bytes(2, "big") for v in FULLWIDTH_DIGITS}
    out = [i for i in range(F.GLYPHS) if F.sjis_of_index(i) in want]
    assert len(out) == 10, out
    return out


def shift_down12(g, dy):
    """`KANJI12` 글리프(12행 × 12비트 밀착)를 아래로 `dy` 행 민다."""
    grid = np.zeros((F.ROWS, F.CELL), dtype=np.uint8)
    src = F.unpack(g + bytes(F.STRIDE), 0)
    grid[dy:] = src[: F.ROWS - dy]
    return F.pack18(grid)


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
    for idx in digit_slots():
        out[idx * F.STRIDE : (idx + 1) * F.STRIDE] = shift_down12(
            bytes(out[idx * F.STRIDE : (idx + 1) * F.STRIDE]), DIGIT_DY
        )
    bake_low(out)
    bake_label_strips(out, base)
    assert len(out) == len(base), (len(out), len(base))
    return bytes(out), missing


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
    return out, n


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
