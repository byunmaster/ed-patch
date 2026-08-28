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
DY = -2  # 🔴 **한 줄 내린다** — 원본은 0~10 행인데 우리는 1~11 행에 앉힌다.
#   창이 **첫 줄의 0 행을 자른다**(유저가 스탯 창에서 짚었다 2026-08-27). 원본도 같이
#   잘리지만 티가 안 난다 — `攻` 의 0 행은 **1 픽셀**인데 `공` 의 0 행은 **9 픽셀**(ㄱ 의
#   가로획)이라 통째로 날아간다. 한글은 초성 ㄱ·ㅁ·ㅂ·ㅍ·ㅈ 이 죄다 윗변이 가로획이라
#   손해가 원본과 비교가 안 된다.
#   ⚠ 11 행은 **원본 글자 146 개가 이미 쓰는 자리**라 아래가 잘리지 않는다(실측).
#   ⚠ 대신 문장부호(`。`·`・`)와 숫자는 원본 자리 그대로라 한글만 1 픽셀 내려앉는다 —
#     실기로 보고 어색하면 되돌린다(이 상수 하나다).
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
    assert len(out) == len(base), (len(out), len(base))
    return bytes(out), missing


def build_ascii(disc=1):
    """`(새 ASCII.FON bytes, 민 글자 수)`."""
    _, asc = F.load(disc)
    return pad_ascii(asc)


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
