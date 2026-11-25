#!/usr/bin/env python3
"""말투 경보 둘(마스터 11-13 밤샘 ③) — 게이트: 기준선(register_alerts_baseline.json)보다 늘면 실패, `--freeze` 로 내린다.

 ① 반말 문장에 듣는 이 「-시-」가 섞임 — 반말(…야·…어·…군·…지·…다)로 끝나는 문장 안에 `시` 활용(…하시는·…가시고·…시지; 부사 「다시」 제외)이 든 줄.
    번역 규칙 4-16 「반말엔 듣는 이 -시- 없음」. 3인칭 높임(「왕께서 가시는」 등)은 정당해서 **경보**다(걸러 보는 몫은 사람) — 그래서 기준선 래칫.
 ② 핫픽스 줄임 — 핫픽스 덮개 문안이 제품 script 문안보다 글자 수가 40%↓ 로 줄어든 항목(줄인 꼴 금지, 규칙 2-17).
    핫픽스는 문안을 늘리거나 같은 길이로 바꾸는 게 정상이라, 급감은 칸에 맞추려 줄인 흔적이다.

  python3 tools/check_register_alerts.py [--freeze|--selftest|-v]
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import rulings_corpus as RC

BASE = os.path.join(C.ROOT, "register_alerts_baseline.json")

# 문장 끝이 반말인가 — 존대(요·니다·습니까·세요·소서·오)로 안 끝나고 반말 어미로 끝남
SENT = re.compile(r"[^.!?…\n]+[.!?…]+|[^.!?…\n]+$")
PLAIN_END = re.compile(r"(?:[다어아야지군네나냐까데]|[는은ㄴ]가|걸|게|거든|잖아|구나|니)[.!?…]*$")
POLITE = re.compile(r"(?:요|니다|니까|십시오|세요|소서|옵니다|오|죠|지요)[.!?…]*$")
# 용언에 붙은 높임 -시- (하시·가시·오시·계시 · …으시)
HON2 = re.compile(r"(?<![마랍모역혹다])시(?:겠|는|던|네|지|려|면|고|며|니|어|거|죠|[ㄴㄹ])")


THIRD = re.compile(r"님|께서|께는|께|아가씨|주인|대통령|선조|분이|분은")


def plain_with_si(t):
    """반말 문장인데 -시- 가 든 문장 목록."""
    bad = []
    for s in SENT.findall(t.replace("\n", " ").replace("{n}", " ")):
        s = s.strip()
        if not s or POLITE.search(s) or not PLAIN_END.search(s):
            continue
        if THIRD.search(s):
            continue  # 3인칭 높임(…님·…께서)은 정당 — 듣는 이 높임만 잡는다
        if HON2.search(s):
            bad.append(s)
    return bad


def shrunk():
    out = []
    import glob

    for f in sorted(glob.glob(os.path.join(RC.HOTFIX, "ED*SCN*.json"))):
        scene = os.path.basename(f)[:-5]
        hot = json.load(open(f, encoding="utf-8"))
        prod = json.load(open(os.path.join(RC.SCRIPT, scene + ".json"), encoding="utf-8"))
        for eid, h in hot.items():
            if not isinstance(h, dict) or "t" not in h:
                continue
            p = prod.get(eid)
            if not isinstance(p, dict) or not isinstance(p.get("t"), str):
                continue
            a = len(re.sub(r"\s|\{n\}", "", p["t"]))
            b = len(re.sub(r"\s|\{n\}", "", h["t"]))
            if a >= 10 and b < a * 0.6:
                out.append(f"{scene}#{eid}")
    return out


def run():
    si = [f"{k}" for k, _, t in RC.corpus() if plain_with_si(t)]
    return sorted(set(si)), shrunk()


def selftest():
    assert plain_with_si("그럼 이리로 가시지.")
    assert not plain_with_si("지금 왕께서 가시는 길이야.")
    assert not plain_with_si("지금 왕께서 가시는 길입니다.")
    assert not plain_with_si("시작은 이제부터야.")
    assert not plain_with_si("다시는 그러지 않을 거야.")  # 부사 「다시」 — 높임 -시- 아님
    print("양성·음성 대조 ✅")


def main():
    if "--selftest" in sys.argv:
        return selftest()
    selftest()
    si, sh = run()
    cur = {"plain_si": len(si), "shrunk": len(sh)}
    if "-v" in sys.argv:
        print("① 반말+시:", *si, sep="\n  ")
        print("② 줄임:", *sh, sep="\n  ")
    if "--freeze" in sys.argv:
        json.dump({**cur, "plain_si_ids": si, "shrunk_ids": sh}, open(BASE, "w"), ensure_ascii=False, indent=1)
        print("기준선 갱신", cur)
        return
    base = json.load(open(BASE, encoding="utf-8")) if os.path.exists(BASE) else {"plain_si": 0, "shrunk": 0}
    new_si = [x for x in si if x not in base.get("plain_si_ids", [])]
    new_sh = [x for x in sh if x not in base.get("shrunk_ids", [])]
    print(f"말투 경보 [ps1-ed1+2] — 반말+시 {cur['plain_si']}(기준선 {base['plain_si']}) · 핫픽스 줄임 {cur['shrunk']}(기준선 {base['shrunk']})")
    for x in new_si:
        print("  ❌ 새 반말+시:", x)
    for x in new_sh:
        print("  ❌ 새 핫픽스 줄임:", x)
    sys.exit(1 if (new_si or new_sh) else 0)


if __name__ == "__main__":
    main()
