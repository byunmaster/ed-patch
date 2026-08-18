#!/usr/bin/env python3
"""**같은 JP 문장이 화면에서 갈리는가** — 한 대사가 마을마다 다른 말로 나가는 자리를 찾는다.

**왜.** 원작은 같은 대사를 여러 곳에 복제해 둔다(신부·도구점·현자의 상투 문구, 재방문
시점 사본). 그 블록들이 **서로 다른 경로로 문안을 받으면**(어떤 건 정발 포인터, 어떤 건
우리 문안, 또 어떤 건 다른 정발 엔트리) 같은 NPC 가 마을마다 다른 말을 한다.

실측(2026-08-17, ED1): **118종 576블록**이 갈려 있었다.

    おや？これ以上持てないようですね  ×49 `이런? 그 이상은…`  vs ×4 `아니? 그 이상 가지실…`
    また来てくださいね              ×43 `또 오세요.`        vs ×1 `또 들러 주십시오.`
    神父 困ったことが…              4갈래(×29·×6·×6·×2)

⚠ **어느 게이트도 이걸 안 봤다.** 블록마다는 다 멀쩡하고(일본어 0 · 구조 계약 통과 ·
저작권 통과) **블록 사이의 일관성**만 깨져 있어서, 화면을 여러 마을 돌아 보기 전엔 안 드러난다.

⚠ **갈린다고 다 결함은 아니다.** 둘을 걸러야 한다:

- **화자가 다르면** 말투가 갈리는 게 맞다(현자마다 `のじゃな`·`かね`, 정발도 `줄꼬?`·`줄까요?`).
- ⭐ **세그먼트(시점)가 다르면 갈리는 게 맞다** — 원작이 같은 지명을 시점 수만큼 반복해
  두고 정발도 시점마다 다른 파일을 쓴다(`ed1-scene-map.md`). 실측: 루디아 도구점이
  `T_011`(루디아#2)에서는 `어서 오십시오`, `T_013`(루디아#4)에서는 **`아니 왕자님 어서
  오십시오`** 다 — **1장에서는 왕자를 못 알아보고 2장부터 알아보는 설정**이다(유저 QA 확인).
  세그먼트를 안 보고 다수결로 통일하면 그 설정이 지워진다.

그래서 **같은 화자·같은 세그먼트인데 갈리는 것**만 실패로 본다.

⚠ 상점·현자의 매매 문구를 **일부러 통일하지 않는다**(유저 확정 2026-08-17). 정발에서 찾고
없으면 JP 를 옮긴다 — 「상점이니 한 문구로」가 아니라 원작·정발이 갈라 둔 대로 간다.

  python3 tools/check_same_jp.py         # 갈린 자리
  python3 tools/check_same_jp.py -v      # 문안까지
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from align_map import scene_map
from common import OUT_DIR, ROOT
from jp_speaker import speakers

MIN_JP = 12  # 이보다 짧은 JP 는 우연히 같을 수 있다(감탄사·부호)


# ⚠ `rendered` 는 `reinsert_kr_pilot` 이 갖는다 — 검출기마다 다시 짜면 조용히 틀린다.
rendered = R.rendered


def scan(games=("ED1",), verbose=False):
    byjp = collections.defaultdict(lambda: collections.defaultdict(list))
    spk_of, seg_of = {}, {}
    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8"))
    for scn, _lba, _size in R.SCN_FILES:
        if not any(scn.startswith(g) for g in games):
            continue
        doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8"))
        jp = {e["entry_id"]: (e.get("text") or "") for e in doc["entries"]}
        sp = speakers(scn)
        pin = scene_map(scn) or {}
        for eid, txt in rendered(scn).items():
            j = jp.get(eid, "")
            if len(j) < MIN_JP:
                continue
            byjp[j][txt].append((scn, eid))
            spk_of[(scn, eid)] = (sp.get(eid) or (None, None, 0))[1]
            # 세그먼트 = 그 블록이 쓰는 정발 표(= 시점). `ed1-scene-map.md` 의 축이다.
            e = ov.get(scn, {}).get(str(eid)) or {}
            m = pin.get(str(eid)) or pin.get(eid) or {}
            seg_of[(scn, eid)] = e.get("table") or m.get("table")

    same_spk, diff_spk = [], []
    for j, variants in byjp.items():
        if len(variants) < 2:
            continue
        spks = {spk_of.get(loc) for locs in variants.values() for loc in locs}
        segs = {seg_of.get(loc) for locs in variants.values() for loc in locs}
        (same_spk if len(spks) <= 1 and len(segs) <= 1 else diff_spk).append((j, variants))

    n = sum(sum(len(v) for v in var.values()) for _j, var in same_spk)
    print(
        f"  {'✅' if not same_spk else '⚠'} 같은 화자·같은 JP 인데 갈린 자리 {len(same_spk)}종 ({n}블록)"
    )
    if diff_spk:
        print(f"  ℹ 화자·시점이 달라 갈린 자리 {len(diff_spk)}종 — 정상(현자 말투 · 시점 사본)")
    if verbose:
        for j, var in sorted(same_spk, key=lambda x: -sum(len(v) for v in x[1].values()))[:20]:
            print(f"\n     JP {j[:52]}")
            for t, locs in sorted(var.items(), key=lambda x: -len(x[1])):
                print(f"       ×{len(locs):<3d} {t[:52]!r}  {locs[0][0]} jp{locs[0][1]}")
    return len(same_spk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--games", default="ED1")
    a = ap.parse_args()
    return 1 if scan(tuple(a.games.split(",")), a.verbose) else 0


if __name__ == "__main__":
    sys.exit(main())
