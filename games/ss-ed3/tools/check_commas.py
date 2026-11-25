"""쉼표 「뺀다」 부류 계수·정리 — 번역 규칙 2-13 (마스터 10-14·11-03 ⑩·⑪).

    python3 games/ss-ed3/tools/check_commas.py            # 부류별 수
    python3 games/ss-ed3/tools/check_commas.py --apply    # 명백한 부류를 script/MAP*.json 에서 뺀다
    python3 games/ss-ed3/tools/check_commas.py --check    # 명백한 부류가 남았거나 애매 목록이 늘면 실패 · 양성 대조

2-13 이 **뺀다**고 한 부류 — 주어·주제 뒤(`~은,` `~는,`) · 부사어 뒤(`지금,` `그때,` `~에서,` `~엔,`) · 짧은 연결 어미 뒤(`~하고,` `~서,` `~며,` — ⑪
**앞 절 11음절 이하**만, 12음절 이상은 남긴다) · 문장 앞 접속 `그럼,`(⑩ — 부르는 말 앞·작별은 남김) · 줄 끝.
남기는 부류(부르는 말 · 감탄·응답 · 나열 · 동격 · 짝을 이룬 구 · `아니,` · 앞 절 12음절 이상의 `~는데,` 등)는 **건드리지 않는다**.
🔴 **명백**(규칙 예시와 꼴이 같은 것)만 자동으로 뺀다 — 낱말 꼴(조사·어미)로 가르고, 남기는 부류와 겹칠 수 있는 것(동격 명사구·부르는 말 의심·되풀이)은
`script/comma_pending.json` 의 **애매 목록**에 부류·열쇠로 둔다(기준선 — 늘면 실패).
검사 범위: 씬 대사·해설(`script/MAP*.json`) 전량. 영상·음성 자막·전투·책은 애매 목록으로만 센다(자막은 줄이 소리 단위라 따로 본다).
"""

import argparse
import functools
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script")
PENDING = os.path.join(SCRIPT, "comma_pending.json")
DAEGU = os.path.join(SCRIPT, "comma_daegu.json")  # 규칙 2-13 ⑪ 예외 — 같은 꼴 두 절이 맞서는 대구는 쉼표를 남긴다(마스터 11-05)

#   부사어(시간·장소) — 말머리나 주어 뒤에 오는 단독 낱말 + 쉼표
ADV = {
    "지금",
    "그때",
    "내일",
    "옛날엔",
    "이 마을에선",
    "소문엔",
    "이 앞엔",
    "내 눈엔",
    "그건 그렇고",
    "그렇다고",
    "하물며",
}
ADV_TAIL = re.compile(
    r"(?:지금|그때|내일|옛날엔|마을에선|소문엔|앞엔|눈엔|그건 그렇고|그렇다고|하물며|바로)$"
)
#   줄 끝·조각 끝 낱말 꼴 — 주제(은/는) · 연결어미 · 부사형. 동격 명사구·부름말은 이 꼴이 아니라 애매로 남는다.
LINE_OBV = re.compile(
    r"(?:[은는]|[가-힣]고|며|[아어해]서|[가-힣]서|니까|면서|으면|[가-힣]면|[아어]|하여|든|[가-힣]도록|[가-힣]려고|[가-힣]다가)$"
)
CONN = re.compile(r"(?:[가-힣]{2,}고|마시고|려고|라고|말고|았고|었고|했고|해서|하며|으며|면서)$")
INTERJ = re.compile(
    r"(?:아이고|어이고|이고|그렇고말고|뭐라고)$"
)  # 감탄·되묻기·맞장구는 남기는 부류
CTRL = re.compile(r"<[0-9A-Fa-f]{2}>")
GATED = re.compile(r"(?:고|며|서)$")  # ⑪ — 앞 절 길이로 가르는 연결 어미
SHORT_MAX = 11  # ⑨·⑪: 11음절 이하면 뺀다(읽는 소리대로, 공백·부호 안 셈)
NAMES = r"(?:쥬리오|크리스|알프|모리슨|구스|바다트|죠안나|로디|루레|라프|저기|<01><[0-9A-Fa-f]{2}>)"
VOCATIVE = re.compile(
    rf"^(?:{NAMES}|아가씨|여러분|얘들아|너|선수|임금님|대신관님|[가-힣]+님|군|양|씨)$"
)
FAREWELL = re.compile(
    r"안녕|이만|조심|또 봐|나중에 봐|잘 자|몸조리|잘 부탁|다녀올|실례|편히|신세|잘 지내|작별|바이바이|배웅|가시지요|갈게요"
)
_DIGIT = "영일이삼사오육칠팔구"


