#!/usr/bin/env python3
"""정발 코퍼스 **전수 검색** — 「정발에 없다」와 「사본마다 다르다」를 그 자리에서 가른다.

**왜.** 이 프로젝트에서 가장 자주 틀린 판단이 둘인데 원인이 같다 — **한 자리만 보고 결론을
냈다.**

- **「정발에 대응이 없다」가 여섯 번 틀렸다**(2026-08-10·11). 이웃 블록이 무는 표에만 없었을
  뿐 **다른 시점 사본**에 멀쩡히 있었다(`보람`→`T_034#12` · `처음 뵈`→`T_432#18` ·
  `말 걸지`→`T_204#31`). 어간 한 낱말로 전 표를 훑으면 나온다.
- **「부호가 없다」도 사본을 보면 뒤집힌다.** `오오, 에리온님` 은 우리가 문 `T_232#0` 엔 온점이
  없지만 사본 `T_233#0` 엔 있다 — 「정발 관용상 무부호」라고 노트까지 달아 뒀던 게 오판이었다.

mcpads PC-98 패처의 `export_translation_proposal` 이 제안을 적용하기 전에 **같은 원문 출현을
빠뜨리지 않았는지** 검증하는 것과 같은 자리다(2026-08-11 흡수). 우리는 검토가 대화로 도니
manifest 대신 **질의 도구**로 옮겼다.

⚠ 검색 대상은 **`spell_fix` 를 통과한 뒤의 문안**이다(`reinsert_kr_pilot.corpus_text`) —
화면에 나가는 표기와 같아야 「있다/없다」 판정이 맞는다.
⚠ 정발 문안이 화면에 찍히므로 **결과를 커밋하지 말 것**(저작권 규칙).

  python3 tools/find_text.py 보람                 # 전 표에서 찾는다
  python3 tools/find_text.py --used 처음 뵈       # 화면에 실제로 쓰이는 자리만
  python3 tools/find_text.py --siblings ED1/T_232#0   # 그 엔트리의 시점 사본들을 나란히
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import ROOT  # noqa: E402
from llm_assign import _raw  # noqa: E402

GAME = "ED1"
CTX = 34  # 앞뒤로 보여 줄 글자 수


def used_map():
    """{(표, 엔트리): [씬:jp_eid …]} — 그 정발 엔트리를 **무는 블록**들."""
    out = collections.defaultdict(list)
    for fn in ("align_map.json", "align_overrides.json"):
        doc = json.load(open(os.path.join(ROOT, fn), encoding="utf-8"))
        for scn, blocks in doc.items():
            if not isinstance(blocks, dict):
                continue
            for jp, v in blocks.items():
                if not (isinstance(v, dict) and v.get("table") and v.get("entry_id") is not None):
                    continue
                out[(v["table"], v["entry_id"])].append(f"{scn}:jp{jp}")
    return out


def corpus():
    """{(표, 엔트리): 교정 후 문안}"""
    return {k: R.corpus_text(v) for k, v in _raw(GAME).items() if v}


def siblings(table):
    """같은 방의 시점 사본 표들 — 정발 파일명 규약상 **접두 4글자가 같으면 같은 방**이다
    (`T_04x`=네리아 · `C_00x`=루디아 성). `segment_copy.table_pool` 이 쓰는 규칙과 같다."""
    stem = table.split("/", 1)[1] if "/" in table else table
    pre = stem[:4]
    return sorted({t for t, _e in corpus() if t.split("/", 1)[1].startswith(pre)})


def show(needle, used_only=False):
    used, corp = used_map(), corpus()
    hits = [(k, t) for k, t in sorted(corp.items()) if needle in t]
    if used_only:
        hits = [(k, t) for k, t in hits if used.get(k)]
    print(f"「{needle}」 {len(hits)}곳" + (" (화면에 쓰이는 것만)" if used_only else ""))
    for (tbl, eid), t in hits:
        i = t.find(needle)
        seg = t[max(0, i - CTX) : i + len(needle) + CTX].replace("\n", " ")
        who = used.get((tbl, eid))
        mark = "●" if who else "○"  # ● 화면에 나간다 · ○ 아무도 안 문다
        print(f"  {mark} {tbl}#{eid:<4} …{seg}…")
        if who:
            print(f"      ← {' '.join(who[:6])}{' …' if len(who) > 6 else ''}")
    if not used_only and not any(used.get(k) for k, _t in hits):
        print("  ⚠ 전부 ○ — 찾긴 했는데 **아무 블록도 안 문다**. 배정이 빠진 자리일 수 있다.")


def show_siblings(coord):
    tbl, _, eid = coord.partition("#")
    if not eid.isdigit():
        raise SystemExit("좌표는 `ED1/T_232#0` 꼴로")
    eid = int(eid)
    used, corp = used_map(), corpus()
    pool = siblings(tbl)
    print(f"{tbl}#{eid} 의 시점 사본 — 접두 `{tbl.split('/')[-1][:4]}` 표 {len(pool)}개")
    for t in pool:
        v = corp.get((t, eid))
        who = used.get((t, eid))
        mark = "●" if who else "○"
        here = " ←여기" if t == tbl else ""
        if v is None:
            print(f"  · {t}#{eid}: (엔트리 없음){here}")
            continue
        print(f"  {mark} {t}#{eid}: {v[:90]!r}{here}")
    print("\n⚠ **사본마다 부호·표기가 다를 수 있다** — 한 벌만 보고 「정발이 원래 그렇다」로")
    print("  결론 내지 말 것(`오오, 에리온님` 실측 2026-08-11).")


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "--siblings":
        return show_siblings(argv[1])
    used_only = argv[0] == "--used"
    needle = " ".join(argv[1:] if used_only else argv)
    return show(needle, used_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
