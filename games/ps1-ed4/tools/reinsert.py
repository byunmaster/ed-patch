"""재삽입 경로 — 대본 조각 문안을 **코드열로 바꿔 빌드 편집 목록으로** 만든다. 번역 정본 로더가 아니다(번역 판단 없음).

두 길(ED4 는 포인터를 다시 쓸 필요가 없다 — 표 규격은 표만 다시 계산, 풀 규격은 `scriptmap.rebuild` 가 포인터를 다시 건다):

- **같은 크기** — 새 코드열이 원본 조각과 **같은 길이**여야 한다(모자라면 공백 코드로 채우고, 넘치면 실패). 멤버 크기가 안 변한다.
- **길이 변경** — 조각 길이가 자유다. 멤버가 커지면 `build` 가 아카이브 안에서 뒤 멤버를 밀고(`gmf_arc.repack`) 디렉터리 크기를 고친다.
  🔴 마지막 섹터 여유를 넘으면 **멈춘다**(다른 파일을 옮겨야 하는 일이다 — 이 빌드가 안 한다).

🔴 **개수·순서를 지킨다** — 조각 색인으로 편집하고, 조각을 합치거나 나누지 않는다(포인터·표가 「몇 번째 조각」으로 다시 매핑된다).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hangul

from shared.ps1 import gmf_script as scriptmap

SPACE = " "
KAGI = str.maketrans("「」『』", "\ue020\ue021\ue022\ue023")  # 대사의 「」『』 → 반각 글리프(마스터 10-26). UI 의 전각 부호는 그대로


def member_segments(mem):
    """[[코드…]] — 멤버의 조각 코드열(원본)."""
    return [list(c) for _, c in scriptmap.parse(mem)["segments"]]


def codes_for(text, table=None, *, same_size_as=None):
    """문안 → 코드열. `same_size_as`(원본 코드열)를 주면 **같은 길이**로 맞춘다 — 모자라면 공백으로 채우고 넘치면 실패."""
    codes = hangul.encode(text.translate(KAGI), table)
    if same_size_as is not None:
        n = len(same_size_as)
        if len(codes) > n:
            raise ValueError(f"같은 크기 재삽입인데 {len(codes)} 코드 > 원본 {n}")
        if len(codes) < n:
            pad = hangul.encode(SPACE, table)[0]
            codes = codes + [pad] * (n - len(codes))
    return codes


def edits_for(members, key, texts, *, same_size=False, table=None):
    """`build` 의 `edits["script"]` 한 칸 — `{(아카이브, 멤버): {조각 색인: 코드열}}`.

    `members` = `build.identity_gate` 가 돌려준 `{(아카이브, 멤버): 원본 바이트}`, `key` = (아카이브, 멤버), `texts` = {조각 색인: 문안}.
    """
    segs = member_segments(members[key])
    per = {}
    for i, text in texts.items():
        per[i] = codes_for(text, table, same_size_as=segs[i] if same_size else None)
    return {key: per}
