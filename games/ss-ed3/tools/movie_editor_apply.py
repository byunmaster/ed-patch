"""영상 자막 편집기에서 바꾼 것을 `script/movie.json` 에 반영한다.

    python3 games/ss-ed3/tools/movie_editor_apply.py edits.json [--adds adds.json]          # 무엇이 바뀌나만 본다
    python3 games/ss-ed3/tools/movie_editor_apply.py edits.json [--adds adds.json] --write  # movie.json 에 쓴다

`edits.json` 은 편집기 db `edits` 목록이다. 항목은 `scene`(M01…)·`idx`(편집기 자료의 줄 번호, 1부터)로 칸을 가리키고 아래만 읽는다:

    kr   자막 문안 — 줄바꿈 `\\n`. 빈 줄이 든 문안은 거부한다.
    ts / te   열림·닫힘 시각(초). 닫힘이 열림보다 앞이면 거부한다.
    comment   읽기만 하고 안 쓴다(보고용).

idx 가 `a…` 인 항목은 편집기에서 **추가한 줄**의 고침이다 — `--adds`(db `adds`) 목록의 같은 `aid` 줄에 덧씌운다.
기존 줄의 idx 는 **추가 전 순서**다. 추가 줄은 열림 시각 순서로 끼운다.
`_fixed`(마스터가 확정한 열림 시각) 는 열림 시각이 바뀐 줄이면 새 시각으로 옮긴다.
문안은 폭·줄 수를 여기서 안 잰다 — 굽기(`movie_hardsub.py`)가 잰다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")


def merge_adds(adds, edits):
    """`(추가 줄 목록, 기존 줄 edits)` — idx 가 `a…` 인 edits 를 같은 `aid` 의 추가 줄에 덧씌운다."""
    byid = {a["aid"]: dict(a) for a in adds}
    plain = []
    for e in edits:
        if str(e["idx"]).startswith("a"):
            if e["idx"] in byid:
                byid[e["idx"]].update({k: v for k, v in e.items() if k not in ("scene", "idx", "at")})
        else:
            plain.append(e)
    return list(byid.values()), plain


def _text(scene, where, kr):
    # 편집기 입력칸 끝에 딸려 오는 줄바꿈·공백은 버린다(10-21 M18 #14 — 끝 `\n` 하나로 반영이 거부될 뻔했다). 가운데 빈 줄은 여전히 거부
    lines = [x.strip() for x in str(kr).strip().split("\n")]
    if not lines or any(not x for x in lines):
        raise SystemExit(f"{scene} {where}: 빈 줄이 든 문안은 못 받는다")
    return "\n".join(lines)


def apply(doc, edits, adds=()):
    """`(바뀐 줄 수, 메모)` — `doc` 을 제자리에서 고친다. 거부 사유가 있으면 `SystemExit`."""
    adds, edits = merge_adds(list(adds), edits)
    changed, notes = 0, []
    fixed = doc.setdefault("_fixed", {})
    for e in edits:
        sc, idx = e["scene"], int(e["idx"])
        rows = doc.get(sc)
        if not rows or sc.startswith("_"):
            raise SystemExit(f"{sc}: 없는 편")
        if not 1 <= idx <= len(rows):
            raise SystemExit(f"{sc} #{idx}: 칸이 없다(1~{len(rows)})")
        row = rows[idx - 1]
        before = list(row)
        a, b, t = row
        if "kr" in e:
            t = _text(sc, f"#{idx}", e["kr"])
        na, nb = float(e.get("ts", a)), float(e.get("te", b))
        if nb <= na:
            raise SystemExit(f"{sc} #{idx}: 닫힘({nb}) 이 열림({na}) 보다 앞이다")
        row[:] = [round(na, 2), round(nb, 2), t]
        if round(a, 2) in [round(x, 2) for x in fixed.get(sc, [])] and round(na, 2) != round(a, 2):
            fixed[sc] = [round(na, 2) if round(x, 2) == round(a, 2) else x for x in fixed[sc]]
        if row != before:
            changed += 1
    for ad in adds:
        sc = ad["scene"]
        if not doc.get(sc) or sc.startswith("_"):
            raise SystemExit(f"{sc}: 없는 편(줄 추가는 자막이 있는 편만)")
        ts, te = float(ad["ts"]), float(ad["te"])
        if te <= ts:
            raise SystemExit(f"{sc} {ad['aid']}: 닫힘({te}) 이 열림({ts}) 보다 앞이다")
        row = [round(ts, 2), round(te, 2), _text(sc, ad["aid"], ad.get("kr", ""))]
        rows = doc[sc]
        i = next((k for k, x in enumerate(rows) if x[0] > row[0]), len(rows))
        rows.insert(i, row)
        changed += 1
    if adds:
        notes.append(f"추가한 줄 {len(adds)}개를 끼웠다")
    for sc in {e["scene"] for e in edits} | {a["scene"] for a in adds}:
        rows = doc[sc]
        if any(x[0] > y[0] for x, y in zip(rows, rows[1:], strict=False)):
            notes.append(f"{sc}: ⚠ 열림 시각이 오름차순이 아니다 — 굽기 전에 순서를 본다")
    return changed, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edits")
    ap.add_argument("--adds", help="편집기 `adds` 목록 JSON — 추가한 줄(없으면 생략)")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    with open(a.edits, encoding="utf-8") as f:
        edits = json.load(f)
    adds = []
    if a.adds:
        with open(a.adds, encoding="utf-8") as f:
            adds = json.load(f)
    with open(SCRIPT, encoding="utf-8") as f:
        doc = json.load(f)
    n, notes = apply(doc, edits, adds)
    print(f"편집 {len(edits)}건 · 추가 {len(adds)}줄 · 실제로 바뀐 줄 {n}")
    for x in notes:
        print(" ", x)
    if a.write:
        with open(SCRIPT, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("movie.json 에 썼다 — 다음은 movie_hardsub.py(다시 굽기) · build.py · check.sh")
    else:
        print("(미리보기 — 쓰려면 --write)")


if __name__ == "__main__":
    main()
