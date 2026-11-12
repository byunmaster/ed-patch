#!/usr/bin/env python3
"""번역 규칙 2-10(한 줄 문장) · 2-13(쉼표)의 정적 전수(마스터 11-03) — 화면 몫으로 남겨 두었던 두 규칙을 구운 글로 센다.

    python3 tools/check_screen_rules.py [--show] [--check|--freeze]

2-10  한 줄에 들어가는 문장이 두 줄 이상으로 쪼개진 창 — 구운 조각(`check_baked_layout.baked_pieces`)을 쪽(op 02)마다 이어
      문장으로 자르고, 한 줄 격자(24글리프·24칸, `typeset._fits`)에 통째로 드는데 줄이 갈린 문장을 센다. 변수가 낀 창은 뺀다(런타임에 이어 붙는다).
      · `머리`  머리 인자(`0F 03 …`) 창 — 재조판 대상 밖(인자의 뜻을 모른다)
      · `줄 모자람`  조각 수(구조 계약) 안에서 문장마다 새 줄을 못 여는 창 — 번역 규칙 2-17(문안을 줄이지 않고, 줄·쪽 나뉨은 허용)
2-13  「뺀다」 부류에 걸리는 쉼표 후보 — 규칙 행의 꼴 그대로: 주어·주제 뒤(`…은,` `…는,`) · 부사어 뒤(`…에,` `…에서,` `…대로,`) ·
      짧은 연결 어미 뒤(`…고,` `…며,` `…면서,`) · 구운 줄 끝(다음 줄이 같은 문장을 잇는 줄바꿈).
      🔴 **후보 수이지 결함 수가 아니다** — 규칙의 「남긴다」 부류(부르는 말 · 응답 · 나열 · 말머리 군말 · 긴 앞 절 · 경계 사례 ①~⑨)가 섞여 있어
      명백한 꼴(예시와 똑같은 것)만 고치고 나머지는 기준선(`screen_rules_baseline.json`)에 둔다. 래칫 — 기준선보다 늘면 실패.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_baked_layout as bl
import script as script_canon
import typeset

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screen_rules_baseline.json"
)
HALF = " .,?!()「」『』"
SENT_END = re.compile(r"[.!?…~～][」』)]?$")
COMMA_CLASSES = (
    ("부사어", re.compile(r"^[가-힣A-Za-z0-9]+(에서는|에게는|에는|으로는|로는|에서|에게|으로|부터|까지|에|로|대로)$")),
    ("주제", re.compile(r"^[가-힣]+(은|는)$")),
    ("연결", re.compile(r"^[가-힣]+(고|며|으며|면서)$")),
)
INTERJECTION = {"아이고"}  # 감탄 — 규칙 「남긴다」(`고` 로 끝나지만 연결 어미가 아니다)
KEYS = ("2-10 머리", "2-10 줄 모자람", "2-13 주제", "2-13 부사어", "2-13 연결", "2-13 줄 끝")


def pages(pieces, pre_ops):
    """[[줄…]] — 쪽(op 02)마다 구운 조각들의 줄."""
    out = [[]]
    for p, ops in zip(pieces, pre_ops, strict=True):
        if 2 in ops:
            out.append([])
        out[-1] += p.split("\n")
    return out


def split_fit_sentences(rows, cols=24):
    """[(문장, [걸친 줄…])] — 한 줄 격자에 통째로 드는데 둘 이상의 줄에 걸친 문장(2-10)."""
    sents, buf, idx = [], "", []
    for i, r in enumerate(rows):
        for t in r.split(" "):
            if not t:
                continue
            buf = f"{buf} {t}" if buf else t
            if i not in idx:
                idx.append(i)
            if SENT_END.search(t):
                sents.append((buf, idx))
                buf, idx = "", []
    if buf:
        sents.append((buf, idx))
    return [(s, [rows[i] for i in ix]) for s, ix in sents if len(ix) > 1 and typeset._fits(s, "ed3", cols)]


def comma_candidates(text):
    """[(부류, 낱말)] — 낱말 끝 쉼표가 「뺀다」 꼴인 것(2-13). 쉼표 앞 낱말이 부류 꼴과 같은지만 본다."""
    out = []
    for m in re.finditer(r"(\S+?),(?=\s|$)", text):
        w = m.group(1)
        if w in INTERJECTION:
            continue
        for name, pat in COMMA_CLASSES:
            if pat.match(w):
                out.append((name, w))
                break
    return out


def row_end_commas(rows):
    """[줄] — 쉼표로 끝나고 다음 줄이 같은 쪽에서 문장을 잇는 줄(줄바꿈이 이미 쉼을 준다)."""
    return [r for r, n in zip(rows, rows[1:], strict=False) if r.rstrip().endswith(",") and n.strip()]


def scan(disc="ed3"):
    found = {k: [] for k in KEYS}
    for member, ids, pre, pieces, _src in bl.windows(disc):
        if any(4 <= o <= 7 for ops in pre for o in ops):
            continue
        for rows in pages(pieces, pre):
            for sent, rs in split_fit_sentences(rows):
                found["2-10 머리" if pre[0] else "2-10 줄 모자람"].append((member, ids[0], rs))
            for r in row_end_commas(rows):
                found["2-13 줄 끝"].append((member, ids[0], [r]))
    canon, _ = script_canon.load_effective(disc)
    for (path, nm), lines in sorted(canon.items()):
        key = os.path.basename(path).split(".")[0] + "_" + nm.replace("\\", "/").split("/")[-1].split(".")[0]
        for i, row in sorted(lines.items()):
            for cls, w in comma_candidates(row["kr"]):
                found[f"2-13 {cls}"].append((key, i, [w + ","]))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    try:
        found = scan(a.disc)
    except (OSError, SystemExit, KeyError) as e:
        print(f"한 줄 문장·쉼표 전수 — 안 쟀다(원판 디스크를 못 읽음: {e})")
        return 1
    cnt = {k: len(v) for k, v in found.items()}
    print("한 줄 문장·쉼표 전수 [ed3] — " + " · ".join(f"{k} {n}" for k, n in cnt.items()))
    if a.show:
        for k, v in found.items():
            for member, p, rs in v:
                print(f"  {k} {member}@{p}: {rs}")
    base = None
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    if a.freeze:
        if base and any(cnt[k] > base.get(k, 0) for k in KEYS):
            print("   🔴 기준선보다 늘었다 — 얼리지 않는다")
            return 1
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cnt, f, ensure_ascii=False)
        print("   기준선을 썼다")
        return 0
    if a.check:
        if base is None:
            print("   🔴 기준선이 없다(--freeze)")
            return 1
        worse = [k for k in KEYS if cnt[k] > base.get(k, 0)]
        for k in worse:
            print(f"   🔴 {k}: 기준선 {base.get(k, 0)} → {cnt[k]} (늘었다)")
            for member, p, rs in found[k][-5:]:
                print(f"      {member}@{p}: {rs}")
        better = [k for k in KEYS if cnt[k] < base.get(k, 0)]
        if better and not worse:
            print(f"   ⚠ {', '.join(better)} 가 기준선보다 줄었다 — `--freeze` 로 내린다")
        return 1 if worse else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
