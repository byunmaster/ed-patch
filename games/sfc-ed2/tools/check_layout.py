"""조판 결과 지표 래칫 — 번역 문안 전량을 빌드와 같은 길로 조판한 결과에서 줄·쪽 나눔 결함을 센다(규칙 2-16 a~e). 값은 `layout_baseline.json` 보다 **늘면 실패**, 줄면 `--freeze`.

    python3 check_layout.py [--freeze] [--list 지표]      # 지표: orphan · midpage · lonepunct · leadspace · overwide · compound · fewer

  a orphan     쪽 끝 한 어절 고아 — 둘 이상의 쪽 가운데 마지막 쪽이 낱말 하나뿐이고 앞 쪽이 문장 끝이 아니다
  b midpage    문장 중간 한 낱말 쪽 — 쪽 끝 줄이 낱말 하나이고 문장 끝 부호가 아니다
  c lonepunct  고아 부호 — 부호만 있는 줄
  d leadspace  첫 칸 공백 — 줄(화자 머리 뒤·구간 첫 줄 제외) 첫머리가 공백 / overwide = 한 줄이 50 폭을 넘는다
  f regress    퇴행 — 원판 조판엔 없던 끊김이 보조용언·의존명사·관형사 고아에 걸리거나 한 줄이던 문장이 갈렸다(조판기가 이런 이동은 거부한다)
  h2 balance   창 분배 — 창이 둘 이상인 구간에서 창 수를 안 늘리고 고르게 나눌 수 있는데 창 줄 수 차가 2 이상이다(쪽 경계는 문장 끝·절 경계로만 옮긴다 — 지표만, 재배치는 안 한다)
  i lean       붙임 포기 — 2-6 보조용언 붙임을 지키면 원문 창보다 쪽이 느는 구간이 붙임을 포기하고 창 수를 지킨 수(한도, 규칙 2-17)
  j fewer     창 줄임 — 조판 결과의 본문 창(쪽) 수가 입력 문안(원문 창 구조)보다 적다(원문 두 창을 한 창에 합쳤다, 규칙 2-17). 끝 `<05>` 반복은 창이 아니라 센 대상 밖
  k joined    고정 배치 합침 — 입력 문안의 빈 줄·둘째 줄부터의 앞 공백 줄(가운데 맞춤 카드·간판 따위의 고정 배치)이 조판 결과에서 줄었다(손 개행을 문장 중간 줄바꿈으로 읽어 합쳤다, 3장 카드 11-06). 의도한 자리는 textmap `raw`
  l more      창 늘어남(상한) — 조판 결과의 본문 창 수가 입력(원문 창 구조)보다 많다. **전수 194 가 용량 때문**이다 — 규칙을 끈 기본 조판(`RULESOFF`)도 같은 창 수라 쪽 위치만 다시 짜서 드는 곳이 0(11-06 전수). 한국어가 원문 칸보다 길어 3줄 쪽에 안 들어가는 곳이고, 문안을 줄이지 않는 것이 규칙 2-17(마스터 10-31)이라 줄이지 않는다 — 늘면 실패(래칫)
  m emptywin  빈 창 — 조판 결과에 본문 가운데 `<05><05>`(내용 없는 대사창, ▼만 기다린다)가 있는데 입력엔 없다(쪽 끝 앞 개행이 줄 배치와 겹침, 마스터 실플레이 11-06 빈 대사창). 0 이어야 한다
  n blankline 빈 줄 개행(규칙 2-18, 마스터 11-08) — 쪽(둘째 창부터) 머리가 빈 줄이거나 창 안쪽에 빈 줄이 낀다. 구간 머리의 `\\n` 은 화자 줄 개행(헤더가 앞 조각에 있다)이라 화면에 빈 줄이 안 생겨 센 대상 밖(원판도 같은 구조 — 11-08 화면 확인)
  e compound   굳은 [명사+명사] 구가 줄·쪽 끝에서 갈렸다 — 앞 어절이 조사·어미로 안 끝나고 같은 이음이 문안 전량에 2회 이상"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import segs
import typeset as T

BASE = Path(__file__).resolve().parents[1] / "layout_baseline.json"
_END = ".!?…~」』"
_PART = set("은는이가을를의에도와과로고며면만다요죠네까니라야지든나서게데기해히")  # 조사·어미로 끝나는 어절은 굳은 구의 앞 마디가 아니다
OLD = False
KEYS = ["orphan", "midpage", "lonepunct", "leadspace", "overwide", "compound", "regress", "balance", "lean", "fewer", "joined", "more", "emptywin", "blankline"]


def body_windows(t: str) -> int:
    """본문 창 수 = 끝의 `<05>` 반복을 뗀 뒤 남은 `<05>` 수(+1 창). 끝 `<05>` 는 마지막 창의 닫힘이라 창 수에 안 든다."""
    return re.sub(r"(<05>)+$", "", t).count("<05>")


def fewer_windows(src: str, out: str) -> bool:
    """입력 문안보다 창이 적으면 True — 원문 창을 합친 것."""
    return body_windows(out) < body_windows(src)


def joined_windows(src: str, out: str) -> int:
    """고정 배치가 든 창에서 빈 줄(둘째 줄부터 가운데) 또는 앞 공백 줄이 조판 결과에서 줄어든 창 수."""
    n = 0
    for a, b in zip(src.split("<05>"), out.split("<05>")):
        al = re.sub(r"<1e>.*?<04>\n?", "", a).split("\n")
        bl = re.sub(r"<1e>.*?<04>\n?", "", b).split("\n")
        blank_a = sum(1 for l in al[1:-1] if not l.strip())
        blank_b = sum(1 for l in bl[1:-1] if not l.strip())
        lead_a = sum(1 for l in al[1:] if l.startswith(" "))
        lead_b = sum(1 for l in bl[1:] if l.startswith(" "))
        if blank_b < blank_a or lead_b < lead_a:
            n += 1
    return n


SRC: dict = {}
ARGS: dict = {}  # 보강 규칙을 포기한 문안(`typeset.FALLBACKS`)의 퇴행 판정을 옛 규칙으로 다시 하려는 재료
RULESOFF: dict = {}  # 같은 선행 폭에서 규칙을 끈 조판 — 퇴행 판정의 기준(가드와 같다)


def typeset_all(glue: bool = True) -> dict[str, str]:
    src = common.rom_bytes()
    seg_map, _, dict_map = build.collect_texts(src)
    names = build.dict_names(src, dict_map)
    e1w = build.e1_texts(src, seg_map)
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
    T.GLUE_PAIRS = T.compound_pairs(build.resolve_josa(v['kr'], names) for v in seg_map.values()) if glue else set()
    jl = build.jump_leads(src, seg_map, sg, names, e1w)
    res, end = {}, {}
    for key, v in sorted(seg_map.items()):
        a, b = sg[key]
        if not (0xC2 <= (common.off2snes(a) >> 16) <= 0xCB) or v.get("raw"):
            continue
        text = build.resolve_josa(v["kr"], names)
        tw = {**names, **e1w, **build.call_texts(text, a, seg_map, sg)}
        pv = build.lead_state(src, a, key, seg_map, names, tw, end, jl)
        SRC[key] = text
        ARGS[key] = (text, src, b, seg_map, names, tw, pv)
        RULESOFF[key] = build.typeset_seg(text, src, b, seg_map, names, tw, pv, T._base)
        res[key] = build.typeset_seg(text, src, b, seg_map, names, tw, pv)
        if pv:
            SRC[key] += "<05>"  # 이어 쓰기 구간은 분배 대상이 아니다
        end[b] = T.chain_state(res[key], pv, tw)
    return res


def _pages(text: str) -> list[list[str]]:
    t = re.sub(r"<1e>.*?<04>\n?", "", text, flags=re.S)
    t = re.sub(r"<E[01]:\d+>", "\x01", t)  # 이름 변수 자리 — 줄 머리 부호가 이름 뒤 조각이면 고아 부호가 아니다
    return [[re.sub(r"<[^>]*>", "", l) for l in p.split("\n") if re.sub(r"<[^>]*>", "", l).strip() or l.startswith(" ")] for p in t.split("<05>")]


def measure(res: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in KEYS}
    pairs = T.compound_pairs(res.values())
    for k, t in res.items():
        pages = _pages(t)
        pages = [p for p in pages if any(l.strip() for l in p)]
        if fewer_windows(SRC.get(k, ""), t):
            out["fewer"].append(k)
        if body_windows(t) > body_windows(SRC.get(k, "")):
            out["more"].append(k)
        if "<05><05>" in re.sub(r"(<05>)+$", "", t) and "<05><05>" not in SRC.get(k, ""):
            out["emptywin"].append(k)
        _ws = re.sub(r"<1e>.*?<04>\n?", "", t, flags=re.S).split("<05>")
        for _i, _w in enumerate(_ws):
            _ls = re.sub(r"<[^>]*>", "", _w).split("\n")
            if any(l.strip() for l in _ls) and ((_i > 0 and len(_ls) > 1 and not _ls[0].strip()) or any(not l.strip() for l in _ls[1:-1])):
                out["blankline"].append(f"{k} 창{_i}")
        if joined_windows(SRC.get(k, ""), t):
            out["joined"].append(k)
        if T.rebalance(t, SRC.get(k, "<05>")) != t:  # 제약 안에서 더 고르게 나눌 수 있는 구간(원본 손 쪽나눔·화자 머리·이어 쓰기는 분모 밖)
            out["balance"].append(k)
        for i, p in enumerate(pages):
            last = p[-1].strip()
            one = " " not in last
            if i == len(pages) - 1 and i > 0 and len(p) == 1 and one and pages[i - 1][-1].strip()[-1:] not in _END:
                out["orphan"].append(k)
            if i < len(pages) - 1 and one and last[-1:] not in _END:
                out["midpage"].append(k)
            for j, ln in enumerate(p):
                s = ln.strip()
                if s and re.fullmatch(r"[.,、。]+", s):
                    out["lonepunct"].append(k)
                if ln.startswith(" ") and ln.strip() and (i or j):
                    out["leadspace"].append(k)
                if sum(T.width(c) for c in re.sub(r"\{\*[^}]*\}", "가", ln).replace("\x01", "").replace(T.NBSP, " ")) > 50:
                    out["overwide"].append(k)
            lines = [l.strip() for l in p]
            for a, b in zip(lines, lines[1:]):
                wa, wb = a.split(" ")[-1:], b.split(" ")[:1]
                if wa and wb and (wa[0], wb[0]) in pairs:
                    out["compound"].append(f"{k} {wa[0]}|{wb[0]}")
    return out


def main() -> None:
    global OLD
    if "--old" in sys.argv:  # 규칙 이전 조판(원판 줄·쪽 나눔) — 전→후 비교용
        OLD = True
        T.CLAUSE, T.LINE_CLAUSE, T.SOFTNL = 0, 0, 0
    T.LEANS.clear()
    res = typeset_all(glue=not OLD)
    lean_texts = set(T.LEANS)
    m = measure(res)
    m["lean"] = sorted(k for k, a in ARGS.items() if a[0] in lean_texts)  # 붙임을 포기해 창 수를 지킨 구간 — 퇴행 판정에서 뺀다(규칙 2-17)
    if not OLD:
        m["regress"] = []
        for k, t in res.items():
            if k not in RULESOFF or k in m["lean"]:
                continue
            bad = T.regress_net(RULESOFF[k], t)
            if bad:  # 쪽·줄이 늘어 보강 규칙을 포기한 문안(typeset.typeset)은 보강 전 규칙으로 판정한다
                T._OLD_RULES = True
                try:
                    if build.typeset_seg(*ARGS[k]) == t:
                        bad = T.regress_net(RULESOFF[k], t)
                finally:
                    T._OLD_RULES = False
            m["regress"] += [f"{k} {r}" for r in bad]
    m.setdefault("regress", [])
    cnt = {k: len(v) for k, v in m.items()}
    if "--list" in sys.argv:
        for x in m[sys.argv[sys.argv.index("--list") + 1]]:
            print(x)
        return
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps(cnt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("기준선 갱신:", cnt)
        return
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    bad = [f"{k} {cnt[k]} > 기준선 {base[k]}" for k in KEYS if k in base and cnt[k] > base[k]]
    print("조판 지표 [sfc-ed2]", " · ".join(f"{k} {cnt[k]}" for k in KEYS), "(기준선 " + (" · ".join(f"{k} {base[k]}" for k in KEYS if k in base) or "없음") + ")")
    if bad:
        print("지표 악화:", "; ".join(bad))
        sys.exit(1)
    print("지표 악화 0")


if __name__ == "__main__":
    main()