def _num_syl(d):
    """숫자 낱말을 읽는 소리의 음절 수 — 만 이하는 자리 읽기(십·백·천), 그 위는 자릿수대로."""
    n = int(d)
    if n == 0 or len(d) > 4:
        return len(d)
    c = 0
    for k, ch in enumerate(reversed(d)):
        v = int(ch)
        if v:
            c += 1 if k and v == 1 else (2 if k else 1)
    return max(c, 1)


def syllables(s):
    """읽는 소리 음절 수 — 한글 한 자 1 · 숫자 읽는 대로 · 영문 한 자 1 · 이름 변수 3 · 공백·부호 0."""
    s = re.sub(r"<01><[0-9A-Fa-f]{2}>", "가나다", s)
    s = re.sub(r"[０-９]", lambda m: str(ord(m.group()) - 0xFF10), s)
    n = 0
    for m in re.finditer(r"[0-9]+|[가-힣]|[A-Za-zＡ-Ｚａ-ｚ]", s):
        g = m.group()
        n += _num_syl(g) if g.isdigit() else 1
    return n


def clause_syl(t, i):
    """`t[i]` 쉼표 앞 절의 음절 수 — 절 머리는 앞 문장 끝 부호·앞 쉼표·쪽 머리, 줄바꿈은 공백으로 읽는다."""
    j = max(t.rfind(c, 0, i) for c in ".!?…,\f")
    return syllables(t[j + 1 : i].replace("\n", " "))


def rest_sentence(t, i):
    """쉼표 뒤 같은 문장(다음 문장 끝 부호까지, 줄바꿈 공백으로)."""
    m = re.search(r"[.!?…]", t[i + 1 :])
    r = t[i + 1 : i + 1 + m.start()] if m else t[i + 1 :]
    return r.replace("\n", " ").replace("\f", " ").strip(" )　")


def _word(pre):
    return re.sub(r"^[\s　]+", "", pre).split(" ")[-1].replace("…", "")


