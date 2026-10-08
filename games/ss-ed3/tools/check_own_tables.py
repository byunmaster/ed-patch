"""게임 폴더에 **자기 JP→KR 표**가 남았나 — 마스터 10-08 「이번 라운드에 모든 워커는 자기사전을 들고 있으면 안돼」.

    python3 games/ss-ed3/tools/check_own_tables.py

고유명사·라벨·호칭·지명·아이템·몬스터의 JP→KR 표는 공용 사전(`shared/canon/nouns/`)·정본(`shared/canon/`)이 갖는다. 게임 폴더가 가진 표가
가나·한자 열쇠에 한글 값을 짝짓고 있으면 실패한다(JSON 은 사전식 객체, 코드는 사전 리터럴 — `ast` 로 본다).

보는 곳: `games/ss-ed3/` 의 `*.json` · `tools/*.py` (`work/` · `docs/` · `tools/tests/` 는 뺀다).
예외(사유를 여기 적는다 — 늘릴 때마다 「이게 사전·정본에 있어야 하나」를 묻는다):
  · `tools/kana_kr.py` — 가타카나 **음절 → 한글** 후보 표(`ア`→아). 이름 표가 아니라 사전 후보를 만드는 도구의 음차 규칙이다.
  · 스태프롤 — 게임마다 제작진이 달라 게임 폴더에 둔다(마스터 10-08). 이 게임은 자막 시계 JSON(`voice_credits.json`)이라 열쇠가 JP 가 아니다.
"""

import ast
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

JP = re.compile(r"[぀-ヿ一-鿿]")
KO = re.compile(r"[가-힣]")
ALLOW = {
    "tools/kana_kr.py": "가타카나 음절 → 한글 음차 규칙(사전 후보 생성기) — 이름 표가 아니다",
}


def _json_hits(o, path=""):
    if isinstance(o, dict):
        n = sum(1 for k, v in o.items() if isinstance(k, str) and JP.search(k) and isinstance(v, str) and KO.search(v))
        if n:
            yield path or "/", n
        for k, v in o.items():
            yield from _json_hits(v, f"{path}/{str(k)[:24]}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _json_hits(v, f"{path}[{i}]")


def _py_hits(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            n = sum(
                1
                for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant)
                and isinstance(k.value, str)
                and JP.search(k.value)
                and isinstance(v, ast.Constant)
                and isinstance(v.value, str)
                and KO.search(v.value)
            )
            if n:
                yield node.lineno, n


def main():
    root = C.GAME_DIR
    bad = []
    for p in sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True)):
        rel = os.path.relpath(p, root)
        if rel.startswith(("work" + os.sep, "docs" + os.sep)):
            continue
        with open(p, encoding="utf-8") as f:
            try:
                doc = json.load(f)
            except ValueError:
                continue
        for where, n in _json_hits(doc):
            bad.append((rel, where, n))
    for p in sorted(glob.glob(os.path.join(root, "tools", "**", "*.py"), recursive=True)):
        rel = os.path.relpath(p, root)
        if rel in ALLOW or rel.startswith(os.path.join("tools", "tests") + os.sep):
            continue  # 테스트는 음차 규칙·검사기 입력의 가짜 표본을 든다
        with open(p, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        for line, n in _py_hits(tree):
            bad.append((rel, f"L{line}", n))
    if bad:
        for rel, where, n in bad:
            print(f"  ❌ {rel} {where} — 가나/한자 열쇠 → 한글 값 {n}쌍")
        print(f"\n🔴 게임 폴더에 자기 표 {len(bad)} 곳 — 사전(`shared/canon/nouns`)·정본(`shared/canon`)에서 읽게 한다(없으면 관리자에게 후보로)")
        return 1
    print(f"✅ 자기 표 0 (예외 {len(ALLOW)}: {', '.join(ALLOW)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
