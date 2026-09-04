#!/usr/bin/env python3
"""번역 진행률 — **번역 정본으로 얼마나 옮겼는가**.

⚠ **축이 바뀌었다**(2026-08-12). 예전엔 `past_assign_pages.jp_open()`(미배정 PS1 블록)으로
「정발 배정 회수율」을 셌는데, 방침이 「정발을 살리되 고친다」로 옮겨 가면서 배정 자체를
그만뒀다([policy.md](../docs/policy.md) 번역 방침). 이제 세는 것은 **`script/` 로 올라간
블록**이다 — 그게 우리가 쓴 문안이고 유일한 정본이다.

세 수가 다르다:

- **총 블록** — 그 씬의 대사 블록(원문 바이트가 있는 것)
- **정본** — `script/ED1SCN*.json` 에 올라간 것. 사람이 읽고 통과시켰다는 뜻
- **재삽입** — 지난 빌드가 실제 이미지에 넣은 수. 구조 계약 게이트를 통과한 것만이라
  정본보다 적을 수 있다(차이가 곧 게이트에 막힌 블록)

  python3 tools/status.py             # 씬 요약
  python3 tools/status.py --maps      # 맵(코드 함수)별 — 어디가 남았는지
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT

GAME = "ED1"
SCENES = range(1, 7)
SCRIPT_DIR = os.path.join(ROOT, "script")


# 🔴 **분모는 「화면에 나가는 대사」다**(2026-08-29). 예전엔 「원문 바이트가 있는 블록」을
#    전부 셌는데, 씬 파일에는 **포인터 표·제어 블록**이 대사와 섞여 있어 분모가 부풀었다 —
#    실측: 남음 887 중 **1,644가 표·제어**고 진짜 문장은 **1**이었다. 같은 게이트가 「화면에
#    나가는 원문 0」이라고 하는데 진행률만 85% 로 떠서 **서로 어긋나 보였다.**
#    ⚠ 「그게 풀리면 얼마가 풀리나」를 안 적으면 병목이 아닌 걸 병목으로 들고 있게 된다.
_KANA = re.compile(r"[ぁ-んァ-ヶ]")  # 가나 = 진짜 일본어 문장의 표지
_ESC = re.compile(r"\\x[0-9A-Fa-f]{2}")  # 이스케이프가 섞이면 바이너리(표·제어)다


def scn_blocks(scn, _skipped=None):
    """{entry_id} — 그 씬의 **대사** 블록. 표·제어는 뺀다.

    ⚠ 한자만 있는 블록도 뺀다 — 포인터 표의 바이트가 한자로 디코드되는 일이 흔해
    (`慓\x17\x80…`) 한자를 표지로 쓰면 표가 대사로 섞인다. **가나**를 표지로 쓴다.
    """
    p = os.path.join(OUT_DIR, "scn_jp", f"{GAME}SCN{scn}.json")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    keep, drop = set(), 0
    for e in doc["entries"]:
        if not e.get("raw_hex"):
            continue
        t = e.get("text", "")
        if _KANA.search(t) and not _ESC.search(t):
            keep.add(e["entry_id"])
        else:
            drop += 1
    if _skipped is not None:
        _skipped[0] += drop
    return keep


def done(scn):
    """{entry_id} — 정본으로 올라간 블록."""
    p = os.path.join(SCRIPT_DIR, f"{GAME}SCN{scn}.json")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as f:
        return {int(k) for k in json.load(f) if k.isdigit()}


def _reinserted():
    """지난 빌드가 남긴 재삽입 수(있으면). 없으면 {}."""
    p = os.path.join(OUT_DIR, "build_stats.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _texts(scn):
    p = os.path.join(OUT_DIR, "scn_jp", f"{GAME}SCN{scn}.json")
    with open(p, encoding="utf-8") as f:
        return {e["entry_id"]: e.get("text", "") for e in json.load(f)["entries"]}


def by_scene():
    stats = _reinserted()
    tot = ok = 0
    skipped = [0]
    print(f"  {'씬':10} {'총':>6} {'정본':>7} {'남음':>7}  진행")
    for scn in SCENES:
        blocks, d = scn_blocks(scn, skipped), done(scn)
        n, k = len(blocks), len(blocks & d)
        tot += n
        ok += k
        bar = "█" * int(k / max(n, 1) * 20)
        pct = k / max(n, 1) * 100
        print(f"  {GAME}SCN{scn:<5} {n:>6} {k:>7} {n - k:>7}  {bar:<20} {pct:5.1f}%")
    print(f"  {'계':10} {tot:>6} {ok:>7} {tot - ok:>7}  {ok / max(tot, 1) * 100:5.1f}%")
    # ⚠ 뺀 수를 같이 찍는다 — 분모를 좁혔다는 걸 감추면 그것대로 거짓말이 된다.
    print(f"  (표·제어 블록 {skipped[0]}개는 분모에서 뺐다 — 화면에 나가는 대사가 아니다)")
    # 남은 것이 전부 짧은 고유명사면 그건 **플레이트**라 `script/` 몫이 아니다 —
    # 그걸 안 적으면 「아직 21블록이 남았다」로 읽힌다.
    plates = [
        t for scn in SCENES for i, t in _texts(scn).items() if i in (scn_blocks(scn) - done(scn))
    ]
    if plates and all(len(t) <= 8 and "{" not in t for t in plates):
        print(
            f"  ⇒ 남은 {len(plates)}은 **전부 이름·지명 플레이트**다(`patch_sys_ui` 관할). 대사는 0."
        )
    if stats:
        print(f"\n  지난 빌드 재삽입 {sum(stats.values())}블록")
    return tot - ok


def by_map():
    """맵(코드 함수)별 남은 블록 — 어디를 다음에 잡을지 고르는 축.

    ⚠ 맵 귀속은 `scn_callgraph`(코드가 실제로 부르는 블록)가 정본이다. 예전엔 `scn_maps`
    (지명 헤더 위치)로 추정했는데 그건 배정 제약용이라 같이 걷어냈다.
    """
    import scn_callgraph as G

    for scn in SCENES:
        name = f"{GAME}SCN{scn}"
        d = done(scn)
        rows = []
        for f, eids in G.functions(name).items():
            left = [e for e in eids if e not in d]
            if left:
                rows.append((len(left), f, left))
        rows.sort(reverse=True)
        print(f"  {name}: 남은 맵 {len(rows)}")
        for n, f, left in rows[:8]:
            print(f"      fn@{f:#x}  {n:>4}블록 남음  jp{left[0]}~jp{left[-1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", action="store_true")
    a = ap.parse_args()
    if a.maps:
        by_map()
    else:
        by_scene()


if __name__ == "__main__":
    main()
