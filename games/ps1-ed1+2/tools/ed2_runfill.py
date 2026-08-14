#!/usr/bin/env python3
"""검증된 배정에서 **런을 뻗는다** — 앵커 하나를 찍으면 그 뒤는 구조가 정한다.

**왜.** 손으로 한 블록씩 짝지으면 배정 하나에 사람 눈이 한 번씩 든다. 7,378블록이니
그 속도로는 안 끝난다. 그런데 실제로 대조해 보면 **일이 그렇게 생기지 않았다** —
정발 표와 JP 씬은 **같은 순서로** 흐른다. SCN1 의 검증된 앵커를 표별로 늘어놓으면 그대로
보인다:

    T_004:  126→1  127→2  128→3  129→4  130→5  131→6  132→7  133→8
    T_000:  2→22  3→23  4→24  5→25   ·   9→35  10→36  11→37   ·   28→13  29→14  30→15

**JP 다음 블록은 정발 다음 엔트리다.** 그래서 사람이 할 일은 **런의 첫 칸을 찍는 것**이고,
나머지는 기계가 뻗는다.

`align_jp_kr` 의 전역 정렬이 이걸 못 하는 이유는 **앵커가 없기 때문**이다 — 표 전체를 한
번에 풀어서 한 칸 밀리면 그 뒤가 통째로 밀린다(실측: `T_000` 전체가 한 칸씩 밀려 있었다).
사람이 찍은 앵커에서 출발하면 그 사고가 구조적으로 안 난다.

**뻗기를 멈추는 조건**(하나라도 걸리면 그 런은 거기서 끝):

- 다음 칸이 이미 누가 물고 있다 — 런이 다른 런과 부딪혔다
- **길이비가 튄다** — 정발은 일본어의 0.55배쯤으로 나온다. 크게 벗어나면 PS1 이 창을
  쪼갰거나 정발이 합친 자리고, 그건 페이지 슬라이스라 사람이 봐야 한다

⚠ **뻗은 것은 정본이 아니라 제안이다.** 이 도구가 만드는 건 **검토 대상**이고, `--apply`
전에 `--check` 로 훑는다. 짝을 **짓는 것**보다 **읽고 맞다/아니다 하는 것**이 훨씬 싸다 —
속도는 거기서 나온다.

  python3 tools/ed2_runfill.py ED2SCN1            # 뻗을 수 있는 자리를 센다
  python3 tools/ed2_runfill.py ED2SCN1 --check    # 제안을 눈으로 (work/review/)
  python3 tools/ed2_runfill.py ED2SCN1 --twins    # 시점 사본으로 옮기기까지
  python3 tools/ed2_runfill.py ED2SCN1 --apply    # 정본에 반영
  python3 tools/ed2_runfill.py --apply            # 13씬 전부
"""

import json
import os
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_jp_kr import load_jp_scene, load_kr_scene  # noqa: E402
from common import REVIEW_DIR, ROOT  # noqa: E402

ALIGN_MAP = os.path.join(ROOT, "align_map.json")

# 길이비 — 한국어는 일본어보다 짧다(조사·압축). `align_jp_kr.KR_PER_JP` 와 같은 값.
KR_PER_JP = 0.55
LO, HI = 0.30, 1.05  # 이 밖이면 창 쪼갬/합침을 의심하고 런을 끊는다
SHORT = 8  # 짧은 문장은 길이비가 요동치니 비율을 안 본다


def _ok_len(jl, kl):
    # ⚠ **한쪽만 짧으면 자른다.** 처음엔 「짧으면 비율을 안 본다」로 뒀는데, 그 예외가
    # 정확히 **틀린 짝을 통과시키는 구멍**이었다 — `父上のところへ`(6자)가 45자짜리 정발
    # 블록에 붙었다(길이비 6.00). 조각(`그먼`·`아,`)도 같은 길로 들어온다.
    # 둘 다 짧으면 맞장구 대사끼리라 통과, 한쪽만 짧으면 창 쪼갬이라 끊는다.
    if jl <= SHORT and kl <= SHORT:
        return True
    if jl <= SHORT or kl <= SHORT:
        return False
    return LO <= kl / jl <= HI


# ⚠ **화자로는 못 거른다.** ED2 정발 덤프의 화자 라벨은 승계가 어긋나 있다 — 시녀 대사에
# `무기상` 이 붙어 있는 식이다(`T_003` 실측). 게이트로 쓰면 맞는 런까지 죽는다.


