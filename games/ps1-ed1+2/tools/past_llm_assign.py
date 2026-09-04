#!/usr/bin/env python3
"""인스턴스 단위 배정 페이로드 — 정렬을 유사도가 아니라 '읽고 배정'으로 푼다.

`past_assign_pages.py`는 LaBSE 코사인 + 양방향 최선으로 배정한다. 홀드아웃 실측 정밀도가
81.9~88.2%에서 천장을 치는데, 감사에서 나온 오배정이 **전부 유사도로는 원리적으로 못 잡는
종류**였다 — `jp284` 의미 반대 · `jp554` 화자 반대, 둘 다 맵은 맞았다. 코사인은 "뜻이
반대"를 낮은 점수로 주지 않는다.

그래서 단위를 바꾼다. **맵 인스턴스 하나를 통째로** 넘긴다:

  · 그 인스턴스의 JP 블록 전량 (파일 순서 · 화자 · 메시지ID)
  · 그 맵에 걸린 정발 페이지 조각 전량 (테이블 · 화자 · 페이지 분할)
  · 인스턴스 실제 메시지 수 vs 정발 엔트리 수 (개수 대조)

후보와 타깃을 동시에 보면 이건 이분 매칭이고, `past_assign_pages`의 양방향 최선은 그걸 국소적으로
근사할 뿐이다. 전량을 읽으면 대화 흐름·화자 일관성·의미 반대까지 근거로 쓸 수 있다.
인스턴스는 이미 정발 테이블 1~3개에 대응하므로(≈NPC 단위) 후보 풀도 충분히 좁다.

⚠ **출력은 포인터만**(table · entry_id · 슬라이스). 정발 문안을 되받으면 안 된다 —
`align_overrides.json`은 커밋되므로 문안이 들어가면 저작권 규약 위반이다(루트 CLAUDE.md).
⚠ 페이로드에는 팔콤 일문과 정발 문안이 그대로 들어간다. **`out/review/`(gitignore) 밖으로
   내보내지 말 것.**

usage:
  past_llm_assign.py ED1 --map "크루즈 마을" --holdout   확정 매핑을 정답으로 두고 페이로드 생성
  past_llm_assign.py ED1 --map "크루즈 마을"             미번역 블록 대상 페이로드 생성
  past_llm_assign.py ED1 --score out/review/assign_llm_<맵>.json   제안을 정답과 대조
"""

import collections
import functools
import json
import os
import re
import sys

from align_jp_kr import load_jp_scene, norm_body
from past_assign_pages import kr_pages, used_keys
from common import OUT_DIR, REVIEW_DIR
from scn_maps import block_instances, block_maps, msg_ids, table_maps

SCENES = range(1, 7)


def gold_all(game, slices=False):
    """{맵: {(scn, jp_id): (table, entry_id[, 슬라이스])}} — 확정 매핑(오버라이드 + align).

    오버라이드가 우선이고 align 무플래그 쌍이 뒤를 채운다(`setdefault`). 맵을 못 정한
    블록(`bm.get`이 None)은 버린다 — 맵 제약 자체를 평가할 수 없다.

    `slices=True`면 오버라이드의 `chain`을 키에 포함한다. **과다배정 판정에는 이게 필요하다**
    — 두 블록이 같은 엔트리를 가리켜도 `chain`이 다르면(`11#0.0` vs `11#0.1`) 정발 1엔트리를
    문장 단위로 나눠 가진 정상 케이스다. 채점에는 쓰지 않는다(제안은 엔트리 단위라서).
    """
    out = collections.defaultdict(dict)
    ov = json.load(open("align_overrides.json", encoding="utf-8"))
    for scn in SCENES:
        bm = block_maps(game, scn)
        # ⚠ `exclude` 는 오버라이드를 건너뛰는 게 아니라 **그 블록의 정렬 쌍을 제거**한다
        # (reinsert_kr_pilot 은 `out.pop(jp_id)`). 건너뛰기만 하면 아래 align 루프가 도로
        # 넣어 제외가 무효가 된다 — 2026-07-31에 실제로 그래서 제외한 블록이 계속 잡혔다.
        dropped = {
            int(j)
            for j, v in ov.get(f"{game}SCN{scn}", {}).items()
            if j.isdigit() and v.get("exclude")
        }
        for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
            if jid.isdigit() and not v.get("exclude") and "table" in v:
                m = bm.get(int(jid))
                if m:
                    key = (v["table"], v["entry_id"])
                    if slices and v.get("chain"):
                        key += (tuple(map(str, v["chain"])),)
                    out[m][(scn, int(jid))] = key
        p = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
        if os.path.exists(p):
            for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
                if pr.get("flags") or pr["jp"]["entry_id"] in dropped:
                    continue
                m = bm.get(pr["jp"]["entry_id"])
                if m:
                    out[m].setdefault(
                        (scn, pr["jp"]["entry_id"]), (pr["kr"]["table"], pr["kr"]["entry_id"])
                    )
    return out


