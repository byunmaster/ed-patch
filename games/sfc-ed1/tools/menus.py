"""sfc-ed1 메뉴 라벨 — 창 배치 표에 **폰트 타일 번호로 구워진** 텍스트를 되읽는다.

`window.asm $02:9F97` 이 `$0F4F` 의 id 로 창 배치 표 셋($03:BD54 · $03:BDA5 · $03:BDF6, 3B 포인터 × 27)
중 하나를 골라 [row, col, w, h][타일맵 워드 w×h] 를 화면에 깐다. 라벨(じゅもん/つかう/…)은 그 워드에
글꼴 타일 번호로 들어 있다 — 대사와 **다른 소비 경로**다(정적 타일맵 · 글리프가 VRAM 에 상주해야 한다).
되읽기는 글자→타일 표($03:F3EC)의 역함수로 한다. 출력은 work/derived/menus/menus.json(원문 — 커밋 금지).
라벨마다 `budget_tiles`(라벨 시작 칸부터 오른쪽 창 틀까지)를 재 둔다 — 한글은 칸 둘을 쓴다.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common

LAYOUT_TABLES = {"A": 0x03BD54, "B": 0x03BDA5, "C": 0x03BDF6}
LAYOUT_COUNT = 27  # (BDA5 − BD54) / 3
BLANK_TILES = {0x000, 0x108}
FRAME = "·"  # 글꼴 밖 타일(창 틀 등)


def inverse_tile_table(rom: bytes) -> dict[int, int]:
    tab = common.snes2off(text.TILE_TABLE)
    inv: dict[int, int] = {}
    for c in range(0xD0):
        t = rom[tab + 2 * c] | ((rom[tab + 2 * c + 1] & 3) << 8)
        inv.setdefault(t, c)
    return inv


def _line(words: list[int], inv: dict[int, int]) -> str:
    chars = []
    for wd in words:
        t = wd & 0x3FF
        if t in BLANK_TILES:
            chars.append(" ")
        elif t in inv and inv[t] != text.SPACE:
            chars.append(text.TABLE.get(inv[t], "?"))
        else:
            chars.append(FRAME)
    return "".join(chars)


def layouts(rom: bytes) -> list[dict]:
    inv = inverse_tile_table(rom)
    out = []
    for name, addr in LAYOUT_TABLES.items():
        base = common.snes2off(addr)
        for wid in range(LAYOUT_COUNT):
            p = (
                rom[base + 3 * wid]
                | (rom[base + 3 * wid + 1] << 8)
                | (rom[base + 3 * wid + 2] << 16)
            )
            try:
                o = common.snes2off(p)
            except ValueError:
                continue
            row, col, w, h = rom[o], rom[o + 1], rom[o + 2], rom[o + 3]
            if not (1 <= w <= 32 and 1 <= h <= 28):
                continue
            words = [rom[o + 4 + 2 * i] | (rom[o + 5 + 2 * i] << 8) for i in range(w * h)]
            labels = []
            for r in range(h):
                ln = _line(words[r * w : (r + 1) * w], inv)
                if not any(("぀" <= ch <= "ヿ") or ch.isalnum() for ch in ln):
                    continue
                x0 = next(i for i, ch in enumerate(ln) if ch not in FRAME + " ")
                x1 = next((i for i in range(x0, len(ln)) if ln[i] == FRAME), len(ln))
                labels.append(
                    {"row": r, "x0": x0, "budget_tiles": x1 - x0, "jp": ln[x0:x1].rstrip()}
                )
            if labels:
                out.append(
                    {
                        "table": name,
                        "id": wid,
                        "addr": f"{p:06X}",
                        "row": row,
                        "col": col,
                        "w": w,
                        "h": h,
                        "labels": labels,
                    }
                )
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    ls = layouts(common.rom_bytes())
    n = sum(len(x["labels"]) for x in ls)
    uniq = sorted({lab["jp"] for x in ls for lab in x["labels"]})
    print(f"라벨이 든 창 {len(ls)} · 라벨 줄 {n} · 고유 {len(uniq)}")
    for x in ls:
        print(
            f"  {x['table']}{x['id']:02X} w{x['w']}: "
            + " / ".join(f"{lab['jp']}[{lab['budget_tiles']}]" for lab in x["labels"])
        )
    if a.dump:
        d = common.OUT_DIR / "menus"
        d.mkdir(parents=True, exist_ok=True)
        (d / "menus.json").write_text(
            json.dumps(ls, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("→", d / "menus.json")
