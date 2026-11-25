"""문장부호 전수 검사 — 마스터 11-13 「! ? !? ... . , ~ 이런 것들 … 이렇게 쓴 부분 없는지 검토해봐」(공통 번역 규칙 1-1·1-3·1-7·2-11).

    python3 games/pce-ed1/tools/check_punct.py            # 검사
    python3 games/pce-ed1/tools/check_punct.py --list     # 음성 자막 보류 목록도 출력

`script/` 의 모든 문자열(대사 · 시스템 문구 · 오프닝/엔딩 자막)을 훑어 잡는다:
  P1 ASCII 점 `..` · P2 일본식 점 `・・`·`･･` · P3 전각 `！？，．`(원판 고정 칸 `？？？？？？` 제외) · P4 `⁉‼⁈⁇` ·
  P5 ASCII `~`(→`～`) · P6 `～.` · P7 `?.`·`!.` · P8 띄워 여러 번 쓴 `… …` · P9 문장 맨 앞 `…` 뒤 공백 ·
  P10 `…` 덩이 길이가 원문 점 n 개의 round(n/3) 와 다름(원문 점 덩이 ≥2 일 때) · P11 `…` 곁에 `.`·`,` · P12 그 밖의 점 글자 · P13 `!?`·`?!` 순서는 원문 그대로 · P14 원문 `!`·`?`·`…`·`～` 를 번역이 뺌 · P15 원문 `。` 쪽 끝을 부호 없이 끝냄
음성 자막 줄은 마스터가 플레이하며 보므로 고치지 않는다 — `punct_voice_pending.json` 에 열쇠로 올려 두고(래칫: 새로 생기면 실패) 목록만 낸다.
양성 대조: 검출기가 죽어 0 이 나오는 걸 막으려고 합성 문장으로 먼저 자가 시험한다.
"""

import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

GAME = Path(common.GAME_DIR)
SCRIPT = GAME / "script"
MSGS = GAME / "work" / "derived" / "messages"
PENDING = GAME / "punct_voice_pending.json"
# 마스터 판정 문안 잠금(`master_rulings.json`)이 문안을 고정한 줄 — 원문 점 손실(P14 `…`)을 알고도 둔다
LOCKED_LOSS = {("15", "b8e57cd08fa125de"): "병사대장 첫 줄 — 「세리오스 왕자님이시군요? 오시기를 기다리고 있었습니다.」 다른 기종과 같은 잠금 문안(원문 끝 `・・・`)"}

# 공유 문자열이 이름이 아니라 감탄·호칭 조각인 줄(씬 64 복권집 「아,」「아니, 세리오스 왕자님!!」 — 호출 앞뒤 문장이 이어 읽는다, 11-23 마스터 판정 대기)
NAME_TAIL_OK = {("64", "610a59bf3ed725d9"), ("64", "cf0b5c633fc66905")}

SKIP_FILES = {
    "broken_fragments.json",
    "coverage_baseline.json",
    "debug_warp_plan.json",
    "editor_added_map.json",
    "glyph_order.json",
    "jump_baseline.json",
    "typeset_fit_one.json",
    "window_many_baseline.json",
}
FIXED_QMARK = "？？？？？？"  # 원판 고정 칸 라벨(sys/names.json files) — 1-4·1-5 예외
RULES = [
    ("P1 ASCII 점 `..`", re.compile(r"\.\.")),
    ("P2 일본식 점 `・・`·`･･`", re.compile(r"[・･]{2,}")),
    ("P3 전각 ！？，．", re.compile(r"[！？，．]")),
    ("P4 ⁉‼⁈⁇", re.compile(r"[⁉‼⁈⁇]")),
    ("P5 ASCII ~ (→ ～)", re.compile(r"~")),
    ("P6 ～ 뒤 마침표", re.compile(r"～\.")),
    ("P7 ?. !. 겹침", re.compile(r"[?!]\.")),
    ("P8 띄워 여러 번 쓴 … …", re.compile(r"…[ \t]+…")),
    ("P9 문장 맨 앞 … 뒤 공백", re.compile(r"(?:^|[\n\f「『(]|[.!?] )… ")),
    ("P11 … 곁에 . ,", re.compile(r"…[.,]")),
    ("P12 그 밖의 점 글자", re.compile(r"[·∙•⋯‥․]")),
    ("G1 숫자·단위 뒤 Gold 붙임(규칙 1-5 「영문 낱말 단위는 띄운다」, 마스터 11-23 「7만Gold」)", re.compile(r"[0-9만천억]Gold")),
    ("G2 1만 이상 금액을 아라비아 0 꼴로 씀(마스터 11-23 — 1만 이상은 「N만 Gold」)", re.compile(r"(?<![0-9])[0-9]{5,}\s?Gold")),
]