def gold(game, mapname):
    """{(scn, jp_id): (table, entry_id)} — 한 맵분."""
    return gold_all(game).get(mapname, {})


def build(game, mapname, holdout):
    """[{instance, blocks[], candidates[], counts}] — 인스턴스별 페이로드."""
    learned, exempt = table_maps(game)
    g = gold(game, mapname) if holdout else {}
    ov = json.load(open("align_overrides.json", encoding="utf-8"))
    used = used_keys(game)

    # 후보 풀: 이 맵으로 학습된 테이블 + 맵무관(상점 등). 검증 모드에서는 정답이 풀에
    # 있어야 하므로 '이미 쓰인 것' 제외를 하지 않는다(past_assign_pages --validate 와 동일).
    pool = [p for p in kr_pages(game) if learned.get(p["table"]) == mapname or p["table"] in exempt]
    if not holdout:
        pool = [p for p in pool if (p["table"], p["eid"]) not in used]

    inst_blocks = collections.defaultdict(list)
    inst_counts = {}
    for scn in SCENES:
        try:
            bi = block_instances(game, scn)
            bm = block_maps(game, scn)
            mids, counts = msg_ids(game, scn)
        except (KeyError, FileNotFoundError):
            continue
        inst_counts.update({k: v for k, v in counts.items() if k.split("#")[0] == mapname})
        taken = {int(k) for k in ov.get(f"{game}SCN{scn}", {}) if k.isdigit()}
        ap = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
        if os.path.exists(ap):
            for pr in json.load(open(ap, encoding="utf-8"))["pairs"]:
                if not pr.get("flags"):
                    taken.add(pr["jp"]["entry_id"])
        for b in load_jp_scene(game, scn):
            if bm.get(b["id"]) != mapname or not b["body"].strip():
                continue
            keep = (scn, b["id"]) in g if holdout else b["id"] not in taken
            if not keep:
                continue
            inst_blocks[bi.get(b["id"]) or f"{mapname}#?"].append(
                {
                    "jp": f"{scn}:{b['id']}",
                    "speaker": b.get("speaker"),
                    "text": b["body"],
                    "msg_ids": mids.get(b["id"], []),
                }
            )

    out = []
    for key in sorted(inst_blocks):
        cands = []
        for p in pool:
            c = {
                "ref": f"{p['table']}#{p['eid']}" + (f".{p['page']}" if p["npage"] > 1 else ""),
                "speaker": p["speaker"],
                "text": p["body"],
            }
            v = variants(game, p["table"], p["eid"], p["page"])
            if v:
                c["speaker_variants"] = v
            cands.append(c)
        out.append(
            {
                "instance": key,
                "engine_msg_count": inst_counts.get(key),
                "blocks": inst_blocks[key],
                "candidates": cands,
            }
        )
    return out, g


@functools.cache
def _npage(game):
    return {(p["table"], p["eid"]): p["npage"] for p in kr_pages(game)}


@functools.cache
def _tmaps(game):
    return table_maps(game)


@functools.cache
def _jptext(game):
    """{(scn, jp_id): 정규화 본문} — 과다배정 판정에 필요(같은 대사의 반복을 걸러낸다)."""
    out = {}
    for scn in SCENES:
        try:
            for b in load_jp_scene(game, scn):
                t = b["body"]
                out[(scn, b["id"])] = norm_body(t) if isinstance(t, str) else str(t)
        except (KeyError, FileNotFoundError):
            continue
    return out


