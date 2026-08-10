#!/usr/bin/env python3
"""맵 단위 최적 배정 — 정발 페이지 조각 ↔ PS1 블록을 1:1로 전역 배정한다.

**목표를 뒤집었다.** 지금까지는 "미번역 PS1 블록마다 정발 후보 찾기"였는데, 그러면 정발에
없는 블록에도 억지 후보가 붙어 오매칭이 난다(sim 0.55 에도 뜻이 반대인 것이 섞인다).
목표가 "정발 대사를 남김없이 소진"이면 **"안 쓰인 정발 조각마다 대응 블록 찾기"**가 맞다 —
정발 엔트리는 게임에 실제로 존재하는 대사라 대응 블록이 반드시 있고, 후보 풀도 좁다.

**단위는 페이지다**(2026-07-30 실측): 정발 엔트리 2,825 → 페이지 5,435 ≈ PS1 대사 블록
5,224(차이 4%). "정발 1엔트리 = PS1 여러 블록"이 최대 잔여였는데, 페이지로 펼치면 1:1 이
자연스러워지고 결과가 그대로 `chain` 슬라이스가 된다.

**탐욕적 argmax 대신 Hungarian 전역 최적**(`linear_sum_assignment`)을 쓴다. 탐욕은 ①같은
정발 조각을 여러 블록이 가로채고(중복타깃) ②어떤 블록이 다른 블록에게 더 필요한 조각을
빼앗는다. 전역 배정은 둘 다 구조적으로 막는다.

usage:
  assign_pages.py ED1 --validate 크루즈 마을   확정 매핑을 정답으로 홀드아웃 검증
  assign_pages.py ED1                          전 맵 배정 → out/review/assign_*.md|json
"""

import collections
import json
import os
import re
import sys

from align_jp_kr import DOS_KR_DIR, load_jp_scene, norm_body
from align_map import scene_map
from common import OUT_DIR, REVIEW_DIR, ROOT
from scn_maps import block_instances, block_maps, table_instances, table_maps

SIM_MIN = 0.75  # 이 미만은 배정하지 않는다. 라운드를 돌리며 낮춘다(0.75→0.65→…) —
# 매 라운드가 다음 라운드의 앵커를 늘려 인스턴스 학습이 좋아진다(부트스트랩).
SPK_BONUS = 0.06  # 화자 일치 가산 — 화자는 유사도보다 강한 신호다(accept_pair 실측)
OV_PATH = os.path.join(ROOT, "align_overrides.json")  # cwd 무관


def _norm(t):
    """본문 비교용 정규화 — 검증 모드는 원문 그대로, 일반 모드는 이미 norm_body 된 값이 온다."""
    return norm_body(t) if isinstance(t, str) else str(t)


def kr_pages(game):
    """정발 페이지 조각 [{table, eid, page, body, speaker, key}] — 본문 있는 것만."""
    out = []
    d = os.path.join(DOS_KR_DIR, game)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json") or f.startswith(("_", "._")):
            continue
        doc = json.load(open(os.path.join(d, f), encoding="utf-8"))
        cur = None
        for e in doc["entries"]:
            if e["kind"] != "block":
                continue
            if e.get("speaker"):
                cur = e["speaker"]
            t = e["text"].removesuffix("{end}")
            for pi, pg in enumerate(t.split("{p}")):
                body = re.sub(r"\{[^}]*\}|\\x..", " ", pg).strip()
                if len(body) < 2 or not re.search(r"[가-힣]", body):
                    continue
                out.append(
                    {
                        "table": doc["table_id"],
                        "eid": e["entry_id"],
                        "page": pi,
                        "npage": t.count("{p}") + 1,
                        "body": body,
                        "speaker": cur,
                    }
                )
    return out


