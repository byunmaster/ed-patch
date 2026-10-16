"""전투 덩이 문구 — 「<몬스터>가 나타났다」와 「<행동한 쪽 이름>의 …」 줄을 정본 battle 틀로 바꾼다.

덩이 꼴(실측): 첫 줄 `[0E]몬스터[0F]が現れた{12}`(이름은 **글 속 리터럴**), 그다음 줄은 이름 라벨(`몬스터{06}Ａ{04}` — 이름 버퍼를 채운다)과
`{1B}…`(**이름 버퍼 출력 + 술어**) 쌍이다. 라벨 줄은 `labels` 가, 여기서는 첫 줄과 `{1B}` 줄을 맡는다.
- 첫 줄: 리터럴 이름이라 조사를 **빌드 때 푼다**(정본 「{name}이(가) 나타났다.」 → 「슬라임이 나타났다.」). 여럿이면 `와/과` 로 잇는다.
- `{1B}` 줄: 정본 틀(`の攻撃` → 「의 공격」 …)과 맞으면 바꾸고, 정본에 없는 몬스터 고유 술어는 원문 그대로 두고 `missing` 에 모은다(관리자 후보).
조사는 정본 병기 꼴 그대로다(행동한 쪽 이름은 런타임 버퍼라 받침을 모른다 — P2 조사 훅 몫).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import jptext
import msgs
import systext
import typeset
from text import josa

APPEAR = "が現れた"
WIDTH_CELLS = 14  # 전투 창 한 줄(12px 14칸 + 반각 공백은 1/3칸)


def _plain(raw: bytes) -> str:
    return jptext.decode(raw).replace("{0E}", "").replace("{0F}", "")


def is_battle_chunk(d: bytes) -> bool:
    first = d.split(b"\x00", 1)[0]
    return APPEAR in _plain(first).replace("\n", "")


def _wrap(text: str) -> list[str] | None:
    pages = typeset.pages(text)
    return pages[0] if len(pages) == 1 else None


def _appear(line: bytes, tab, missing: set) -> bytes:
    toks = systext.tokens(line)
    glyph_at = [k for k, (kind, _b) in enumerate(toks) if kind == "glyph"]
    if not glyph_at:
        return line
    trail = b"".join(b for kind, b in toks[glyph_at[-1] + 1 :] if kind == "ctrl")
    jp = re.sub(r"\{[^}]*\}", "", _plain(line)).replace("\n", "").replace("\u3000", "")
    m = re.match(rf"^(.+?){APPEAR}", jp)
    if not m:
        return line
    names = m.group(1).split("と")
    krs = [canon.lookup(n, "monster", "ed2") for n in names]
    tail = canon.lookup("{name}が現れた。", "battle", "ed2")
    if None in krs or not tail or not tail.startswith("{name}이(가)"):
        missing.add(jp)
        return line
    text = krs[0]
    for prev, nxt in zip(krs, krs[1:], strict=False):
        text = text + josa.josa(prev, "과/와") + nxt
    text = text + josa.josa(krs[-1], "이/가") + tail[len("{name}이(가)") :]
    lines = _wrap(text)
    if lines is None:
        missing.add(jp)
        return line
    return b"\r".join(tab.enc(ln) for ln in lines) + trail


def edit_chunk(d: bytes, tab, missing: set) -> bytes:
    """전투 덩이 한 개의 줄을 바꾼다 — 이미 정본에 있는 것만(없는 술어는 `missing`)."""
    lines = d.split(b"\x00")
    n = len(lines) - 1
    for i in range(n):
        raw = lines[i]
        if i == 0:
            lines[i] = _appear(raw, tab, missing)
            continue
        if not raw.startswith(b"\x1b"):
            continue
        new = msgs.translate(raw, tab, battle=True)
        if new is None:
            missing.add(_plain(raw).replace("\n", "/"))
        else:
            lines[i] = new
    return b"\x00".join(lines)