@functools.cache
def _raw(game):
    """{(table, eid): 원문 텍스트} — `kr_pages` 는 `\\x06` 을 지우므로 원문이 따로 필요하다."""
    import glob

    from align_jp_kr import DOS_KR_DIR

    out = {}
    for f in sorted(glob.glob(os.path.join(DOS_KR_DIR, game, "*.json"))):
        if os.path.basename(f).startswith(("_", ".")):
            continue
        doc = json.load(open(f, encoding="utf-8"))
        for e in doc["entries"]:
            if e["kind"] == "block":
                out[(doc["table_id"], e["entry_id"])] = e["text"]
    return out


def variants(game, table, eid, page):
    """[{slice, text}] — 한 페이지 안의 `\\x06` 화자 변형. 없으면 [].

    **정발은 화자 변형 여럿을 한 엔트리에 `\\x06` 으로 이어 담고 PS1 은 각각 별도 블록으로
    쪼갠다**(T_030#20 실측: 변형 5개). `kr_pages` 는 `\\x06` 을 공백으로 지우므로 후보 본문만
    보면 변형이 뭉쳐 보이고 — 유사도든 사람이든 — 대응을 못 찾는다. 전 정발 블록의 7.2%
    (204개, 그중 미사용 131개)가 여기 해당하므로 페이로드에 명시적으로 실어야 한다.

    반환 `slice` 는 그대로 오버라이드 `chain` 에 쓸 수 있는 `eid#page.시작-끝` 이다.
    ⚠ 조각 선두에 `\\x06` 이 남으므로 적용 시 `subs` 로 제거할 것.
    """
    from reinsert_kr_pilot import _sentences

    raw = _raw(game).get((table, eid))
    if not raw:
        return []
    pg = raw.removesuffix("{end}").split("{p}")
    if page >= len(pg) or "\\x06" not in pg[page]:
        return []
    sents = _sentences(pg[page])
    groups, cur = [], []
    for i, t in enumerate(sents):
        if t.startswith("\\x06") and cur:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        body = re.sub(r"\{[^}]*\}|\\x..", " ", "".join(sents[i] for i in g)).strip()
        if len(body) < 2:
            continue
        out.append({"slice": f"{eid}#{page}.{g[0]}-{g[-1]}", "text": body})
    return out if len(out) > 1 else []


def contaminated(game, mapname, g):
    """확정 매핑 중 **정답으로 쓸 수 없는 것** — (풀 밖, 과다배정).

    이걸 빼지 않고 잰 정밀도는 의미가 없다 — 어떤 배정기도 못 맞히거나, 맞혀도 옳지 않다.

    - **풀 밖**: 정답 테이블이 이 맵 후보 풀에 없다(`table_maps`가 다른 맵으로 학습했거나
      아예 미학습). 구조상 도달 불가 — 전 씬 202건.
    - **과다배정**: 한 정발 엔트리에 물린 JP 블록의 **서로 다른 본문 수**가 그 엔트리의
      페이지 수를 넘는다. 초과분 중 최소 하나는 틀렸다 — 전 씬 54건/13엔트리.

    ⚠ **"블록 수 > 페이지 수"로 재면 안 된다**(2026-07-31에 그렇게 재서 147건으로 3배
    부풀었다). PS1은 **같은 대사를 여러 블록에 반복**한다 — `T_022#22`는 JP 4블록이 전부
    같은 문장(신부 대사가 4곳), `C_00B#7`은 2페이지 대화가 3번 반복. 정발 1엔트리가 그
    블록들 전부에 걸리는 게 정상이다. 고유 본문으로 세야 진짜 충돌만 남는다.
    """
    learned, exempt = _tmaps(game)
    pool_t = {t for t, m in learned.items() if m == mapname} | exempt
    npage, jt = _npage(game), _jptext(game)
    sl = gold_all(game).get(mapname) and _gslice(game).get(mapname, {})
    byk = collections.defaultdict(list)
    for j, v in g.items():
        byk[sl.get(j, v) if sl else v].append(j)
    over = {k for k, js in byk.items() if len({jt.get(j, "") for j in js}) > npage.get(k[:2], 1)}
    outside = {k for k, v in g.items() if v[0] not in pool_t}
    dup = {k for k, v in g.items() if (sl.get(k, v) if sl else v) in over}
    return outside, dup


