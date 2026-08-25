"""고유명사 표기 후보를 정발 코퍼스로 판정한다 — **표기만** 가져온다.

    python3 games/ss-ed3/tools/glossary_probe.py            # 요약
    python3 games/ss-ed3/tools/glossary_probe.py --md       # 검토표(work/review, 커밋 금지)

방침(루트 「기본 방침」): **문안은 자체 번역, 고유명사·용어 표기는 정발을 유지**한다.
그래서 정발에서 가져오는 건 **단어 하나하나의 표기**뿐이고, 그건 저작권 대상이 아니다.

어떻게 정하나 — **코퍼스가 판정한다**:

  1. JP 고유명사를 **구조에서** 뽑는다(추측이 아니라 표에서) —
     지명 = `MAP*.BIN` 맵 이름 · 인명 = `/0.BIN` 인명 표 · 몬스터 = `SYSTEM/PARAM.BIN` 레코드
  2. `kana_kr.candidates()` 로 음차 **후보**를 여럿 만든다(`ジュ` = 주/쥬, `ク` = 쿠/크 …)
  3. 정발 DOS ED3(`ED3_DT*.DAT`, 평문 EUC-KR)에서 **각 후보의 빈도를 센다**
  4. 최다 빈도를 채택하고, **차점과의 격차**를 같이 낸다 — 애매하면 사람이 본다

⚠ **한자가 섞인 이름은 음차로 안 된다**(`大ネズミ` = 큰쥐). 그건 번역이라 사람 판단으로 뺀다.
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import param as P
from kana_kr import candidates

KR_DIR = os.path.join(C.ROOT, "originals", "kr", "dos-ed3")
KATA = re.compile(r"^[ァ-ヴー・＝=]+$")
# 한자가 붙은 이름은 **가타카나 몸통만** 판정한다 — `ラグピック村` 의 `村`(마을)은
# 음차가 아니라 번역이고, 몸통 표기는 그대로 쓰인다.
BODY = re.compile(r"^([ァ-ヴー・＝=]{2,})(.*)$")
# `PARAM.BIN` 의 표 경계는 `param.py` 가 정본이다 — 여기서 다시 세지 않는다.
# ⚠ 예전엔 아이템을 「파일 끝까지」로 뒀는데, 그 뒤가 **설명문 영역**이라 표에 없는 것이
#   섞여 들어온다(실측: 적을 끝까지 밀었더니 이름 아닌 144 개가 나왔다).


_KR_RUN = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe])+")


CACHE = "kr_corpus.json"


def corpus(rebuild=False):
    """정발 원본 → **한글 낱말 빈도표**. 조회만 한다(문안을 옮기지 않는다).

    소재가 둘이다 — `ED3_DT*.DAT`(대사)와 **`CD/*.ISO`**. 🔴 **몬스터 이름은 CD 에만 있다**:
    DAT 에서는 「스켈」·「샌드」가 0 회인데 ISO 에 `0x75DEFB` 부터 **10바이트 간격**으로
    라디커스·헬게이터·바베트맨·다크나이트·리치·가스트본·데빌임프·이블아이… 가 늘어서 있다
    (전투 배치 표로 보인다). ISO 를 안 보면 몬스터 표기를 영영 못 찾는다.

    ⚠ ISO 가 493MB 라 훑는 데 시간이 든다 — 낱말 빈도를 `work/derived` 에 캐시한다.
      캐시는 **파생물**이고 판정 근거는 정본(`glossary_auto/manual.json`)에 박힌다.

    🔴 **바이트로 세면 안 된다.** 짧은 후보가 흔한 한국어 낱말에 묻혀 이긴다 —
    `グース` 가 「그」(3,847회)로 판정됐다. 낱말 단위로 세고 **접두 일치**만 인정하면
    조사(`구스는`·`구스가`)를 살리면서 그 사고가 사라진다.
    """
    cache = os.path.join(C.OUT_DIR, CACHE)
    if not rebuild and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    paths = sorted(glob.glob(os.path.join(KR_DIR, "ED3_DT*.DAT")))
    paths += sorted(glob.glob(os.path.join(KR_DIR, "CD", "*.ISO")))
    cnt = {}
    for p in paths:
        with open(p, "rb") as f:
            while chunk := f.read(1 << 24):
                for r in _KR_RUN.findall(chunk):
                    w = r.decode("euc_kr", "replace")
                    if len(w) <= 24:
                        cnt[w] = cnt.get(w, 0) + 1
    os.makedirs(C.OUT_DIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(cnt, f, ensure_ascii=False)
    return cnt


# 고유명사 뒤에 붙는 것들 — 이것만 인정한다
JOSA = (
    "",
    "는",
    "은",
    "이",
    "가",
    "를",
    "을",
    "와",
    "과",
    "에",
    "의",
    "도",
    "만",
    "라",
    "란",
    "야",
    "아",
    "씨",
    "님",
    "다",
    "여",
    "랑",
    "에게",
    "에겐",
    "에서",
    "한테",
    "보다",
    "까지",
    "부터",
    "이다",
    "이라",
    "이란",
    "인",
    "였",
    "이었",
)


def score(cand, corp):
    """그 표기가 **이름으로** 쓰인 횟수 — 낱말이 `표기 + 조사` 꼴일 때만 센다.

    🔴 **접두 일치만 보면 활용형에 오염된다.** `シャーラ` 후보 「사라」가 37회로 잡혔는데
    전부 *사라지다*(사라졌다·사라져·사라진…)였고, 진짜 표기인 「샤라」(56회, 전부
    샤라와·샤라를·샤라는)에 이길 뻔했다. 조사로 거르면 「사라」는 0 이 된다.
    """
    # ⚠ **사전을 훑지 않는다** — 조사 꼴을 만들어 **직접 조회**한다. 코퍼스가 31만 낱말이라
    #   순회하면 판정 하나에 수백 ms 가 든다(실측: 전체 판정이 2분을 넘겼다).
    return sum(corp.get(cand + j, 0) for j in JOSA)


def jp_names():
    """`{범주: [JP 이름]}` — 구조에서 뽑는다."""
    out = {"place": [], "person": [], "monster": [], "item": []}
    for p in sorted(glob.glob(os.path.join(C.OUT_DIR, "map_jp", "*.json"))):
        with open(p, encoding="utf-8") as f:
            nm = json.load(f)["map_name"]
        if nm and nm not in out["place"]:
            out["place"].append(nm)

    zero = os.path.join(C.OUT_DIR, "sys_jp", "0.json")
    with open(zero, encoding="utf-8") as f:
        rows = json.load(f)["strings"]
    for s in rows:  # 0x76c60 표가 제어 바이트 없이 깨끗하다
        if 0x76C60 <= s["off"] < 0x76D20 and s["text"] not in out["person"]:
            out["person"].append(s["text"])

    # ⚠ **레코드를 건너뛰되 멈추지 않는다** — 표 중간에 이름이 빈 칸이 있다(적 94 중 20).
    #   `names()` 가 빈 칸과 경계 표식(`reserve`·`Sentinel`)을 함께 걸러 준다.
    b = P.load()
    for key, tbl in (("monster", P.ENEMY), ("item", P.ITEM)):
        for nm in P.names(b, tbl):
            if nm not in out[key]:
                out[key].append(nm)
    return out


def judge(name, corp):
    """`(채택, 빈도, 차점, 후보수, 사유)` — 못 정하면 채택이 `None`.

    한자가 붙으면 **가타카나 몸통만** 판정하고 꼬리는 사유에 남긴다.
    """
    tail = ""
    if not KATA.match(name):
        m = BODY.match(name)
        if not m:
            return None, 0, 0, 0, "가타카나 몸통이 없다 — 번역이다", name, ""
        name, tail = m.group(1), m.group(2)
    body = name.replace("・", "").replace("＝", "").replace("=", "")
    # ⚠ **음절 수를 JP 에 맞춰 거른다.** 안 그러면 1~2글자 후보가 흔한 낱말에 얹혀 이긴다
    #   (`ハック` → 「하」 4,995회).
    # ⚠ 자를 너무 좁게 잡아도 안 된다 — **요음·촉음·장음·`ン` 은 음절을 안 만든다.**
    #   그걸 세면 `ジョアンナ`(=죠안나 3음절)가 「4~6음절」로 걸러진다(실측).
    core = sum(1 for ch in body if ch not in "ーッンャュョァィゥェォ")
    lo, hi = max(2, core - 1), core + 2
    cands = [c for c in candidates(body) if lo <= len(c) <= hi]
    if not cands:
        return None, 0, 0, 0, f"길이 {lo}~{hi} 후보가 없다", name, tail
    scored = sorted(((score(c, corp), c) for c in cands), reverse=True)
    if not scored or scored[0][0] == 0:
        return None, 0, 0, len(cands), "정발 코퍼스에 후보가 없다", name, tail
    best, second = scored[0], (scored[1] if len(scored) > 1 else (0, ""))
    why = f"몸통만 채택 — 꼬리 `{tail}` 는 번역이다" if tail else ""
    return best[1], best[0], second[0], len(cands), why, name, tail


MANUAL = "glossary_manual.json"
AUTO = "glossary_auto.json"


def merge():
    """`{범주: {JP: KR}}` — 자동 판정 위에 **수동이 이긴다.**

    자동은 「코퍼스가 최다로 고른 것」이고 수동은 「사람이 근거를 보고 확정한 것」이다.
    실측으로 갈린 자리가 있다 — `ハック`(자동 실패 → 허크) · `シャーラ`(공략집은 사라,
    게임은 샤라) — 그래서 순서를 못 박는다.
    """
    out = {}
    for name in (AUTO, MANUAL):
        p = os.path.join(C.GAME_DIR, name)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for cat, tbl in json.load(f).get("categories", {}).items():
                out.setdefault(cat, {}).update(tbl)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true", help="검토표를 work/review 에 쓴다")
    ap.add_argument("--freeze", action="store_true", help="자동 판정을 후보 정본으로 박는다")
    ap.add_argument("--merged", action="store_true", help="자동 + 수동을 합쳐 보여 준다")
    a = ap.parse_args()

    if a.merged:
        m = merge()
        for cat, tbl in sorted(m.items()):
            print(f"{cat:<9}{len(tbl):>4}개")
        print(f"합계 {sum(len(v) for v in m.values())}")
        return m

    corp = corpus()
    names = jp_names()
    res = {}
    rows = []
    tails = {}
    for cat, items in names.items():
        ok = 0
        for nm in items:
            kr, n, n2, ncand, why, body, tail = judge(nm, corp)
            if kr:
                ok += 1
                # ⚠ **정본에는 몸통만 담는다.** `アンデラ城` → `안데라` 로 넣으면 꼬리가
                #   조용히 사라진다. 꼬리(`城`·`村`·`号`…)는 번역이라 따로 낸다.
                res.setdefault(cat, {})[body] = kr
                if tail:
                    tails.setdefault(tail, []).append(nm)
            rows.append((cat, nm, kr or "", n, n2, ncand, why))
        print(f"{cat:<8} {ok:>4}/{len(items):<4} 자동 판정")
    if tails:
        print("\n꼬리(번역 대상) — 사람이 정한다:")
        for tl, who in sorted(tails.items(), key=lambda x: -len(x[1]))[:10]:
            print(f"  {tl:<10}×{len(who):<3} 예: {who[0]}")

    if a.md:
        os.makedirs(C.REVIEW_DIR, exist_ok=True)
        out = os.path.join(C.REVIEW_DIR, "glossary_ed3.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write("# ED3 고유명사 표기 — 정발 코퍼스 판정\n\n")
            f.write("⚠ 원문 포함 — 커밋 금지. 빈도는 **정발에서 그 표기가 쓰인 횟수**다.\n\n")
            f.write(
                "| 범주 | JP | 채택 | 빈도 | 차점 | 후보 | 비고 |\n|---|---|---|--:|--:|--:|---|\n"
            )
            for cat, nm, kr, n, n2, nc, why in rows:
                f.write(f"| {cat} | {nm} | {kr} | {n} | {n2} | {nc} | {why} |\n")
        print(f"\n검토표 → {out}")
    print(
        f"\n자동 판정 합계 {sum(len(v) for v in res.values()):,} / {sum(len(v) for v in names.values()):,}"
    )

    if a.freeze:
        out = os.path.join(C.GAME_DIR, "glossary_auto.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "_doc": [
                        "ED3 고유명사 표기 — **정발 코퍼스가 판정한 자동분**. 근거는 그 표기가",
                        "정발에서 쓰인 횟수다(`glossary_probe.py`). ⚠ 아직 후보다 —",
                        "유저가 훑은 뒤 `shared/glossary/` 로 올린다(자리가 main 이라 확인을 받는다).",
                        "⚠ 단어 표기만 담는다. 문안은 여기 오지 않는다(루트 「저작권」).",
                    ],
                    "categories": {k: dict(sorted(v.items())) for k, v in sorted(res.items())},
                    "freq": {nm: n for _, nm, kr, n, *_ in rows if kr},
                    "tails": {k: sorted(v) for k, v in sorted(tails.items())},
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"후보 정본 → {out}")
    return res


if __name__ == "__main__":
    main()
