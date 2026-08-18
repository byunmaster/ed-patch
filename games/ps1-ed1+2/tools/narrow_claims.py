#!/usr/bin/env python3
"""통째 점유 배정을 **페이지 단위로 축소** — 가려진 정발 페이지를 후보 풀에 돌려준다.

회수를 가장 크게 막는 건 정밀도가 아니라 **축소(narrowing)** 다. 정발 1엔트리가 P페이지인데
PS1 이 그걸 여러 블록으로 쪼갠 경우, 앞 블록의 배정이 `chain` 없이 엔트리를 **통째로** 물면
나머지 P-1 장이 어느 후보 풀에도 안 나온다(`assign_pages.used_pages` 주석 참조). 실측
2026-07-31: SCN1 만 97건이 통째 점유 + 다중페이지고 그 뒤에 107장이 가려져 있었다.

**축소는 공짜가 아니다.** 페이지 수가 창 수와 다르면 재삽입기는 전 페이지를 창에 욱여넣는다
(`build_from_template` 의 `joined = "\\n".join(...)` 폴백). 그러니 페이지를 떼면 그 블록이
실제로 보여주던 글자가 빠진다. 근거 없이 좁히면 안 된다.

근거는 **창 수(W) = PS1 이 강제하는 구조 계약** 이다. 재삽입기가 `target` 으로 쓰는 바로 그
값을 여기서도 같은 식으로 계산한다(`mc - 2*헤더 - 2*인라인%s`). W < P 면 그 블록이 감당하는
건 W장이고, 남은 P-W 장은 **뒤따르는 PS1 블록의 몫**이라고 본다 — 정발이 한 엔트리로 둔 걸
PS1 이 쪼갠 그 지점이다.

안전장치(전부 통과해야 후보로 낸다):
  1. W < P — 창보다 페이지가 많아야 축소할 게 있다
  2. 인접(±ADJ) 에 **미번역 블록**이 있다 — 쪼개짐이 실재한다는 증거. 없으면 정발 여러 페이지가
     정말 이 블록 하나에 들어가는 경우일 수 있어 손대지 않는다
  3. 그 인접 블록이 이름·지명 플레이트가 아니다 — 거긴 `patch_sys_ui` 관할이다
  4. 이미 페이지 단위(`eid#page`)로 물고 있으면 건드리지 않는다

축소만으로는 회수가 늘지 않는다. **푸는 것까지가 절반**이고, 풀린 페이지는 기존 배정
파이프라인(`llm_assign` → 서브에이전트 → `merge_assign`)이 가져간다. 그래서 `merge_assign`
이 "기존 통째점유와 충돌 — 축소 먼저"로 막아둔 제안들이 이 뒤에 통과하게 된다.

⚠ 검증은 반드시 빌드 A/B 로 한다 — 좁힌 블록이 창을 못 채우면 `창 분배 실패`로 **탈락**한다.
총 재삽입 수가 줄거나 제외 사유가 늘면 되돌린다.

usage:
  narrow_claims.py ED1 1          검토(dry-run) — 무엇이 좁혀지고 몇 장이 풀리는지
  narrow_claims.py ED1 1 --apply  align_overrides.json 에 chain 을 써넣는다
  narrow_claims.py ED1 all        전 씬 검토
"""

import collections
import json
import os
import sys

from align_jp_kr import load_jp_scene
from common import OUT_DIR, ROOT
from patch_sys_ui import is_name_plate

OV = os.path.join(ROOT, "align_overrides.json")
ADJ = 3  # 인접 판정 반경(블록 id 기준) — 쪼개진 조각은 대개 바로 뒤에 붙는다


def _pages(text):
    """정발 엔트리의 실질 페이지 수(내용 있는 `{p}` 조각)."""
    return [p for p in text.removesuffix("{end}").split("{p}") if p.strip()]


def _win_count(game, scn):
    """{entry_id: 창 수} — 재삽입기가 `target` 으로 쓰는 값과 **같은 식**으로 계산한다.

    (reinsert_kr_pilot.load_translations 참조: W = %c수 - 2*블록헤더 - 2*인라인 %s 헤더)
    어긋나면 좁힌 뒤 `창 분배 실패`가 나므로 여기서 정본을 따라야 한다.
    """
    from reinsert_kr_pilot import MC, jp_has_header, jp_inline_fmt_windows

    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    out = {}
    for e in doc["entries"]:
        if not e.get("raw_hex"):
            continue
        raw = bytes.fromhex(e["raw_hex"])
        _, inline = jp_inline_fmt_windows(raw)
        out[e["entry_id"]] = max(
            1, raw.count(MC) - (2 if jp_has_header(raw) else 0) - 2 * len(inline)
        )
    return out


