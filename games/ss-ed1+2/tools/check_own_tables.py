"""**자기 표 0** — 게임 폴더에 JP→KR 표(가나·한자 열쇠 표)가 남았나.

    python3 tools/check_own_tables.py

🔴 마스터 2026-10-08 「이번 라운드에 모든 워커는 자기사전을 들고 있으면 안 돼」. 고유명사·라벨·호칭·지명·아이템·몬스터의
   JP→KR 은 전부 `shared/canon`(고유명사 `nouns/` + 공통 문안)에서 읽는다. 게임 폴더엔 **자리·구조·규칙**만 둔다.

## 무엇을 표로 치나 (전부 실패)

  ① 파이썬 `dict` 리터럴의 **JP(가나·한자) 문자열 열쇠**
  ② 파이썬 `[(JP, KR), …]` 꼴 — 앞 둘이 문자열이고 앞이 JP·뒤가 한글인 튜플/리스트가 3개 이상
  ③ JSON 의 **JP 열쇠** · `[JP, KR]` 짝이 3개 이상인 배열

## 무엇을 안 치나 — 사유가 있는 예외만(여기에 적는다)

  - `names_exceptions.json` · `canon_exceptions.json` — 표가 아니라 **마스터 승인 기록**이다(승인은 마스터만 채운다).
  - **스태프롤**(`script/title.json`) — 마스터 2026-10-08 「제작진은 게임마다 다르니 게임마다 가지고 있는 게 맞다」.
    ⚠ 지금 그 파일은 **KR 줄만** 담아(JP 열쇠 없음) 어차피 걸리지 않는다 — 나중에 JP 를 곁들여도 이 예외로 통과한다.
  - 한 글자·조각 상수(정규식·반각 판별 등)는 표가 아니다 — 위 세 꼴만 본다.

⚠ 안 걸리는 꼴로 표를 숨기면(예: `zip(JP목록, KR목록)`) 이 검사는 못 잡는다 — 검사기의 한계다. 코드 리뷰가 메운다.
"""

import ast
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)

_JP = re.compile(r"[ぁ-ゟ゠-ヿ一-鿿ｦ-ﾟ]")
_KO = re.compile(r"[가-힣]")

# 표가 아닌 파일 — 사유는 위 머리말.
EXEMPT_FILES = {"names_exceptions.json", "canon_exceptions.json", os.path.join("script", "title.json")}


def _is_str(n):
    return isinstance(n, ast.Constant) and isinstance(n.value, str)


def py_tables(path):
    found = []
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            ks = [k.value for k in n.keys if _is_str(k) and _JP.search(k.value)]
            if ks:
                found.append((n.lineno, f"dict JP 열쇠 {len(ks)}개 (예 {ks[0]!r})"))
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            pairs = [
                e
                for e in n.elts
                if isinstance(e, (ast.Tuple, ast.List))
                and len(e.elts) >= 2
                and _is_str(e.elts[0])
                and _is_str(e.elts[1])
                and _JP.search(e.elts[0].value)
                and _KO.search(e.elts[1].value)
            ]
            if len(pairs) >= 3:
                found.append((n.lineno, f"(JP, KR) 짝 {len(pairs)}개 (예 {pairs[0].elts[0].value!r})"))
    return found


def json_tables(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    found = []

    def walk(x, where):
        if isinstance(x, dict):
            ks = [k for k in x if isinstance(k, str) and not k.startswith("_") and _JP.search(k)]
            if ks:
                found.append((where, f"JP 열쇠 {len(ks)}개 (예 {ks[0]!r})"))
            for k, v in x.items():
                walk(v, f"{where}/{k}")
        elif isinstance(x, list):
            pairs = [
                e
                for e in x
                if isinstance(e, list)
                and len(e) >= 2
                and isinstance(e[0], str)
                and isinstance(e[1], str)
                and _JP.search(e[0])
                and _KO.search(e[1])
            ]
            if len(pairs) >= 3:
                found.append((where, f"[JP, KR] 짝 {len(pairs)}개 (예 {pairs[0][0]!r})"))
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")

    walk(data, "")
    return found


def scan():
    bad = []
    for p in sorted(glob.glob(os.path.join(GAME, "**", "*.py"), recursive=True)):
        rel = os.path.relpath(p, GAME)
        if rel.startswith("work" + os.sep) or os.sep + "tests" + os.sep in os.sep + rel:
            continue
        for ln, what in py_tables(p):
            bad.append((rel, ln, what))
    for p in sorted(glob.glob(os.path.join(GAME, "**", "*.json"), recursive=True)):
        rel = os.path.relpath(p, GAME)
        if rel.startswith("work" + os.sep) or rel in EXEMPT_FILES:
            continue
        for where, what in json_tables(p):
            bad.append((rel, where, what))
    return bad


def main():
    bad = scan()
    if bad:
        for rel, where, what in bad[:30]:
            print(f"     🔴 {rel} {where}: {what}")
        print(f"  ❌ 자기 표 {len(bad)}곳 — 정본(`shared/canon`)에서 읽게 옮긴다(후보는 관리자에게)")
        return 1
    print("  ✅ 자기 표 0 — 게임 폴더에 JP→KR 표가 없다 (예외: 마스터 승인 기록 · 스태프롤)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
