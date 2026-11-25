"""문안 경보 둘 — 화면 몫이 아니라 문안만 보는 정적 검사 (관리자 11-13 밤샘 3).

① **반말 줄에 듣는 이 높임 「-시-」가 섞임** — 문장 끝이 반말(~해·~다·~네·~지)인데 같은 문장 안에 「-(으)시-」 활용
   (「오시게」 「가시지」 같은 하게·존대 혼합이 아니라 평어 종결 앞의 「-시-」)이 낀 것. 듣는 이를 높이면서 끝을 낮추는 꼴이 의심된다.
   하게체(~게·~세·~네) 종결의 「-시-」는 노인 말투라 허용하지 않고 **보고만** 한다(경보는 같다 — 기준선으로 래칫).
② **원문 대비 길이 급감** — 원문(가나) 12자 이상인데 우리 글자 수가 원문의 40% 미만이면 의심(누락 가능성).
둘 다 **기준선 래칫**: 지금 있는 것은 목록(games/sfc-ed1/register_alarm_baseline.json)에 두고, 새로 늘면 실패.
줄면 `--freeze`. 양성 대조(`selftest`)가 먼저 돌아 검출기가 살아 있음을 보인다.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import typeset  # noqa: E402

BASE = HERE.parent / "register_alarm_baseline.json"
PAGE = re.compile(r"<PAGE>|<CLEAR>|<RETURN>|<END>")
WIN = re.compile(r"<FF>|<EF>|<E0>|<E4>|<FE>")
HEAD = re.compile(r"^<E3>.*?<E1>|^\{D[0-9A-F]:[0-9A-F]+\}\n?", re.S)
JHEAD = re.compile(r"^(?:<COLOR_C>)?\{?[^\n<>{}]{1,10}\}?\n?<COLOR_POP>")


def plain(t):
    t = re.sub(r"<[^>]*>", "", t)
    return re.sub(r"\{[^}]*\}", "X", t).replace("\n", " ")


# 반말 종결 앞에 「-시-」: 「가시는군」 「오시나」처럼 높임 어간 + 평어 어미. 존대 종결(~요·~니다·~십시오)은 제외.
HON_PLAIN = re.compile(r"[가-힣]시(?:는군|는구나|네|나|는가|려나|는지|어|지|렴|ㄴ다|는데)(?=[ ?!.…~～]|$)")
POLITE_END = re.compile(r"(습니까|습니다|니까|세요|에요|예요|어요|아요|해요|지요|군요|네요|까요|옵니다|옵소서|시오|십시오|입죠|습죠)$")
HON_OK = re.compile(r"시(?:오|옵|요|죠|지요|겠습|ㅂ니다|ㅂ쇼|십시오|옵소서)")


def alarm_honorific(kr):
    """반말 줄에서 듣는 이 높임 어간이 낀 문장."""
    out = []
    for s in re.split(r"[.!?…]+", plain(kr)):
        s = s.strip(" 「」~～")
        if not s or HON_OK.search(s) or POLITE_END.search(s) or re.search(r"마시|들이마시|드시|주무시", s):
            continue
        m = HON_PLAIN.search(s)
        if m:
            out.append(s)
    return out


def alarm_short(jp, kr):
    jp = JHEAD.sub("", jp)
    j = re.sub(r"[\s　、。！？…「」『』ー〜～・]", "", re.sub(r"\{[^}]*\}", "", re.sub(r"<[^>]*>", "", jp)))
    k = re.sub(r"[\s.,!?…「」『』~～]", "", plain(kr).replace("X", "가"))
    return len(j) >= 12 and len(k) < 0.35 * len(j), len(j), len(k)


def selftest():
    assert alarm_honorific("어서 가시지.<E0>"), "양성 대조 실패(-시- 반말)"
    assert not alarm_honorific("어서 가십시오.<E0>"), "음성 대조 실패(존대)"
    jp = chr(0x3042) * 14  # 가나 14자(원문 흉내)
    assert alarm_short(jp, "응")[0], "양성 대조 실패(길이 급감)"
    assert not alarm_short(jp, "가" * 14)[0], "음성 대조 실패(길이 정상)"


def scan():
    hon, short = set(), set()
    for it in typeset.targets():
        jw = [w for w in PAGE.split(it["jp"]) if w.strip()]
        kw = [w for w in WIN.split(it["kr"]) if w.strip()]
        for wi, k in enumerate(kw):
            kb = HEAD.sub("", k)
            for s in alarm_honorific(kb):
                hon.add(f"{it['id'][:12]}.{wi}:{s[:30]}")
        if len(jw) == len(kw):
            for wi, (j, k) in enumerate(zip(jw, kw)):
                bad, nj, nk = alarm_short(j, HEAD.sub("", k))
                if bad:
                    short.add(f"{it['id'][:12]}.{wi}:{nj}>{nk}")
    return sorted(hon), sorted(short)


def main():
    selftest()
    hon, short = scan()
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps({"honorific_plain": hon, "short": short}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  문안 경보 기준선 갱신 — 반말 줄 -시- {len(hon)} · 길이 급감 {len(short)}")
        return 0
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.exists() else {"honorific_plain": [], "short": []}
    new_h = [x for x in hon if x not in set(base["honorific_plain"])]
    new_s = [x for x in short if x not in set(base["short"])]
    print(f"  문안 경보 — 반말 줄 -시- {len(hon)}(기준선 {len(base['honorific_plain'])}) · 길이 급감 {len(short)}(기준선 {len(base['short'])}) · 양성 대조 통과")
    for x in new_h + new_s:
        print("    🔴 새 경보:", x)
    return 1 if (new_h or new_s) else 0


if __name__ == "__main__":
    sys.exit(main())
