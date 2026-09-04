#!/usr/bin/env python3
"""화자 변형 겹침 검출 — 정발 한 엔트리에 묶인 변형이 **한 창에 쏟아지는** 자리를 찾는다.

정발은 같은 NPC 의 상태별·화자별 대사를 한 엔트리에 `\\x06`/`\\x07` 로 이어 붙여 두고,
PS1 은 그걸 **블록으로 쪼개** 둔다. 그래서 엔트리를 통째로 물면 변형이 전부 한 창에 나온다
(`아아, 지겨울 정도라니까. … 음.. 파렌왕국에서 … 아아 얼마 전에 …`). 고르는 문법은
`chain: ["31~0#0"]`(`eid~v`) — `text-pipeline.md` 참조.

⚠ **배정 경로가 둘**이라 소스만 봐서는 못 잡는다. `align_overrides.json` 뿐 아니라
의미정렬 쌍(`work/derived/align`)으로 들어온 블록도 같은 사고를 낸다 — 실제로 오버라이드만
훑던 감사기가 마스쿤 시장 구출(jp402, 변형 4벌)을 놓쳤다(2026-08-07). 그래서 이 도구는
**재조립기가 실제로 만든 최종 문안**을 보고, 그 안에 서로 다른 변형의 알맹이가 둘 이상
들어 있는지를 센다. 어떤 경로로 배정됐든 걸린다.

⚠ 남는 오탐 하나 — `\x06`/`\x07` 가 **변형 구분이 아니라 이름줄과 본문 사이**에 오는
엔트리가 있다(`T_116#14` = `세리오스왕자님` + `\x06` + `요르도 항구도 …`). 한 발화인데
둘로 세어진다. 개수가 적고(SCN2 5건) 눈으로 한 번 보면 갈리므로 규칙을 더 얹지 않았다.

  python3 tools/check_variants.py            # 전 씬
  python3 tools/check_variants.py ED1SCN2    # 한 씬
"""

import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import OUT_DIR, ROOT
from past_llm_assign import _raw

MIN_CHARS = 8  # 변형 하나가 '들어 있다'고 볼 최소 글자수(짧은 감탄사 오탐 방지)


def _picked(ov):
    """오버라이드가 **변형을 손으로 골라 이었는가**(`chain` 원소 둘 이상에 `~v`).

    이 도구가 잡으려는 건 "엔트리를 통째로 물어 변형이 쏟아진" 자리다. 정발이 리더별로
    어미만 다른 대사를 「공통 앞부분 + 리더별 꼬리」로 갈라 둔 자리(`H_210#19`:
    `…신탁을 받으러` + `들어가는게 아니었나요.`/`들어간다고 하지 않았어.`)는 사람이
    `~v` 로 두 벌을 짚어 이은 것이라 **의도한 배정**이다 — 겹침이 아니다.
    실제로 오배정 셋(jp1086·295·296)은 전부 `#page` 로 통째로 문 자리였고, 의도한 조합
    셋(jp167·168·170)은 전부 `~v` 조합이었다(2026-08-11).
    """
    ch = [str(c) for c in (ov.get("chain") or [])]
    return sum("~" in c for c in ch) >= 2


def _plain(s):
    """마크업·제어코드를 걷어낸 한글 알맹이만."""
    s = re.sub(r"\{[a-z/]*\}", "", s)
    s = re.sub(r"\\x[0-9A-Fa-f]{2}", "", s)
    return re.sub(r"\s+", "", s)


def variants(text):
    """엔트리 → 변형 조각들. `\\x06`·`\\x07` 둘 다 변형 마커로 쓰인다."""
    parts = re.split(r"\\x0[67]", text.removesuffix("{end}"))
    return [p for p in parts if len(_plain(p)) >= MIN_CHARS]


def sources(game, scn):
    """{jp_id: (table, entry_id)} — 오버라이드와 정렬 쌍을 합친다(오버라이드 우선).

    ⚠ 사람이 `~v` 로 변형 둘 이상을 짚어 이은 자리는 뺀다(`_picked`).
    """
    out = {}
    p = os.path.join(OUT_DIR, "align", f"{game}_SCN{scn}.json")
    if os.path.exists(p):
        for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
            if pr.get("flags"):
                continue
            kr = pr.get("kr") or {}
            if kr.get("table") is not None and kr.get("entry_id") is not None:
                out[pr["jp"]["entry_id"]] = (kr["table"], kr["entry_id"])
    # ⚠ 상대경로면 레포 루트에서 돌릴 때 죽는다 — 경로 정본은 `common.ROOT` 다.
    p = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(p, encoding="utf-8")).get(f"{game}SCN{scn}", {})
    for j, v in ov.items():
        # `ours`(우리가 쓴 문안)는 정발 엔트리를 안 물어 `entry_id` 가 없다 — 볼 게 없으니 건너뛴다
        ok = j.isdigit() and isinstance(v, dict) and v.get("entry_id") is not None
        if ok and _picked(v):
            out.pop(int(j), None)
        elif ok and v.get("table") and not v.get("exclude"):
            out[int(j)] = (v["table"], v["entry_id"])
    return out


def scan(game, scn):
    name = f"{game}SCN{scn}"
    tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
    raws = _raw(game)
    hits = []
    for jid, (table, eid) in sorted(sources(game, scn).items()):
        t = tr.get(jid)
        if not t or len(t) < 2 or not isinstance(t[1], list):
            continue  # `__shop_price__` 같은 특수 빌더
        got = _plain(" ".join(s for _c, s in t[1]))
        if not got:
            continue
        src = raws.get((table if "/" in table else f"{game}/{table}", eid))
        if not src:
            continue
        vs = variants(src)
        if len(vs) < 2:
            continue
        # 변형 알맹이의 앞 MIN_CHARS 글자가 최종 문안에 있으면 '들어갔다'로 본다
        got_v = [_plain(v) for v in vs if _plain(v)[:MIN_CHARS] in got]
        # ⚠ 접두가 겹치는 변형끼리 서로를 오탐한다(`파렌에서 왔어요` ⊂ `파렌에서 돌아 왔다고`).
        # 그래서 **길이**로 한 번 더 거른다 — 창에 담긴 글자가 가장 긴 변형 하나보다
        # 뚜렷이 많아야 진짜 겹침이다.
        if len(got_v) >= 2 and len(got) > max(len(v) for v in got_v) * 1.3:
            hits.append((jid, table, eid, len(got_v), len(vs)))
    return hits


def main():
    game = "ED1"
    only = next((a for a in sys.argv[1:] if a.startswith(game)), None)
    total = 0
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        if only and only != name:
            continue
        hits = scan(game, scn)
        total += len(hits)
        if hits:
            print(f"\n{name}: 변형 겹침 **{len(hits)}건**")
            for jid, table, eid, n, m in hits:
                print(f"  jp{jid:<5} {table}#{eid:<4} 변형 {m}벌 중 **{n}벌**이 한 창에")
    print(f"\n합계 {total}건" + ("" if total else " — 깨끗하다"))


if __name__ == "__main__":
    main()
