"""ss-ed3 문안을 저본으로 한 **제안 파일** — 씬 대사(P4) 번역의 첫 단계.

    python3 tools/propose_ss.py                # 제안 → work/review/ed3-prop/<키>.json (⚠ 커밋 금지: 원문이 든다)
    python3 tools/propose_ss.py --stats        # 매칭 실측만
    python3 tools/propose_ss.py --apply        # 제안 파일의 kr → work/review/ed3/ 검토표(이후 script.py --sync)

짝짓기(`policy.md` 「ss-ed3 문안을 물려받을 때」):
- 정규화(공백·제어 제거, 부호 통일) 원문으로 PS1 **연속 조각 1~12개를 이어 붙여** 새턴 블록 **전체**와 맞춘다.
  새턴 문안이 하나뿐이고 줄 수가 같으면(`auto`) 줄대로 초안을 넣는다. 문안이 갈렸거나 줄 수가 다르면 초안 없이
  후보(`refs`)만 준다 — 🔴 다수결로 뭉개지 않는다(화자가 다르면 갈린 채 두는 게 정상).
- 맞는 블록이 없는 조각은 새턴 블록 **안에 든** 것을 후보로 준다.
⚠ 제안 파일엔 원문(JP)이 들어 있다 — `work/review/` 로만 나가고 커밋하지 않는다.
"""

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

MAXRUN = 12
PROP_DIR = os.path.join(common.REVIEW_DIR, "ed3-prop")


def ss_root():
    gc = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True
    ).strip()
    p = os.path.join(os.path.dirname(gc), ".claude", "worktrees", "ss-ed3", "games", "ss-ed3")
    if not os.path.isdir(os.path.join(p, "work", "derived", "map_jp")):
        raise SystemExit(f"ss-ed3 JP 덤프가 없다: {p}/work/derived/map_jp")
    return p


def norm(s):
    s = re.sub(r"[\s　]", "", s)
    return (
        s.replace("…", "・・・").replace("！", "!").replace("？", "?").replace("〜", "~").replace("～", "~")
    )


def load_saturn():
    root = ss_root()
    out = []
    for p in sorted(glob.glob(root + "/work/derived/map_jp/MAP*.json")):
        m = os.path.basename(p)[:-5]
        blocks = json.load(open(p, encoding="utf-8"))["blocks"]
        kp = f"{root}/script/{m}.json"
        kr = json.load(open(kp, encoding="utf-8")) if os.path.exists(kp) else {}
        for i, b in enumerate(blocks):
            if kr.get(str(i)):
                out.append({"map": m, "i": i, "who": b["head"], "jp": b["text"], "kr": kr[str(i)]})
    return out


def lines_of(s):
    """줄 목록 — 새턴 나레이션의 가운데 맞춤 공백(전각·반각 앞뒤 공백)은 뗀다(PS1 은 자기 정렬을 쓴다)."""
    return [t.strip(" \u3000") for t in re.split(r"[\n\f]", s) if t.strip()]