def used_keys(game):
    """이미 매핑에 쓰인 (table, eid) — 오버라이드 + align 무플래그 쌍."""
    used = set()
    ov = json.load(open(OV_PATH, encoding="utf-8"))
    for scn in range(1, 7):
        for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
            if jid.isdigit() and not v.get("exclude") and "table" in v:
                used.add((v["table"], v["entry_id"]))
        p = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
        if os.path.exists(p):
            for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
                if not pr.get("flags"):
                    used.add((pr["kr"]["table"], pr["kr"]["entry_id"]))
    return used


def used_pages(game):
    """(전부쓰인 엔트리, 쓰인 페이지) — **페이지 단위** 소진 판정.

    ⚠ `used_keys` 는 (table, eid) 단위라 **한 페이지만 쓰여도 엔트리가 통째로 후보에서
    빠진다.** 배정 단위는 페이지인데 소진 판정이 엔트리라 생긴 어긋남이다. 실측(2026-07-31):
    일부만 쓰인 여러 페이지 엔트리 413개가 통째로 빠지면서 **페이지 조각 1,013개(전체
    4,749의 21%)가 후보에서 증발**했다. `T_030#15` 0페이지를 jp496 이 쓰자 1페이지가 사라져
    그 짝인 jp497 이 회수 불가가 된 게 실례다.

    - 오버라이드에 `chain` 이 있고 항목이 `eid#page` 꼴이면 **그 페이지만** 쓰인 것으로 본다.
    - 문장 슬라이스(`eid#page.a-b`)는 페이지를 소진시키지 않는다 — `\x06` 화자 변형처럼
      **여러 블록이 한 페이지를 나눠 갖는 게 정상**이기 때문이다.
    - `chain` 이 없거나 항목에 `#` 가 없으면 엔트리 전체를 쓴 것으로 본다(align 쌍 포함).
    """
    full, pages = set(), set()
    ov = json.load(open(OV_PATH, encoding="utf-8"))
    for scn in range(1, 7):
        for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
            if not jid.isdigit() or v.get("exclude") or "table" not in v:
                continue
            key = (v["table"], v["entry_id"])
            ch = v.get("chain")
            if not ch:
                full.add(key)
                continue
            for it in ch:
                base, _, rest = str(it).partition("#")
                # `2~0` = 변형 슬라이스(리더별 4종 등). 엔트리 번호만 떼어 낸다 —
                # 안 그러면 int() 가 죽는다(jp1200~1203 배정 후 실측 2026-08-03).
                base = base.partition("~")[0]
                if not rest:
                    full.add((v["table"], int(base)))
                elif "." in rest:
                    pass  # 문장 슬라이스 — 페이지를 소진시키지 않는다
                else:
                    pages.add((v["table"], int(base), int(rest)))
        p = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
        if os.path.exists(p):
            for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
                if not pr.get("flags"):
                    full.add((pr["kr"]["table"], pr["kr"]["entry_id"]))
    return full, pages


