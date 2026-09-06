#!/usr/bin/env python3
"""**인물별 말투가 인물표와 맞는가** — 대장(`docs/ed<N>-story-bible.md`)을 기계로 대조한다.

**왜(2026-09-06).** 유저가 ED2 첫 장면에서 「왕자가 교육계 노인에게 **야**」를 잡았다.
그건 낱말 오역이었지만(`やあ`=인사 감탄사), **ED2 가 말투 검수를 한 번도 안 받았다**는
신호였다 — ED1 은 454자리를 훑었다. 그런데 있는 도구 어느 것도 이 축을 안 본다:

    speaker_profile      재료 추출(검사기가 아니다)
    check_speech_level   **한 창 안** 혼용 · 원문 경어 → 우리 해라체
    ⇒ 「이 인물이 이 말투를 쓰나」는 아무도 안 본다

## 무엇을 하나

인물표가 인물마다 **한국어 등급 지침**을 적어 뒀다(플로라=품위 있는 합쇼체 · 란도=거친
반말 · 챨리=거만한 합쇼체 …). 그 지침을 `EXPECT` 로 옮기고, 그 인물의 대사 종결이
허용 등급 밖이면 **검토 후보**로 낸다.

🔴 **게이트가 아니다.** 등급은 상대·상황에 따라 정당하게 오르내린다(아트라스는 동료엔
반말·어른엔 합쇼체). 여기 뜨는 건 「틀렸다」가 아니라 「사람이 볼 자리」다.

## 라벨 함정을 피한다 — 인물표 0절의 실측 그대로

    이름창 없는 블록이 라벨을 앞 창에서 **상속**한다   4,634 중 1,436(31.0%)
    한 블록에 이름창이 둘                              7건 — `s` 는 첫 화자만
    이름창이 `%s`                                      499블록 — 상점이면 물건 이름이다
    `s` 가 아예 없다                                   7,055 중 2,421

⇒ **자기 이름창(`%c이름%c\\n`)을 가진 블록만** 센다. 상속·`%s` 블록은 라벨이 화자를
가리킨다는 보장이 없다.

⚠ **익명 역할군은 대상이 아니다**(병사·상점·마을 사람 — ED2 의 63.7%). 같은 라벨이
마을마다 **다른 사람**이라 통일하면 마을 색이 사라진다(ED1 실측: 163블록이 이 오탐이었다).

  python3 tools/check_speaker_register.py            # 요약
  python3 tools/check_speaker_register.py -v         # 블록 목록
  python3 tools/check_speaker_register.py --grades   # 인물별 등급 분포(대장을 고칠 때)
"""

import io
import json
import os
import pathlib
import re
import sys
from contextlib import redirect_stdout

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "script"
NAMEPLATE = re.compile(r"^%c([^%\n]{1,20})%c\n")
CLEAN = re.compile(r"[\x00-\x1f%a-zA-Z0-9\"'~()\[\]\s]+")

# 등급 — **거친 것부터 정중한 것 순**. 한 문장이 여럿에 걸리면 먼저 맞는 것으로 센다.
GRADE = [
    (
        "합쇼체",
        re.compile(
            r"(습니다|습니까|십니다|십니까|입니다|ㅂ니다|드립니다|십시오|사옵|옵니다|나이다|옵소서)$"
        ),
    ),
    (
        "해요체",
        re.compile(
            r"(세요|셔요|예요|이에요|어요|아요|여요|지요|나요|까요|군요|네요|는데요|고요|죠)$"
        ),
    ),
    ("하게체", re.compile(r"(하게|이네|일세|시게|게나|는가|던가|누먼|구먼|나\?|ㄹ세)$")),
    ("하소체", re.compile(r"(구나|란다|느냐|더냐|거라|려무나|로다|노라|니라|시오)$")),
    ("해라체", re.compile(r"(는다|았다|었다|였다|한다|이다|있다|없다|같다|겠다|더군|는군|로군)$")),
    ("반말", re.compile(r"(거야|잖아|는데|야|어|아|지|래|자|냐|니|까|걸|텐데|든지)$")),
]