def build(stats_only=False):
    sat = load_saturn()
    idx = collections.defaultdict(list)
    for s in sat:
        idx[norm(s["jp"])].append(s)
    big = "\x00".join(norm(s["jp"]) for s in sat)
    starts, pos = [], 0
    for s in sat:
        starts.append(pos)
        pos += len(norm(s["jp"])) + 1
    import bisect

    def containing(piece, limit=3):
        out, at = [], 0
        while len(out) < limit:
            at = big.find(piece, at)
            if at < 0:
                break
            s = sat[bisect.bisect_right(starts, at) - 1]
            if s not in out:
                out.append(s)
            at += 1
        return out

    rev = {}
    for fn in sorted(glob.glob(os.path.join(common.REVIEW_DIR, "ed3", "*.json"))):
        rev[os.path.basename(fn)[:-5]] = json.load(open(fn, encoding="utf-8"))
    st = collections.Counter()
    for key, doc in rev.items():
        rows = sorted(((int(k), v) for k, v in doc["lines"].items()), key=lambda x: x[0])
        n, i = len(rows), 0
        res = {}
        while i < n:
            best, acc = None, ""
            for j in range(i, min(n, i + MAXRUN)):
                acc += norm(rows[j][1]["jp"])
                if acc in idx:
                    best = j
            if best is None:
                k, v = rows[i]
                st["miss"] += 1
                refs = []
                p = norm(v["jp"])
                if len(p) >= 6:
                    refs = [{"who": s["who"], "jp": s["jp"], "kr": s["kr"]} for s in containing(p, 2)]
                    st["contained"] += bool(refs)
                res[str(k)] = {"jp": v["jp"], "budget": v["budget"], "kr": v["kr"], "refs": refs}
                i += 1
                continue
            L = best - i + 1
            key_s = "".join(norm(rows[k][1]["jp"]) for k in range(i, best + 1))
            cands = idx[key_s]
            variants = {c["kr"] for c in cands}
            auto = len(variants) == 1
            kls = lines_of(cands[0]["kr"]) if auto else []
            jls = lines_of(cands[0]["jp"])
            # 줄 수만 같고 경계가 다르면 위치로 붙인 문안이 한 칸씩 밀린다(10-11 실측 301줄) — 줄 경계까지 같아야 자동이다
            ok = auto and len(kls) == L == len(jls) and all(
                norm(rows[i + t][1]["jp"]) == norm(jls[t]) for t in range(L)
            )
            st["run_auto" if ok else "run_manual"] += L
            for t, (k, v) in enumerate(rows[i : best + 1]):
                e = {"jp": v["jp"], "budget": v["budget"], "kr": v["kr"]}
                if ok and not v["kr"]:
                    e["kr"] = kls[t]
                    e["auto"] = True
                else:
                    e["run"] = [i, best] if L > 1 else None
                    e["refs"] = [
                        {"who": c["who"], "jp": c["jp"], "kr": c["kr"]}
                        for c in cands[: 3 if not auto else 1]
                    ]
                res[str(k)] = e
            i = best + 1
        if not stats_only:
            os.makedirs(PROP_DIR, exist_ok=True)
            with open(os.path.join(PROP_DIR, key + ".json"), "w", encoding="utf-8") as f:
                json.dump(
                    {"archive": doc["archive"], "member": doc["member"], "lines": res},
                    f,
                    ensure_ascii=False,
                    indent=1,
                )
    return st


