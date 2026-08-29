#!/usr/bin/env python3
"""손으로 옮겨 적은 문안(`ours`)을 **정발 엔트리 포인터**로 되돌린다.

**왜.** `ours` 는 우리가 타이핑한 문자열이라 세 가지가 어긋난다 —
① 정발 문장이 **커밋되는 파일에 축자로 남는다**(리포 규칙 "문장급 문안 임베드 금지" 위반),
② A급 맞춤법 치환(`dos_spelling_fixes`)이 **정발 코퍼스에만 걸려** 이 문안은 안 지나간다,
③ 나중에 정발 추출이 개선돼도 이 자리는 안 따라온다.
포인터(`table`/`entry_id`/`chain`)로 바꾸면 셋 다 사라지고 **화면 결과는 그대로**다.

**어떻게.** `chain_text` 가 실제로 만들어 내는 슬라이스를 **같은 방식으로 전부 펼쳐**
(`~변형` · `#페이지` · `.문장`) 정규화 비교한다. 우리가 따로 자르면 파이프라인과 어긋나므로
분할은 반드시 `reinsert_kr_pilot._sentences` 를 그대로 쓴다.

⚠ 후보 테이블은 **맵 제약**으로 좁힌다(`scn_maps.table_maps`) — 다른 마을의 같은 문구가
우연히 잡히면 엉뚱한 인스턴스를 물게 된다.
⚠ 전환 뒤에는 **렌더 결과를 원래 문안과 대조**한다. 맞춤법 규칙이 이제 걸리므로 글자가
달라질 수 있는데, 그건 의도된 개선이라 따로 보고한다.

  python3 tools/ours_to_pointer.py            # 찾기만(기본)
  python3 tools/ours_to_pointer.py --apply    # align_overrides.json 에 반영
  python3 tools/ours_to_pointer.py --min 0.995   # 일치 기준(기본 축자)
"""

import difflib
import glob
import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import MARKUP, OUT_DIR, ROOT
from scn_maps import block_maps, table_maps

OV_PATH = os.path.join(ROOT, "align_overrides.json")
# 마크업 한 벌은 **`common.MARKUP` 이 정본**이다 — 사본을 두면 조용히 갈린다
# (2026-08-29 통합: 여섯 파일 중 둘이 대문자 헥스만 봤다).
_STRIP = MARKUP
_NORM = re.compile(r"[\s.,!?~…·\-'\"]+")


def norm(s):
    return _NORM.sub("", _STRIP.sub("", s))


def slices(text):
    """`chain_text` 가 만들 수 있는 조각을 (chain 표기, 본문) 으로 전부 펼친다."""
    out = []
    base = text.removesuffix("{end}")
    for vi, var in enumerate(base.split("\\x06")):
        vtag = f"~{vi}" if "\\x06" in base else ""
        pages = var.split("{p}")
        out.append((vtag, var))  # 엔트리(변형) 통째
        for pi, page in enumerate(pages):
            if len(pages) > 1:
                out.append((f"{vtag}#{pi}", page))
            sents = R._sentences(page)
            if len(sents) > 1:
                for si, s in enumerate(sents):
                    out.append((f"{vtag}#{pi}.{si}", s))
    return out


def corpus(game):
    """{table: {eid: [(chain 꼬리, 본문)]}}"""
    out = {}
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", game, "*.json"))):
        doc = json.load(open(p, encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        table = f"{game}/{os.path.basename(p)[:-5]}"
        out[table] = {
            e["entry_id"]: slices(e.get("text", ""))
            for e in doc.get("entries", [])
            if isinstance(e, dict)
        }
    return out


def main():
    game = "ED1"
    lo = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 0.995
    ov = json.load(open(OV_PATH, encoding="utf-8"))
    corp = corpus(game)
    learned, exempt = table_maps(game)

    found, miss = [], 0
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        bm = block_maps(game, scn)
        for eid, e in sorted(ov.get(name, {}).items(), key=lambda kv: (kv[0].isdigit(), kv[0])):
            if not isinstance(e, dict) or not isinstance(e.get("ours"), str):
                continue
            o = norm(e["ours"])
            if not o:
                continue
            mp = bm.get(int(eid)) if eid.isdigit() else None
            # 후보 테이블: 이미 물고 있는 것 → 같은 맵 → 맵에 안 묶인 공용
            pref = [e["table"]] if e.get("table") in corp else []
            tabs = pref + [t for t in corp if learned.get(t) == mp or t in exempt]
            best = None
            for t in tabs:
                for kr_eid, sl in corp[t].items():
                    for tag, body in sl:
                        r = difflib.SequenceMatcher(None, o, norm(body)).ratio()
                        if r >= lo and (best is None or r > best[0]):
                            best = (r, t, kr_eid, tag)
                if best and best[0] >= 0.9999 and t in pref:
                    break
            if best is None:
                miss += 1
                continue
            found.append((name, eid, e, *best))

    print(f"{'씬':10} {'jp':>6}  전환 대상 → 정발 포인터")
    for name, eid, e, r, t, kr_eid, tag in found:
        print(
            f"{name:10} {eid:>6}  ({r:.3f}) {t} chain={kr_eid}{tag}"
            f"   {e['ours'].replace(chr(10), ' ')[:40]}"
        )
    print(f"\n전환 가능 {len(found)}건 · 못 찾음 {miss}건 (기준 {lo})")
    if "--apply" not in sys.argv:
        print("(찾기만 — 반영하려면 --apply)")
        return
    for name, eid, e, _r, t, kr_eid, tag in found:
        new = {k: v for k, v in e.items() if k != "ours"}
        new["table"], new["entry_id"] = t, kr_eid
        if tag:
            new["chain"] = [f"{kr_eid}{tag}"]
        new["note"] = (e.get("note", "") + " | ours→포인터 전환 2026-08-04").lstrip(" |")
        ov[name][eid] = new
    json.dump(ov, open(OV_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {OV_PATH} 갱신. 재빌드해 렌더 결과를 대조할 것.")


if __name__ == "__main__":
    main()
