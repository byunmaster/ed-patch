"""씬 모듈(대본 아카이브 블록) 모델 — 코드 · 자료 · **문안 스트림**이 한 덩이에 섞여 있다.

    python3 tools/scene.py --check     # 225블록: 스트림 수 · 화자 태그 도달률 · 미지 코드
    python3 tools/scene.py --dump N    # 블록 N 의 스트림을 사람이 읽게

모듈은 RAM 0xFF6650 에 통째로 놓인다(`$18460`). 문안은 코드가 `lea x(pc),a1` 로 가리키고
(메시지 함수 a5 = 85E2/85E3/85DC/85E4 …), 렌더러 `$978C` 가 스트림을 읽는다. 스트림 안에는
**문안 상대 오프셋**을 가진 제어코드가 있다(핸들러 실측 — 오프셋 기준은 첫 인자 바이트 자리):

    0F hh ll   goto(16비트)          — 스트림이 거기로 이어진다
    10 hh ll   call(렌더 재귀)       — 대상은 스트림. `10 8644` 만 특수($FF3644 동적 문자열)
    15 hh ll   모듈 코드 호출 / hh = 8x 이면 엔진 함수(a5 = hh ll & 7FFF)
    F2 hh ll   셀 비교 → 조건부 3B 건너뜀     F3 hh ll  셀 설정
    F5 00 hh ll vv / F5 nn AAAAAAAA vv   셀에 1B 쓰기(상대 / 절대)
    FB 00 hh ll vvvv / FB nn AAAAAAAA vvvv 셀에 2B 쓰기
    11·12 xx xx 플래그 검사 → 조건부 3B 건너뜀   F8 xx 조건부 3B 건너뜀   13·14 xx xx 플래그
그 밖의 인자 길이는 렌더러 표 `$9FE2` 그대로(ARGS). 뜻을 모르는 코드는 **길이만 알고 raw 로** 둔다.

재조립 방침(docs/status.md 3절): 원본 바이트는 전부 제자리에 두고(코드·자료·셀·옛 문안), 번역된
스트림을 **모듈 끝에 덧붙인 뒤** 그 스트림을 가리키는 lea 변위와 스트림 간 오프셋(0F·10)만 다시
쓴다. 셀(F2·F3·F5·FB)과 코드(15)는 안 움직이므로 새 자리에서의 상대 오프셋만 재계산한다.
"""

import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LOAD = 0xFF6650  # 모듈 로드 주소
MODULE_MAX = 0x4000  # 0xFFA650 이 다음 버퍼(엔진 참조 3곳) — 미확정, 실측 최대 모듈 11,562B

# 인자 길이 — 렌더러 `$9FE2` 표. 00~1F 직접, EB~FF 는 -0xCB.
_ARGS_LO = [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    2,
    0,
    0,
    0,
    2,
    2,
    2,
    2,
    2,
    2,
    10,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
]
_ARGS_HI = {
    0xEB: 0,
    0xEC: 0,
    0xED: 4,
    0xEE: 1,
    0xEF: 1,
    0xF0: 1,
    0xF1: 1,
    0xF2: 2,
    0xF3: 2,
    0xF4: 3,
    0xF5: 0,
    0xF6: 2,
    0xF7: 0,
    0xF8: 3,
    0xF9: 3,
    0xFA: 0,
    0xFB: 0,
    0xFC: 1,
    0xFD: 1,
    0xFE: 1,
    0xFF: 1,
}
ARGS = {**{i: n for i, n in enumerate(_ARGS_LO)}, **_ARGS_HI}
# ⚠ 0F 는 표에선 0 이지만 핸들러가 2B 를 읽고 그리로 간다(goto). F8 은 표에선 1 인데 핸들러가 (a1)+ 로
#   하나를 더 읽고 조건부로 3 을 건너뛴다 — 여기선 「최소 길이」만 정적으로 세고 나머지는 흐름으로 본다.
ARGS[0x0F] = 2
ARGS[0xF8] = 1

GOTO, CALL, CELL, CODE = "goto", "call", "cell", "code"
COND = {0x11, 0x12, 0xF2, 0xF8}  # 다음 3B(대개 0F goto)를 조건부로 건너뛴다
# 렌더 한 번을 끝내는 코드 — 00(창 닫기) · 06(그냥 반환) · 07(개행 + 대기 + 반환). 메시지 함수
# `$60A0` 은 렌더러 `$978C` 를 한 번만 부르므로 이 셋이 곧 스트림의 끝이다. 05 는 페이지 넘김(계속).
END = {0x00, 0x06, 0x07}
REL16 = {0x0F: GOTO, 0x10: CALL, 0x15: CODE, 0xF2: CELL, 0xF3: CELL}

SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){1,8})\x04")


@dataclass
class Token:
    off: int  # 모듈 안 오프셋
    raw: bytes
    kind: str = "text"  # text | ctl | end
    code: int = -1
    ref: str | None = None  # goto/call/cell/code
    target: int = -1  # 모듈 안 오프셋(참조가 있을 때)

    @property
    def argpos(self) -> int:
        return self.off + 1


@dataclass
class Stream:
    start: int
    tokens: list[Token] = field(default_factory=list)
    end: int = -1  # 00 다음(또는 goto 뒤) 오프셋

    def text(self) -> str:
        out = []
        for t in self.tokens:
            if t.kind == "text":
                out.append(t.raw.decode("cp932", "replace"))
            elif t.kind == "end":
                out.append(f"<{t.code:02x}|끝>")
            else:
                s = f"<{t.raw.hex()}"
                if t.ref:
                    s += f"→{t.ref}:{t.target:#x}"
                out.append(s + ">")
        return "".join(out)


def is_lead(c: int) -> bool:
    return 0x80 <= c <= 0x9F or 0xE0 <= c <= 0xEA


def parse_stream(b: bytes, start: int) -> Stream:
    """`start` 부터 00 또는 goto 까지 토큰으로 가른다. 모듈 끝을 넘으면 ValueError."""
    st = Stream(start)
    p = start
    while True:
        if p >= len(b):
            # 모듈 끝에서 06/07 로 끝나는 스트림이 69개 있다(렌더러가 거기서 돌아온다) — 끝으로 친다
            st.tokens.append(Token(p, b"", "eof"))
            st.end = p
            return st
        c = b[p]
        if c in END:
            st.tokens.append(Token(p, bytes([c]), "end", c))
            st.end = p + 1
            return st
        if c < 0x20 or c >= 0xEB:
            n = ARGS[c]
            if c == 0xF5:
                n = 4 if b[p + 1] == 0 else 6
            elif c == 0xFB:
                n = 5 if b[p + 1] == 0 else 7
            raw = b[p : p + 1 + n]
            t = Token(p, raw, "ctl", c)
            if c in REL16:
                off = struct.unpack(">h", raw[1:3])[0]
                # ⚠ 음수 오프셋(0x9000~0xFFFF)도 상위비트가 선다 — 15 는 `$A32E` 대로 상위 니블이 딱 8 일 때만
                #   엔진 함수, 10 은 `$A2AE` 대로 정확히 8644 만 특수(동적 문자열 $FF3644)
                if (c == 0x15 and raw[1] & 0xF0 == 0x80) or (c == 0x10 and raw[1:3] == b"\x86\x44"):
                    t.ref = None
                else:
                    t.ref, t.target = REL16[c], t.argpos + off
            elif c in (0xF5, 0xFB) and raw[1] == 0:
                t.ref, t.target = CELL, t.argpos + 1 + struct.unpack(">h", raw[2:4])[0]
            st.tokens.append(t)
            p += 1 + n
            if c == 0x0F:
                st.end = p
                return st
            continue
        if is_lead(c):
            q = p + 2
        else:
            q = p + 1
        # 연속 글자는 한 토큰으로
        while q < len(b) and not (b[q] < 0x20 or b[q] >= 0xEB):
            q += 2 if is_lead(b[q]) else 1
        st.tokens.append(Token(p, b[p:q], "text"))
        p = q


MSG_IDS = {0x85E3, 0x85E2, 0x85DC, 0x85E4, 0x0403, 0x8421, 0x8422, 0x04B3}  # 문안을 a1 로 받는 a5
# 표 참조 — `lea T(pc),a6; move.w (a6,d2.w),d2; lea B(pc),a6; lea (a6,d2.w),a1; movea.w #MSG,a5`
# 표 항목(BE16) = B 기준 오프셋(실측 B = 모듈 시작). 블록 83·84 의 선택지 문안 4개씩(2026-09-05).
TABLE_PAT = re.compile(
    rb"\x4d\xfa(..)\x34\x36\x20\x00\x4d\xfa(..)\x43\xf6\x20\x00\x3a\x7c(..)", re.DOTALL
)


def _textlike(st: Stream) -> bool:
    """내용으로 본 문안 — 화자 태그가 있거나 SJIS 전각이 3자 이상. 자료 포인터가 파싱된 쓰레기
    (`D<00>` · `<06><00>` · 0x80 섞인 바이트)는 여기서 걸러진다(실측 529건)."""
    if any(t.code == 0x1E for t in st.tokens):
        return True
    sj = sum(1 for t in st.tokens if t.kind == "text" for c in t.raw if is_lead(c))
    return sj >= 3