def classify(text):
    """`[(위치, 부류, 명백)]` — 쉼표마다 「뺀다」 부류에 걸리면 (문자열 속 위치, 부류, 자동으로 뺄 만한가). 걸리지 않으면 안 낸다(남기는 부류)."""
    out = []
    t = text
    for m in re.finditer(",", t):
        i = m.start()
        rs = max(t.rfind("\n", 0, i), t.rfind("\f", 0, i)) + 1
        re_ = [x for x in (t.find("\n", i), t.find("\f", i)) if x >= 0]
        re_ = min(re_) if re_ else len(t)
        row = t[rs:re_]
        pre = t[rs:i]
        w = _word(pre)
        wl = re.sub(r"[^가-힣]", "", w)
        multi = row.count(",") >= 2
        two = re.sub(r"^[\s　]+", "", pre)
        nxt = t[i + 1 : i + 2]
        at_end = i + 1 == re_ and t[i + 1 : i + 2] in ("\n", "\f")
        if nxt == ")" and (i + 2 == len(t) or t[i + 2] in "\n\f"):
            continue  # 속말 괄호가 쉼표에서 닫힘 — 다음 창으로 이어진다는 표시(fix_line_commas 와 같은 판정)
        if len(wl) <= 1:
            continue
        if INTERJ.search(wl):
            continue
        if w == "그럼" and re.search(r"(?:^|[.!?…(「\s]|그,)\s*$", pre[: len(pre) - len(w)]):
            rest = rest_sentence(t, i)
            if all(VOCATIVE.match(x) for x in rest.split()) or FAREWELL.search(rest):
                continue  # ⑩ 부르는 말 앞 · 작별은 남김
            out.append((i, "그럼", True))
            continue
        if GATED.search(wl) and not multi and (at_end or CONN.search(wl)):
            rs_ = rest_sentence(t, i)
            if clause_syl(t, i) > SHORT_MAX:
                out.append((i, "연결-긴절", False))
            elif syllables(rs_) <= 3 and re.match(r"[^.!?…]*[!?]", t[i + 1 :].replace("\n", " ")):
                out.append(
                    (i, "연결-도치", False)
                )  # 강조하려 뒤집은 문장(`봤다니까, 내가!!`)은 남김
            else:
                out.append((i, "줄끝" if at_end else "연결", True))
            continue
        if at_end:
            if multi:
                out.append((i, "줄끝-나열의심", False))
            elif LINE_OBV.search(wl) and len(wl) >= 3:
                out.append((i, "줄끝", True))
            else:
                out.append((i, "줄끝-애매", False))
            continue
        if two.endswith(("은", "는")) and re.search(r"[은는]$", wl) and len(wl) >= 3:
            nw = t[i + 1 :].lstrip(" ").split(" ")[0]
            if nw.rstrip(",.!?…") == w:
                continue  # 되풀이(맛있는, 맛있는)
            out.append((i, "주제", True))
        elif ADV_TAIL.search(two):
            out.append((i, "부사어", True))
        elif re.search(r"(?:에서|에선|에도|엔)$", wl) and len(wl) >= 3:
            out.append((i, "부사어-애매", False))
        elif CONN.search(wl) and not multi:
            out.append((i, "연결", True))
        elif CONN.search(wl):
            out.append((i, "연결-나열의심", False))
    return out


def strip(text):
    """`(고친 텍스트, 뺀 수)` — 명백한 부류만."""
    pos = [i for i, _c, ob in classify(text) if ob]
    for i in reversed(pos):
        text = text[:i] + text[i + 1 :]
    return text, len(pos)


@functools.cache
def locked():
    """마스터 판정으로 문안이 잠긴 블록(`master_rulings.json`) — 이 도구는 건드리지 않고 목록으로만 센다."""
    with open(os.path.join(C.GAME_DIR, "master_rulings.json"), encoding="utf-8") as fh:
        keys = set(re.findall(r"MAP\d+#\d+", fh.read()))
    if os.path.exists(DAEGU):  # 대구 보존 블록도 자동으로 안 건드린다(되살린 쉼표를 다시 빼지 않게)
        with open(DAEGU, encoding="utf-8") as fh:
            keys |= set(json.load(fh)["blocks"])
    return keys


def docs():
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        with open(f, encoding="utf-8") as fh:
            yield f, json.load(fh)


def census():
    """`({부류: [열쇠]}, 명백 목록)` — 맵 대사 전량."""
    pend, obv = {}, []
    for f, doc in docs():
        stem = os.path.basename(f)[:-5]
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            for _i, c, ob in classify(v):
                if ob and f"{stem}#{k}" in locked():
                    continue  # 판정 잠금 — 목록(comma-1103.txt)으로만
                (obv.append(f"{stem}#{k}") if ob else pend.setdefault(c, []).append(f"{stem}#{k}"))
    return pend, obv


