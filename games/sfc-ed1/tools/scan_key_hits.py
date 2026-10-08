#!/usr/bin/env python3
"""사전·정본 열쇠 전부를 **원본 롬 전 영역에서 정확 검색**해, 문안 스트림(어댑터) 밖 출현을 모은다 — 숨은 표를 찾는 그물.

출처를 손으로 열거하면 놓친다(PS1 ED3 월드맵 지명 목록이 검사기 분모 밖이라 일본어로 남았다). 이 게임 롬은 가나 전용 1바이트라
가나로만 된 열쇠를 코드열로 바꿔 롬 전체에서 찾는다. 짧은(3자) 열쇠도 넣는다 — 거짓 양성은 「이미 아는 영역」을 빼고 사람이 본다.

  python3 tools/scan_key_hits.py            # 아는 영역 밖 출현을 군집별로
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common

ROOT = common.ROOT
INV = {}
for code, ch in text.TABLE.items():
    if len(ch) == 1 and ch.strip() and code not in (0x0D, 0x76, 0x80, 0x81, 0x82):
        INV.setdefault(ch, code)
INV["　"] = 0x10


def keys() -> dict[str, set[str]]:
    sys.path.insert(0, str(ROOT / "shared"))
    import canon

    out: dict[str, set[str]] = {}
    for cat in canon.categories("ed1"):
        for k in canon.table(cat, "ed1"):
            out.setdefault(k.split("@")[0], set()).add(f"canon:{cat}")
    for k, v in canon.aliases("ed1").items():
        for x in (k, v):
            out.setdefault(x.split("@")[0], set()).add("canon:alias")
    return out


def encode_key(k: str) -> bytes | None:
    try:
        return bytes(INV[c] for c in k)
    except KeyError:
        return None


def known(rom: bytes) -> list[tuple[int, int, str]]:
    """어댑터가 이미 보는 영역(파일 오프셋 [a,b))."""
    r = [(sg[4], sg[4] + len(sg[5]), "대본 조각") for sg in text.all_segments(rom)]  # 네 포인터 표 전부(대본 본체 · $05·$1E 뱅크 포함)
    for code, (addr, n, name) in text.DICT_TABLES.items():
        bank = addr & 0xFF0000
        base = common.snes2off(addr)
        for i in range(n):
            p = rom[base + 2 * i] | (rom[base + 2 * i + 1] << 8)
            o = common.snes2off(bank | p)
            r.append((o, o + len(text.cstr(o, rom)) + 1, f"사전 D{code - 0xD0}"))
    r.append((common.snes2off(0x06FB55), common.snes2off(0x06FB55) + 850, "스태프롤"))
    ui = json.loads((common.GAME_DIR / "textmap" / "battle_ui.json").read_text(encoding="utf-8"))
    for key in ("names", "title"):
        for x in ui.get(key, []):
            o = common.snes2off(int(x["addr"], 16))
            r.append((o, o + x["cells"], f"전투 UI {key}"))
    for g in ui.get("grid", []):
        o = common.snes2off(int(g["addr"], 16))
        r.append((o, o + g["cells"], "전투 UI grid"))
    return r


def main() -> int:
    rom = common.rom_bytes()
    kn = known(rom)
    hits = []
    for k, why in keys().items():
        b = encode_key(k)
        if b is None or len(k) < 3:
            continue
        i = rom.find(b)
        while i >= 0:
            if not any(a <= i < z for a, z, _ in kn):
                hits.append((i, k, sorted(why)[0]))
            i = rom.find(b, i + 1)
    hits.sort()
    clusters: list[list] = []
    for h in hits:
        if clusters and h[0] - clusters[-1][-1][0] < 64:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    print(f"열쇠 {len(keys())} · 아는 영역 밖 출현 {len(hits)} · 군집 {len(clusters)}")
    for c in clusters:
        a = c[0][0]
        ctx = text.decode(rom[max(0, a - 6) : a + 24])
        print(f"  ${common.off2snes(a):06X} ×{len(c):2d} {sorted({x[1] for x in c})[:4]} | {ctx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
