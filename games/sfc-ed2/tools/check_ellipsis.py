"""번역 규칙 2-11 — 「…」 뒤에 말이 이어지면 반각 공백을 띄운다(줄 끝·닫는 부호·개행·제어코드 앞은 안 띄운다). textmap 전체 문안을 훑어 어긴 곳이 있으면 실패."""

import json
import re
import sys
from pathlib import Path

TEXTMAP = Path(__file__).resolve().parent.parent / "textmap"
BAD = re.compile(r"(?<=(.))…+(?=[^\s…<.,!?」』)(（~\-：:;。、]|<E)(?=(.))|(?<![^\n])…+(?=[^\s…<.,!?」』)(（~\-：:;。、]|<E)")  # 규칙 2-11 예외: 여는 괄호 앞은 붙인다


def walk(o, path, out):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, path + [k], out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, path + [i], out)
    elif isinstance(o, str):
        for m in BAD.finditer(o):
            if m.group(1) and m.group(1) == m.group(2):  # 같은 소리를 되풀이하는 의성어(흑…흑…흑…)는 붙인다
                continue
            out.append((path, o[max(0, m.start() - 8) : m.end() + 8]))


def main() -> None:
    out: list = []
    for f in sorted(TEXTMAP.glob("*.json")):
        walk(json.loads(f.read_text(encoding="utf-8")), [f.name], out)
    for path, ctx in out[:20]:
        print(f"  … 뒤 공백 없음 {path[:3]} {ctx!r}")
    if out:
        sys.exit(f"규칙 2-11 위반 {len(out)}곳")
    print("… 뒤 공백 규칙(2-11) 위반 0")


if __name__ == "__main__":
    main()
