"""`script/MAP*.json` 에 원문 지문(`_jp`)을 박는다 — 「이 번역은 그 블록의 것인가」.

    python3 games/ss-ed3/tools/stamp_script.py            # 없는 것만 채운다
    python3 games/ss-ed3/tools/stamp_script.py --check    # 어긋난 것만 보고(안 쓴다)

🔴 색인만으로는 조용히 어긋난다. 블록 파서를 고치면 색인이 밀리는데 **빌드는 성공한다** —
   번역이 엉뚱한 대사 자리에 들어갈 뿐이다. 저작권상 원문은 커밋 못 하므로 sha1 앞 8자만 남긴다.
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    #   🔴 **굴리는 중인 맵을 건드리면 안 된다.** 이 도구는 **전 맵을 다시 쓴다** — 에이전트가
    #     그 맵을 옮기는 중이면 「읽고 → 옮기고 → 쓴다」 사이에 끼어들어 서로를 덮는다
    #     (2026-08-27 실측: MAP021 이 작업 중 딴 맵 문안으로 바뀌었다). `--skip` 으로 뺀다.
    ap.add_argument("--skip", nargs="*", default=[], help="지금 누가 굴리는 맵 — 건드리지 않는다")
    a = ap.parse_args()

    seen = {}
    for disc in (1, 2):
        with C.open_disc(disc) as d:
            for n, lba, size in sorted(d.files()):
                if not C.is_map_file(n)[0]:
                    continue
                stem = C.is_map_file(n)[1]
                if stem in a.skip:
                    continue
                if stem in seen:
                    continue
                seen[stem] = M.blocks(d.read_extent(lba, size))

    n_new = n_bad = 0
    for p in sorted(glob.glob(os.path.join(R.SCRIPT_DIR, "MAP*.json"))):
        stem = os.path.basename(p)[:-5]
        bl = seen.get(stem)
        if bl is None:
            print(f"⚠ {stem} — 원본에 그런 맵이 없다")
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        jp = d.get("_jp", {})
        for k in [x for x in d if not x.startswith("_")]:
            i = int(k)
            if not 0 <= i < len(bl):
                print(f"❌ {stem}:{k} — 색인이 범위 밖({len(bl)})")
                n_bad += 1
                continue
            s = R.jp_stamp(bl[i]["body"])
            if k not in jp:
                jp[k] = s
                n_new += 1
            elif jp[k] != s:
                print(f"❌ {stem}:{k} — 지문 불일치 {jp[k]} → {s}")
                n_bad += 1
        if not a.check and jp:
            d["_jp"] = jp
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
                f.write("\n")

    print(f"지문 {'확인' if a.check else '갱신'} — 새로 박은 것 {n_new} · 어긋난 것 {n_bad}")
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