def claims(game, scn, ov):
    """[(jp_id, table, eid, 출처)] — 이 씬에서 엔트리를 **통째로** 물고 있는 배정."""
    out, seen = [], set()
    for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
        if not jid.isdigit() or v.get("exclude") or "table" not in v:
            continue
        # ⚠ seen 등록이 먼저다 — 오버라이드가 align 쌍보다 우선하므로, 손대지 않는 경우에도
        # 그 블록을 아래 align 루프에서 **다시 후보로 잡으면 안 된다**(이미 좁힌 걸 또 좁힘).
        seen.add(int(jid))
        ch = v.get("chain")
        if ch and all("#" in str(c) for c in ch):
            continue  # 이미 페이지 단위 — 손대지 않는다
        out.append((int(jid), v["table"], v["entry_id"], "override"))
    ap = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
    if os.path.exists(ap):
        for p in json.load(open(ap, encoding="utf-8"))["pairs"]:
            if p["jp"] and not p.get("flags") and p["jp"]["entry_id"] not in seen:
                out.append((p["jp"]["entry_id"], p["kr"]["table"], p["kr"]["entry_id"], "align"))
    return sorted(out)


def plan(game, scn):
    """축소 후보 목록 + 통계."""
    from llm_assign import _raw

    raw = _raw(game)
    ov = json.load(open(OV, encoding="utf-8"))
    wins = _win_count(game, scn)
    blocks = {b["id"]: b for b in load_jp_scene(game, scn)}

    # 미번역(열린) 블록 — 축소가 실재한다는 증거이자 풀린 페이지의 수요처
    from assign_pages import jp_open

    opens = {b["id"] for b in jp_open(game) if b["scn"] == scn}

    rows, skip = [], collections.Counter()
    for jid, tbl, eid, src in claims(game, scn, ov):
        t = raw.get((tbl, eid))
        if not t:
            skip["엔트리 없음"] += 1
            continue
        p = len(_pages(t))
        w = wins.get(jid)
        if w is None:
            skip["창 수 미상"] += 1
            continue
        if p <= w:
            skip["창≥페이지(축소 불가)"] += 1
            continue
        adj = [
            i
            for d in range(1, ADJ + 1)
            for i in (jid + d, jid - d)
            if i in opens and not is_name_plate(blocks.get(i, {}).get("body", ""))
        ]
        if not adj:
            skip["인접 미번역 없음"] += 1
            continue
        rows.append((jid, tbl, eid, p, w, sorted(set(adj)), src))
    return rows, skip


def pair(game, scn, sim_min):
    """해방된 페이지를 뒤따르는 PS1 블록에 짝지어 준다 — 축소의 나머지 절반.

    축소만 하면 **보이는 한국어가 줄어든다**(앞 블록이 욱여넣어 보여주던 뒷장이 사라진다).
    그래서 축소와 배정은 한 거래로 묶어야 한다.

    대응 규칙은 자료가 알려준다 — 실측 표본에서 예외 없이 **해방 페이지 i → 블록 jid+i** 였다
    (jp91/T_011#14 p1 ↔ jp92, jp98 p1 ↔ jp99 …). 정발이 한 엔트리에 이어 쓴 대화를 PS1 이
    순서대로 쪼갠 것이니 당연한 결과다. 다만 규칙만 믿지 않고 **LaBSE 로 JP 본문 ↔ 정발 페이지
    유사도를 재서** 문턱을 넘는 짝만 채택한다(오프바이원·중간에 낀 블록 방어).
    """
    from align_semantic import get_model
    from llm_assign import _raw
    from reinsert_kr_pilot import parse_kr

    raw = _raw(game)
    ov = json.load(open(OV, encoding="utf-8"))
    blocks = {b["id"]: b for b in load_jp_scene(game, scn)}
    from assign_pages import jp_open

    opens = {b["id"] for b in jp_open(game) if b["scn"] == scn}

    # ⚠ 축소가 **이미 반영된 뒤에도** 돌아야 한다(멱등). `plan()` 은 축소할 게 남았는지를 보는
    # 함수라 축소 후엔 빈 목록이다 — 여기서는 현재 점유 상태에서 **비어 있는 페이지**를 직접 센다.
    held = collections.defaultdict(dict)  # (tbl,eid) → {page: 그 페이지를 물고 있는 jid}
    for jid, v in ov.get(f"{game}SCN{scn}", {}).items():
        if not jid.isdigit() or v.get("exclude") or "table" not in v:
            continue
        for c in v.get("chain") or []:
            base, _, rest = str(c).partition("#")
            if rest and "." not in rest:
                held[(v["table"], int(base))][int(rest)] = int(jid)

    cand = []  # (target_jid, tbl, eid, page_idx, jp본문, kr본문)
    for (tbl, eid), used in held.items():
        t = raw.get((tbl, eid))
        if not t:
            continue
        pgs = _pages(t)
        for pi in range(len(pgs)):
            if pi in used:
                continue
            # 정발이 이어 쓴 걸 PS1 이 순서대로 쪼갠다 — 가장 가까운 기준점에서 오프셋을 뜬다.
            # 앞뒤 어느 쪽이든 기준이 된다(앞 페이지가 비면 **앞 블록**이 임자다 — jp1128 실측).
            prev = [q for q in used if q < pi]
            nxt = [q for q in used if q > pi]
            if prev:
                pj = max(prev)
            elif nxt:
                pj = min(nxt)
            else:
                continue  # 기준점이 없다
            tj = used[pj] + (pi - pj)
            if tj not in opens or tj not in blocks:
                continue
            jb = blocks[tj]["body"].strip()
            if not jb or is_name_plate(jb):
                continue
            try:
                kb = " ".join(t for _c, t in parse_kr({"text": pgs[pi], "speaker": None})[1])
            except Exception:
                continue
            if len(kb.strip()) < 2:
                continue
            cand.append((tj, tbl, eid, pi, jb, kb))
    if not cand:
        return []
    m = get_model()
    je = m.encode([c[4] for c in cand], normalize_embeddings=True)
    ke = m.encode([c[5] for c in cand], normalize_embeddings=True)
    out = []
    for c, s in zip(cand, (je * ke).sum(1), strict=True):
        out.append((*c, float(s)))
    # 한 블록에 후보가 둘 이상이면 최고점만 — 오프바이원이 겹칠 수 있다
    best = {}
    for r in out:
        if r[0] not in best or r[-1] > best[r[0]][-1]:
            best[r[0]] = r
    return [r for r in best.values() if r[-1] >= sim_min]


