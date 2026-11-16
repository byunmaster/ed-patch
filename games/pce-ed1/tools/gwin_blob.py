"""비모달 자막 쪽 자료 블롭 — 쪽마다 글자 타일 압축본(8B/타일)을 **타일 풀로 중복 제거**하고 쪽 서술·줄 배치를 한 덩이로 묶는다(제품 공사, 마스터 10-30).

왜: 씬 블록(8KB)에 쪽 자료를 넣으면 쪽 하나(≈900B)가 한계였다. 씬 6 전체(16쪽)는 1,082타일 8,656B 인데 **고유 타일은 402개**뿐이라 풀 + 1바이트 인덱스로 ≈4.7KB.
이 블롭은 빈 디스크 섹터에 심겨 씬을 열 때 CD RAM 뱅크 0x85 에 올라간다(런타임 `gwin_rt`). 쪽 BAT(쪽당 440B)는 저장하지 않고 **줄 배치**(`gwin.make_window` 와 같은 규칙)에서 런타임이 만든다.

레이아웃(리틀엔디언, 오프셋은 블롭 머리 기준):
  +0  쪽 수 n(1B)
  +1  쪽 서술 n × 12B: 시작 프레임(2) · 끝 프레임(2) · 타일 수(1) · 줄 수(1) · 풀 오프셋(2) · 인덱스 오프셋(2) · 줄 배치 오프셋(2)
  … 타일 풀들(타일마다 8B, 풀 하나 ≤ 256타일) · 인덱스들(쪽마다 타일 수 바이트) · 줄 배치들(줄마다 첫 행(1) · 기둥 수(1), 줄 수만큼)
쪽의 글자 타일 번호는 `gwin.TILE0` 부터 차례로(줄 → 기둥 → 위·아래 반) — 줄 배치만 있으면 BAT 가 정해진다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gwin

DESC = 12
POOL_MAX = 256


def page_lines(speaker: str | None, text: str) -> list[tuple[int, int]]:
    """쪽의 줄 배치 [(첫 행, 기둥 수)] — `gwin.make_window` 와 같은 규칙."""
    lines = ([speaker] if speaker else []) + gwin.page_lines(speaker, text)
    return [(gwin.LINE_ROWS[li], gwin.strip(line)[1]) for li, line in enumerate(lines)]


def pack(pages: list[dict], frames) -> bytes:
    """pages = [{speaker, text, start, end}] → 블롭. `frames(초)` = 프레임 수 변환."""
    descs, pools, idxs, lays = [], [], [], []
    cur: dict[bytes, int] = {}
    cur_tiles: list[bytes] = []
    pool_starts: list[int] = []  # 풀마다 타일 목록(아래서 오프셋 확정)
    page_pool: list[int] = []
    page_idx: list[bytes] = []
    for pg in pages:
        tiles, _bat = gwin.make_window(pg.get("speaker"), pg["text"])
        ts = [tiles[k : k + 8] for k in range(0, len(tiles), 8)]
        new = {t for t in ts if t not in cur}
        if len(cur) + len(new) > POOL_MAX:  # 풀이 넘치면 새 풀
            pools.append(cur_tiles)
            cur, cur_tiles = {}, []
        for t in ts:
            if t not in cur:
                cur[t] = len(cur_tiles)
                cur_tiles.append(t)
        page_pool.append(len(pools))
        page_idx.append(bytes(cur[t] for t in ts))
    pools.append(cur_tiles)
    n = len(pages)
    head = 1 + DESC * n
    pool_off, off = [], head
    for p in pools:
        pool_off.append(off)
        off += 8 * len(p)
    idx_off = []
    for ix in page_idx:
        idx_off.append(off)
        off += len(ix)
    lay_off, lay_bytes = [], []
    for pg in pages:
        ln = page_lines(pg.get("speaker"), pg["text"])
        lay_off.append(off)
        b = b"".join(bytes([r, c]) for r, c in ln)
        lay_bytes.append(b)
        off += len(b)
    out = bytearray([n])
    for k, pg in enumerate(pages):
        ln = len(lay_bytes[k]) // 2
        out += frames(pg["start"]).to_bytes(2, "little") + frames(pg["end"]).to_bytes(2, "little")
        out += bytes([len(page_idx[k]), ln]) + pool_off[page_pool[k]].to_bytes(2, "little") + idx_off[k].to_bytes(2, "little") + lay_off[k].to_bytes(2, "little")
    for p in pools:
        for t in p:
            out += t
    for ix in page_idx:
        out += ix
    for b in lay_bytes:
        out += b
    assert len(out) == off
    return bytes(out)


def unpack(blob: bytes) -> list[dict]:
    """참조 디코더(시험·런타임 대조용) — 쪽마다 {start, end, tiles(압축본 바이트), bat(글자 칸 {(행, 열): 단어})}."""
    n = blob[0]
    out = []
    for k in range(n):
        d = blob[1 + DESC * k : 1 + DESC * (k + 1)]
        start, end = int.from_bytes(d[0:2], "little"), int.from_bytes(d[2:4], "little")
        nt, nl = d[4], d[5]
        po, io, lo = (int.from_bytes(d[6:8], "little"), int.from_bytes(d[8:10], "little"), int.from_bytes(d[10:12], "little"))
        tiles = b"".join(blob[po + 8 * blob[io + t] : po + 8 * blob[io + t] + 8] for t in range(nt))
        bat, n_ = {}, gwin.TILE0
        for li in range(nl):
            top, ncol = blob[lo + 2 * li], blob[lo + 2 * li + 1]
            for c in range(ncol):
                for half in (0, 1):
                    bat[(top + half, gwin.TEXT_COL0 + c)] = gwin.PAL | n_
                    n_ += 1
        out.append({"start": start, "end": end, "tiles": tiles, "bat": bat})
    return out
