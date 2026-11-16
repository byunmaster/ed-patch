"""문장부호 전수 검사 (게이트) — 공통 번역 규칙 1-1 · 1-3 · 1-7 · 2-12(마스터 11-13 「문장부호 한번 검토」).

    python3 games/ss-ed3/tools/check_punct.py            # 검사(위반이 있으면 실패)
    python3 games/ss-ed3/tools/check_punct.py --list     # 부류별 계수 + 자리
    python3 games/ss-ed3/tools/check_punct.py --selftest # 양성 대조(심은 표본이 잡히나)

잡는 것(문안 전량 — 대사·읽을거리·시스템·설명문. 음성 자막은 목록만):
  1-3  `...`(ASCII 점 둘 이상 — ⚠ **점만 든 블록은 뺀다**: 마스터 10-30 「148곳만 하자」 판정(`master_rulings.json`)이 원판 개수대로 반각 점을 잠갔다) · `・` `･` `‥` `·` `。` `、` 잔존 · `… …` 처럼 띄워 여러 번 쓴 꼴(원문 「· · ·」 오역 → `…` 하나)
  1-1  전각 `！ ？ ． ，` · `⁉ ‼ ⁈ ⁇` — `!?` 는 반각 두 글자(원판 고정 칸 예외는 1-4·1-5 — 이 게임은 0건)
  1-7  ASCII `~`(→ `～`) · `～.`
  원문 부호 빠짐(마스터 11-13) — 번역의 `～ ! ? …` 수가 원문보다 적은 블록(래칫: 기준선보다 늘면 실패, `--freeze` 로 내림)
  2-12 `[?!]…` 순서(`…` 가 앞) · `?.` `!.` `?,` `!,` 겹침
`?!` 순서는 규칙이 못 박지 않아 세지만 실패로 치지 않는다(`!?` 와 섞여 있다).
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

RULES = [
    ("1-3 ASCII 점 `..`", re.compile(r"\.{2,}")),
    ("1-3 일본식 점", re.compile(r"[・･‥·。、]")),
    ("1-3 띄운 `… …`", re.compile(r"…+(?: +…+)+")),
    ("1-1 전각 ！？．，", re.compile(r"[！？．，]")),
    ("1-1 ⁉‼⁈⁇", re.compile(r"[⁉‼⁈⁇]")),
    ("1-7 ASCII ~", re.compile(r"~")),
    ("1-7 `～.`", re.compile(r"[～〜]\.")),  # `〜`(U+301C)도 같은 물결표 — 종전엔 `～`(U+FF5E)만 봐서 `〜.` 넷이 샜다(11-14 페이블 검수)
    ("2-12 [?!]… 순서", re.compile(r"[?!？！]…")),
    ("2-12 ?. !. ?, !,", re.compile(r"[?!][.,]")),
]
INFO = [("(참고) ?! 순서", re.compile(r"\?!"))]


def corpus():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import names_corpus as N

    for loc, _jp, kr, _k in N.pairs():
        if isinstance(kr, str) and "+" not in loc:
            yield loc, kr


BASE = os.path.join(C.GAME_DIR, "punct_short_baseline.json")


def _baseline():
    try:
        with open(BASE, encoding="utf-8") as f:
            return json.load(f)["short"]
    except (OSError, KeyError, ValueError):
        return 0


def corpus_pairs():
    import names_corpus as N

    for loc, jp, kr, _k in N.pairs():
        if isinstance(kr, str) and "+" not in loc and not loc.startswith(("SYS", "PARAM")):
            yield loc, jp, kr


def voice():
    def walk(o, p):
        if isinstance(o, str):
            yield p, o
        elif isinstance(o, dict):
            for k, v in o.items():
                if not str(k).startswith("_"):
                    yield from walk(v, f"{p}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, f"{p}[{i}]")

    for fn in ("voice", "voice_credits", "movie"):
        path = os.path.join(C.GAME_DIR, "script", f"{fn}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                yield from ((f"{fn}:{p}", s) for p, s in walk(json.load(f), ""))


DOT_ONLY = re.compile(r"[.\s]*")  # 점만 든 블록(침묵 줄) — 마스터 10-30 판정으로 반각 점 그대로


def scan(items):
    hit = {name: [] for name, _ in RULES + INFO}
    for loc, s in items:
        for name, pat in RULES + INFO:
            if name.startswith("1-3 ASCII") and DOT_ONLY.fullmatch(s):
                continue
            if pat.search(s):
                hit[name].append((loc, s))
    return hit


def _runs(s):
    """원문 점 덩이(`・・`↑ · `…`) → `…` 개수 합(round(n/3), 최소 1). 이름 가운뎃점 `・` 한 개는 안 센다."""
    return sum(max(1, round(len(m) / 3)) for m in re.findall(r"・{2,}|…+", s))


def short(jp, kr):
    """번역이 원문 부호를 뺀 부류 — 마스터 11-13 「원문 부호는 빼지말자」. `{부류: (원문 수, 번역 수)}`."""
    out = {}
    pairs = {
        "～": (len(re.findall(r"[〜～]", jp)), len(re.findall(r"[〜～]", kr))),
        "!": (len(re.findall(r"[！!]", jp)), kr.count("!")),
        "?": (len(re.findall(r"[？?]", jp)), kr.count("?")),
        "…": (_runs(jp), kr.count("…")),
    }
    for k, (a, b) in pairs.items():
        if a > b:
            out[k] = (a, b)
    return out


def selftest():
    samples = {
        "1-3 ASCII 점 `..`": "그런가...",
        "1-3 일본식 점": "응\u30fb\u30fb\u30fb",
        "1-3 띄운 `… …`": "아… … 응",
        "1-1 전각 ！？．，": "뭐？",
        "1-1 ⁉‼⁈⁇": "뭐⁉",
        "1-7 ASCII ~": "응~",
        "1-7 `～.`": "응〜.",
        "2-12 [?!]… 순서": "뭐?…",
        "2-12 ?. !. ?, !,": "뭐?.",
    }
    ok = True
    for name, pat in RULES:
        if not pat.search(samples[name]):
            print(f"  ❌ 양성 대조 실패 — {name} 이 표본을 못 잡는다")
            ok = False
    if short("やった！？う〜ん・・・", "해냈다"). keys() != {"～", "!", "?", "…"}:
        print("  ❌ 양성 대조 실패 — 원문 부호 빠짐(short)을 못 잡는다")
        ok = False
    if short("やった！", "해냈다!") or short("キャプテン・トーマス", "캡틴 토마스"):
        print("  ❌ 음성 대조 실패 — 부호를 지킨 번역·이름 가운뎃점을 잡는다")
        ok = False
    if scan([("t", "......"), ("t", "...\f")])["1-3 ASCII 점 `..`"]:
        print("  ❌ 음성 대조 실패 — 점만 든 블록(마스터 10-30 판정)을 잡는다")
        ok = False
    for good in ["그런가… 응.", "뭐…?", "…그래.", "응～", "뭐!?", "세…리…오…스…"]:
        for name, pat in RULES:
            if pat.search(good):
                print(f"  ❌ 음성 대조 실패 — {name} 이 정상 표본 {good!r} 을 잡는다")
                ok = False
    return ok


def main():
    if not selftest():
        sys.exit(1)
    items = list(corpus())
    pairs = list(corpus_pairs())
    sh = [(loc, short(jp, kr)) for loc, jp, kr in pairs if short(jp, kr) and not DOT_ONLY.fullmatch(kr)]
    hit = scan(items)
    vhit = scan(voice())
    if "--list" in sys.argv:
        for name in hit:
            print(f"{name}: 문안 {len(hit[name])} · 음성/무비 {len(vhit[name])}")
            for loc, s in hit[name][:20] + vhit[name][:20]:
                print(f"    {loc}  {s!r:.90}")
        return
    bad = sum(len(hit[n]) for n, _ in RULES)
    vbad = sum(len(vhit[n]) for n, _ in RULES)
    for name, _ in RULES:
        for loc, s in hit[name][:10]:
            print(f"  ❌ {name} — {loc}: {s!r:.90}")
    if vbad:
        print(f"  ⚠ 음성 자막·무비 {vbad}곳은 목록만 — `--list` (고치지 않는다)")
    base = _baseline()
    for loc, d in sh[:15]:
        print(f"  ⚠ 원문 부호 빠짐 — {loc}: {d}")
    print(f"문안 {len(items)}줄 점검 — 위반 {bad} · 번역 부호 수 < 원문 {len(sh)}블록(기준선 {base})")
    if "--freeze" in sys.argv:
        with open(BASE, "w", encoding="utf-8") as f:
            json.dump({"short": len(sh)}, f)
        print("기준선 갱신")
        return
    if len(sh) > base:
        print("  ❌ 원문 부호를 뺀 블록이 기준선보다 늘었다 — 원문 `～ ! ? …` 개수대로 되살린다(마스터 11-13)")
        bad += 1
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
