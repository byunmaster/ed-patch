"""부호 규칙 검사 — 번역 규칙 2-11(`…` 뒤에 말이 이어지면 반각 공백) · 2-12(`?!` 와 `…` 가 겹치면 `…` 가 앞) · 1-7(`～` 뒤 마침표 금지). 0건 유지.

대상은 textmap/*.json 의 한글 문안(kr·ko 값) 전량. 제어 토큰(`<..>`·`{..}`)·줄 끝·닫는 부호 앞은 안 본다 —
`…` 바로 뒤가 한글·영숫자일 때만 위반이다.
"""

import json
import re
import sys
from pathlib import Path

TEXTMAP = Path(__file__).resolve().parents[1] / "textmap"
ELLIPSIS_GLUED = re.compile("…(?=[가-힣A-Za-z0-9])")  # 2-11
ELLIPSIS_INITIAL_SPACED = re.compile("… (?=[가-힣A-Za-z0-9])")  # 2-11 정정: 문장 맨 앞 `…` 뒤는 붙인다
# 예외(마스터 10-12): 한 낱말을 음절마다 끊어 말하는 꼴(세…리…오…스…) — 홑음절 + … + 홑음절 + … 은 붙인다.
# 끊긴 조각이 한 낱말인지(붙임) 낱말이 바뀌는지(띄움)는 기계가 못 가리므로 홑음절 사슬은 통과시키고 문안이 정한다.
QUESTION_ELLIPSIS = re.compile("[?!？！]…")  # 2-12: …는 물음표·느낌표 앞에 (…?  …!  …!?)
TILDE_PERIOD = re.compile("～\\.")  # 1-7


def _repeated_sound(text: str, i: int) -> bool:
    """같은 소리를 되풀이하는 의성어(흑…흑…흑…, 마스터 10-13) — `…` 앞뒤 글자가 같다. (`…(` 는 애초에 위반 꼴이 아니다)"""
    return 0 < i < len(text) - 1 and text[i - 1] == text[i + 1] and "가" <= text[i + 1] <= "힣"


def _sentence_initial(text: str, i: int) -> bool:
    """문장 맨 앞의 `…`(마스터 10-13) — 앞이 없거나 줄바꿈·공백·「 뒤. 뒤는 붙인다(…그런 것처럼). `?…` 처럼 앞말에 붙은 건 말줄임이다."""
    return i == 0 or text[i - 1] in "\n \u300c" or text[max(0, i - 2) : i] == "\\n"


def _in_chain(text: str, i: int) -> bool:
    """i 의 `…` 가 홑음절 사이(앞 글자가 홑음절이고 뒤 글자가 홑음절 + `…`)인가."""
    before = text[max(0, i - 2) : i]
    after = text[i + 1 : i + 3]
    lone_before = bool(re.fullmatch("(?:^|[^가-힣])[가-힣]", before)) or len(before) == 1 and before.isalpha()
    lone_after = bool(re.fullmatch("[가-힣]…", after))
    return lone_before and lone_after


def violations(text: str) -> list[str]:
    out = []
    for rule, rx in (("2-11", ELLIPSIS_GLUED), ("1-7", TILDE_PERIOD)):
        for m in rx.finditer(text):
            if rule == "2-11" and (
                _in_chain(text, m.start()) or _repeated_sound(text, m.start()) or _sentence_initial(text, m.start())
            ):
                continue
            out.append(f"{rule} …{text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for m in QUESTION_ELLIPSIS.finditer(text):
        out.append(f"2-12 {text[max(0, m.start() - 8) : m.end() + 6]!r}")
    for m in ELLIPSIS_INITIAL_SPACED.finditer(text):
        if _sentence_initial(text, m.start()):
            out.append(f"2-11 문장 첫 …{text[max(0, m.start() - 8) : m.end() + 6]!r}")
    return out


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in ("kr", "ko") and isinstance(v, str):
                yield v
            else:
                yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def main() -> int:
    bad = []
    total = 0
    for f in sorted(TEXTMAP.glob("*.json")):
        for key, v in json.loads(f.read_text(encoding="utf-8")).items():
            texts = [v] if isinstance(v, str) else list(_strings(v))
            for t in texts:
                total += 1
                bad += [f"{f.name}:{key} {x}" for x in violations(t)]
    for b in bad:
        print("  ✗", b)
    print(f"부호 규칙(2-11 … 뒤 공백 · 2-12 ?!… 순서 · 1-7 ～ 뒤 마침표): 문안 {total}건 중 위반 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
