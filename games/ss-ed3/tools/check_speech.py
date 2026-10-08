"""한 블록 안에서 **높임과 반말이 섞였나**를 본다.

    python3 games/ss-ed3/tools/check_speech.py            # 옮긴 것 전량
    python3 games/ss-ed3/tools/check_speech.py MAP012     # 그 맵만
    python3 games/ss-ed3/tools/check_speech.py --quiet    # 건수만(게이트용)

🔴 **화자의 말투는 조판보다 먼저 눈에 띈다.** 같은 인물이 한 창 안에서 「~습니다」와
「~야」를 오가면 번역이 아니라 기계가 뱉은 것으로 읽힌다. 유저 방침(2026-08-26):
**화자 개성을 살리고, 높임과 반말을 섞지 않는다 — 상대가 바뀌는 자리만 예외.**

기계가 잡을 수 있는 것은 **명백한 혼용**뿐이다. 한국어 화계는 층이 여럿이고
(하십시오체 · 해요체 · 하게체 · 해체 · 해라체), 그중 하게체(「~하게」 「~하네」 「~거라」)는
노인·촌장의 말투라 반말도 높임도 아니다. 그래서 **하십시오체·해요체**와
**해체·해라체**가 한 블록에 같이 있을 때만 운다.

⚠ **경고지 실패가 아니다.** 한 블록 안에서 말 상대가 바뀌는 자리가 실제로 있다
(어른에게 답하고 이어서 동행에게 말하는 장면). 사람이 보고 가른다 —
「지금 고칠 수 있는 것만 실패로 친다」(CLAUDE.md).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import glossary_src as GS
import mapfile as M
import reinsert as R
import typeset as T

# 🔴 **문장부호로 끝난 것만 본다.** 우리 조판은 한 문장을 여러 줄에 나눠 담으므로
#   `0D`·`0F` 를 문장 경계로 삼으면 「계산대 안에 들어오지」 같은 **중간 토막**이 문장이
#   되어 반말로 오판된다(실측: 오탐 7 중 5). 개행·대기점은 공백으로 이어 붙인다.
_END = re.compile(r"[^.!?…]+[.!?…]+")
# 대답·맞장구는 화계를 안 가른다 — 「네.」의 `네` 가 종결어미 「~네」로 잡히던 자리다.
# ⚠ **거듭한 것도 맞장구다** — 말을 더듬는 자리의 「네, 네.」가 반말로 잡히던 걸 같이 막는다.
_INTERJ = r"(?:네|예|응|어|아|아니|아니요|그래|왜|뭐|음|흠)"
_SHORT = re.compile(rf"^{_INTERJ}(?:\s*,\s*{_INTERJ})*[.!?…]*$")
# 부르는 말만 있는 문장(「케빈 할아버지.」)도 화계를 안 가른다 — `할아버지` 의 `지` 가 반말 「~지」로
#   잡혀, 검수자가 오탐을 피하려고 멀쩡한 문안을 비틀던 자리다(10-02 라운드 8).
_VOC = re.compile(
    r"^(?:\S+\s)?(?:할아버지|할머니|아저씨|아주머니|삼촌|아빠|엄마|아버지|어머니|누나|언니|"
    r"선생님|촌장님|선장님|군|양|씨|님)[.!?…]*$"
)

# 하십시오체 · 해요체
HIGH = re.compile(
    r"(습니다|ㅂ니다|입니다|십시오|세요|셔요|어요|아요|여요|에요|예요|해요|"
    r"지요|죠|네요|군요|까요|는데요|든요|거든요|드려요|주세요|하세요)[.!?…]*$"
)
# 해체 · 해라체 (하게체 「~하게/~하네/~거라/~느냐」 는 뺀다 — 노인 말투라 어느 쪽도 아니다)
LOW = re.compile(
    r"(잖아|거야|건데|는걸|을걸|ㄹ걸|야|냐|자|어|아|지|네|군|구나|더라|는데|든가|"
    r"란다|는단다|겠어|했어|이야|이다|한다|같아|말야)[.!?…]*$"
)
# ⚠ 하게체·나레이션 표지 — 여기 걸리면 판정에서 뺀다
NEUTRAL = re.compile(
    r"(하게|하네|거라|느냐|시게|게나|구먼|당께|것이여|이여|였다|이었다|했다)[.!?…]*$"
)


def sentences(text):
    """블록 텍스트 → **문장부호로 끝난** 문장 목록. 개행·대기점은 공백으로 잇는다."""
    flat = T.visible(text).replace("\n", " ").replace("\f", " ")
    out = []
    for s in _END.findall(flat):
        s = s.strip()
        if (
            s
            and not _SHORT.match(s)
            and not _VOC.match(re.sub(r"^(?:네|예|아|아아|어머|오오|저기)[,\s]+", "", s))
        ):
            out.append(s)
    return out


def _names():
    """정본의 우리 표기 — **긴 것부터**(짧은 이름이 긴 이름 안에 먹히지 않게)."""
    cats = GS.categories()
    out = {v for c in cats.values() for v in c.values() if isinstance(v, str) and len(v) >= 2}
    return sorted(out, key=len, reverse=True)


_NAMES = None


def level(s):
    """`'high'` · `'low'` · `None`(가릴 수 없음).

    🔴 **고유명사를 먼저 지운다.** 이름의 끝 글자가 종결어미로 읽히는 자리가 있다 —
    「고죠」의 `죠`(해요체) · 「루레」의 `레` · 「그러네」의 `네`. 실측 2026-08-27 에
    「제１시합은 바닷트와 **고죠**.」가 높임으로 잡혀 뒤의 반말과 혼용 판정이 났다.
    문안을 비틀어 피하면 **이름이 나올 때마다 다시 물린다.**
    """
    global _NAMES
    if _NAMES is None:
        _NAMES = _names()
    s = s.rstrip()
    # 🔴 **말끝을 흐린 문장은 화계를 안 정한다** — 「~했는데...」 「어쩌지...」 는 종결이
    #   아니라 여운이라 어느 쪽으로도 못 읽는다. 전각 「・・・」 를 쓰던 동안은 그게 부호가
    #   아니라 **글자**여서 종결어미 뒤 `[.!?…]*$` 에 안 걸려 저절로 빠져 있었는데, 반각
    #   「...」 로 바꾸자 한꺼번에 종결로 잡혀 오탐 11 이 났다(2026-08-27).
    if re.search(r"\.{2,}[.!?…]*$", s):
        return None
    for nm in _NAMES:
        if nm in s:
            s = s.replace(nm, "○")
    # 문장 끝에 붙은 부르는 말(「어때요, 쥬리오 군.」)은 걷어 내고 그 앞 어미로 판정한다
    s = re.sub(r",\s*\S+\s(?:군|양|씨|님)([.!?…]*)$", r"\1", s)
    if NEUTRAL.search(s):
        return None
    if HIGH.search(s):
        return "high"
    if LOW.search(s):
        return "low"
    return None


def mixed(text):
    """섞였으면 `(높임 문장, 반말 문장)`, 아니면 `None`."""
    if T.is_narration(text):
        return None
    hi = lo = None
    for s in sentences(text):
        lv = level(s)
        if lv == "high" and hi is None:
            hi = s
        elif lv == "low" and lo is None:
            lo = s
    return (hi, lo) if hi and lo else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    maps = {}
    for disc in (1, 2):
        with C.open_disc(disc) as d:
            for n, lba, size in sorted(d.files()):
                if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                    continue
                stem = os.path.basename(n)[:-4]
                if stem not in maps:
                    maps[stem] = M.blocks(d.read_extent(lba, size))

    n_hit = n_all = 0
    for stem in sorted(maps):
        if a.stems and stem not in a.stems:
            continue
        kr, _ = R.load_script(stem)
        for k, v in sorted(kr.items(), key=lambda x: int(x[0])):
            n_all += 1
            m = mixed(v)
            if not m:
                continue
            n_hit += 1
            if a.quiet:
                continue
            print(f"  {stem}:{k}")
            print(f"    높임 {m[0]!r}")
            print(f"    반말 {m[1]!r}")
    print(
        f"말투 혼용 {n_hit} / 옮긴 블록 {n_all}" + (" — ⚠ 경고이지 실패가 아니다" if n_hit else "")
    )


if __name__ == "__main__":
    main()
