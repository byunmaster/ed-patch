#!/usr/bin/env python3
"""**문장부호 게이트** — 공통 번역 규칙 1-1 · 1-3 · 1-7 · 2-12 (마스터 11-13 「게임별 문장부호 한번 검토할까」).

실제로 화면에 나가는 문안(제품 대본 `script/` + 핫픽스 덮개 `hotfix/script/` 를 겹친 것 · 텍스트맵 `ours`)을 센다.
전부 **0 이어야 한다**(기준선 없음).

 ① 전각 `！？，．。、` · `‼⁉⁈⁇`      — 1-1: `! ? . ,` 는 반각, `!?` 는 반각 두 글자
 ② `...` · `・･·`(일본식 점)          — 1-3: `…` 한 글자(n 점 → round(n/3))
 ③ 띄운 `… …` · `. . .`              — 원문 「· · ·」(띄운 점 셋)은 점 하나 묶음 — `…` 하나로
 ④ `～～` · `~~` · `～.` · `~.`        — 1-7: 물결표는 하나, 뒤에 마침표 없음
 ⑤ (없음) `!?`·`?!` 순서는 **원문 그대로**라 기계로 못 가른다 — 반각 두 글자이기만 하면 된다(관리자 11-13)
 ⑥ `?.` `!.` `?,` `!,`                 — 부호 겹침(`??` · `!!` 은 원문대로)
 ⑦ `[?!]…` 순서                        — 2-12: `…?` · `…!` · `…!?`
 ⑨ 번역 부호 수 < 원문(`？`·`！`·`～`·말줄임) — 원문 부호를 번역이 뺀 블록(마스터 11-13 「원문 부호는 빼지말자」)
 ⑧ `.…`(마침표 뒤 말줄임)                — 점 수대로 `…` 로(새턴 ED1SCN11 선례, 11-13)

ASCII `~` 하나는 **위반이 아니다** — 인코더(`encode_ext`)가 전각 ～(U+FF5E)로 낸다(반각 0x7E 는 오버라인이라 안 쓴다).
엔딩 문자열 앞의 `~` 도 같다(출력은 전각 ～).

  python3 tools/check_punct_marks.py             # 위반이 있으면 종료 코드 1
  python3 tools/check_punct_marks.py --selftest  # 양성·음성 대조
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# 마스터 판정으로 일본식 점 규칙을 건너뛰는 블록(좌표 → 사유) — 원문 「な・か・ま」의 가운뎃점을 전각 「・」로 살린다.
EXCEPT = {"ED2SCN3:775": "마스터 11-14 동・료 판정(전각 ・)"}

RULES = {
    "1-1 전각 ！？，．。、‼⁉": re.compile(r"[！？，．。、‼⁉⁈⁇]"),
    "1-3 점 `...`·일본식 점": re.compile(r"\.{2,}|[・･·]"),
    "1-3 띄운 말줄임 `… …`·`. . .`": re.compile(r"…[ 　]+…|\.( \.){2,}"),
    "1-7 물결표 겹침·뒤 온점": re.compile(r"[~～]{2,}|[~～][.。]"),
    "부호 겹침 `?.` `!.` `?,` `!,`": re.compile(r"[?!][.,]"),
    "2-12 `?!…` 순서": re.compile(r"[?!]+…"),
    "마침표 뒤 말줄임 `.…`": re.compile(r"\.…"),
}


def scan_text(t):
    return [name for name, rx in RULES.items() if rx.search(t)]


def _walk_ours(o, path, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "ours" and isinstance(v, str):
                out.append((path + "/ours", v))
            else:
                _walk_ours(v, path + "/" + str(k), out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk_ours(v, path + "/" + str(i), out)


def corpus():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "script", "*.json"))):
        scn = os.path.basename(f)[:-5]
        base = json.load(open(f))
        hp = os.path.join(ROOT, "hotfix", "script", scn + ".json")
        hot = json.load(open(hp)) if os.path.exists(hp) else {}
        for k, v in base.items():
            if isinstance(v, dict) and "t" in v:
                e = hot.get(k)
                t = e["t"] if isinstance(e, dict) and "t" in e else v["t"]
                rows.append((f"{scn}:{k}", t))
    for f in sorted(glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        out = []
        _walk_ours(json.load(open(f)), "", out)
        rows += [(os.path.basename(f) + p, s) for p, s in out]
    return rows


# ── ⑨ 번역 부호 수 < 원문 경보(마스터 11-13 「원문 부호는 빼지말자」) ───────────────────────────
# 원문(JP 원판)에 있는 `？`·`！`·`～`·말줄임(점 n → `…` round(n/3))을 번역이 뺀 블록을 잡는다.
#  · `ー`(장음)는 부호가 아니라 글자 표기 — 셈 밖(우리 `～` 가 원문 `～`+`ー` 보다 많으면 안 된다는 상한은 별개).
#  · 범위 `～`(숫자 ～ 숫자)는 한국어 표기(`60000~100000`)대로라 셈 밖. `。`·`、` 는 한국어 규칙(2-13)이라 셈 밖.
#  · 한글이 없는 블록(이름 플레이트·깨진 원문)은 셈 밖.
def _jp_marks(jp):
    q = jp.count("？") + jp.count("?")
    x = jp.count("！") + jp.count("!")
    til = len(re.findall(r"[～〜]", re.sub(r"[0-9０-９] ?[～〜] ?[0-9０-９]", "", jp)))
    ell = 0
    for m in re.finditer(r"[･…](?: ?[･…])*|・{2,}", jp):
        n = sum(3 if ch == "…" else 1 for ch in m.group(0) if ch in "･・…")
        ell += max(1, round(n / 3))
    return q, x, til, ell


def _kr_marks(t):
    return t.count("?"), t.count("!"), len(re.findall(r"[~～]", t)), t.count("…")


def orig_alarms():
    """[(좌표, 이름, 원문 수, 번역 수)] — 원본이 없으면 None(안 쟀다)."""
    try:
        os.environ.setdefault("LOCK_BYPASS", "1")
        from check_window_nl import SCN_COUNT, raws_of
    except Exception:
        return None
    out = []
    for game in ("ED1", "ED2"):
        for n in range(1, SCN_COUNT[game] + 1):
            scn = f"{game}SCN{n}"
            base = json.load(open(os.path.join(ROOT, "script", scn + ".json")))
            hp = os.path.join(ROOT, "hotfix", "script", scn + ".json")
            hot = json.load(open(hp)) if os.path.exists(hp) else {}
            raws = raws_of(scn)
            for k, v in base.items():
                if not isinstance(v, dict) or "t" not in v or not k.isdigit():
                    continue
                raw = raws.get(int(k))
                e = hot.get(k)
                t = e["t"] if isinstance(e, dict) and "t" in e else v["t"]
                if raw is None or len(re.findall(r"[가-힣]", t)) < 2:
                    continue
                jp = raw.decode("cp932", errors="replace")
                if any(c in jp for c in "\x14\x17\x1f\x18"):  # 깨진 원문(이름 플레이트 조각)
                    continue
                if f"{scn}:{k}" in EXCEPT:
                    continue
                for name, a, b in zip(("？", "！", "～", "…"), _jp_marks(jp), _kr_marks(t)):
                    if b < a:
                        out.append((f"{scn}:{k}", name, a, b))
    return out


def selftest():
    bad = ["뭐라！", "뭐야？", "그래。", "그래...", "그래・・・", "그래… … …", "고마워～～", "고마워~~", "불렀어～.", "응?. 뭐", "응?!…", "네.… 그래"]
    good = ["뭐라!?", "그래…", "고마워～", "고마워~ 응", "와!! 정말??", "…?", "…!?", "응?! 뭐", "3.5 Gold", "…그랬어."]
    for s in bad:
        assert scan_text(s), f"양성 대조 실패(못 잡음): {s}"
    for s in good:
        assert not scan_text(s), f"음성 대조 실패(오탐): {s} {scan_text(s)}"
    # ⑨ 양성·음성 대조
    assert _jp_marks("やあ ･ ･ ･ 元気？") == (1, 0, 0, 1) and _jp_marks("60000 ～ 100000") == (0, 0, 0, 0)
    assert _jp_marks("･ ･ ･ ･ ･ ･ ･") == (0, 0, 0, 2) and _jp_marks("ウルフ・ビル") == (0, 0, 0, 0)
    assert _kr_marks("응…?") == (1, 0, 0, 1)
    print("  selftest ok — 양성 %d · 음성 %d · 원문 부호 셈 3" % (len(bad), len(good)))


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0
    selftest()
    rows = corpus()
    fails = [(k, t, scan_text(t)) for k, t in rows if k not in EXCEPT]
    fails = [x for x in fails if x[2]]
    print(f"문장부호 검사 [ps1-ed1+2] — {len(rows)}건(핫픽스 덮개 적용) · 위반 {len(fails)}")
    for k, t, names in fails[:30]:
        print("  ❌", k, "·".join(names), repr(t)[:70])
    al = orig_alarms()
    if al is None:
        print("  ⚠ 원문 부호 대조: 원본이 없어 안 쟀다")
    else:
        print(f"  원문 부호 대조(번역 < 원문): {len(al)}건")
        for k, nm, a, b in al[:30]:
            print(f"  ❌ {k} `{nm}` 원문 {a} > 번역 {b}")
        fails += al
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
