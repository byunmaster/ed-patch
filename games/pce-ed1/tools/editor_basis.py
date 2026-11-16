#!/usr/bin/env python3
"""편집기 기준 도구(마스터 11-10 「이전 자막데이터는 편집기 기준으로」) — 정답은 「마스터가 지금 편집기에서 보는 값」 = 게시본 data.json 의 행(clip·idx) + 같은 키 `{clip}-{idx}` 의 DB 편집.

  renumber <data.json> <db edits 폴더> <out 폴더>   토막별 행 번호를 시각 순 1..N 으로 다시 매긴다(편집 내용 불변) → out/data.json · out/idx-map.json · out/orphans.json · out/check.json
  view     <data.json> <db edits 폴더> <out 폴더>   편집기 화면 값(게시본+DB)을 **현재 생성본(시각표) 번호**의 편집 문서로 풀어 `voice_editor_apply --sched` 에 먹인다(열쇠·쪽으로 맞댐)

번호 규칙: 효과 시작(DB ts 가 있으면 그것, 없으면 행 t_start)순, 같으면 옛 idx 순. 끝 시각이 900 이상(마스터가 화면 밖으로 민 「뺄 줄」)은 맨 뒤에 옛 순서로.
"""

import glob
import hashlib
import json
import sys
from pathlib import Path


def _load(data_json: str, db_dir: str):
    d = json.loads(Path(data_json).read_text("utf-8"))
    rows = d["rows"] if isinstance(d, dict) else d
    clips = d["clips"] if isinstance(d, dict) else []
    db = {}
    for f in glob.glob(str(Path(db_dir) / "*.json")):
        x = json.loads(Path(f).read_text("utf-8"))
        x.pop("_version", None)
        db[(x["clip"], x["idx"])] = x
    return rows, clips, db


def _eff(r, d):
    ts = d.get("ts", r.get("t_start"))
    te = d.get("te", r.get("t_end"))
    return ts, te


