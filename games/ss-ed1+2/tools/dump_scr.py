"""`SCR*.2D` — 인게임 화면 그래픽(챕터 판 · HUD 패널 · 프레임)을 뜯는다.

🔴 **HUD 의 인명·`あと`·하단 챕터 판은 문자열이 아니라 그림이다.** 문자열을 다 고치고도
   화면이 안 바뀌어서 알았다(2026-08-24) — 디스크 어디에도 그 낱말의 SJIS 가 없고 실행 중
   RAM 에도 없다. 전부 여기 들어 있다.

## 파일 꼴 (실측 — VDP2 VRAM 대조로 확정, 2026-08-24)

    0x00  "SEGA SATURN SCR\\0" + BE32 1 + BE32 0 + BE16 0x1200(문자 번호 바탕) + 0…
    0x20~ 구획 표 — 16B 씩 `[오프셋 BE32][크기 BE32][0 8B]`, 네 칸

    구획0  패턴 네임 테이블 : 16B 머리 + 64×64 × BE16
    구획1  문자 데이터      : 16B 머리 + **8bpp · 8×8 셀**(셀 하나 64B)
    구획2  팔레트           : 16B 머리 + 256색 RGB555 BE (⚠ **R 이 하위 5비트**)
    구획3  0 으로 찬 칸     : 미사용

⚠ **한때 4bpp 라고 적어 두었는데 틀렸다**(2026-08-24 정정). 4bpp 로 조립해도 워터마크가
  읽혀서 확증했다고 믿었지만, 실기 VDP2 는 이 층을 **8bpp·8×8** 로 읽는다
  (`get_video_state` → NBG1 `color_mode 8bpp` · `char_size 8x8`). 패턴 색인이 2씩 뛰는 건
  4bpp 라서가 아니라 **문자 번호 단위가 32B 인데 8bpp 셀이 64B** 라서다.
  🔴 교훈 — 「조립해 보니 읽힌다」는 포맷의 증거가 못 된다. **실기 레지스터가 정본이다.**

## 어디에 뭐가 있나 (SCR1 = ED1 필드 화면, SCR2 = ED2. 팔레트는 둘이 같다)

    셀   0~ 255   기본 맵이 쓰는 것 — 금색 프레임 · 우측 패널 · 판 바탕
    셀 256~1023   **챕터 판 여섯 장** — 판 하나가 24×5 셀(192×40), **스트라이드 128**
                  (뒤 8 셀은 안 쓴다). 시작 셀 = 256 · 384 · 512 · 640 · 768 · 896
    셀1024~       **HUD 패널** — 인명과 `Lv`·`EP`·`HP`·`MP`·`Gold` 가 미리 합성돼 있다
    ⚠ 기본 맵은 일부만 쓴다. 나머지는 게임이 **런타임에 패턴 이름을 바꿔 끼운다.**

    python3 tools/dump_scr.py            # 구획 요약
    python3 tools/dump_scr.py --sheet    # 셀 시트 PNG → work/review/scr/
    python3 tools/dump_scr.py --plates   # 챕터 판 여섯 장 PNG → work/review/scr/
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

FILES = ("/SCR1.2D", "/SCR2.2D")
MAGIC = b"SEGA SATURN SCR\x00"
SEC_TABLE = 0x20
SEC_HEAD = 16  # 각 구획 앞머리
CELL_BYTES = 64  # 8bpp 8×8

# ── 챕터 판 — 판 하나가 24×5 셀, 스트라이드 128 (실측) ─────────────────────────
PLATE_COLS, PLATE_ROWS = 24, 5
PLATE_W, PLATE_H = PLATE_COLS * 8, PLATE_ROWS * 8  # 192 × 40
PLATE_CELLS = PLATE_COLS * PLATE_ROWS  # 120
PLATE_STARTS = (256, 384, 512, 640, 768, 896)


def sections(d):
    """`[(오프셋, 크기)]` — 0 인 칸은 버린다."""
    assert d[: len(MAGIC)] == MAGIC, "SCR 시그니처가 아니다"
    out = []
    for i in range(SEC_TABLE, SEC_TABLE + 16 * 8, 16):
        off, size = struct.unpack_from(">II", d, i)
        if size:
            out.append((off, size))
    return out


def cell_base(d):
    """문자 데이터 첫 셀의 **파일 오프셋** — 재삽입이 쓰는 좌표계."""
    return sections(d)[1][0] + SEC_HEAD


def parse(d):
    """`{map, cells, pal}` — 각각 numpy 배열."""
    import numpy as np

    sec = sections(d)
    assert len(sec) >= 3, f"구획이 {len(sec)}개뿐이다"
    (mo, ms), (co, cs), (po, _ps) = sec[0], sec[1], sec[2]
    nt = np.frombuffer(d[mo + SEC_HEAD : mo + ms], ">u2")
    n = (cs - SEC_HEAD) // CELL_BYTES
    raw = np.frombuffer(d[co + SEC_HEAD : co + SEC_HEAD + n * CELL_BYTES], np.uint8)
    pal = np.frombuffer(d[po + SEC_HEAD : po + SEC_HEAD + 512], ">u2").astype(np.uint32)
    rgb = np.stack([pal & 31, (pal >> 5) & 31, (pal >> 10) & 31], 1).astype(np.uint8) * 8
    return {"map": nt.reshape(64, 64), "cells": raw.reshape(n, 8, 8), "pal": rgb}


def plate_px(cells, start):
    """셀 `start` 부터 24×5 를 **화면 배치대로** 이어 붙인다 → (40, 192) 색인 배열."""
    blk = cells[start : start + PLATE_CELLS].reshape(PLATE_ROWS, PLATE_COLS, 8, 8)
    return blk.transpose(0, 2, 1, 3).reshape(PLATE_H, PLATE_W)


def px_to_cells(px):
    """(40, 192) 색인 배열 → 셀 순서 바이트열(120 × 64B). `plate_px` 의 역."""
    import numpy as np

    a = np.asarray(px, np.uint8).reshape(PLATE_ROWS, 8, PLATE_COLS, 8)
    return a.transpose(0, 2, 1, 3).reshape(PLATE_CELLS * 64).tobytes()


def main():
    from PIL import Image

    common.verify_source()
    _f, mm = common.open_image()
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    out = os.path.join(common.REVIEW_DIR, "scr")
    for path in FILES:
        lba, size = files[path]
        d = common.read_extent(mm, lba, size)
        r = parse(d)
        used = sorted({int(v) & 0x3FFF for v in r["map"].flatten()})
        print(f"{path} {size:,}B · 구획 {[(hex(o), s) for o, s in sections(d)]}")
        print(f"   셀 {len(r['cells'])} · 기본 맵이 쓰는 문자번호 {len(used)} (최대 {used[-1]})")
        if "--sheet" in sys.argv or "--plates" in sys.argv:
            os.makedirs(out, exist_ok=True)
        if "--sheet" in sys.argv:
            import numpy as np

            n = len(r["cells"])
            w = 24  # 판 폭과 같게 두면 챕터 판이 시트에서도 바로 읽힌다
            h = (n + w - 1) // w
            sheet = np.zeros((h * 8, w * 8), np.uint8)
            for i, c in enumerate(r["cells"]):
                y, x = divmod(i, w)
                sheet[y * 8 : y * 8 + 8, x * 8 : x * 8 + 8] = c
            p = os.path.join(out, os.path.basename(path).replace(".2D", "_cells.png"))
            Image.fromarray(r["pal"][sheet]).resize((w * 8 * 2, h * 8 * 2), Image.NEAREST).save(p)
            print(f"   → {p}")
        if "--plates" in sys.argv:
            import numpy as np

            sheet = np.zeros((PLATE_H * len(PLATE_STARTS), PLATE_W), np.uint8)
            for i, s in enumerate(PLATE_STARTS):
                sheet[i * PLATE_H : (i + 1) * PLATE_H] = plate_px(r["cells"], s)
            p = os.path.join(out, os.path.basename(path).replace(".2D", "_plates.png"))
            im = Image.fromarray(r["pal"][sheet])
            im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(p)
            print(f"   → {p}")


if __name__ == "__main__":
    main()
