"""백업 RAM·시스템 카드 안내 화면의 그림 글자(패키지 20) — 간판 「満員」「宿」과 말풍선 「な」를 한글 그림으로 바꾼다.

그림은 패키지 +0x73E3 의 **LZSS 한 덩이**(디코드 0x4000B = VRAM 워드 0~0x1FFF)에 BAT(32×32, 워드 0~0x3FF)와 타일(4비트 평면, 워드 0x400~)이 같이 들어 있다.
  · 풀이는 BIOS 쪽이 아니라 패키지 자체 루틴(`$50F7`)이 한다 — 링 버퍼 256B(0 으로 채움, 쓰기 위치 시작 0xEF)·길이 2~17·플래그 MSB 먼저·긴 길이는 두 개씩 한 바이트(윗 니블 먼저).
  · 글자 모양은 `data/card_art.json`(마스터 시안 → 원판 픽셀 격자, 층 문자 F=채움 · K=검은 윤곽 · .=그대로)이다. 원본 픽셀은 저장하지 않는다 — 옛 글자는 규칙으로 지우고(채움색 + 그 윤곽)
    지운 자리는 같은 행의 가장 가까운 나무(또는 말풍선 흰색)로 채운다.
  · 타일은 화면에서 하나씩만 쓰이는 걸 그대로 고치고, 둘 이상이 쓰는 타일(만실 아랫줄 0x121)은 **빈 타일**을 새로 받아 BAT 만 갈라 쓴다.
  · 다시 압축한 덩이는 원본 덩이 자리보다 짧아야 한다(뒤 덩이로 넘어가지 못한다) — 남는 자리는 원본 바이트를 그대로 둔다.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PKG_REL, PKG_SECTORS = 2562, 78
U = common.USER
STREAM_OFF = 0x73E3  # 덩이 시작(패키지 오프셋 — 논리 주소 $B3E3)
STREAM_END = 0x976D  # 원본 덩이 끝 — 다음 덩이가 이어진다
OUT_LEN = 0x4000
DATA = common.GAME_DIR / "data" / "card_art.json"
FIRST_FREE_TILE = 0x1B8  # 원본 BAT 가 안 쓰는 빈 타일 구간(0x1B8~0x1FF — 72칸)
WOOD = {2, 4, 6, 12, 13, 14}  # 나무 판자 색 번호(팔레트 2)
WOOD_SHIFTS = (-24, 24, -16, 16, -8, 8, -32, 32, -40, 40)


def decode(buf: bytes, pos: int, outlen: int) -> tuple[bytes, int]:
    win = bytearray(256)
    r = 0xEF
    out = bytearray()
    flags = nbits = 0
    nib = None
    p = pos
    while len(out) < outlen:
        if nbits == 0:
            flags, p, nbits = buf[p], p + 1, 8
        bit = (flags >> 7) & 1
        flags = (flags << 1) & 0xFF
        nbits -= 1
        if bit:
            b = buf[p]
            p += 1
            out.append(b)
            win[r] = b
            r = (r + 1) & 255
        else:
            off = buf[p]
            p += 1
            if nib is None:
                v = buf[p]
                p += 1
                ln, nib = (v >> 4) + 2, v & 15
            else:
                ln, nib = nib + 2, None
            for i in range(ln):
                b = win[(off + i) & 255]
                out.append(b)
                win[r] = b
                r = (r + 1) & 255
    return bytes(out[:outlen]), p


def encode(data: bytes) -> bytes:
    """`decode` 의 역 — 탐욕 매칭(링 256칸 전부 시험, 복사 중 링이 바뀌는 것까지 흉내)."""
    win = bytearray(256)
    r = 0xEF
    out = bytearray()
    flag_pos = 0
    flag_bit = 0
    nib_pos = None
    i = 0
    n = len(data)
    while i < n:
        best, boff = 1, 0
        maxl = min(17, n - i)
        for off in range(256):
            if win[off] != data[i]:
                continue
            tmp = win[:]
            rr = r
            ln = 0
            while ln < maxl:
                b = tmp[(off + ln) & 255]
                if b != data[i + ln]:
                    break
                tmp[rr] = b
                rr = (rr + 1) & 255
                ln += 1
            if ln > best:
                best, boff = ln, off
        if flag_bit == 0:
            flag_pos = len(out)
            out.append(0)
            flag_bit = 8
        flag_bit -= 1
        if best >= 2:
            out.append(boff)
            if nib_pos is None:
                nib_pos = len(out)
                out.append((best - 2) << 4)
            else:
                out[nib_pos] |= best - 2
                nib_pos = None
            for k in range(best):
                b = win[(boff + k) & 255]
                win[r] = b
                r = (r + 1) & 255
            i += best
        else:
            out[flag_pos] |= 1 << flag_bit
            out.append(data[i])
            win[r] = data[i]
            r = (r + 1) & 255
            i += 1
    return bytes(out)


def tile_px(buf: bytes, t: int) -> np.ndarray:
    o = t * 32
    px = np.zeros((8, 8), int)
    for y in range(8):
        p0, p1, p2, p3 = buf[o + y * 2], buf[o + y * 2 + 1], buf[o + 16 + y * 2], buf[o + 16 + y * 2 + 1]
        for x in range(8):
            s = 7 - x
            px[y, x] = ((p0 >> s) & 1) | (((p1 >> s) & 1) << 1) | (((p2 >> s) & 1) << 2) | (((p3 >> s) & 1) << 3)
    return px


def tile_bytes(px: np.ndarray) -> bytes:
    b = bytearray(32)
    for y in range(8):
        for plane in range(4):
            v = 0
            for x in range(8):
                v |= ((int(px[y, x]) >> plane) & 1) << (7 - x)
            b[(plane >> 1) * 16 + y * 2 + (plane & 1)] = v
    return bytes(b)


def dilate(m: np.ndarray) -> np.ndarray:
    h, w = m.shape
    o = np.zeros_like(m)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sh = np.zeros_like(m)
            sh[max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)] = m[
                max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)
            ]
            o |= sh
    return o


class Screen:
    """BAT(32×32) + 타일 → 화면 색 번호 배열. 수정은 화면에서 하고 `repack` 이 타일·BAT 로 되돌린다."""

    def __init__(self, vram: bytes):
        self.vram = bytearray(vram)
        self.bat = [int.from_bytes(vram[i * 2 : i * 2 + 2], "little") for i in range(0x400)]
        self.idx = np.zeros((29 * 8, 256), int)
        for r in range(29):
            for c in range(32):
                self.idx[r * 8 : r * 8 + 8, c * 8 : c * 8 + 8] = tile_px(vram, self.bat[r * 32 + c] & 0xFFF)
        self.orig = self.idx.copy()

    def erase(self, kind: str, box: list[int], fill_idx: int):
        x0, y0, x1, y1 = box
        sub = self.idx[y0 : y1 + 1, x0 : x1 + 1]
        if kind == "bubble":  # 말풍선 안은 통째로 흰색
            self.idx[y0 : y1 + 1, x0 : x1 + 1] = 15
            return
        core = np.zeros(self.idx.shape, bool)
        core[y0 : y1 + 1, x0 : x1 + 1] = np.isin(sub, [fill_idx, 1, 8] if kind == "red" else [fill_idx, 3])
        ring = dilate(core) & (self.idx == 1)  # 윤곽(검정)
        mask = core | ring
        src = self.idx.copy()
        for y, x in zip(*np.where(mask), strict=True):
            for dy in WOOD_SHIFTS:  # 같은 열의 지워지지 않은 나무 결을 가져온다(가로결이 이어지게 위·아래 8px 배수)
                yy = y + dy
                if y0 <= yy <= y1 and not mask[yy, x] and src[yy, x] in WOOD:
                    self.idx[y, x] = src[yy, x]
                    break
            else:
                for d in range(1, 40):
                    hit = None
                    for xx in (x - d, x + d):
                        if 0 <= xx < 256 and not mask[y, xx] and src[y, xx] in WOOD:
                            hit = src[y, xx]
                            break
                    if hit is not None:
                        self.idx[y, x] = hit
                        break
                else:
                    self.idx[y, x] = 4

    def stamp(self, x: int, y: int, rows: list[str], fill: int):
        for dy, line in enumerate(rows):
            for dx, ch in enumerate(line):
                if ch == "F":
                    self.idx[y + dy, x + dx] = fill
                elif ch == "K":
                    self.idx[y + dy, x + dx] = 1

    def repack(self) -> bytes:
        used: dict[int, list[int]] = {}
        for i, e in enumerate(self.bat):
            used.setdefault(e & 0xFFF, []).append(i)
        free = [
            t
            for t in range(FIRST_FREE_TILE, 0x200)
            if t not in used and not any(self.vram[t * 32 : t * 32 + 32])
        ]
        vram = bytearray(self.vram)
        bat = list(self.bat)
        for t, cells in sorted(used.items()):
            news = {}
            for i in cells:
                r, c = divmod(i, 32)
                if r >= 29:
                    continue
                blk = self.idx[r * 8 : r * 8 + 8, c * 8 : c * 8 + 8]
                if not np.array_equal(blk, self.orig[r * 8 : r * 8 + 8, c * 8 : c * 8 + 8]):
                    news[i] = blk
            if not news:
                continue
            blocks = {tile_bytes(b) for b in news.values()}
            untouched = [i for i in cells if i not in news]
            if untouched or len(blocks) > 1:  # 다른 칸도 쓰는 타일 — 바뀐 칸만 새 타일을 받는다
                groups: dict[bytes, list[int]] = {}
                for i, b in news.items():
                    groups.setdefault(tile_bytes(b), []).append(i)
                keep_first = not untouched  # 안 바뀐 칸이 없으면 첫 묶음이 원래 타일을 쓴다
                for tb, ids in groups.items():
                    if keep_first:
                        nt, keep_first = t, False
                    else:
                        if not free:
                            raise RuntimeError("카드 그림: 빈 타일이 모자란다")
                        nt = free.pop(0)
                    vram[nt * 32 : nt * 32 + 32] = tb
                    for i in ids:
                        bat[i] = (bat[i] & 0xF000) | nt
            else:
                vram[t * 32 : t * 32 + 32] = blocks.pop()
        for i, e in enumerate(bat):
            vram[i * 2 : i * 2 + 2] = e.to_bytes(2, "little")
        return bytes(vram)


def make_vram(vram: bytes) -> bytes:
    scr = Screen(vram)
    art = json.loads(DATA.read_text(encoding="utf-8"))
    for s in art["signs"]:
        e = s["erase"]
        scr.erase(e["kind"], e["box"], 9 if e["kind"] == "red" else 15 if e["kind"] == "white" else 2)
        scr.stamp(s["x"], s["y"], s["rows"], s["fill"])
    return scr.repack()


def writes(pkg: bytes):
    """[(선형 오프셋, 새 바이트, 기대 원본, 라벨)] — 압축 덩이 한 곳."""
    vram, end = decode(pkg, STREAM_OFF, OUT_LEN)
    assert end == STREAM_END, hex(end)
    new = encode(make_vram(vram))
    assert len(new) <= STREAM_END - STREAM_OFF, (len(new), STREAM_END - STREAM_OFF)
    assert decode(new, 0, OUT_LEN)[0] == make_vram(vram)
    base = PKG_REL * U
    return [(base + STREAM_OFF, new, pkg[STREAM_OFF : STREAM_OFF + len(new)], "카드 안내 화면 그림(만실·여관·헉)")], {
        "bytes": len(new),
        "slot": STREAM_END - STREAM_OFF,
    }


def apply(w) -> dict:
    pkg = common.track_data(PKG_REL, PKG_SECTORS)
    spans, info = writes(pkg)
    for linear, new, expect, label in spans:
        w.put(linear, new, expect, label)
    print(f"  카드 안내 화면 그림: {info['bytes']}B / 자리 {info['slot']}B")
    return info
