#!/usr/bin/env python3
"""상점 매매 **동사가 뒤집힌 블록**을 잡는다 — JP 는 사기인데 KR 이 팔기(또는 반대).

**왜(유저 지적 2026-08-05).** "무기점은 판매가 없다. 파시겠습니까는 나올 수 없다." 맞다 —
전수로 보니 **무기점 19블록이 JP `買ってくれますか`(사기)인데 `(정발 문안)` 로
렌더**되고 있었다. 정발 매매 엔트리는 한 엔트리 안에 사기·팔기를 `\\x06`/`\\x07` 로 담고
파일마다 배치가 달라, 슬라이스 인덱스가 한 칸만 어긋나도 **동사가 뒤집힌다.**

⚠ **화면만 봐서는 어색하지 않다** — "(정발 문안)"도 멀쩡한 한국어라 QA 를
통과한다. JP 와 대조해야만 잡히는 클래스라 검사기로 못 박는다.

JP 표지는 낱말 수준이라 코드에 둔다(`patch_items.SHOP_PRICE` 의 `になるけど` 선례).

  python3 tools/check_shop_verbs.py            # 어긋난 블록 보기
  python3 tools/check_shop_verbs.py --apply    # `subs` 로 동사 교정
"""

import json
import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from align_jp_kr import load_jp_scene  # noqa: E402
from align_map import scene_map  # noqa: E402
from common import ROOT  # noqa: E402

BUY_JP = ("買って", "買う")  # 플레이어가 산다
SELL_JP = ("売って", "売る")  # 플레이어가 판다
# ⚠ 낱말표에 구멍이 있으면 **조용히 통과한다** — `파시렵니까` 가 빠져 있어 7건을 놓쳤고,
# 표기 통일로 `파시겠습니까` 가 되고 나서야 드러났다(2026-08-05). 이형태를 다 적어 둔다.
KR_BUY = ("사시겠습니까", "사시려나요", "사시렵니까", "사가시겠습니까", "사시겠어요", "사실")
KR_SELL = ("파시겠습니까", "파시려나요", "파시렵니까", "파시겠어요", "파실", "파시려")


def scan(game="ED1"):
    """[(씬, eid, 방향, 렌더)] — JP 와 KR 의 매매 동사가 어긋난 블록."""
    out = []
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        jp = {b["id"]: b for b in load_jp_scene(game, scn)}
        for e, t in tr.items():
            body = (jp.get(e, {}).get("body") or "")
            try:
                kr = " ".join(x[1] for x in t[1])
            except (TypeError, IndexError):
                continue
            jp_buy = any(w in body for w in BUY_JP)
            jp_sell = any(w in body for w in SELL_JP)
            if jp_buy == jp_sell:  # 둘 다거나 둘 다 아니면 판정 불가
                continue
            kr_buy = any(w in kr for w in KR_BUY)
            kr_sell = any(w in kr for w in KR_SELL)
            if jp_buy and kr_sell and not kr_buy:
                out.append((name, e, "사기인데 팔기", kr))
            elif jp_sell and kr_buy and not kr_sell:
                out.append((name, e, "팔기인데 사기", kr))
    return out


def main():
    rows = scan()
    print(f"매매 동사가 뒤집힌 블록 {len(rows)}건")
    for name, e, why, kr in rows[:24]:
        print(f"  {name} jp{e}  [{why}]  {kr[:44]}")
    if len(rows) > 24:
        print(f"  … 외 {len(rows) - 24}건")

    if "--apply" in sys.argv and rows:
        path = os.path.join(ROOT, "align_overrides.json")
        ov = json.load(open(path, encoding="utf-8"))
        n = 0
        for name, e, why, _kr in rows:
            src, dst = (KR_SELL, KR_BUY) if why == "사기인데 팔기" else (KR_BUY, KR_SELL)
            pairs = [[a, b] for a, b in zip(src, dst, strict=True)]
            sc = ov.setdefault(name, {})
            cur = dict(sc.get(str(e)) or scene_map(name).get(e) or {})
            if not cur.get("table"):
                continue
            # ⚠ 기존 `subs` 를 덮지 않고 **앞에 붙인다** — 사람이 넣은 치환이 먼저 돈다.
            cur["subs"] = pairs + list(cur.get("subs") or [])
            cur["note"] = f"매매 동사 교정(check_shop_verbs 2026-08-05) — JP 기준 {why}"
            sc[str(e)] = cur
            n += 1
        json.dump(ov, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → align_overrides.json 반영 {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
