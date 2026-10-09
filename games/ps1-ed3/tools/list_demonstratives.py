"""지시사 목록기 — 「저/그/이」가 원문과 맞나 **후보를 센다**.

🔴 **게이트가 아니다.** 「보이는 데 있나」는 장면을 알아야 갈리므로 기계로 못 닫는다
(ss-ed3 가 독립적으로 같은 결론에 닿았다). 이 도구는 **판정하지 않고 자리를 모아 준다** —
사람이 그 목록만 보면 되게 하는 것이 목적이다.

## 왜 필요한가

일본어 `あの/あれ` 는 **눈앞에 없는 것을 가리키는 조응**으로도 쓴다(`あの話` = 그 얘기 ·
`あの人` = 그 사람). 한국어 「저」는 **보이는 데 있어야** 쓴다. 그대로 옮기면
**원문이 `あの` 라서 오히려 안심하고 지나간다** — ps1-ed1+2 실측: 「저 드래곤이란 게 저거야?」
가 틀렸고 드래곤은 눈에 안 보이는 곳에 있었다.

실측 분모(2026-09-12): 원문 `あの`+`あれ` 가 **ED3 469 · ED4 301**. 첫 씬 165줄에는 셋뿐이었고
셋 다 우연히 맞았다 — **축을 몰라도 문맥으로 맞을 수 있다는 게 이 도구가 필요한 이유다**
(469 중 몇이 새는지 모른다).

## 부류 셋 — 위험도가 다르다 (ss-ed3 실측으로 갈랐다)

| 부류 | 무엇 | 어떻게 보나 |
| --- | --- | --- |
| `made-up` | 🔴 **원문에 지시사가 없는데 우리가 넣었다** | **기계로 닫힌다** — 원문 대조만으로 결함이다 |
| `ano` | ⚠ 원문 `あの/あれ` + 우리 「저」 | **가장 위험** — 조응이면 「그」가 맞다. 사람이 장면을 본다 |
| `sono` | 원문 `その/それ` + 우리 「저」 | 1순위 후보 — 거의 「그」다 |

🔴 **`その` 만 잡는 검사기를 만들면 위험한 쪽을 통째로 놓친다.** ss-ed3 표본에서 `その` 2 ·
`あの` 70 · 지시사 없음 18 이었다 — **분모가 `あの` 에 몰려 있다.**

## 언제 부르나 (게이트에 안 물리므로 여기 적는다)

🔴 **안 도는 검사기는 잊힌다.** 게이트에 못 물릴 성격이면 **부르는 시점을 문서에 적는 것으로
갈음한다**(ss-ed1+2 가 `check_determinism` 에서 낸 규약).

- **씬 하나를 정본에 옮긴 직후** — 그 씬만 보면 후보가 몇 안 된다(`--member` 로 좁힌다).
- **묶음 ④(연출)·P4(대사) 를 닫기 전에** 전량으로 한 번.
- **인게임 QA 회차 전에** — 화면을 보는 김에 그 자리를 같이 확인한다.

    python3 tools/list_demonstratives.py --disc ed3
    python3 tools/list_demonstratives.py --disc ed3 --member FT0000 --show
    python3 tools/list_demonstratives.py --disc ed4 --kind made-up --show

⚠ `shared/` 에 올리지 않는다 — 소비자가 둘(ps1-ed3 · ps1-ed1+2)인데 **같은 `script/*.json`
꼴**이라 복사가 싸다. 꼴이 다른 트랙(ss-ed3 는 MAP 단위 · md 는 스트림)은 그대로 못 쓴다.
**셋째 소비자가 꼴까지 맞으면** 그때 올린다(설계 원칙 YAGNI).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import script as script_canon

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


def scan(disc, member=None):
    """[(부류, 아카이브, 멤버, 색인, 원문, 우리 문안, 걸린 낱말)] — 후보 전량."""
    src = {(a, m): dict(segs) for a, m, segs in script_canon.members(disc)}
    out = []
    for (archive, mem), lines in sorted(script_canon.load(disc).items()):
        if member and member not in mem:
            continue
        jp_by_idx = src.get((archive, mem), {})
        for i, row in sorted(lines.items()):
            words = kr_hits(row["kr"])
            if not words:
                continue
            jp = jp_by_idx.get(i, "")
            out.append((classify(jp), archive, mem, i, jp, row["kr"], words))
    order = {k: n for n, k in enumerate(KINDS)}
    out.sort(key=lambda r: (order[r[0]], r[2], r[3]))
    return out


def main():
    ap = argparse.ArgumentParser(description="지시사 후보 목록 (게이트 아님)")
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--member", help="멤버 이름의 일부로 좁힌다 (예 FT0000)")
    ap.add_argument("--kind", choices=KINDS, help="한 부류만")
    ap.add_argument("--show", action="store_true", help="자리마다 원문·문안을 찍는다")
    a = ap.parse_args()
    common.verify_source(a.disc)

    rows = scan(a.disc, a.member)
    if a.kind:
        rows = [r for r in rows if r[0] == a.kind]
    n = {k: sum(1 for r in rows if r[0] == k) for k in KINDS}
    total = sum(len(v) for v in script_canon.load(a.disc).values())
    print(
        f"{a.disc}: 정본 {total:,}줄 중 「저」 지시사가 든 줄 {len(rows)} — "
        f"🔴 made-up {n['made-up']} · ⚠ ano {n['ano']} · sono {n['sono']}"
    )
    if not rows:
        print("  (후보 없음)")
        return 0
    print(
        "  🔴 made-up = 원문에 지시사가 없다(또는 근칭이다) → **원문 대조만으로 결함**\n"
        "  ⚠ ano     = 원문 あの/あれ → 조응이면 「그」다. **장면을 봐야 갈린다**\n"
        "  sono      = 원문 その/それ → 거의 「그」다"
    )
    if a.show:
        for kind, _archive, mem, i, jp, kr, words in rows:
            mark = {"made-up": "🔴", "ano": "⚠ ", "sono": "  "}[kind]
            print(f"  {mark} {mem}[{i}] {'·'.join(words)}")
            print(f"       원문 {jp}")
            print(f"       우리 {kr}")
    else:
        print("  (자리를 보려면 `--show`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
