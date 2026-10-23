"""원판·한글 짝 대조용 글자 기록 — 롬·RAM 에서 읽은 **실제 바이트**를 쪽 단위 문자열로 디코드한다.

대본 JSON 이 아니라 엔진이 읽는 바이트(씬 모듈 RAM `$FF6650~`, 전투 블록 RAM `$FF20AE~`, 시스템 메시지 ROM)를 읽으므로
배정 어긋남·누락·덮어쓰기·분기 꼬리가 그대로 드러난다. 변수 자리는 `{target}`·`{item}`·`{p:n}`·`{num}`·`{josa}` 꼴.

흐름 규칙(정적 걷기 — 실제 길은 캡처가 보여 준다):
  `01` 줄바꿈 · `05` 쪽 넘김 · `0F` goto 는 따라가고(조건 `11/12/F2/F8` 바로 뒤의 것은 「조건」 표시 뒤 건너뛴 채 그 아래로 이어 읽는다) ·
  `10` call 은 피호출 문안을 그 자리에 끼워 읽고 · `00/06/07/0A/0D` 에서 끝낸다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scene

COND = {0x11, 0x12, 0xF2, 0xF6, 0xF8}
KRQ = {0x60: "“", 0x7E: "”"}  # 반각 따옴표 — hangul.QUOTES_HALF


def _inv() -> dict[int, str]:
    d = json.loads((common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8"))
    return {v: k for k, v in d.items()}


_INV: dict[int, str] | None = None


def decode_text(raw: bytes, kr: bool) -> str:
    global _INV
    if not kr:
        return raw.decode("cp932", "replace")
    if _INV is None:
        _INV = _inv()
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c >= 0x80 and i + 1 < len(raw):
            code = (c << 8) | raw[i + 1]
            ch = _INV.get(code)
            if ch is None:
                try:
                    ch = raw[i : i + 2].decode("cp932")
                except UnicodeDecodeError:
                    ch = f"<{raw[i]:02x}{raw[i + 1]:02x}>"
            out.append(ch)
            i += 2
        else:
            out.append(KRQ.get(c, chr(c)))
            i += 1
    return "".join(out)


def _var(t: scene.Token) -> str | None:
    """변수·조사 토큰 → 표시 문자열. 아니면 None."""
    c = t.code
    if c == 0x02:
        return "{target}"
    if c == 0x09:
        return f"{{p:{t.raw[1]}}}" if len(t.raw) > 1 else "{p}"
    if c == 0x0B:
        return "{leader}"
    if c == 0x0E:
        return "{item}"
    if c == 0x15:
        return "{num}"
    if c in (0xEB, 0xEC):
        return "{josa}"
    return None


def walk_pages(b: bytes, start: int, kr: bool, depth: int = 0, follow06: bool = False) -> list[str]:
    """`start` 의 스트림을 따라가며 쪽별 문자열을 낸다. 조건 분기는 「⟨조건⟩」 표시 뒤 아래로 이어 읽는다.
    follow06 — 전투·시스템 메시지의 `06`(여기서 수치를 끼워 넣고 뒤 바이트로 이어 읽는다)을 「{값}」 표시 뒤 물리적으로 이어 읽는다."""
    pages: list[list[str]] = [[]]
    pos, hops = start, 0
    seen: set[int] = set()
    while hops < 80:
        hops += 1
        if pos in seen or not 0 <= pos < len(b):
            pages[-1].append("⟨끝:범위⟩")
            break
        seen.add(pos)
        try:
            st = scene.parse_stream(b, pos)
        except (ValueError, IndexError):
            pages[-1].append("⟨파싱 실패⟩")
            break
        jump = None
        ended = False
        prev_cond = False
        for t in st.tokens:
            if t.kind == "text":
                pages[-1].append(decode_text(t.raw, kr))
            elif t.kind == "end":
                if follow06 and t.code == 0x06 and depth == 0:
                    pages[-1].append("{값}")
                    jump = st.end
                else:
                    ended = True
            elif t.kind == "ctl":
                c = t.code
                v = _var(t)
                if c == 0x01:
                    pages[-1].append("\n")
                elif c == 0x05:
                    pages.append([])
                elif c == 0x03:
                    pages[-1].append("")  # 시간 이음 — 창 유지
                elif c == 0x1E:
                    pages[-1].append("【")
                elif c == 0x04:
                    pages[-1].append("】")
                elif v is not None:
                    pages[-1].append(v)
                elif c in COND:
                    pages[-1].append("⟨조건⟩")
                    prev_cond = True
                    continue
                elif t.ref == scene.GOTO and t.target is not None:
                    if prev_cond:
                        pass  # 조건 참이면 건너뜀 → 아래로 이어 읽는다
                    else:
                        jump = t.target
                elif t.ref == scene.CALL and t.target is not None and depth < 3:
                    sub = walk_pages(b, t.target, kr, depth + 1)
                    pages[-1].append("".join(sub))
                elif c in (0x08, 0x0C, 0x0D, 0x17, 0x1A, 0x1C):
                    pass
                else:
                    pages[-1].append(f"<{t.raw.hex()}>")
            prev_cond = prev_cond and t.kind == "ctl" and t.code in COND
        if ended or jump is None:
            break
        pos = jump
    # 호출된 조각(depth>0)은 끝 공백을 남긴다 — 「따위가 」 + 「이 몸을」 이 「따위가이」 로 붙어 보여 style 이 공백 누락으로 오판했다(10-21)
    return ["".join(p).replace("\n\n", "\n").strip("\n " if depth == 0 else "\n") for p in pages]