def text_rules(t: str) -> list[str]:
    if t == FIXED_QMARK:
        return []
    return [n for n, rx in RULES if rx.search(t)]


def jp_runs(j: str) -> list[int]:
    return [max(1, round(len(m) / 3)) for m in re.findall(r"[…・･]{2,}", j)]


def ell_rule(t: str, j: str) -> bool:
    """P10 — 우리 `…` 덩이(≥2)와 원문 점 덩이(≥2 점)의 round(n/3)(≥2) 가 같은 모양이어야."""
    ours = sorted(len(m) for m in re.findall(r"…+", t) if len(m) >= 2)
    want = sorted(x for x in jp_runs(j) if x >= 2)
    return ours != want


def order_rule(t: str, j: str) -> bool:
    """P13 — `!?`·`?!` 는 반각 두 글자, 순서는 원문 그대로(마스터 11-13 보충) — 원문에 없는 순서·원문 순서만 있는데 뒤집은 것."""
    norm = str.maketrans("！？", "!?")
    jo = set(re.findall(r"[!?]{2}", j.translate(norm)))
    return any(x in ("!?", "?!") and x not in jo and ("?!" if x == "!?" else "!?") in jo for x in re.findall(r"[!?]{2}", t))


def lost_rule(t: str, j: str) -> list[str]:
    """P14 — 원문 부호를 번역이 뺀 줄(마스터 11-13 「원문 부호는 빼지말자」): `!`·`?`·`…`(점 n→round(n/3))·명시 `～` 개수가 원문보다 적다.
    예외 — `。`·`、` 는 한국식 규칙(쉼표만 조절), 장음 `ー` 는 부호가 아니라 글자 표기라 안 센다."""
    out = []
    if t.count("!") < len(re.findall("[！!]", j)):
        out.append("!")
    if t.count("?") < len(re.findall("[？?]", j)):
        out.append("?")
    jd = sum(max(1, round(len(m) / 3)) for m in re.findall(r"[…・･]+", j) if len(m) >= 2 or "…" in m)
    if sum(len(m) for m in re.findall("…+", t)) < jd:
        out.append("…")
    if t.count("～") + t.count("~") < len(re.findall("[～〜]", j)):
        out.append("～")
    return out


def end_rule(t: str, j: str) -> bool:
    """P15 — 원문 `。` 로 끝난 쪽을 번역이 아무 종결 부호 없이 끝냄(마스터 11-13 「쉼표만 한국어에 맞게」— 마침표는 예외 아님). 쪽 수가 같을 때만(쪽을 가르는 위치가 달라지면 짝을 못 짓는다)."""
    pj = [p.strip() for p in j.split("\f") if p.strip()]
    pk = [p.strip() for p in t.split("\f") if p.strip()]
    for i, p in enumerate(pj):
        if not p.endswith("\u3002"):
            continue
        q = pk[i] if len(pj) == len(pk) else None
        if q is not None and not re.search(r"[.!?…～」』)\"'\u3002]$", q):
            return True
    return False


def name_tail_rule(t: str, j: str) -> bool:
    """N1 — 공유 이름 문자열(원문이 부호·개행 없는 짧은 낱말 — 「アグニージャ」)의 번역이 부호·공백으로 끝남. 호출한 문장마다 따라 붙어 「아그니쟈?라는」으로 읽힌다(마스터 11-23 종장 — 끝의 `?` 가 뒤 조사 훅의 받침 판정도 깨 「를」이 가나로 찍혔다)."""
    return 0 < len(j) <= 10 and not re.search(r"[\u3002\u3001\uff01\uff1f\n\f\u30fb]", j) and bool(re.search(r"[?!.,…]$", t.strip()))