def jp_open(game):
    """미번역 PS1 블록 [{scn, id, body, speaker, map}] — 오버라이드/align 채택분 제외."""
    ov = json.load(open(OV_PATH, encoding="utf-8"))
    out = []
    for scn in range(1, 7):
        bm = block_maps(game, scn)
        bi = block_instances(game, scn)
        # ⚠ `exclude` 는 **오배정을 물린 것**이지 번역이 아니다. 여기에 섞으면 두 번 손해다 —
        # 커버리지가 부풀고, 그 블록이 후보 풀에 영영 안 올라와 회수 대상에서 빠진다
        # (jp284 `ルディアの城に行ってきましたよ` 가 인게임에서 일본어로 남아 있던 원인, 07-31).
        taken = {
            int(k)
            for k, v in ov.get(f"{game}SCN{scn}", {}).items()
            if k.isdigit() and not (isinstance(v, dict) and v.get("exclude"))
        }
        # 빌드와 같은 판정을 쓴다 — **배정 정본(커밋)이 있으면 그게 입력이고 정렬 파일은
        # 안 읽는다**(`reinsert_kr_pilot.load_translations` 와 같은 규약).
        # ⚠ 정렬 파일은 `work/derived` 라 새 머신엔 없다(LaBSE·torch 가 있어야 만든다).
        #   재삽입기는 진작 정본 우선으로 갔는데 이 함수만 안 따라와서, 정렬 파일이 없는
        #   머신에서는 `status.py` 가 FileNotFoundError 로 죽었다(2026-08-09 홈서버 실측).
        pinned = scene_map(f"{game}SCN{scn}")
        if pinned:
            taken |= set(pinned)
        else:  # 정본이 없는 씬은 정렬 결과로 갈음한다(과도기 경로 — 있을 때만).
            ap = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
            if os.path.exists(ap):
                al = json.load(open(ap, encoding="utf-8"))
                for pr in al["pairs"]:
                    if not pr.get("flags"):
                        taken.add(pr["jp"]["entry_id"])
        for b in load_jp_scene(game, scn):
            if b["id"] in taken or not b["body"].strip():
                continue
            out.append(
                {
                    "scn": scn,
                    "id": b["id"],
                    "body": norm_body(b["body"]) if isinstance(b["body"], str) else b["body"],
                    "speaker": b.get("speaker"),
                    "map": bm.get(b["id"]),
                    "inst": bi.get(b["id"]),
                }
            )
    return out


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    val = sys.argv[sys.argv.index("--validate") + 1] if "--validate" in sys.argv else None

    learned, exempt = table_maps(game)
    pages = kr_pages(game)
    used = used_keys(game)
    blocks = jp_open(game)

    # 맵별 버킷. 검증 모드에서는 이미 쓰인 조각도 후보에 넣고(정답 포함) 해당 맵만 돈다.
    if val:
        pool = [p for p in pages if learned.get(p["table"]) == val or p["table"] in exempt]
        gold = {}
        ov = json.load(open(OV_PATH, encoding="utf-8"))
        for scn in range(1, 7):
            bm = block_maps(game, scn)
            for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
                if (
                    jid.isdigit()
                    and not v.get("exclude")
                    and "table" in v
                    and bm.get(int(jid)) == val
                ):
                    gold[(scn, int(jid))] = (v["table"], v["entry_id"])
            p = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
            for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
                if not pr.get("flags") and bm.get(pr["jp"]["entry_id"]) == val:
                    gold.setdefault(
                        (scn, pr["jp"]["entry_id"]), (pr["kr"]["table"], pr["kr"]["entry_id"])
                    )
        tgt = []
        for scn in range(1, 7):
            bm = block_maps(game, scn)
            bi = block_instances(game, scn)
            for b in load_jp_scene(game, scn):
                if bm.get(b["id"]) == val and (scn, b["id"]) in gold and b["body"].strip():
                    tgt.append(
                        {
                            "scn": scn,
                            "id": b["id"],
                            "body": b["body"],
                            "speaker": b.get("speaker"),
                            "map": val,
                            "inst": bi.get(b["id"]),
                        }
                    )
        buckets = {val: (pool, tgt)}
        print(f"검증 맵 [{val}]: 정발 조각 {len(pool)} × 정답 있는 블록 {len(tgt)}")
    else:
        avail = [p for p in pages if (p["table"], p["eid"]) not in used]
        buckets = {}
        for m in sorted({b["map"] for b in blocks if b["map"]}):
            pool = [p for p in avail if learned.get(p["table"]) == m or p["table"] in exempt]
            tgt = [b for b in blocks if b["map"] == m]
            if pool and tgt:
                buckets[m] = (pool, tgt)
        print(
            f"안 쓰인 정발 조각 {len(avail):,} · 미번역 블록 {len(blocks):,} · 맵 {len(buckets)}개"
        )

    from align_semantic import get_model

    tinst = table_instances(game, min_share=0.50)
    model = get_model()
    spkmap = {}
    sp = os.path.join(OUT_DIR, "align", f"{game}_speakers.json")
    if os.path.exists(sp):
        spkmap = json.load(open(sp, encoding="utf-8")).get("map", {})

    rows, hit, miss, none = [], 0, 0, 0
    for m, (pool, tgt) in buckets.items():
        pe = model.encode([p["body"] for p in pool], normalize_embeddings=True)
        be = model.encode([b["body"] for b in tgt], normalize_embeddings=True)
        sim = be @ pe.T
        for i, b in enumerate(tgt):  # 화자 일치 가산
            ks = spkmap.get(b["speaker"])
            if ks:
                for j, p in enumerate(pool):
                    if p["speaker"] == ks:
                        sim[i][j] += SPK_BONUS

        # 인스턴스 제약: 학습된 테이블이면 그 인스턴스의 블록만 후보로 본다
        def allowed(i, j, pool=pool, tgt=tgt):
            s = tinst.get(pool[j]["table"])
            return (not s) or (tgt[i].get("inst") in s)

        # ── 동일 본문은 한 덩어리로 ──────────────────────────────────────────
        # PS1은 **같은 대사를 여러 블록에 반복**한다(신부의 「お困りの時には…」가 크루즈
        # 마을 4블록, 병사의 「まさかヨルドの港も…」가 랄파 요새 5블록). 정발은 그걸
        # 엔트리 **하나**로 갖는다. 그런데 아래 매칭은 `uj` 로 후보를 **소비**하므로, 대표
        # 하나가 가져가면 나머지 반복은 **강제로 다른 엔트리로 밀린다 = 확정 오답**.
        # 전 씬 실측 53건(깨끗한 정답의 3.6%)이 이 구조적 강제 오답이고, 크루즈 마을은
        # 오답 8건 중 3건이 여기서 나왔다(전부 정답이 `T_022#22` 신부 대사).
        # ⚠ 배정이 끝난 뒤 전파하는 방식은 **안 먹는다** — 반복 블록이 이미 틀리게 배정돼
        #   있어 전파 대상에서 빠진다(2026-07-31 실측 +1히트/+1오답, 사실상 무효).
        #   매칭 자체를 대표 블록만으로 돌리고 끝나서 펼쳐야 한다.
        group = collections.defaultdict(list)
        for i in range(len(tgt)):
            group[_norm(tgt[i]["body"])].append(i)
        reps = {g[0] for g in group.values()}

        # 양방향 최선(서로가 1순위일 때만 확정) — 반복해서 소비하며 제외한다.
        # Hungarian(합계 최대)보다 정밀도가 3%p 높다(2026-07-30 홀드아웃).
        ui, uj = set(), set()
        for _ in range(80):
            cand = []
            for i in sorted(reps):
                if i in ui:
                    continue
                js = [j for j in range(len(pool)) if j not in uj and allowed(i, j)]
                if not js:
                    continue
                j = max(js, key=lambda j: sim[i][j])
                iss = [x for x in sorted(reps) if x not in ui and allowed(x, j)]
                if max(iss, key=lambda x: sim[x][j]) == i and sim[i][j] >= SIM_MIN:
                    cand.append((i, j))
            if not cand:
                break
            for i, j in cand:
                if i in ui or j in uj:
                    continue
                ui.add(i)
                uj.add(j)
                # 대표가 받은 후보를 같은 본문 블록 전부에 물려준다 — 배타성을 깨는 게
                # 아니라 '정발 1엔트리 = PS1 N블록'을 표현하는 것.
                for k in group[_norm(tgt[i]["body"])]:
                    ui.add(k)
                    rows.append((m, tgt[k], pool[j], float(sim[i][j])))
        none += len(tgt) - len(ui)
        if val:
            got = {(b["scn"], b["id"]): (p["table"], p["eid"]) for _m, b, p, _s in rows}
            for k, g in gold.items():
                if k in got:
                    if got[k] == g:
                        hit += 1
                    else:
                        miss += 1

    if val:
        tot = hit + miss + none
        print(
            f"\n정답 {tot}건 대비:  일치 {hit} ({hit / tot * 100:.1f}%) · "
            f"불일치 {miss} · 미배정 {none}"
        )
        # ⚠ 총 정밀도만으로는 **문턱을 못 정한다.** 제안을 그대로 반영할지는 "sim 얼마 위가
        # 믿을 만한가"의 문제이고, 그건 구간별로 갈린다. 총계만 보고 반영하면 저구간의
        # 오배정이 딸려 들어와 **일본어보다 나쁜 결과**(그럴듯한 오역은 QA 를 통과한다)가 된다.
        bands, order = collections.defaultdict(lambda: [0, 0]), (0.90, 0.85, 0.80, 0.75, 0.0)
        for _m, b, p, s in rows:
            g = gold.get((b["scn"], b["id"]))
            if g is None:
                continue
            lo = next(x for x in order if s >= x)
            bands[lo][0 if (p["table"], p["eid"]) == g else 1] += 1
        print(f"\n{'sim':>10} {'맞음':>5} {'틀림':>5} {'정밀도':>8} {'누적':>8}")
        cok = cno = 0
        for lo in order:
            ok, no = bands[lo]
            if ok + no == 0:
                continue
            cok, cno = cok + ok, cno + no
            print(
                f"{f'≥{lo:.2f}' if lo else '<0.75':>10} {ok:5} {no:5} "
                f"{ok / (ok + no) * 100:7.1f}% {cok / (cok + cno) * 100:7.1f}%"
            )
        # 제안을 덤프해 둔다 — `llm_assign.py --score --clean` 으로 오염(풀 밖·과다배정)을
        # 뺀 자로 다시 재려면 필요하다. 위 수치는 오염 포함이라 그대로 비교하면 안 된다.
        os.makedirs(REVIEW_DIR, exist_ok=True)
        dump = {f"{b['scn']}:{b['id']}": f"{p['table']}#{p['eid']}" for _m, b, p, _s in rows}
        vp = os.path.join(REVIEW_DIR, f"assign_labse_{val}.json")
        json.dump(dump, open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"제안 {len(dump)}건 → {vp}")
        return

    os.makedirs(REVIEW_DIR, exist_ok=True)
    prop = collections.defaultdict(dict)
    md = ["# 맵 단위 최적 배정 결과", "", "⚠ 원문·정발 문안 포함 — **커밋 금지**(gitignore).", ""]
    for m in sorted({r[0] for r in rows}):
        sub = [r for r in rows if r[0] == m]
        md += [
            f"## {m} ({len(sub)})",
            "",
            "| sim | 블록 | JP 원문 | 정발 | 정발 대사 |",
            "| ---: | --- | --- | --- | --- |",
        ]
        for _m, b, p, s in sorted(sub, key=lambda r: -r[3]):
            ch = f"{p['eid']}#{p['page']}" if p["npage"] > 1 else str(p["eid"])
            prop[f"{'ED1'}SCN{b['scn']}"][str(b["id"])] = {
                "table": p["table"],
                "entry_id": p["eid"],
                **({"chain": [ch]} if p["npage"] > 1 else {}),
                "note": f"맵 최적 배정 sim={s:.2f} ({m})",
            }
            jt = b["body"].replace("\n", " ")[:52].replace("|", "\\|")
            kt = p["body"][:52].replace("|", "\\|")
            md.append(
                f"| {s:.2f} | jp{b['id']}(S{b['scn']}) | `{jt}` | `{p['table']}#{ch}` | `{kt}` |"
            )
        md.append("")
    open(os.path.join(REVIEW_DIR, f"assign_{game}.md"), "w", encoding="utf-8").write(
        "\n".join(md) + "\n"
    )
    json.dump(
        prop,
        open(os.path.join(REVIEW_DIR, f"assign_{game}.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"배정 {len(rows):,}건 (문턱 미달 미배정 {none:,}) → out/review/assign_{game}.md|json")


if __name__ == "__main__":
    main()
