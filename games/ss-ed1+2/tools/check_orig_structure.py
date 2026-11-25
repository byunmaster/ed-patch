"""원판 메시지 구조 대조 게이트 — 변수 앞뒤 어절 경계 · 쪽 수·빈 줄 · 끝 개행이 원판과 같나.

    python3 games/ss-ed1+2/tools/check_orig_structure.py

🔴 이유(10-30, pce-ed1 에서 나온 결함 셋과 같은 부류를 전수로 — 마스터 「보물상자처럼 띄어쓰기 개행 제대로 안된 게 꽤 있을 것 같은데」):
  1. 엔진이 끼우는 이름·아이템·숫자 칸(`%s`·`%d`·`{p}`·`{name}`) — 앞이 한글이면 어절이 붙는다, 뒤는 조사·단위만 붙는다.
  2. 원판의 쪽 넘김(`%c` 수)·빈 줄이 우리 문안에 그대로 있나(두 문장이 한 쪽에 이어 붙는 사고).
  3. 원판 메시지가 개행으로 끝나는데 우리 문안엔 없나(다음 메시지가 같은 줄에 붙는다).
문안은 `names_corpus.pairs()`(저본+덮어쓰기, 빌드 불필요)에서 읽는다. 3·2(빈 줄)의 알려진 자리는 `KNOWN_*` 에 사유와 함께 둔다 — 늘면 실패.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import names_corpus as N

VAR = r"(?:%[sd]|\{p\}|\{name\})"
# 변수 뒤에 바로 붙어도 되는 것 — 조사 · 단위(수치 칸)
_AFTER_OK = (
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "로", "으", "도", "만", "께", "한", "부", "까", "처", "보", "라", "야", "여", "랑",
    "포인트", "개", "번", "회", "배", "층", "명", "마리", "골드", "초", "분", "시", "턴", "장", "곳", "자", "단", "점", "레벨",
)  # fmt: skip

# 3. 원판은 개행으로 끝나는데 우리는 이어 붙이는 자리 — 모두 PS1 도 같은 꼴(이어 붙는 사슬 메시지)이라 화면 확인 대상으로 둔다
KNOWN_NO_END_NL = {
    "scn:/BIN/ED2MON03.BIN#9": "PS1 저본과 같은 꼴(「의 피해!! 」)",
    "scn:/BIN/ED2MON03.BIN#77": "PS1 저본과 같은 꼴",
    "sys:/ED.BIN@0x2C660": "「…은(는) 」 + 다음 메시지 — 한 문장 사슬",
    "sys:/BIN/ED2MON01.BIN@0xCF0": "「…분열해서 」 + 다음 메시지 — 한 문장 사슬",
}
# 2. 원판 끝의 빈 줄이 없는 자리(의성어 두 줄)
KNOWN_NO_BLANK = {"scn:/BIN/ED1SCN14.BIN#127": "의성어 두 줄 뒤 빈 줄 — 쪽 높이만 다르다"}


# 호칭 치환 부작용(「너희이」·「자네은」) — 받침 없는 대명사 뒤 이/을/은/과, 받침 있는 뒤 가/를/는/와
_PRON_OPEN = ("너희", "자네", "그대", "저희", "우리", "너")
_PRON_CLOSED = ("당신", "여러분")
_PRON_BAD = re.compile(
    r"(?<![가-힣])(?:(?:"
    + "|".join(_PRON_OPEN)
    + r")(?:이|을|은|과)|(?:"
    + "|".join(_PRON_CLOSED)
    + r")(?:가|를|는|와))(?![가-힣])"
)


def check(pairs):
    bad = {"변수 앞뒤": [], "쪽 수": [], "빈 줄": [], "끝 개행": [], "대명사 조사": []}
    for site, jp, kr, *_ in pairs:
        if kr is None:
            continue
        for m in re.finditer(r"([가-힣]?)" + VAR + r"([가-힣]{0,3})", kr):
            pre, post = m.group(1), m.group(2)
            if pre or (post and not post.startswith(_AFTER_OK)):
                bad["변수 앞뒤"].append((site, kr[max(0, m.start() - 6) : m.end() + 3]))
        for m in _PRON_BAD.finditer(kr.replace("\n", "")):
            bad["대명사 조사"].append((site, m.group()))
        if jp.count("%c") != kr.count("%c"):
            bad["쪽 수"].append((site, f"원판 {jp.count('%c')} · 우리 {kr.count('%c')}"))
        if "\n\n" in jp and "\n\n" not in kr and site not in KNOWN_NO_BLANK:
            bad["빈 줄"].append((site, kr[:30]))
        if jp.endswith("\n") and not kr.endswith("\n") and site not in KNOWN_NO_END_NL:
            bad["끝 개행"].append((site, kr[-20:]))
    return bad


def main():
    bad = check(list(N.pairs()))
    n = sum(len(v) for v in bad.values())
    print(
        "  원판 구조 대조 — "
        + " · ".join(f"{k} {len(v)}" for k, v in bad.items())
        + f" · 알려진 예외 {len(KNOWN_NO_END_NL) + len(KNOWN_NO_BLANK)}"
    )
    for k, v in bad.items():
        for site, ctx in v[:10]:
            print(f"    ✗ [{k}] {site}  {ctx!r}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
