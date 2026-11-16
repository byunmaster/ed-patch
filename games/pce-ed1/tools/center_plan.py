"""한글 지명 가운데 맞춤 계산 — 입장 배너(`scn000` raw)·HUD 지명 칸(`places` 12B) 공용(번역 규칙 2-8 「지명 입장 배너는 전 기종 틀 안 가운데」, 마스터 11-05).

모든 패딩은 **전각 공백(12px)** 이다 — 배너·HUD 칸 모두 글자 코드를 2바이트 단위로 읽어(반각 공백 1B 를 끼우면 정렬이 깨져 글이 잘렸다, 11-05 실측) 반 칸(4px) 단위 앞 공백은 못 쓴다.
그래서 쏠림은 12px 단위 선택의 남는 값이고, 번역 규칙 2-8 이 「기계 단위 탓에 남는 반 칸(6px) 이하 쏠림은 허용」한다.

배너(헤드리스 실측, 씬 0): 틀 안쪽 98px, 글 원점은 틀 안쪽 왼쪽에서 5px. 앞 공백 12px·5글자(60px)에서 잉크 중심이 틀 중심보다 2.5px 왼쪽 ⇒ 틀 중심의 원점 기준 x `BANNER_C` = 44.5.
HUD 지명 칸(마스터 캡처 16·20): 칸 안쪽 약 90px, 글 원점은 왼쪽에서 7px ⇒ 중심 x `HUD_C` = 38.
쏠림 = 앞 공백 px + 이름 폭/2 − C (양수 = 오른쪽).
"""

import typeset

BANNER_C = 44.5
HUD_C = 38.0
HALF_CELL = 6.0  # 규칙 2-8 허용 쏠림(반 칸 = 6px)


def _w(name: str) -> float:
    """이름 폭(px) — 문안 속 반 칸 공백(`HALF_MARK`, 입장 배너 「엘아스타 마을」의 띄어쓰기)은 4px."""
    return typeset.px(name.replace(HALF_MARK, "").replace(JOIN_MARK, "")) + 4 * (name.count(HALF_MARK) + name.count(JOIN_MARK))


def best_lead(name: str, c: float, max_cells: int) -> tuple[int, float]:
    """전각 앞 공백 칸 수(0..max_cells)와 그때 쏠림(px) — 쏠림 절댓값 최소, 같으면 칸 적은 쪽."""
    w = typeset.px(name)
    best = None
    for k in range(max_cells + 1):
        shift = 12 * k + w / 2 - c
        key = (abs(shift), k)
        if best is None or key < best[0]:
            best = (key, k, shift)
    return best[1], best[2]


def banner_shift(text: str) -> float:
    """배너 문자열(앞·뒤 공백 포함)의 잉크 쏠림 — 앞 공백은 전각 12px."""
    name = text.strip(" " + HALF_MARK)
    lead_s = text[: len(text) - len(text.lstrip(" " + HALF_MARK))]
    return 12 * lead_s.count(" ") + 4 * lead_s.count(HALF_MARK) + _w(name) / 2 - BANNER_C


def best_lead_half(name: str, c: float, enc_len: int, field: int = 12) -> tuple[int, int, float]:
    """HUD 지명 — 전각 앞 공백 칸 수 k · 시작 열 +1(8px) h(0/1) 와 쏠림. h=1 은 데이터 맨 앞에 표시 `F8 24`(2B)가 들어간다(`hud_half`)."""
    w = _w(name)
    best = None
    for h in (0, 1):
        room = field - enc_len - (2 if h else 0)
        if room < 0:
            continue
        for k in range(room // 2 + 1):
            shift = 12 * k + 8 * h + w / 2 - c
            key = (round(abs(shift), 3), shift, h, k)  # 규칙 2-8 11-09 개정 「최대한 가운데」: 가능한 위치 중 가운데에 가장 가까운 것, 좌우 거리가 같을 때만 왼쪽(쏠림 작은 쪽)
            if best is None or key < best[0]:
                best = (key, k, h, shift)
    return best[1], best[2], best[3]


JOIN_MARK = "\u200a"  # 글자 바로 뒤 반 칸(4px)을 **그 글자의 변형 코드**(`font.variant`, 글자 칸 + 4px)로 쓴다는 표시 — 공백 코드 한 개를 아낀다(엘아스타 마을)
HALF_MARK = "\u2002"  # 정본 문안 속 「반 칸 공백(4px, 대사창 반각 코드)」 표시 — translate.compose(raw)가 `HALF_SPACE` 바이트로 푼다


def banner_lead(name: str, max_px: int = 96) -> tuple[str, float]:
    """입장 배너 앞 공백 문자열(전각 12px × k + 반 칸 4px × h)과 쏠림 — 4px 단위라 쏠림 ≤2px(마스터 11-08 「배너도 전부 가운데」)."""
    w = _w(name)
    best = None
    for k in range(0, 4):
        for h in range(0, 4):
            if 12 * k + 4 * h + w > max_px or k + h + len(name.replace(JOIN_MARK, "")) > 7:  # 7칸(14B) 고정 표 — 글자 코드 7개 안
                continue
            shift = 12 * k + 4 * h + w / 2 - BANNER_C
            key = (round(abs(shift), 3), shift, k + h, k)  # 규칙 2-8 11-09 개정: 가운데에 가장 가까운 쪽 · 같을 때만 왼쪽
            if best is None or key < best[0]:
                best = (key, " " * k + HALF_MARK * h, shift)
    return best[1], best[2]



def banner_form(name: str) -> tuple[str, float]:
    """배너 최종 문안(앞 공백 포함)과 쏠림. 이름 안 반 칸 공백은 먼저 공백 코드(`HALF_MARK`)로 두고, 그래도 쏠림이 한 단위(4px)를 넘으면(6글자+공백이라 7코드를 다 써 앞 공백을 못 넣는 이름) 그 공백을
    앞 글자의 변형 코드(`JOIN_MARK`, 글자 칸 + 4px)로 바꿔 코드 한 개를 아껴 앞 공백을 넣는다 — 폭은 같다(마스터 11-09: 공백은 반각 4px, 위치로 맞춘다)."""
    lead, sh = banner_lead(name)
    if HALF_MARK in name and abs(sh) > 4:
        joined = name.replace(HALF_MARK, JOIN_MARK)
        lead2, sh2 = banner_lead(joined)
        if abs(sh2) < abs(sh):
            return lead2 + joined, sh2
    return lead + name, sh
