"""지시사 목록기 — 「저/그/이」가 원문과 맞나 **후보를 센다**.

🔴 **게이트가 아니다.** 「보이는 데 있나」는 장면을 알아야 갈리므로 기계로 못 닫는다
(ss-ed3 가 독립적으로 같은 결론에 닿았다). 이 도구는 **판정하지 않고 자리를 모아 준다** —
사람이 그 목록만 보면 되게 하는 것이 목적이다.

`games/ps1-ed3+4/tools/list_demonstratives.py` 를 포팅했다(2026-09-13). 판정 로직
(`kr_hits`·`classify`·정규식)은 그대로다 — 로더만 이 게임 꼴(`script/ED*SCN*.json` 평면
딕셔너리 + `work/derived/scn_jp/<scn>.json`)에 맞춰 새로 짰다. `shared/` 로 올리지 않는다 —
소비자가 둘(ps1-ed3+4·ps1-ed1+2)인데 저장 꼴이 갈라 로더가 다르다(설계 원칙 YAGNI).

## 왜 필요한가

일본어 `あの/あれ` 는 **눈앞에 없는 것을 가리키는 조응**으로도 쓴다(`あの話` = 그 얘기 ·
`あの人` = 그 사람). 한국어 「저」는 **보이는 데 있어야** 쓴다. 그대로 옮기면
**원문이 `あの` 라서 오히려 안심하고 지나간다** — 실측: 「저 드래곤이란 게 저거야?」가
틀렸고 드래곤은 눈에 안 보이는 곳에 있었다(qa 037 축, 마스터 QA 2026-09-13).

## 부류 셋 — 위험도가 다르다 (ss-ed3 실측으로 갈랐다)

| 부류 | 무엇 | 어떻게 보나 |
| --- | --- | --- |
| `made-up` | 🔴 **원문에 지시사가 없는데 우리가 넣었다** | **기계로 닫힌다** — 원문 대조만으로 결함이다 |
| `ano` | ⚠ 원문 `あの/あれ` + 우리 「저」 | **가장 위험** — 조응이면 「그」가 맞다. 사람이 장면을 본다 |
| `sono` | 원문 `その/それ` + 우리 「저」 | 1순위 후보 — 거의 「그」다 |

🔴 **`その` 만 잡는 검사기를 만들면 위험한 쪽을 통째로 놓친다** — 분모가 `あの` 에 몰려 있다.

⚠ **1인칭 겸양 「저」가 섞인다**(「저 어른이 되면」·「저 때문에」·「저 같은 자」) — 정규식만으로는
못 가른다. 이 도구는 **원문 대조**를 하므로 원문에 지시사가 없는 1인칭 「저」는 `made-up` 으로
잘못 잡히는 게 아니라 **JP_NEAR/FAR/MID 어디에도 안 걸리면 그대로 made-up** 이 된다 — 즉
1인칭 「저」+원문에 지시사 없음도 made-up 으로 섞여 나온다. **분모를 그대로 「결함」으로
읽지 말 것** — `--show` 로 원문을 같이 보고 1인칭 겸양인지 가른다.

## 언제 부르나 (게이트에 안 물리므로 여기 적는다)

🔴 **안 도는 검사기는 잊힌다.**

- **씬 하나를 정본으로 다듬은 직후** — `--scene ED2SCN5` 로 좁힌다.
- **QA 라운드가 닫히기 전에** 전량으로 한 번.
- **인게임 QA 회차 전에** — 화면을 보는 김에 그 자리를 같이 확인한다.

    python3 tools/list_demonstratives.py
    python3 tools/list_demonstratives.py --scene ED2SCN5 --show
    python3 tools/list_demonstratives.py --kind made-up --show

⚠ 판정(보이나 안 보이나)은 사람이 한다 — 마스터 규칙: **대상이 눈앞에 보이면 이/저, 안
보이면 그**(원문이 `あの` 라도 안 보이면 「그」다).
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT

# 우리 문안에서 찾는 것 — 「저」 계열만 본다.
#   「그」 계열은 원문이 무엇이든 대개 안전하고(조응), 「이」 계열은 근칭이라 원문도 `この` 다.
#   ⚠ 「저」로 시작하는 낱말(저녁·저희·저울…)을 걸러야 한다 — 지시사 「저」는 **뒤에 띄어쓰기나
#     체언이 붙는 꼴**로만 센다.
KR_FAR = re.compile(
    r"(?:^|[\s,.!?\"'“”(\[])"  # 앞이 문장 머리나 공백·부호
    r"(저(?:\s+\S+|것|거|건|기|쪽|래|런|렇|만큼|리|자))"
)
# ⚠ 오탐이 잦은 낱말 — 지시사가 아니다(「저희」·「저녁」은 위 꼴에도 걸린다).
KR_FALSE = re.compile(r"^저(?:희|녁|울|택|주|자세|명|번지)")

JP_FAR = ("あの", "あれ", "あっち", "あそこ")
JP_MID = ("その", "それ", "そっち", "そこ")
JP_NEAR = ("この", "これ", "こっち", "ここ")
KINDS = ("made-up", "ano", "sono")

SCN_COUNT = {"ED1": 6, "ED2": 13}


def kr_hits(kr):
    """[우리 문안의 「저」 지시사]. 지시사가 아닌 낱말은 뺀다."""
    out = []
    for m in KR_FAR.finditer(kr):
        w = m.group(1)
        if KR_FALSE.match(w):
            continue
        out.append(w)
    return out


def classify(jp):
    """원문이 어느 부류인가 — `made-up` · `ano` · `sono`."""
    if any(w in jp for w in JP_FAR):
        return "ano"
    if any(w in jp for w in JP_MID):
        return "sono"
    if any(w in jp for w in JP_NEAR):
        # 근칭 원문에 우리가 원칭을 썼다 — 이것도 만들어 낸 것이다
        return "made-up"
    return "made-up"


def _scenes():
    return [f"{g}SCN{i}" for g in ("ED1", "ED2") for i in range(1, SCN_COUNT[g] + 1)]


def scan(scenes=None):
    """[(부류, 씬, entry_id, 원문, 우리 문안, 걸린 낱말)] — 후보 전량."""
    out = []
    total = 0
    for scn in scenes or _scenes():
        script_path = os.path.join(ROOT, "script", f"{scn}.json")
        jp_path = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(script_path) or not os.path.exists(jp_path):
            continue
        with open(script_path, encoding="utf-8") as f:
            kr_by_id = json.load(f)
        with open(jp_path, encoding="utf-8") as f:
            jp_by_id = {str(e["entry_id"]): e.get("text", "") for e in json.load(f)["entries"]}
        for eid, e in sorted(kr_by_id.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else -1):
            if not isinstance(e, dict):
                continue
            kr = e.get("t") or ""
            total += 1
            words = kr_hits(kr)
            if not words:
                continue
            jp = jp_by_id.get(eid, "")
            out.append((classify(jp), scn, eid, jp, kr, words))
    order = {k: n for n, k in enumerate(KINDS)}
    out.sort(key=lambda r: (order[r[0]], r[1], int(r[2]) if r[2].isdigit() else -1))
    return out, total


def main():
    ap = argparse.ArgumentParser(description="지시사 후보 목록 (게이트 아님)")
    ap.add_argument("--scene", help="씬 이름의 일부로 좁힌다 (예 ED2SCN5)")
    ap.add_argument("--kind", choices=KINDS, help="한 부류만")
    ap.add_argument("--show", action="store_true", help="자리마다 원문·문안을 찍는다")
    a = ap.parse_args()

    scenes = [s for s in _scenes() if not a.scene or a.scene in s] if a.scene else None
    rows, total = scan(scenes)
    if a.kind:
        rows = [r for r in rows if r[0] == a.kind]
    n = {k: sum(1 for r in rows if r[0] == k) for k in KINDS}
    print(
        f"정본 {total:,}블록 중 「저」 지시사가 든 블록 {len(rows)} — "
        f"🔴 made-up {n['made-up']} · ⚠ ano {n['ano']} · sono {n['sono']}"
    )
    if not rows:
        print("  (후보 없음)")
        return 0
    print(
        "  🔴 made-up = 원문에 지시사가 없다(또는 근칭이다, 1인칭 겸양 「저」도 섞인다)\n"
        "  ⚠ ano     = 원문 あの/あれ → 조응이면 「그」다. **장면을 봐야 갈린다**\n"
        "  sono      = 원문 その/それ → 거의 「그」다"
    )
    if a.show:
        for kind, scn, eid, jp, kr, words in rows:
            mark = {"made-up": "🔴", "ano": "⚠ ", "sono": "  "}[kind]
            print(f"  {mark} {scn}:{eid} {'·'.join(words)}")
            print(f"       원문 {jp}")
            print(f"       우리 {kr}")
    else:
        print("  (자리를 보려면 `--show`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
