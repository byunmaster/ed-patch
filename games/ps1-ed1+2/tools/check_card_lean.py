#!/usr/bin/env python3
"""**장 끝 카드가 화면에서 왼쪽으로 기우는가** — 규칙 2-8(마스터 11-09 「최대한 가운데」: 가능한 위치 중 가장 가까운 쪽, 같을 때만 왼쪽).

`check_card_centering` 은 **칸(열)** 로 센다 — 글자 잉크의 좌우 여백(L−R)은 못 본다. 「끝」 줄은 칸이 대칭(pad = right)인데
화면에선 L−R **+3**(왼쪽이 더 큼)이었다. 잉크는 렌더 없이 정적으로 못 재므로 **실측 장부**로 묶는다:

  card_lean.json = 카드 키 → {sha1: 그 카드가 **나가는 문안**(textmap + 핫픽스 덮어쓰기)의 해시, lr: 줄마다 L−R(px)}
  실측은 scene_shots 의 `text:` 주입(대화창 그리기 경로) — 측정 하네스는 `.local/work/inbox/…/center-all/harness/`.

검사 — ① 나가는 문안의 해시가 장부와 같다(문안이 바뀌었는데 재촬영을 안 했으면 **실패**) ② 모든 줄 −6 ≤ L−R ≤ +5(공백 한 칸 = L−R 12 이동 → 이 범위가 곧 최근접, 동률은 왼쪽). 문안을 바꾸면 재촬영해 장부를 갱신(`--update lr.json`)한다.

  python3 tools/check_card_lean.py
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "..")
LEDGER = os.path.join(G, "card_lean.json")
FILES = ("items_battle.json", "battle_ed2.json")


def shipped():
    """카드 키 → 나가는 문안(textmap 위에 핫픽스 덮어쓰기)."""
    out = {}
    for f in FILES:
        base = {e["k"]: e.get("ours") for e in json.load(open(os.path.join(G, "textmap", f), encoding="utf-8"))["entries"]}
        hp = os.path.join(G, "hotfix", "textmap", f)
        hot = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {}
        for k, v in hot.items():
            if k in base:
                base[k] = v
        out.update(base)
    return out


def digest(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--update":
        meas = json.load(open(sys.argv[2]))  # {키: [L−R,…]}
        sh = shipped()
        json.dump({k: {"sha1": digest(sh[k]), "lr": v} for k, v in meas.items()}, open(LEDGER, "w"), indent=1, ensure_ascii=False)
        print(f"장부 {len(meas)}장 갱신")
        return 0
    led = json.load(open(LEDGER))
    sh = shipped()
    bad = []
    for k, v in led.items():
        if k not in sh:
            bad.append((k, "textmap 에 없음"))
        elif digest(sh[k]) != v["sha1"]:
            bad.append((k, "문안이 바뀌었는데 재촬영·장부 갱신이 없다"))
        for d in v["lr"]:
            # 최대한 가운데(마스터 11-09): 공백 한 칸 = L−R 12 — 가능한 위치 중 |L−R| 이 가장 작은 쪽, 같을 때만 왼쪽(−6 은 되고 +6 은 안 된다)
            if not -6 <= d <= 5:
                bad.append((k, f"더 가운데에 가까운 위치가 있다 (L−R {d:+d}, 허용 −6..+5)"))
    print(f"  {'✅' if not bad else '❌'} 장 끝 카드 최대한 가운데(최근접, 동률 왼쪽) 실측 장부 {len(led)}장 중 어긋남 {len(bad)}")
    for k, why in bad:
        print(f"      {k}: {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
