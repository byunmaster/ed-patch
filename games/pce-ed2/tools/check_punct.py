"""번역 규칙 부호·조판 검사 — **화면에 나가는 최종 문안 전량**(대사 · 제어 줄 틀 · 오프닝/엔딩 자막)을 훑어 규칙을 어긴 꼴을 센다(0 이어야 통과).

 · 1-3 `…` 개수 — 원문 점 n 개는 `…` round(n/3) 개(최소 1). 긴 말줄임(`……`↑)은 원문 점 수와 대조한다
 · 1-7 `～.` 금지 · 2-1 부호 뒤 글자 붙임 금지 · 2-2 부호 앞 공백 금지
 · 2-11 문장 맨 앞 `… ` 뒤 공백 금지(음절 끊어 말하기·의성어는 예외라 붙임이 정상) · 2-12 `?!…` 금지(`…?` `…!`)
 · 2-3/2-4/2-5 조판 전수 — 대사창에 앉힌 줄이 부호만으로 시작하거나(여는 `…` · 한 줄짜리 부호열은 제외) 빈 줄이거나 3줄을 넘으면 실패
 · 3-5 대사에 병기 조사(`은(는)` …)가 남으면 실패(제어 틀은 런타임 훅이 푸는 자리라 예외)
2-13 쉼표는 기계가 판정할 수 없다 — `comma_suspects()` 가 패턴 후보를 세기만 한다(실패로 치지 않는다).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

GAME = Path(__file__).resolve().parents[1]
RULES = {
    "1-3 점 연속·가운뎃점": re.compile(r"\.{2,}|[・･·]"),
    "1-7 `～.`": re.compile(r"～\."),
    "2-1 부호 뒤 글자 붙임": re.compile(r"(?<!\d)[,.!?](?=[가-힣A-Za-z])"),
    "2-2 부호 앞 공백": re.compile(r" +[,.!?]"),
    "2-12 부호+…": re.compile(r"[?!？！]+…"),
    "2-11 문장 앞 … 뒤 공백": re.compile(r"(?:^|(?<=[.!?]) )…+ (?=[가-힣A-Za-z0-9「“'(])"),
    "전각 부호": re.compile(r"[！？．，]"),
}
JOSA = re.compile(r"(은\(는\)|이\(가\)|을\(를\)|과\(와\)|으로\(로\))")
ORPHAN = re.compile(r"^[\s.,!?～」』)]")
COMMA_PAT = {
    "주제 뒤": re.compile(r"[가-힣](?:은|는),(?= |$)"),
    "부사어 뒤": re.compile(r"(?:에는|에서는|에도|에서도|에게는),(?= |$)"),
    "짧은 연결어미 뒤": re.compile(r"(?:하고|하며|으며|이며|며),(?= |$)"),
}


PUA = re.compile("[\ue000-\uf8ff]")


def has_pua(t: str) -> bool:
    return bool(PUA.search(t))


def violations(t: str) -> list[str]:
    """문안 한 줄(쪽·구간 표지 `¶` `§` 는 줄바꿈으로 본다) → 어긴 규칙 이름."""
    out = []
    for seg in re.split(r"[¶§\f\n]", t):
        for name, rx in RULES.items():
            if rx.search(seg) and name not in out:
                out.append(name)
    return out


def dot_violation(ours: str, src_dots: int) -> bool:
    """1-3 — 우리 문안에 긴 말줄임(`…` 3개↑ 연속)이 있으면 원문 점 수의 round(n/3) 와 총 `…` 개수가 같아야 한다."""
    runs = re.findall(r"…+", ours)
    if not runs or max(len(r) for r in runs) < 3 or not src_dots:
        return False
    return sum(len(r) for r in runs) != max(1, round(src_dots / 3))


def comma_suspects(t: str) -> list[str]:
    return [n for n, rx in COMMA_PAT.items() if rx.search(t)]


def corpus():
    """(자리, 종류, 문안, 원문 점 수|None) — 종류: dlg(대사) · tmpl(제어 틀) · sub(자막)."""
    import common
    import ctrllines
    import dialogue
    import jptext
    import package

    for rel in sorted(dialogue.package_chars()):
        pkg = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(pkg):
            if pkg[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(pkg, a, b)[0]
            lines = d.split(b"\x00")
            for li, _p, _spk, txt in dialogue.candidates(rel, a, d):
                src = re.sub(r"\{[^}]*\}", "", jptext.decode(lines[li]))
                dots = sum(3 if c == "…" else 1 for c in src if c in "･・…")
                yield f"{rel}:{a}:{li}", "dlg", txt, dots
    for k, v in ctrllines.table().items():
        yield k, "tmpl", ctrllines.strip_refs(v).replace("\\n", "\n").replace("\f", "\n"), None  # 틀의 `\\n` 은 줄바꿈 — 공백이 아니다(`? ……\\n그` 는 붙임이 맞다)
    for f in ("opening_sub", "ending_sub"):
        for i, s in enumerate(json.loads((GAME / "data" / f"{f}.json").read_text(encoding="utf-8"))["subs"]):
            yield f"{f}[{i}]", "sub", s["text"].replace("\n", " "), None


def main() -> int:
    import typeset

    bad = []
    n = {"dlg": 0, "tmpl": 0, "sub": 0}
    suspects = 0
    lines = 0
    for where, kind, t, dots in corpus():
        n[kind] += 1
        if has_pua(t):  # PS1 자리표시 문자(붙임 공백 U+E003 등)가 섞이면 글리프 표지로 읽혀 엉뚱한 글자가 된다(md-ed2 10-18)
            bad.append((where, "PUA 혼입", t))
        for v in violations(t):
            bad.append((where, v, t))
        if kind == "dlg":
            if JOSA.search(t):
                bad.append((where, "3-5 병기 조사", t))
            if dot_violation(t, dots or 0):
                bad.append((where, "1-3 … 개수(원문 점 수와 다름)", t))
            try:
                pages = typeset.pages(t.replace("§", "\f"))
            except Exception as e:  # noqa: BLE001
                bad.append((where, "조판 실패", str(e)[:60]))
                continue
            for p in pages:
                lines += len(p)
                if len(p) > typeset.LINES:
                    bad.append((where, "2-4 쪽이 3줄 초과", t))
                for ln in p:
                    if not ln.strip():
                        bad.append((where, "2-4 빈 줄", t))
                    elif ORPHAN.match(ln) and not re.fullmatch(r"[.,!?～ ]+", ln):
                        bad.append((where, "2-3/2-5 줄 머리 부호·공백", ln))
        suspects += bool(comma_suspects(t))
    for w, k, t in bad[:25]:
        print(f"  ✗ {w} {k}: {t[:60]}")
    print(
        f"  부호·조판 검사 [pce-ed2] — 문안 대사 {n['dlg']} · 제어 틀 {n['tmpl']} · 자막 {n['sub']} · 조판 줄 {lines} · 어긋남 {len(bad)} (쉼표 2-13 후보 {suspects}줄 — 참고)"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
