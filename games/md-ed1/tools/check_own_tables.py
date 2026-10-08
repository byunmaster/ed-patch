"""자기 표 0 검사 — 게임 폴더에 **JP→KR 표**(고유명사·라벨·호칭·지명·아이템·몬스터)가 남으면 실패한다.

    python3 tools/check_own_tables.py

마스터 2026-10-08 「모든 워커는 자기사전을 들고 있으면 안 돼」 — 이름·라벨은 정본(`shared/canon`)
에서만 읽는다. 게임 폴더에는 **원문(JP)만 든 목록**(칸 배치·열쇠)과 **우리 문장 정본**(번역 문장은 자체 번역이라 둔다)이 있어도 된다.

잡는 꼴 둘:
  ① JSON — 가나/한자가 든 **열쇠**가 한글이 든 값(또는 `ours` 가 한글인 객체)을 가리키는 사전꼴 (`{"呪文": "주문"}` ·
     `{"呪文": {"ours": "주문"}}`). 문장 정본(`script/*.json` 등)은 열쇠가 주소·번호라 안 걸린다.
  ② 파이썬 — 사전 리터럴(JP 열쇠 → 한글 값) · 튜플 목록(JP 와 한글이 함께 든 튜플 셋↑).

예외(사유를 여기 적는다):
  - `PENDING`(`dict_names.py`) — **정본·사전에 올릴 후보 대기** 임시 목록. 관리자가 main 정본에 올리면 비운다 — 남은 수를 알리고,
    비면 이 예외가 필요 없어진다.
  - 스태프롤(제작진) 이름 표 — 게임마다 제작진이 달라 게임 폴더에 두는 게 맞다(마스터 2026-10-08). md 에는 아직 없다 — 생기면
    `STAFFROLL` 에 파일을 적는다.
"""

import ast
import json
import re
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
JP = re.compile(r"[぀-ヿ㐀-鿿]")
KR = re.compile(r"[가-힣]")
STAFFROLL: set[str] = set()  # 스태프롤 이름 표 파일(게임 폴더 기준 상대경로) — 지금 없음
SKIP_DIRS = {"work", "docs", "__pycache__", "tests"}
# 마스터 승인 예외 대장 — 「자리|정본 열쇠 → 사유」 라 사전이 아니다(열쇠가 자리 이름이고 값은 한국어 사유 문장)
EXC_FILES = {"canon_exceptions.json", "names_exceptions.json"}


def _files(suffix: str):
    for p in sorted(GAME.rglob(f"*{suffix}")):
        rel = p.relative_to(GAME)
        if SKIP_DIRS & set(rel.parts) or str(rel) in STAFFROLL or rel.name in EXC_FILES:
            continue
        yield p, str(rel)


def _has_kr(v) -> bool:
    if isinstance(v, str):
        return bool(KR.search(v))
    if isinstance(v, dict):
        return any(_has_kr(x) for x in v.values())
    return False


def json_tables(o, path="") -> list[str]:
    out = []
    if isinstance(o, dict):
        hits = [k for k, v in o.items() if isinstance(k, str) and JP.search(k) and _has_kr(v)]
        if hits:
            out.append(f"{path or '/'} — JP 열쇠 {len(hits)}개가 한글 값을 가리킨다 (예: {hits[0]!r})")
        for k, v in o.items():
            out += json_tables(v, f"{path}/{str(k)[:16]}")
    elif isinstance(o, list):
        for i, v in enumerate(o[:200]):
            out += json_tables(v, f"{path}[{i}]")
    return out


def _strs(n):
    return [c.value for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)]


def py_tables(path: Path, rel: str) -> tuple[list[str], int]:
    """(발견, 예외로 센 PENDING 항목 수)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    pending = 0
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PENDING" for t in n.targets)
            and isinstance(n.value, ast.Dict)
        ):
            skip.add(id(n.value))
            pending = len(n.value.keys)
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict) and id(n) not in skip:
            ks = [
                k for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str) and JP.search(k.value)
            ]
            if ks and any(KR.search(s) for v in n.values for s in _strs(v)):
                out.append(f"{rel}:{n.lineno} — 사전 리터럴 (JP 열쇠 {len(ks)}개 → 한글 값)")
        elif isinstance(n, (ast.List, ast.Tuple)) and len(n.elts) >= 3:
            both = [
                s
                for s in (_strs(e) for e in n.elts if isinstance(e, ast.Tuple))
                if any(JP.search(x) for x in s) and any(KR.search(x) for x in s)
            ]
            if len(both) >= 3:
                out.append(f"{rel}:{n.lineno} — 튜플 목록 ({len(both)}개에 JP 와 한글이 함께 든다)")
    return out, pending


def main() -> None:
    bad: list[str] = []
    for p, rel in _files(".json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        bad += [f"{rel}: {m}" for m in json_tables(d)]
    pending = 0
    for p, rel in _files(".py"):
        found, n = py_tables(p, rel)
        bad += found
        pending += n
    note = f" · 정본 후보 대기(PENDING) {pending}건" if pending else ""
    print(f"  자기 표 — 걸린 곳 {len(bad)}{note}")
    if pending:
        print("    ⚠ PENDING 은 관리자가 정본·사전에 올리면 비운다(`dict_names.py`)")
    if bad:
        raise SystemExit("\n".join("    " + b for b in bad))


if __name__ == "__main__":
    main()
