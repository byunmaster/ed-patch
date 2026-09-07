#!/usr/bin/env python3
"""고유명사 표기 검사기 — `rpg-translate` §5 의 「고유명사」 축.

축이 둘인데 **무게가 다르다.**

    ① 우리 안에서 갈림   같은 낱말이 우리 문안에서 두 표기로 나온다   → 🔴 실패
    ② 정본과 다름        공용 정본(`shared/glossary`)과 표기가 다르다 → ⚠ 보고(대개 정상)

🔴 **① 만 실패로 친다.** 어느 표기가 옳든 **한 게임 안에서 갈리는 건 무조건 결함**이고
   지금 고칠 수 있다. 실측(2026-09-06): PS1 사전에서 씨앗을 받으며 「수정의 탑」 4곳 사이에
   「수정의탑」 하나가 섞여 들어왔다.

🔴 **② 는 대개 「정상」이다** — `docs/naming.md` 「접미는 층마다 다르다」가 정한 자리다.
   정본(`shared/glossary`)의 지명은 **HUD·표 꼴(붙임)** 이고 **대사는 띄운다**. 층이 다른
   것이지 갈린 게 아니다. 그래서 여기서 죽이지 않고 세어서 보여 주기만 한다.
   ⚠ 반대로 ① 에서는 **표 층을 빼고** 본다 — 안 그러면 규칙대로 넣은 표가 결함으로 잡힌다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import translate
from text.josa import josa

GLOSSARY = common.ROOT / "shared" / "glossary" / "eiyuu.json"
HANGUL = re.compile(r"[가-힣]")


def canon() -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, str) and key and not key.startswith("_"):
            out[key] = o

    walk(json.loads(GLOSSARY.read_text(encoding="utf-8")))
    return {k: v for k, v in out.items() if len(v) >= 3}


def spaced_forms(kr: str) -> list[str]:
    """공백만 다른 꼴 — 「수정의 탑」 ↔ 「수정의탑」.

    ⚠ **낱말 머리에서만** 본다. 안 그러면 「지나」의 변형 「지 나」가 「하지 나」에 걸린다
    (실측 오탐). 앞 글자가 한글이면 다른 낱말의 꼬리다.
    """
    out = {kr.replace(" ", "")}
    for i in range(1, len(kr)):
        if kr[i - 1] != " " and kr[i] != " ":
            out.add(kr[:i] + " " + kr[i:])
    return sorted(out - {kr})


def occurrences(text: str, term: str) -> int:
    """낱말 머리에서 시작하는 것만 센다."""
    n, i = 0, 0
    while (i := text.find(term, i)) >= 0:
        if i == 0 or not HANGUL.match(text[i - 1]):
            n += 1
        i += 1
    return n


def main() -> int:
    tbl = canon()
    script = json.loads(translate.SCRIPT.read_text(encoding="utf-8"))
    # 🔴 **표 층은 빼고 본다.** `docs/naming.md` 「접미는 층마다 다르다」 — HUD·표는 접미를
    #    붙이고(`크루즈마을`) 대사는 띄운다(`크루즈 마을`). **층이 다른 것이지 갈린 게 아니다.**
    #    안 빼면 이 검사기가 규칙대로 넣은 표를 결함으로 운다(실측 2026-09-06).
    body = "\n".join(v["t"] for v in script.values() if v.get("layer") != "table")

    split = []  # ① 우리 안에서 갈림
    differ = []  # ② 정본과 다름
    for kr in sorted(set(tbl.values())):
        forms = {f: occurrences(body, f) for f in [kr, *spaced_forms(kr)]}
        forms = {f: n for f, n in forms.items() if n}
        if len(forms) > 1:
            split.append((kr, forms))
        elif forms and kr not in forms:
            differ.append((kr, next(iter(forms))))

    # ③ 정본 낱말 **바로 뒤**의 조사 — 받침이 맞나
    #    ⚠ 문안 전체를 훑으면 오탐이 넘친다(「먹는」·「나을」은 어미지 조사가 아니다).
    #    **정본에 있는 낱말 뒤**로 좁히면 정확하다 — 실측으로 잡았다(「워프의 날개은」).
    PAIRS = ["은/는", "이/가", "을/를", "과/와", "으로/로"]
    wrong = []
    for k, v in script.items():
        t = v["t"]
        for kr in sorted(set(tbl.values())):
            i = 0
            while (i := t.find(kr, i)) >= 0:
                nxt = t[i + len(kr) : i + len(kr) + 2]
                for pair in PAIRS:
                    a, b = pair.split("/")
                    for got in (a, b):
                        if nxt.startswith(got):
                            want = josa(kr, pair)
                            if want != got and "(" not in want:
                                wrong.append((k, kr, got, want))
                            break
                i += 1

    print(f"정본 {len(set(tbl.values())):,}표기 · 우리 문안 {len(script):,}줄")
    if wrong:
        print(f"  🔴 정본 낱말 뒤 조사가 안 맞는다 {len(wrong)}건")
        for k, kr, got, want in wrong[:10]:
            print(f"     [{k[:8]}] 「{kr}{got}」 → 「{kr}{want}」")
    if differ:
        print(f"  ℹ 대사 층이라 정본(표 꼴)과 다르게 통일된 것 {len(differ)}종 — 정상")
        for kr, ours in differ[:10]:
            print(f"     우리 「{ours}」 · 정본 「{kr}」")
    if split:
        print(f"  🔴 우리 문안 안에서 갈린 표기 {len(split)}종")
        for kr, forms in split:
            print(f"     {forms}   (정본 「{kr}」)")
    if not split and not wrong:
        print("  ✅ 표기가 갈린 자리도, 조사가 어긋난 자리도 없다")
    return 1 if (split or wrong) else 0


if __name__ == "__main__":
    raise SystemExit(main())
