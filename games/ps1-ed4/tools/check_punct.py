"""문장부호 게이트(번역 규칙 1-1 · 1-3 · 1-7 · 2-12, 마스터 11-13 「게임별 문장부호 한번 검토」) — 대본·UI 문안 전수.

    python3 tools/check_punct.py            # 검사(실패 시 종료 코드 1)
    python3 tools/check_punct.py --freeze   # 점 개수 어긋남 래칫 기준선을 내린다(줄었을 때만)

  ① 꼴 금지(0) — `...`·`..`·`･`·`‥`·`・・`(점 겹침) · `… …`(띄운 반복 = 원문 「· · ·」 오역) · 전각 `！？．，。、` · `⁉‼⁈⁇` ·
     ASCII `~`(→ `～`) · `～.`(1-7) · `?.`·`!.`·`?,` · `…?` 순서 뒤집힘 `?…`·`!…`(2-12) · 전각 공백.
  ③ 원문 부호 누락(마스터 11-13 「원문 부호는 빼지말자」) — 원문 `！`·`？`·`〜`(숫자 자리표시 뒤 제외) 수보다 한국어 `!`·`?`·`～` 가 적은 줄. 끝 `。` 는 번역이 문장을 다음 조각으로 이어 쓴 자리(「~와서는」)가 대부분이라 되살리지 않고 **래칫**(period_lost)만 둔다. `、` 는 한국식 쉼표 규칙이라 대상 아님, 장음 `ー` 는 글자라 셈 밖(`～` 늘림 상한에만: 한국어 `～` > 원문 `〜`+히라가나 뒤 `ー`). **기준선 래칫**.
  ② 말줄임 개수 — 원문 점 n(≥2) 덩이마다 한국어 `…` round(n/3)(최소 1). 어긋난 줄은 **기준선 래칫**(늘면 실패 —
     남은 것은 낱말을 음절째 끊거나 조사를 떼어 말하는 말더듬이 · 번역에서 원문 점을 뺀 줄).
양성 대조(`selftest`)가 가짜 줄에서 전부 잡는지 먼저 확인한다.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

BASE = os.path.join(HERE, "..", "punct_baseline.json")
FORMS = {
    "ASCII 점 ... / ..": re.compile(r"\.{2,}"),
    "반각 가운뎃점 ･ · ‥": re.compile(r"[･‥]"),
    "가운뎃점 겹침 ・・": re.compile(r"・{2,}"),
    "띄운 … 반복": re.compile(r"…\s+…"),
    "전각 ！？．，。、": re.compile(r"[！？．，。、]"),
    "⁉ ‼ ⁈ ⁇": re.compile(r"[⁉‼⁈⁇]"),
    "ASCII ~": re.compile(r"~"),
    "～ 뒤 마침표(1-7)": re.compile(r"～\."),
    "?. !. ?,": re.compile(r"[?!][.,]"),
    "?… !… 순서(2-12)": re.compile(r"[?!]…"),
    "전각 공백": re.compile("　"),
}
JP_DOTS = re.compile(r"[・･…‥]+")


def forms(kr):
    return [n for n, r in FORMS.items() if r.search(kr)]


def expected_runs(jp):
    """원문 점 덩이(점 2개 이상 — 한 개 `・` 는 이름 가운뎃점) → 한국어 `…` 개수 목록."""
    out = []
    for m in JP_DOTS.finditer(jp):
        n = sum(2 if c == "‥" else 3 if c == "…" else 1 for c in m.group())
        if n >= 2:
            out.append(max(1, round(n / 3)))
    return out


def ellipsis_mismatch(jp, kr):
    e = expected_runs(jp)
    return bool(e) and e != [len(m.group()) for m in re.finditer(r"…+", kr)]


END_PUNCT = re.compile(r"[.!?…～][」』”’)\"']*$")


def lost(jp, kr):
    """번역이 뺀 원문 부호 — 이름(`!`·`?`·`～`·`.`) 목록."""
    out = []
    if len(re.findall("[！!]", jp)) > kr.count("!"):
        out.append("!")
    if len(re.findall("[？?]", jp)) > kr.count("?"):
        out.append("?")
    if len(re.findall("(?<!e)〜|～", jp)) > kr.count("～"):
        out.append("～")
    return out


def period_lost(jp, kr):
    """원문 조각 끝 `。` 인데 한국어 조각 끝에 문장 끝 부호가 없다 — 번역이 문장을 다음 조각으로 이어 쓴 자리라 마침표를 되살리면 오적용(마스터 11-13 관리자 확인). 래칫만 둔다."""
    return bool(re.search("。[」』）)]*$", jp.strip())) and not END_PUNCT.search(kr.strip())


def tilde_extra(jp, kr):
    return kr.count("～") > len(re.findall("[〜～]", jp)) + len(re.findall("(?<=[ぁ-ん])ー", jp))


def selftest():
    assert lost("大丈夫か！", "괜찮아") == ["!"] and not lost("大丈夫か！", "괜찮아!")
    assert lost("そうか？", "그래") == ["?"] and lost("う〜ん", "으음") == ["～"]
    assert period_lost("行くぞ。", "간다") and not period_lost("行くぞ。", "간다…")
    assert not lost("�eeee〜ロゼ", "１０로제") and not lost("さあ、行こう", "자, 가자")
    assert tilde_extra("そう", "그래～") and not tilde_extra("そーう", "그래～")
    for bad in (
        "아니...",
        "그건..",
        "엘･필딘",
        "응‥",
        "아ㆍ・・",
        "그래… …",
        "뭐야！",
        "어？",
        "응。",
        "응~",
        "좋아～.",
        "뭐?.",
        "와!,",
        "왜?…",
        "응!…",
        "가　나",
    ):
        assert forms(bad), bad
    for ok in (
        "그래…!?",
        "응… 알았어?!",
        "자～, 가자.",
        "아쿠아・스플래시",
        "닿…지…않…는…다…",
        "좋아～",
    ):
        assert not forms(ok), ok
    assert expected_runs("あ・・・・・い") == [2] and expected_runs("Ｄｒ・バンドル") == []
    assert expected_runs("・・・と・・・") == [1, 1] and expected_runs("・・・・・・・・") == [3]
    assert ellipsis_mismatch("・・・・・あ", "…저") and not ellipsis_mismatch(
        "・・・・・あ", "……저"
    )
    assert not ellipsis_mismatch("さあ。", "글쎄…")  # 원문에 점이 없으면 한국어가 더해도 규칙 밖


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _json_rows():
    g = os.path.join(HERE, "..")
    for fn, key in (("ui_ed4.json", "strings"), ("ui_frag_ed4.json", "rows")):
        p = os.path.join(g, fn)
        if os.path.exists(p):
            for k, v in _load(p)[key].items():
                if v.get("kr"):
                    yield f"{fn}:{k}", v["kr"]
    p = os.path.join(g, "board4_ed4.json")
    if os.path.exists(p):
        for q, v in _load(p)["quests"].items():
            for j, ln in enumerate(v["lines"]):
                yield f"board4:{q}.{j}", ln


def scan():
    import names_corpus

    f, m, ls, te, pl = [], [], [], [], []
    for pos, jp, kr, _kind in names_corpus.pairs():
        if not kr:
            continue
        for n in forms(kr):
            f.append((n, pos, kr))
        if ellipsis_mismatch(jp, kr):
            m.append((pos, kr))
        if pos.startswith("scn:"):
            if lost(jp, kr):
                ls.append((pos, kr))
            if period_lost(jp, kr):
                pl.append((pos, kr))
            if tilde_extra(jp, kr):
                te.append((pos, kr))
    for pos, kr in _json_rows():
        for n in forms(kr):
            f.append((n, pos, kr))
    return f, m, ls, te, pl


KEYS = ("ellipsis_mismatch", "punct_lost", "tilde_extra", "period_lost")
LABEL = {
    "ellipsis_mismatch": "말줄임 개수 어긋남",
    "punct_lost": "원문 부호 누락",
    "tilde_extra": "～ 늘림",
    "period_lost": "조각 끝 마침표 없음",
}


def main():
    selftest()
    f, m, ls, te, pl = scan()
    base = {k: 10**9 for k in KEYS}
    if os.path.exists(BASE):
        with open(BASE) as fh:
            base.update(json.load(fh))
    lists = {"ellipsis_mismatch": m, "punct_lost": ls, "tilde_extra": te, "period_lost": pl}
    now = {k: len(lists[k]) for k in KEYS}
    print(
        f"  꼴 위반 {len(f)} · "
        + " · ".join(f"{LABEL[k]} {now[k]} (기준선 {base[k]})" for k in KEYS)
    )
    if "--freeze" in sys.argv:
        out = {k: min(now[k], base[k]) for k in KEYS}
        with open(BASE, "w") as fh:
            json.dump(out, fh, indent=1)
            fh.write("\n")
        print("  기준선 갱신", out)
        return 0
    bad = 0
    for n, pos, kr in f[:30]:
        print(f"    ✗ {n} {pos} {kr[:40]!r}")
        bad += 1
    for k in KEYS:
        if now[k] > base[k]:
            print(f"    ✗ {LABEL[k]} 늘었다 {base[k]} → {now[k]}")
            for pos, kr in lists[k][:10]:
                print("      ", pos, kr[:40])
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
