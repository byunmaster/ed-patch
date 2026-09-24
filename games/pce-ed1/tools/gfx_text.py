"""엔딩·오마케의 **그림 글자** — 압축 타일 스트림을 풀어 글자 칸만 갈고 다시 싼다.

    python3 tools/gfx_text.py            # 미리보기 PNG → work/review/gfx_text_*.png + 크기 보고

| 자리 | 원문 | 한글 | 글꼴 | 마스터 확정 |
| ---- | ---- | ---- | ---- | ----------- |
| 엔딩 끝 카드(rel 898) | 英雄たちの伝説 / 制作・著作 | 영웅들의 전설 / 제작·저작 | 네오둥근모 16 | 2026-09-24 |
| 오마케 간판(rel 706) | どらごんすれいや〜一座 | 드래곤슬레이어 극단 | Galmuri9 | 2026-09-24 |
| 오마케 끝(rel 706) | おしまい | 끝 | 그림(`assets/graphics/kkeut.txt`) | 마스터 목업 09-23 |

어디 있나(2026-09-24 에뮬 실측, devlog 09-24 (4)):
- 두 모듈 다 같은 그래픽 로더를 쓴다 — 스트림 앞 1B 가 **모드**(0 그대로 · 1 면 재배열 ·
  2 행 XOR · 3 합산), 뒤는 `lz.py` 와 같은 LZ(헤더 없음, 링 0 에서 시작, 쓰기 자리 0xEF).
  호출은 인라인 인자(`JSR $4A10`/`$4953` + src·뱅크·VRAM·개수·마스크) 또는 **객체 표**(카드가
  그렇다 — $305B 목적지 · $31A3 개수 · $31F5 마스크)라, 인라인 호출만 훑으면 카드가 안 보인다.
  스트림 위치 = (뱅크 인자 & 0x1F)×0x2000 + 주소 인자 + 1.
- 면 재배열(모드 1): 스트림 32B = 면0 8행 · 면1 8행 · 면2 8행 · 면3 8행 →
  VRAM 은 행마다 (면0,면1) 워드 8개 + (면2,면3) 워드 8개.
- 카드: 모듈 +0x37C98, 타일 0x300 부터 **128장**(객체 호출 `JSR $4ADE` @+0x535F 의 개수 인자 0x80).
  🔴 처음엔 VRAM 과 「512장이 이어서 맞는다」 보고 512장을 다시 쌌다 — 그런데 +0x38254 부터는 **다른
  호출(`JSR $4BFF` @+0x53D4)의 스트림**이라, 그 자리를 덮어 카드 직전에 CPU 가 폭주했다(2026-09-24 에뮬).
  장수는 VRAM 대조가 아니라 **호출 인자**에서 읽는다.
  BAT — 제목 14칸 위 0x302~ · 아래 0x312~, 제작 10칸 위 0x320~ · 아래 0x330~. 팔레트 0 —
  1 회색($124) · 2 흰색($1FF) · 3 짙은 회색($092).
- 간판: 모듈 +0x162F8, 타일 0x700 부터 128장(전부 일치). 글자 띠 = 타일 0x720~0x72F(위) ·
  0x730~0x73F(아래), 팔레트 10. 글자 자리는 3~11행 · 3~124열, 배경은 행마다 한 색(노란 그러데이션).
  글자 = 11(초록 $0C1). 원본의 계단 보정(12 $151 · 카드의 회색 두 단)은 **안 흉내 낸다** —
  오목한 모서리를 채웠더니 둥근 ㅇ 이 네모가 되어 「이」가 「미」로 읽혔다(2026-09-24 미리보기).
- 끝: 타일 = 모듈 +0x184A6(모드 2 행 XOR), 0x100 부터 160장 · 배치 = +0x19AD4(모드 0), 32×32 워드를
  BAT 에 그대로(`JSR $4B48` 인라인). 「おしまい」 는 BAT 5~15행 · 4~27열, 타일 0x101~0x198, 팔레트 0
  (15 흰색 · 11 푸른 회색 테두리). 옛 글자 타일은 이 자리 말고 안 쓰인다(배치 전수) — 비우고 새로 깐다.
🔴 **원래 자리를 넘지 않는다** — 재부호화 크기를 원본 스트림 길이와 비교해 넘으면 빌드가 죽는다
  (넘으면 옮길 자리와 포인터가 필요하다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import lz

REPO = Path(__file__).resolve().parents[3]
NEODGM = REPO / "shared" / "fonts" / "neodgm.ttf"
GALMURI9 = REPO / "shared" / "fonts" / "Galmuri9.bdf"


# ── 스트림 ─────────────────────────────────────────────────────────────────
class Stream:
    def __init__(self, name, rel, sectors, off, n_tiles, tile0, mode=1):
        self.name, self.rel, self.sectors, self.off = name, rel, sectors, off
        self.n_tiles, self.tile0, self.mode = n_tiles, tile0, mode

    def module(self) -> bytes:
        return common.track_data(self.rel, self.sectors)

    def original(self) -> tuple[bytearray, int]:
        """(VRAM 순서 타일, 원본 스트림 길이)."""
        m = self.module()
        mb = m[self.off - 1]
        assert mb == self.mode, f"{self.name}: 모드 바이트 {mb:#x} ≠ {self.mode}"
        raw, used = lz.decode(m[self.off :], self.n_tiles * 32, with_header=False)
        return bytearray(DECODE[self.mode](raw)), used

    def tile(self, vram, t) -> bytes:
        return bytes(vram[(t - self.tile0) * 32 :][:32])

    def put(self, vram, t, b: bytes) -> None:
        vram[(t - self.tile0) * 32 : (t - self.tile0) * 32 + 32] = b

    def encode(self, vram) -> bytes:
        new = lz.encode(ENCODE[self.mode](bytes(vram)), with_header=False)
        back, _ = lz.decode(new, self.n_tiles * 32, with_header=False)
        assert DECODE[self.mode](back) == bytes(vram), f"{self.name}: 재부호화 왕복 불일치"
        return new

    def apply(self, f, touched, new: bytes, used: int) -> str:
        from shared.disc import mode1

        assert len(new) <= used, f"{self.name}: 원래 자리({used}B)를 넘는다: {len(new)}B"
        m = self.module()
        lba = common.T2_SECTOR + self.rel
        # 남는 꼬리는 원본 그대로 둔다(디코더는 정해진 장수에서 멈춘다)
        mode1.write_at(
            f, lba, self.sectors * common.USER, self.off, new,
            label=self.name, expect=m[self.off : self.off + len(new)],
        )  # fmt: skip
        first, last = self.off // common.USER, (self.off + len(new) - 1) // common.USER
        touched.append((lba + first, last - first + 1))
        return f"{self.name} 스트림 {len(new)}B / 원래 {used}B → rel {self.rel} +0x{self.off:X}"


def to_vram(raw: bytes) -> bytes:
    out = bytearray()
    for t in range(len(raw) // 32):
        b = raw[t * 32 : t * 32 + 32]
        buf = bytearray(32)
        for j, x in enumerate((0, 1, 0x10, 0x11)):
            for k in range(8):
                buf[x + 2 * k] = b[j * 8 + k]
        out += buf
    return bytes(out)


def to_stream(vram: bytes) -> bytes:
    out = bytearray()
    for t in range(len(vram) // 32):
        buf = vram[t * 32 : t * 32 + 32]
        for x in (0, 1, 0x10, 0x11):
            out += bytes(buf[x + 2 * k] for k in range(8))
    return bytes(out)


def xor_to_vram(raw: bytes) -> bytes:
    """모드 2(행 XOR): 면 재배열 뒤, 면마다 첫 행은 반전 · 나머지 행은 윗행(이미 풀린 값)과 XOR."""
    out = bytearray(to_vram(raw))
    for t in range(len(out) // 32):
        for i in range(32):
            k = t * 32 + i
            out[k] ^= 0xFF if (i & 15) < 2 else out[k - 2]
    return bytes(out)


def xor_to_stream(vram: bytes) -> bytes:
    enc = bytearray(vram)
    for t in range(len(vram) // 32):
        for i in range(32):
            k = t * 32 + i
            enc[k] = vram[k] ^ (0xFF if (i & 15) < 2 else vram[k - 2])
    return to_stream(bytes(enc))


DECODE = {0: bytes, 1: to_vram, 2: xor_to_vram}
ENCODE = {0: bytes, 1: to_stream, 2: xor_to_stream}


def tile_px(b: bytes) -> list[list[int]]:
    return [
        [
            ((b[2 * y] >> (7 - x)) & 1)
            | (((b[2 * y + 1] >> (7 - x)) & 1) << 1)
            | (((b[16 + 2 * y] >> (7 - x)) & 1) << 2)
            | (((b[17 + 2 * y] >> (7 - x)) & 1) << 3)
            for x in range(8)
        ]
        for y in range(8)
    ]


def px_tile(px, cx: int, cy: int) -> bytes:
    b = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = px[cy * 8 + y][cx * 8 + x]
            bit = 0x80 >> x
            for p, off in ((0, 2 * y), (1, 2 * y + 1), (2, 16 + 2 * y), (3, 17 + 2 * y)):
                if v >> p & 1:
                    b[off] |= bit
    return bytes(b)


def read_band(st, vram, tops, bots, cells) -> list[list[int]]:
    """두 줄(위·아래 첫 타일) × cells 칸 → 16행 픽셀."""
    px = [[0] * (cells * 8) for _ in range(16)]
    for cy, first in ((0, tops), (1, bots)):
        for cx in range(cells):
            p = tile_px(st.tile(vram, first + cx))
            for y in range(8):
                px[cy * 8 + y][cx * 8 : cx * 8 + 8] = p[y]
    return px


def write_band(st, vram, tops, bots, cells, px) -> None:
    for cy, first in ((0, tops), (1, bots)):
        for cx in range(cells):
            st.put(vram, first + cx, px_tile(px, cx, cy))


# ── 글꼴 ───────────────────────────────────────────────────────────────────
def neodgm(ch: str) -> list[list[int]]:
    """네오둥근모 16px(16행 × 전진폭). 임계값 이진화라 렌더러 판이 달라도 같은 비트가 나온다(제1원칙).
    16px 트루타입이 뭉개는 글자가 있다(ps1-ed3+4 narration.py) — 여기 쓰는 글자는 160px 참값과
    전부 같았다(2026-09-24). 글자가 바뀌면 다시 잰다."""
    if ch == "·":  # 원문 「・」 처럼 2×2 굵은 점을 전각 칸 가운데에 — 폰트의 점은 1px 라 묻힌다
        return [[1 if y in (7, 8) and x in (7, 8) else 0 for x in range(16)] for y in range(16)]
    if ch == " ":
        return [[0] * 8 for _ in range(16)]
    from PIL import Image, ImageDraw, ImageFont

    f = ImageFont.truetype(str(NEODGM), 16)
    im = Image.new("L", (32, 32), 0)
    ImageDraw.Draw(im).text((8, 8), ch, font=f, fill=255)
    w = int(f.getlength(ch))
    return [[1 if im.getpixel((8 + x, 8 + y)) >= 128 else 0 for x in range(w)] for y in range(16)]


_BDF = {}


def galmuri9(ch: str) -> list[list[int]]:
    """Galmuri9 BDF(도트 그대로) — 9행(베이스라인 위 9행) × 전진폭 10. 공백은 5."""
    if ch == " ":
        return [[0] * 5 for _ in range(9)]
    if not _BDF:
        from fonts import load_bdf

        _BDF.update(load_bdf(str(GALMURI9))[0])
    w, h, xo, yo, rows = _BDF[ord(ch)][:5]
    out = [[0] * 10 for _ in range(9)]
    top = (
        w + 7
    ) // 8 * 8 - 1  # BDF 행은 바이트 단위 — 폭 8 이하면 MSB 가 bit 7 이다(「이」·「어」)
    for i, r in enumerate(rows):
        y = 9 - yo - h + i
        for x in range(w):
            if r >> (top - x) & 1 and 0 <= y < 9:
                out[y][xo + x] = 1
    return out


def line(text: str, face) -> list[list[int]]:
    gs = [face(ch) for ch in text]
    H = len(gs[0])
    return [[v for g in gs for v in g[y]] for y in range(H)]


# ── 자리 ───────────────────────────────────────────────────────────────────
CARD = Stream("엔딩 카드", 898, 128, 0x37C98, 0x80, 0x300)
CARD_LINES = [  # (문구, 위 첫 타일, 아래 첫 타일, 칸 수)
    ("영웅들의 전설", 0x302, 0x312, 14),
    ("제작·저작", 0x320, 0x330, 10),
]

BANNER = Stream("오마케 간판", 706, 192, 0x162F8, 0x80, 0x700)
BANNER_TEXT = "드래곤슬레이어 극단"
BANNER_BAND = (0x720, 0x730, 16)
BANNER_ROWS = range(3, 13)  # 지우는 자리(원문 잉크 3~11행 + 아래 배경 12행)
BANNER_TOP = 4  # 글자 윗줄 — 9행 글자를 4~12행에(위아래 여백이 1·1, 마스터 2026-09-25 「1px 아래로」)
BANNER_COLS = range(3, 125)
BANNER_INK = 11


OSHIMAI_TILES = Stream("오마케 끝 타일", 706, 192, 0x184A6, 0xA0, 0x100, mode=2)
OSHIMAI_MAP = Stream("오마케 끝 배치", 706, 192, 0x19AD4, 0x40, 0, mode=0)  # 32×32 워드
OSHIMAI_ART = REPO / "games" / "pce-ed1" / "assets" / "graphics" / "kkeut.txt"
OSHIMAI_AT = (5, 4, 11, 24)  # 배치 (행, 열, 행 수, 열 수) — 원문 「おしまい」 자리 그대로
OSHIMAI_BLANK = 0x0100  # 팔레트 0 · 빈 타일 0x100
ART_COLOR = {".": 0, "B": 11, "F": 15}


def kkeut() -> tuple[bytearray, bytearray, bytearray, bytearray]:
    """(원 타일, 새 타일, 원 배치, 새 배치). 그림 = `assets/graphics/kkeut.txt`(정본)."""
    tiles, _ = OSHIMAI_TILES.original()
    mp, _ = OSHIMAI_MAP.original()
    old_t, old_m = bytearray(tiles), bytearray(mp)
    rows = [ln for ln in OSHIMAI_ART.read_text().splitlines() if ln and not ln.startswith("#")]
    r0, c0, nr, nc = OSHIMAI_AT
    assert len(rows) == nr * 8 and all(len(r) == nc * 8 for r in rows), "끝 그림 크기가 칸과 다르다"
    px = [[ART_COLOR[ch] for ch in r] for r in rows]
    # 옛 글자 타일(0x101~)은 이 자리만 쓴다(배치 전수 확인) — 비우고 새로 채운다
    for t in range(0x101, 0x100 + OSHIMAI_TILES.n_tiles):
        OSHIMAI_TILES.put(tiles, t, bytes(32))
    seen: dict[bytes, int] = {}
    nxt = 0x101
    for cy in range(nr):
        for cx in range(nc):
            b = px_tile(px, cx, cy)
            if not any(b):
                ent = OSHIMAI_BLANK
            else:
                if b not in seen:
                    assert nxt < 0x100 + OSHIMAI_TILES.n_tiles, "끝 타일이 원래 칸 수를 넘는다"
                    seen[b] = nxt
                    OSHIMAI_TILES.put(tiles, nxt, b)
                    nxt += 1
                ent = seen[b]  # 팔레트 0
            k = ((r0 + cy) * 32 + c0 + cx) * 2
            mp[k : k + 2] = ent.to_bytes(2, "little")
    return old_t, tiles, old_m, mp


def apply_kkeut(f, touched) -> str:
    _, tiles, _, mp = kkeut()
    a = OSHIMAI_TILES.apply(f, touched, OSHIMAI_TILES.encode(tiles), OSHIMAI_TILES.original()[1])
    b = OSHIMAI_MAP.apply(f, touched, OSHIMAI_MAP.encode(mp), OSHIMAI_MAP.original()[1])
    return a + " · " + b


def card() -> tuple[bytearray, bytearray]:
    vram, _ = CARD.original()
    old = bytearray(vram)
    for text, top, bot, cells in CARD_LINES:
        g = line(text, neodgm)
        W = cells * 8
        assert len(g[0]) <= W, (text, len(g[0]), W)
        left = (W - len(g[0])) // 2
        px = [[0] * W for _ in range(16)]
        for y in range(16):
            for x, v in enumerate(g[y]):
                if v:
                    px[y][left + x] = 2
        write_band(CARD, vram, top, bot, cells, px)
    return old, vram


def banner() -> tuple[bytearray, bytearray]:
    vram, _ = BANNER.original()
    old = bytearray(vram)
    px = read_band(BANNER, vram, *BANNER_BAND)
    # 글자 자리를 행마다 배경 한 색으로 지운다(그 행에서 가장 흔한 색 = 그러데이션)
    for y in BANNER_ROWS:
        seg = [px[y][x] for x in BANNER_COLS]
        bg = max(set(seg), key=seg.count)
        for x in BANNER_COLS:
            px[y][x] = bg
    g = line(BANNER_TEXT, galmuri9)
    W = len(BANNER_COLS)
    assert len(g[0]) <= W, (len(g[0]), W)
    left = BANNER_COLS.start + (W - len(g[0])) // 2
    for y in range(9):
        for x, v in enumerate(g[y]):
            if v:
                px[BANNER_TOP + y][left + x] = BANNER_INK
    write_band(BANNER, vram, *BANNER_BAND, px)
    return old, vram


def apply_card(f, touched) -> str:
    _, vram = card()
    return CARD.apply(f, touched, CARD.encode(vram), CARD.original()[1])


def apply_banner(f, touched) -> str:
    _, vram = banner()
    return BANNER.apply(f, touched, BANNER.encode(vram), BANNER.original()[1])


# ── 미리보기 ────────────────────────────────────────────────────────────────
CARD_PAL = {0: (0, 0, 0), 1: (146, 146, 146), 2: (255, 255, 255), 3: (73, 73, 73)}
BANNER_PAL = [
    0x0,
    0x48,
    0x91,
    0xDA,
    0x123,
    0x16C,
    0x1FB,
    0xE8,
    0x130,
    0x90,
    0xE0,
    0xC1,
    0x151,
    0x1E1,
    0x1FC,
    0x1FE,
]


OSHIMAI_PAL = [
    0x0,
    0x17C,
    0x13B,
    0xF2,
    0x178,
    0xF8,
    0xA8,
    0xE7,
    0xC7,
    0x43,
    0x1AF,
    0x116,
    0x38,
    0x18,
    0x0,
    0x1FF,
]


def _rgb(c):
    return (((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36, (c & 7) * 36)


def preview() -> list[Path]:
    from PIL import Image

    outs = []
    old, new = card()
    im = Image.new("RGB", (136, 88), (0, 0, 0))
    for i, (_, top, bot, cells) in enumerate(CARD_LINES):
        for k, vram in enumerate((old, new)):
            px = read_band(CARD, vram, top, bot, cells)
            for y in range(16):
                for x in range(cells * 8):
                    im.putpixel(
                        (12 + x + (14 - cells) * 4, 4 + i * 44 + k * 20 + y), CARD_PAL[px[y][x] & 3]
                    )
    p = common.REVIEW_DIR / "gfx_text_card.png"
    outs.append(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    im.resize((im.width * 6, im.height * 6), Image.NEAREST).save(p)

    old, new = banner()
    im = Image.new("RGB", (128, 36), (0, 0, 0))
    for k, vram in enumerate((old, new)):
        px = read_band(BANNER, vram, *BANNER_BAND)
        for y in range(16):
            for x in range(128):
                im.putpixel((x, k * 20 + y), _rgb(BANNER_PAL[px[y][x]]))
    p = common.REVIEW_DIR / "gfx_text_banner.png"
    outs.append(p)
    im.resize((im.width * 6, im.height * 6), Image.NEAREST).save(p)

    old_t, new_t, old_m, new_m = kkeut()
    r0, c0, nr, nc = OSHIMAI_AT
    im = Image.new("RGB", (nc * 8 * 2 + 8, nr * 8), (0, 0, 0))
    for k, (tl, mp) in enumerate(((old_t, old_m), (new_t, new_m))):
        for cy in range(nr):
            for cx in range(nc):
                i = ((r0 + cy) * 32 + c0 + cx) * 2
                ent = int.from_bytes(mp[i : i + 2], "little")
                tp = tile_px(OSHIMAI_TILES.tile(tl, ent & 0x7FF))
                for y in range(8):
                    for x in range(8):
                        im.putpixel(
                            (k * (nc * 8 + 8) + cx * 8 + x, cy * 8 + y), _rgb(OSHIMAI_PAL[tp[y][x]])
                        )
    p = common.REVIEW_DIR / "gfx_text_kkeut.png"
    outs.append(p)
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(p)
    return outs


def main() -> None:
    for st, fn in ((CARD, card), (BANNER, banner)):
        _, vram = fn()
        print(f"{st.name}: 스트림 {len(st.encode(vram))}B / 원래 {st.original()[1]}B")
    _, tl, _, mp = kkeut()
    for st, d in ((OSHIMAI_TILES, tl), (OSHIMAI_MAP, mp)):
        print(f"{st.name}: 스트림 {len(st.encode(d))}B / 원래 {st.original()[1]}B")
    for p in preview():
        print(p)


if __name__ == "__main__":
    main()
