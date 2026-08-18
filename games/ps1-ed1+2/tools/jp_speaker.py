#!/usr/bin/env python3
"""JP 블록의 **화자를 추정**한다 — 정발 후보를 좁히는 데 쓴다(확정용이 아니다).

## 왜 필요한가

정발 전수 대조의 순서는 **장소·화자·시기로 후보를 좁힌 뒤 JP 와 정발을 대조**하는 것이다
(유저 확정 2026-08-17). 그런데 미탐색 블록의 **68%가 화자 정보가 없었다** — JP 원문에
`{c}이름{c}` 헤더가 있는 건 대사의 **첫 블록뿐**이고, 이어지는 조각엔 없다(ED1 실측
1,675건). 화자가 없으면 후보가 안 좁혀져 그 블록은 아예 판정에 못 들어간다.

## 어떻게

헤더가 나오면 현재 화자를 갈고, 헤더 없는 블록은 그 화자를 **잇는다**. 대사가 여러 블록에
걸치는 게 원작의 기본 꼴이라 이게 맞는다.

## ⚠ 확정이 아니다 — 후보 좁히기용이다

우리 정본의 `s`(사람이 적은 화자) 1,000건을 정답셋으로 재니 **전체 87%**, 거리별로는:

| 헤더로부터 | 정확도 |
| ---------- | -----: |
| 1블록 뒤   |    90% |
| 2블록 뒤   |    90% |
| 3블록 뒤   |    77% |
| 4블록 이상 |    85% |

틀리는 자리는 **대사가 오가는 장면**이다 — `아론` 다음에 헤더 없이 `소니아` 가 받는 꼴.
그래서 이 값으로 **채택을 결정하면 안 된다.** 후보 목록을 줄이는 데만 쓰고, 최종 판정은
JP 원문을 읽어서 한다. `confidence` 를 같이 돌려주므로 부르는 쪽이 문턱을 정한다.

  python3 tools/jp_speaker.py ED1SCN1      # 씬의 블록별 추정 화자
  python3 tools/jp_speaker.py --verify     # 정본 `s` 로 정확도 재기
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from align_jp_kr import SPEAKER_DICT, kana_to_hangul, name_sim
from common import OUT_DIR, ROOT

HEADER = re.compile(r"\{c\}([^{]+)\{c\}")
# 거리별 실측 정확도 — 부르는 쪽이 문턱을 정할 수 있게 값으로 준다
CONF = {0: 1.00, 1: 0.90, 2: 0.90, 3: 0.77}
CONF_FAR = 0.85


def kr_name(jp_spk):
    """JP 화자 → 우리 표기. 정본 사전이 먼저고, 없으면 음차."""
    if not jp_spk:
        return None
    return SPEAKER_DICT.get(jp_spk) or kana_to_hangul(jp_spk) or None


def speakers(scn):
    """{eid: (JP 화자, 우리 표기, confidence)} — 헤더 없는 블록은 앞 화자를 잇는다."""
    p = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
    doc = json.load(open(p, encoding="utf-8"))
    out, cur, dist = {}, None, 0
    for e in sorted(doc["entries"], key=lambda x: x["entry_id"]):
        if e.get("kind") != "block":
            continue
        m = HEADER.match(e.get("text") or "")
        if m:
            cur, dist = m.group(1), 0
        elif cur is not None:
            dist += 1
        if cur is None:
            continue
        out[e["entry_id"]] = (cur, kr_name(cur), CONF.get(dist, CONF_FAR))
    return out


def verify():
    """정본 `s` 를 정답으로 거리별 정확도를 잰다 — ⚠ **필터를 만든 뒤 그 필터로 재면 순환**이라
    사람이 적은 화자만 정답으로 쓴다."""
    band = collections.defaultdict(collections.Counter)
    for i in range(1, 7):
        scn = f"ED1SCN{i}"
        sp = speakers(scn)
        p = os.path.join(ROOT, "script", f"{scn}.json")
        if not os.path.exists(p):
            continue
        canon = json.load(open(p, encoding="utf-8"))
        for eid, (_jp, ours, conf) in sp.items():
            s = (canon.get(str(eid)) or {}).get("s")
            if not s or not ours:
                continue
            band[conf]["ok" if (ours == s or name_sim(ours, s) >= 0.6) else "no"] += 1
    print("  화자 추정 정확도(정본 `s` 대비)")
    for c in sorted(band, reverse=True):
        k = band[c]
        t = k["ok"] + k["no"]
        print(f"    confidence {c:.2f}: {k['ok']:4d}/{t:4d}  {k['ok'] * 100 // t}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", nargs="?")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        verify()
        return 0
    if not a.scene:
        ap.error("씬 이름을 주거나 --verify")
    for eid, (jp, ours, conf) in sorted(speakers(a.scene).items()):
        print(f"  jp{eid:<5} {jp} → {ours}  ({conf:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
