"""**우리 문안**을 외부 맞춤법 검사기에 돌려 띄어쓰기·오타를 잡는다 — ss-ed3 어댑터.

분류·API·보고서는 공용 엔진 `shared/text/spellcheck.py` 가 한다. 여기서는 이 게임 몫만
맡는다 — 코퍼스를 어디서 긁는지(`script/MAP*.json`), 어디에 쓰는지(REVIEW_DIR),
채택분을 **어디에 반영하는지**.

🔴 **ps1 과 반영 자리가 다르다.** 거기는 정발 문안이 원본에서 파생되니 치환표
(`dos_spelling_fixes.json`)가 필요했지만, 여기는 **`script/` 가 곧 정본**이라 고친 문장을
그 자리에 바로 쓴다. 표를 하나 더 두면 「어느 쪽이 진짜인가」가 갈린다(DRY).

🔴 **낱말 치환이 아니라 문장 치환**이다. 전역 리터럴 치환은 사정거리가 넓어 엉뚱한 데
걸린다(공용 엔진이 `MIN_LEN`·`CONTEXT_SENSITIVE` 로 막는 게 그 위험이다). 여기서는
**그 문장의 치환쌍이 전부 A급일 때만 그 문장을 통째로** 바꾼다 — 사정거리가 그 자리뿐이다.

⚠ **예산이 는다.** 띄어쓰기를 넣으면 반각 한 자(1B)가 더 든다. 문장 단위로 바꾼 뒤
`reinsert.py --check` 가 막으면 그 블록만 되돌린다(`--apply` 가 자동으로 한다).

⚠ 외부 서비스에 **우리 한국어 문안**을 보낸다(원문이 아니다). 역번역 대조와 같은 부류다.

    python3 games/ss-ed3/tools/spellcheck_kr.py --limit 5   # 시험 (앞 5청크)
    python3 games/ss-ed3/tools/spellcheck_kr.py             # 전량
    python3 games/ss-ed3/tools/spellcheck_kr.py --report    # 캐시로 보고서만
    python3 games/ss-ed3/tools/spellcheck_kr.py --apply     # A급 문장을 script 에 반영
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_REPO, "shared"))

import check_fidelity as CF
import common as C
from text import spellcheck as sc

SEG = re.compile(r"[\n\f]")
SCRIPT = os.path.join(C.GAME_DIR, "script")
CACHE = os.path.join(C.REVIEW_DIR, "spell_cache.json")
REPORT = os.path.join(C.REVIEW_DIR, "spell_report.md")
ACCEPT = os.path.join(C.GAME_DIR, "spell_accept.json")


def collect():
    """`{문장: {"n": 등장 수, "inject": 주입코드 있나}}` — 블록을 개행으로 쪼갠 조각."""
    uniq = {}
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, v in d.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            for s in SEG.split(v):
                s = s.strip()
                if not s:
                    continue
                rec = uniq.setdefault(s, {"n": 0, "inject": "%" in s})
                rec["n"] += 1
    return uniq


def gloss_words():
    """정본 표기 조각들 — 검사기가 **되돌리려 드는** 자리다.

    🔴 이 게임의 고유명사는 **일부러 붙여 쓴다** — 「하얀마녀」·「사막의흑표」·「매발톱호」.
      이름은 **가장 좁은 칸에 맞춰 하나로** 정했기 때문이다(게임 `CLAUDE.md`). 그런데
      맞춤법 검사기는 이걸 죄다 띄어 놓는다(`하얀마녀`→`하얀 마녀`). **A급(공백만 차이)에
      정확히 걸리는 꼴**이라 자동 채택에 그냥 실려 온다 — 실측 4 건 중 3 건이 그랬다.
      정본을 검사기가 뒤집게 두면 `check_fidelity` 와 정면으로 싸운다.
    """
    out = set()
    for v in CF.load_gloss().values():
        out.add(v)
        out.add(v.replace(" ", ""))
    return {w for w in out if len(w) >= 2}


def touches_gloss(x, y, words):
    """치환쌍이 정본 표기를 건드리나 — 공백을 지운 꼴로 본다."""
    nx = sc.nospace(x)
    return any(w in nx for w in words if sc.nospace(w) in nx)


def accepted():
    """받아들이기로 한 치환쌍 — **커밋되는 정본**(`spell_accept.json`)."""
    with open(ACCEPT, encoding="utf-8") as f:
        return {tuple(p) for p in json.load(f)["replace"]}


def sentence_fixes(changed, ok):
    """문장별 채택안 — **그 문장의 치환쌍이 전부 정본에 있을 때만**.

    🔴 A급(공백만 차이) 전체를 받지 않는다. 실측 95 중 대부분이 틀렸다 —
      `-는걸`·`-고말고` 는 어미라 붙여 쓰는 게 맞는데 검사기가 가르고,
      `안절부절못한다` 를 `안 절부절못한다` 로 만든다. 판단은 사람이 하고 여기 박는다.
    """
    out = {}
    for a, b, _ in changed:
        pairs = sc.min_pairs(a, b)
        if pairs and all(p in ok for p in pairs):
            out[a] = b
    return out


def apply_fixes(fix):
    """`script/` 에 문장 치환을 반영 — `(고친 블록 수, 파일 수)`."""
    nb = nf = 0
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        ch = False
        for k, v in d.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            parts = SEG.split(v)
            seps = SEG.findall(v)
            new = [fix.get(p.strip(), p.strip()) if p.strip() else p for p in parts]
            #   ⚠ 앞뒤 공백은 원문 조각 그대로 둔다 — 조판이 그걸 센다.
            for i, p in enumerate(parts):
                if p.strip() and new[i] != p.strip():
                    new[i] = p.replace(p.strip(), new[i], 1)
                else:
                    new[i] = p
            s = "".join(x + (seps[i] if i < len(seps) else "") for i, x in enumerate(new))
            if s != v:
                d[k] = s
                nb += 1
                ch = True
        if ch:
            nf += 1
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    return nb, nf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=900, help="요청당 최대 글자 수")
    ap.add_argument("--jobs", type=int, default=4, help="동시 요청 수")
    ap.add_argument("--limit", type=int, default=0, help="요청 청크 수 제한(시험용)")
    ap.add_argument("--report", action="store_true", help="API 호출 없이 캐시로 보고서만")
    ap.add_argument("--apply", action="store_true", help="A급 문장을 script 에 반영")
    a = ap.parse_args()

    os.makedirs(C.REVIEW_DIR, exist_ok=True)
    uniq = collect()
    keys = sorted(uniq)
    meta = {s: {"n": v["n"], "inject": v["inject"]} for s, v in uniq.items()}
    print(f"문장 {len(keys):,}종 · 총 등장 {sum(v['n'] for v in uniq.values()):,}")

    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}

    def save(c):
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)

    parts = sc.chunks(keys, a.chunk)
    todo = [p for p in parts if "\n".join(p) not in cache]
    print(
        f"  청크 {len(parts)} · 캐시 {len(parts) - len(todo)} · 요청 {0 if a.report else len(todo)}"
    )
    if not a.report:
        sc.fetch(parts[: a.limit] if a.limit else parts, cache, jobs=a.jobs, on_save=save)

    changed, pairs, skewed = sc.collate(parts, cache, meta)
    auto, manual, dropped = sc.classify(pairs)
    words = gloss_words()
    guarded = [t for t in auto if touches_gloss(t[0], t[1], words)]
    auto = [t for t in auto if t not in guarded]
    manual = guarded + manual
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(
            sc.report(
                "ss-ed3 우리 문안 맞춤법 검사 (engram, proof)",
                len(keys),
                changed,
                auto,
                manual,
                dropped,
                skewed,
            )
        )
    fix = sentence_fixes(changed, accepted())
    print(
        f"  제안 있음 {len(changed)} · A급 쌍 {len(auto)} · B급 쌍 {len(manual)}"
        f" · 부호공백 버림 {dropped} · 정본 보호 {len(guarded)}"
    )
    print(
        f"  → 정본이 받아들인 쌍으로 바꿀 문장 {len(fix)}  ({os.path.relpath(REPORT, C.WORK_DIR)})"
    )
    if skewed:
        print(f"  ⚠ 줄 대응이 깨진 청크 {skewed}")

    if a.apply:
        nb, nf = apply_fixes(fix)
        print(f"  ✅ script 반영 — 블록 {nb} · 파일 {nf}")
        print("  ⚠ 이제 `reinsert.py --check` 로 예산을 본다")
    else:
        top = collections.Counter({k: meta[k]["n"] for k in fix})
        for s, n in top.most_common(15):
            print(f"     {n:>3}회  {s[:34]!r} → {fix[s][:34]!r}")


if __name__ == "__main__":
    main()
