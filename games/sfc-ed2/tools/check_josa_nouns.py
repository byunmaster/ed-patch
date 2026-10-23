"""정본 고유명사 전 목록 × 조사(이/가 · 은/는 · 과/와 · 을/를) 받침 대조 — 우리 문안 전량.

기존 조사 검사는 관형사형(`먹는` · `있는`)·단일 형태소(`사과` · `마을`) 오탐 때문에 은/는·이/가·과/와 축을 못 본다. 여기는 **명사 목록 기반**이다 —
정본(`shared/canon`)의 ED1·ED2 고유명사(아이템·몬스터·인물·지명·주문) 한국어 표기가 **낱말 경계에서 시작해 바로 조사가 붙은** 자리만 본다
(`란도가` · `플로라이`…). 사전 토큰(`<E0:n>`) 뒤는 토큰이 푸는 이름의 받침으로 본다. 정적 `{이/가}`·런타임 `{*은/는}` 병기는 빌드가 푸니 건너뛴다.
조사 뒤에 한글이 바로 이어지면(`이다` · `가장`) 조사가 아니라 낱말이라 본다 않는다(단어 경계 — 조사 뒤는 공백·부호·태그·끝).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import build
import canon
import common
import kr

PAIRS = {"이": True, "가": False, "은": True, "는": False, "과": True, "와": False, "을": True, "를": False}  # 값 = 받침이 있어야 하는가
LATIN_FINAL = set("LMNRlmnr")  # 엘·엠·엔·알 — 영문 끝 글자가 받침 읽기(그 밖은 받침 없음: 에이·비·씨·디…)
STOP = {"이", "가", "은", "는", "과", "와", "을", "를", "그", "저", "이것"}


def has_final(s: str) -> bool | None:
    s = re.sub(r"[\s<>]", "", s)
    if not s:
        return None
    c = s[-1]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    if c.isascii() and c.isalpha():
        return c in LATIN_FINAL
    return None


def noun_list() -> list[str]:
    out = set()
    for cat, tbl in canon.nouns("ed2")["categories"].items():
        for v in tbl.values():
            if isinstance(v, str) and len(v.replace(" ", "")) >= 2:
                out.add(v.replace(" ", ""))
    return sorted(out, key=len, reverse=True)


def scan(texts: list[tuple[str, str]], names: dict[str, str]) -> tuple[int, list[tuple[str, str]]]:
    nouns = noun_list()
    pat = re.compile("(" + "|".join(re.escape(n) for n in nouns) + r")([이가은는과와을를])(?![가-힣])")
    seen, bad = 0, []
    for sid, t in texts:
        t = re.sub(r"\{\*?[^{}/]+/[^{}/]+\}", "\x00", t)  # 병기는 빌드가 푼다 — 자리만 막아 둔다
        t = re.sub(r"<E([01]):(\d+)>", lambda m: names.get(f"E{m.group(1)}:{m.group(2)}", "\x01"), t)
        t = re.sub(r"<[^>]*>", "", t)
        flat = t.replace("\n", "\x03")  # 줄바꿈도 막는다(줄 끝 이름 + 다음 줄 첫 「이」 를 조사로 안 붙인다)
        for m in re.finditer(pat, flat):
            n, j = m.group(1), m.group(2)
            if m.start() > 0 and "가" <= flat[m.start() - 1] <= "힣":  # 더 긴 낱말의 꼬리(`엘아스타마을` 의 뒤쪽 `마을` 같은)
                continue
            f = has_final(n)
            if f is None:
                continue
            seen += 1
            if PAIRS[j] != f:
                bad.append((sid, flat[max(0, m.start() - 6) : m.end() + 6].replace("\x03", "/")))
    return seen, bad


def main() -> None:
    src = common.rom_bytes()
    _, _, dm = build.collect_texts(src)
    names = build.dict_names(src, dm)
    texts = []
    for f in ("segments", "spans", "cells", "dict", "listsplit", "opsplit"):
        import json

        d = json.loads((common.ROOT / "games/sfc-ed2/textmap" / f"{f}.json").read_text(encoding="utf-8"))

        def walk(o, tag):
            if isinstance(o, dict):
                if isinstance(o.get("kr"), str):
                    texts.append((f"{f}:{tag}", o["kr"]))
                else:
                    for k, v in o.items():
                        walk(v, k)

        for k, v in d.items():
            walk(v, k) if isinstance(v, dict) else None
    seen, bad = scan(texts, names)
    print(f"명사×조사 대조: 문안 {len(texts):,}줄 · 정본 명사 {len(noun_list()):,}개 · 조사가 붙은 자리 {seen:,} · 받침 불일치 {len(bad)}")
    for sid, ctx in bad[:40]:
        print(f"  ✗ {sid} …{ctx}…")
    if bad:
        sys.exit(f"조사 받침 불일치 {len(bad)}곳")


if __name__ == "__main__":
    main()
