#!/usr/bin/env python3
"""**매매 문구 일원화를 걷는다** — 폐기된 규칙(유저 확정 2026-08-17)이 박아 둔 좌표를 되돌린다.

## 왜 도구인가

`past_sys_phrases` 가 상점·현자의 시스템 문구 369블록을 **한 표**(`T_011` 루디아 도구점 ·
`T_040` 네리아 현자)로 몰아 놨다. 유저가 그 규칙을 폐기했는데 **데이터는 그대로였다** —
문서는 「통일하지 않는다」인데 배정은 통일하고 있었다. 이 도구가 그 369건의 출처다.

## 통일이 지운 것 (실측)

- **화자 개성** — JP 부터 갈라 놨다(`どれを買うね？` 사투리 · `なんだ 持てねえじゃん。` 반말 ·
  `あら？…みたいよ。` 여성). 정발도 갈라 놨다(`어느 걸 팔려나?` · `뭘 사시려나요?`).
- **정발이 있는데 자체번역** — 현자 프롬프트 넷이 전부 그랬다.
- **형제 블록이 갈림** — 일부에만 걸려 같은 가게가 마을마다 다른 말을 했다.

## 어느 표를 쓰나

`adopt_jeongbal.own_table()` — 배정이 있으면 그것, 없으면 **바로 앞 화자 헤더 블록**의 배정.
가게 대사는 `{c}道具屋{c}` 인사 바로 뒤에 붙으므로 이게 가장 국소적이다(실측 369 중 244).
⚠ 시점을 넓게 추정하지 말 것 — `ed1-scene-map.md` 의 시점 열은 54%만 맞는다.

  python3 tools/past_undo_sys_phrases.py --dry    # 무엇이 어디로 가는지만
  python3 tools/past_undo_sys_phrases.py          # 적용
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import adopt_jeongbal as A
from common import ROOT

SYS = re.compile(r"시스템 문구 일원화 `?([a-z_]+)")

# 정발 표 안에서 역할을 찾는 자리 — 구조가 정해져 있다(`jeongbal-matching` 스킬).
FULL = re.compile(
    r"이상은?|더 가지실|못 가지|너무 많|못 드실|가지실 수 없|가질 수 없|못 들|더 들|들수도 없"
)
BUYP = re.compile(
    r"사시|사가시|사려|사겠|살 것|뭐가 필요|무엇이 필요|파시려나요|파시겠습니까|팔려나"
)
SELLP = re.compile(r"파시|팔려|팔겠|파실|파시렵|팔려나|파시겟|팔 것")
THANKS = re.compile(r"감사|고맙")
DECL = re.compile(r"유감|그렇습니까|아쉽|관두|그만두|섭섭|어쩔 수 없")
WHO = re.compile(r"누구의|누가|누구에게|어느 분|어떤 분")
WHERE = re.compile(r"어디에|어느 ?곳에|어디에다|어디어")
WHICH = re.compile(r"(주문|마법)[이을가는] .*(싶|필요|가르쳐|원하|있습니까|계신가)|도움이 될만한")
DONE = re.compile(r"볼까|썼|써졌|써 넣도록|쓰도록 하지|기록해|끝났")

# ⚠ 정발이 **구매 프롬프트를 「팔다」로 옮긴** 표 — 그 표 전체에 「사다」가 아예 없다(실측).
# 우리 슬라이스 오류가 아니라 정발의 슬립이라 어절 하나만 바로잡는다.
MISTRANS = {
    "ED1/T_032": [["파시겠습니까", "사시겠습니까"]],
    "ED1/T_042": [["파시겠습니까", "사시겠습니까"]],
    "ED1/T_330": [["파시려나요", "사시려나요"]],
    "ED1/T_331": [["파시려나요", "사시려나요"]],
    "ED1/T_332": [["파시려나요", "사시려나요"]],
    "ED1/T_333": [["파시려나요", "사시려나요"]],
}
# 정발 원문이 제어 바이트로 오염된 자리 — 손대지 않는다
SKIP = {("ED1/T_400", "sell")}


def entries(t):
    return [e for e in range(90) if A.dos_text(t, e)]


def pages(t, e):
    d = collections.defaultdict(list)
    for pi, si, x in A.slices(t, e):
        d[pi].append((si, x))
    return d


def shop_map(tbl):
    """{역할: chain 좌표} — 그 표의 상점 스크립트에서 뽑는다."""
    out, buy_e = {}, None
    for e in entries(tbl):
        pg = pages(tbl, e)
        p0 = pg.get(0) or []
        if len(pg) < 2 or not p0 or not any(FULL.search(x) for _s, x in p0):
            continue
        nxt = pg.get(1) or []
        if not nxt or not BUYP.search(nxt[0][1]):
            continue
        buy_e = e
        out["full"] = f"{e}#0.{p0[0][0]}" + (f"-{p0[-1][0]}" if len(p0) > 1 else "")
        out["buy"] = f"{e}#1.{nxt[0][0]}"
        th = [s for s, x in nxt if THANKS.search(x)]
        if th:
            out["thanks"] = f"{e}#1.{th[-1]}"
        for pi in sorted(pg):  # 같은 엔트리 뒷 페이지에 판매·거절이 이어지는 표가 있다
            if pi < 2:
                continue
            for si, x in pg[pi]:
                if SELLP.search(x) and "sell" not in out:
                    out["sell"] = f"{e}#{pi}.{si}"
                if DECL.search(x) and "decline" not in out:
                    out["decline"] = f"{e}#{pi}.{si}"
        break
    for e in entries(tbl):
        if e == buy_e:
            continue
        pg = pages(tbl, e)
        p0 = pg.get(0) or []
        if p0 and SELLP.search(p0[0][1]) and "sell" not in out:
            out["sell"] = f"{e}#0.{p0[0][0]}"
            for pi in sorted(pg):
                for si, x in pg[pi]:
                    if DECL.search(x) and "decline" not in out:
                        out["decline"] = f"{e}#{pi}.{si}"
                    if THANKS.search(x) and "thanks" not in out:
                        out["thanks"] = f"{e}#{pi}.{si}"
    if "decline" not in out or "thanks" not in out:  # 정산 엔트리가 따로인 표
        for e in entries(tbl):
            pg = pages(tbl, e)
            flat = [(pi, si, x) for pi in sorted(pg) for si, x in pg[pi]]
            if not any(DECL.search(x) for _p, _s, x in flat):
                continue
            if not any(
                re.search(r"되겠습니까|되시겠습니까|만족하십니까|괜찮겠", x) for _p, _s, x in flat
            ):
                continue
            for pi, si, x in flat:
                if DECL.search(x) and "decline" not in out:
                    out["decline"] = f"{e}#{pi}.{si}"
                if THANKS.search(x) and "thanks" not in out:
                    out["thanks"] = f"{e}#{pi}.{si}"
            break
    return out


def mag_map(tbl):
    """현자 프롬프트 넷 — 한 엔트리에 `\\x07` 로 이어 붙어 있고 **순서가 곧 역할**이다."""
    for e in entries(tbl):
        sl = A.slices(tbl, e)
        wi = next((i for i, (_p, _s, x) in enumerate(sl) if WHO.search(x)), None)
        if wi is None:
            continue
        out = {"mag_who": f"{e}#{sl[wi][0]}.{sl[wi][1]}"}
        for i in range(wi + 1, min(wi + 3, len(sl))):
            if WHERE.search(sl[i][2]) and "mag_where" not in out:
                out["mag_where"] = f"{e}#{sl[i][0]}.{sl[i][1]}"
            elif "mag_where" in out and DONE.search(sl[i][2]) and "mag_done" not in out:
                out["mag_done"] = f"{e}#{sl[i][0]}.{sl[i][1]}"
        for i in range(wi - 1, max(wi - 3, -1), -1):
            if WHICH.search(sl[i][2]):
                out["mag_which"] = f"{e}#{sl[i][0]}.{sl[i][1]}"
                break
        return out
    return {}


def frag_glue(tbl, chain):
    """정발이 「응? 그 」+「이상은…」 처럼 **엔트리 둘로 갈라 둔** 문장이면 앞 조각을 잇는다.

    ⚠ 앞 조각은 **페이지 통째**(`#0.0-`)로 받는다 — `#0.0` 이면 `_sentences` 가 `응?` 에서
    끊어 `그 ` 를 버린다(실측 17건, 화면에 `응? 이상은 …` 이 나갔다).
    """
    base = int(chain.split("#")[0])
    if not chain.endswith(("#0.0", "#0.0-1", "#0.0-2")):
        return [chain]
    first = A.slices(tbl, base)
    if not first or not re.match(r"이?이상", first[0][2]):
        return [chain]
    for prev in (base - 1, base - 2):
        t = A.dos_text(tbl, prev)
        if t and len(t) <= 12 and not t.rstrip().endswith((".", "?", "!", "{end}")):
            return [f"{prev}#0.0-", "+" + chain]
    return [chain]


def mag_fix(tbl, chain):
    """현자 엔트리는 `\\x0A` 로 「써 볼까」와 「다 썼다」가 붙어 있다 — 페이지로 가른다."""
    base = int(chain.split("#")[0])
    raw = A.dos_text(tbl, base) or ""
    if "\\x0A" not in raw:
        return chain, None
    lead = raw.split("\\x0A")[0][-2:]
    pre = []
    if not lead.endswith((".", "?", "!")):
        pre.append([lead + "\\x0A", lead + ".\\x0A"])
    pre.append(["\\x0A", "{p}"])
    fixed = raw
    for a, b in pre:
        fixed = fixed.replace(a, b)
    import reinsert_kr_pilot as R

    for pi, page in enumerate(fixed.removesuffix("{end}").split("{p}")):
        for si, sent in enumerate(R._sentences(page)):
            c = A.clean(sent)
            if c and re.search(r"볼까|기록해|끝났|써졌", c) and not re.search(r"썼|끝났소", c[-6:]):
                return f"{base}#{pi}.{si}", pre
    return chain, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    ovp = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    maps, stat, rows = {}, collections.Counter(), []
    for scn, d in ov.items():
        if not isinstance(d, dict) or scn.startswith("_"):
            continue
        for eid, e in sorted(d.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            if not isinstance(e, dict):
                continue
            m = SYS.search(e.get("note") or "")
            if not m:
                continue
            grp = m.group(1)
            # ⚠ 일원화 배정은 **믿으면 안 된다** — 안 거르면 자기 잘못을 자기 표로 읽어 순환한다
            tbl, how = A.own_table(scn, int(eid), ignore=lambda n: bool(SYS.search(n)))
            if tbl and tbl not in maps:
                mm = shop_map(tbl)
                mm.update(mag_map(tbl))
                maps[tbl] = mm
            ch = (maps.get(tbl) or {}).get(grp)
            if not tbl or not ch or (tbl, grp) in SKIP:
                stat["자기 표에 대응 없음(그대로 둔다)"] += 1
                e["note"] = f"자기 가게 표에 대응이 없다 — {grp}(일원화 폐기 2026-08-18)"
                continue
            pre = None
            if grp == "mag_done":
                ch, pre = mag_fix(tbl, ch)
            chain = frag_glue(tbl, ch) if grp == "full" else [ch]
            new = {k: v for k, v in e.items() if k == "speaker"}
            new["table"] = tbl
            new["entry_id"] = int(str(chain[0]).lstrip("+").split("#")[0])
            new["chain"] = chain
            if pre:
                new["pre_subs"] = pre
            new["note"] = (
                f"자기 가게·현자의 정발 조각으로 되돌림 — {grp} · 장소·시기 {tbl}({how})"
                " · 일원화 폐기 2026-08-18"
            )
            if grp == "buy" and tbl in MISTRANS:
                new["subs"] = MISTRANS[tbl]
                new["note"] += " · 정발이 구매를 「팔다」로 옮긴 자리라 어절 하나를 바로잡는다"
                stat["  └ 정발 오역 교정"] += 1
            if not a.dry:
                ov[scn][eid] = dict(sorted(new.items()))
            stat["옮김"] += 1
            if len(chain) > 1:
                stat["  └ 조각 이음"] += 1
            rows.append((scn, eid, grp, tbl, chain))
    print("일원화 되돌리기:", dict(stat))
    if a.dry:
        for r in rows[:15]:
            print(f"   {r[0]} jp{r[1]:<5} {r[2]:<10} → {r[3]}#{r[4]}")
        return 0
    json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {ovp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
