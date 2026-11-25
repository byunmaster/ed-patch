"""말투 안전망 셋 — 문안 전량(script/MAPnnn.json)을 본다.

    python3 games/ss-ed3/tools/check_tone_guard.py            # 검사(그대 금지만 실패)
    python3 games/ss-ed3/tools/check_tone_guard.py --selftest # 양성 대조(심은 표본이 잡히나)

① **「그대」 금지**(실패) — 2인칭 「그대」는 쓰지 않는다(원문 あなた·そなた → 당신·너·자네 등 상대에 맞춰).
   「그대로」(그대로 두다)는 다른 낱말이라 뺀다.
② **반말 문장에 듣는 이를 높이는 「-시-」가 섞임**(래칫) — 「~하시고 …해」 같은 꼴은 등급이 한 문장에서 갈린 것이다.
   하게체·합쇼·해요체 문장은 보지 않는다. 낱말(마시다·모시다·계시다·혹시)은 거름식에서 뺀다.
   기계는 제3자 높임(「엄마가 읽어 주셨지」)을 못 가려 남는 건 사람이 한 줄씩 본 것이다(11-13: 듣는 이 높임 6곳을 풀고
   남은 것은 전부 제3자) — 그래서 실패가 아니라 **기준선(`tone_guard_baseline.json`)보다 늘면 실패**하는 래칫이다(`--freeze` 로 내림).
③ **원문 대비 길이 급감**(경보) — 원문 글자 수(공백·부호 뺌)가 12 이상인데 번역이 0.35 미만이면 빠뜨린 문장을 의심한다
   (규칙 2-17: 줄여 맞추지 않는다). 짧은 관용구(「ありがとうございました。」→「고마워.」)는 비율이 이보다 높아 안 걸린다.
"""

import glob
import json
import os
import re
import sys

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GUDAE = re.compile(r"그대(?!로)")
_END = re.compile(r"[^.!?…]+[.!?…]+")
# 반말(해체·해라체) 끝 — check_speech 와 같은 잣대(하게체 · 해요 · 합쇼는 뺀다)
_LOW = re.compile(r"(잖아|거야|건데|는걸|야|냐|자|어|아|지|네|군|구나|더라|란다|겠어|이야|이다|한다|같아|말야|해|줘|래)[.!?…]*$")
_HIGH = re.compile(r"(습니다|ㅂ니다|입니다|십시오|세요|셔요|어요|아요|여요|에요|예요|해요|지요|죠|네요|군요|까요|요)[.!?…]*$")
# 듣는 이를 높이는 -시- (낱말 속 「시」는 안 걸리게 어미 꼴만)
_SI = re.compile(r"[가-힣](?:시(?:는|ㄴ|고|며|면|니|려|어|었|겠|지|오|죠)|셨|셔)")
_SIOK = re.compile(r"(?:시간|시작|시장|시체|시계|시험|시선|시민|시대|시절|시내|시도|시력|시골|시야|마시|마셔|마셨|모시|모셔|모셨|혹시|계시|계셔|계셨|쑤시)")


def sentences(text):
    t = text.replace("\f", " ").replace("\n", " ")
    return [s.strip() for s in _END.findall(t)]


def mixed_si(sent):
    s = sent.strip()
    if _HIGH.search(s) or not _LOW.search(s):
        return False
    return bool(_SI.search(_SIOK.sub("", s)))


def cnt(t):
    return len(re.sub(r"[\s\x00-\x1f　・…\.\!\?！？。、，,]", "", t))


def scan():
    gudae, si, shrink = [], [], []
    for f in sorted(glob.glob(os.path.join(G, "script", "MAP*.json"))):
        m = os.path.basename(f)[:-5]
        kr = json.load(open(f, encoding="utf-8"))
        jp = json.load(open(os.path.join(G, "work", "derived", "map_jp", m + ".json"), encoding="utf-8"))["blocks"]
        for k, v in kr.items():
            if k == "_wide" or not isinstance(v, str):
                continue
            i = int(k)
            if GUDAE.search(v):
                gudae.append((m, k, v))
            if any(mixed_si(s) for s in sentences(v)):
                si.append((m, k, v))
            if i < len(jp) and jp[i].get("text"):
                a, b = cnt(jp[i]["text"]), cnt(v)
                if a >= 12 and b / a < 0.35:
                    shrink.append((m, k, f"{b}/{a}", v))
    return gudae, si, shrink


_BASE = os.path.join(G, "tone_guard_baseline.json")


def _baseline():
    try:
        return json.load(open(_BASE))["si"]
    except (OSError, KeyError, ValueError):
        return None


def selftest():
    ok = True

    def need(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print("  ✗ 양성 대조 실패 —", msg)

    need(GUDAE.search("그대가 사랑한 사람"), "그대 를 못 잡는다")
    need(not GUDAE.search("그대로 두자"), "그대로 를 잡는다")
    need(mixed_si("선생님이 오시고 나서 가자."), "반말 + -시- 를 못 잡는다")
    need(not mixed_si("어서 오십시오, 손님이 오시는 날입니다."), "합쇼를 잡는다")
    need(not mixed_si("시간이 없어."), "시간 을 잡는다")
    need(not mixed_si("물이나 마시면 되잖아."), "마시다 를 잡는다")
    need(not mixed_si("혹시 알고 있어?"), "혹시 를 잡는다")
    print("  양성 대조", "통과" if ok else "실패")
    return ok


def main():
    if "--selftest" in sys.argv:
        return 0 if selftest() else 1
    if not selftest():
        return 1
    gudae, si, shrink = scan()
    print(f"  「그대」 {len(gudae)}곳 (0 이어야 한다)")
    for m, k, v in gudae[:10]:
        print(f"    {m}#{k} {v[:40]!r}")
    print(f"  반말 문장 안 「-시-」 섞임 {len(si)}곳 (기준선 {_baseline()}, 늘면 실패 — 남은 건 제3자 높임)")
    for m, k, v in si[:8]:
        print(f"    {m}#{k} {v[:50]!r}")
    print(f"  ⚠ 원문 대비 길이 급감(0.35 미만) 경보 {len(shrink)}곳")
    for m, k, r, v in shrink[:8]:
        print(f"    {m}#{k} {r} {v[:40]!r}")
    base = _baseline()
    msg = ""
    if base is not None and len(si) > base:
        msg = f"기준선보다 늘었다: {base}→{len(si)} — 듣는 이를 높인 반말(4-16 ③)을 풀거나 제3자 높임이면 --freeze"
    if "--freeze" in sys.argv:
        json.dump({"si": len(si)}, open(_BASE, "w"), indent=1)
        print(f"  기준선 → {len(si)}")
        msg = ""
    if msg:
        print("  ❌", msg)
    return 1 if (gudae or msg) else 0


if __name__ == "__main__":
    sys.exit(main())
