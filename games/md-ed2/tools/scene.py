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

import itertools
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reloc_ledger as RL  # noqa: E402

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
# 우리가 연 조사 코드 — 원본 표에선 인자 0(핸들러가 rts 뿐인 빈 코드)이지만 빌드가 1 로 고친다.
# 원본 문안엔 한 번도 안 나오므로 파서를 미리 1 로 맞춰 둬도 원본 파싱은 그대로다(`tools/josa.py`).
ARGS[0xEB] = 1
ARGS[0xEC] = 1

GOTO, CALL, CELL, CODE = "goto", "call", "cell", "code"
COND = {0x11, 0x12, 0xF2, 0xF6, 0xF8}  # 다음 3B(대개 0F goto)를 조건부로 건너뛴다
# 렌더 한 번을 끝내는 코드 — 00(창 닫기) · 06(그냥 반환) · 07(개행 + 대기 + 반환). 메시지 함수
# `$60A0` 은 렌더러 `$978C` 를 한 번만 부르므로 이 셋이 곧 스트림의 끝이다. 05 는 페이지 넘김(계속).
END = {
    0x00,
    0x06,
    0x07,
    0x0A,
    0x0D,
}  # 0D($A22C)·0A($A202) 핸들러는 07 핸들러로 끝난다 — 0A 는 「대기·계속」이 아니라 끝(2026-09-05 전투 블록에서 확정)
REL16 = {0x0F: GOTO, 0x10: CALL, 0x15: CODE, 0xF2: CELL, 0xF3: CELL}

SPEAKER = re.compile(
    rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|\x20){1,12})\x04"
)  # 이름 안 반각 공백 허용(「教育係 ラウエル」)


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
                # ED2: F3 80xx = 램 절대 셀($FFFF80xx, 부호 확장된 짧은 절대 주소) — 상대 오프셋이 아니다
                if (
                    (c == 0x15 and raw[1] & 0xF0 == 0x80)
                    or (c == 0x10 and raw[1:3] == b"\x86\x44")
                    or (c in (0xF2, 0xF3) and raw[1] == 0x80)
                ):
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


KANA_RUN = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){2,}")
SLOT_TABLE = re.compile(rb"(?:[\x20-\x7e\x81-\x9f\xe0-\xea\x40-\xfc]{14}\x07){3,}")
LEA_A1 = b"\x43"
LEA_OTHER = (
    b"\x41\x45\x47\x49\x4b\x4d"  # a0 a2 a3 a4 a5 a6 — 대사 상점 따위가 a3·a6 로 문안을 가리킨다
)


def lea_roots(
    b: bytes, force: frozenset[int] | set[int] | None = None, regs: bytes = LEA_A1
) -> dict[int, int]:
    """`lea x(pc),a1` 중 문안 뿌리 (명령 오프셋 → 스트림 시작).
    (a) 바로 뒤(또는 `46DF` 하나 건너)에 `movea.w #MSG,a5` 가 오거나, (b) 가리키는 곳이 내용상 문안.
    ⚠ 뒤에 `46DF` 만 오고 내용이 쓰레기인 529건은 **자료 포인터**다 — 옮기면 코드가 엉뚱한 자료를 읽는다."""
    roots = {}
    pat = rb"[" + regs + rb"]\xfa(..)(\x46\xdf)?(?:\x3a\x7c(..))?"
    for m in re.finditer(pat, b, re.DOTALL):
        disp = struct.unpack(">h", m.group(1))[0]
        t = m.start() + 2 + disp
        if not 0 <= t < len(b):
            continue
        by_id = m.group(3) is not None and struct.unpack(">H", m.group(3))[0] in MSG_IDS
        # `force` = 원본에서 이미 뿌리로 확정된 자리 — 번역 뒤의 **아주 짧은 한글 이름**(「윌」 2B)은 내용 판별(`_textlike`)을 못 넘으니
        # 재조립 검증이 다시 파싱할 때만 뿌리로 인정한다(원본 파싱엔 쓰지 않는다)
        if force is not None and m.start() in force:
            roots[m.start()] = t
            continue
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


def is_cond_goto(tk: list[Token]) -> bool:
    """조건부(11·12·F2·F8) + goto 로 끝나 **바로 뒤 스트림으로 흘러간다**. F8 은 인자 바이트(`84 3F` 꼴)가 텍스트 토큰으로 읽히니 한 칸 더 본다."""
    if len(tk) < 2 or tk[-1].code != 0x0F:
        return False
    p = tk[-2]
    if p.code in COND:
        return True
    return len(tk) >= 3 and p.kind == "text" and len(p.raw) == 2 and tk[-3].code == 0xF8


def entry_tables(b: bytes, only: set[int] | None = None) -> list[tuple[int, int, list[TableRef]]]:
    """모듈 머리 표 — `[길이 워드, E 기준 상대 워드 …]` 레코드를 가리키는 BE16 항목들. 반환 [(E, 길이, 표 항목들)].
    워드가 전부 문안 스트림이면(기계어 레코드는 걸러진다) 채택하고, 레코드 끝(E+길이)부터 **고정 위치에서 이어 읽는** 바이트코드(분기 허브 사슬)가 있다.
    `only` = 원본에서 확정한 E 들 — 번역 뒤 바이트를 다시 읽을 때는 내용 판별을 건너뛴다."""
    if len(b) < 4:
        return []
    n = struct.unpack(">H", b[:2])[0] // 2
    if not 2 <= n < 64:
        return []
    ents = [struct.unpack(">H", b[2 * i : 2 * i + 2])[0] for i in range(n)]
    out = []
    seen = set()
    for e in ents[1:]:
        if e in seen or e + 2 > len(b):
            continue
        seen.add(e)
        ln = struct.unpack(">H", b[e : e + 2])[0]
        if ln % 2 or ln < 4 or e + ln > len(b):
            continue
        refs = []
        ok = True
        for p in range(e + 2, e + ln, 2):
            t = e + struct.unpack(">H", b[p : p + 2])[0]
            if not 0 < t < len(b):
                ok = False
                break
            if only is None or e not in only:
                try:
                    st = parse_stream(b, t)
                except (ValueError, IndexError):
                    ok = False
                    break
                if not looks_like_text(st):
                    ok = False
                    break
            refs.append(TableRef(p, e, t))
        if ok and refs and (only is None or e not in only):
            # 연속한 작은 수(1004 1005 1006 …)는 오프셋이 아니라 id 표다 — 가리킨 스트림끼리 겹치면 버린다(한 바이트씩 어긋난 가짜 스트림)
            spans = sorted({(r.target, parse_stream(b, r.target).end) for r in refs})
            if any(a_[1] > b_[0] for a_, b_ in itertools.pairwise(spans)):
                ok = False
        if ok and refs:
            out.append((e, ln, refs))
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
    # 참조(lea·표·goto/call)가 안 닿는 화자 태그 스트림 — 죽은 문안이거나 런타임 계산으로 닿는다(ED2 74건).
    # 🔴 `streams` 에 안 섞는다 — 재조립이 옮기는 건 참조가 있는 것뿐이고, 이건 제자리·원본 길이 안에서만 다룬다.
    orphans: dict[int, Stream] = field(default_factory=dict)
    # 머리 표 레코드 — E → 길이. 레코드 끝(E+길이)의 바이트코드 허브는 **제자리 고정**(실행기가 그 자리에서 이어 읽는다) — 옮기면 안 된다.
    entries: dict[int, int] = field(default_factory=dict)
    pinned: set[int] = field(default_factory=set)
    # 고정 스트림 중 **바이트코드 허브**(머리 표 레코드 끝) — 길이가 모자라면 옛 자리에 goto 스텁을 두고 본문만 옮길 수 있다(가나 글줄은 못 한다)
    hubs: set[int] = field(default_factory=set)


