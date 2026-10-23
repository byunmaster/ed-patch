"""공통 번역 규칙 2-11 · 1-7 — 문안 전수 검사 (게이트).

    python3 games/ss-ed3/tools/check_ellipsis_space.py          # 어긋난 자리 보기
    python3 games/ss-ed3/tools/check_ellipsis_space.py --apply  # 「…」 뒤 붙임에 반각 공백을 넣는다(`～.` 는 손으로)

2-11  「…」 뒤에 글자가 바로 붙으면 안 된다 — `그대도…잊었다` ✗ → `그대도… 잊었다` ✓.
      음절마다 끊어 말하는 꼴(`세…리…오…스…`)·같은 소리를 되풀이하는 의성어(`흑…흑…흑…`)·`…(` 는 붙인다(마스터 10-12·10-13 예외).
      문장 맨 앞 `…` 뒤는 붙인다(`…그런 것처럼` — 마스터 10-13, 앞말 뒤 말줄임 다음만 띄운다).
      줄 끝·개행·닫는 부호(`」` `?` `!` 등) 앞은 띄우지 않는다(그래서 한글·영문·숫자가 이어질 때만 본다).
2-12  물음표·느낌표와 `…` 가 겹치면 `…` 를 앞에 — `없잖아!…` ✗ → `없잖아…!` ✓(`--apply` 가 바꾼다. 마스터 10-13).
1-7   물결표 뒤에 마침표를 붙이지 않는다 — `불렀어～.` ✗.
대상: `script/MAP*.json` · `script/book/*.json` · `script/voice.json`(음성 자막).
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")
GLUED = re.compile(r"…(?=[가-힣A-Za-z0-9])")


def _hg(c):
    return "가" <= c <= "힣"


def _syllable_chain(s, i):
    """`s[i]` 의 「…」 가 음절 끊어 말하기(`세…리…오…스…`)의 가운데인가 — 홀로 선 한 글자 앞 · 한 글자 + 「…」 가 바로 뒤.
    마스터 10-12: 한 낱말을 음절마다 끊으면 붙여 쓴다."""
    return (
        i >= 1 and _hg(s[i - 1]) and (i < 2 or not _hg(s[i - 2]))
        and _hg(s[i + 1 : i + 2] or " ") and s[i + 2 : i + 3] == "…"
    )


ONOMATO = re.compile(r"([가-힣]{1,2})…\1(?![가-힣])")  # 같은 소리 되풀이(`흑…흑…흑…`) — 마스터 10-13: 붙인다


def _repeat(s, i):
    """`s[i]` 의 「…」 앞뒤가 같은 소리(1~2음절)인가 — 낱말이 아니라 의성어 되풀이."""
    k = i
    while k > 0 and _hg(s[k - 1]) and i - k < 2:
        k -= 1
    return any(m.start() <= k and m.end() > i for m in ONOMATO.finditer(s)) or bool(
        ONOMATO.match(s, k)
    )


def _initial(s, i):
    """`s[i]` 의 「…」 가 문장 맨 앞인가 — 블록·페이지 머리, 또는 끝맺는 부호 뒤(같은 줄·개행 뒤). 마스터 10-13: 맨 앞 「…」 뒤는 붙인다."""
    if i == 0 or s[i - 1] == "\f":
        return True
    if s[i - 1] == "\n":
        return i >= 2 and s[i - 2] in ".?!」~～"
    return i >= 2 and s[i - 1] == " " and s[i - 2] in ".?!」~～"


def spaced_initial(s):
    """문장 맨 앞 「…」 뒤를 띄운 자리."""
    return [
        i
        for i, c in enumerate(s)
        if c == "…" and _initial(s, i) and s[i + 1 : i + 2] == " " and s[i + 2 : i + 3].isalnum()
    ]


def glued(s):
    # 「…(」 처럼 여는 괄호가 붙는 꼴은 애초에 안 센다(한글·영문·숫자가 이어질 때만 본다) — 마스터 10-13 예외
    return [
        m.start()
        for m in GLUED.finditer(s)
        if not _syllable_chain(s, m.start())
        and not _repeat(s, m.start())
        and not _initial(s, m.start())
    ]


def fix_str(s):
    out, last = [], 0
    for i in glued(s):
        out += [s[last : i + 1], " "]
        last = i + 1
    s = QE_ELLIPSIS.sub(r"…\1", "".join(out) + s[last:])
    for i in reversed(spaced_initial(s)):
        s = s[: i + 1] + s[i + 2 :]
    return s


def fix(raw):
    """JSON 원문 텍스트의 문자열 리터럴마다 `fix_str` — `\\f` · `\\n` 이스케이프를 잠깐 풀어 센다."""

    def one(m):
        x = m.group(1).replace("\\f", "\f").replace("\\n", "\n")
        return '"' + fix_str(x).replace("\f", "\\f").replace("\n", "\\n") + '"'

    return re.sub(r'"((?:[^"\\]|\\.)*)"', one, raw)


QE_ELLIPSIS = re.compile(r"([?!？！]+)…")  # 2-12: `…` 가 앞 — `!?…` ✗ → `…!?` ✓
TILDE_DOT = re.compile(r"[～~]\.")


def files():
    yield from sorted(glob.glob(os.path.join(SCRIPT_DIR, "MAP*.json")))
    yield from sorted(glob.glob(os.path.join(SCRIPT_DIR, "book", "BOOK*.json")))
    yield os.path.join(SCRIPT_DIR, "voice.json")


def walk(o, path=()):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            if not str(k).startswith("_"):
                yield from walk(v, (*path, str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, (*path, str(i)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    bad = tilde = 0
    for p in files():
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        for path, s in walk(json.loads(raw)):
            for rule, hit in (
                ("2-11", bool(glued(s) or spaced_initial(s))),
                ("2-12", bool(QE_ELLIPSIS.search(s))),
                ("1-7", bool(TILDE_DOT.search(s))),
            ):
                if hit:
                    if rule in ("2-11", "2-12"):
                        bad += 1
                    else:
                        tilde += 1
                    if not a.apply or rule == "1-7":
                        print(f"  ✗ {rule} {os.path.basename(p)} {'/'.join(path)}: {s[:40]!r}")
        if a.apply:
            n = fix(raw)
            if n != raw:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(n)
    print(f"  「…」 뒤 붙임·`?!…` {bad} · 「～.」 {tilde}")
    return 1 if (bad or tilde) and not a.apply else 0


if __name__ == "__main__":
    sys.exit(main())
