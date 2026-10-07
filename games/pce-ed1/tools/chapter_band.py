"""장 제목 띠(A6) — 뱅크 0x84 의 1bpp 글리프 스트립을 읽고·그리고·다시 짠다.

🔴 **띠는 그림이 아니다.** 화면의 띠는 BG 타일인데, 타일마다 **plane0 = 0xff(채운 상자)**
이고 **글자는 plane1 에만** 있다. 즉 게임이 1bpp 글리프를 상자에 OR 해 넣는다 —
그래서 디스크에는 **4bpp 그림이 아니라 1bpp 비트맵**이 무압축으로 들어 있다.
(이 전제를 4bpp·압축·스프라이트로 잡아 세 번 헛짚었다 — devlog 09-15 (14).)

## 자리와 구조 (실측, 2026-09-15)

데이터 트랙 **rel 210~213 = 뱅크 `0x84`**(8,192B). 디스크와 RAM 이 **오프셋까지 바이트 동일**
이라 압축·변형이 없다. 뱅크는 논리 `$A000` 에 매핑된다(디렉터리 포인터가 그 값이다).

    +0x000  디렉터리 6개 × 8B   {src(LE,논리), 타일수(LE), bat(LE,논리), 0}
    +0x030  글리프 스트림       1bpp, **타일 하나 = 8B**(8×8, 행당 1B, MSB 왼쪽)
    +0x608  BAT 표 6개 × 44B    2행 × 22칸, **타일 번호 하위 바이트**만
    +0x710  0 으로 빈 칸 (~0x800)

BAT 칸 값 `v` → 스트립 안의 타일 번호 `v - 0xB0`(전 장 공통, VRAM 은 `0x1B0` 부터 올린다).
빈칸도 그 규칙을 그대로 따른다 — **빈 타일을 생략하지 않는다**(타일 24개를 실측해
`off = src + (v-0xB0)*8` 이 **어긋남 0**으로 맞았다).

⚠ 장마다 **행 길이가 다르다**(15·14·14·16·15·?타일). 게다가 같은 장 안에서도 위/아래 행의
실제 타일 수가 하나 어긋나는 데가 있다 — 제목 안의 빈칸이 **어떤 행에서는 스트립 타일을
쓰고 어떤 행에서는 이미 올라간 빈 타일을 가리키기** 때문이다. 그래서 **행 길이를 상수로
두지 않고 BAT 표를 정본으로 읽는다.**
"""

import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

from shared import fonts

BANK_REL = range(210, 214)  # 뱅크 0x84 = 데이터 트랙 rel 210~213
LOGICAL = 0xA000  # 이 뱅크가 매핑되는 논리 주소
DIR_OFF = 0x000
NCHAP = 6
BAT_COLS = 22  # BAT 표 한 행의 칸 수
BAT_ROWS = 2
TILE = 8  # 1bpp 타일 하나 = 8바이트(8×8)
BASE_TILE = 0xB0  # BAT 칸 값의 기준 (VRAM 0x1B0)
PITCH = 12  # 글자 한 칸 = 12px (원문 실측)
INK_TOP = 2  # 잉크 시작 행 (16px 띠 안에서, 원문 실측 2~13행 = 12행)


def bank_bytes(img=None):
    """뱅크 0x84 원본 8,192B."""
    img = img if img is not None else common.iso_bytes()

    def sect(s):
        b = s * common.RAW + common.USER_OFF
        return img[b : b + common.USER]

    return b"".join(sect(common.T2_SECTOR + r) for r in BANK_REL)


def directory(bank):
    """[(src_off, tiles, bat_off)] × 6 — 논리 주소를 뱅크 오프셋으로 바꿔 돌려준다."""
    out = []
    for i in range(NCHAP):
        src, cnt, bat, _z = struct.unpack_from("<HHHH", bank, DIR_OFF + i * 8)
        out.append((src - LOGICAL, cnt, bat - LOGICAL))
    return out


