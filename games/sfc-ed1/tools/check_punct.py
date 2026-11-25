"""부호 규칙 검사 — 번역 규칙 2-11(`…` 뒤에 말이 이어지면 반각 공백) · 2-12(`?!` 와 `…` 가 겹치면 `…` 가 앞) · 1-7(`～` 뒤 마침표 금지). 0건 유지.

대상은 textmap/*.json 의 한글 문안(kr·ko 값) 전량. 제어 토큰(`<..>`·`{..}`)·줄 끝·닫는 부호 앞은 안 본다 —
`…` 바로 뒤가 한글·영숫자일 때만 위반이다.
"""

import json
import re
import sys
from pathlib import Path

TEXTMAP = Path(__file__).resolve().parents[1] / "textmap"
ELLIPSIS_GLUED = re.compile("…(?=[가-힣A-Za-z0-9])")  # 2-11
ELLIPSIS_INITIAL_SPACED = re.compile(
    "… (?=[가-힣A-Za-z0-9])"
)  # 2-11 정정: 문장 맨 앞 `…` 뒤는 붙인다
# 예외(마스터 10-12): 한 낱말을 음절마다 끊어 말하는 꼴(세…리…오…스…) — 홑음절 + … + 홑음절 + … 은 붙인다.
# 끊긴 조각이 한 낱말인지(붙임) 낱말이 바뀌는지(띄움)는 기계가 못 가리므로 홑음절 사슬은 통과시키고 문안이 정한다.
QUESTION_ELLIPSIS = re.compile("[?!？！]…")  # 2-12: …는 물음표·느낌표 앞에 (…?  …!  …!?)
TILDE_PERIOD = re.compile("～\\.")  # 1-7
RESIDUE = (  # 1-3 점 셋 잔존 · 띄운 반복 · 1-7 ASCII `~` · 1-1 ⁉‼ · 2-12 `?.`·`!.` 겹침(마스터 11-13 문장부호 전수)
    ("1-3 `...` 잔존", re.compile(r"\.{2,}")),
    ("1-3 일본식 가운뎃점", re.compile("[・･]")),
    ("1-3 `…` 띄운 반복(원문 「· · ·」 오역)", re.compile("…(?: …)+")),
    ("1-7 ASCII `~`", re.compile("~")),
    ("1-1 합자 ⁉‼", re.compile("[⁉‼⁈⁇]")),
    ("2-12 `?.`·`!.` 겹침", re.compile(r"[?!]\.(?![\.])")),
)
FULLWIDTH_BANG = re.compile(
    "[！？]"
)  # 1-8: 느낌표·물음표는 원판 반각 `!` `?`(원판 글자판 8px) — 전각은 2바이트 글꼴 글리프로 그려져 가늘고 사이가 벌어진다(마스터 11-06)


def _repeated_sound(text: str, i: int) -> bool:
    """같은 소리를 되풀이하는 의성어(흑…흑…흑…, 마스터 10-13) — `…` 앞뒤 글자가 같다. (`…(` 는 애초에 위반 꼴이 아니다)"""
    return 0 < i < len(text) - 1 and text[i - 1] == text[i + 1] and "가" <= text[i + 1] <= "힣"


def _sentence_initial(text: str, i: int) -> bool:
    """문장 맨 앞의 `…`(마스터 10-13) — 앞이 없거나 줄바꿈·공백·「 뒤. 뒤는 붙인다(…그런 것처럼). `?…` 처럼 앞말에 붙은 건 말줄임이다."""
    return (
        i == 0
        or text[i - 1] in "\n \u300c"
        or text[max(0, i - 2) : i] == "\\n"
        or text[max(0, i - 4) : i]
        in ("<E1>", "<FF>", "<E0>")  # 화자 이름표·쪽 넘김 바로 뒤도 문장 맨 앞이다
    )


def _in_chain(text: str, i: int) -> bool:
    """i 의 `…` 가 홑음절 사이(앞 글자가 홑음절이고 뒤 글자가 홑음절 + `…`)인가."""
    before = text[max(0, i - 2) : i]
    after = text[i + 1 : i + 3]
    lone_before = (
        bool(re.fullmatch("(?:^|[^가-힣])[가-힣]", before)) or len(before) == 1 and before.isalpha()
    )
    lone_after = bool(re.fullmatch("[가-힣]…", after))
    return lone_before and lone_after