def propose(scn):
    """[(jp_eid, table, kr_eid, 길이비)] — 앵커에서 뻗은 제안."""
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    kr_tables = load_kr_scene("ED2", n)
    doc = json.load(open(ALIGN_MAP, encoding="utf-8"))
    got = doc.get(scn, {})

    jp_ids = sorted(x for x in jp if jp[x]["body"].strip())
    nxt_jp = {a: b for a, b in zip(jp_ids, jp_ids[1:], strict=False)}
    taken_jp = {int(x) for x in got}
    taken_kr = {(v["table"], v["entry_id"]) for v in got.values()}

    out = []
    for eid, v in sorted(got.items(), key=lambda kv: int(kv[0])):
        table = v["table"]
        blocks = kr_tables.get(table)
        if not blocks:
            continue
        kr_ids = [b["id"] for b in blocks]
        nxt_kr = {a: b for a, b in zip(kr_ids, kr_ids[1:], strict=False)}
        body = {b["id"]: b for b in blocks}
        j, k = int(eid), v["entry_id"]
        while True:  # 런을 뻗는다 — 막힐 때까지
            j, k = nxt_jp.get(j), nxt_kr.get(k)
            if j is None or k is None or j in taken_jp or (table, k) in taken_kr:
                break
            jb, kb = jp[j], body[k]
            if not _ok_len(len(jb["body"]), len(kb["body"])):
                break
            taken_jp.add(j)
            taken_kr.add((table, k))
            out.append((j, table, k, len(kb["body"]) / max(1, len(jb["body"]))))
    return out


def twins(scn):
    """[(jp_eid, table, kr_eid, 유사도)] — **시점 사본으로 옮긴 제안.**

    같은 마을이 이야기 단계마다 표를 따로 갖는다(엘아스타만 `T_000`·`T_001`·`T_003`·
    `T_004`·`T_006` 다섯). JP 쪽도 같은 대사를 그 수만큼 반복한다 — 그래서 **한 벌을
    맞추면 나머지는 옮기기만 하면 된다**. 손으로 하면 같은 판단을 네 번 하는 셈이다.

    옮기는 근거는 **양쪽 본문이 다 같다**는 것이다 — JP 본문이 이미 배정된 블록과 같고,
    후보 엔트리의 정발 본문도 그 짝과 (거의) 같을 때만 짚는다. 사본 표는 문안이 미세하게
    다르므로(`평화로운 게 좋군요` / `평화가 좋군요`) 완전 일치가 아니라 유사도로 본다.
    """
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    kr_tables = load_kr_scene("ED2", n)
    doc = json.load(open(ALIGN_MAP, encoding="utf-8"))
    got = doc.get(scn, {})
    taken_kr = {(v["table"], v["entry_id"]) for v in got.values()}

    body = {(t, b["id"]): b["body"] for t, bs in kr_tables.items() for b in bs}
    # JP 본문 → 이미 배정된 (표, 엔트리)
    seen = {}
    for eid, v in got.items():
        b = jp.get(int(eid), {}).get("body", "").strip()
        if b:
            seen.setdefault(b, (v["table"], v["entry_id"]))

    out = []
    for j in sorted(jp):
        if str(j) in got:
            continue
        b = jp[j]["body"].strip()
        src = seen.get(b)
        if not src:
            continue
        want = body.get(src, "")
        if len(want) < 6:  # 너무 짧으면 사본 판별이 안 선다
            continue
        best, score = None, 0.0
        for coord, txt in body.items():
            if coord[0] == src[0] or coord in taken_kr or not txt:
                continue
            r = SequenceMatcher(None, want, txt).ratio()
            if r > score:
                best, score = coord, r
        if best and score >= 0.90:
            taken_kr.add(best)
            out.append((j, best[0], best[1], score))
    return out


def report(scn, rows, verbose=False):
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    body = {}
    for t, blocks in load_kr_scene("ED2", n).items():
        for b in blocks:
            body[(t, b["id"])] = b["body"]
    lines = []
    for j, t, k, r in rows:
        lines.append(f"jp{j} → {t}#{k}  (길이비 {r:.2f})")
        lines.append(f"    JP  {jp[j]['body'][:88]}")
        lines.append(f"    KR  {body[(t, k)][:88]}")
        lines.append("")
    if verbose:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, f"{scn}_runfill.txt")
        open(p, "w", encoding="utf-8").write("\n".join(lines))
        print(f"  → {p}")
    print(f"{scn}: 런으로 뻗은 제안 {len(rows)}건")


def apply(scn, rows):
    n = int(scn.replace("ED2SCN", ""))
    jp = {b["id"]: b for b in load_jp_scene("ED2", n)}
    doc = json.load(open(ALIGN_MAP, encoding="utf-8"))
    sec = doc.setdefault(scn, {})
    for j, t, k, _r in rows:
        sec[str(j)] = {"table": t, "entry_id": k, "speaker": jp[j].get("speaker") or ""}
    doc[scn] = {x: sec[x] for x in sorted(sec, key=int)}
    with open(ALIGN_MAP, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"{scn}: {len(rows)}건 반영 · 누계 {len(sec)}건")


if __name__ == "__main__":
    a = sys.argv[1:]
    scenes = [x for x in a if x.startswith("ED2SCN")] or [f"ED2SCN{i}" for i in range(1, 14)]
    for s in scenes:
        rows = propose(s) + (twins(s) if "--twins" in a else [])
        if not rows:
            print(f"{s}: 뻗을 자리 없음 — 앵커가 없다(먼저 `ed2_align_review.py` 로 찍는다)")
            continue
        report(s, rows, verbose="--check" in a)
        if "--apply" in a:
            apply(s, rows)