def apply():
    """제안 파일의 kr(초안 포함) → 검토표(`work/review/ed3/`). 이후 `script.py --sync`."""
    n = 0
    for fn in sorted(glob.glob(os.path.join(PROP_DIR, "*.json"))):
        prop = json.load(open(fn, encoding="utf-8"))
        rp = os.path.join(common.REVIEW_DIR, "ed3", os.path.basename(fn))
        doc = json.load(open(rp, encoding="utf-8"))
        for k, v in prop["lines"].items():
            if v.get("kr") and k in doc["lines"]:
                doc["lines"][k]["kr"] = v["kr"]
                n += 1
        json.dump(doc, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return n


TASK_DIR = os.path.join(common.REVIEW_DIR, "ed3-task")
OUT_DIR = os.path.join(common.REVIEW_DIR, "ed3-out")
JP_RE = re.compile("[\u3040-\u30ff\u31f0-\u31ff\u4e00-\u9fff\uff66-\uff9f\ufffd]")


def tasks():
    """제안 파일 → 번역가용 작업표(`work/review/ed3-task/<키>.txt`). 확정(✓)·미정(◻)을 가르고 참조 블록은 한 번만 적는다."""
    os.makedirs(TASK_DIR, exist_ok=True)
    n = 0
    for fn in sorted(glob.glob(os.path.join(PROP_DIR, "*.json"))):
        key = os.path.basename(fn)[:-5]
        doc = json.load(open(fn, encoding="utf-8"))
        rows = sorted(((int(k), v) for k, v in doc["lines"].items()), key=lambda x: x[0])
        refs, ids = [], {}
        for _, v in rows:
            for r in v.get("refs") or []:
                k = (r["jp"], r["kr"])
                if k not in ids:
                    ids[k] = len(refs) + 1
                    refs.append(r)
        todo = sum(1 for _, v in rows if not v["kr"])
        out = [f"# {key}  {doc['member']}  줄 {len(rows)} · 번역할 줄(◻) {todo}", ""]
        if refs:
            out.append("## 참조 블록 (ss-ed3 — 같은 원문이거나 원문을 포함한 블록. who=새턴 화자 머리값, \\f=페이지, \\n=줄)")
            for k, r in enumerate(refs, 1):
                jp = r["jp"].replace("\n", "\\n").replace("\f", "\\f")
                kr = r["kr"].replace("\n", "\\n").replace("\f", "\\f")
                out.append(f"R{k} who={r['who']}\n  JP {jp}\n  KR {kr}")
            out.append("")
        out.append("## 줄  (색인 | 칸 | 상태 | 원문 | 참조·초안)")
        for k, v in rows:
            tag = "✓" if v["kr"] else "◻"
            rr = " ".join(f"R{ids[(r['jp'], r['kr'])]}" for r in v.get("refs") or [])
            kr = f" => {v['kr']}" if v["kr"] else ""
            out.append(f"{k} | {v['budget'].split('칸')[0]} | {tag} | {v['jp']}{kr}" + (f"   [{rr}]" if rr else ""))
        with open(os.path.join(TASK_DIR, key + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        n += 1
    return n


def collect(keys=None):
    """`ed3-out/<키>.tsv`(색인<TAB>문안) → 제안 파일 kr 에 덮는다. 반환 (옮긴 줄, [문제])."""
    moved, bad = 0, []
    for fn in sorted(glob.glob(os.path.join(OUT_DIR, "*.tsv"))):
        key = os.path.basename(fn)[:-4]
        if keys and key not in keys:
            continue
        pp = os.path.join(PROP_DIR, key + ".json")
        prop = json.load(open(pp, encoding="utf-8"))
        for ln in open(fn, encoding="utf-8").read().splitlines():
            if not ln.strip() or ln.startswith("#"):
                continue
            k, _, kr = ln.partition("\t")
            if k not in prop["lines"]:
                bad.append(f"{key}[{k}]: 없는 색인")
                continue
            prop["lines"][k]["kr"] = kr.strip()
            moved += 1
        json.dump(prop, open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return moved, bad


def validate(keys=None):
    """[사유] — 빈 칸 · 일본어 잔존 · 조판 예산 · 넣을 수 없는 글자. 정본(`script.py --check`)과 같은 자."""
    import hangul_map
    import script as sc
    import textenc
    import typeset

    ok_chars = set(hangul_map.ksc_syllables()) | set(textenc.charmap("ed3").values())
    ok_chars |= set(textenc.CONTROL.values()) | set(hangul_map.punct("ed3")) | set(" \n.,?!…～「」『』()") | set(map(chr, range(33, 127)))
    bad = []
    override = {}
    for fn in sorted(glob.glob(os.path.join(PROP_DIR, "*.json"))):
        key = os.path.basename(fn)[:-5]
        if keys and key not in keys:
            continue
        doc = json.load(open(fn, encoding="utf-8"))
        override[key] = {int(k): v["kr"] for k, v in doc["lines"].items() if v["kr"].strip()}
        segs = [(int(k), v["jp"]) for k, v in doc["lines"].items()]
        fl = sc.member_floors(segs)
        for k, v in doc["lines"].items():
            kr = v["kr"]
            if not kr.strip():
                bad.append(f"{key}[{k}]: 비었다")
                continue
            if JP_RE.search(kr):
                bad.append(f"{key}[{k}]: 일본어 잔존 {kr!r}")
            for ch in kr:
                if ch not in ok_chars:
                    bad.append(f"{key}[{k}]: 넣을 수 없는 글자 {ch!r}")
                    break
            for m in typeset.violations(kr, "ed3", jp=v["jp"], floor=fl.get(int(k), 0)):
                bad.append(f"{key}[{k}]: {m}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tasks", action="store_true", help="번역가용 작업표")
    ap.add_argument("--collect", nargs="*", metavar="키", help="ed3-out/*.tsv → 제안 파일(키 생략하면 전부)")
    ap.add_argument("--validate", nargs="*", metavar="키", help="제안 파일 검사(키 생략하면 전부)")
    a = ap.parse_args()
    if a.tasks:
        print(f"작업표 {tasks()} 파일 → {TASK_DIR}")
        return 0
    if a.collect is not None:
        m, bad = collect(set(a.collect) or None)
        print(f"제안 파일에 옮긴 줄 {m}")
        for b in bad:
            print("  🔴", b)
        return 1 if bad else 0
    if a.validate is not None:
        bad = validate(set(a.validate) or None)
        for b in bad[:60]:
            print("  🔴", b)
        print(f"문제 {len(bad)}건")
        return 1 if bad else 0
    if a.apply:
        print(f"검토표로 옮긴 줄 {apply()}")
        return 0
    st = build(stats_only=a.stats)
    print(dict(st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
