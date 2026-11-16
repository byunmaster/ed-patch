"""공통 번역 규칙 2-18 — 빈 줄 개행 금지 (게이트).

    python3 games/ss-ed3/tools/check_blank_lines.py

창은 첫 줄부터 쓴다. 문안 값에 ① 빈 첫 줄(공백뿐인 줄 포함) ② 연속 개행(`\\n\\n` — 공백뿐인 줄 포함) ③ 빈 끝 줄
(개행 뒤 아무것도 없는 꼴은 원문 종결이라 제외)이 있으면 실패한다.
면제: 원판 동일 문단 빈 줄 5블록(`EXEMPT`, 마스터 11-09 판정 「오프닝 엔딩 빈 줄은 건드리지마. 빈줄제거는 대사창 한정」).
대상: `script/**/*.json` 전부의 문자열 값(`_` 로 시작하는 메타 키 제외).
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")

# 면제 — 엔딩·나레이션 두루마리의 문단 사이 빈 줄 5블록. **원판과 같은 꼴**(원문도 빈 줄)이라 화면 모양이 바뀌므로
# 마스터 11-09 판정: 「오프닝 엔딩 빈 줄은 건드리지마. 빈줄제거는 대사창 한정이야」 — 그대로 둔다(규칙 2-18 은 대사창 한정).
EXEMPT = {
    "MAP061.json#82", "MAP061.json#83", "MAP061.json#120", "MAP072.json#337", "MAP084.json#472",
}  # fmt: skip


def walk(o, path):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            if not str(k).startswith("_"):
                yield from walk(v, f"{path}#{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")


def bad(v):
    lines = v.split("\n")
    if len(lines) < 2:
        return None
    if lines[0].strip(" 　") == "":
        return "빈 첫 줄"
    if any(ln.strip(" 　") == "" for ln in lines[1:-1]):
        return "연속 개행(빈 줄)"
    return None


def main():
    fails = []
    n = 0
    exempt_seen = set()
    for f in sorted(glob.glob(os.path.join(SCRIPT_DIR, "**", "*.json"), recursive=True)):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        rel = os.path.relpath(f, SCRIPT_DIR)
        for p, v in walk(d, rel):
            n += 1
            if p in EXEMPT:
                exempt_seen.add(p)
                continue
            why = bad(v)
            if why:
                fails.append(f"{p}: {why} — {v[:30]!r}")
    for x in fails:
        print("✗", x)
    for gone in sorted(EXEMPT - exempt_seen):
        fails.append(f"{gone}: 면제 목록에 있는데 그 자리가 없다(목록을 고친다)")
        print("✗", fails[-1])
    print(f"빈 줄 개행 검사 {n}건 중 어긋남 {len(fails)} (원판 동일 면제 {len(exempt_seen)} — 마스터 판정: 엔딩·나레이션은 유지)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
