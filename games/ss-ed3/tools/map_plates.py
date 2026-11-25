"""맵 선택 화면(디버그 메뉴 「맵 선택」)의 **지명판 34장** — `/SYSTEM/SLMAPDAT.BIN` 끝에 구워진 그림이다.

    python3 games/ss-ed3/tools/map_plates.py --preview OUT.png     # 원판 판 ↔ 한글 판 나란히(2배)
    python3 games/ss-ed3/tools/map_plates.py --check               # 원판 판 ↔ 원문 이름 대조

🔴 **지명은 글자가 아니라 그림이다**(10-24 실측) — `SELPRG.BIN`·`SLMAPDAT.BIN` 어디에도 문자열이 없고, 전역 글리프 함수는 이 화면에서 전각 공백만 그린다.
   그림은 파일 끝 `0xD4DC~` 에 **80×16 · 4bpp · 무압축**(행당 40B)으로 34장이 이어 붙어 있고 팔레트(RGB555 16색)는 `0xD4BC` 다.
   그래서 폰트를 고쳐도 안 바뀐다 — 판 그림을 다시 그린다. **파일 길이·위치 불변.**

## 판의 구조(실측)
  · 바깥 둘레 행 0·1·14·15 와 열 0·1·78·79 는 테두리다 — 건드리지 않는다.
  · 안쪽(행 2~13)은 **잔 무늬가 낀 바탕**(색인 6~15 — 어두운 청회색 계조)이고 글자는 **밝은 회색 색인 1~5**(1 흰 · 2 밝은 · 5 중간 · 3·4 가장자리)로 얹혀 있다(획 1px).
  · 원판 글자는 **양끝 맞춤**이다 — 첫 글자 칸 왼쪽이 열 4, 끝 글자 칸 왼쪽이 열 65 로 고정이고 가운데 글자가 그 사이를 균등 분할한다
    (두 자 「遺跡」는 양끝, 여섯 자 「ラグピック村」는 12px 간격으로 빽빽하다). 잉크 행은 3~13.

## 한글 판
  · 한글은 원판처럼 양끝 맞춤이되 **간격 상한 22**(`KR_MAX_PITCH`) — 두세 자 이름이 60px 벌어지지 않게 가운데로 모은다(마스터 미리보기 판정 대상).
  · 문안은 **정본**(`shared/canon/nouns/ed3.json` 의 `place`)에서 읽는다 — 이 파일엔 원문 열쇠 목록(`ORDER`)뿐이다(자기 표 0).
  · 지명판도 **띄어 쓴다**(마스터 10-29 — 10-09 「원판처럼 붙여 쓴다」를 대체. 「일본어 원문은 원래 띄어쓰기가 없어 한국어로는 띄어 쓰는 게 맞다」) — 정본 값 그대로,
    공백은 글자 반 칸 너비의 틈이다(`SPACE_W`).
  · 글꼴은 **Galmuri11**(갈무리 계열 — 인게임 대사·장 끝 지명과 같은 격자, 한글 12px 칸 `DX=1`)이다.
  · 글자 바탕은 **그 판의 바탕 무늬를 되살려** 원문 획만 걷어 낸다(획 칸을 같은 행의 이웃 바탕 색으로 메운다).
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import font as F

sys.path.insert(0, os.path.join(C.ROOT, "shared"))
import canon as CN

from shared import fonts

PATH = "/SYSTEM/SLMAPDAT.BIN"
PAL_AT = 0xD4BC
IMG_AT = 0xD4DC
W, H = 80, 16
ROW_B = W // 2
PLATE_B = ROW_B * H
N = 34
INK = (1, 2, 3, 4, 5)  # 글자 색인 — 팔레트 1~5 는 밝은 회색(획·가장자리), 바탕은 6~15 의 어두운 청회색
TEXT_ROWS = (2, 14)  # 안쪽 행 [2, 14)
TEXT_COLS = (2, 78)
CELL_TOP = 3  # 글리프 칸 윗줄 = 판 행 3 (원판 잉크 3~13)
CELL_LEFT_FIRST, CELL_LEFT_LAST = 4, 65
DX = 1  # 인게임 한글 칸과 같은 한 열 들여쓰기(`build_font.DX`)
DY = -3
INK_FILL = 1  # 한글 획 색인(원판의 밝은 획)
SPACE_W = 0.5  # 띄어쓰기 틈 — 글자 한 칸의 절반(마스터 10-29 지명판도 띄어 쓴다)
KR_MAX_PITCH = 22  # 한글 판의 글자 간격 상한 — 원판 네 자 판(`ラグーナ` 등)의 간격이 20 이다

#   판 순서의 원문 이름 — **열쇠 목록**이다(값은 정본). 판을 한 장씩 읽어 적었고 `--check` 가 원판 잉크와 대조한다.
ORDER = (
    "ラグピック村", "緑の高原", "ディーネ", "ラグーナ", "ニーリ", "アルデ", "テグラ", "チッタ", "ネルバ城",
    "テュエール", "双竜谷の関所", "ダイス", "ダーツ", "三都橋", "ボルト", "イグニス", "アンデラ", "静寂の森",
    "シフール", "北ヒーツ街道", "オルドス", "ハイゼン", "ルイズの関所", "ホルク", "ホルクの砦", "望砂の関所",
    "バラカ", "遺跡", "乾きの砂漠", "ギドネル", "ディルトの関所", "アロザ", "ドルフェス", "ルード",
)  # fmt: skip
assert len(ORDER) == N


def korean(jp):
    """정본 `place` 값 그대로(공백 포함) — 없으면 `None`(후보로 올린다)."""
    v = CN.nouns("ed3")["categories"]["place"].get(jp)
    return v if isinstance(v, str) else None


def read(data):
    """`(팔레트 [(r,g,b)], 판 N 장 — 각 (16, 80) 색인 배열)`."""
    pal = []
    for i in range(16):
        w = int.from_bytes(data[PAL_AT + 2 * i : PAL_AT + 2 * i + 2], "big")
        pal.append(((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8))
    plates = []
    for k in range(N):
        raw = np.frombuffer(data[IMG_AT + k * PLATE_B : IMG_AT + (k + 1) * PLATE_B], dtype=np.uint8)
        a = np.empty((H, W), np.uint8)
        r = raw.reshape(H, ROW_B)
        a[:, 0::2], a[:, 1::2] = r >> 4, r & 15
        plates.append(a)
    return pal, plates


def write(data, plates):
    out = bytearray(data)
    for k, a in enumerate(plates):
        r = ((a[:, 0::2] << 4) | a[:, 1::2]).astype(np.uint8)
        out[IMG_AT + k * PLATE_B : IMG_AT + (k + 1) * PLATE_B] = r.tobytes()
    return bytes(out)


def layout(n, max_pitch=None):
    """글자 칸 왼쪽 열 `n` 개 — 양끝 맞춤. `max_pitch` 를 주면 간격이 그 이상 벌어지지 않게 **가운데로 모은다**(한글 두 자가 60px 벌어지면 낱말로 안 읽힌다)."""
    if n == 1:
        return [(CELL_LEFT_FIRST + CELL_LEFT_LAST) // 2]
    span = CELL_LEFT_LAST - CELL_LEFT_FIRST
    pitch = span / (n - 1)
    if max_pitch is not None and pitch > max_pitch:
        pitch = max_pitch
    first = CELL_LEFT_FIRST + (span - pitch * (n - 1)) / 2
    return [round(first + i * pitch) for i in range(n)]


def layout_text(text, max_pitch=None):
    """`text` 의 글자(공백 제외)마다 칸 왼쪽 열 — 양끝 맞춤이되 공백은 `SPACE_W` 칸 틈으로 센다."""
    glyphs = [c for c in text]
    w = [SPACE_W if c == " " else 1.0 for c in glyphs]
    units = sum(w[:-1])
    if units == 0:
        return {i: (CELL_LEFT_FIRST + CELL_LEFT_LAST) // 2 for i, c in enumerate(glyphs) if c != " "}
    span = CELL_LEFT_LAST - CELL_LEFT_FIRST
    pitch = span / units
    if max_pitch is not None and pitch > max_pitch:
        pitch = max_pitch
    first = CELL_LEFT_FIRST + (span - pitch * units) / 2
    out, cum = {}, 0.0
    for i, c in enumerate(glyphs):
        if c != " ":
            out[i] = round(first + pitch * cum)
        cum += w[i]
    return out


def _inner(a):
    m = np.zeros(a.shape, bool)
    m[TEXT_ROWS[0] : TEXT_ROWS[1], TEXT_COLS[0] : TEXT_COLS[1]] = True
    return m


def ink_mask(a):
    return np.isin(a, INK) & _inner(a)


def clean(a):
    """원문 획을 걷어 바탕만 남긴다 — 획 칸을 **같은 행의 가장 가까운 바탕 칸** 색으로(왼쪽 우선) 메운다."""
    b = a.copy()
    ink = ink_mask(a)
    for y in range(H):
        xs = np.where(ink[y])[0]
        if not len(xs):
            continue
        ok = np.where(~ink[y] & _inner(a)[y])[0]
        for x in xs:
            d = np.abs(ok - x)
            # 같은 거리면 왼쪽 — 결과가 결정적이어야 한다
            j = ok[np.lexsort((ok, d))[0]]
            b[y, x] = a[y, j]
    return b


def render_kr(a, text):
    """원판 판 `a` 의 바탕 위에 `text` 를 양끝 맞춤으로 그린다."""
    b = clean(a)
    bdf = fonts.galmuri()
    for i, x0 in layout_text(text, KR_MAX_PITCH).items():
        ch = text[i]
        bits = bdf.bits(ch, dy=DY, rows=F.ROWS, width=F.CELL)
        for y in range(F.ROWS):
            for x in range(F.CELL - DX):
                if bits[y, x]:
                    px, py = x0 + DX + x, CELL_TOP + y
                    if TEXT_COLS[0] <= px < TEXT_COLS[1] and TEXT_ROWS[0] <= py < TEXT_ROWS[1]:
                        b[py, px] = INK_FILL
    return b


def table():
    """`[(원문, 한글 또는 None)]` — 판 순서."""
    return [(jp, korean(jp)) for jp in ORDER]


def patch(data, tbl=None):
    """`/SYSTEM/SLMAPDAT.BIN` → `(새 bytes, 바꾼 판 수)`. **길이 불변.** 정본에 없는 이름이 있으면 멈춘다."""
    tbl = tbl or table()
    #   🔴 정본에 없는 이름을 조용히 일본어로 두지 않는다 — 판이 화면에 그대로 뜬다(블록 탈락과 같은 부류의 사고).
    miss = [jp for jp, kr in tbl if not kr]
    assert not miss, f"지명판 정본에 없는 이름 {miss} — 관리자에게 후보로"
    _, plates = read(data)
    n = 0
    for k, (_jp, kr) in enumerate(tbl):
        plates[k] = render_kr(plates[k], kr)
        n += 1
    new = write(data, plates)
    assert len(new) == len(data)
    return new, n


def check(data):
    """원판 판의 잉크가 **원문 이름을 양끝 맞춤으로 그린 것**과 겹치나 — `[(번호, 이름, 겹침 비율)]`.

    원문 글리프는 원판 폰트(`KANJI12.FON`)에서 뽑는다. 판 순서·이름 목록이 틀리면 비율이 떨어진다.
    """
    with C.open_disc(1) as d:
        fs = {n: (lba, size) for n, lba, size in d.files()}
        fon = d.read_extent(*fs["/SYSTEM/KANJI12.FON"])
    _, plates = read(data)
    out = []
    for k, jp in enumerate(ORDER):
        m = np.zeros((H, W), bool)
        for ch, x0 in zip(jp, layout(len(jp)), strict=True):
            g = F.unpack(fon, F.jis_index(ch)).astype(bool)
            for y in range(F.ROWS):
                for x in range(F.CELL):
                    if g[y, x] and CELL_TOP + y < H and x0 + x < W:
                        m[CELL_TOP + y, x0 + x] = True
        ink = ink_mask(plates[k])
        # 한 칸 어긋남을 봐 준다 — 원판 글리프가 칸 안에서 한 열쯤 흔들린다
        grown = m.copy()
        for dx in (-1, 1):
            grown |= np.roll(m, dx, 1)
        out.append((k, jp, float((ink & grown).sum() / max(1, ink.sum()))))
    return out


def preview(data, new, path):
    """원판 판(왼쪽) ↔ 한글 판(오른쪽) — 2배 확대, 두 열."""
    from PIL import Image

    pal, old = read(data)
    _, nw = read(new)
    S, GAP = 2, 10
    cols = 2
    rows = (N + cols - 1) // cols
    cw = 2 * W * S + GAP * 2
    im = Image.new("RGB", (cols * cw, rows * (H * S + 4)), (24, 24, 24))
    for k in range(N):
        c, r = divmod(k, rows)
        for j, plate in enumerate((old[k], nw[k])):
            t = Image.new("RGB", (W, H))
            t.putdata([pal[v] for v in plate.flatten()])
            im.paste(t.resize((W * S, H * S), Image.NEAREST), (c * cw + j * (W * S + GAP), r * (H * S + 4)))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    with C.open_disc(1) as d:
        fs = {n: (lba, size) for n, lba, size in d.files()}
        data = d.read_extent(*fs[PATH])
    if a.check:
        res = check(data)
        for k, jp, r in res:
            print(f"{k:2d} {jp:8s} {r:.2f}")
        print("최저", min(r for *_x, r in res))
    miss = [jp for jp, kr in table() if not kr]
    if miss:
        print(f"정본에 없음 {miss}")
        raise SystemExit(1)
    new, n = patch(data)
    print(f"한글 판 {n}/{N}")
    if a.preview:
        preview(data, new, a.preview)
        print(a.preview)


if __name__ == "__main__":
    main()
