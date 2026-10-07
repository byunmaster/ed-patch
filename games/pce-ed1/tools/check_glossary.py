#!/usr/bin/env python3
"""고유명사 사전 대조 — 원문에 정본 이름이 있으면 우리 문안에 **정본 표기**가 있어야 한다(라운드⑥ 닫힘 조건 「다른 표기 잔존 0」).

pc98-ed1 `check_glossary.py` 의 축(① 우리 안에서 갈림 · ③ 정본 낱말 뒤 조사)에 하나를 더한다:

    ④ 원문 대조   원문 줄에 정본 JP 이름이 있는데 우리 줄에 그 KR 표기가 없다   → 🔴 실패

④ 가 이 게임에 맞는 이유 — 원문(`work/derived/`)과 우리 문안이 **열쇠로 1:1** 이라 줄마다 맞대 볼 수 있다.
「비슷한 다른 표기」를 사전으로 추측하지 않아도 된다(실측 10-07: PS1 문안을 저본으로 옮기자 `철거인`·`다루디아`·
`쟈딘`·`데스코브라` 처럼 **PS1 이 정본과 다르게 쓴 이름**이 그대로 따라 들어왔다).

⚠ 지명은 정본이 **표 꼴(붙임)** 이고 대사는 띄운다(`docs/naming.md`) — 공백을 빼고 견준다.
⚠ 범주마다 다른 말인 JP(`カース` = 아이템 커스 / 몬스터 카스)는 어느 하나만 있어도 통과다.

    python3 games/pce-ed1/tools/check_glossary.py        # 원본 파생물이 없으면 건너뛴다
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

sys.path.insert(0, str(common.ROOT))
from shared.glossary import all_names, diff_labels

CATS = ("monster", "person", "place", "item")
HANGUL = re.compile(r"[가-힣]")


def _norm_jp(s: str) -> str:
    return s.replace("－", "ー").replace("・", "").replace("＝", "").replace("　", "")


def _norm_kr(s: str) -> str:
    return re.sub(r"\{[0-9A-F]+\}|\s|·", "", s)  # 가운뎃점 — 끊어 읽는 연출(「세·리·오·스…」)


KATA = "ァ-ヶー"


def _find(name: str, j: str) -> bool:
    """가타카나 이름은 낱말 경계에서만 — 「ロー」가 「クローラー」·「ロード」에 걸리지 않게."""
    if not re.fullmatch(f"[{KATA}]+", name):
        return name in j
    return re.search(f"(?<![{KATA}]){re.escape(name)}(?![{KATA}])", j) is not None


def canon() -> dict[str, set[str]]:
    """JP(정규화) → KR 후보(범주가 갈리면 여럿). 두 글자 미만 JP 는 뺀다(우연 일치)."""
    out: dict[str, set[str]] = {}
    for cat, jp, kr in all_names():
        if cat.split("@")[0] not in CATS or not kr:
            continue
        j = _norm_jp(jp.split("@")[0])
        if len(j) >= 2:
            out.setdefault(j, set()).add(kr)
    return out


def pairs() -> list[tuple[str, str, str]]:
    """(어디, 원문, 우리) — 전투 문구 · 시스템 메시지 · 씬 대사. 파생물이 없으면 빈 목록."""
    d = common.GAME_DIR / "work" / "derived"
    s = common.GAME_DIR / "script"
    out = []
    bm = d / "battle" / "messages.json"
    if bm.exists():
        kr = json.loads((s / "sys" / "battle.json").read_text("utf-8"))["messages"]
        for k, r in json.loads(bm.read_text("utf-8")).items():
            if k in kr:
                out.append((f"battle:{k}", r["tokens"], kr[k]))
    sm = d / "sys" / "sysmsg.json"
    if sm.exists():
        kr = json.loads((s / "sys" / "sysmsg.json").read_text("utf-8"))["messages"]
        for r in json.loads(sm.read_text("utf-8")):
            if r["key"] in kr:
                out.append((f"sysmsg:{r['addr']:04X}", r["jp"], kr[r["key"]]))
    for p in sorted((d / "messages").glob("scn*.json")) if (d / "messages").exists() else []:
        sp = s / p.name
        if not sp.exists():
            continue
        kr = json.loads(sp.read_text("utf-8")).get("messages", {})
        for r in json.loads(p.read_text("utf-8")):
            v = kr.get(r["key"])
            if v and v.get("t"):
                out.append((f"{p.stem}:{r['key']}", r["jp"], v["t"]))
    return out


def missing(rows=None, tbl=None) -> list[tuple[str, str, set[str], str]]:
    """④ — (어디, JP 이름, 정본 KR, 우리 줄)."""
    tbl = tbl if tbl is not None else canon()
    # 긴 이름부터 — 「ハイ＝アギール」 안의 「アギール」를 따로 세지 않는다
    names = sorted(tbl, key=len, reverse=True)
    out = []
    for where, jp, kr in rows if rows is not None else pairs():
        j = _norm_jp(jp)
        k = _norm_kr(kr)
        for name in names:
            if not _find(name, j):
                continue
            j = j.replace(name, "\0")
            if not any(_norm_kr(c) in k for c in tbl[name]):
                out.append((where, name, tbl[name], kr))
    return out


def ui_diff():
    """⑤ 메뉴·커맨드 라벨 ↔ 정본 `ui`(`diff_labels`). 묶음 라벨(전투 커맨드 창)은 칸마다 갈라 견준다 —
    `強さ` 는 자리마다 다른 말이라 전투 커맨드 창에선 `強さ@전투커맨드`(강함)로 묻는다(10-07: 「상태」로 나가고 있었다)."""
    d = json.loads((common.GAME_DIR / "script" / "sys" / "labels.json").read_text("utf-8"))
    mine = {}
    sep = r"\{[0-9A-F]+\}|　+"
    for jp, kr in d.get("labels", d).items():
        if jp.startswith("_") or not isinstance(kr, str):
            continue
        a = [w for w in re.split(sep, jp) if w]
        b = [w for w in re.split(sep, kr) if w]
        if len(a) != len(b):
            continue
        for x, y in zip(a, b, strict=True):
            if "戦う" in a and x == "強さ":
                x = "強さ@전투커맨드"
            mine.setdefault(x, y)
    return diff_labels(mine), len(mine)


def main() -> int:
    rows = pairs()
    if not rows:
        print("원본 파생물이 없어 건너뛴다")
        return 0
    bad = missing(rows)
    print(f"사전 대조 — 정본 이름 {len(canon()):,} · 우리 줄 {len(rows):,}")
    for where, name, want, kr in bad:
        print(f"  🔴 {where}  {name} → {'/'.join(sorted(want))}  ⟨{kr}⟩")
    (ui, unmatched), n = ui_diff()
    for jp, want, ours in ui:
        print(f"  🔴 라벨 {jp}: 정본 「{want}」 · 우리 「{ours}」")
    print(f"  라벨 {n - len(unmatched)}/{n} 견줌(나머지는 정본에 없는 이 게임 라벨)")
    print("  ✅ 다른 표기 잔존 0" if not (bad or ui) else f"  🔴 {len(bad) + len(ui)}건")
    return 1 if (bad or ui) else 0


if __name__ == "__main__":
    raise SystemExit(main())
