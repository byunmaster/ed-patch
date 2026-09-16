"""번역 정본 → 씬 블록 바이트 합성.

정본(커밋):
    script/speakers.json      {"侍女": "시녀", …}   화자 이름(JP 는 단어 수준이라 커밋 OK)
    script/scnNNN.json        {"messages": {열쇠: {"t": "우리 문안"}}}   열쇠 = messages.Message.key
        `t` 는 산문. `\\n` 하드 개행 · `\\f` 강제 페이지. 조판은 typeset.pages 가 한다.
JP 원문은 정본에 없다 — `work/derived/messages/scnNNN.json` 이 열쇠↔원문 대조표다(커밋 안 함).

합성: [1F 화자 04 | 09 nn] + (원문이 화자 뒤 01 로 시작했으면 01) + 줄들(01) · 창(05) + 종료(원문 것).
종료가 없는 조각(화자 전환·옵코드 앞에서 끊긴 메시지)은 splice 가 `0F` 로 다음 자리에 잇는다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import messages as M
import typeset

PAGE = 0x05
NL = 0x01


class TranslateError(Exception):
    pass


def all_glyph_chars() -> set[str]:
    """정본 전체가 쓰는 우리 글리프 글자(한글·부호·숫자) — 글리프 표는 여기서 결정적으로 나온다."""
    chars = set()
    for p in sorted(M.SCRIPT_DIR.glob("scn*.json")):
        for e in json.loads(p.read_text())["messages"].values():
            chars |= {ch for ch in e["t"] if font.needs_glyph(ch)}
    # 🔑 **화면에 나가는 표기만** 공용에서 받는다(`kr_texts`) — 열쇠도 `_aliases` 도 안 온다.
    #    ⚠ `load_speakers()` 는 **맵**이라 조판이 쓰고, 글리프 커버리지는 이쪽이다.
    import glossary as G  # shared/

    for v in list(G.kr_texts()) + list(M.load_speaker_overrides().values()):
        chars |= {ch for ch in v if font.needs_glyph(ch)}
    return chars


def compose(m: M.Message, tr: dict, table: dict[str, bytes], speakers: dict[str, str]) -> bytes:
    out = bytearray()
    if m.speaker is not None:
        name = speakers.get(m.speaker, m.speaker)
        out += b"\x1f" + font.encode(name, table) + b"\x04"
    elif m.common is not None:
        out += bytes([0x09, m.common])
    lead_nl = bool(m.tokens) and m.tokens[0] == ("op", NL)
    if lead_nl:
        out.append(NL)
    pgs = typeset.pages(tr["t"], speaker=m.speaker is not None or m.common is not None)
    for i, pg in enumerate(pgs):
        if i:
            out.append(PAGE)
        for j, line in enumerate(pg):
            # 🔴 **틀을 꽉 채운 줄 뒤에는 개행을 안 넣는다** — 인터프리터가 열 ≥ $99(13)에서 스스로
            #    넘기므로 우리 `01` 이 얹히면 **빈 줄**이 된다(our-findings 2026-08-30, PS1 이 122곳).
            if j and len(pg[j - 1]) < typeset.WIDTH:
                out.append(NL)
            out += font.encode(line, table)
    if m.terminated:
        out.append(m.tokens[-1][1])
    elif m.tokens and m.tokens[-1] in (("op", PAGE), ("op", 0x03)):
        # 화자 전환 앞의 페이지 옵코드는 원문 흐름의 일부다 — 빼먹으면 다음 화자가 같은 창에 이어 붙는다(실측)
        out.append(m.tokens[-1][1])
    return bytes(out)


def translate_block(scene_id: int, block: bytes, table: dict[str, bytes]) -> tuple[bytes, int]:
    """번역이 있는 메시지를 합성해 splice. (새 블록, 넣은 메시지 수)."""
    trs = M.load_translations(scene_id)
    if not trs:
        return block, 0
    speakers = M.load_speakers()
    msgs = M.parse(block)
    edits = []
    seen = set()
    for m in msgs:
        tr = trs.get(m.key)
        if tr is None and m.speaker in speakers and not m.jp:
            tr = {
                "t": ""
            }  # 이름만 있는 메시지(이벤트 코드가 화자 표시용으로 부른다) — speakers.json 으로 자동
        if tr is None:
            continue
        if m.pinned:
            raise TranslateError(
                f"scn {scene_id} 열쇠 {m.key}: pinned(안쪽 참조) — 자리 규칙으로 못 넣는다"
            )
        edits.append((m, compose(m, tr, table, speakers)))
        seen.add(m.key)
    missing = set(trs) - seen
    if missing:
        raise TranslateError(
            f"scn {scene_id}: 정본 열쇠 {sorted(missing)} 가 블록에 없다(원문이 바뀌었나)"
        )
    return M.splice(block, edits), len(edits)