def bat_cells(bank, bat_off):
    """BAT 표 → (2, 22) 타일 번호(스트립 인덱스). 빈칸도 인덱스로 나온다."""
    raw = bank[bat_off : bat_off + BAT_ROWS * BAT_COLS]
    return np.frombuffer(raw, dtype=np.uint8).reshape(BAT_ROWS, BAT_COLS).astype(int) - BASE_TILE


def render(bank, chapter):
    """장 하나를 (16, 176) 0/1 비트맵으로 — BAT 표가 정본이다."""
    src, cnt, bat = directory(bank)[chapter]
    cells = bat_cells(bank, bat)
    img = np.zeros((BAT_ROWS * TILE, BAT_COLS * TILE), dtype=np.uint8)
    for r in range(BAT_ROWS):
        for c in range(BAT_COLS):
            idx = cells[r, c]
            if not 0 <= idx < cnt:
                continue
            tile = bank[src + idx * TILE : src + idx * TILE + TILE]
            for y, v in enumerate(tile):
                for x in range(8):
                    img[r * TILE + y, c * TILE + x] = (v >> (7 - x)) & 1
    return img


def ink_box(bits):
    """잉크 경계 (x0, x1, y0, y1) — 없으면 None."""
    ys, xs = np.nonzero(bits)
    if not len(xs):
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def typeset(text, font=None, pitch=PITCH, top=INK_TOP, height=BAT_ROWS * TILE, space_px=None):
    """한글 문안 → (height, 폭) 0/1. **글자는 전각 고정폭, 공백만 폭을 고를 수 있다.**

    ⚠ 전각 고정폭인 이유는 원문이 그렇기 때문이다 — 원문 평균 피치가 11.8~12.4px 로
    **12px 격자**이고(여섯 장 실측), 마스터 확정대로 **장 번호도 전각**이다.

    `space_px` 로 공백 폭을 정한다 — `None`이면 원문과 같은 전각(=pitch), 정수면 그 폭,
    리스트면 **공백마다** 따로(예: 장 번호 뒤만 전각, 낱말 사이는 반각). 원문의 공백은
    전각 하나다(글자 사이 빈틈 14px = 12 + 양쪽 여백, 실측).

    🔴 **글리프는 「잉크」 기준으로 칸 가운데에 놓는다.** BDF 박스 기준으로 놓으면
    갈무리11 의 전각 숫자가 칸 왼쪽에 붙는다 — 「１」의 잉크는 폭 2px 인데 박스 안
    3열째에서 시작해 **왼 3 / 오 7** 로 치우쳤다(실측). 같은 함정을 오늘 sfc-ed1 이
    밟았다(숫자 폭만 넓히고 정렬을 안 봐 왼쪽에 붙었다). **폭을 바꿨으면 정렬도 다시 본다.**
    """
    font = font or fonts.galmuri("Galmuri11")
    spaces = [i for i, c in enumerate(text) if c == " "]
    if space_px is None:
        widths = {i: pitch for i in spaces}
    elif isinstance(space_px, int):
        widths = {i: space_px for i in spaces}
    else:
        widths = {i: space_px[min(k, len(space_px) - 1)] for k, i in enumerate(spaces)}

    total = sum(widths.get(i, pitch) for i in range(len(text)))
    out = np.zeros((height, max(total, 1)), dtype=np.uint8)
    pen = 0
    for i, ch in enumerate(text):
        adv = widths.get(i, pitch)
        if ch != " ":
            # ⚠ dy 는 fonts.GALMURI11_DY(-3) 다 — 0 으로 두면 글리프가 3행 내려가 아랫줄이
            #    잘린다(획이 끊겨 「왕」이 「왁」처럼 보인다, 실측 2026-09-15).
            g = font.bits(ch, dy=fonts.GALMURI11_DY, rows=fonts.ROWS, width=fonts.WIDTH)
            xs = np.nonzero(g)[1]
            if len(xs):
                x0, x1 = int(xs.min()), int(xs.max())
                ox = pen + (adv - (x1 - x0 + 1)) // 2 - x0  # 잉크를 칸 가운데로
                for y in range(fonts.ROWS):
                    if not 0 <= top + y < height:
                        continue
                    for x in range(x0, x1 + 1):
                        if g[y, x] and 0 <= ox + x < out.shape[1]:
                            out[top + y, ox + x] = 1
        pen += adv
    return out


