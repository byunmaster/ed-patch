#!/usr/bin/env python3
"""안 쓰인 정발 페이지 ↔ 옆의 미번역 블록을 짝지어 후보로 낸다.

**왜(2026-08-04 실측).** 2장 QA 첫 라운드에서 나온 오배정 넷이 전부 같은 꼴이었다 —
정발 한 엔트리가 여러 페이지({p})인데 PS1 은 그걸 **여러 블록**으로 쪼개 놓았고, 한 블록이
엔트리를 통째로 물면 **나머지 페이지의 임자가 미번역으로 남는다**(jp1210·jp1212·jp1214·jp1218).
반대로 임자 없는 페이지가 앞 블록 창에 붙어 나와 "정발에 없는 대사"로 보이기도 한다.

기계로 찾을 수 있는 자리다 — 배정된 엔트리의 **안 쓰인 페이지**를 모으고, 그 엔트리를 쓰는
블록 **근처의 미번역 블록**을 후보로 짝지운다. 판단은 사람이 한다(순서·화자·창 수).

⚠ 산출물은 정발 문안을 담으므로 **REVIEW_DIR(work/review, gitignore)** 로만 나간다.

  python3 tools/find_page_gaps.py ED1SCN2          # 후보 목록 → work/review/page_gaps_ED1SCN2.md
  python3 tools/find_page_gaps.py ED1SCN2 --near 5 # 인접 판정 범위(기본 3)
  python3 tools/find_page_gaps.py ED1SCN2 --apply  # **모호하지 않은 것만** 정본에 반영

⚠ `--apply` 는 **딱 붙은 자리만** 건드린다 — 안 쓰인 페이지가 k개이고, 그 엔트리를 쓰는
마지막 블록 **바로 다음 k개**가 전부 미번역이고 같은 맵일 때만. 하나라도 어긋나면 건너뛴다.
추정이 아니라 **순서 대응**이라 `recover_twins`(바이트 동일)보다는 약하고 유사도 배정보다는
훨씬 강하다. 그래도 최종 확인은 인게임이다.
"""

import json
import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import OUT_DIR, REVIEW_DIR, ROOT
from scn_maps import block_maps
from todo_untranslated import pending


def entry_pages(table, entry_id):
    """정발 엔트리 → 페이지 본문 목록({p} 분할)."""
    game, name = table.split("/")
    doc = json.load(open(os.path.join(OUT_DIR, "dos_kr", game, f"{name}.json"), encoding="utf-8"))
    for e in doc["entries"]:
        if e.get("entry_id") == entry_id:
            return (e.get("text") or "").split("{p}")
    return []


def assignments(scn_name):
    """{jp_eid: (table, entry_id, 소비 페이지 집합 또는 None=엔트리 통째)}."""
    from align_map import scene_map

    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8"))
    out = {}
    for eid, v in scene_map(scn_name).items():
        out[eid] = (v["table"], v["entry_id"], None)
    for k, v in ov.get(scn_name, {}).items():
        if not (k.isdigit() and isinstance(v, dict) and "table" in v):
            continue
        pages = None
        if "chain" in v:
            pages = set()
            for it in v["chain"]:
                # `+` = 앞 항목에 이어붙임(2026-08-06 도입). 접두를 안 떼면 `int()` 가 죽거나
                # **소비 안 한 페이지로 오인**해 후보로 다시 올라온다(C_203#28 실측).
                ent, _, pg = str(it).lstrip("+").partition("#")
                # `31~0` = 화자 변형(\x06 분할). 변형 번호를 안 떼면 `int()` 가 죽는다
                ent = ent.partition("~")[0]
                if not ent.isdigit():
                    continue
                # `12#0` = 12번 엔트리 0페이지 · `12` = 통째 · `12#0.5` 류는 부분 슬라이스
                if pg.isdigit() and int(ent) == v["entry_id"]:
                    pages.add(int(pg))
                # ⚠ `12#0.3` 처럼 **문장 슬라이스**도 그 페이지를 쓴 것이다 — 안 세면 같은
                # 페이지가 "안 쓰임"으로 남아 후보 목록이 부풀고 진짜가 묻힌다.
                elif "." in pg and pg.partition(".")[0].isdigit() and int(ent) == v["entry_id"]:
                    pages.add(int(pg.partition(".")[0]))
        out[int(k)] = (v["table"], v["entry_id"], pages)
    return out


