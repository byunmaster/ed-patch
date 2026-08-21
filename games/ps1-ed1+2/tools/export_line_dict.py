#!/usr/bin/env python3
"""**JP 원문 → 우리 문안 사전** — 플랫폼을 옮겨도 살아남는 유일한 산출물.

**왜.** 08-18 자체 번역 전환의 근거가 이것이다(policy.md) — 배정표(`align_map`)는 씬 분할·창
구조가 달라 새턴·PCE 로 **한 줄도 안 넘어가지만**, 문장 자체는 같은 원작 대사라 그대로 쓴다.
지금 문안은 `script/<씬>.json` 에 **eid** 로 박혀 있어 그대로는 못 옮긴다 — 원문으로 키를
바꿔 두면 그때 바로 붙는다. 이 레포 안에서 이미 증명되고 있다: `rewrite_dupfill` 이 같은
키로 ED1↔ED2 를 오가며 하루에 1,200건 넘게 전파했다.

🔴 **A·B 시대 문안만 담는다**(`audit_provenance`). 「C 전환 이전」은 **정발 유래**라
(policy.md 「전환은 아직 미완」) 그걸 실으면 다음 플랫폼으로 오염을 퍼뜨린다.

⚠ **키는 JP 원문의 sha1 이다 — 평문이 아니다.** 루트 CLAUDE.md 「문장급 문안은 코드에
임베드 금지」는 팔콤 일문에도 걸린다. `textmap/*.json` 이 같은 이유로 sha1 키를 쓴다.
원문은 각 플랫폼의 `originals/` 에서 나오므로 사전에는 있을 필요가 없다.

⚠ **자리**: 지금은 게임 아래다. `shared/` 로 올리는 건 **둘째 타이틀이 실재할 때**다 —
루트 CLAUDE.md 「두 번째 소비자가 생길 때 추상화한다. 기준은 언젠가 쓸 것 같다가 아니라
지금 둘째가 있는가」. `shared/glossary` 도 ED3 스캔이라는 소비자가 생기고서 올라갔다.
그리고 공용은 `main` 에서만 고친다(게임 브랜치에서 고치면 다른 게임이 조용히 바뀐다).

  python3 tools/export_line_dict.py            # → line_dict.json (커밋 가능, sha1 키)
  python3 tools/export_line_dict.py --review   # → work/review/line_dict_plain.md (평문, 커밋 금지)
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import audit_provenance as A
from common import OUT_DIR, REVIEW_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "line_dict.json")
# 인자 센티널 — 담되 **표시**한다. 자리가 플랫폼마다 달라 그대로는 못 붙인다.
FMT = re.compile(r"[\x17\x1a\x1b]")


# 마크업·부호를 **플랫폼 중립꼴**로 되돌리는 표. 덤퍼마다 표기가 다르다 —
# PS1 은 `{c}`·`{n}`·`\x25\x73`, 새턴은 `%c`·진짜 개행·`%s`. 가운뎃점도 세 꼴이 있다.
_NEUTRAL = [
    ("{c}", "\x01"),
    ("%c", "\x01"),  # 창·색 전환
    ("{n}", ""),  # 개행 — 어차피 공백과 함께 지운다
    ("\\x25\\x73", "\x02"),
    ("%s", "\x02"),  # 이름 인자
    ("\\x25\\x64", "\x03"),
    ("%d", "\x03"),  # 수치 인자
    ("\\x21", "!"),  # 이식판이 문자로 쓰는 자리가 있다
]
_DOTS = str.maketrans({"･": "·", "・": "·", "｡": "。"})


def key(jp):
    """JP 원문 → sha1 앞 16자.

    ⚠ 공백을 지우고 잰다 — 이식판은 줄나눔이 다르다.
    🔴 **마크업 표기도 지운다**(2026-08-20). 이 사전은 「타이틀을 넘어가는 유일한 창구」인데
    (루트 `docs/patcher-checklist.md` 10-D) 키가 **PS1 덤퍼의 표기를 타고 있었다** —
    PS1 `{c}ライアス{c}{n}…` ↔ 새턴 `%cライアス%c\n…` 은 같은 원문인데 키가 달라진다.
    실측: 새턴 15,468 문자열 중 붙는 게 **1.3%** 였고, 중립화하니 **71.9%** 다
    (ED1SCN 84% · ED2SCN 91%). 사전이 있어도 못 쓰고 있었던 셈이다.

    ⚠ 인자는 **자리만 표시**하고 값은 안 담는다 — 플랫폼마다 자리가 달라 그대로는 못 붙인다.
    """
    s = jp
    for a, b in _NEUTRAL:
        s = s.replace(a, b)
    return hashlib.sha1(re.sub(r"\s+", "", s.translate(_DOTS)).encode("utf-8")).hexdigest()[:16]


def _josa(w, pair):
    """앞말 받침으로 조사를 고른다. `pair` = (받침 있을 때, 없을 때).

    ⚠ 이름이 문자열에 **박혀 있어** 조사를 정적으로 정할 수 있는 자리에서만 쓴다
    (`patch_ed2_monster_lines` 와 같은 판단). 런타임 인자 뒤면 병기를 남기거나 훅이 푼다.
    """
    c = ord(w[-1])
    has = 0xAC00 <= c <= 0xD7A3 and (c - 0xAC00) % 28
    return pair[0] if has else pair[1]


def resolve(jp, lines, names=None):
    """원문 하나를 문안으로 — 사전에 **없는 꼴**을 규칙으로 푼다.

    사전에 다 박지 않고 조회 때 푸는 이유는 **크기**다. `XとY가 현れた。` 를 전부 담으면
    이름 118 종의 곱으로 14,000 항목이 느는데, 실측으로 그게 잡는 건 새턴 ED2MON 700 중
    35 개다(5%). 규칙은 열 줄이면 되고 데이터는 안 는다.

    푸는 것 넷(2026-08-20 실측, 새턴 ED2MON 기준 52% → 57.7%):

    - **개체 구분자** `スライムＡ`·`赤スライムB'` — 이식판이 전각·반각·따옴표를 섞어 쓴다
    - **반각 카타카나** `ﾄﾞﾗｽﾄｺﾞｰｽﾄ` — NFKC 로 접어서 다시 본다
    - **`XとYが現れた。`** — 이름 둘로 쪼개 각각 찾는다
    - **ED2 전투 문안**(`textmap/battle_ed2`) — `JpMap` 이 JP 원문 키로 조회된다

    🔴 **`textmap/battle`(ED1 전투 498건)은 안 쓴다.** 재현 기준표에 「전투 문안 **정발
    전환**」이 남아 있고 `check_forbidden` 이 그 파일에서 축자 동일 12 건을 센다 — 출처가
    서기 전에 두 번째 플랫폼으로 복제하면 안 된다. 쓰면 4.6% 를 더 얻지만 그 값이 아니다.

    ⚠ 이 함수는 **`shared/` 로 갈 자리**다 — 둘째 소비자(새턴)가 실재하는 순간 옮긴다.
    지금 여기 두는 건 `shared/` 가 `main` 몫이라서다(루트 CLAUDE.md).
    """
    got = lines.get(key(jp))
    if got:
        return got["t"]
    folded = lines.get(key(unicodedata.normalize("NFKC", jp)))
    if folded:
        return folded["t"]
    m = re.match(r"^(.+?)と(.+?)が現れた。$", jp)
    if m:
        a, b = (resolve(x, lines, names) for x in m.groups())
        if a and b:
            return f"{a}{_josa(a, ('과', '와'))} {b}{_josa(b, ('이', '가'))} 나타났다."
    base = jp.rstrip("\uff21\uff22\uff23\uff24\uff25\uff26ABCDEF'")
    if base != jp:
        got = lines.get(key(base)) or lines.get(key(unicodedata.normalize("NFKC", base)))
        if got:
            return got["t"] + jp[len(base) :]
    try:
        from derive_text import jp_map

        ed2 = jp_map("battle_ed2")  # ⚠ ED1 `battle` 은 출처가 안 섰다 — 위 주석
        for cand in (jp, jp + "\n", jp.rstrip("\n")):
            if cand in ed2:
                return ed2[cand]
    except Exception:  # noqa: BLE001,S110 — 파생 표가 없어도 사전 조회는 살아 있어야 한다
        pass
    return None


def collect():
    """{sha1: {"t": 문안, "n": 블록수, "fmt": 인자 있음}} · 평문 대조표"""
    era = A.scan()
    out, plain, split = {}, {}, 0
    for path in sorted(glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        jp_path = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jp_path):
            continue
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
        with open(jp_path, encoding="utf-8") as f:
            jp = {str(e["entry_id"]): e.get("text", "") for e in json.load(f)["entries"]}
        mine = set(era.get(scn, {}).get("A 작업 중", ())) | set(
            era.get(scn, {}).get("B 자체번역", ())
        )
        for eid in mine:
            s, t = jp.get(eid, ""), (cur.get(eid) or {}).get("t")
            if not s or not t:
                continue
            k = key(s)
            if k in out and out[k]["t"] != t:
                split += 1  # 같은 원문에 두 문안 — dupfill 이 놓친 자리
                continue
            e = out.setdefault(k, {"t": t, "n": 0})
            e["n"] += 1
            if FMT.search(t):
                e["fmt"] = True
            plain.setdefault(k, (s, t))
    _add_names(out, plain)
    return out, plain, split


# 이름 뒤에 붙는 개체 구분자 — 새턴은 `スライムＡ`·`スライムB` 처럼 전각·반각을 섞어 쓴다.
_SUFFIX = "\uff21\uff22\uff23\uff24\uff25ABCDE"


def _add_names(out, plain):
    """**낱말 정본과 그 정형문**을 사전에 얹는다 — 이식판이 쓰는 층이 대사만이 아니다.

    실측(2026-08-20): PS1 대사만 담은 사전으로 새턴을 재니 `ED2MON*`(전투) 적중이 **0%**
    였다. PS1 은 전투 메시지가 SCN 이 아니라 **본체(EXE)** 에 있어 `script/` 기반 사전에
    애초에 안 담긴다. 이름 정본과 정형문을 얹으니 **52%** 가 됐고 전체가 76% → **84.1%** 다.

    🔴 **담는 것은 「우리 것이라고 증명되는 층」뿐이다.**

    - `line_dict` 본체 — A·B 시대(자체 번역)만
    - 이름 정본(`shared/glossary` · `textmap/monsters_ed2`) — **낱말 수준**이라 저작권
      대상이 아니다(루트 `CLAUDE.md`)
    - `textmap/monster_lines_ed2` — 헤더가 「우리 문안」이라고 못 박았다

    ⚠ **`{class, entries}` 꼴 textmap 여덟은 안 담는다**(`battle`·`opening`·`ending`…).
    그 층은 「정발 원본 포인터 + 우리 번역」이고 재현 기준표에 「전투 문안 **정발 전환**」이
    남아 있다 — 출처가 서기 전에는 **두 번째 플랫폼으로 복제하면 안 된다.**
    """
    names = {}
    gl = os.path.join(ROOT, "..", "..", "shared", "glossary", "eiyuu.json")
    if os.path.exists(gl):
        with open(gl, encoding="utf-8") as f:
            for tbl in json.load(f)["categories"].values():
                names.update(tbl)
    for fn in ("monsters_ed2.json", "monster_lines_ed2.json"):
        path = os.path.join(ROOT, "textmap", fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                if not k.startswith("_") and isinstance(v, str):
                    names[k] = v

    def put(jp, kr):
        k = key(jp)
        if k in out:
            return
        out[k] = {"t": kr, "n": 0, "src": "name"}
        plain.setdefault(k, (jp, kr))

    for jp, kr in names.items():
        put(jp, kr)
        for suf in _SUFFIX:
            put(jp + suf, kr + suf)
    # 정형문 — 이름이 문자열에 **박혀 있어서** 조사까지 정적으로 정해진다(`patch_ed2_monster_lines`)
    for jp, kr in names.items():
        put(f"{jp}が現れた。", f"{kr}{_josa(kr, ('이', '가'))} 나타났다.")
        put(f"{jp}との戦闘だ。", f"{kr}{_josa(kr, ('과', '와'))}의 전투다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="평문 대조표도 뜬다(커밋 금지)")
    a = ap.parse_args()

    d, plain, split = collect()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"_doc": __doc__.split("\n")[0], "lines": d}, f, ensure_ascii=False, indent=1)
    blocks = sum(e["n"] for e in d.values())
    fmt = sum(1 for e in d.values() if e.get("fmt"))
    print(f"  고유 원문 {len(d)} · 블록 {blocks} · 인자 포함 {fmt} → {os.path.relpath(OUT, ROOT)}")
    if split:
        print(f"  ⚠ 같은 원문에 두 문안 {split}건 — `check_same_jp` 로 본다")

    if a.review:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "line_dict_plain.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# JP 원문 ↔ 우리 문안 (평문) — ⚠ 커밋 금지\n\n")
            f.writelines(
                f"- `{k}`\n  - JP {s}\n  - KR {t}\n" for k, (s, t) in sorted(plain.items())
            )
        print(f"  평문 대조표 → {os.path.relpath(p, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