def violations(text: str) -> list[str]:
    out = []
    for rule, rx in (("2-11", ELLIPSIS_GLUED), ("1-7", TILDE_PERIOD)):
        for m in rx.finditer(text):
            if rule == "2-11" and (
                _in_chain(text, m.start())
                or _repeated_sound(text, m.start())
                or _sentence_initial(text, m.start())
            ):
                continue
            out.append(f"{rule} …{text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for m in QUESTION_ELLIPSIS.finditer(text):
        out.append(f"2-12 {text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for m in FULLWIDTH_BANG.finditer(text):
        out.append(f"1-8 전각 느낌표·물음표 {text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for name, rx in RESIDUE:
        for m in rx.finditer(text):
            out.append(f"{name} {text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for m in ELLIPSIS_INITIAL_SPACED.finditer(text):
        if _sentence_initial(text, m.start()):
            out.append(f"2-11 문장 첫 …{text[max(0, m.start() - 8) : m.end() + 6]!r}")
    return out


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in ("kr", "ko") and isinstance(v, str):
                yield v
            else:
                yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def dot_runs(jp: str) -> list[int]:
    """원문 점 덩이(`・`·`･`·`…` 글자 하나가 점 하나) 길이들 — 규칙 1-3: `…` 개수 = round(n/3), 최소 1."""
    return [len(m.group()) for m in re.finditer("[・･…]+", jp)]


def expected_ellipsis(jp: str) -> list[int]:
    return [max(1, round(n / 3)) for n in dot_runs(jp)]


def ellipsis_vs_original() -> tuple[list[str], int, int]:
    """한글 `…` 덩이 수가 원문 점 덩이 수와 같은 창은 덩이마다 `…` 개수가 round(n/3) 인가(1-3). 덩이 수가 갈리면(번역이 더하거나 뺀 말줄임) 짝이 안 되어 안 본다.
    (위반 줄, 쟀다, 짝 안 된 수)"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import text  # noqa: I001  (common 보다 먼저)
    import common
    import textmap
    import units

    rom = common.rom_bytes()
    items, _ = units.extract(rom)
    res = text.resolver(rom)
    tm = textmap.load()
    bad, seen, measured, unpaired = [], set(), 0, 0
    for s in units.segments(items, res):
        sid = s["id"]
        v = tm.get(sid)
        if sid in seen or not v or not v.get("kr"):
            continue
        seen.add(sid)
        kr_runs = [len(m.group()) for m in re.finditer("…+", v["kr"])]
        exp = expected_ellipsis(s["jp"])
        if not kr_runs or not exp:
            continue
        if len(kr_runs) != len(exp):
            unpaired += 1
            continue
        measured += 1
        if kr_runs != exp:
            bad.append(
                f"1-3 {sid}@{s['addr']} 원문 점 {dot_runs(s['jp'])} → `…` {exp} 이어야 하는데 {kr_runs}"
            )
    return bad, measured, unpaired


# 원문 부호는 빼지 않는다(마스터 11-13 「원문 부호는 빼지말자」) — 번역 부호 수 < 원문 이면 실패. `ー`(장음 표기)는 부호가 아니라 대상 아님.
# 예외(사유 있는 것만): 사전 토큰 속 부호 · 음절을 잇는 `…` 짝이 어긋난 줄 · 전투 보상 「EP n 포인트 획득」 마침표 없음(규칙 1-5).
OMISSION_ALLOW = {
    ("4b65cacecc5b", "!"): "원문 `!` 가 사전 토큰({D5:2B}) 안 — 사전 문안이 가진다",
    ("b285f304ee31", "…"): "음절 5 · 4 개로 다른 한 음절씩 잇는 말줄임 — 짝이 안 맞는다",
    (
        "6034e1aaccc4",
        "…",
    ): "`ハイ…アギール` 는 정본 이름 「하이아길」(사전 토큰 {D3:39}) — 이름 속 점은 정본이 정한다",
    ("1e1e2057b774", "…"): "〃",
    ("61682a9346f8", "…"): "`울프 빌` 은 원문 단일 가운뎃점(점 1개 — 낱말 사이 구분자)이라 이름은 띄움 표기 — 점 한 개는 말줄임이 아니다",
    ("cd0b521950aa", "…"): "〃",
    ("bef4353647c9", "…"): "〃(원문 「…ビル………」 — 한글은 끝 말줄임만)",
    ("80e73d0eda15", "。"): "전투 보상 `EP n 포인트 획득` 은 마침표 없음(규칙 1-5, 마스터 10-09)",
}
_TOK = re.compile(r"<[^>]*>")


def omissions(jp: str, kr: str) -> dict[str, tuple[int, int]]:
    """한 문안에서 번역이 원문보다 적게 쓴 부호 → {부호: (원문, 번역)}. `…` 는 round(점/3), `～` 는 원문 `～`·`〜` 글자만."""
    j = re.sub(r"<[^>]*>|\{[^}]*\}", "", jp)
    k = re.sub(r"<[^>]*>|\{[^}]*\}", "", kr)
    out = {}
    for name, jn, kn in (
        ("?", len(re.findall("[?？]", j)), k.count("?")),
        ("!", len(re.findall("[!！]", j)), k.count("!")),
        (
            "…",
            sum(max(1, round(len(m.group()) / 3)) for m in re.finditer("[・･…]+", j)),
            sum(len(m.group()) for m in re.finditer("…+", k)),
        ),
        ("～", len(re.findall("[～〜]", j)), k.count("～")),
    ):
        if kn < jn:
            out[name] = (jn, kn)
    return out


_JS = re.compile(r"<PAGE>|<END>|<COLOR_C>|<JUMP[^>]*>|<IF_[A-Z0-9_]+[^>]*>|<CALL[^>]*>|<RETURN>")
_KS = re.compile(
    r"<FF>|<E0>|<E3>|<FE>|<F[0-9A-F]:[0-9A-F]*>|<FA:[0-9A-F]*>|<FC:[0-9A-F]*>|<FD:[0-9A-F]*>|<ED:[0-9A-F]*>|<EE:[0-9A-F]*>|<E[0-9A-F]>"
)
_END_MARK = re.compile(r"[.!?…～」』)]$")


def window_pairs(jp: str, kr: str, dict_kr: dict) -> list[tuple[str, str]] | None:
    """원문 창 · 한글 창 짝(창 수가 같을 때만 — 아니면 None). 사전 토큰은 사전 문안으로 펼치고 모르는 토큰은 `?` 로 둔다(끝 부호 판정을 느슨하게)."""

    def tok(m):
        v = dict_kr.get(m.group(1))
        return (v.get("kr") or "?") if isinstance(v, dict) else "?"

    jw = [re.sub(r"<[^>]*>|[{}]", "", w).replace("\n", "") for w in _JS.split(jp)]
    kw = [
        re.sub(r"<[^>]*>", "", re.sub(r"\{(D[0-9A-F]:[0-9A-F]{2})\}", tok, w)).replace("\n", "")
        for w in _KS.split(kr)
    ]
    jw, kw = [w for w in jw if w.strip()], [w for w in kw if w.strip()]
    return list(zip(jw, kw)) if len(jw) == len(kw) else None


def period_window_missing(jw: str, kw: str) -> bool:
    """원문 창이 `。` 로 끝나는데 한글 창이 끝 부호 없이 끝났나(`…`·`!`·`?`·`～`·닫는 부호도 문장 끝이다)."""
    return (
        jw.rstrip().endswith("。")
        and not _END_MARK.search(kw.rstrip())
        and not kw.rstrip().endswith("?")
    )


def punct_omissions() -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import text  # noqa: I001  (common 보다 먼저)
    import common
    import textmap
    import units

    rom = common.rom_bytes()
    items, _ = units.extract(rom)
    res = text.resolver(rom)
    tm = textmap.load()
    dict_kr = json.loads((TEXTMAP / "dict.json").read_text(encoding="utf-8"))
    bad, seen = [], set()
    for s in units.segments(items, res):
        sid = s["id"]
        v = tm.get(sid)
        if sid in seen or not v or not v.get("kr"):
            continue
        seen.add(sid)
        for name, (jn, kn) in omissions(s["jp"], v["kr"]).items():
            if (sid, name) not in OMISSION_ALLOW:
                bad.append(f"원문 부호 빠짐 {name} {sid}@{s['addr']} 원문 {jn} → 번역 {kn}")
        pairs = window_pairs(s["jp"], v["kr"], dict_kr)
        if pairs and (sid, "。") not in OMISSION_ALLOW:
            for jw, kw in pairs:
                if period_window_missing(jw, kw):
                    bad.append(
                        f"원문 `。` 끝 창에 끝 부호 없음 {sid}@{s['addr']} 「…{jw[-14:]}」→「…{kw[-10:]}」"
                    )
    return bad


def selftest() -> int:
    """양성 대조 — 위반 꼴은 잡고 정상 꼴은 놓아 줘야 한다. 못 잡으면 게이트가 고장난 것."""
    bad_forms = ["가서..", "그래・・・", "아… … …", "아~", "정말⁉", "응?.", "응!."]
    ok_forms = ["그래…", "응?", "정말!?", "꼬꼬댁～!?", "그래… 그렇군", "응…?"]
    miss = [t for t in bad_forms if not violations(t)]
    false = [t for t in ok_forms if violations(t)]
    if (
        expected_ellipsis("あ・・・") != [1]
        or expected_ellipsis("あ……") != [1]
        or expected_ellipsis("…" * 8) != [3]
    ):
        miss.append("expected_ellipsis")
    a, wa = (
        "\u3042",
        "\u304a\u308f\u3063\u305f\u305e",
    )  # 「あ」·「おわったぞ」 — JP 글자는 이스케이프로(자기 표 게이트가 JP·KR 혼합 리터럴을 센다)
    maru = "\u3002"
    ko = "응."
    if omissions(a + "?!!" + "\u2026" * 2 + maru, ko) != {"?": (1, 0), "!": (2, 0), "…": (1, 0)}:
        miss.append("omissions 양성")
    ok_kr = "응? 아! 그래～"
    if omissions(a + "?!" + "\uff5e", ok_kr) or omissions(a + "\u30fc!", "응!"):
        false.append("omissions 음성")
    nok, ell = "끝났네", "끝났네…"
    if (
        not period_window_missing(wa + maru, nok)
        or period_window_missing(wa + maru, ell)
        or period_window_missing(wa, nok)
    ):
        miss.append("period_window_missing")
    for t in miss:
        print("  ✗ 양성 대조 놓침", t)
    for t in false:
        print("  ✗ 음성 대조 오탐", t)
    return 1 if miss or false else 0


def main() -> int:
    bad = []
    total = 0
    for f in sorted(TEXTMAP.glob("*.json")):
        for key, v in json.loads(f.read_text(encoding="utf-8")).items():
            if key.startswith("_"):  # `_doc`·`_note` 는 주석이다(화면 문안 아님)
                continue
            texts = [v] if isinstance(v, str) else list(_strings(v))
            for t in texts:
                total += 1
                bad += [f"{f.name}:{key} {x}" for x in violations(t)]
    rom_bad, measured, unpaired = ellipsis_vs_original()
    bad += rom_bad
    for b in bad:
        print("  ✗", b)
    print(
        f"  ※ `…` 개수 원문 대조(1-3 round(n/3)): {measured}창 쟀다 · 짝 안 되는 창 {unpaired}(번역이 말줄임을 더하거나 뺀 곳)"
    )
    om = punct_omissions()
    bad += om
    for b in om:
        print("  ✗", b)
    if selftest():
        return 1
    print(
        f"부호 규칙(2-11 … 뒤 공백 · 2-12 ?!… 순서 · 1-7 ～ 뒤 마침표 · 1-3 점 셋 잔존·개수 · 1-1 합자): 문안 {total}건 중 위반 {len(bad)}건"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
