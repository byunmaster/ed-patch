"""번역 규칙 1-1·1-3·1-7·2-12 — 문장부호 전수 검사(마스터 11-13 「문장부호 한번 검토」).

대사·자막·시스템·전투 문안(`names_corpus.pairs()` 의 우리 줄) 전수에서 아래 꼴이 하나라도 있으면 실패(기준선 없음, 0 이 정상):
 전각 ！？⁉‼ · 전각 ．，。、 · `...` · 가운뎃점 반복 `・・・`·`･･･` · 띄운 `… … …` · ASCII `~` · `～.` · `?!`·`!?` 순서가 원문과 다름 · `?.`·`!.` · `[?!]…`(2-12) · 문장부호 앞 공백.
`--selftest` = 양성 대조(가짜 문장에서 각 규칙이 울어야 하고, 올바른 꼴에서는 울지 않아야 한다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TAG = re.compile(r"<[^>]*>")
RULES = {
    "전각 !?": re.compile(r"[！？⁉‼⁈⁇]"),
    "전각 .,": re.compile(r"[．，。、]"),
    "...": re.compile(r"\.{2,}"),
    "가운뎃점 반복": re.compile(r"[・･]{2,}|[・･] [・･]"),
    "띄운 …": re.compile(r"…(?: +…)+"),
    "ASCII ~": re.compile(r"~"),
    "～ 뒤 마침": re.compile(r"～ ?[.,]"),
    "?. !.": re.compile(r"[?!]\.(?!\.)"),
    "[?!]…": re.compile(r"[?!]…"),
    "부호 앞 공백": re.compile(r"[가-힣A-Za-z0-9\)] +[.,!?](?![.,!?])"),
}


# 어댑터(`_t`)가 쪽 넘김 `<05>` 를 떼서 「!!<05>…」 가 「!!…」 로 보이는 자리 — 새 쪽 머리의 `…`(2-11 문장 머리)라 위반이 아니다
PAGE_HEAD_OK = {"sysmsg:039398"}


MIX = re.compile(r"[!?！？]{2,}")


def order_bad(jp: str, ours: str) -> bool:
    """`!?`·`?!` 순서는 원문을 따른다(관리자 11-13 — 규칙 1-1 은 반각 두 글자만 정한다). 원문에 없는 순서를 우리가 지어 넣으면 위반.
    원문에 쓰인 순서 집합 밖의 순서가 우리 줄에 있으면 true(원문에 혼합 부호가 없으면 어느 쪽이든 원문 근거가 없으니 `!?` 만 허용)."""
    norm = str.maketrans("！？", "!?")
    jset = {
        g
        for g in MIX.findall(TAG.sub("", jp).replace(" ", "").translate(norm))
        if "!" in g and "?" in g
    }
    oset = {g for g in MIX.findall(TAG.sub("|", ours)) if "!" in g and "?" in g}
    allowed = jset or {"!?"}
    return (
        bool(oset - {g for g in oset if g in allowed or g.strip("!?") == "" and False})
        and not oset <= allowed
    )


def violations(ours: str):
    t = TAG.sub("|", ours.replace("<01>", "\n"))  # 태그(쪽·화자 구분)는 경계로 둔다
    return [k for k, r in RULES.items() if r.search(t)]


DEFICIT_BASE = Path(__file__).resolve().parents[1] / "punct_deficit_baseline.json"


def marks_jp(jp: str) -> dict:
    """원문 줄의 부호 수 — `!`·`?`(전각 포함) 글자 수 · `…`(원문 점 ･ ･ ･ 는 round(n/3), 최소 1) 글자 수와 덩이 수 · `～` · `。`. 장음 `ー` 는 부호가 아니라 안 센다(관리자 11-13)."""
    t = TAG.sub("|", jp).translate(str.maketrans("！？〜", "!?～"))
    t = re.sub(
        r"(?<=[･・…!?])\s*。", "", t
    )  # 줄임표·!·? 바로 뒤 `。` 는 그 부호가 문장 끝이라 따로 안 센다
    runs = [
        max(1, round((len(re.findall("[･・]", m.group())) + 3 * m.group().count("…")) / 3))
        for m in re.finditer(r"(?:[･・] ?){2,}|…+", t)
    ]
    return {
        "!": t.count("!"),
        "?": t.count("?"),
        "…": sum(runs),
        "…덩이": len(runs),
        "～": t.count("～"),
        "。": t.count("。"),
    }


def marks_ko(ours: str) -> dict:
    t = TAG.sub("|", ours)
    return {
        "!": t.count("!"),
        "?": t.count("?"),
        "…": t.count("…"),
        "…덩이": len(re.findall("…+", t)),
        "～": t.count("～"),
        ".": len(re.findall(r"(?<!\.)\.(?!\.)", t)),
    }


def deficits(jp: str, ours: str) -> dict:
    """번역이 원문 부호를 뺀 만큼(원문 − 우리, 양수만). 문장 끝은 `。` ↔ `.`·`…`·`!`·`?`·`～` 합산으로 잰다(그 부호가 문장 끝 노릇을 한다 — 관리자 11-13)."""
    a, k = marks_jp(jp), marks_ko(ours)
    d = {m: a[m] - k[m] for m in "!?…～" if a[m] > k[m]}
    term_jp = a["。"] + a["!"] + a["?"] + a["…덩이"] + a["～"]
    term_ko = k["."] + k["!"] + k["?"] + k["…덩이"] + k["～"]
    if term_jp > term_ko:
        d["끝"] = term_jp - term_ko
    return d


def deficit_main(write: bool):
    import json

    import names_corpus as n

    cur = {}
    for pl, jp, ours, _k in n.pairs():
        if not ours or not pl.startswith(("script:", "sysmsg:", "battle:")):
            continue
        d = deficits(jp, ours)
        if d:
            cur[pl] = d
    if write:
        DEFICIT_BASE.write_text(
            json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"  부호 빠짐 기준선 {len(cur)}줄 기록")
        return
    base = json.loads(DEFICIT_BASE.read_text(encoding="utf-8")) if DEFICIT_BASE.exists() else {}
    worse = [
        (pl, d)
        for pl, d in cur.items()
        if any(v > base.get(pl, {}).get(k, 0) for k, v in d.items())
    ]
    if worse:
        for pl, d in worse[:30]:
            print(f"  ✗ {pl} — 번역 부호가 원문보다 적다 {d} (기준선 {base.get(pl, {})})")
        print(
            f"❌ 원문 부호를 뺀 줄 {len(worse)}건 (기준선 밖 — 되살리거나 판단이면 --freeze-deficit)"
        )
        sys.exit(1)
    print(f"  ✅ 부호 빠짐 경보 — 기준선 {len(base)}줄 · 새 빠짐 0 (현재 {len(cur)}줄)")


def selftest():
    assert deficits("何だ !!", "뭐야!!") == {} and deficits("何だ !!", "뭐야!") == {"!": 1, "끝": 1}
    assert deficits("何だ？", "뭐야.") == {"?": 1}  # 끝은 `.` 가 대신 서서 0
    assert deficits("ふう ･ ･ ･ ･ ･ ", "휴우") == {"…": 2, "끝": 1}
    assert deficits("行くぞ。", "간다") == {"끝": 1}
    assert not deficits("行くぞ。", "간다.") and not deficits("いやー。", "아.")
    assert not deficits("だめだ！？", "안 돼!?")

    bad = {
        "전각 !?": "뭐？",
        "전각 .,": "그래，",
        "...": "그래...",
        "가운뎃점 반복": "그래・・・",
        "띄운 …": "그래… … …",
        "ASCII ~": "그래~",
        "～ 뒤 마침": "불렀어～.",
        "?. !.": "뭐?.",
        "[?!]…": "뭐!?…",
        "부호 앞 공백": "뭐 ?",
    }
    for k, s in bad.items():
        assert k in violations(s), f"양성 대조 실패: {k}"
    assert order_bad("何？！", "뭐!?") and not order_bad("何！？", "뭐!?")
    assert order_bad("何だ！？", "뭐?!") and not order_bad("何だ？！", "뭐?!")
    for s in ("뭐!? 그래…", "…그랬나?", "그래… 알았어!!", "불렀어～"):
        assert not violations(s), f"음성 대조 실패: {s}"
    print("  ✅ 부호 검사 양성·음성 대조 통과")


def main():
    selftest()
    if "--freeze-deficit" in sys.argv:
        deficit_main(True)
        return
    import names_corpus as n

    bad = []
    tot = 0
    for pl, _jp, ours, _k in n.pairs():
        if not ours or pl.startswith("names:"):
            continue
        tot += 1
        if order_bad(_jp, ours):
            bad.append((pl, "?! 순서(원문과 다름)"))
        for k in violations(ours):
            if pl in PAGE_HEAD_OK and k == "[?!]…":
                continue
            bad.append((pl, k))
    if bad:
        for pl, k in bad[:30]:
            print(f"  ✗ {pl} — {k}")
        print(f"❌ 부호 위반 {len(bad)}건")
        sys.exit(1)
    print(f"  ✅ 문장부호 검사 — 우리 줄 {tot}개 위반 0")
    deficit_main(False)


if __name__ == "__main__":
    main()
