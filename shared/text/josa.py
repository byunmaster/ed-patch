"""한국어 조사 선택 유틸 — 앞말 받침 유무로 은/는·이/가·을/를 등을 고른다.

게임 텍스트 파이프라인용: 이름·명사가 빌드 시점에 확정되는 자리에서 병기(은(는))
대신 정확한 조사를 쓴다. 런타임 치환(%s) 자리는 코드 훅이 필요해 대상 아님
(ED1 동적 조사 훅 — status.md 개선 항목).

받침을 알 수 없는 앞말(라틴·숫자·기호로 끝나면)은 병기 폴백("은(는)")을 돌려준다 —
잘못 고르는 것보다 병기가 안전하다는 기존 전투 코퍼스 방침 유지.
"""

from __future__ import annotations

# (받침 있음, 받침 없음) — 대표 표기 "은/는" 키로 조회
PAIRS = {
    "은/는": ("은", "는"),
    "이/가": ("이", "가"),
    "을/를": ("을", "를"),
    "과/와": ("과", "와"),
    "아/야": ("아", "야"),
    "이랑/랑": ("이랑", "랑"),
    "으로/로": ("으로", "로"),  # ㄹ 받침은 '로' — batchim() 참조
}

_RIEUL = 8  # 종성 인덱스: ㄹ


def batchim(ch: str) -> int | None:
    """한글 음절의 종성 인덱스(0=없음, 1~27). 한글이 아니면 None."""
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28
    return None


def josa(word: str, pair: str) -> str:
    """word 뒤에 붙일 조사를 고른다. 예: josa("검", "이/가") → "이".

    - '으로/로'는 ㄹ 받침이면 '로'(칼로, 손으로).
    - 받침 판정 불가(비한글 꼬리)면 병기 폴백 "은(는)" 형태.
    """
    a, b = PAIRS[pair]
    tail = word.rstrip()[-1:] if word.rstrip() else ""
    f = batchim(tail)
    if f is None:
        return f"{a}({b})"
    if pair == "으로/로" and f == _RIEUL:
        return b
    return a if f else b


def attach(word: str, pair: str) -> str:
    """word + 조사. 예: attach("세리오스", "이/가") → "세리오스가"."""
    return word + josa(word, pair)