def selftest() -> None:
    must = {
        "P1": "좋아..",
        "P2": "그래・・・",
        "P3": "뭐야！",
        "P4": "뭐⁉",
        "P5": "좋~아",
        "P6": "와～.",
        "P7": "뭐?.",
        "P8": "그래… … …",
        "P9": "좋다. … 응?",
        "P11": "그래….",
        "P12": "그래·",
        "G1": "7만Gold나",
        "G2": "50000 Gold를",
    }
    for k, s in must.items():
        assert any(n.startswith(k + " ") for n in text_rules(s)), f"양성 대조 실패 {k}: {s!r}"
    for ok in (
        "좋아…",
        "7만 Gold나",
        "…그랬다",
        "꼬꼬댁～!?",
        "그래, 알았어!? 응?",
        "세…리…오…스…",
        "……",
        FIXED_QMARK,
    ):
        assert not text_rules(ok), f"음성 대조 실패: {ok!r} → {text_rules(ok)}"
    dot = "\u30fb"  # 원문 점 글자(소스에 일본어를 안 둔다)
    dt = "\u30fb"
    assert lost_rule("그래", "x" + dt * 3) == ["…"] and not lost_rule("그래…", "x" + dt * 3)
    assert lost_rule("그래", "x\uff01\uff01") == ["!"] and not lost_rule("그래!!", "x\uff01\uff01")
    assert lost_rule("그래.", "x\uff1f") == ["?"] and lost_rule("으음", "x\uff5ex") == ["～"]
    assert not lost_rule("그래", "x\u3002") and not lost_rule("좋아", "x" + chr(0x30FC) + "x"), "。·ー 는 대상 아님"
    mr = "\u3002"
    assert end_rule("어서 오십시오", "x" + mr) and not end_rule("어서 오십시오.", "x" + mr) and not end_rule("어서 오십시오!", "x" + mr)
    q, e = "\uff1f", "\uff01"  # 전각 ？！
    assert order_rule("정말인가!?", "x" + q + e) and not order_rule("정말인가?!", "x" + q + e)
    assert not order_rule("뭐!?", "x" + e + q) and not order_rule("뭐!?", "x")
    assert ell_rule("딸이…", "x" + dot * 7) and not ell_rule("딸이……", "x" + dot * 7)
    assert not ell_rule("그래…", "x" + dot * 3), "3점→… 1개"
    assert ell_rule("그래……", "x" + dot * 3) and not ell_rule("…………", dot * 13)


def voice_keys() -> set[tuple[str, str]]:
    vs = json.load(open(SCRIPT / "voice_sched.json", encoding="utf-8"))["scenes"]
    return {
        (str(int(sn)), m["key"])
        for sn, s in vs.items()
        for e in (s if isinstance(s, list) else [s])
        if isinstance(e, dict)
        for m in e.get("msgs", [])
    }


def jp_map() -> dict[tuple[str, str], str]:
    out = {}
    for f in glob.glob(str(MSGS / "scn*.json")):
        d = json.load(open(f, encoding="utf-8"))
        ms = d["messages"] if "messages" in d else d
        sn = str(int(Path(f).stem[3:]))
        for m in ms.values() if isinstance(ms, dict) else ms:
            out[(sn, m["key"])] = m.get("jp", "")
    return out


def scan() -> tuple[list[str], list[str]]:
    vk, jp = voice_keys(), jp_map()
    bad, voice = [], []

    def walk(o, rel):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.startswith("_") and isinstance(v, str):
                    continue
                walk(v, rel)
        elif isinstance(o, list):
            for v in o:
                walk(v, rel)
        elif isinstance(o, str):
            for n in text_rules(o):
                bad.append(f"{n}: {rel} ⟨{o[:40]!r}⟩")

    for f in sorted(glob.glob(str(SCRIPT / "**" / "*.json"), recursive=True)):
        rel = os.path.relpath(f, SCRIPT)
        if os.path.basename(rel) in SKIP_FILES or rel.startswith("voice_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        if not rel.startswith("scn"):
            walk(d, rel)
            continue
        sn = str(int(rel[3:6]))
        for k, v in d.get("messages", {}).items():
            t = v.get("t") if isinstance(v, dict) else None
            if not isinstance(t, str):
                continue
            hit = text_rules(t)
            if sn_k := jp.get((sn, k)):
                if ell_rule(t, sn_k):
                    hit.append("P10 … 길이 ≠ round(원문 점/3)")
                if (sn, k) not in LOCKED_LOSS:
                    hit += [f"P14 원문 부호 `{x}` 를 번역이 뺌" for x in lost_rule(t, sn_k)]
                if end_rule(t, sn_k):
                    hit.append("P15 원문 마침표 쪽을 번역이 부호 없이 끝냄")
                if name_tail_rule(t, sn_k) and (sn, k) not in NAME_TAIL_OK:
                    hit.append("N1 공유 이름 문자열 끝 부호")
                if order_rule(t, sn_k):
                    hit.append("P13 !?·?! 순서가 원문과 반대")
            for n in hit:
                (voice if (sn, k) in vk else bad).append(f"{n}: scn{sn}#{k} ⟨{t[:40]!r}⟩")
    return bad, voice


def main() -> int:
    selftest()
    bad, voice = scan()
    pend = set(json.load(open(PENDING, encoding="utf-8"))) if PENDING.exists() else set()
    new_voice = [v for v in voice if v not in pend]
    if "--freeze" in sys.argv:
        json.dump(sorted(voice), open(PENDING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  음성 자막 보류 {len(voice)}건 기록")
        new_voice = []
    for r in bad + new_voice:
        print("  ✗", r)
    if "--list" in sys.argv:
        for r in voice:
            print("  (음성 보류)", r)
    print(
        f"  문장부호 전수: 위반 {len(bad)} · 새 음성 자막 위반 {len(new_voice)} · 음성 보류 {len(voice)}"
    )
    return 1 if bad or new_voice else 0


if __name__ == "__main__":
    sys.exit(main())
