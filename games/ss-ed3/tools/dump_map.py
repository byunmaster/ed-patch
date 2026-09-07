"""`/MAP/MAP*.BIN` 88 파일을 전부 덤프한다 — 원문·구조를 `work/derived/map_jp/` 로.

    python3 games/ss-ed3/tools/dump_map.py            # 덤프 + 라운드트립 확인
    python3 games/ss-ed3/tools/dump_map.py --check    # 확인만(안 쓴다)
    python3 games/ss-ed3/tools/dump_map.py --disc 2   # 두 번째 디스크로

🔴 **라운드트립을 매번 본다** — 「블록을 도로 끼워 넣으면 원본과 바이트 동일한가」.
   경계를 한 칸 잘못 잡으면 재삽입이 옆 바이트를 조용히 먹는다(이 레포의 단골 사고).

⚠ 산출물은 **원문을 담는다** — `work/derived` 는 gitignore 다. 커밋하지 않는다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M

OUT = os.path.join(C.OUT_DIR, "map_jp")


def dump_one(b):
    #   ⚠ **헤더가 없는 맵이 하나 있다** — `MAP077` 은 데이터가 `.FON` 에 있고(`common.MAP_EXTRA`)
    #     그 파일엔 매직·포인터표가 없다. 헤더는 「있으면 적는다」로 두고 **블록은 그대로 뜬다.**
    try:
        ptrs, name = M.parse_header(b)
    except ValueError:
        ptrs, name = [], ""
    bl = M.blocks(b)
    return {
        "size": len(b),
        "map_name": name,
        "ptrs": ptrs,
        "blocks": [
            {"off": x["off"], "head": x["head"], "term": x["term"], "text": M.text_of(x["body"])}
            for x in bl
        ],
    }, bl


def rebuild(b, bl):
    """덤프한 블록을 원래 자리에 도로 써 넣는다 — 원본과 같아야 한다."""
    out = bytearray(b)
    for x in bl:
        body = M.encode_text(M.text_of(x["body"]))
        out[x["off"] : x["off"] + len(x["body"])] = body
        if len(body) != len(x["body"]):
            raise AssertionError(f"길이가 변했다 @{x['off']:#x}")
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=1, choices=C.DISCS)
    ap.add_argument("--check", action="store_true", help="쓰지 않고 라운드트립만 본다")
    a = ap.parse_args()

    if not a.check:
        os.makedirs(OUT, exist_ok=True)
    nb = nfile = nchar = 0
    fails = []
    with C.open_disc(a.disc) as d:
        files = [(n, l, s) for n, l, s in d.files() if C.is_map_file(n)[0]]
        for n, l, s in files:
            b = d.read_extent(l, s)
            try:
                rec, bl = dump_one(b)
            except ValueError as e:
                fails.append((n, f"헤더: {e}"))
                continue
            if rebuild(b, bl) != b:
                fails.append((n, "라운드트립 불일치"))
                continue
            nfile += 1
            nb += len(bl)
            nchar += sum(len(x["text"]) for x in rec["blocks"])
            if not a.check:
                stem = C.is_map_file(n)[1]
                with open(os.path.join(OUT, f"{stem}.json"), "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=1)

    print(f"disc{a.disc}  파일 {nfile}/{len(files)}  블록 {nb:,}  글자 {nchar:,}")
    if fails:
        print(f"❌ 실패 {len(fails)}")
        for n, why in fails[:10]:
            print(f"   {n} — {why}")
        raise SystemExit(1)
    print("✅ 전 파일 라운드트립 통과" + ("" if a.check else f" → {OUT}"))


if __name__ == "__main__":
    main()