def lea_roots(b: bytes) -> dict[int, int]:
    """`lea x(pc),a1` 중 문안 뿌리 (명령 오프셋 → 스트림 시작).
    (a) 바로 뒤(또는 `46DF` 하나 건너)에 `movea.w #MSG,a5` 가 오거나, (b) 가리키는 곳이 내용상 문안.
    ⚠ 뒤에 `46DF` 만 오고 내용이 쓰레기인 529건은 **자료 포인터**다 — 옮기면 코드가 엉뚱한 자료를 읽는다."""
    roots = {}
    for m in re.finditer(rb"\x43\xfa(..)(\x46\xdf)?(?:\x3a\x7c(..))?", b, re.DOTALL):
        disp = struct.unpack(">h", m.group(1))[0]
        t = m.start() + 2 + disp
        if not 0 <= t < len(b):
            continue
        by_id = m.group(3) is not None and struct.unpack(">H", m.group(3))[0] in MSG_IDS
        if not by_id:
            try:
                if not _textlike(parse_stream(b, t)):
                    continue
            except (ValueError, IndexError):
                continue
        roots[m.start()] = t
    return roots


@dataclass
class TableRef:
    word: int  # 표 항목(BE16) 자리
    base: int  # 오프셋 기준
    target: int


def table_roots(b: bytes) -> list[TableRef]:
    """표 참조 스트림 — 항목은 「기준 + 값이 문안 스트림」인 동안 센다(표 끝 표식이 없다)."""
    out = []
    for m in TABLE_PAT.finditer(b):
        tbl = m.start() + 2 + struct.unpack(">h", m.group(1))[0]
        base = m.start() + 10 + struct.unpack(">h", m.group(2))[0]
        p = tbl
        while p + 2 <= len(b) and len(out) < 256:
            t = base + struct.unpack(">H", b[p : p + 2])[0]
            if not 0 <= t < len(b):
                break
            try:
                if not _textlike(parse_stream(b, t)):
                    break
            except (ValueError, IndexError):
                break
            out.append(TableRef(p, base, t))
            p += 2
    return out


@dataclass
class Module:
    data: bytes
    roots: dict[int, int]  # lea 명령 오프셋 → 스트림 시작
    streams: dict[int, Stream]  # 시작 오프셋 → 스트림
    bad_roots: list[int]
    cells: set[int]
    codes: set[int]
    bad_refs: list[int]  # goto/call 대상인데 파싱이 안 된 자리 — 재조립 전에 풀어야 한다
    tables: list[TableRef] = field(default_factory=list)


def looks_like_text(st: Stream) -> bool:
    """뿌리 후보가 스트림인가 — 글자가 있거나, 참조(goto/call/셀/코드)가 있거나, 화자 태그가 있다.
    ⚠ `12 xxxx 0F yyyy` 처럼 제어코드뿐인 분기 허브도 스트림이다 — 글자만 보면 버려진다(실측 142건)."""
    n = sum(len(t.raw) for t in st.tokens if t.kind == "text")
    return n >= 2 or any(t.ref or t.code == 0x1E for t in st.tokens)


def parse_module(b: bytes) -> Module:
    roots = lea_roots(b)
    tables = table_roots(b)
    streams: dict[int, Stream] = {}
    bad: list[int] = []
    cells: set[int] = set()
    codes: set[int] = set()
    badref: list[int] = []
    work = []
    for ins, t in roots.items():
        try:
            st = parse_stream(b, t)
        except ValueError:
            bad.append(ins)
            continue
        work.append(t)
    work += [tr.target for tr in tables]
    seen = set()
    while work:
        t = work.pop()
        if t in seen:
            continue
        seen.add(t)
        try:
            st = parse_stream(b, t)
        except (ValueError, IndexError):
            badref.append(t)
            continue
        streams[t] = st
        # 조건부(11·12·F2·F8) 뒤의 goto 는 「3B 건너뜀」으로 넘어갈 수 있다 — 그 뒤도 뿌리다
        if len(st.tokens) >= 2 and st.tokens[-1].code == 0x0F and st.tokens[-2].code in COND:
            work.append(st.end)
        for tok in st.tokens:
            if tok.ref in (GOTO, CALL):
                work.append(tok.target)
            elif tok.ref == CELL:
                cells.add(tok.target)
            elif tok.ref == CODE:
                codes.add(tok.target)
    return Module(
        b,
        {i: t for i, t in roots.items() if i not in bad},
        streams,
        bad,
        cells,
        codes,
        badref,
        tables,
    )