@functools.cache
def _gslice(game):
    """{맵: {(scn, jp_id): 슬라이스까지 포함한 키}} — 과다배정 판정 전용."""
    return gold_all(game, slices=True)


def scan(game):
    """전 맵 오염 집계 + 풀 밖을 유발한 테이블 진단.

    풀 밖은 두 원인이 섞여 있어 따로 봐야 한다:
      · **앵커가 틀림** — 그 블록이 실제로 다른 맵 소속인데 잘못 물린 것
      · **학습 실패** — 진짜 양다리 테이블(상점 등)인데 `table_maps`가 면제로 못 뺀 것
    아래 분포(최빈 점유율/2위 점유율)를 `_PURITY_MIN=0.7`·`_EXEMPT_SHARE=0.3`과 대조하면
    갈린다. 학습 실패면 앵커를 고칠 게 아니라 문턱을 고쳐야 한다.
    """
    ga = gold_all(game)
    learned, exempt = _tmaps(game)
    rows, detail = [], {}
    tally = collections.defaultdict(collections.Counter)
    for m, g in ga.items():
        for tbl, _e in g.values():
            tally[tbl][m] += 1
    tot_g = tot_o = tot_d = 0
    for m in sorted(ga, key=lambda x: -len(ga[x])):
        g = ga[m]
        outside, dup = contaminated(game, m, g)
        rows.append((m, len(g), len(outside), len(dup)))
        tot_g += len(g)
        tot_o += len(outside)
        tot_d += len(dup)
        detail[m] = {
            "outside": [f"{s}:{j}" for s, j in sorted(outside)],
            "over": [f"{s}:{j}" for s, j in sorted(dup)],
        }

    print(f"{'맵':<16}{'gold':>7}{'풀밖':>7}{'과다':>7}{'깨끗':>9}")
    for m, n, o, d in rows:
        c = n - o - d
        print(f"{m:<16}{n:>7}{o:>7}{d:>7}{c:>7} ({c / n * 100:.0f}%)")
    clean_n = tot_g - tot_o - tot_d
    print(f"{'계':<16}{tot_g:>7}{tot_o:>7}{tot_d:>7}{clean_n:>7} ({clean_n / tot_g * 100:.0f}%)")

    # 풀 밖을 유발한 테이블 진단
    culprits = collections.Counter()
    for m, g in ga.items():
        pool_t = {t for t, mm in learned.items() if mm == m} | exempt
        for tbl, _e in g.values():
            if tbl not in pool_t:
                culprits[tbl] += 1
    print(f"\n풀 밖을 유발한 테이블 {len(culprits)}개 (상위 12):")
    for tbl, n in culprits.most_common(12):
        c = tally[tbl]
        s = sum(c.values())
        top, ntop = c.most_common(1)[0]
        second = c.most_common(2)[1][1] / s if len(c) > 1 else 0.0
        why = (
            "학습됨→다른맵"
            if tbl in learned
            else ("면제" if tbl in exempt else f"미학습(최빈{ntop / s:.0%}·2위{second:.0%})")
        )
        dist = " ".join(f"{k}{v}" for k, v in c.most_common(4))
        print(f"  {tbl:14} 참조{n:>4}  {why:22} [{dist}]")

    p = os.path.join(REVIEW_DIR, f"contamination_{game}.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(detail, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n상세 → {p}")


