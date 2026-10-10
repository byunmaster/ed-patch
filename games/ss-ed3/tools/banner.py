"""지명 배너(`폴티아 루데라 관문` — 지방 + 장소) 판별.

필드에 들어서면 위쪽에 뜨는 파란 막대 안의 글이다. 🔴 **글자가 막대 안쪽(16행)에서 위 1 · 아래 2 로 앉았다**(마스터 10-09 「이러한 배너는 위로 2px,
아래로 1px」 — 전투 위 배너와 같은 규칙, `patch_ui_center.py`). 한글 기본 글리프는 0 행부터 잉크가 있어 한 행 높다 ⇒ **한 행 내린 글리프**(`lowered_map`)로
넣으면 위 2 · 아래 1 이 된다. 지방 이름 표는 거기서 센 것(대사·이름 정본과 별개 — 배너 전용).
"""

import re

REGIONS = (
    "폴티아",
    "메나트",
    "챠놈",
    "앰비쉬",
    "우돌",
    "퓨엔테",
    "올도스",
    "기드나",
)
#   지방 하나 또는 `A−B` 두 지방 + **전각 공백(원문 꼴)** + 장소(한글·공백), 같은 꼴이 더 이어질 수 있다(`메나트　네갈섬　테그라`).
#   ⚠ 전각 공백이 **표지**다 — 「폴티아 병사」처럼 화자 이름도 지방으로 시작하지만 반각 공백이라 배너가 아니다.
_RE = re.compile(
    "(?:" + "|".join(REGIONS) + ")(?:−(?:" + "|".join(REGIONS) + "))?\u3000[가-힣0-9 \u3000]+"
)


def is_place_banner(text):
    """한 줄짜리 `지방 장소` 문안인가 — 줄바꿈·페이지가 없고 맨 앞이 지방 이름이다."""
    return (
        isinstance(text, str)
        and "\n" not in text
        and "\f" not in text
        and bool(_RE.fullmatch(text))
    )


def chars(texts):
    """배너 문안들의 한글 음절 — 한 행 내린 판이 필요한 글자."""
    return sorted({c for t in texts if is_place_banner(t) for c in t if "가" <= c <= "힣"})


def normalize(text):
    """전각 공백 → 반각(규칙 1-6, 마스터 10-09 「폴티아  루데라」가 넓어 보인다)."""
    return text.replace("\u3000", " ")
