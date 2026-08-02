#!/usr/bin/env python3
"""서브에이전트 배정 결과 → `align_overrides.json` 병합 (검증 먼저, 기본 dry-run).

`llm_assign.py --split` 이 떨군 인스턴스 파일을 에이전트가 처리해 `OUT_*.json` 으로 돌려준다.
그걸 그대로 믿고 병합하면 안 된다 — **빌드는 `%c`/`%s` 수만 보므로 제어바이트가 남거나 엉뚱한
엔트리를 가리켜도 통과한다**(HANDOFF `jp495` 사례). 여기서 미리 걸러낸다.

검사 항목
  1. **엔트리 실재** — table/entry_id 가 정발에 있는가
  2. **체인 해석** — 슬라이스가 실제로 문자열을 내는가(빈 조각 = 잘못된 인덱스)
  3. **제어바이트 잔존** — 최종 문자열에 `\\xNN` 이 남았는가 ⇐ **가장 중요**
  4. **대상 유효** — 그 JP 블록이 정말 미번역 상태인가(이미 배정된 걸 덮어쓰지 않는다)
  5. **슬라이스 충돌** — 서로 다른 JP 본문이 같은 조각을 물었는가
  6. **신뢰도** — `low` 는 기본 제외(`--low` 로 포함)

usage:
  merge_assign.py ED1 1              검증만(dry-run) — 무엇이 병합될지 표로 보여준다
  merge_assign.py ED1 1 --apply      align_overrides.json 에 실제로 쓴다
  merge_assign.py ED1 1 --low        low 신뢰도도 포함
"""

import collections
import glob
import json
import os
import sys

from align_jp_kr import load_jp_scene
from common import OUT_DIR, REVIEW_DIR, ROOT
from patch_sys_ui import is_name_plate


# ⚠ repr 문자열에서 `\\xNN` 을 찾으면 안 된다 — `NAME_SENT`(\x1a, `%s` 자리)·`NUM_SENT`
# (\x1b, `%d` 자리)가 **정상 출력물**인데 repr 에서는 똑같이 `\\x1a` 로 보여 오탐이 난다.
# 실제 제어문자만, 센티널과 개행을 빼고 본다.
def _stray(parts):
    from reinsert_kr_pilot import NAME_SENT, NUM_SENT

    keep = {NAME_SENT, NUM_SENT, "\n"}
    return sorted({hex(ord(c)) for t in parts for c in t if ord(c) < 0x20 and c not in keep})


# reinsert_kr_pilot 과 같은 방식으로 절대 경로를 만든다 — 어느 cwd 에서 돌려도 맞게.
OV = os.path.join(ROOT, "align_overrides.json")


def _pipeline_text(table, eid, chain, subs):
    """reinsert_kr_pilot 과 같은 경로로 최종 문자열을 만든다 — 감사는 반드시 실제 경로로."""
    from llm_assign import _raw
    from reinsert_kr_pilot import _sentences, parse_kr

    raw = _raw("ED1").get((table, eid))
    if raw is None:
        return None, "엔트리 없음"
    parts = []
    for item in chain or [str(eid)]:
        base, _, rest = str(item).partition("#")
        pi, _, si = rest.partition(".")
        t = _raw("ED1").get((table, int(base)))
        if t is None:
            return None, f"체인 대상 {base} 없음"
        t = t.removesuffix("{end}")
        if pi:
            pg = t.split("{p}")
            if int(pi) >= len(pg):
                return None, f"페이지 {pi} 범위 밖"
            t = pg[int(pi)]
        if si:
            sents = _sentences(t)
            lo, dash, hi = si.partition("-")
            a = int(lo)
            b = (int(hi) + 1 if hi else len(sents)) if dash else a + 1
            if a >= len(sents):
                return None, f"문장 {si} 범위 밖(총 {len(sents)})"
            t = "".join(sents[a:b]).lstrip()
            t = t.removeprefix("{n}").lstrip() if t.startswith("{n}") else t
        parts.append(t if t.endswith("{p}") else t + "{p}")
    txt = "".join(parts)
    for a, b in subs or []:
        txt = txt.replace(a, b)
    from reinsert_kr_pilot import SkipBlock

    try:
        out = parse_kr({"text": txt, "speaker": None})
    except SkipBlock as e:
        # 본문 없는 엔트리(= 화자명 플레이트). 재삽입기에 "침묵 블록(이름만 번역)" 경로가
        # 있으니 틀린 배정은 아니지만, 자동 병합 대상은 아니다 — 사람이 보고 넣는다.
        return None, f"본문 없음({e})"
    parts = [t for _c, t in out[1]]
    return parts, None


