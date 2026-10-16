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
            return v
    return None


def edit_line(line: bytes, tab) -> bytes | None:
    jp = jptext.decode(line)
    val = _card_value(jp)
    if val is None:
        return None
    tail = b"\x12" if line.endswith(b"\x12") else b""
    rows = val.split("\n")
    wid = max(sum(4 if c == " " else 12 for c in r) for r in rows)  # 카드 한 덩이의 폭(px) — 덩이째 가운데로 민다
    left = max(0, (168 - wid) // 2) // 4 * 4
    pad = chapter._pad(left)
    return b"\x0d".join((pad + tab.enc(r, space=0x60)) if r.strip() else b"" for r in rows) + tail


def edit_chunk(d: bytes, tab) -> bytes:
    lines = d.split(b"\x00")
    for i, l in enumerate(lines[:-1]):
        r = edit_line(l, tab)
        if r is not None:
            lines[i] = r
    return b"\x00".join(lines)
