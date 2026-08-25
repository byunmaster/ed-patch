"""`BOOK*.BIN` 재삽입 — 문단 번역을 **줄로 다시 나눠** 제자리에 되끼운다.

🔴 **줄 수를 원문과 같게** 맞춰야 한다. 줄 하나가 독립 문자열이고 오프셋이 고정이라,
하나라도 남거나 모자라면 그 뒤가 통째로 어긋난다(설명문에서 배운 것과 같다).
모자라면 **빈 줄을 끝에 붙이고**, 넘치면 그 문단은 **원문을 그대로 둔다**(문안을 줄여야 한다).

⚠ 줄마다 **제 칸을 지킨다** — 남는 자리는 전각 공백, 넘치면 못 넣는다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import book as B
import common as C
import hangul_map as H
import strtab as S

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script", "book")


def table(stem):
    p = os.path.join(SCRIPT_DIR, f"{stem}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def patch(data, stem, tbl, hg):
    """`(새 bytes, 넣은 문단 수, [문제])` — 파일 크기 불변."""
    if not tbl:
        return data, 0, []
    # ⚠ **덤프가 아니라 파일에서 읽는다** — 덤프 JSON 에는 `raw` 가 없어 칸 길이를 모른다.
    #   `book.load_lines` 는 눈으로 훑는 용도고, 되끼울 땐 원본 바이트가 필요하다.
    lines = [dict(s, text=S.text_of(s["raw"])) for s in S.strings(data)]
    if not lines:
        return data, 0, []
    out = bytearray(data)
    done, bad = 0, []
    for pi, (at, rows) in enumerate(B.paragraphs(lines)):
        kr = tbl.get(str(pi))
        if kr is None:
            continue
        widths = [len(x["raw"]) for x in lines[at : at + len(rows)]]
        new, ok = B.split_to(kr, widths)
        if not ok:
            bad.append(f"{stem}[{pi}]: 원문 {sum(widths)}칸에 안 들어간다 — {kr[:24]}…")
            continue
        for k, s in enumerate(lines[at : at + len(rows)]):
            raw = H.encode_kr(new[k], hg)
            room = len(s["raw"])
            if len(raw) > room:
                bad.append(f"{stem}[{pi}] {k}번째 줄: {len(raw)}B > {room}B")
                break
            raw += "　".encode("shift_jis") * ((room - len(raw)) // 2)
            raw += b" " * (room - len(raw))
            out[s["off"] : s["off"] + room] = raw
        else:
            done += 1
    assert len(out) == len(data), (len(out), len(data))
    return bytes(out), done, bad


def main():
    hg = H.load()
    total = nbad = 0
    with C.open_disc(1) as d:
        for name, lba, size in d.files():
            if not (name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN")):
                continue
            stem = os.path.basename(name)[:-4]
            tbl = table(stem)
            if not tbl:
                continue
            b = d.read_extent(lba, size)
            new, n, bad = patch(b, stem, tbl, hg)
            total += n
            nbad += len(bad)
            print(f"  {stem}: 문단 {n} 넣음" + (f" · 문제 {len(bad)}" if bad else ""))
            for e in bad[:4]:
                print(f"     ❌ {e}")
    print(f"\n문단 {total} 넣음 · 문제 {nbad}")


if __name__ == "__main__":
    main()
