"""이미 옮긴 대사를 **원문이 같은 자리**에 다시 쓴다.

    python3 games/ss-ed3/tools/reuse_tr.py --dry        # 무엇이 채워지나만 본다
    python3 games/ss-ed3/tools/reuse_tr.py              # 전 맵에 채운다
    python3 games/ss-ed3/tools/reuse_tr.py MAP004       # 그 맵만

원본은 같은 대사를 여러 맵에 그대로 복사해 뒀다 — **블록 17,586 중 고유가 71.5%,
글자로는 21%(9.3만 자)가 중복**이다(전투 중 대사·간판·「응.」 같은 맞장구). 손으로 다시
옮기면 그만큼 **표기가 갈릴 뿐**이라, 원문이 **한 글자도 다르지 않을 때만** 그대로 쓴다.

⚠ 자동으로 채운 자리도 **화면 검증 대상**이다 — 같은 대사를 다른 인물이 말하면 말투가
   어긋날 수 있다. `--dry` 로 먼저 보고, 어색하면 그 자리를 손으로 덮어쓴다(뒤에 채운
   것이 이긴다 — 이미 번역이 있는 블록은 건드리지 않는다).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R


def corpus(maps):
    """`{원문: 번역}` — 이미 옮긴 것 전부. 같은 원문에 번역이 갈리면 **버린다**."""
    out, clash = {}, set()
    for stem, bl in maps.items():
        kr, _ = R.load_script(stem)
        for k, v in kr.items():
            i = int(k)
            if not 0 <= i < len(bl):
                continue
            jp = M.text_of(bl[i]["body"])
            if jp in out and out[jp] != v:
                clash.add(jp)
            out[jp] = v
    for jp in clash:
        del out[jp]
    return out, clash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--dry", action="store_true")
    #   🔴 **굴리는 중인 맵을 건드리면 안 된다.** 이 도구는 **전 맵을 다시 쓴다** — 에이전트가
    #     그 맵을 옮기는 중이면 「읽고 → 옮기고 → 쓴다」 사이에 끼어들어 서로를 덮는다
    #     (2026-08-27 실측: MAP021 이 작업 중 딴 맵 문안으로 바뀌었다). `--skip` 으로 뺀다.
    ap.add_argument("--skip", nargs="*", default=[], help="지금 누가 굴리는 맵 — 건드리지 않는다")
    a = ap.parse_args()

    maps = {}
    for disc in (1, 2):
        with C.open_disc(disc) as d:
            for n, lba, size in sorted(d.files()):
                if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                    continue
                stem = os.path.basename(n)[:-4]
                if stem in a.skip:
                    continue
                if stem not in maps:
                    maps[stem] = M.blocks(d.read_extent(lba, size))

    tr, clash = corpus(maps)
    print(f"이미 옮긴 문안 {len(tr):,} 가지 (번역이 갈려 버린 것 {len(clash)})")

    total = 0
    for stem, bl in maps.items():
        if a.stems and stem not in a.stems:
            continue
        kr, _ = R.load_script(stem)
        add = {}
        for i, x in enumerate(bl):
            if str(i) in kr or M.suspect_head(x):
                continue
            jp = M.text_of(x["body"])
            if jp.strip() and jp in tr:
                add[str(i)] = tr[jp]
        if not add:
            continue
        total += len(add)
        print(f"  {stem}  +{len(add)}")
        if a.dry:
            continue
        p = os.path.join(R.SCRIPT_DIR, f"{stem}.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        else:
            d = {}
        d.update(add)
        out = {k: d[k] for k in sorted((x for x in d if not x.startswith("_")), key=int)}
        out["_jp"] = d.get("_jp", {})
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")
    print(f"{'채울 수 있는' if a.dry else '채운'} 블록 {total:,}")


if __name__ == "__main__":
    main()