# 🔴 인물표(`docs/ed2-story-bible.md`)의 「한국어 지침」을 옮긴 것이다 — **정본은 그 문서**고
#    여기는 기계가 읽는 사본이다. 지침이 바뀌면 양쪽을 같이 고친다.
# ⚠ 등급이 **여럿 허용**인 인물이 있다(상대에 따라 오르내린다) — 그건 결함이 아니다.
EXPECT = {
    # 일행 — 상대가 갈리니 등급도 갈린다
    "아트라스": ({"합쇼체", "해요체", "해라체", "반말"}, "동료엔 반말 · 어른/왕족엔 합쇼체"),
    "란도": ({"해라체", "반말", "합쇼체"}, "거친 반말. 왕 앞에서도 어휘는 반말, 종결만 합쇼체"),
    "플로라": ({"합쇼체", "해요체"}, "품위 있는 합쇼체 + 여성어"),
    "레이시아": ({"해요체", "반말", "해라체"}, "여성 반말/해요체"),
    "신디": ({"반말", "해라체"}, "짧은 반말. 자기를 이름으로 부른다"),
    # 어른 — 등급이 고정에 가깝다
    "교육계 라우엘": ({"합쇼체", "하게체"}, "합쇼체로 훈계"),
    "라우엘": ({"합쇼체", "하게체"}, "〃"),
    "디나 왕비": ({"하게체", "하소체", "합쇼체"}, "어머니의 하게체(존댓말 금지)"),
    "페리시아 황태후": ({"하게체", "하소체", "합쇼체"}, "할머니의 하게체"),
    "제랄드 부인": ({"합쇼체", "해요체"}, "합쇼체"),
    "챨리": ({"합쇼체"}, "거만한 합쇼체"),
    "제니": ({"합쇼체", "해요체"}, "ですわ 합쇼체"),
    "리더": ({"하게체", "하소체", "해라체"}, "노인 하게체"),
    "모건": ({"하소체", "해라체", "하게체"}, "노인 해라체"),
    "하베이": ({"하소체", "해라체", "하게체"}, "노인 해라체"),
    "에리사": ({"하게체", "해요체", "반말"}, "하게체 여성"),
    "나레사 대장": ({"해라체", "하소체"}, "해라체 — 적으로 만나도 막말은 아니다"),
    # 반말 인물
    "보자": ({"반말", "해라체"}, "반말"),
    "사미": ({"반말", "해라체"}, "젊은 반말"),
    "로우": ({"반말", "해라체"}, "반말(ED1 그대로)"),
    "보아드": ({"반말", "해라체"}, "친구의 아들이라 아트라스에게도 반말"),
    "드레이크": ({"반말", "해라체"}, "겁먹은 반말"),
    # 적
    "황제 고드윈 2세": ({"해라체", "하소체"}, "오만한 해라체"),
    "가드": ({"해라체", "반말"}, "해라체 막말"),
}


def grade(sentence):
    s = CLEAN.sub("", sentence).strip()
    if len(s) < 2:
        return None
    for name, pat in GRADE:
        if pat.search(s):
            return name
    return None


def scan(track="ED2"):
    """[(씬, eid, 화자, 등급, 문장)] — 자기 이름창을 가진 블록만."""
    out = []
    for p in sorted(SCRIPT.glob(f"{track}SCN*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        with redirect_stdout(io.StringIO()):
            rows = [(e, c) for _s, e, _j, c, _t in R.iter_candidates((p.stem,))]
        for eid, cand in rows:
            out_txt = R.render_bytes(cand.rstrip(b"\x00"), ctrl=True)
            m = NAMEPLATE.match(out_txt)
            if not m or "%s" in m.group(1):
                continue  # 상속·런타임 이름창 — 라벨을 못 믿는다
            who = m.group(1).strip()
            v = doc.get(str(eid))
            if not isinstance(v, dict):
                continue
            body = re.sub(r"%[csd]", "", out_txt[m.end() :]).replace("\n", " ")
            # 🔴 **종결 부호가 실제로 붙은 문장만 센다**(스킬 ④ 「블록은 문장이 아니다」).
            #    창은 문장 중간에서 끊기므로 조각을 종결로 세면 오탐이 쏟아진다 —
            #    실측: 안 거르면 `아닙니다, 나무라다니` 같은 **잘린 조각**이 후보에 낀다.
            for mm in re.finditer(r"([^.!?…]+)[.!?…]", body):
                g = grade(mm.group(1))
                if g:
                    out.append((p.stem, eid, who, g, mm.group(1).strip()[:34]))
    return out


def main():
    import collections

    rows = scan()
    if "--grades" in sys.argv:
        per = collections.defaultdict(collections.Counter)
        for _s, _e, who, g, _t in rows:
            per[who][g] += 1
        for who, c in sorted(per.items(), key=lambda x: -sum(x[1].values())):
            if sum(c.values()) < 8:
                continue
            print(f"   {sum(c.values()):>4}  {who:<14} {dict(c.most_common())}")
        return 0
    bad = [r for r in rows if r[2] in EXPECT and r[3] not in EXPECT[r[2]][0]]
    per = collections.Counter((r[2], r[3]) for r in bad)
    print(f"  ℹ 인물표와 어긋난 대사 {len(bad)}곳 (대장 등재 인물 {len(EXPECT)}종 기준)")
    for (who, g), n in per.most_common(12):
        print(f"       {n:>3}  {who} — {g} (지침: {EXPECT[who][1]})")
    if "-v" in sys.argv:
        for s, e, who, g, t in bad[:40]:
            print(f"          {s}:{e} [{who}/{g}] {t!r}")
    print("     ⚠ 게이트가 아니다 — 등급은 상대·상황에 따라 정당하게 오르내린다. 사람이 본다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
