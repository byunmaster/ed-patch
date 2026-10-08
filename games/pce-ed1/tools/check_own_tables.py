"""「자기 표 0」 — 게임 폴더에 일본어 열쇠 → 한글 값 표가 새로 생기지 않았나(마스터 10-08 「모든 워커는 자기사전을 들고 있으면 안돼」).

고유명사·라벨·호칭·지명·아이템·몬스터는 정본(`shared/canon` — 고유명사 nouns·공통 문안)에서 읽는다. 이 검사는 게임 폴더의 둘을 본다:
  · JSON — `script/`·루트의 파일에서 **일본어 글자가 든 열쇠**(번역 문안은 열쇠가 해시·주소라 안 걸린다)
  · 파이썬 — `tools/*.py` 의 dict 리터럴(일본어 열쇠 → 한글 값) · 쌍(일본어 문자열, 한글 문자열) · 호출 인자(일본어, 한글 폴백)
**정본에 아직 없는 값**은 관리자에게 후보로 올렸고(coverage-1008) 정본에 올라오기까지 `PENDING` 에 둔다 — 올라오면 그 줄과 표 항목을 같이 지운다.
`PENDING` 밖의 것이 보이면 실패다(새 자기 표).

예외(마스터 10-08): **스태프롤 이름 표는 게임마다 제작진이 달라 게임 폴더에 둔다** — `tools/staffroll.py` 는 통째로 뺀다.
"""

import ast
import json
import re
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
JP = re.compile("[ぁ-ヺー-ヿ㐀-鿿ｦ-ﾟ]")
KO = re.compile("[가-힣]")
EXEMPT_FILES = {"staffroll.py"}  # 스태프롤 — 제작진 표는 게임별(위 예외)

# 정본 후보로 관리자에게 올린 값 — (파일, 일본어 열쇠). 정본에 올라오면 읽는 쪽으로 바꾸고 여기서 지운다. (지금은 비었다 — 자기 표 0)
PENDING: set[tuple[str, str]] = set()


def _json_keys(f: Path):
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and JP.search(k):
                    yield k
                yield from walk(v)

    try:
        yield from walk(json.loads(f.read_text("utf-8")))
    except ValueError:
        return


def _py_keys(f: Path):
    for n in ast.walk(ast.parse(f.read_text("utf-8"))):
        if isinstance(n, ast.Dict):
            if any(
                isinstance(v, ast.Constant) and isinstance(v.value, str) and KO.search(v.value)
                for v in n.values
            ):
                for k in n.keys:
                    if (
                        isinstance(k, ast.Constant)
                        and isinstance(k.value, str)
                        and JP.search(k.value)
                    ):
                        yield k.value
        elif isinstance(n, (ast.Tuple, ast.List, ast.Call)):
            els = n.elts if not isinstance(n, ast.Call) else n.args
            strs = [
                e.value for e in els if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if any(KO.search(x) for x in strs):
                yield from (
                    x for x in strs if JP.search(x) and "→" not in x
                )  # 「→」 가 든 건 패치 이름표(라벨)지 표가 아니다


def found():
    out = []
    for f in sorted([*GAME.glob("script/**/*.json"), *GAME.glob("*.json")]):
        out += [(f.relative_to(GAME).as_posix(), k) for k in _json_keys(f)]
    for f in sorted(GAME.glob("tools/*.py")):
        if f.name in EXEMPT_FILES or f.name.startswith("test_"):
            continue
        out += [(f.relative_to(GAME).as_posix(), k) for k in _py_keys(f)]
    return out


def main() -> int:
    got = set(found())
    new = sorted(got - PENDING)
    stale = sorted(PENDING - got)
    print(
        f"자기 표 [pce-ed1] — 일본어 열쇠 표 항목 {len(got)}개 (정본 후보로 올림 {len(got & PENDING)}) · 새 자기 표 {len(new)}"
    )
    for f, k in new:
        print(f"  ✗ {f}: {k!r} — 사전·정본에서 읽는다(없으면 관리자에게 후보로)", file=sys.stderr)
    for f, k in stale:
        print(f"  ⚠ PENDING 에 남은 줄이 코드에 없다 — 지운다: {f} {k!r}", file=sys.stderr)
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
