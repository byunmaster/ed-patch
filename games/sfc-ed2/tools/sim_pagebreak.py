"""쪽 나눔(문장 단위) 규칙의 영향을 센다 — 대사 $C2~$CB 전 구간을 빌드와 같은 길로 조판해 규칙 끔/켬을 비교한다(원판 롬은 읽기만).

`python3 games/sfc-ed2/tools/sim_pagebreak.py [--list 바뀐구간.txt]` — 바뀐 구간 수 · 쪽 수가 느는 구간 · 쪽 사이에서 문장이 갈리는 자리(규칙 전/후)."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import segs
import typeset as T


def run(rule: bool) -> tuple[dict, dict]:
    T.RULE = rule
    src = common.rom_bytes()
    seg_map, _, dict_map = build.collect_texts(src)
    names = build.dict_names(src, dict_map)
    e1w = build.e1_texts(src, seg_map)
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
    res, spl, end = {}, {}, {}
    for key, v in sorted(seg_map.items()):
        a, b = sg[key]
        if not (0xC2 <= (common.off2snes(a) >> 16) <= 0xCB) or v.get("raw"):
            continue
        text = build.resolve_josa(v["kr"], names)
        tw = {**names, **e1w, **build.call_texts(text, a, seg_map, sg)}
        pv = end.get(a)
        res[key] = T.typeset(text, tw, T.end_state(pv[0], pv[1]) if pv else None)
        end[b] = (res[key], tw)
        spl[key] = list(T.SPLITS)
    T.RULE = True
    return res, spl


def main() -> None:
    off, soff = run(False)
    on, son = run(True)
    ch = [k for k in off if off[k] != on[k]]
    more = [k for k in ch if on[k].count("<05>") > off[k].count("<05>")]
    print(f"구간 {len(off):,} · 쪽 나눔 바뀐 구간 {len(ch)} · 쪽 수 늘어난 {len(more)} {more} · 줄어든 {sum(1 for k in ch if on[k].count('<05>') < off[k].count('<05>'))}")
    for name, sp in (("규칙 전", soff), ("규칙 후", son)):
        print(f"  {name} 쪽 사이 문장 갈림:", dict(Counter(x[0] for k in sp for x in sp[k])), "(auto-pgstart·auto-long = 문장이 한 쪽보다 길다 · hand = 손 개행)")
    if len(sys.argv) > 2 and sys.argv[1] == "--list":
        Path(sys.argv[2]).write_text("\n".join(k[1:] for k in ch) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