def fix_offsets(game, scns, margin=0.08):
    """축소된 배정의 **시작 페이지**를 LaBSE 로 재확정 — 축소 규칙의 맹점 교정.

    축소는 "창이 W개면 앞 W장을 쓴다"고 봤는데, **앞 블록이 미배정이면 그만큼 밀린다.**
    실측(2026-07-31): 369건 중 75건(20%)이 p0 이 아닌 페이지가 임자였다. 예를 들어
    `jp1129`(`あれはのうアクダムさまの船じゃ…`)는 `C_001#35` p1 이 맞는데 p0(`아니 저 배는.`)을
    물어, 앞 블록 `jp1128` 몫을 가로채고 자기 대사는 잃었다.

    그래서 시작 페이지를 가정하지 않는다 — JP 본문과 각 페이지의 유사도를 재서 argmax 를
    시작점으로 잡고, 거기서 W장을 연속으로 문다. 여유(margin) 미만이면 손대지 않는다.
    """
    from align_semantic import get_model
    from llm_assign import _raw
    from reinsert_kr_pilot import parse_kr

    raw = _raw(game)
    ov = json.load(open(OV, encoding="utf-8"))
    rows = []
    for scn in scns:
        blocks = {b["id"]: b["body"] for b in load_jp_scene(game, scn)}
        for j, v in ov.get(f"{game}SCN{scn}", {}).items():
            ch = v.get("chain") if isinstance(v, dict) else None
            if not ch or not all("#" in str(c) and "." not in str(c) for c in ch):
                continue
            t = raw.get((v["table"], v["entry_id"]))
            if not t:
                continue
            pgs = _pages(t)
            w = len(ch)
            if len(pgs) <= w:
                continue  # 고를 여지가 없다
            jb = (blocks.get(int(j)) or "").strip()
            if not jb:
                continue
            texts = []
            for pg in pgs:
                try:
                    texts.append(
                        " ".join(x for _c, x in parse_kr({"text": pg, "speaker": None})[1])
                    )
                except Exception:
                    texts.append("")
            cur = int(str(ch[0]).partition("#")[2])
            rows.append((scn, int(j), v, pgs, texts, w, cur, jb))
    if not rows:
        return []
    m = get_model()
    je = m.encode([r[7] for r in rows], normalize_embeddings=True)
    out = []
    for r, e in zip(rows, je, strict=True):
        scn, j, v, pgs, texts, w, cur, _jb = r
        s = m.encode(texts, normalize_embeddings=True) @ e
        best = max(range(len(pgs) - w + 1), key=lambda k: float(s[k]))
        if best != cur and float(s[best]) - float(s[cur]) > margin:
            out.append((scn, j, v, cur, best, w, float(s[cur]), float(s[best])))
    return out


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    arg = sys.argv[2] if len(sys.argv) > 2 else "1"
    apply_ = "--apply" in sys.argv
    scns = range(1, 7) if arg == "all" else [int(arg)]

    ov = json.load(open(OV, encoding="utf-8"))
    total_rows, freed = 0, 0
    for scn in scns:
        rows, skip = plan(game, scn)
        free = sum(p - w for _j, _t, _e, p, w, _a, _s in rows)
        total_rows += len(rows)
        freed += free
        print(f"{game}SCN{scn}: 축소 후보 **{len(rows)}건** → 페이지 {free}장 해방")
        for r, n in skip.most_common():
            print(f"    보류 {n:4}  {r}")
        for jid, tbl, eid, p, w, adj, src in rows[:8]:
            print(f"    jp{jid:<5} {tbl}#{eid} {p}p→{w}p [{src}]  인접미번역 {adj[:4]}")
        if len(rows) > 8:
            print(f"    … 외 {len(rows) - 8}건")

        if apply_:
            tgt = ov.setdefault(f"{game}SCN{scn}", {})
            for jid, tbl, eid, p, w, _adj, _src in rows:
                e = tgt.setdefault(str(jid), {})
                e.setdefault("table", tbl)
                e.setdefault("entry_id", eid)
                e["chain"] = [f"{eid}#{i}" for i in range(w)]
                note = e.get("note", "")
                add = f"창 수 계약으로 축소({p}p→{w}p) — 남은 페이지 해방 2026-07-31"
                e["note"] = f"{note} · {add}" if note else add

    print(f"\n합계: 축소 {total_rows}건 · 페이지 {freed}장 해방")

    # ⚠ 축소를 **먼저 디스크에 쓴다** — `pair()` 는 현재 점유 상태를 파일에서 다시 읽어
    # 빈 페이지를 찾으므로, 메모리에만 있으면 방금 해방한 페이지를 못 본다.
    if apply_ and total_rows:
        json.dump(ov, open(OV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(OV, "a", encoding="utf-8").write("\n")

    if "--fix-offset" in sys.argv:
        fx = fix_offsets(game, scns)
        print(f"\n시작 페이지 재확정 **{len(fx)}건** (JP 본문↔페이지 유사도로 판정)")
        for scn, j, v, cur, best, _w, s0, sb in sorted(fx, key=lambda r: -(r[7] - r[6]))[:10]:
            print(
                f"    SCN{scn} jp{j:<5} {v['table']}#{v['entry_id']}  p{cur}({s0:.2f}) → p{best}({sb:.2f})"
            )
        if len(fx) > 10:
            print(f"    … 외 {len(fx) - 10}건")
        if apply_:
            ov = json.load(open(OV, encoding="utf-8"))
            for scn, j, _v, cur, best, w, _s0, _sb in fx:
                e = ov[f"{game}SCN{scn}"][str(j)]
                e["chain"] = [f"{e['entry_id']}#{i}" for i in range(best, best + w)]
                e["note"] = (
                    e.get("note", "") + f" · 시작 페이지 재확정 p{cur}→p{best}(2026-07-31)"
                ).strip(" ·")
            json.dump(ov, open(OV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            open(OV, "a", encoding="utf-8").write("\n")
            print(f"→ {len(fx)}건 반영")

    if "--pair" in sys.argv:
        ov = json.load(open(OV, encoding="utf-8"))  # 축소 반영본 재적재
        sim_min = float(os.environ.get("PAIR_SIM", "0.55"))
        for scn in scns:
            ps = pair(game, scn, sim_min)
            print(
                f"\n{game}SCN{scn}: 해방 페이지 → 후속 블록 짝짓기 **{len(ps)}건** (유사도 ≥{sim_min})"
            )
            for tj, tbl, eid, pi, jb, kb, s in sorted(ps, key=lambda r: -r[-1])[:8]:
                print(f"    jp{tj:<5} ({s:.2f}) ← {tbl}#{eid} p{pi}")
                print(f"        JP {jb[:52]!r}")
                print(f"        KR {kb[:52]!r}")
            if len(ps) > 8:
                print(f"    … 외 {len(ps) - 8}건")
            if apply_:
                tgt = ov.setdefault(f"{game}SCN{scn}", {})
                for tj, tbl, eid, pi, _jb, _kb, s in ps:
                    tgt[str(tj)] = {
                        "table": tbl,
                        "entry_id": eid,
                        "chain": [f"{eid}#{pi}"],
                        "note": f"축소로 해방된 페이지 회수 — 후속 블록 대응(유사도 {s:.2f}) 2026-07-31",
                    }

    if not apply_:
        print("(dry-run — 쓰려면 --apply)")
        return
    json.dump(ov, open(OV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OV, "a", encoding="utf-8").write("\n")
    print(f"→ {OV} 반영. ⚠ 빌드 A/B 로 **총 재삽입 수·제외 사유**를 반드시 확인할 것.")


if __name__ == "__main__":
    main()