def renumber(data_json: str, db_dir: str, out: str) -> dict:
    rows, clips, db = _load(data_json, db_dir)
    pub = {(r["clip"], r["idx"]) for r in rows}
    # DB 에만 있는 추가 행(added)은 행으로 만들어 끼운다(게시본에 없는 x 행)
    for (clip, idx), d in sorted(db.items()):
        if (clip, idx) not in pub and d.get("added") and idx >= 1000:
            base = next((r for r in rows if r["clip"] == clip), None)
            if base is None:
                continue
            nr = dict(base)
            nr.update(
                {
                    "idx": idx,
                    "key": f"x{idx}",
                    "page": 1,
                    "jp": "",
                    "kr": d.get("kr", ""),
                    "stt": "",
                    "speaker_name": d.get("spk", ""),
                    "t_start": d.get("ts"),
                    "t_end": d.get("te"),
                    "added": True,
                    "draft": True,
                    "approx": True,
                }
            )
            nr.pop("dup_of", None)
            rows.append(nr)
            pub.add((clip, idx))
    # 편집기 화면에 보이는 행 = ① added 가 아닌 생성 행 ② added 생성 행 중 같은 키 DB 문서가 있는 것 ③ DB 의 added 문서. added·DB 없음 행은 onSnapshot 때 dropRow 로 지워져 안 보인다(편집기 코드 11-10)
    hidden = [r for r in rows if r.get("added") and (r["clip"], r["idx"]) not in db]
    rows = [r for r in rows if not (r.get("added") and (r["clip"], r["idx"]) not in db)]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["clip"], []).append(r)
    idx_map: dict[str, str] = {}
    new_rows = []
    for clip, rs in by.items():

        def sk(r, clip=clip):
            ts, te = _eff(r, db.get((clip, r["idx"]), {}))
            hid = te is not None and te >= 900
            return (hid, ts if (ts is not None and not hid) else 0.0, r["idx"])

        rs2 = sorted(rs, key=sk)
        for n, r in enumerate(rs2, 1):
            idx_map[f"{clip}-{r['idx']}"] = f"{clip}-{n}"
            nr = dict(r)
            nr["idx"] = n
            new_rows.append(nr)
    for nr in new_rows:  # 같은 음성을 쓰는 짝 토막 참조(dup_of = 「토막-idx」)도 새 번호로
        if nr.get("dup_of") and nr["dup_of"] in idx_map:
            nr["dup_of"] = idx_map[nr["dup_of"]]
    new_rows.sort(key=lambda r: (r["scene"], r["clip"], r["idx"]))
    cnt = {}
    for r in new_rows:
        cnt[r["clip"]] = cnt.get(r["clip"], 0) + 1
    new_clips = []
    for c in clips:
        c = dict(c)
        c["rows"] = cnt.get(c["clip"], c.get("rows"))
        new_clips.append(c)
    orphans = [
        {"old_key": f"{c}-{i}", **{k: v for k, v in d.items() if k in ("ts", "te", "spk", "kr")}}
        for (c, i), d in sorted(db.items())
        if (c, i) not in pub
    ]
    moved_db = {f"{c}-{i}": idx_map[f"{c}-{i}"] for (c, i) in sorted(db) if f"{c}-{i}" in idx_map}

    def h(rs, fn):
        return hashlib.sha1(
            json.dumps(sorted(fn(r) for r in rs), ensure_ascii=False).encode()
        ).hexdigest()[:12]

    def text_of(r, key):
        return [r["clip"], r["key"], r["page"], r.get("kr", "")]

    old_view = {
        (r["clip"], r["key"], r["page"]): _eff(r, db.get((r["clip"], r["idx"]), {}))
        + (db.get((r["clip"], r["idx"]), {}).get("spk", r.get("speaker_name")),)
        for r in rows
    }
    new_view = {}
    for r in new_rows:
        o = next(k for k, v in idx_map.items() if v == f"{r['clip']}-{r['idx']}")
        oc, oi = o.rsplit("-", 1)
        new_view[(r["clip"], r["key"], r["page"])] = _eff(r, db.get((oc, int(oi)), {})) + (
            db.get((oc, int(oi)), {}).get("spk", r.get("speaker_name")),
        )
    chk = {
        "행 수 전": len(rows),
        "행 수 후": len(new_rows),
        "문안 해시 전": h(rows, lambda r: text_of(r, 0)),
        "문안 해시 후": h(new_rows, lambda r: text_of(r, 0)),
        "시각·화자 해시 전": hashlib.sha1(
            json.dumps(sorted(map(str, old_view.items()))).encode()
        ).hexdigest()[:12],
        "시각·화자 해시 후": hashlib.sha1(
            json.dumps(sorted(map(str, new_view.items()))).encode()
        ).hexdigest()[:12],
        "옮긴 DB 키": len(moved_db),
        "added 행 중 DB 짝 없음": sum(
            1
            for r in new_rows
            if r.get("added")
            and not any(
                f"{r['clip']}-" in k and v == f"{r['clip']}-{r['idx']}" for k, v in moved_db.items()
            )
        ),
        "안 보이던 행(빼냄)": len(hidden),
        "고아 DB 편집": len(orphans),
    }
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "data.json").write_text(
        json.dumps({"rows": new_rows, "clips": new_clips}, ensure_ascii=False), "utf-8"
    )
    (o / "idx-map.json").write_text(
        json.dumps({"rows": idx_map, "db_keys": moved_db}, ensure_ascii=False, indent=1), "utf-8"
    )
    (o / "orphans.json").write_text(json.dumps(orphans, ensure_ascii=False, indent=1), "utf-8")
    (o / "hidden.json").write_text(
        json.dumps(
            [
                {
                    "clip": r["clip"],
                    "old_idx": r["idx"],
                    "key": r["key"],
                    "kr": r.get("kr"),
                    "t": [r.get("t_start"), r.get("t_end")],
                }
                for r in hidden
            ],
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )
    (o / "check.json").write_text(json.dumps(chk, ensure_ascii=False, indent=1), "utf-8")
    return chk


def view(data_json: str, db_dir: str, out: str) -> int:
    """편집기 화면 값(게시본 행 + 같은 키 DB 편집)을 현재 생성본(시각표 행) 번호의 편집 문서로 풀어 `out/` 에 쓴다 — `voice_editor_apply.py <out> --sched` 에 먹인다.
    맞대는 열쇠 = (씬, 메시지 키, 쪽). 생성본에 대응 행이 없으면 건너뛴다. 추가 행(DB `added`, idx≥1000)은 그대로 문서로 둔다."""
    import collections
    import re

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import voice_editor_data as D

    rows, _clips, db = _load(data_json, db_dir)
    B = collections.defaultdict(list)
    for r in D.build()[0]:
        if r.get("sched") and r["idx"] < 1000:
            B[(r["scene"], r["key"], r["page"])].append(r)
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for f in o.glob("*.json"):
        f.unlink()
    n = 0
    for r in rows:
        if r["idx"] >= 1000:  # 🔴 `sched` 딱지는 보지 않는다 — 게시본 행 일부(씬 34 g0 등)에 딱지가 없어 마스터 시각이 통째로 건너뛰였다(11-11). 생성본(B)에 짝이 있는 행만 쓴다
            continue
        d = db.get((r["clip"], r["idx"]), {})
        ts, te = _eff(r, d)
        cands = B.get((r["scene"], r["key"], r["page"]), [])
        if not cands:
            continue
        c = ([x for x in cands if x["clip"] == r["clip"]] or cands)[0]
        doc = {"clip": c["clip"], "idx": c["idx"], "ts": ts, "te": te}
        if d.get("spk"):
            doc["spk"] = d["spk"]
        (o / f"{c['clip']}-{c['idx']}.json").write_text(
            json.dumps(doc, ensure_ascii=False), "utf-8"
        )
        n += 1
    for (clip, idx), d in db.items():
        if d.get("added") and idx >= 1000:
            d = dict(d)
            if re.match(r"scn177_x0$", clip):
                d["clip"] = "scn177_s0"
            (o / f"{d['clip']}-{idx}.json").write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    return n


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "renumber":
        print(json.dumps(renumber(*sys.argv[2:5]), ensure_ascii=False, indent=1))
    elif len(sys.argv) == 5 and sys.argv[1] == "view":
        print(view(*sys.argv[2:5]), "문서")
    else:
        print(__doc__)