def tiles_needed(width_px):
    """가로 픽셀 폭 → 스트립 타일 수(2행). 8px 타일이라 올림한다."""
    return ((width_px + TILE - 1) // TILE) * BAT_ROWS


# ── 재삽입 ────────────────────────────────────────────────────────────────────
#
# 마스터 확정(2026-09-15): **갈무리11 · 공백은 혼합**(장 번호 뒤 전각 · 낱말 사이 반각).
# 문안은 이미 승인된 D2 장 카드 것을 그대로 쓴다(`script/scn*.json`) — 두 자리가 갈리면
# 안 되니 여기서 새로 짓지 않는다.
def _kr_titles():
    """장 제목 여섯 — 낱말은 정본 `chapter`(마스터 10-08: 모든 장 제목 정본)에서 읽고 「제N장」 머리만 여기서 붙인다."""
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "shared"))
    import canon

    jp_kr = list(canon.table("chapter", "ed1").values())
    nums = "１２３４５"
    return tuple(
        (f"제{nums[i]}장 " if i < 5 else "종장 ") + kr for i, kr in enumerate(jp_kr)
    )


KR_TITLES = _kr_titles()
SPACE_PX = [12, 6]  # 첫 공백(장 번호 뒤) 전각, 나머지 반각
STREAM_OFF = 0x030  # 글리프 스트림이 시작하는 자리(디렉터리 바로 뒤)
STREAM_END = 0x608  # 첫 BAT 표 자리 = 스트림이 넘으면 안 되는 선
SECTOR_REL = 210  # 띠 자산은 이 **한 섹터**가 전부다


