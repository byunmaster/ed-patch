"""말투 경보 둘(밤샘 11-13) — ① 반말 줄 안의 「-시-」 섞임 ② 원문 대비 길이 급감.

경보는 **기준선(register_alarm_baseline.json) 밖의 새 줄**만 실패로 친다(래칫). 기준선은 사람이 훑어 정당한 것(제3자 높임·짧은 외침 등)만 `--freeze` 로 올린다.
`--selftest` = 양성 대조(가짜 문장에서 경보가 울어야 한다).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import names_corpus as n

BASE = common.GAME_DIR / "register_alarm_baseline.json"
SP = re.compile(r"(<1e>([^<]*)<04>|<09([0-9a-f]{2})>(?=<01>| ))")
POL = re.compile(
    r"(습니다|ㅂ니다|입니다|니다|[ㅂ십입겁랍됩갑옵]니까|십시[오요]|세요|어요|아요|해요|예요|에요|죠|지요|군요|네요|나요|가요|래요|데요|걸요|까요|시다|시오|하오|이오|구려|소이다|으오|그려|[았었겠있없같렇]소|세나|십쇼|쇼|요)$"
)
HAGE = re.compile(r"(게나|일세|하게|구먼|는가|ㄴ가|인가|[가오하보세]세|[가주하보먹오맡]게)$")
HON = re.compile(r"(으?시(?:어|지|네|나|군|려나|는가)?|셨(?:어|지|네|군|나|다)?)$")


def segs(s):
    ms = list(SP.finditer(s))
    return [
        (m.group(2) if m.group(2) is not None else "#" + m.group(3), s[m.end() : (ms[i + 1].start() if i + 1 < len(ms) else len(s))])
        for i, m in enumerate(ms)
    ]


def sents(t):
    t = re.sub(r"<[^>]*>", "", t).replace("\x0c", " ")
    return [p.strip(" ,~)(「」』『\"'") for p in re.split(r"[.!?…]+", t) if len(p.strip(" ,~)(「」』『\"'")) >= 2]


def plain_with_hon(s):
    """반말(해체·하게 아님 — 존대 꼴이 아닌 줄)인데 마지막 어절이 -시-/-셨- 로 끝난다."""
    if POL.search(s) or HAGE.search(s):
        return False
    w = s.split()[-1] if s.split() else ""
    return w not in ("역시", "혹시") and bool(HON.search(w))


def hangul(t):
    return len(re.findall(r"[가-힣]", re.sub(r"<[^>]*>", "", t)))


def jplen(t):
    return len(re.sub(r"<[^>]*>|[\x0c\s　、。…・･ー―!?！？「」『』]", "", t))


def alarms():
    out = {}
    for pl, jp, kr, _ in n.pairs():
        if not pl.startswith("script:") or not kr:
            continue
        a, b = segs(jp), segs(kr)
        if len(a) != len(b):
            continue
        for (_, tj), (_, tk) in zip(a, b):
            for s in sents(tk):
                if plain_with_hon(s):
                    out[f"시|{pl}|{s}"] = s
            if jplen(tj) >= 14 and hangul(tk) < 0.35 * jplen(tj):
                out[f"짧|{pl}|{tk[:30]}"] = tk[:40]
    return out


def selftest():
    assert plain_with_hon("어서 가셨어"), "경보① 양성 대조 실패"
    assert not plain_with_hon("어서 가셨어요"), "경보① 음성 대조 실패"
    assert jplen("これはとても長い文章ですよね") >= 14 and hangul("네") < 0.35 * 14
    print("  ✅ 말투 경보 양성·음성 대조 통과")


def main():
    selftest()
    cur = alarms()
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps(sorted(cur), ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"기준선 {len(cur)}건 기록")
        return 0
    base = set(json.loads(BASE.read_text(encoding="utf-8"))) if BASE.exists() else set()
    new = [k for k in cur if k not in base]
    print(f"  말투 경보 {len(cur)}건 · 기준선 {len(base)} · 새 줄 {len(new)}")
    for k in new[:30]:
        print("   ❌", k)
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
