#!/usr/bin/env python3
"""**시스템 문구 일원화** — 상점 매매·현자 전수처럼 흐름이 정해진 문구를 한 벌로 맞춘다.

**왜(유저 제안 2026-08-06).** "미세하게 몇 글자 다른 것보다 이런 시스템적인 문구는
일원화하는 게 낫지 않나." 맞다 — JP 원판이 같은 프롬프트를 마을 방언·경어로 흩어 놨을 뿐
**의미가 하나**다(사기 7가지·팔기 6가지·꽉참 8가지 변형). 정발도 그걸 따라가느라 갈렸고,
그 탓에 `어느 것을 파시겟습니까?`(사기 블록인데 팔기 동사 + 오타)가 6건 살아 있었다.

## ⚠ 이 작업은 한 번 크게 실패했다 — 무엇이 달랐나

2026-08-05 에 같은 걸 하다 **바뀐 233블록 중 92건(39%)이 남의 대사**로 나가 전면 철회했다.
원인은 **발상이 아니라 식별**이었다 — `인사` 판정을 렌더된 한국어 낱말 하나(`어서 오`)로 해서
곶의 동굴 경고까지 끌려왔다. 이번엔 셋을 바꾼다:

1. **판정을 JP 원본 구조로 한다** — 창 1개(`%c`=1) · `%s`/`%d` 없음 · 낱말 표지 ·
   **문맥(군집)** · **길이 상한**. `stock_kind`·`is_shop_price` 와 같은 관용이다.

   ⚠ **문맥과 길이는 서로를 대체하지 못한다**(유저 지적 2026-08-06 "텍스트만으로 찾지 말고
   도구점 대사로 필터 걸면 되지 않아?" → 실측). 각자 **다른 실패**를 잡는다:
   - **길이**가 잡는 것 — 상점 *옆에 선* 마을 사람. `しかも、お金を貯めて…売ってくれない`(43자)은
     이웃이 상점이라 문맥을 통과한다. 길이만이 막는다.
   - **군집**이 잡는 것 — 낱말만 우연히 겹친 고립 NPC.
   그리고 **고립된 진짜 상점**도 있다(`これ以上 持てないようですぜ。` — 가격 프롬프트가 없는
   작은 상점). 그래서 **군집 안이면 상한까지, 고립이면 `TIGHT` 까지**로 가른다. 매직넘버가
   고립 블록에만 걸려 근거가 생긴다(오늘 기준 결과는 동일 — 순수 강건성 개선).
2. **증거는 JP 쪽에서 낸다** — 잡아낸 **서로 다른 JP 본문을 전부 찍는다.** 그게 한 문장의
   방언·경어 변형뿐이면 식별이 옳고, 남의 대사가 섞이면 눈에 바로 띈다(그룹당 10줄 남짓이라
   실제로 볼 수 있다). ⚠ **"현행 KR 이 표준안과 얼마나 닮았나"는 안전 축이 아니다** —
   처음엔 그걸로 걸렀는데, 걸린 65건이 전부 *바꿔야 할* 것들이었다: 같은 문구의 다른 변형
   (`어느 걸 사시려나요?` 0.44)이거나 **지금 문안이 틀린 자리**(`무엇을 찾으십니까?` 0.33 — JP 는
   `売ってくれますか`인데 첫인사가 나가고 있었다, 24블록). 그래서 KR 분포는 **보고만** 한다.
3. **표준안 문안을 코드에 안 적는다** — 정발 포인터(`sys_phrases.json`)로 두고 빌드 때 파생.
   JP 표지는 낱말 수준이라 코드에 둔다(`SHOP_PRICE` 의 `になるけど` 선례).

  python3 tools/sys_phrases.py             # 후보·현행 문안 분포(동질성 포함)
  python3 tools/sys_phrases.py --apply     # align_overrides.json 에 표준안 기록
"""

import difflib
import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
import segment_copy as S  # noqa: E402
from align_map import scene_map  # noqa: E402
from check_window_nl import raws_of  # noqa: E402
from common import ROOT  # noqa: E402

SPEC = os.path.join(ROOT, "sys_phrases.json")
# 이만큼도 안 닮은 현행 문안은 **눈으로 한 번 보라고** 표시만 한다(자동으로 빼지 않는다 —
# 위 2번 참조: 걸리는 건 대개 "지금이 틀린 자리"라 오히려 통일이 고친다).
ODD = 0.30
# 군집 = 이 칸수 안에 **다른 시스템 문구 블록**이 또 있다. 상점·현자는 프롬프트가 붙어 있고
# (사기·팔기·꽉참·감사) 지나가는 NPC 는 혼자다. ±6·±8·±12 다 같은 결과라 가운데를 쓴다.
NEAR = 8
# 고립 블록에만 걸리는 길이 상한. 실측 — 고립된 진짜 상점 문구 최장 17자,
# 고립된 남의 대사 최단 32자. 사이를 잡는다.
TIGHT = 20