def pack_chapter(text, space_px=SPACE_PX):
    """문안 → (타일 목록, BAT 2×22). **같은 타일은 하나로 합친다.**

    🔑 중복 제거는 우리가 지어낸 수가 아니라 **원문이 이미 쓰는 기법**이다 — 원문 BAT 는
    제목 속 빈칸과 좌우 여백을 **빈 타일 하나**(`0xB5`)로 돌려 쓴다. 덕분에 혼합 간격이
    194 → 182 타일로 줄어 **표 앞 공간에 그대로 들어간다**(꼬리 240B 를 안 건드린다).
    """
    bits = typeset(text, space_px=space_px)
    w = bits.shape[1]
    n = (w + TILE - 1) // TILE  # 한 행의 타일 수
    pad = np.zeros((BAT_ROWS * TILE, n * TILE), dtype=np.uint8)
    pad[:, :w] = bits

    uniq, index, rows = [], {}, []
    for r in range(BAT_ROWS):
        row = []
        for t in range(n):
            blk = pad[r * TILE : (r + 1) * TILE, t * TILE : (t + 1) * TILE]
            raw = np.packbits(blk, axis=1)[:, 0].tobytes()
            if raw not in index:
                index[raw] = len(uniq)
                uniq.append(raw)
            row.append(index[raw])
        rows.append(row)

    blank = bytes(TILE)
    if blank not in index:  # 여백 칸이 가리킬 빈 타일이 없으면 하나 만든다
        index[blank] = len(uniq)
        uniq.append(blank)
    bidx = index[blank]

    lead = max(0, (BAT_COLS - n) // 2)  # 22칸 안에서 가운데 (원문과 같은 방식)
    bat = np.full((BAT_ROWS, BAT_COLS), bidx, dtype=int)
    for r in range(BAT_ROWS):
        for t in range(min(n, BAT_COLS - lead)):
            bat[r, lead + t] = rows[r][t]
    return uniq, bat


def build_sector(orig):
    """원본 섹터(2048B) → 한글판 섹터(2048B).

    ⚠ **BAT 표는 원래 자리에 그대로 둔다**(크기도 같다) — 디렉터리가 포인터를 들고 있지만
    코드가 그 포인터를 정말 읽는지까지는 값으로 못 봤다. 안 옮겨도 되는 이유가 있으니
    (중복 제거로 스트림이 표 앞에 다 들어간다) **안 옮긴다.**
    ⚠ **꼬리(0x710~0x7FF)는 손대지 않는다** — 원본 그대로 0 으로 남긴다.
    """
    assert len(orig) == common.USER, f"섹터가 {len(orig)}B"
    out = bytearray(orig)
    dirs = directory(bytes(orig))

    streams, bats, off = [], [], STREAM_OFF
    for i, text in enumerate(KR_TITLES):
        uniq, bat = pack_chapter(text)
        streams.append((off, uniq))
        bats.append((dirs[i][2], bat))
        off += len(uniq) * TILE
    if off > STREAM_END:
        raise ValueError(f"글리프 스트림이 BAT 표를 침범한다: {off:#06x} > {STREAM_END:#06x}")

    out[STREAM_OFF:STREAM_END] = bytes(STREAM_END - STREAM_OFF)  # 스트림 칸을 비우고 다시 깐다
    for i, ((soff, uniq), (boff, bat)) in enumerate(zip(streams, bats, strict=True)):
        for k, t in enumerate(uniq):
            out[soff + k * TILE : soff + (k + 1) * TILE] = t
        struct.pack_into("<HHHH", out, DIR_OFF + i * 8, LOGICAL + soff, len(uniq), LOGICAL + boff, 0)
        cells = (bat + BASE_TILE).astype(np.uint8).tobytes()
        out[boff : boff + len(cells)] = cells

    assert out[0x710:] == orig[0x710:], "꼬리를 건드렸다"
    return bytes(out)


def apply(f, touched):
    """ISO 에 제자리 되쓰기. `build.py` 가 부른다."""
    from shared.disc import mode1

    orig = common.track_data(SECTOR_REL, 1)
    data = build_sector(orig)
    lba = common.T2_SECTOR + SECTOR_REL
    mode1.write_user_data(f, lba, data, label=f"chapter band rel {SECTOR_REL}", expect=orig)
    touched.append((lba, 1))
    moved = sum(1 for a, b in zip(data, orig, strict=True) if a != b)
    used = struct.unpack_from("<H", data, DIR_OFF + 5 * 8)[0] - LOGICAL
    used += struct.unpack_from("<H", data, DIR_OFF + 5 * 8 + 2)[0] * TILE
    return f"장 제목 띠 rel {SECTOR_REL}: 6장 · 스트림 끝 {used:#06x} · 바뀐 바이트 {moved}/{len(orig)}"


def to_png(rows, path, scale=3, gap=4):
    """(이름, 비트맵) 목록을 세로로 쌓아 PNG 로. 원문·후보를 나란히 보여 줄 때 쓴다."""
    w = max(b.shape[1] for _n, b in rows)
    h = sum(b.shape[0] + gap for _n, b in rows)
    sheet = Image.new("L", (w, h), 0)
    y = 0
    for _name, b in rows:
        im = Image.fromarray((b * 255).astype(np.uint8), "L")
        sheet.paste(im, (0, y))
        y += b.shape[0] + gap
    sheet.resize((w * scale, h * scale), Image.NEAREST).save(path)
    return path


if __name__ == "__main__":
    bank = bank_bytes()
    print("장 | src    | 타일 | bytes | bat    | 잉크폭 | 칸수(12px)")
    for i, (src, cnt, bat) in enumerate(directory(bank)):
        box = ink_box(render(bank, i))
        w = (box[1] - box[0] + 1) if box else 0
        print(
            f" {i + 1} | {src:#06x} | {cnt:4d} | {cnt * TILE:5d} | {bat:#06x} |"
            f" {w:5d}px | {w / PITCH:5.1f}"
        )
