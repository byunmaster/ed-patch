"""조판 여섯 규칙 — 영역(씬 대사·나레이션·시스템·전투·무비·음성) 전수 집계 + 게이트.

    python3 games/ss-ed3/tools/check_typeset6.py            # 영역 × 규칙 표
    python3 games/ss-ed3/tools/check_typeset6.py --check    # 받아들인 대장 밖이 나오면 실패
    python3 games/ss-ed3/tools/check_typeset6.py --freeze   # 지금 걸린 것을 대장에 올린다(사유는 손으로)

규칙(관리자 공통 지시 09-27):
  ① 부호 고아·폭 초과  ② 빈 줄 개행  ③ 줄 첫 칸 공백  ④ 묶음 안 끊기(조사가 줄머리 · 『』「」 가 줄을 넘음)
  ⑤ 반각 0.5칸       ⑥ 조사 훅
⑤·⑥ 은 다른 도구가 게이트로 본다 — ⑤ `typeset.char_cols`(폭 모형)·`reinsert_desc`(설명문 반각 거부),
⑥ `patch_josa_hook`·`check_josa.py`. 여기서는 ①~④ 를 **줄 단위로** 센다.

🔴 **걸린 것이 다 결함은 아니다** — ②·③ 의 대부분은 원판 배치(가운데 정렬 여백·값 뒤 조각)다.
그래서 「0 이어야 한다」가 아니라 **대장(`script/typeset6_accept.json`) 밖에서 새로 생기면 실패**한다.
대장에는 사유를 적는다(설계 · 대사 라운드 몫 등).
⚠ 「17칸 꽉 찬 줄 + 개행」은 세지 않는다 — 이 엔진에선 **넘칠 때만** 빈 줄이 생긴다(r5-typeset 캡처 04~06).
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import center_narration as CN
import common as C
import typeset as T

SCRIPT = os.path.join(C.GAME_DIR, "script")
ACCEPT = os.path.join(SCRIPT, "typeset6_accept.json")
JOSA = re.compile(r"^(은|는|이|가|을|를|의|와|과|에게|에서|으로|로|도|만)(?=[\s.,!?…]|$)")
CLOSE = ("》", "』", "」", "〉", ")", "）")


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(text, width=T.WIN_COLS):
    """`[규칙]` — 한 블록에서 걸린 규칙 번호(줄마다 하나씩)."""
    hits = []
    for pg in text.replace("\r", "\n").split("\f"):
        vis = [T.visible(x) for x in pg.split("\n")]
        core = vis[:]
        while core and core[-1] == "":
            core.pop()
        hits += ["②"] * sum(1 for x in core if x == "")
        for i, x in enumerate(vis):
            if not x:
                continue
            if T.orphans(x, width) or T.cols(x) > width:
                hits.append("①")
            if x.startswith(" "):
                hits.append("③")
            #   ⚠ 줄머리 조사만 보면 지시어 「이 배」·「이 마을」 이 264 건 걸린다(첫 판 실측).
            #     묶음은 **닫는 괄호 바로 뒤**에서만 끊긴다 — 「《제목》⏎을 읽을까?」 꼴.
            #     여러 줄에 걸친 인용(『예언… ⏎ …』)은 원판도 그렇게 쓰는 배치라 세지 않는다.
            if i > 0 and vis[i - 1].rstrip().endswith(CLOSE) and JOSA.match(x):
                hits.append("④")
    return hits


def blocks():
    """`[(영역, 열쇠, 문안, 폭)]`."""
    out = []
    narr = {(n, str(i)) for n, i, _ in CN.targets()}
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        n = os.path.basename(f)
        for k, v in _json(f).items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            if (n, k) in narr:
                out.append(("씬 나레이션", f"{n[:-5]}[{k}]", v, 26))
            else:
                out.append(("씬 대사", f"{n[:-5]}[{k}]", v, T.WIN_COLS))
    sysd = _json(os.path.join(SCRIPT, "system.json"))
    for sec in ("message", "notice", "menu", "setting", "stat", "minigame", "blackjack"):
        for jp, v in sysd.get(sec, {}).items():
            if isinstance(v, str):
                w = 26 if sec == "notice" else T.WIN_COLS
                out.append(("시스템", f"{sec}:{jp}", v, w))
    for jp, v in sysd.get("battle", {}).items():
        out.append(("전투", f"battle:{jp}", v, T.WIN_COLS))
    mv = _json(os.path.join(SCRIPT, "movie.json"))
    for k, v in mv.items():
        if k.startswith("M") and isinstance(v, list):
            for j, x in enumerate(v):
                out.append(("무비 자막", f"{k}#{j}", x[-1], 26))
    vc = _json(os.path.join(SCRIPT, "voice.json"))
    for k, v in vc.items():
        if k.startswith("_"):
            continue
        for j, h in enumerate(v.get("hooks", []) + v.get("items", [])):
            if h.get("lines"):
                out.append(("음성 자막", f"{k}#{j}", "\n".join(h["lines"]), T.WIN_COLS))
    return out


def findings():
    """`{열쇠|규칙: (영역, 문안)}` — 같은 블록의 같은 규칙은 개수를 붙여 가른다."""
    out = {}
    for area, key, text, w in blocks():
        seen = {}
        for r in check(text, w):
            seen[r] = seen.get(r, 0) + 1
            out[f"{key}|{r}{'' if seen[r] == 1 else seen[r]}"] = (area, text)
    return out


def load_accept():
    if not os.path.exists(ACCEPT):
        return {}
    with open(ACCEPT, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    got = findings()
    table = {}
    for k, (area, _) in got.items():
        rule = k.split("|")[1][0]
        table.setdefault(area, {}).setdefault(rule, 0)
        table[area][rule] += 1
    print("  영역          ①    ②    ③    ④")
    for area in ("씬 대사", "씬 나레이션", "시스템", "전투", "무비 자막", "음성 자막"):
        t = table.get(area, {})
        print(f"  {area:<10} " + " ".join(f"{t.get(r, 0):>4}" for r in "①②③④"))
    ok = load_accept()
    if a.freeze:
        doc = (
            {"_doc": _json(ACCEPT)["_doc"]}
            if os.path.exists(ACCEPT)
            else {
                "_doc": [
                    "`check_typeset6.py` 가 읽는다 — 여섯 규칙(①~④)에 걸렸지만 받아들인 자리. 키는 `블록|규칙`.",
                    "사유 없이 늘리지 않는다 — 늘릴 때마다 「화면에서 이게 결함인가」를 묻는다.",
                ]
            }
        )
        for k in sorted(got):
            doc[k] = ok.get(k, "⚠ 사유 미기입")
        with open(ACCEPT, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"  대장에 {len(got)} 건을 적었다 — 사유 미기입은 손으로 채운다")
        return 0
    new = sorted(k for k in got if k not in ok)
    gone = sorted(k for k in ok if k not in got)
    for k in new[:30]:
        print(f"  🔴 새로 걸림 {k}  {got[k][1][:40]!r}")
    if gone:
        print(f"  ⓘ 대장에 있는데 이제 안 걸리는 것 {len(gone)} — 고쳐졌으면 대장에서 뺀다")
    if new:
        print(f"  🔴 조판 여섯 규칙 — 대장 밖 {len(new)} 건")
        return 1 if a.check else 0
    print(f"  ✅ 조판 여섯 규칙 — 걸린 {len(got)} 건 전부 대장 안(설계·이월)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