def load(game, scn):
    """[(jp_key, 제안, 인스턴스)] — OUT_*.json 전부."""
    d = os.path.join(REVIEW_DIR, "inst")
    out = []
    for f in sorted(glob.glob(os.path.join(d, f"OUT_{game}SCN{scn}_*.json"))):
        inst = os.path.basename(f).removeprefix(f"OUT_{game}SCN{scn}_").removesuffix(".json")
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ⚠ {os.path.basename(f)}: JSON 파손 — {e}")
            continue
        for k, v in doc.items():
            out.append((k, v, inst))
    return out


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    scn = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    apply_ = "--apply" in sys.argv
    allow_low = "--low" in sys.argv

    props = load(game, scn)
    open_ids = {b["id"] for b in load_jp_scene(game, scn)}
    ov = json.load(open(OV, encoding="utf-8"))
    taken = {int(k) for k in ov.get(f"{game}SCN{scn}", {}) if k.isdigit()}
    ap = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
    aligned = set()
    if os.path.exists(ap):
        for pr in json.load(open(ap, encoding="utf-8"))["pairs"]:
            if not pr.get("flags"):
                aligned.add(pr["jp"]["entry_id"])

    # 기존 배정이 **통째로** 물고 있는 엔트리 — 여기에 페이지 슬라이스를 새로 물리면
    # 그 문장이 게임에 두 번 나온다(앞 블록을 같이 축소해야 안전하다). 근거가 맞아도
    # 자동 병합 대상이 아니다 — 축소와 짝지어 사람이 처리한다.
    from assign_pages import used_pages

    held_full, _held_pg = used_pages(game)

    jptext = {b["id"]: b["body"] for b in load_jp_scene(game, scn)}
    ok, rej = [], collections.Counter()
    claims = collections.defaultdict(list)
    detail = []

    for key, v, inst in props:
        s, _, j = key.partition(":")
        if not j.isdigit() or int(s) != scn:
            rej["키 형식"] += 1
            continue
        jid = int(j)
        if v.get("new"):
            rej["신규번역(new)"] += 1
            continue
        if jid not in open_ids:
            rej["블록 없음"] += 1
            continue
        if jid in taken or jid in aligned:
            rej["이미 배정됨"] += 1
            continue
        # 이름·지명 단독 블록은 patch_sys_ui 관할(patch_sys_ui.is_name_plate 주석 참조)
        if is_name_plate(jptext.get(jid, "")):
            rej["이름·지명 플레이트"] += 1
            continue
        conf = (v.get("confidence") or "").lower()
        if conf == "low" and not allow_low:
            rej["low 신뢰도"] += 1
            continue
        tbl, eid = v.get("table"), v.get("entry_id")
        if not tbl or eid is None:
            rej["table/entry_id 누락"] += 1
            continue
        parts, err = _pipeline_text(tbl, eid, v.get("chain"), v.get("subs"))
        if err:
            rej[f"체인 오류({err[:14]})"] += 1
            detail.append(("✗", key, f"{tbl}#{eid}", err))
            continue
        body = " ".join(parts)
        if len(body.strip()) < 2:
            rej["빈 결과"] += 1
            detail.append(("✗", key, f"{tbl}#{eid}", "빈 조각"))
            continue
        if (tbl, eid) in held_full:
            rej["기존 통째점유와 충돌"] += 1
            detail.append(("!", key, f"{tbl}#{eid}", "이미 통째 점유 — 축소 먼저"))
            continue
        stray = _stray(parts)
        if stray:
            rej["제어문자 잔존"] += 1
            detail.append(("✗", key, f"{tbl}#{eid}", f"제어문자 {stray}"))
            continue
        claims[(tbl, eid, tuple(map(str, v.get("chain") or [])))].append((jid, jptext.get(jid, "")))
        ok.append((jid, v, inst, conf, body))

    # 슬라이스 충돌 — 본문이 다른 두 블록이 같은 조각을 물면 최소 하나는 틀렸다
    conflict = set()
    for _k, js in claims.items():
        if len({t for _i, t in js}) > 1:
            for i, _t in js:
                conflict.add(i)
    ok = [x for x in ok if x[0] not in conflict]
    if conflict:
        rej["슬라이스 충돌"] += len(conflict)

    print(f"제안 {len(props)}건 → **병합 가능 {len(ok)}건**")
    for r, n in rej.most_common():
        print(f"  제외 {n:3}  {r}")
    if detail:
        print("\n검증 실패 상세(최대 12):")
        for d in detail[:12]:
            print(f"  {d[0]} {d[1]:<9} {d[2]:<18} {d[3]}")
    byc = collections.Counter(c for _i, _v, _n, c, _b in ok)
    print(f"\n신뢰도: {dict(byc)}")
    byi = collections.Counter(n for _i, _v, n, _c, _b in ok)
    for i, n in byi.most_common():
        print(f"  {i:34} {n}")

    if not apply_:
        print("\n(dry-run — 쓰려면 --apply)")
        return

    tgt = ov.setdefault(f"{game}SCN{scn}", {})
    for jid, v, inst, conf, _b in ok:
        e = {"table": v["table"], "entry_id": v["entry_id"]}
        for f in ("chain", "subs", "speaker"):
            if v.get(f):
                e[f] = v[f]
        e["note"] = f"인스턴스 단위 회수 2026-07-31 ({inst}, 신뢰도 {conf})"
        tgt[str(jid)] = e
    json.dump(ov, open(OV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OV, "a", encoding="utf-8").write("\n")
    print(f"\n{len(ok)}건 병합 완료 → align_overrides.json")


if __name__ == "__main__":
    main()
