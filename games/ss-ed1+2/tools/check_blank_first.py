"""빈 줄 개행 — 번역 규칙 2-18 (창은 첫 줄부터 시작한다, 이유 없는 빈 첫 줄·겹개행 금지).

    python3 tools/check_blank_first.py          # 위반 수 (0 이어야 한다)
    python3 tools/check_blank_first.py --show   # 목록

잰다 (씬 대사·카드·시스템 문안 전부, 화자 머리 `%c이름%c`+개행은 구분자라 뺀다):
 · 우리 문안이 빈 첫 줄로 시작하는데 원문은 아니다 → 실패. 단 키 대기 뒤 같은 줄 이어 그리기 보정
   (`script/key_cont.json` 의 `nl`·값 열쇠 — 커서가 이미 줄 가운데라 이음 줄바꿈이다, 창 첫 줄이 아니다)은 면제.
 · 우리 문안에 겹개행(`\\n\\n`)이 있는데 원문엔 없다 → 실패.
원문이 스스로 빈 첫 줄/겹개행인 자리는 원문을 따른다(3-10) — 보고 전용으로 세기만 한다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
)

import common
import names_corpus
from text.line_key import key as line_key

_HDR = re.compile(r"^%c[^%\n]*%c")


def blank_first(s):
    """화자 머리를 뗀 본문이 빈 줄로 시작하나 (머리 뒤 개행 하나는 구분자)."""
    m = _HDR.match(s)
    if m:
        rest = s[m.end() :]
        rest = rest.removeprefix("\n")
        return rest.startswith("\n")
    return s.startswith("\n")


def main():
    with open(os.path.join(common.GAME_DIR, "script", "key_cont.json"), encoding="utf-8") as f:
        kc = json.load(f)
    exempt = set(kc.get("nl", {}).get("ED1", ())) | set(kc.get("nl", {}).get("ED2", ()))
    exempt |= set(kc.get("ED1", {})) | set(kc.get("ED2", {}))
    bad, orig_blank = [], 0
    for where, jp, kr, _kind in names_corpus.pairs():
        if not jp or kr is None:
            continue
        for what, f in (
            ("빈 첫 줄", blank_first),
            ("겹개행", lambda s: "\n\n" in s.replace("\r", "")),
        ):
            if f(kr):
                if f(jp):
                    orig_blank += 1
                elif what == "빈 첫 줄" and line_key(jp) in exempt:
                    pass
                else:
                    bad.append((where, what))
    if "--show" in sys.argv:
        for b in bad:
            print(*b)
    print(f"빈 줄 개행 위반 {len(bad)} · 원문 따름(보고) {orig_blank}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