def spec():
    """`_` 로 시작하는 키는 파일 머리의 설명이다 — 규칙이 아니라 주석."""
    d = json.load(open(SPEC, encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _norm(s):
    return re.sub(r"[\s.,!?~…·]+", "", s or "")


def jp_body(raw):
    """블록이 **단창 프롬프트**면 그 JP 본문, 아니면 None.

    ⚠ 구조 조건(`%c`=1 · `%s`/`%d` 없음)이 판정의 절반이다. 낱말 표지만으로는 남의 대사가
    걸린다 — 그게 2026-08-05 사고의 기전이었다."""
    t = raw.rstrip(b"\x00")
    if t.count(R.MC) != 1 or b"%s" in t or b"%d" in t:
        return None
    return t.replace(R.MC, b"").decode("cp932", "ignore").replace("\n", "")


def marked(body, sp):
    """표지만 본 1차 후보 — 길이·문맥은 아직 안 본다."""
    if body is None:
        return None
    for key, d in sp.items():
        if not any(m in body for m in d["marks"]):
            continue
        if any(m in body for m in d.get("not_marks", [])):
            continue
        return key
    return None


def matches(raws, sp):
    """{eid: key} — 표지 + 구조 + **문맥(군집)** + 길이까지 통과한 블록.

    ⚠ 문맥과 길이 중 하나만 쓰면 샌다(도크스트링 1번 참조). 군집 안이면 그룹의 `maxlen`
    까지, 고립이면 `TIGHT` 까지만 받는다."""
    cand = {}
    for eid, raw in raws.items():
        b = jp_body(raw)
        k = marked(b, sp)
        if k:
            cand[eid] = (k, b)
    out = {}
    for eid, (k, b) in cand.items():
        near = any(o != eid and abs(o - eid) <= NEAR for o in cand)
        if len(b) <= (sp[k]["maxlen"] if near else min(TIGHT, sp[k]["maxlen"])):
            out[eid] = k
    return out


def canon(d):
    """표준안 KR — 정발 엔트리에서 파생한다(문안을 커밋 파일에 안 남기기 위함).

    ⚠ `chain_text` 는 `load_translations` 안의 중첩 함수라 밖에서 못 부른다 —
    슬라이스 의미론은 `segment_copy.slice_text` 가 그대로 흉내 낸다."""
    src = d["src"]
    raw = S.entries(src["table"]).get(src["entry_id"], ("", "", ""))[2]
    # `pre_subs` 는 **슬라이스 전**에 걸린다 — 정발이 페이지를 `\x0A` 로 나눠 둔 자리를
    # `{p}` 로 바꿔야 문장 분리기가 본다(T_040#0 `볼까\x0A자, 다 썼네.` 실측 2026-08-06).
    for a, b in src.get("pre_subs", ()):
        raw = raw.replace(a, b)
    txt = S.slice_text(raw, src["slice"]) if src.get("slice") else raw
    # `chain_extra` = **같은 테이블의 다른 엔트리 조각**을 이어 붙인다. 빌드 쪽은 `chain` 의
    # `+` 접두가 하니 여기서도 같은 결과를 내야 미리보기가 맞는다.
    for it in src.get("chain_extra", ()):
        item = str(it).lstrip("+")
        ent = int(item.partition("#")[0])
        txt += S.slice_text(S.entries(src["table"]).get(ent, ("", "", ""))[2], item)
    for a, b in src.get("subs", ()):
        txt = txt.replace(a, b)
    txt = re.sub(r"\\x[0-9A-Fa-f]{2}|\{end\}|\{p\}|\{spk\}.*?\{/spk\}", "", txt)
    return re.sub(r"\s+", " ", txt.replace("{n}", " ")).strip()


def scan(game="ED1"):
    """{key: [(씬, eid, JP 본문, 현행 KR, 표준안과의 유사도)]}"""
    sp = spec()
    out = {k: [] for k in sp}
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        raws = raws_of(name)
        for eid, key in matches(raws, sp).items():
            jb = jp_body(raws[eid])
            t = tr.get(eid)
            try:
                cur = " ".join(x[1] for x in t[1]) if t else ""
            except (TypeError, IndexError):
                cur = ""
            sim = (
                difflib.SequenceMatcher(None, _norm(cur), _norm(canon(sp[key]))).ratio()
                if cur
                else -1.0  # 미번역 — 지금 일본어가 나가는 자리라 비교 대상이 없다
            )
            out[key].append((name, eid, jb, cur, sim))
    return out


def main():
    sp, found = spec(), scan()
    plans, odd = [], 0
    for key, rows in found.items():
        std = canon(sp[key])
        new = [r for r in rows if r[4] < 0]
        print(f"\n=== {key}  {len(rows)}블록(미번역 {len(new)}) → 표준안: {std}")
        # ① 식별 증거 — 잡아낸 JP 가 한 문장의 변형뿐인지 **눈으로** 본다
        jps = {}
        for _, _, jb, _, _ in rows:
            jps[jb] = jps.get(jb, 0) + 1
        print(f"    JP {len(jps)}변형:")
        for jb, n in sorted(jps.items(), key=lambda x: -x[1]):
            print(f"      {n:3}x  {jb}")
        # ② 현행 KR 분포 — 보고만 한다(자동 제외 아님)
        krs = {}
        for _, _, _, cur, _ in rows:
            if cur and cur != std:
                krs[cur] = krs.get(cur, 0) + 1
        if krs:
            print("    현행 KR:")
            for cur, n in sorted(krs.items(), key=lambda x: -x[1])[:8]:
                print(f"      {n:3}x  {cur[:74]}")
        for nm, e, _, cur, sim in rows:
            if 0 <= sim < ODD:
                print(f"      ⚠ 확인 {nm} jp{e} ({sim:.2f})  {cur[:62]}")
                odd += 1
        plans += [(key, nm, e) for nm, e, _, _, _ in rows]
    print(f"\n통일 대상 {len(plans)}블록 · 눈으로 볼 것 {odd}건")

    if "--apply" in sys.argv and plans:
        path = os.path.join(ROOT, "align_overrides.json")
        ov = json.load(open(path, encoding="utf-8"))
        n = 0
        skipped_ours = []
        for key, nm, e in plans:
            d = sp[key]
            sc = ov.setdefault(nm, {})
            cur = dict(sc.get(str(e)) or scene_map(nm).get(e) or {})
            if "유저 확정 유지" in (cur.get("note") or ""):
                continue
            # ⚠ `ours`(손으로 쓴 문안)는 `chain` 보다 **우선**한다 — 안 걷으면 좌표만 바뀌고
            # 화면은 그대로다(decline 8블록 실측 2026-08-06, 통일했는데 안 바뀌어 있었다).
            # 표준안과 닮았을 때만 걷는다. 다른 문장이면 우리가 일부러 쓴 것이니 **건드리지
            # 않고 건너뛴다** — `ours` 는 커밋 파일에 문안을 남기므로 포인터가 낫지만,
            # 그건 "같은 말일 때"만 참이다.
            if "ours" in cur:
                sim = difflib.SequenceMatcher(None, _norm(cur["ours"]), _norm(canon(d))).ratio()
                if sim < 0.6:
                    skipped_ours.append((nm, e, sim, cur["ours"]))
                    continue
                cur.pop("ours")
            cur["table"] = d["src"]["table"]
            cur["entry_id"] = d["src"]["entry_id"]
            if d["src"].get("slice"):
                # `chain_extra` = 같은 테이블의 다른 조각을 `+` 로 이어 붙인다(2026-08-06).
                # 판매 후 프롬프트 복귀처럼 **정발 두 조각을 한 창에** 넣을 때 쓴다 —
                # 문안을 새로 쓰지 않고 포인터만 늘리는 방법이다.
                cur["chain"] = [d["src"]["slice"], *d["src"].get("chain_extra", ())]
            else:
                cur.pop("chain", None)
            if d["src"].get("subs"):
                cur["subs"] = [list(x) for x in d["src"]["subs"]]
            if d["src"].get("pre_subs"):
                cur["pre_subs"] = [list(x) for x in d["src"]["pre_subs"]]
            else:
                cur.pop("pre_subs", None)
            cur["note"] = f"시스템 문구 일원화 `{key}`(sys_phrases 2026-08-06)"
            sc[str(e)] = cur
            n += 1
        json.dump(ov, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → align_overrides.json 반영 {n}건")
        if skipped_ours:
            print(f"  ⛔ `ours` 가 표준안과 달라 건너뜀 {len(skipped_ours)}건:")
            for nm, e, sim, o in skipped_ours:
                print(f"      {nm} jp{e} ({sim:.2f})  {o[:56]}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