def coverage(mod: Module) -> tuple[int, int]:
    """(화자 태그 수, 그중 스트림 안에 있는 수)."""
    cov = bytearray(len(mod.data))
    for st in mod.streams.values():
        for t in st.tokens:
            cov[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    tags = list(SPEAKER.finditer(mod.data))
    return len(tags), sum(1 for m in tags if cov[m.start()])


# ── 재조립 ─────────────────────────────────────────────────────────────────────


def _emit_stream(tokens: list[Token]) -> int:
    return sum(len(t.raw) for t in tokens) + (1 if tokens and tokens[-1].kind == "eof" else 0)


def reassemble(
    mod: Module, replace: dict[int, list[Token]] | None = None, *, zero_dead: bool = True
) -> bytes:
    """원본 바이트는 제자리에 두고, 도달 가능한 스트림 전부를 **끝에 다시 쓴다**.

    replace = {스트림 시작: 새 토큰 목록}. 제어 토큰은 raw 그대로 두고 text 토큰만 바꾸는 게 원칙 —
    참조(ref/target)는 원본 토큰의 것을 그대로 쓴다. 옮긴 스트림을 가리키는 것: 뿌리 lea 변위 ·
    goto/call 오프셋. 안 옮기는 것(셀·코드)은 새 자리에서의 상대 오프셋만 다시 잰다.
    스트림이 모듈 끝(eof)으로 끝났으면 00 을 붙인다 — 뒤에 이어 쓰는 스트림으로 새지 않게.
    """
    replace = replace or {}
    covered = bytearray(len(mod.data))
    for st in mod.streams.values():
        for t in st.tokens:
            covered[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    for ins in mod.roots:
        if covered[ins]:
            raise ValueError(
                f"뿌리 lea 가 문안 안에 있다 @{ins:#x} — 우연한 43 FA 다, 뿌리 규칙을 손봐야 한다"
            )
    b = bytearray(mod.data)
    if zero_dead:
        # 옮긴 스트림의 옛 바이트는 죽은 자리다 — 0 으로 지우면 LZ 의 RLE 가 거의 공짜로 눌러
        # 아카이브가 원본 크기로 돌아온다(문안을 두 벌 들고 가지 않는다). 셀·코드는 스트림 밖이라 안 건드린다.
        for st in mod.streams.values():
            for t in st.tokens:
                b[t.off : t.off + len(t.raw)] = b"\x00" * len(t.raw)
    if len(b) & 1:
        b.append(0)
    order = sorted(mod.streams)
    toks = {s: replace.get(s, mod.streams[s].tokens) for s in order}
    # 1. 새 자리
    pos = {}
    cur = len(b)
    for s in order:
        pos[s] = cur
        cur += _emit_stream(toks[s])
    if cur > MODULE_MAX:
        raise ValueError(f"모듈이 {cur}B — 한도 {MODULE_MAX}B 를 넘는다")
    # 2. 내보내기
    out = bytearray()
    for s in order:
        for t in toks[s]:
            if t.ref is None:
                out += t.raw
                continue
            raw = bytearray(t.raw)
            tgt = pos.get(t.target, t.target) if t.ref in (GOTO, CALL) else t.target
            here = len(b) + len(out)
            if t.code in (0xF5, 0xFB):
                rel = tgt - (here + 2)
                raw[2:4] = struct.pack(">h", rel)
            else:
                rel = tgt - (here + 1)
                raw[1:3] = struct.pack(">h", rel)
            out += raw
        if toks[s] and toks[s][-1].kind == "eof":
            out.append(0)
    b += out
    # 3. 표 항목
    for tr in mod.tables:
        v = pos[tr.target] - tr.base
        if not 0 <= v < 0x10000:
            raise ValueError(f"표 오프셋 범위 초과 @{tr.word:#x}")
        b[tr.word : tr.word + 2] = struct.pack(">H", v)
    # 4. 뿌리 lea 변위
    for ins, s in mod.roots.items():
        disp = pos[s] - (ins + 2)
        if not -0x8000 <= disp < 0x8000:
            raise ValueError(f"lea 변위 범위 초과 @{ins:#x}")
        b[ins + 2 : ins + 4] = struct.pack(">h", disp)
    return bytes(b)


def verify_reassembly(
    orig: Module, new_bytes: bytes, replace: dict[int, list[Token]] | None = None
) -> None:
    """다시 파싱해 스트림별 토큰(raw 텍스트 + 제어코드 종류)이 의도와 같은지 본다."""
    replace = replace or {}
    new = parse_module(new_bytes)
    # 덧붙인 문안 바이트 안에서 우연히 `43 FA` 가 lea 로 읽힐 수 있다 — 원본 뿌리 자리만 맞댄다
    if any(ins not in new.roots for ins in orig.roots):
        raise ValueError("원본 뿌리가 새 모듈에서 사라졌다")
    if len(new.tables) != len(orig.tables):
        raise ValueError(f"표 항목 수가 갈렸다 {len(orig.tables)} → {len(new.tables)}")
    remap = {}
    for ins, s in orig.roots.items():
        remap[s] = new.roots[ins]
    for a, c in zip(orig.tables, new.tables, strict=True):
        remap[a.target] = c.target
    for s, st in orig.streams.items():
        want = replace.get(s, st.tokens)
        # 뿌리가 아닌 스트림(goto/call 대상)은 뿌리에서 참조를 따라간 새 파서가 이미 품고 있다 —
        # 여기선 뿌리 스트림만 맞대고, 나머지는 참조 그래프가 같은지로 본다(아래 개수 비교)
        if s not in remap:
            continue
        got = new.streams[remap[s]]
        a = [
            (t.kind, t.code, t.raw if t.kind == "text" else t.raw[:1])
            for t in want
            if t.kind != "eof"
        ]
        g = [
            (t.kind, t.code, t.raw if t.kind == "text" else t.raw[:1])
            for t in got.tokens
            if t.kind != "eof"
        ]
        if want and want[-1].kind == "eof":
            a.append(("end", 0, b"\x00"))
        if a != g:
            k = next(
                (i for i, (x, y) in enumerate(zip(a, g, strict=False)) if x != y),
                min(len(a), len(g)),
            )
            raise ValueError(
                f"스트림 @{s:#x} 토큰 {k} 이 의도와 다르다\n  want {a[k : k + 3]}\n  got  {g[k : k + 3]}"
            )
    if len(new.streams) < len(orig.streams):
        raise ValueError(f"스트림 수가 줄었다 {len(orig.streams)} → {len(new.streams)}")


if __name__ == "__main__":
    import archives
    import common

    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    if "--dump" in sys.argv:
        n = int(sys.argv[sys.argv.index("--dump") + 1])
        mod = parse_module(bl[n][1])
        for s in sorted(mod.streams):
            print(f"--- @{s:#x}\n{mod.streams[s].text()}")
        print(
            "cells", sorted(hex(c) for c in mod.cells), "codes", sorted(hex(c) for c in mod.codes)
        )
    else:
        tot = {"streams": 0, "tags": 0, "hit": 0, "bad": 0, "cells": 0, "codes": 0, "badref": 0}
        worst = []
        for i, (_, b, _) in enumerate(bl):
            mod = parse_module(b)
            tags, hit = coverage(mod)
            tot["streams"] += len(mod.streams)
            tot["tags"] += tags
            tot["hit"] += hit
            tot["bad"] += len(mod.bad_roots)
            tot["cells"] += len(mod.cells)
            tot["codes"] += len(mod.codes)
            tot["badref"] += len(mod.bad_refs)
            if mod.bad_refs:
                worst.append((-len(mod.bad_refs), i, [hex(x) for x in mod.bad_refs[:3]]))
            if tags - hit:
                worst.append((tags - hit, i))
        print(
            f"  스트림 {tot['streams']} · 화자 태그 {tot['hit']}/{tot['tags']} 도달 · 뿌리 탈락 {tot['bad']} · "
            f"셀 {tot['cells']} · 코드 호출 {tot['codes']} · 참조 파싱 실패 {tot['badref']}"
        )
        print("  미도달·실패 블록:", sorted(worst, key=lambda x: -abs(x[0]))[:12])
        if (tot["streams"], tot["hit"], tot["tags"], tot["badref"]) != (2752, 1425, 1437, 0):
            raise SystemExit("씬 모듈 분모가 갈렸다 (기대 2752 스트림 · 1425/1437 · 실패 0)")
        biggest = 0
        for _, b, _ in bl:
            mod = parse_module(b)
            new = reassemble(mod)
            verify_reassembly(mod, new)
            biggest = max(biggest, len(new))
        if biggest > MODULE_MAX:
            raise SystemExit(f"항등 재조립 모듈이 한도를 넘는다 {biggest}")
        print(f"  항등 재조립 225블록 검증 OK (최대 {biggest:,}B / 한도 {MODULE_MAX:,}B)")