def controls():
    return [
        ("주제 뒤", [c for _i, c, ob in classify("파렌 왕국은, 번영했다") if ob] == ["주제"]),
        ("부사어 뒤", [c for _i, c, ob in classify("지금, 가겠다") if ob] == ["부사어"]),
        ("연결 어미 뒤", [c for _i, c, ob in classify("방에 들어가고, 앉았다") if ob] == ["연결"]),
        ("줄 끝", [c for _i, c, ob in classify("마을 사람들이 모여서\n얘기를 했다") if ob] == []),
        (
            "줄 끝 쉼표",
            [c for _i, c, ob in classify("그들은 마을로 모여서,\n얘기를 했다") if ob] == ["줄끝"],
        ),
        ("⑩ 그럼 뺌", [c for _i, c, ob in classify("그럼, 하루라도 쉬자") if ob] == ["그럼"]),
        ("⑩ 그럼 — 부름말 앞 남김", classify("그럼, 쥬리오.") == []),
        ("⑩ 그럼 — 작별 남김", classify("그럼, 몸조리 잘하세요.") == []),
        ("⑪ 짧은 앞 절 뺌", [c for _i, c, ob in classify("방이 끝났고, 앉았다") if ob] == ["연결"]),
        (
            "⑪ 긴 앞 절 남김(12음절↑)",
            [(c, ob) for _i, c, ob in classify("처음에는 다이스에 지지 않는 마을로 만들려고, 했다")]
            == [("연결-긴절", False)],
        ),
        (
            "⑪ 강조 도치 남김",
            [(c, ob) for _i, c, ob in classify("그걸 말했고, 내가!!")] == [("연결-도치", False)],
        ),
        ("부름말은 남김", classify("아트라스, 이리 와") == []),
        ("감탄은 남김", classify("그래, 알았다") == []),
        ("나열 줄끝은 자동 아님", not any(ob for _i, _c, ob in classify("허크, 바다트,\n죠안나"))),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument(
        "--freeze", action="store_true", help="애매 목록 기준선을 지금 값으로(줄었을 때만)"
    )
    a = ap.parse_args()
    lock = locked()
    if a.apply:
        total = 0
        for f, doc in docs():
            n = 0
            for k, v in doc.items():
                if (
                    k.startswith("_")
                    or not isinstance(v, str)
                    or f"{os.path.basename(f)[:-5]}#{k}" in lock
                ):
                    continue
                new, c = strip(v)
                if c:
                    doc[k] = new
                    n += c
            if n:
                total += n
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=1)
                    fh.write("\n")
        print(f"뺀 쉼표 {total}")
    ctl = controls()
    for name, ok in ctl:
        print(f"  양성 대조 {'✅' if ok else '🔴'} {name}")
    pend, obv = census()
    print(f"  명백(자동으로 뺄 것) 남음 {len(obv)}")
    for c, v in sorted(pend.items()):
        print(f"  애매 {c} {len(v)}")
    base = {}
    if os.path.exists(PENDING):
        with open(PENDING, encoding="utf-8") as fh:
            base = json.load(fh)["counts"]
    if a.freeze:
        cur = {c: len(v) for c, v in pend.items()}
        new = {c: min(n, base.get(c, n)) for c, n in cur.items()} if base else cur
        with open(PENDING, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "_why": "규칙 2-13 애매 부류 기준선(부류별 개수) — 늘면 실패, --freeze 는 줄었을 때만 낮춘다. 부류·열쇠는 check_commas.py 로 뽑는다.",
                    "counts": new,
                    "keys": {c: sorted(set(v)) for c, v in pend.items()},
                },
                fh,
                ensure_ascii=False,
                indent=1,
            )
            fh.write("\n")
        print("기준선 갱신")
        return 0
    bad = [n for n, ok in ctl if not ok]
    rc = 0
    if a.check:
        if bad:
            print("  🔴 양성 대조 실패:", bad)
            rc = 1
        if obv:
            print("  🔴 명백한 쉼표가 남았다 —", ", ".join(obv[:10]))
            rc = 1
        for c, v in pend.items():
            if len(v) > base.get(c, 0):
                print(f"  🔴 애매 부류 {c} 가 기준선 {base.get(c, 0)} 보다 늘었다 ({len(v)})")
                rc = 1
        if rc == 0:
            print("  ✅ 2-13 쉼표 — 명백 0 · 애매 기준선 이하")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