def looks_like_text(st: Stream) -> bool:
    """뿌리 후보가 스트림인가 — 글자가 있거나, 참조(goto/call/셀/코드)가 있거나, 화자 태그가 있다.
    ⚠ `12 xxxx 0F yyyy` 처럼 제어코드뿐인 분기 허브도 스트림이다 — 글자만 보면 버려진다(실측 142건)."""
    n = sum(len(t.raw) for t in st.tokens if t.kind == "text")
    return n >= 2 or any(t.ref or t.code == 0x1E for t in st.tokens)


def parse_module(
    b: bytes,
    force: set[int] | None = None,
    entries_only: set[int] | None = None,
    pin_force: set[int] | None = None,
) -> Module:
    roots = lea_roots(b, force)
    tables = table_roots(b)
    entries: dict[int, int] = {}
    pinned: set[int] = set()
    ent_starts: list[int] = []
    for e, ln, refs in entry_tables(b, entries_only):
        entries[e] = ln
        tables = [*tables, *refs]
        try:
            parse_stream(b, e + ln)
        except (ValueError, IndexError):
            continue
        ent_starts.append(e + ln)
        pinned.add(e + ln)
    streams: dict[int, Stream] = {}
    bad: list[int] = []
    cells: set[int] = set()
    codes: set[int] = set()
    badref: list[int] = []
    seen: set[int] = set()

    def explore(
        work: list[int],
        out: dict[int, Stream],
        cl: set[int],
        cd: set[int],
        br: list[int],
        seen_: set[int],
    ) -> None:
        while work:
            t = work.pop()
            if t in seen_:
                continue
            seen_.add(t)
            try:
                st = parse_stream(b, t)
            except (ValueError, IndexError):
                br.append(t)
                continue
            out[t] = st
            # 조건부(11·12·F2·F6·F8) 뒤의 goto 는 「3B 건너뜀」으로 넘어갈 수 있다 — 그 뒤도 뿌리다
            if is_cond_goto(st.tokens):
                work.append(st.end)
            for tok in st.tokens:
                if tok.ref in (GOTO, CALL):
                    work.append(tok.target)
                elif tok.ref == CELL:
                    cl.add(tok.target)
                elif tok.ref == CODE:
                    cd.add(tok.target)

    def cover(ss) -> bytearray:
        c = bytearray(len(b))
        for st in ss:
            for t in st.tokens:
                c[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
        return c

    work = []
    for ins, t in roots.items():
        try:
            parse_stream(b, t)
        except ValueError:
            bad.append(ins)
            continue
        work.append(t)
    work += [tr.target for tr in tables]
    work += ent_starts
    explore(work, streams, cells, codes, badref, seen)
    # 2단계: a1 이 아닌 주소 레지스터(a3·a6 …)로 문안을 가리키는 lea — 우연한 명령(이미 찾은 문안 **안**에 있거나, 뒤늦게 찾은 문안이 도리어
    # 기존 뿌리 명령을 덮는 것)은 버린다. 하나씩 받아들이며 충돌을 본다.
    extra = lea_roots(b, force, LEA_OTHER)
    for ins in sorted(extra):
        t = extra[ins]
        if ins in roots:
            continue
        cov = cover(streams.values())
        if cov[ins] or cov[t]:
            continue
        try:
            parse_stream(b, t)
        except (ValueError, IndexError):
            continue
        tmp: dict[int, Stream] = {}
        tcl: set[int] = set()
        tcd: set[int] = set()
        tbr: list[int] = []
        tseen = set(seen)
        explore([t], tmp, tcl, tcd, tbr, tseen)
        newcov = cover(tmp.values())
        if tbr or any(newcov[i] for i in [*roots, ins]):
            continue
        roots[ins] = t
        streams.update(tmp)
        cells |= tcl
        codes |= tcd
        seen |= tseen
    # 3단계: 절대 오프셋 워드 표 — 상점 대사처럼 `05 06 w w w w` 꼴(워드마다 모듈 안 문안 시작)로 남은 문안을 가리킨다(코드가 base 0 으로 읽는다).
    # 연속 둘 이상이 전부 문안 시작이고 하나라도 아직 모르는 스트림이면 표로 받는다 — 코드 워드와 우연히 맞을 일이 없게 연속 조건을 건다.
    cov = cover(streams.values())
    p = 0
    while p + 2 <= len(b):
        if cov[p] or cov[p + 1]:
            p += 1
            continue
        tab: list[tuple[int, int]] = []
        nnew = 0
        q = p
        while q + 2 <= len(b) and not cov[q] and not cov[q + 1]:
            w = struct.unpack(">H", b[q : q + 2])[0]
            if not 0 < w < len(b):
                break
            if w not in streams and not cov[w]:
                try:
                    st3 = parse_stream(b, w)
                except (ValueError, IndexError):
                    break
                if not _textlike(st3):
                    break
                nnew += 1
            if w in streams or not cov[w]:
                tab.append((q, w))
            # 이미 아는 스트림 **안**을 가리키는 워드(첫 항목이 +2 어긋나는 상점 표)는 이어 읽되 표 항목으로는 안 센다(옮길 대상이 아니다)
            q += 2
        if len(tab) >= 2 and nnew >= 1:
            tmp = {}
            tcl: set[int] = set()
            tcd: set[int] = set()
            tbr: list[int] = []
            tseen = set(seen)
            explore(
                [w for _, w in tab if w not in streams and not cov[w]], tmp, tcl, tcd, tbr, tseen
            )
            spans = sorted({(w_, parse_stream(b, w_).end) for _, w_ in tab if w_ in tmp})
            if any(a_[1] > b_[0] for a_, b_ in itertools.pairwise(spans)):
                p += 1  # 연속한 작은 수 표(id) — 가리킨 스트림끼리 겹친다
                continue
            newcov = cover(tmp.values())
            if (
                not tbr
                and not any(newcov[i] for i in roots)
                and not any(newcov[q_] for q_, _ in tab)
            ):
                tables = [*tables, *(TableRef(q_, 0, w_) for q_, w_ in tab)]
                streams.update(tmp)
                cells |= tcl
                codes |= tcd
                seen |= tseen
                cov = cover(streams.values())
            p = q + 2
        else:
            p += 1
    # 4단계: 그래도 남은 **가나 글줄**(상점 대사 따위 — 코드가 계산한 자리로만 읽는다)은 글줄이 시작하는 자리를 스트림으로 **제자리 고정**한다.
    # 참조가 없으니 옮길 수 없다(번역은 원래 칸 안에서만) — 시작은 글줄을 왼쪽으로(SJIS 쌍 · 공백) 늘려 잡는다.
    cov = cover(streams.values())
    for j in sorted(
        pin_force or ()
    ):  # 재조립 검증 — 번역으로 가나가 사라진 고정 스트림은 가나 글줄 규칙으로 못 찾는다
        if j in streams or cov[j]:
            continue
        try:
            st4 = parse_stream(b, j)
        except (ValueError, IndexError):
            continue
        streams[j] = st4
        pinned.add(j)
        cov = cover(streams.values())
    slots = bytearray(
        len(b)
    )  # 지명 배너 표(14B 칸 + 07 구분자 반복) — banners.py 가 칸 단위로 굽는다, 스트림이 아니다
    for ms in SLOT_TABLE.finditer(b):
        slots[ms.start() : ms.end()] = b"\x01" * (ms.end() - ms.start())
    for m4 in KANA_RUN.finditer(b):
        i = m4.start()
        if cov[i] or slots[i]:
            continue
        j = i
        while j >= 2 and not cov[j - 1]:
            if b[j - 1] == 0x20 and j >= 3 and not cov[j - 2]:
                j -= 1
            elif is_lead(b[j - 2]) and 0x40 <= b[j - 1] <= 0xFC and b[j - 1] != 0x7F:
                j -= 2
            else:
                break
        try:
            st4 = parse_stream(b, j)
        except (ValueError, IndexError):
            continue
        if not _textlike(st4):
            continue
        hit = [t.off for t in st4.tokens if cov[t.off]]
        if hit and not (
            # 꼬리를 같이 쓰는 글줄 — 겹친 토큰이 끝에 몰려 있고 거기서 시작해 같은 자리에서 끝나는 스트림이 이미 있다
            all(cov[t.off] for t in st4.tokens if t.off >= hit[0])
            and any(s0 > j and s0 <= hit[0] and st0.end == st4.end for s0, st0 in streams.items())
        ):
            continue
        streams[j] = st4
        pinned.add(j)
        cov = cover(streams.values())
    covered = bytearray(len(b))
    for st in streams.values():
        for t in st.tokens:
            covered[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    orphans: dict[int, Stream] = {}
    for m in SPEAKER.finditer(b):
        if covered[m.start()]:
            continue
        try:
            st = parse_stream(b, m.start())
        except (ValueError, IndexError):
            continue
        orphans[m.start()] = st
        for t in st.tokens:
            covered[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    return Module(
        b,
        {i: t for i, t in roots.items() if i not in bad},
        streams,
        bad,
        cells,
        codes,
        badref,
        tables,
        orphans,
        entries,
        {s_ for s_ in pinned if s_ in streams},
        {s_ for s_ in ent_starts if s_ in streams},
    )


def coverage(mod: Module) -> tuple[int, int]:
    """(화자 태그 수, 그중 스트림 안에 있는 수)."""
    cov = bytearray(len(mod.data))
    for st in [*mod.streams.values(), *mod.orphans.values()]:
        for t in st.tokens:
            cov[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    tags = list(SPEAKER.finditer(mod.data))
    return len(tags), sum(1 for m in tags if cov[m.start()])


# ── 재조립 ─────────────────────────────────────────────────────────────────────


def _emit_stream(tokens: list[Token]) -> int:
    return sum(len(t.raw) for t in tokens) + (1 if tokens and tokens[-1].kind == "eof" else 0)


def _emit_tokens(tokens: list[Token], base: int, pos: dict[int, int]) -> bytes:
    """토큰 → 바이트(`base` 에 놓일 때). 참조는 새 자리(`pos`)와 이 토큰의 새 위치로 상대 오프셋을 다시 잰다."""
    out = bytearray()
    for t in tokens:
        if t.ref is None:
            out += t.raw
            continue
        raw = bytearray(t.raw)
        tgt = pos.get(t.target, t.target) if t.ref in (GOTO, CALL) else t.target
        here = base + len(out)
        if t.code in (0xF5, 0xFB):
            raw[2:4] = struct.pack(">h", tgt - (here + 2))
        else:
            raw[1:3] = struct.pack(">h", tgt - (here + 1))
        out += raw
    return bytes(out)


def reassemble(
    mod: Module, replace: dict[int, list[Token]] | None = None, *, zero_dead: bool = True
) -> bytes:
    """원본 바이트는 제자리에 두고, **바뀐 스트림만** 손댄다.

    replace = {스트림 시작: 새 토큰 목록}. 제어 토큰은 raw 그대로 두고 text 토큰만 바꾸는 게 원칙 —
    참조(ref/target)는 원본 토큰의 것을 그대로 쓴다. 옮긴 스트림을 가리키는 것: 뿌리 lea 변위 ·
    goto/call 오프셋. 안 옮기는 것(셀·코드)은 새 자리에서의 상대 오프셋만 다시 잰다.

    - 새 스트림이 **원래 칸보다 작거나 같고** 그 칸 안에 다른 스트림이 시작하지 않으면 **제자리에** 쓴다(남는 칸은 0).
    - 아니면 끝으로 옮기고 옛 칸은 0 으로 지운다(LZ 의 RLE 가 거의 공짜로 누른다).
    - **안 바뀐 스트림은 안 움직인다**(옮긴 스트림을 가리키는 goto/call 만 제자리에서 고친다) — 예전엔 모듈의 스트림을
      전부 끝에 다시 썼고, 그 탓에 번역이 한 줄만 있어도 디코드 블록이 스트림 총량만큼 커져 RAM 버퍼 한도를 넘었다.
    스트림이 모듈 끝(eof)으로 끝났는데 옮기면 00 을 붙인다 — 뒤에 이어 쓰는 스트림으로 새지 않게.
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
    order = sorted(mod.streams)
    toks = {s: replace.get(s, mod.streams[s].tokens) for s in order}
    old_len = {s: mod.streams[s].end - s for s in order}
    new_len = {s: _emit_stream(toks[s]) for s in order}
    # 이어 읽기 스트림(끝 표식 없이 뒤 글줄로 흘러간다) — 안쪽 스트림 앞까지 칸을 **공백으로 꽉 채운다**(사이에 NUL 이 끼면 글이 끊긴다)
    cont: set[int] = set()
    for s_ in replace:
        tk_ = toks.get(s_)
        if s_ in mod.streams and tk_ and tk_[-1].kind not in ("end", "eof") and tk_[-1].ref != GOTO:
            cont.add(s_)
            inn_ = [x for x in order if s_ < x < s_ + old_len[s_]]
            full = (min(inn_) - s_) if inn_ else old_len[s_]
            if new_len[s_] > full:
                raise ValueError(
                    f"이어 읽기 스트림 @{s_:#x} 이 칸({full}B)보다 길다({new_len[s_]}B) — 번역을 줄인다"
                )
            if new_len[s_] < full:
                RL.add("채움", s_, None, f"이어 읽기 스트림 — 뒤 글줄까지 공백 {full - new_len[s_]}B 로 칸을 꽉 채운다", RL.EVID_FILL, RL.UNDO_FILL)
                toks[s_] = [*tk_, Token(0, b" " * (full - new_len[s_]), "text")]
                new_len[s_] = full

    # 안에 다른 스트림이 시작하는 스트림(꼬리를 같이 쓰는 글줄)이 제자리에서 모자라면, 그 안쪽 스트림이 **전부 번역돼 옮겨질 수 있을 때**(고정도
    # 허브도 아니다) 안쪽 칸을 빌려 쓴다 — 안쪽 스트림은 새 자리로 옮기고(참조는 새 자리로 고친다) 옛 칸은 바깥 스트림 글이 차지한다.
    forced: set[int] = set()
    absorbed: set[int] = set()

    def _inner(s: int) -> list[int]:
        return [x for x in order if s < x < s + old_len[s]]

    for s in sorted(replace, key=lambda x: -old_len.get(x, 0)):
        if s not in mod.streams:
            continue
        inn = _inner(s)
        if s in cont:
            continue
        if inn and new_len[s] > min(inn) - s and new_len[s] <= old_len[s]:
            tb = {t.off for t in mod.streams[s].tokens}
            mv = [
                x for x in inn if x in tb
            ]  # 토큰 경계에서 시작하는 안쪽 스트림 — 옮겨야 한다(번역 필요)
            if (
                all(x in replace and x not in mod.pinned and x not in forced for x in mv)
                and all(x in tb or x not in replace for x in inn)
            ):  # 토큰 한가운데서 시작하는 것은 글자 중간을 가리킨 쓰레기 — 건드리지 않고 바깥 글이 덮는다
                absorbed.add(s)
                forced.update(mv)

    def room(s: int) -> int:
        """제자리에 쓸 수 있는 길이 — 원래 칸, 단 **그 안에서 다른 스트림이 시작하면** 그 앞까지(꼬리를 같이 쓰는 스트림을 안 건드린다)."""
        if s in absorbed:
            return old_len[s]
        inner = _inner(s)
        return min(inner) - s if inner else old_len[s]

    def too_big(s: int) -> bool:
        return new_len[s] > room(s)

    # 조건부(11·12·F2·F8) + goto 로 끝나는 스트림은 **바로 뒤 스트림으로 흘러간다**(파서가 `st.end` 를 뿌리로 본다) — 물리적으로
    # 붙어 있어야 하니 같이 한 묶음으로 옮기거나 같이 둔다(제자리 축소는 `st.end` 를 당겨 뒤 스트림을 놓친다).
    chain: dict[int, int] = {}
    for s in order:
        tk = mod.streams[s].tokens
        e = mod.streams[s].end
        if is_cond_goto(tk) and e in mod.streams:
            chain[s] = e
    group: dict[int, int] = {s: s for s in order}  # 묶음 대표(앞쪽)
    for a_, b_ in sorted(chain.items()):
        group[b_] = group[a_]
    members: dict[int, list[int]] = {}
    for s in order:
        members.setdefault(group[s], []).append(s)
    moved: set[int] = set()
    stub_at: set[int] = set()
    tail_stub: set[int] = set()  # 꼬리 goto 스텁을 더 붙인 조건 분기 스트림

    def _shrunk_front(m: int) -> None:
        """묶음 앞 스트림이 제자리에서 줄었다 — 끝이 당겨져 뒤 꼬리를 놓치지 않게 끝을 지킨다.
        남는 칸이 3B 이상이면 **공백으로 채우지 않고** 조건 분기 뒤에 `goto 꼬리` 스텁을 붙인다(조건이 맞아 goto 를 건너뛰면 이 스텁이 꼬리로 잇는다 —
        공백 패딩은 줄 가운데 넓은 빈칸·이름 칸 부풀림·줄 넘침 빈 줄로 보였다, 10-19 qa). 3B 미만이면 공백 1~2칸으로 끝을 지킨다."""
        tk = list(toks[m])
        d = old_len[m] - new_len[m]
        if d >= 3 and is_cond_goto(tk) and m in chain:
            tk.append(Token(m, b"\x0f\x00\x00", "ctl", 0x0F, GOTO, chain[m]))
            toks[m] = tk
            new_len[m] += 3
            tail_stub.add(m)
            RL.add("스텁", m, None, f"제자리에서 줄어든 조건 분기 앞 스트림 — 남는 {d}B 에 goto 꼬리 스텁(3B)", RL.EVID_VM, RL.UNDO_FILL)
            return
        ti = next(x for x in range(len(tk) - 3, -1, -1) if tk[x].kind == "text")
        RL.add("채움", m, None, f"제자리에서 줄어든 묶음 앞 스트림 — 끝을 지키려 공백 {d}B", RL.EVID_FILL, RL.UNDO_FILL)
        tk[ti] = Token(tk[ti].off, tk[ti].raw + b" " * d, "text", tk[ti].code)
        toks[m] = tk
        new_len[m] = old_len[m]

    for ms in members.values():
        if len(ms) > 1:
            rep_ms = [m for m in ms if m in replace]
            if not rep_ms:
                continue
            # 묶음 안에서 바뀐 스트림이 **전부 칸 안에 들고**(앞 스트림은 길이를 같게 맞출 수 있어야 한다) 다른 스트림이 그 안에서 시작하지 않으면
            # 제자리에 둔다 — 앞 스트림이 줄면 뒤 스트림이 붙는 자리(`st.end`)가 당겨지니 **빈 칸을 공백(0x20)으로 채워 끝을 지킨다**.
            ok = True
            for m in rep_ms:
                if too_big(m):
                    ok = False
                elif m != ms[-1] and new_len[m] < old_len[m]:
                    tk = toks[m]
                    ti = next((x for x in range(len(tk) - 3, -1, -1) if tk[x].kind == "text"), None)
                    if ti is None:
                        ok = False
            if ok:
                for m in rep_ms:
                    if m != ms[-1] and new_len[m] < old_len[m]:
                        _shrunk_front(m)
            else:
                # 앞쪽(고정 스트림 포함)이 칸 안에 들면 제자리에 두고 **뒤쪽만 옮긴다** — 옛 시작 자리에 goto 스텁을 둬 조건이 거짓일 때
                # 물리적으로 이어지던 흐름을 새 자리로 잇는다.
                j = next(
                    (i for i in range(1, len(ms)) if ms[i] in rep_ms and (too_big(ms[i]))),
                    None,
                )
                pre_ok = j is not None
                if pre_ok:
                    for m in ms[:j]:
                        if m not in rep_ms:
                            continue
                        if (
                            too_big(m)
                            or new_len[m] < old_len[m]
                            and not any(
                                x.kind == "text" for x in toks[m][: max(len(toks[m]) - 2, 0)]
                            )
                        ):
                            pre_ok = False
                    if pre_ok and old_len[ms[j]] < 3:
                        pre_ok = False
                if pre_ok:
                    for m in ms[:j]:
                        if m in rep_ms and new_len[m] < old_len[m]:
                            _shrunk_front(m)
                    moved.update(ms[j:])
                    stub_at.add(ms[j])
                else:
                    moved.update(ms)
        else:
            s = ms[0]
            if s in replace and (too_big(s)):
                moved.add(s)
    for x in forced:
        moved.update(members[group[x]])
    for s in sorted(moved):
        if s in mod.pinned and old_len[s] >= 3:
            stub_at.add(
                s
            )  # 허브·고정 글줄은 옛 자리에 goto 스텁(3B)만 남기고 본문을 옮긴다 — 읽기가 그 자리에서 시작하므로 스텁이 먼저 읽힌다(10-18: 상점 「…이군요」 43곳을 줄이지 않고 넣으려고)
        elif s in mod.pinned:
            raise ValueError(
                f"제자리 고정 스트림 @{s:#x} 이 원래 칸({old_len[s]}B)보다 길다({new_len[s]}B) — 번역을 줄인다"
            )
    # 🔴 **꼬리를 둘 이상이 이어받는 조건 분기**(바깥 스트림 S 와 그 안쪽에서 시작하는 S′ 가 같은 끝에서 같은 꼬리 T 로 흐른다 — md-ed1 24씬 29곳, 10-19):
    # 묶음은 T 를 마지막 S 하나에만 붙인다 — 나머지는 조건이 맞아 goto 를 건너뛰면 **물리적으로 바로 뒤**(0 이나 남의 스트림 머리)를 읽는다.
    #  · S 가 옮겨졌으면 본문 바로 뒤에 `goto T` 3B 를 한 벌 더 둔다(조건 참이면 건너뛴 goto 다음의 이 스텁이 T 로 잇는다)
    #  · S 는 제자리인데 T 가 옮겨졌으면 T 의 옛 시작 자리에 스텁을 둔다
    for s_, t_ in sorted(chain.items()):
        if group[s_] == group[t_]:
            continue
        if s_ in moved:
            tk = list(toks[s_])
            if tk and tk[-1].kind not in ("end", "eof"):
                tk.append(Token(s_, b"\x0f\x00\x00", "ctl", 0x0F, GOTO, t_))
                toks[s_] = tk
                new_len[s_] += 3
                tail_stub.add(s_)
                RL.add("스텁", s_, t_, "옮겨진 조건 분기 본문 뒤에 goto 꼬리 스텁(3B) — 꼬리를 둘 이상이 이어받는다", RL.EVID_VM, RL.UNDO_NONE)
        elif s_ in replace and new_len[s_] < old_len[s_]:
            # 제자리에서 **줄어든** 앞 스트림 — 끝이 당겨져 바로 뒤가 0 패딩이 된다. 남는 칸이 3B 이상이면 `goto T` 스텁을 붙이고, 아니면 공백으로 끝을 지킨다
            tk = list(toks[s_])
            if tk and tk[-1].kind not in ("end", "eof"):
                if old_len[s_] - new_len[s_] >= 3:
                    tk.append(Token(s_, b"\x0f\x00\x00", "ctl", 0x0F, GOTO, t_))
                    toks[s_] = tk
                    new_len[s_] += 3
                    tail_stub.add(s_)
                    RL.add("스텁", s_, t_, "제자리에서 줄어든 조건 분기 — 남는 칸에 goto 꼬리 스텁(3B)", RL.EVID_VM, RL.UNDO_FILL)
                else:
                    ti = next((x for x in range(len(tk) - 3, -1, -1) if tk[x].kind == "text"), None)
                    if ti is not None:
                        d = old_len[s_] - new_len[s_]
                        RL.add("채움", s_, None, f"제자리에서 줄어든 조건 분기 — 공백 {d}B 로 끝을 지킨다(3B 미만이라 스텁 불가)", RL.EVID_FILL, RL.UNDO_FILL)
                        tk[ti] = Token(tk[ti].off, tk[ti].raw + b" " * d, "text", tk[ti].code)
                        toks[s_] = tk
                        new_len[s_] = old_len[s_]
        if t_ in moved and old_len[t_] >= 3 and s_ not in moved:
            stub_at.add(t_)
    shrunk = {s for s in replace if s in mod.streams and s not in moved}
    # 옮긴 스트림의 옛 칸은 죽은 자리 — 0. 단 **그 안에서 다른 스트림이 시작하면**(꼬리를 같이 쓰는 스트림) 그 시작 앞까지만 죽은 자리다
    dead_end = {}
    for s in moved:
        inner = [x for x in order if s < x < s + old_len[s]]
        dead_end[s] = min(inner) if inner else s + old_len[s]
    for s in moved:
        if zero_dead:
            b[s : dead_end[s]] = b"\x00" * (dead_end[s] - s)
    for s in shrunk:
        if zero_dead:
            b[s : s + room(s)] = b"\x00" * room(s)
    if len(b) & 1:
        b.append(0)
    pos = {s: s for s in order}
    # 죽은 칸(옮긴 스트림의 옛 자리 · 제자리 축소 뒤 남은 꼬리)에 **먼저** 앉힌다 — 안 그러면 늘어난 스트림마다 모듈 끝에 새 칸을 더하고
    # 디코드 블록이 램 버퍼 한도(원본 최대)를 넘는다. 묶음(조건부 흐름)은 쪼갤 수 없는 한 덩이다.
    free: list[list[int]] = []
    for s in sorted(moved):
        free.append([s + (3 if s in stub_at else 0), dead_end[s]])
    for s in sorted(shrunk):
        if room(s) > new_len[s]:
            free.append([s + new_len[s], s + room(s)])
    free.sort()
    occupied = sorted((s, s + new_len[s]) for s in shrunk if s in absorbed)
    if occupied:  # 안쪽 스트림의 옛 칸 가운데 바깥 스트림 글이 차지한 곳은 빈 칸이 아니다
        cut: list[list[int]] = []
        for lo, hi in free:
            segs = [[lo, hi]]
            for ol, oh in occupied:
                nxt = []
                for a_, b_ in segs:
                    if oh <= a_ or ol >= b_:
                        nxt.append([a_, b_])
                        continue
                    if a_ < ol:
                        nxt.append([a_, ol])
                    if oh < b_:
                        nxt.append([oh, b_])
                segs = nxt
            cut += segs
        free = sorted(cut)
    merged: list[list[int]] = []
    for a_, b_ in free:
        # 🔴 겹치는 칸도 한 덩이로 합친다 — 옛 코드는 「맞닿은」 칸만 합쳐서, 같은 죽은 자리가 두 번 올라오면(옮긴 스트림 + 그 안쪽 스트림의 옛 칸) 서로 다른 두 묶음이
        # 같은 자리에 앉았다(씬058-1: 0x4A6 과 0x863 이 둘 다 0x762 — 한쪽 대사가 남의 대사로 덮였다, 10-20 짝 표)
        if merged and a_ <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b_)
        else:
            merged.append([a_, b_])
    units = []
    for ms in members.values():
        mv = [m for m in ms if m in moved]
        if mv:
            units.append(mv)
    units.sort(key=lambda u: -sum(new_len[m] + 1 for m in u))
    appended: list[list[int]] = []
    for u in units:
        need = sum(new_len[m] + (1 if toks[m] and toks[m][-1].kind == "eof" else 0) for m in u)
        fits = [iv for iv in merged if iv[1] - iv[0] >= need]
        if not fits:
            appended.append(u)
            continue
        iv = min(fits, key=lambda x: x[1] - x[0])
        at = iv[0]
        for m in u:
            pos[m] = at
            at += new_len[m] + (1 if toks[m] and toks[m][-1].kind == "eof" else 0)
        iv[0] = at
    if len(b) & 1:
        b.append(0)
    cur = len(b)
    for u in sorted(appended, key=lambda u: u[0]):
        for m in u:
            pos[m] = cur
            cur += new_len[m] + (1 if toks[m] and toks[m][-1].kind == "eof" else 0)
    spans = sorted((pos[m], pos[m] + new_len[m]) for u in units for m in u)
    for (a1, b1), (a2, _b2) in zip(spans, spans[1:], strict=False):
        if a2 < b1:
            raise ValueError(
                f"옮긴 스트림 둘이 같은 자리에 앉았다 @{a2:#x} (앞 {a1:#x}~{b1:#x}) — 빈 칸 계산이 틀렸다"
            )
    if cur > MODULE_MAX:
        raise ValueError(f"모듈이 {cur}B — 한도 {MODULE_MAX}B 를 넘는다")
    for s in sorted(moved):
        why = (
            "안쪽 스트림 칸을 바깥 글이 차지해 같이 옮김"
            if s in forced
            else f"번역 글 {new_len[s]}B > 제자리 {room(s)}B(칸 넘침)"
            if too_big(s)
            else "조건 분기 묶음이라 같이 옮김(꼬리가 물리적으로 이어져야 한다)"
        )
        RL.add("옮김", s, pos[s], why + f" · 옛 칸 {dead_end[s] - s}B 는 0 으로 지움", RL.EVID_VM, RL.UNDO_NONE)
        if s in stub_at:
            RL.add("스텁", s, pos[s], "옛 시작 자리에 goto 스텁(3B) — 고정·허브·묶음 글줄은 읽기가 그 자리에서 시작한다", RL.EVID_VM, RL.UNDO_NONE)
    for ins, s in sorted(mod.roots.items()):
        if pos[s] != s:
            RL.add("포인터", ins, pos[s], f"뿌리 lea 변위 재측정 — 가리키는 스트림 {s:#06x} 이 옮겨졌다", RL.EVID_VM, RL.UNDO_POINTER)
    for tr in mod.tables:
        if pos[tr.target] != tr.target:
            RL.add("포인터", tr.word, pos[tr.target], f"표 항목 워드 재측정 — 표가 가리키는 스트림 {tr.target:#06x} 이 옮겨졌다", RL.EVID_VM, RL.UNDO_POINTER)
    for s in order:
        if s not in moved and s not in shrunk:
            for t_ in mod.streams[s].tokens:
                if t_.ref in (GOTO, CALL) and pos.get(t_.target, t_.target) != t_.target:
                    RL.add("포인터", t_.off, pos[t_.target], f"{'goto' if t_.ref == GOTO else 'call'} 변위 재측정 — 대상 {t_.target:#06x} 이 옮겨졌다", RL.EVID_VM, RL.UNDO_POINTER)
    out = bytearray()
    for s in order:
        if s in moved:
            body = _emit_tokens(toks[s], pos[s], pos)
            if toks[s] and toks[s][-1].kind == "eof":
                body += b"\x00"
            if pos[s] >= len(mod.data) + (len(mod.data) & 1):
                out += body  # 모듈 끝에 덧붙이는 것 — pos 가 곧 자리(정렬 순서와 같다)
            else:
                b[pos[s] : pos[s] + len(body)] = body
        elif s in shrunk:
            body = _emit_tokens(toks[s], s, pos)
            b[s : s + len(body)] = body
        else:  # 안 바뀐 스트림 — 옮겨진 스트림을 가리키는 goto/call 만 제자리에서 고친다
            for t in mod.streams[s].tokens:
                if t.ref in (GOTO, CALL) and pos.get(t.target, t.target) != t.target:
                    fixed = _emit_tokens([t], t.off, pos)
                    b[t.off : t.off + len(fixed)] = fixed
    for s in stub_at:  # 옛 시작 자리의 goto 스텁 → 새 자리
        b[s : s + 3] = _emit_tokens([Token(s, b"\x0f\x00\x00", "ctl", 0x0F, GOTO, s)], s, pos)
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


def _flat(tokens) -> bytes:
    """토큰 → 바이트(참조 변위는 0 으로 — 재조립이 새 자리로 다시 쟀다)."""
    out = b"".join(t.raw[:1] + b"\x00" * (len(t.raw) - 1) if t.ref else t.raw for t in tokens)
    return out + (b"\x00" if tokens and tokens[-1].kind == "eof" else b"")


def _lead_merge(tokens):
    """우리 문안에서 SJIS 선두 바이트(0x84 …)가 태그로 홀로 선 꼴 `<84>?` 를 원본 파서가 읽는 한 덩이 텍스트(`84 3f`)로 합친다 —
    조건 명령 뒤의 인자 바이트가 원본에선 텍스트로 읽힌다."""
    out = []
    for t in tokens:
        if (
            out
            and out[-1].kind == "ctl"
            and len(out[-1].raw) == 1
            and 0x80 <= out[-1].raw[0] <= 0x9F
            and t.kind == "text"
        ):
            prev = out.pop()
            t = Token(prev.off, prev.raw + t.raw, "text", -1, None, -1)
        out.append(t)
    return out


def verify_reassembly(
    orig: Module,
    new_bytes: bytes,
    replace: dict[int, list[Token]] | None = None,
    skip: frozenset[int] = frozenset(),
) -> None:
    """다시 파싱해 스트림별 토큰(raw 텍스트 + 제어코드 종류)이 의도와 같은지 본다."""
    replace = replace or {}
    new = parse_module(new_bytes, set(orig.roots), set(orig.entries), set(orig.pinned))
    # 덧붙인 문안 바이트 안에서 우연히 `43 FA` 가 lea 로 읽힐 수 있다 — 원본 뿌리 자리만 맞댄다
    if any(ins not in new.roots for ins in orig.roots):
        raise ValueError("원본 뿌리가 새 모듈에서 사라졌다")
    remap = {}
    for ins, s in orig.roots.items():
        remap[s] = new.roots[ins]
    # 표는 워드 자리로 짝짓는다 — 번역으로 가나가 사라지면 절대 워드 표(3단계)를 새 파서가 못 찾는다(재조립이 원본 표로 고쳤다)
    new_by_word = {(c.word, c.base): c for c in new.tables}
    for a in orig.tables:
        c = new_by_word.get((a.word, a.base))
        if c is not None:
            remap[a.target] = c.target
    protected = bytearray(
        len(orig.data)
    )  # 표 워드 · 머리 표 레코드 — 재조립이 바이트를 고친다(겹친 쓰레기 스트림은 비교 대상이 아니다)
    for a in orig.tables:
        protected[a.word : a.word + 2] = b"\x01\x01"
    for e, ln in orig.entries.items():
        protected[e : e + ln] = b"\x01" * ln
    for s in orig.pinned:
        remap[s] = s  # 제자리 고정
    for s, st in orig.streams.items():
        want = replace.get(s, st.tokens)
        if s in skip:
            continue  # 머리가 자료인 스트림(상점 표) — 별도 게이트(`build.verify_head_tables`)가 본다
        if s in replace and want and want[-1].kind not in ("end", "eof") and want[-1].ref != GOTO:
            continue  # 이어 읽기 스트림 — 뒤 글줄까지 한 글줄로 읽힌다
        # 뿌리가 아닌 스트림(goto/call 대상)은 뿌리에서 참조를 따라간 새 파서가 이미 품고 있다 —
        # 여기선 뿌리 스트림만 맞대고, 나머지는 참조 그래프가 같은지로 본다(아래 개수 비교)
        if s not in remap:
            continue
        if s not in replace and (
            any(protected[t.off] for t in st.tokens)
            or any(s < orig.streams[r].end and r < st.end for r in replace if r in orig.streams)
        ):
            continue
        got = new.streams[remap[s]]
        if s in orig.pinned and got.tokens and got.tokens[0].ref == GOTO:
            w0 = want[0] if want else None
            if not (w0 is not None and w0.ref == GOTO and w0.target == got.tokens[0].target):
                tgt = got.tokens[
                    0
                ].target  # 스텁 → 옮긴 본문(고정 글줄은 새 파서가 스트림으로 안 잡아 직접 읽는다)
                got = new.streams[tgt] if tgt in new.streams else parse_stream(new.data, tgt)
        a = [
            (t.kind, t.code, t.raw.rstrip(b" ") if t.kind == "text" else t.raw[:1])
            for t in _lead_merge(want)
            if t.kind != "eof"
        ]
        g = [
            (t.kind, t.code, t.raw.rstrip(b" ") if t.kind == "text" else t.raw[:1])
            for t in got.tokens
            if t.kind != "eof"
        ]
        if want and want[-1].kind == "eof":
            a.append(("end", 0, b"\x00"))
        if (
            len(g) == len(a) + 1
            and g[-1] == ("ctl", 0x0F, b"\x0f")
            and a
            and a[-1] == ("ctl", 0x0F, b"\x0f")
        ):
            g = g[
                :-1
            ]  # 꼬리를 이어받는 조건 분기에 더한 `goto T` 스텁(재조립이 붙인다) — 의도한 토큰열 뒤의 덤
        if a != g and _flat(_lead_merge(want)) == _flat(got.tokens):
            continue  # 접두 쓰레기 바이트를 `<4c>` 로 낸 꼴 — 토큰 종류만 다르고 바이트는 같다(참조 변위는 새 자리라 뺀다)
        if a != g:
            k = next(
                (i for i, (x, y) in enumerate(zip(a, g, strict=False)) if x != y),
                min(len(a), len(g)),
            )
            raise ValueError(
                f"스트림 @{s:#x} 토큰 {k} 이 의도와 다르다\n  want {a[k : k + 3]}\n  got  {g[k : k + 3]}"
            )
    lost_tables = sum(1 for a in orig.tables if (a.word, a.base) not in new_by_word)
    if len(new.streams) + lost_tables < len(orig.streams):
        raise ValueError(f"스트림 수가 줄었다 {len(orig.streams)} → {len(new.streams)}")


def _norm_tokens(toks) -> list:
    return [
        (t.kind, t.code, t.raw.rstrip(b" ") if t.kind == "text" else t.raw[:1])
        for t in _lead_merge(toks)
        if t.kind != "eof"
    ]


def pair_streams(orig: Module, new_bytes: bytes) -> tuple[Module, dict[int, int]]:
    """원판 스트림 → 새 모듈 스트림 짝(진입점 뿌리·표·고정에서 시작해 goto·call·조건 꼬리를 같이 걸어 짝지음) → (새 모듈, {원판 시작: 새 시작})."""
    new = parse_module(new_bytes, set(orig.roots), set(orig.entries), set(orig.pinned))
    pair: dict[int, int] = {}
    for ins, s in orig.roots.items():
        if ins in new.roots:
            pair[s] = new.roots[ins]
    for s in orig.pinned:
        pair.setdefault(s, s)
    for a in orig.tables:
        c = {(c.word, c.base): c for c in new.tables}.get((a.word, a.base))
        if c is not None:
            pair[a.target] = c.target
    follow = _follower(new)
    work = list(pair)
    seen: set[int] = set()
    while work:
        s = work.pop()
        if s in seen or s not in orig.streams:
            continue
        seen.add(s)
        so = orig.streams[s]
        # 원판이 goto 하나뿐인 스트림이면 새 쪽도 그 스텁 자체를 본다 — 따라가 버리면 한 단계 건너뛴 목적지 스트림의 참조와 어긋나게 짝지어진다
        lone = len(so.tokens) == 1 and so.tokens[0].ref == GOTO
        if s in orig.pinned or lone:
            sn = new.streams.get(pair[s])
            if sn is None and lone:
                try:
                    sn = parse_stream(new.data, pair[s])
                except (ValueError, IndexError):
                    sn = None
        else:
            sn = follow(pair[s])
        if sn is None:
            continue
        ot = [t for t in so.tokens if t.ref in (GOTO, CALL) and t.target is not None]
        nt = [t for t in sn.tokens if t.ref in (GOTO, CALL) and t.target is not None]
        if len(ot) == len(nt):
            for a, b in zip(ot, nt, strict=True):
                if a.target not in pair:
                    pair[a.target] = b.target
                    work.append(a.target)
        e = so.end
        if is_cond_goto(so.tokens) and e in orig.streams and e not in pair:
            pair[e] = sn.end
            work.append(e)
    return new, pair


def _follower(new: Module):
    def follow(n: int):
        st = new.streams.get(n)
        if st is None:
            try:
                st = parse_stream(new.data, n)
            except (ValueError, IndexError):
                return None
        if len(st.tokens) == 1 and st.tokens[0].ref == GOTO and st.tokens[0].target is not None:
            return follow(st.tokens[0].target)
        return st

    return follow


def cond_tail_report(
    orig: Module,
    new_bytes: bytes,
    replace: dict[int, list[Token]] | None = None,
    rows: list[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, list[str], list[str]]:
    """조건 분기(11·12·F2·F6·F8 + 0F) 스트림 **바로 뒤 바이트**가 원판의 꼬리 스트림과 같은지 센다 → (분모, 일치, 불일치, 못 잰 것).

    원판은 조건이 맞으면 goto 를 건너뛰고 **물리적으로 바로 뒤**를 읽는다 — 앞 스트림만 옮기거나 늘리면 그 자리에 남의 스트림 머리가 와
    남의 문장으로 샌다(md-ed1 24씬 29곳, 10-19). 모든 진입점(뿌리·goto·call 대상)에서 원본·새 모듈을 **같이 걸어** 짝을 짓고 짝마다 꼬리를 맞댄다.
    옛 자리에 goto 스텁만 둔 꼬리는 스텁을 따라가 비교한다(의미가 같다)."""
    replace = replace or {}
    new, pair = pair_streams(orig, new_bytes)
    follow = _follower(new)
    total = ok = 0
    bad: list[str] = []
    unmapped: list[str] = []
    protected = bytearray(
        len(orig.data)
    )  # 표 워드 · 머리 표 레코드 — 재조립이 바이트를 고치는 자료다(그 안에서 우연히 스트림으로 읽힌 것은 대상이 아니다)
    for a in orig.tables:
        protected[a.word : a.word + 2] = b"\x01\x01"
    for e_, ln in orig.entries.items():
        protected[e_ : e_ + ln] = b"\x01" * ln
    for s, so in sorted(orig.streams.items()):
        if not is_cond_goto(so.tokens):
            continue
        if any(protected[t.off] for t in so.tokens):
            continue
        total += 1
        t = so.end
        if t not in orig.streams:
            unmapped.append(f"{s:#x}(꼬리가 스트림 아님)")
            continue
        if s not in pair:
            unmapped.append(f"{s:#x}(진입점 못 찾음)")
            continue
        sn = new.streams.get(pair[s]) or parse_stream(new.data, pair[s])
        if len(sn.tokens) == 1 and sn.tokens[0].ref == GOTO:
            sn = follow(pair[s])  # 제자리 스텁 → 옮긴 본문
        if sn is None:
            bad.append(f"{s:#x}(새 스트림을 못 읽음)")
            continue
        if rows is not None:
            rows.append(
                (s, t, pair[s], sn.end)
            )  # (원판 S, 원판 꼬리 T, 새 S, 새 꼬리 자리) — 화면 대조용
        want = replace.get(t, orig.streams[t].tokens)
        if len(want) == 1 and want[0].ref == GOTO:
            # 꼬리 자체가 goto 하나 — 새 자리에서도 goto 하나여야 하고 목적지가 짝(원본 목적지의 새 자리)이어야 한다
            try:
                raw = parse_stream(new.data, sn.end)
            except (ValueError, IndexError):
                raw = None
            tgt = pair.get(want[0].target)

            def _dest(
                a: int,
            ) -> int:  # goto 하나뿐인 자리를 따라 최종 목적지(꼬리 스텁이 꼬리 자체를 가리켜도 같은 곳이다)
                for _ in range(8):
                    st_ = new.streams.get(a)
                    if st_ is None or len(st_.tokens) != 1 or st_.tokens[0].ref != GOTO:
                        break
                    a = st_.tokens[0].target
                return a

            if (
                raw is not None
                and len(raw.tokens) >= 1
                and raw.tokens[0].ref == GOTO
                and (tgt is None or _dest(raw.tokens[0].target) == _dest(tgt))
            ):
                ok += 1
            else:
                bad.append(f"{s:#x}→{t:#x}(꼬리 goto)")
            continue
        tn = follow(sn.end)
        if tn is not None and _norm_tokens(tn.tokens) == _norm_tokens(want):
            ok += 1
        else:
            gn = _norm_tokens(tn.tokens)[:2] if tn is not None else None
            bad.append(f"{s:#x}→{t:#x} 새={gn} 원={_norm_tokens(want)[:2]}")
    return total, ok, bad, unmapped


def verify_cond_tails(orig: Module, new_bytes: bytes, replace=None) -> None:
    total, _ok, bad, _unmapped = cond_tail_report(orig, new_bytes, replace)
    if bad:
        raise ValueError(
            f"조건 분기 뒤 꼬리가 원판과 다르다 {len(bad)}/{total}: {', '.join(bad[:6])}"
        )


if __name__ == "__main__":
    import archives
    import common

    mods = archives.modules(common.rom())
    tot = {"streams": 0, "tags": 0, "hit": 0, "bad": 0, "badref": 0, "orphans": 0}
    worst = []
    reasm_fail = []
    for blk, k, b in mods:
        mod = parse_module(b)
        tags, hit = coverage(mod)
        tot["streams"] += len(mod.streams)
        tot["orphans"] += len(mod.orphans)
        tot["tags"] += tags
        tot["hit"] += hit
        tot["bad"] += len(mod.bad_roots)
        tot["badref"] += len(mod.bad_refs)
        if tags - hit or mod.bad_refs:
            worst.append((blk, k, tags - hit, len(mod.bad_refs)))
        try:
            verify_reassembly(mod, reassemble(mod))
        except (ValueError, Exception) as e:  # noqa: BLE001 — 실패 모듈을 모아 보여 준다
            reasm_fail.append((blk, k, str(e).splitlines()[0][:60]))
    print(
        f"  모듈 {len(mods)} · 스트림 {tot['streams']} · 화자 태그 {tot['hit']}/{tot['tags']} 도달 · "
        f"뿌리 탈락 {tot['bad']} · 참조 파싱 실패 {tot['badref']} · 고아 스트림 {tot['orphans']}"
    )
    print(f"  태그 미도달 모듈 {len(worst)} · 항등 재조립 실패 {len(reasm_fail)} {reasm_fail}")
    # ⚠ 분모는 첫 조사(2026-10-12) 실측이다.
    got = (len(mods), tot["streams"], tot["hit"], tot["tags"], tot["badref"], tot["orphans"])
    if got != (356, 5886, 2083, 2083, 0, 4):
        raise SystemExit(
            f"씬 모듈 분모가 갈렸다 {got} (기대 356모듈 · 5886 스트림 · 2083/2083 · 실패 0 · 고아 4)"
        )
    if reasm_fail:
        raise SystemExit(f"항등 재조립 실패 수가 갈렸다 (기대 0): {reasm_fail}")


_LEA_RE = re.compile(rb"[\x41\x43\x45\x47\x49\x4b\x4d]\xfa..", re.DOTALL)
_EVENT_REG = (
    b"\x2a\x7c\x00\x00\x83\xe8",
    b"\x2a\x7c\x00\x00\x84\x28",
)  # movea.l #$83E8|#$8428,a5 — 이벤트 표 등록 서비스


def event_table_sites(m: bytes) -> list[tuple[int, int]]:
    """(lea 자리, 표 자리) — `lea 표(pc),aN` 뒤 48B 안에서 이벤트 표 등록 서비스(`movea.l #$83E8|#$8428,a5`)를 부르는 것.
    이 표는 글이 아니라 맵 이벤트 자료다 — 빌드의 문안 뿌리 찾기가 오인해 문안 풀로 옮기고 제자리를 0 으로 지우면 맵 전체가 이벤트 타일이 된다(md-ed1 16씬, 10-20)."""
    out = []
    for mm in _LEA_RE.finditer(m):
        i = mm.start()
        t = i + 2 + struct.unpack(">h", m[i + 2 : i + 4])[0]
        if 0 <= t < len(m) and any(x in m[i + 4 : i + 52] for x in _EVENT_REG):
            out.append((i, t))
    return out


def event_table_extent(m: bytes, t: int) -> int:
    """이벤트 표의 끝 — 머리(`FF FF` 로 끝난다) 뒤에 8B 항목 `xx xx xx xx 06 (80|84) 00 00` 이 이어지는 만큼. 머리를 못 찾으면 0x30B."""
    h = m.find(b"\xff\xff", t, t + 32)
    if h < 0:
        return min(t + 0x30, len(m))
    p = h + 2
    while (
        p + 8 <= len(m)
        and m[p + 4] == 0x06
        and m[p + 5] in (0x80, 0x84)
        and m[p + 6 : p + 8] == b"\x00\x00"
    ):
        p += 8
    return p


def verify_event_tables(orig_bytes: bytes, new_bytes: bytes, replace: dict | None = None) -> int:
    """원판과 새 모듈의 이벤트 표가 바이트까지 같은지 본다 → 표 수. 표 범위는 `event_table_extent`, 번역된 스트림이 표 자리를 덮으면(표를 글로 오인) 실패."""
    starts = sorted(replace or {})
    sites = event_table_sites(orig_bytes)
    for i, t in sites:
        end = event_table_extent(orig_bytes, t)
        if any(t <= s_ < end for s_ in starts):
            raise ValueError(
                f"이벤트 표 @{t:#x}(lea@{i:#x}) 안에 번역 스트림이 시작한다 — 표를 글로 오인했다"
            )
        if new_bytes[t:end] != orig_bytes[t:end]:
            raise ValueError(f"이벤트 표 @{t:#x}(lea@{i:#x}) 가 원판과 다르다({end - t}B)")
    return len(sites)
