"""sfc-ed2 번역 조각(segment) — 대사 단위를 「글자 구간」으로 쪼갠 번역·재삽입의 최소 단위.

한 메시지 단위(`script.units`)는 구조 토큰(플래그 검사 `$11~$14`·점프 `$0F`·네이티브 호출 `$15`·`$F0~` 스크립트·끝 `$00`…)과
**글자 구간**으로 이뤄진다. 글자 구간 = 글자·반각·줄바꿈($01)·키대기($02 $05 $08)·색($04 $18~$1F)·사전 참조($E0/$E1) 만으로 된 연속 토큰.
번역은 구간마다 따로 하고(`textmap/segments.json`, 키 = 구간 시작 주소), 재삽입은 구간 첫머리를 트램펄린(`build.py`)으로 돌린다 —
구조 토큰은 한 바이트도 안 건드리므로 조건·점프 구조가 그대로다.

표기(원문·번역 공통): 글자는 그대로, 줄바꿈 $01 = 실제 개행, 그 밖의 비구조 제어 = `<hh>`(예 `<05>` `<1e>`), 사전 참조 = `<E0:12>` `<E1:3>`.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import glyphmap
import script

TEXTLEVEL = (
    set(range(0x20, 0xE2))  # 반각·전각·1바이트 글자·사전 $E0 $E1 은 아래서 따로
    | {1, 2, 4, 5, 8}
    | set(range(0x18, 0x20))
    | set(range(0xE2, 0xF0))
)


def is_char(b: int) -> bool:
    return (0x20 < b < 0xE0) or (0xE2 <= b < 0xF0)


def jump_targets(d: bytes) -> set[int]:
    """다른 곳에서 **들어오는** 자리(파일 오프셋) — 점프 `$0F`·호출 `$10` 의 목적지, 코드의 `$A6` 즉치 포인터. 구간은 이 자리에서 끊어야 한다
    (공유 꼬리 — 「会心」+점프 → 「痛恨の一撃」 한가운데 — 를 구간 통째로 바꾸면 점프가 옛 바이트 한가운데로 떨어진다)."""
    out = set()
    for s, e in script.all_units(d):
        bank = (common.off2snes(s) >> 16) & 0xFF
        for o, _ln in script.tokens(d, s, e):
            if d[o] in (0x0F, 0x10) and o + 2 < len(d):
                out.add(common.snes2off((bank << 16) | d[o + 1] | d[o + 2] << 8))
    for p in script.a6_targets(d):
        out.add(common.snes2off(p))
    return out


# 다른 종류(textmap ptrs16·dict·spans·records·cells·ui)가 번역하는 자리 — 대사 구간에서 뺀다. (SNES 주소 시작·끝, 끝 미포함)
EXCLUDE = (
    (0xCB3175, 0xCB3469),  # 지역명 표(ptrs16 `$CB:30E9`)
    (0xCB3563, 0xCB3869),  # `$E0` 이름 사전(정본에서) · `$E1` 포인터 표 앞 잡음
    (0xCB3AB0, 0xCB3D00),  # 문구 풀 뒤 잡음(그래픽·표 데이터)
    (0xCB6890, 0xCB6950),  # 저장·로드 안내(spans)
    (0xCB6AB0, 0xCB6AF0),  # 장 번호 라벨(spans)
    (0xCB8C00, 0xCBB000),  # 몬스터 이름 풀(③ 전투에서 따로)
)


def excluded(off: int) -> bool:
    return any(common.snes2off(a) <= off < common.snes2off(b) for a, b in EXCLUDE)


def jump_sources(d: bytes) -> dict[int, list[int]]:
    """점프 목적지(파일 오프셋) → 그 점프를 거는 자리 바로 앞 글자 구간의 시작들. 번역이 앞 조각과 이어지는지 볼 때 쓴다(공유 꼬리 문장)."""
    out: dict[int, list[int]] = {}
    for s, e in script.all_units(d):
        bank = (common.off2snes(s) >> 16) & 0xFF
        last = None
        cur = None
        for o, ln in script.tokens(d, s, e):
            b = d[o]
            if b in TEXTLEVEL or b in (0xE0, 0xE1):
                if cur is None:
                    cur = o
                last = cur
            else:
                if b in (0x0F, 0x10) and o + 2 < len(d) and last is not None:
                    tgt = common.snes2off((bank << 16) | d[o + 1] | d[o + 2] << 8)
                    out.setdefault(tgt, []).append(last)
                cur = None
    return out


def segments(d: bytes) -> list[tuple[int, int]]:
    """(시작, 끝) 파일 오프셋 — 글자가 하나 이상 든 글자 구간만."""
    out = []
    tg = jump_targets(d)
    for s, e in script.all_units(d):
        if excluded(s):
            continue
        cur = None
        for o, ln in script.tokens(d, s, e):
            b = d[o]
            if o in tg and cur is not None and o != cur[0]:  # 들어오는 자리에서 끊는다
                if cur[2]:
                    out.append((cur[0], cur[1]))
                cur = None
            if b in TEXTLEVEL or b in (0xE0, 0xE1):
                if cur is None:
                    cur = [o, o + ln, False]
                cur[1] = o + ln
                cur[2] = cur[2] or is_char(b)
            else:
                if cur and cur[2]:
                    out.append((cur[0], cur[1]))
                cur = None
        if cur and cur[2]:
            out.append((cur[0], cur[1]))
    return [r for r in (_clean(d, a, b, tg) for a, b in out) if r]


def _clean(d: bytes, a: int, b: int, tg: set[int] | None = None) -> tuple[int, int] | None:
    """코드 곁 인라인 문자열의 잡음을 걷는다 — 바로 앞 명령(`28 6B` = plp·rtl 등)이 `(k` 로 읽혀 구간 앞에 붙는다. 대사 뱅크($C2~$CA)와 $C0·$C1 은 그대로.
    그 밖의 뱅크는 ① 들어오는 자리(`$A6` 즉치·점프 목적지)에서 시작하는 구간만 인정하거나 ② 앞머리 영문·부호 잡음을 건 뒤 글자(전각·반각 가나)가 넷 이상이고
    영문·부호가 없는 구간만 인정한다."""
    bank = (common.off2snes(a) >> 16) & 0xFF
    if 0xC2 <= bank <= 0xCA or bank <= 0xC1:
        return (a, b)
    if 0xCC <= bank <= 0xD3:  # 그래픽·표 데이터 — 글자 구간이 아니다(잡음만 걸린다)
        return None
    if tg is not None and a in tg:
        return (a, b)
    # 앞머리 잡음: 앞 8토큰 안의 마지막 영문·부호 토큰 뒤에서 시작
    toks, j = [], a
    while j < b:
        ln = script.token_len(d, j) or 1
        toks.append((j, d[j]))
        j += ln
    cut = -1
    for k, (_o, t) in enumerate(toks[:8]):
        if 0x21 <= t <= 0x7F:
            cut = k
    start = toks[cut + 1][0] if cut + 1 < len(toks) else b
    g = asc = 0
    for o, t in toks:
        if o < start:
            continue
        if 0x80 <= t < 0xE0:
            g += 1
        elif 0x21 <= t <= 0x7F:
            asc += 1
    if g < 4 or asc:
        return None
    # 시작 앞의 1바이트 가나 한두 개(`チ` 등 코드 조각)는 영문 잡음 바로 뒤가 아니면 남는다 — 그 경우만 걷는다
    return (start, b)


def seg_id(off: int) -> str:
    return f"${common.off2snes(off):06X}"


def src_hash(d: bytes, a: int, b: int) -> str:
    return hashlib.sha1(d[a:b]).hexdigest()[:8]


def notation(d: bytes, a: int, b: int) -> str:
    """구간 원문 표기(사람이 읽는 JP)."""
    out, i = [], a
    while i < b:
        t = d[i]
        ln = script.token_len(d, i)
        if ln is None:
            out.append(f"<{t:02x}?>")
            break
        if 0x80 <= t < 0x88 or 0xE2 <= t < 0xF0:
            out.append(script.glyph_char((t << 8) | d[i + 1]))
        elif 0x20 <= t < 0x80:
            out.append(chr(t))
        elif 0x88 <= t < 0xE0:
            out.append(glyphmap.HALF_TABLE[t - 0x88])
        elif t in (0xE0, 0xE1):
            out.append(f"<E{t - 0xE0}:{d[i + 1]}>")
        elif t == 1:
            out.append("\n")
        else:
            out.append(f"<{t:02x}>")
        i += ln
    return "".join(out)


if __name__ == "__main__":
    common.verify_originals()
    d = common.rom_bytes()
    sg = segments(d)
    short = sum(1 for a, b in sg if b - a < 4)
    print(f"글자 구간 {len(sg):,}개 · 4바이트 미만 {short}개(트램펄린 불가 — 제자리 치환만)")