def score(game, mapname, path, clean=False):
    """제안 {jp: ref} 를 확정 매핑과 대조한다. past_assign_pages --validate 와 같은 자."""
    g = gold(game, mapname)
    if clean:
        outside, dup = contaminated(game, mapname, g)
        print(f"오염 제외: 풀 밖 {len(outside)} · 과다배정 {len(dup)} → 정답 {len(g)}→", end="")
        g = {k: v for k, v in g.items() if k not in outside and k not in dup}
        print(f"{len(g)}")
    prop = json.load(open(path, encoding="utf-8"))
    hit = miss = 0
    wrong = []
    for (scn, jid), (tbl, eid) in g.items():
        r = prop.get(f"{scn}:{jid}")
        if not r or r == "NEW":
            continue
        got = (r.split("#")[0], int(r.split("#")[1].split(".")[0]))
        if got == (tbl, eid):
            hit += 1
        else:
            miss += 1
            wrong.append((f"{scn}:{jid}", r, f"{tbl}#{eid}"))
    none = len(g) - hit - miss
    tot = len(g)
    print(
        f"정답 {tot}건 대비:  일치 {hit} ({hit / tot * 100:.1f}%) · 불일치 {miss} · 미배정 {none}"
    )
    if hit + miss:
        print(f"배정한 것 중 정밀도: {hit / (hit + miss) * 100:.1f}%")
    for w in wrong[:15]:
        print(f"  ✗ {w[0]}  제안 {w[1]}  정답 {w[2]}")


def split(game, scn):
    """씬 하나를 인스턴스별 파일로 떨군다 — 서브에이전트가 파일로 읽게 하려는 것.

    프롬프트에 페이로드를 인라인하면 팔콤 일문·정발 문안이 대화에 떠다닌다. 파일 경로만
    넘기고 읽게 하면 `out/review/`(gitignore) 밖으로 안 나간다.
    """
    from past_assign_pages import jp_open

    maps = sorted({b["map"] for b in jp_open(game) if b["scn"] == scn and b["map"]})
    d = os.path.join(REVIEW_DIR, "inst")
    os.makedirs(d, exist_ok=True)
    made = []
    for m in maps:
        payloads, _ = build(game, m, holdout=False)
        for x in payloads:
            blocks = [b for b in x["blocks"] if b["jp"].startswith(f"{scn}:")]
            if not blocks:
                continue
            # ⚠ 파일명에 **맵을 넣어야 한다**. 인스턴스 키는 씬 단위 지명 카운터라
            # `block_maps` 가 준 맵과 어긋날 수 있고(같은 `베르가 광산#1` 이 두 맵에서
            # 나온다), 맵을 빼면 뒤 파일이 앞 파일을 덮어쓴다.
            safe = f"{m}_{x['instance']}".replace("/", "_").replace(" ", "_")
            p = os.path.join(d, f"{game}SCN{scn}_{safe}.json")
            json.dump(
                {**x, "map": m, "scene": scn, "blocks": blocks},
                open(p, "w", encoding="utf-8"),
                ensure_ascii=False,
                indent=1,
            )
            made.append((p, x["instance"], len(blocks), len(x["candidates"])))
    for p, inst, nb, nc in made:
        print(f"  {inst:24} 블록 {nb:3} · 후보 {nc:4}  → {os.path.basename(p)}")
    print(f"인스턴스 파일 {len(made)}개 → {d}")


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    mapname = sys.argv[sys.argv.index("--map") + 1] if "--map" in sys.argv else None
    if "--scan" in sys.argv:
        return scan(game)
    if "--split" in sys.argv:
        return split(game, int(sys.argv[sys.argv.index("--split") + 1]))
    if "--score" in sys.argv:
        p = sys.argv[sys.argv.index("--score") + 1]
        return score(game, mapname, p, clean="--clean" in sys.argv)

    payloads, g = build(game, mapname, "--holdout" in sys.argv)
    d = REVIEW_DIR
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"payload_{mapname}.json")
    json.dump(payloads, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nb = sum(len(x["blocks"]) for x in payloads)
    nc = payloads[0]["candidates"] if payloads else []
    print(
        f"인스턴스 {len(payloads)}개 · 블록 {nb} · 후보 {len(nc)}"
        + (f" · 정답 {len(g)}" if g else "")
    )
    for x in payloads:
        print(
            f"  {x['instance']:20} 블록 {len(x['blocks']):3}  엔진 메시지 {x['engine_msg_count']}"
        )
    print(f"→ {p}  (⚠ 원문·정발 문안 포함 — 커밋 금지)")


if __name__ == "__main__":
    main()
