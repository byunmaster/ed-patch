"""조사 일치 검사(정적) — 이름 **바로 뒤에 손으로 쓴 조사**가 그 이름의 받침과 맞는가. (기반 F8)

    python3 tools/check_josa_agreement.py          # 자리 목록
    python3 tools/check_josa_agreement.py --check  # 게이트(어긋남이 있으면 실패)

`check_josa.py` 는 **훅**(`<02><eb…>`)의 짝과 병기를 본다. 여기는 그 바깥 — 문안에 사전 이름이 **그대로 박혀 있고**
그 뒤에 조사 글자가 붙은 자리(`슬러그는` · `류난에게` 같은 정적 이름)를 문안 전량(번역된 줄)에서 잰다.
- 이름 = 정본 고유명사(`shared/canon/nouns`)의 한국어 값(item·monster·person·place), 길이 2 이상, 가장 긴 것 우선.
- 조사 = 은/는 · 이/가 · 을/를 · 과/와 · 으로/로(ㄹ 받침은 「로」). 뒤가 한글이면(조사가 아니라 다음 낱말) 안 잰다.
- 숫자 끝은 읽는 소리(1·3·6·7·8·0 받침 있음 — `josa.ASCII_FINAL`), 영문·부호 끝은 무받침.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import battle
import common
import halfspace
import josa
import names_corpus
from shared import canon

PAIR = {"은": 0, "는": 0, "이": 1, "가": 1, "을": 2, "를": 2, "과": 3, "와": 3}
# 종류: 0 은/는 · 1 이/가 · 2 을/를 · 3 과/와 — 받침 있음이면 앞 글자(은·이·을·과), 없음이면 뒤 글자(는·가·를·와)
WITH_FINAL = {"은", "이", "을", "과"}
TAG = re.compile(r"<[^>]*>")


def final_of(name: str) -> int:
    """0 없음 · 1 받침 · 2 ㄹ — 이름 끝 글자 기준."""
    c = name[-1]
    if "가" <= c <= "힣":
        return josa.final_kind(c)
    if c in josa.ASCII_RIEUL:
        return 2
    if c in josa.ASCII_FINAL:
        return 1
    return 0


def names() -> list[str]:
    out = set()
    for cat in ("item", "monster", "person", "place"):
        for v in canon.table(cat, "ed1").values():
            v = halfspace.plain(v).replace(" ", "")
            if len(v) >= 2 and re.fullmatch(r"[가-힣A-Za-z0-9ＡＢＣＤ]+", v):
                out.add(v)
    return sorted(out, key=lambda x: (-len(x), x))


def agrees(name: str, p: str) -> bool:
    f = final_of(name)
    if p in ("으로", "로"):
        return (p == "으로") == (f == 1)
    return (p in WITH_FINAL) == (f >= 1)


def scan_lines(lines: list[tuple[str, str]]) -> tuple[int, list[str]]:
    """[(자리, 문안)] → (잰 자리 수, 어긋남 목록)."""
    pat = re.compile(
        "(" + "|".join(re.escape(n) for n in names()) + r")(으로|로|은|는|이|가|을|를|과|와)(?![가-힣])"
    )
    n, errs = 0, []
    for where, ours in lines:
        t = halfspace.plain(TAG.sub("", ours)).replace("\n", " ")
        for m in pat.finditer(t):
            n += 1
            name, p = m.group(1), m.group(2)
            if not agrees(name, p):
                f = final_of(name)
                errs.append(f"{where}: 「{name}{p}」 — 받침 {'없음' if f == 0 else 'ㄹ' if f == 2 else '있음'}")
    return n, errs


def scan() -> tuple[int, list[str]]:
    lines = [
        (w, o)
        for w, _jp, o, _k in names_corpus.pairs()
        if o and not w.startswith(("names:", "monsters:", "banner:"))
    ]
    return scan_lines(lines)


def main() -> None:
    n, errs = scan()
    print(f"  조사 일치(정적) — 이름 뒤 손조사 {n}곳 중 어긋남 {len(errs)}")
    for e in errs[:40]:
        print(f"    ❌ {e}")
    if "--check" in sys.argv and errs:
        raise SystemExit("조사 일치 검사 실패 — 문안을 고치거나 훅(<02><eb>·<0e><ec>)을 쓴다")


if __name__ == "__main__":
    main()
