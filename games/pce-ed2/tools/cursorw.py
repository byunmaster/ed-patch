"""디버그 마을 목록 커서 폭 — 패키지 258 장면 스크립트의 목록 열기 연산 `18 <폭 단계>`(마스터 11-22 「한 항목은 한 커서 안에」).

목록을 여는 연산은 `a1 NN … b9 e0 18 W`(NN = 메시지 줄 번호, W = 커서 틀 폭 단계 0~8)이고 W 가 작업 RAM `$28A9`·`$2D4C` 로 복사돼 커서 스프라이트 묶음(`cursorfix.py` 머리말)을 고른다.
실측(11-22, 원판 디버그 사본에서 RAM 을 바꿔 측정): 단계 0~8 의 틀 폭 = 26·36·50·62·74·90·98·110·122px(9 이상은 깨진다). 원판은 일본어 항목이 틀보다 길어도 틀이 앞 글자만 덮는 설계라 한국어 이름이
틀 밖으로 나온다 — 줄(`data/ctrl_lines.tsv`)마다 가장 긴 이름이 드는 최소 단계로 올리고 칸 폭(`gridlist.py`)을 그 틀에 맞춘다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REL = 258
WIDTH_PX = (26, 36, 50, 62, 74, 90, 98, 110, 122)
# 메시지 줄 번호 → (스크립트 안 W 바이트 위치, 원판 단계)
SITES = {
    1: (0x2E6, 0),  # 병사 이름(다리스…)
    2: (0x364, 1),  # 이벤트 점프(엘아스타 오프닝…)
    3: (0x3D3, 1),  # 이벤트 점프 둘째(해적섬…)
    4: (0x460, 1),  # 주문
    5: (0x57D, 2),  # 무기
    6: (0x59D, 2),  # 방어구
    7: (0x5BD, 2),  # 지팡이·반지 따위
    8: (0x7F1, 2),  # 도구
    9: (0x811, 2),  # 소지품(친서·통행증)
    10: (0x96A, 1),  # OP/ED
    11: (0x9DE, 0),  # 장
    12: (0xA3D, 5),  # 전투 시험 장
}


# 배틀 테스트 마을(패키지 16~19 = rel 2050·2178·2306·2434) — 같은 목록 열기 연산 `a1 NN … b9 e0 18 W`. 값 = 메시지 줄 번호 → (W 바이트 위치, 원판 단계). 원판 단계 0(26px)은 일본어 앞 두 글자만 덮는다.
BT_SITES = {
    2050: {9: (0x12C0, 0), 10: (0x1395, 0)},
    2178: {2: (0x10BD, 0), 3: (0x1190, 0)},
    2306: {2: (0xF09, 0), 3: (0xFDC, 0)},
    2434: {2: (0xD82, 0), 3: (0xE55, 0)},
}
BT_STEPS = {9: 1, 2: 1}  # 목록(「경고 평화 슬라임 성 …」) = 칸 폭 40px · 틀 36px(단계 1). 격자(「서장1 …」, 둘째 번호)는 원판 단계 0 그대로


def apply_bt(nb: bytearray, rel: int) -> None:
    """배틀 테스트 마을 패키지 바이트열(`nb`)의 목록 틀 폭 단계를 쓴다. 원판 값·앞 바이트(`18`)를 되읽어 대조한다."""
    for msg, (off, orig) in BT_SITES[rel].items():
        if msg in BT_STEPS:
            assert nb[off - 1] == 0x18 and nb[off] == orig, f"배틀 테스트 {rel} 목록 {msg} 연산 위치가 다르다 {nb[off - 1]:02x} {nb[off]:02x}"
            nb[off] = BT_STEPS[msg]


def name_px(name: str) -> int:
    """좁은 글꼴 목록의 글 폭 — 글자 8px · ASCII 공백 4px(실측 11-22: 「표」+공백 7 → 다음 항목이 36px 뒤)."""
    return sum(4 if c == " " else 8 for c in name)


def step_for(longest_px: int) -> int:
    """가장 긴 이름(px)이 틀 안(양끝 1px 여유)에 드는 최소 단계."""
    need = longest_px + 2
    for i, w in enumerate(WIDTH_PX):
        if w >= need:
            return i
    raise ValueError(f"이름이 너무 길다 {longest_px}px")


def apply(nb: bytearray, steps: dict[int, int]) -> None:
    """패키지 258 바이트열(`nb`)의 목록 열기 연산 W 바이트를 새 단계로 쓴다. 원판 값·앞 바이트(`18`)를 되읽어 대조한다."""
    for msg, w in steps.items():
        off, orig = SITES[msg]
        assert nb[off - 1] == 0x18 and nb[off] == orig, f"목록 {msg} 연산 위치가 다르다 {nb[off - 1]:02x} {nb[off]:02x}"
        nb[off] = w


# 줄 → 단계(`gridlist.layout` 이 가장 긴 이름으로 정한 값 — 테스트 `tests/test_cursorw.py` 가 틀에서 다시 계산해 대조한다)
STEPS = {1: 1, 2: 4, 3: 5, 4: 1, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: 0, 11: 0, 12: 3}
