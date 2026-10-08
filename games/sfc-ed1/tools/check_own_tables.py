#!/usr/bin/env python3
"""「자기 표 0」 검사 — 게임 폴더에 가나/한자 열쇠 → 한글 값 표가 남았나(마스터 2026-10-08 「모든 워커는 자기 사전을 들고 있으면 안 된다」).

세는 것: ① `textmap/*.json` 에서 **원문(JP) 열쇠 옆에 한글 값이 박힌 칸** — 사전·정본에서 읽을 수 있는 건 빌드가 `namesrc` 로 읽으니 JSON 엔 열쇠만
남아야 한다 ② `tools/*.py` 안의 **가나/한자 열쇠 → 한글 값 리터럴**.
정본에 없는 값(줄인 꼴·이 기종만의 말)은 **관리자에게 후보로** 올리고 main 정본에 오르면 `namesrc.py --strip` 이 걷는다 — 그때까지의 수는 천장
(`own_tables_baseline.json`)으로 눌러 두어 **늘 수는 없다**(줄어들기만). 목표는 0.

예외(사유가 있다 — 마스터 10-08):
· **스태프롤**(`credits.json`): 게임마다 제작진이 달라 게임이 들고 있는 게 맞다(열쇠도 JP 가 아니다).
· **번역 문안 자체**(`segments.json` 대본 조각 · 사전 D5 시스템 문장 · `dict.json` 의 `kind: script` — 대사 속 호칭·일반 낱말·지명 접미 조각): 이 기종 원문에서 우리가 옮긴 **문안**이지 이름·라벨 표가 아니다.

  python3 tools/check_own_tables.py              # 천장보다 늘었으면 종료코드 1
  python3 tools/check_own_tables.py --list       # 남은 칸 전부(후보 표)
  python3 tools/check_own_tables.py --freeze     # 천장을 지금 값으로 내린다(줄었을 때만)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common
import namesrc

BASE = common.GAME_DIR / "own_tables_baseline.json"
JP = r"[぀-ヿ一-鿿]"
HANGUL = r"[가-힣]"


def json_rows() -> list[tuple[str, str, str, str]]:
    """(출처, 열쇠, 원문, 한글 값) — 사전·정본에서 읽을 수 있는 칸은 이미 걷혀 있어야 한다(읽을 수 있는데 남은 칸도 여기 잡힌다)."""
    rows = []
    tdir = common.GAME_DIR / "textmap"
    d = json.loads((tdir / "dict.json").read_text(encoding="utf-8"))
    rom = common.rom_bytes()
    for code in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4):  # D5 = 시스템 문장(번역 문안) — 예외
        for i, b in enumerate(text.dict_entries(code, rom)):
            k = f"{code:02X}:{i:02X}"
            if d.get(k, {}).get("kr") and d[k].get("kind") != "script":  # script = 대사 번역 문안 낱말(사전 D0·D1 조각) — 이름 표가 아니다(관리자 10-08)
                rows.append(("dict", k, text.decode(b).strip(), d[k]["kr"]))
    p = json.loads((tdir / "places.json").read_text(encoding="utf-8"))["names"]
    rows += [("places", jp, jp, kr) for jp, kr in p.items() if kr]
    b = json.loads((tdir / "battle_ui.json").read_text(encoding="utf-8"))
    rows += [("battle_ui", x["jp"], x["jp"], x["kr"]) for x in namesrc._battle_rows(b) if x.get("kr")]
    rows += [("battle_ui", x["jp"], x["jp"], x["kr"]) for x in b.get("names", []) if x.get("kr")]
    for k, v in json.loads((tdir / "menus.json").read_text(encoding="utf-8")).items():
        if v.get("kr"):
            rows.append(("menus", k, k.split("@")[0], v["kr"]))
    for t in json.loads((tdir / "chapters.json").read_text(encoding="utf-8"))["titles"]:
        if t.get("kr"):
            rows.append(("chapters", t["jp"], t["jp"], t["kr"]))
    return rows


def code_literals() -> list[str]:
    """`tools/*.py` 의 가나/한자 열쇠 → 한글 값 리터럴(딕셔너리 항목·튜플 쌍)."""
    pat = re.compile(rf'["\']{JP}[^"\']*["\']\s*[:,]\s*\(?\s*["\'][^"\']*{HANGUL}')
    out = []
    for f in sorted((common.GAME_DIR / "tools").glob("*.py")):
        if f.name in ("check_own_tables.py",):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pat.search(line):
                out.append(f"{f.name}:{n}: {line.strip()[:90]}")
    return out


def main() -> int:
    rows, lits = json_rows(), code_literals()
    cur = {"json": len(rows), "code": len(lits)}
    if "--list" in sys.argv:
        for r in rows:
            print("\t".join(r))
        for x in lits:
            print("code\t" + x)
        return 0
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.exists() else {"json": 10**9, "code": 0}
    if "--freeze" in sys.argv:
        if cur["json"] > base["json"] or cur["code"] > base["code"]:
            print("천장보다 늘었다 — 동결 거부")
            return 1
        BASE.write_text(json.dumps(cur, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"천장 갱신: {cur}")
        return 0
    by = {}
    for r in rows:
        by[r[0]] = by.get(r[0], 0) + 1
    print(f"자기 표: JSON {cur['json']}칸 {by} · 코드 리터럴 {cur['code']}줄 (천장 {base['json']}/{base['code']}, 목표 0)")
    bad = cur["json"] > base["json"] or cur["code"] > base["code"]
    if bad:
        print("🔴 자기 표가 늘었다 — 정본에서 읽거나(namesrc) 관리자에게 후보로 올린다")
        for x in lits:
            print("   ", x)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