def apply_unambiguous(scn_name, rows, todo, bm):
    """안 쓰인 페이지 k개 ↔ **바로 뒤 연속 k개**가 전부 미번역·같은 맵일 때만 정본에 쓴다."""
    path = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(path, encoding="utf-8"))
    scn = ov.setdefault(scn_name, {})
    applied, skipped = [], []
    for tbl, ent, free, _pgs, by, _cands, real, cap, whole in rows:
        anchor = max(by)
        want = [anchor + i + 1 for i in range(len(free))]
        why = None
        if whole and len(by) != 1:
            # 통째 배정을 앞뒤로 자르려면 임자가 하나여야 한다(여러 블록이 같은 엔트리를
            # 물면 어느 쪽을 자를지 알 수 없다 — 상점 공통 문구가 그렇다)
            why = "같은 엔트리를 여러 블록이 통째로 뭄"
        elif any(e not in todo for e in want):
            why = "뒤 연속 블록이 미번역이 아님"
        elif len({bm.get(e) for e in [anchor, *want]}) != 1:
            why = "맵이 갈림"
        elif any(str(e) in scn for e in want):
            why = "이미 오버라이드가 있음"
        if why:
            skipped.append((tbl, ent, why))
            continue
        if whole:
            # ⚠ **앵커도 같이 잘라야 한다.** 안 자르면 앵커가 엔트리를 통째로 계속 물어서
            # 뒷페이지가 **두 곳에 중복 렌더**된다(2026-08-04 실측 — jp962 가 p0·p1·p2 를
            # 한 창에 담은 채 jp963·jp964 에도 같은 문장이 나갔다).
            scn[str(anchor)] = {
                "table": tbl,
                "entry_id": ent,
                "chain": [f"{ent}#{p}" for p in real[:cap]],
                "note": f"페이지 갭 회수(find_page_gaps 2026-08-04) — 뒷페이지를 jp{want[0]}~ 로 넘기고 앞 {cap}페이지만 유지",
            }
        for e, p in zip(want, free, strict=True):
            scn[str(e)] = {
                "table": tbl,
                "entry_id": ent,
                "chain": [f"{ent}#{p}"],
                "note": f"페이지 갭 회수(find_page_gaps 2026-08-04) — jp{anchor} 가 문 {tbl}#{ent} 의 남은 p{p}",
            }
            applied.append(e)
    json.dump(ov, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{scn_name}: {len(applied)}블록 회수 · 건너뜀 {len(skipped)}엔트리")
    for tbl, ent, why in skipped[:8]:
        print(f"  - {tbl}#{ent}: {why}")
    return 0


def main():
    scn_name = next((a for a in sys.argv[1:] if a.startswith("ED")), "ED1SCN2")
    near = int(sys.argv[sys.argv.index("--near") + 1]) if "--near" in sys.argv else 3
    game, scn = scn_name[:3], int(scn_name.split("SCN")[1])

    asg = assignments(scn_name)
    todo = {e: (mp, spk, body) for e, mp, spk, body in pending(game, scn)}
    bm = block_maps(game, scn)

    # 엔트리별 소비 페이지
    used = {}
    for eid, (tbl, ent, pages) in asg.items():
        k = (tbl, ent)
        cur = used.setdefault(k, {"pages": set(), "whole": False, "by": []})
        cur["by"].append(eid)
        if pages is None:
            cur["whole"] = True
        else:
            cur["pages"] |= pages

    # 블록별 창 수 — 통째 배정에서 "창보다 페이지가 많은" 자리를 잡는 데 쓴다.
    tr, _, _ = R.load_translations(scn_name.replace("SCN", "_SCN"), scn_name)
    wins = {e: (t[2] if len(t) > 2 and isinstance(t[2], int) else 1) for e, t in tr.items()}

    # 시스템 문구 일원화(`sys_phrases`)가 표준안으로 쓰는 엔트리는 **일부러 여러 블록이
    # 공유**한다 — "안 쓰인 페이지"가 남는 게 정상이라 후보로 내면 안 된다. 안 빼면 상점·현자
    # 흐름 엔트리(T_011#4·T_011#6·T_033#6·T_040#0·T_333#2)가 근처 미번역을 전부 끌어모아
    # 보고서가 읽을 수 없게 된다(2026-08-06 실측 — 진짜 후보가 그 사이에 묻혔다).
    from sys_phrases import spec as _sys_spec

    sys_src = {(d["src"]["table"], d["src"]["entry_id"]) for d in _sys_spec().values()}

    rows = []
    for (tbl, ent), info in sorted(used.items()):
        if (tbl, ent) in sys_src:
            continue
        pgs = entry_pages(tbl, ent)
        # 본문이 있는 페이지만 후보(제어코드·빈 페이지 제외)
        real = [i for i, p in enumerate(pgs) if any("가" <= c <= "힣" for c in p)]
        cap = max((wins.get(b, 1) for b in info["by"]), default=1)
        if info["whole"]:
            # ⚠ 통째 배정은 "다 썼다"가 아니다 — 블록의 **창 수**보다 페이지가 많으면 남는 게
            # 한 창에 욱여넣어지고(jp1214 실측: 두 문장이 한 창에), 그 페이지의 임자가 미번역으로
            # 남는다. 창 수를 넘는 뒷페이지를 후보로 본다.
            free = real[cap:]
        else:
            free = [i for i in real if i not in info["pages"]]
        if not free:
            continue
        # 이 엔트리를 쓰는 블록 근처의 미번역 블록
        cands = sorted({e for b in info["by"] for e in range(b - near, b + near + 1) if e in todo})
        if not cands:
            continue
        rows.append((tbl, ent, free, pgs, info["by"], cands, real, cap, info["whole"]))

    if "--apply" in sys.argv:
        return apply_unambiguous(scn_name, rows, todo, bm)

    os.makedirs(REVIEW_DIR, exist_ok=True)
    path = os.path.join(REVIEW_DIR, f"page_gaps_{scn_name}.md")
    n_cand = len({e for r in rows for e in r[5]})
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {scn_name} 안 쓰인 정발 페이지 ↔ 인접 미번역 블록 (인접 ±{near})\n\n")
        f.write(f"엔트리 {len(rows)}건 · 후보 블록 {n_cand}건. **판단은 사람이 한다.**\n")
        for tbl, ent, free, pgs, by, cands, _real, _cap, _whole in rows:
            f.write(f"\n## {tbl}#{ent} — 안 쓰인 페이지 {free} (쓰는 블록 {by})\n\n")
            f.writelines(f"- p{i}: {pgs[i].strip()[:110]}\n" for i in free)
            f.write("\n  인접 미번역:\n")
            for e in cands:
                mp, spk, body = todo[e]
                f.write(f"  - jp{e} [{mp}] {spk}: {body[:70]}\n")
    print(f"{scn_name}: 안 쓰인 페이지를 가진 엔트리 {len(rows)}건 · 후보 블록 {n_cand}건")
    print(f"  → {path}")


if __name__ == "__main__":
    main()
