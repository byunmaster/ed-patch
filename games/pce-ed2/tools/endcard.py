"""장 끝 카드 — 「第Ｎ章 제목 / (빈 줄) / 完」 가운데 맞춘 카드 줄을 정본 `battle` 범주의 카드 문안으로 바꾼다.

정본 값은 줄 배치까지 한 벌이다(`제３장  용의 알\\n\\n              끝` — 마스터 10-12). 줄바꿈은 `0D`, 공백은 반각 `60`, 꼬리 제어(`12`)는 원문 그대로.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import chapter
import jptext

_NUM = {c: i for i, c in enumerate("０１２３４５６７８９")}


def _card_value(jp: str) -> str | None:
    m = re.search("第([０-９])章[\\s\u3000]+(.+?)\n", jp)
    if not m or "完" not in jp:
        return None
    for k, v in canon.table("battle", "ed2").items():
        if k.startswith(f"第{m.group(1)}章") and k.endswith("完") and (m.group(2) in k or "{name}" in k):
            return chapter.chapter_gap(v)
    return None


def edit_line(line: bytes, tab) -> bytes | None:
    jp = jptext.decode(line)
    val = _card_value(jp)
    if val is None:
        return None
    tail = b"\x12" if line.endswith(b"\x12") else b""
    rows = val.split("\n")
    out = []
    for r in rows:
        body = r.strip(" ")
        if not body:
            out.append(b"")
            continue
        out.append(chapter._pad(_row_left(body)) + tab.enc(body, space=0x60))
    return b"\x0d".join(out) + tail


def _row_left(body: str) -> int:
    """카드 한 줄의 앞 여백(px, 4 의 배수) — 줄마다 따로 가운데(창 안쪽 169px, 글 시작 +1): 잉크 쏠림 |2·pad + 잉크폭 − 167| 이 가장 작은 칸. 원래는 가장 긴 줄(제목) 기준으로 덩이째 밀어 짧은 제3장 카드의 「끝」이 오른쪽으로 18px 쏠렸다(마스터 11-08 「장 끝제목 가운데」 실화면)."""
    ink = sum(4 if c == " " else 12 for c in body) - 1
    return min(range(0, 168, 4), key=lambda p: (abs(2 * p + ink - 167), p))  # 가장 가까운 칸, 같을 때만 왼쪽(마스터 11-09 2-8 개정)


def edit_chunk(d: bytes, tab) -> bytes:
    lines = d.split(b"\x00")
    for i, l in enumerate(lines[:-1]):
        r = edit_line(l, tab)
        if r is not None:
            lines[i] = r
    return b"\x00".join(lines)
