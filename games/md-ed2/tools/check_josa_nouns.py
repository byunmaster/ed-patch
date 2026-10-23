"""명사 목록 × 조사 받침 대조 — 정본 고유명사(`shared/canon/nouns/eiyuu.json` 전 범주)의 한국어 값 바로 뒤에 붙은 이/가·은/는·을/를·과/와·으로/로 가 앞말 받침과 맞는가.

    python3 tools/check_josa_nouns.py [--list]     # 어긋남 0 이 아니면 종료 코드 1

「이름을 바꾸며 조사를 안 고친」 꼴을 잡는다(예: 슬라임→슬러그 로 바꾸고 「…이」 가 남은 줄). 목록 기반이라 관형사형 오탐이 없다 — 명사 값 + 조사 + (한글 아닌 글자·끝).
조사 뒤에 한글이 이어지면(「이다」·「가서」) 조사가 아니라 말의 일부라 넘긴다. 앞이 한글이면(더 긴 말의 끝) 넘긴다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

from shared.text import josa

GAME = common.GAME_DIR
NOUNS = Path(__file__).resolve().parents[3] / "shared" / "canon" / "nouns" / "eiyuu.json"
TAG = re.compile(r"<[^>]*>")
# (받침 있을 때, 받침 없을 때, ㄹ 받침 예외)
PAIRS = [("이", "가"), ("은", "는"), ("을", "를"), ("과", "와"), ("으로", "로")]


def nouns() -> list[str]:
    d = json.loads(NOUNS.read_text(encoding="utf-8"))["categories"]
    out = {v for cat in d.values() for v in cat.values() if isinstance(v, str)}
    return sorted(
        (v for v in out if len(v) >= 2 and all("가" <= c <= "힣" for c in v)), key=lambda x: -len(x)
    )


def texts():
    for p in sorted((GAME / "script").glob("*.json")):
        if p.name.startswith("ED2MON"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for k, e in d.get("streams", {}).items():
            if e.get("ours"):
                yield f"{p.stem}:{k}", e["ours"]
    for name in ("sysmsg", "battle", "captions"):
        p = GAME / "textmap" / f"{name}.json"
        if p.exists():
            for k, e in json.loads(p.read_text(encoding="utf-8")).items():
                if isinstance(e, dict) and e.get("ours"):
                    yield f"{name}:{k}", e["ours"]


def wrong(noun: str, particle: str) -> bool:
    """noun 뒤 particle 이 받침에 안 맞으면 True."""
    f = josa.batchim(noun[-1])
    if f is None:
        return False
    for has, no in PAIRS:
        if particle in (has, no):
            if has == "으로":
                return particle != ("로" if f in (0, 8) else "으로")
            return (f != 0 and particle == no) or (f == 0 and particle == has)
    return False


def scan() -> list[tuple[str, str, str]]:
    ns = nouns()
    pat = re.compile(
        r"(?<![가-힣])("
        + "|".join(map(re.escape, ns))
        + r")(으로|로|이|가|은|는|을|를|과|와)(?![가-힣])"
    )
    bad = []
    for where, t in texts():
        s = TAG.sub("\x00", t)  # 태그는 경계(조사 훅 `<ec02>` 앞뒤는 훅이 맡는다)
        for m in pat.finditer(s):
            if wrong(m.group(1), m.group(2)):
                bad.append(
                    (
                        where,
                        m.group(1) + m.group(2),
                        s[max(0, m.start() - 8) : m.end() + 8].replace("\x00", "·"),
                    )
                )
    return bad


def main() -> None:
    bad = scan()
    print(f"  명사×조사 받침 대조 — 어긋남 {len(bad)}")
    if "--list" in sys.argv or bad:
        for w, x, c in bad[:80]:
            print(f"    {w}\t{x}\t{c}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
