"""번역 규칙 2-11 — 「…」 뒤에 말이 이어지면 반각 공백을 띄운다(그대도… 잊었다 ✓ · 그대도…잊었다 ✗). 줄 끝·닫는 부호·태그 앞은 띄우지 않는다.

python3 tools/check_ellipsis.py          # 위반 목록(있으면 실패)
python3 tools/check_ellipsis.py --fix    # 정본(script·textmap)의 `ours` 를 고친다
"""

import json
import re
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
CAND = re.compile(r"…(?=[가-힣A-Za-z0-9])")


def _stutter(s: str, i: int) -> bool:
    """예외(마스터 10-12 「세…리…오…스… 이런건 붙여쓰는게 맞을듯」): 한 낱말을 음절마다 끊어 말하는 꼴은 「…」 뒤를 붙인다 —
    「…」 바로 앞이 **홀로 선 한 음절**(그 앞이 한글이 아니다)이면 말더듬 꼴로 본다."""
    return i >= 1 and "가" <= s[i - 1] <= "힣" and (i == 1 or not ("가" <= s[i - 2] <= "힣"))


def _repeat(s: str, i: int) -> bool:
    """예외(마스터 10-13): 같은 소리를 되풀이하는 의성어(흑…흑…흑…)는 붙인다 — 「…」 앞 한글 덩이가 뒤 덩이(다시 「…」 로 끝난다)와 같다.
    (「…」 뒤 여는 괄호 `…(화끈!)` 는 후보(한글·영숫자 앞)에 애초에 안 든다.)"""
    m = re.search(r"([가-힣]+)$", s[:i])
    n = re.match(r"([가-힣]+)…", s[i + 1 :])
    return bool(m and n and m.group(1) == n.group(1))


def count(s: str) -> int:
    return sum(1 for m in CAND.finditer(s) if not (_stutter(s, m.start()) or _repeat(s, m.start())))


def fix_text(s: str) -> str:
    return CAND.sub(
        lambda m: m.group(0) if (_stutter(s, m.start()) or _repeat(s, m.start())) else "… ", s
    )


FILES = [*sorted((GAME / "script").glob("*.json")), *sorted((GAME / "textmap").glob("*.json"))]


def walk(obj, fix: bool):
    """(위반 수, 고친 수) — `ours` 문자열을 훑는다."""
    bad = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "ours" and isinstance(v, str):
                n = count(v)
                bad += n
                if n and fix:
                    obj[k] = fix_text(v)
            else:
                bad += walk(v, fix)
    elif isinstance(obj, list):
        for v in obj:
            bad += walk(v, fix)
    return bad


def main() -> int:
    fix = "--fix" in sys.argv
    total = 0
    for p in FILES:
        j = json.loads(p.read_text(encoding="utf-8"))
        n = walk(j, fix)
        if n:
            total += n
            if fix:
                p.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
            else:
                print(f"  ✗ {p.name}: 「…」 뒤 공백 없음 {n}곳")
    if fix:
        print(f"  「…」 뒤 공백 {total}곳을 고쳤다")
        return 0
    if total:
        print(f"  ✗ 번역 규칙 2-11 위반 {total}곳 — `--fix` 로 고친다")
        return 1
    print("  「…」 뒤 공백 — 위반 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
