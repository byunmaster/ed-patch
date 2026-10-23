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

import hashlib
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
# 우리가 연 조사 코드 — 원본 표에선 인자 0(핸들러가 rts 뿐인 빈 코드)이지만 빌드가 1 로 고친다.
# 원본 문안엔 한 번도 안 나오므로 파서를 미리 1 로 맞춰 둬도 원본 파싱은 그대로다(`tools/josa.py`).
ARGS[0xEB] = 1
ARGS[0xEC] = 1

GOTO, CALL, CELL, CODE, MULTI = "goto", "call", "cell", "code", "multi"
COND = {0x11, 0x12, 0xF2, 0xF8}  # 다음 3B(대개 0F goto)를 조건부로 건너뛴다
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

SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){1,8})\x04")


@dataclass
class Token:
    off: int  # 모듈 안 오프셋
    raw: bytes
    kind: str = "text"  # text | ctl | end
    code: int = -1
    ref: str | None = None  # goto/call/cell/code
    target: int = -1  # 모듈 안 오프셋(참조가 있을 때)
    targets: tuple = ()  # MULTI(16) — 변위 다섯 각각의 착지(각자 자기 위치 기준). target = 첫째

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
            elif c == 0x16:
                # 파티 리더별 분기 — 변위 다섯, **각자 자기 자리 기준**(블록 34: 같은 착지 셋이 변위 240·238·236)
                offs = struct.unpack(">5h", raw[1:11])
                t.ref = MULTI
                t.targets = tuple(t.argpos + 2 * k + o for k, o in enumerate(offs))
                t.target = t.targets[0]
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


EVENT_TABLE_REG = re.compile(rb"\x46\xdf\x48\xe7..\x3a\x7c(?:\x83\xe8|\x84\x28)", re.DOTALL)


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
        # 🔴 이벤트 표 등록(`lea 표,a1; 46DF; 48E7 …; movea.w #$83E8|#$8428,a5; … jsr (a6)`) 은 문안이 아니다 — 표 첫 항목 `80 00 1E 1C …` 의
        # 0x1E 가 화자 태그로 읽혀 「문안다움」 검사를 통과하면 재조립이 표를 문안 풀로 옮기고 원래 자리를 0 으로 지워, 이벤트 조회가
        # 한글 글자 바이트(≥0x80 = 와일드카드)를 항목으로 읽어 맵 전체가 이벤트 타일이 된다(10-20 씬 179 LOAD 후 map=0000 폭주, 16씬 영향).
        if EVENT_TABLE_REG.match(b, m.start() + 4):
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
    entries: dict[int, int] = field(default_factory=dict)  # 절대 오프셋 BE16 자리 → 스트림 시작
    forced: dict[int, int] = field(default_factory=dict)  # 낡은 변위를 고친 lea(뿌리 규칙 밖) → 대상
    pool_ins: int | None = None  # 문안 풀의 첫 스트림을 가리키는 lea
    orphans: list[int] = field(default_factory=list)  # 참조 없이 앞 스트림 끝에서 이어 읽히는 스트림(ORPHANS)


def looks_like_text(st: Stream) -> bool:
    """뿌리 후보가 스트림인가 — 글자가 있거나, 참조(goto/call/셀/코드)가 있거나, 화자 태그가 있다.
    ⚠ `12 xxxx 0F yyyy` 처럼 제어코드뿐인 분기 허브도 스트림이다 — 글자만 보면 버려진다(실측 142건)."""
    n = sum(len(t.raw) for t in st.tokens if t.kind == "text")
    return n >= 2 or any(t.ref or t.code == 0x1E for t in st.tokens)


CHAIN_HEADS = {0x08, 0x09, 0x0B, 0x0E, 0x10, 0x11, 0x12, 0x13, 0x16, 0x1E}  # 실측 뿌리 스트림 머리
FLOW = {0x06, 0x07, 0x0A, 0x0D}  # 이 코드로 끝난 스트림은 **물리적으로 다음 스트림으로 이어진다**(상점·NPC 대사 사슬)


def _clean(b: bytes, st: Stream) -> bool:
    """사슬에 넣어도 되는 스트림 — 문안 꼴이고 글자 토막이 전부 SJIS 로 풀린다."""
    if not _textlike(st):
        return False
    if sum(1 for t in st.tokens if t.kind == "text" for c in t.raw if is_lead(c)) < 3:
        return False  # 화자 태그만 걸려 통과한 쓰레기(「<1e>9」)를 거른다
    first = st.tokens[0]
    if first.kind != "text" and first.code not in CHAIN_HEADS:
        return False  # 표·자료가 SJIS 로 풀리는 우연(`0C xx` 로 시작)을 거른다
    prev = None
    for t in st.tokens:
        if t.kind == "text":
            try:
                t.raw.decode("cp932")
            except UnicodeDecodeError:
                return False
            if prev is not None and prev.code == 0x02 and not is_lead(t.raw[0]):
                return False  # `02 xx` 표 항목(BE16)이 이름 삽입 + 반각 글자로 읽힌 우연
        prev = t
    return True


# 블록 161(미니게임 문안, 원본 sha1) — 문안 풀 앞이 10B 밀린 채 조립돼 **문안 lea 가 전부 문장 한복판을 가리킨다**
# (+10 하면 19곳 모두 제어코드 뒤 문장 경계, `bsr` 셋은 `48E7` 진입점). 마스터 10-11 「미니게임은 번역해 둔다」
STALE_SHIFT = {"08ddb695eff9584f4090abbbe45ea263513f9a80": 10}


# 연속 스트림 — 문안 호출이 `a1` 을 복원하지 않아 **앞 스트림이 00 으로 끝난 자리에서 이어 읽히는** 스트림들.
# 가리키는 lea 가 없어 참조 규칙이 못 찾는다(숨은 일본어 덩이 56런, 마스터 10-11). 재조립이 앞 스트림만 옮기면
# 이어 읽기가 엉뚱한 스트림으로 샌다. 원본 sha1 → 그 블록의 연속 스트림 머리들(물리 순서, 글자 없는 `00` 포함).
# 목록 밖 자리로 넓히지 않는다. 새 바이트를 다시 읽을 땐 꼬리(옮겨 쓴 영역)의 덮이지 않은 자리가 곧 이것들이다.
ORPHANS = {
    "51cc4c323548de787075fd28adb96407076efd5e": [0xAE0, 0xB40],  # 33
    "0d4db15700c95dbe70d30a80efcd8b474fa8b965": [0xAC0, 0xB7D, 0x12CD, 0x12CE, 0x13DB],  # 85
    "ce788cd31fd939bade3b6b29732b3490d784d629": [0x9D1, 0x9F9],  # 92
    "5803383c1252ab37f495ddd40592534c5bda3a2f": [0xEA6],  # 115
    "44abf9621594d15e3bf8b1690d5ae11e4f6658b6": [0x794],  # 117
    "45783940a6de82c6820dc9ecbff8606e3c9cede1": [0x7D7, 0x7D8, 0x7E5, 0x83B],  # 141
    "b8172c01b408fec917a9d5050187c72d9d62a349": [0x1706],  # 174
    "31cd87dd0c73bbeec77385e08be7537889519b1f": [0xE67, 0xE68],  # 176
    "da668fd946fc8e307c6bf72574e6c6cb1c88146c": [0x86D, 0x86E],  # 223
}


def _walk_pool(b: bytes, first: int) -> tuple[list[int], int]:
    """`first` 에서 연달아 읽히는 문안 스트림 머리들(글자 없는 끝 코드뿐인 줄은 건너뜀)과 풀의 끝."""
    starts: list[int] = []
    q = first
    while q < len(b):
        try:
            st = parse_stream(b, q)
        except (ValueError, IndexError):
            break
        bare = len(st.tokens) == 1 and st.tokens[0].kind == "end"
        if not bare and not any(t.kind == "text" and any(map(is_lead, t.raw)) for t in st.tokens):
            break
        if not bare:
            starts.append(q)
        q = st.end
        if st.tokens[-1].kind == "end" and st.tokens[-1].code == 0x00:
            break  # 풀의 마지막 스트림은 00 으로 닫힌다 — 그 뒤는 코드다
    return starts, q


def fix_stale(b: bytes, shift: int) -> tuple[bytes, list[int], dict[int, int]]:
    """(낡은 변위를 `shift` 만큼 바로잡은 사본, 문안 풀의 스트림 머리들, 고친 lea → 대상).
    풀 = 문안 lea 중 +shift 가 깨끗한 스트림 머리(앞이 끝 코드·`rts`)인 것에서 시작해 연달아 읽히는 스트림 줄.
    lea 는 +shift 가 풀의 머리(또는 풀 스트림 한복판 토막 머리)인 것을, 풀 안 `goto` 는 같은 만큼 고친다.
    ⚠ **코드 쪽 분기(`bsr`·`bra`…)는 안 건드린다** — 코드도 뒤쪽 절반이 10B 밀려 있어(`bsr` 대상이 자료 한복판,
    +10 이면 `48E7` 진입점) 고치려면 앞→뒤로 걸치는 분기를 전부 디스어셈블로 골라야 한다. 원판도 같은 상태다."""
    leas = []
    for m in re.finditer(rb"\x43\xfa(..)", b, re.DOTALL):
        leas.append((m.start(), m.start() + 2 + struct.unpack(">h", m.group(1))[0] + shift))
    ends = (0x00, 0x05, 0x06, 0x07, 0x0A, 0x0D, 0xFC, 0x75)
    first = None
    for _, t in sorted(leas, key=lambda x: x[1]):
        if not 0 < t < len(b) or b[t - 1] not in ends:
            continue
        try:
            st = parse_stream(b, t)
        except (ValueError, IndexError):
            continue
        if _clean(b, st):
            first = t
            break
    if first is None:
        return b, [], {}
    starts, pool_end = _walk_pool(b, first)

    def inner(t: int) -> bool:
        """풀 스트림 한복판의 토막 머리 — 앞이 끝·쪽 넘김 코드이고 거기서 읽히는 꼴이 문안이거나 끝 코드뿐이다."""
        if not first <= t < pool_end or b[t - 1] not in ends:
            return False
        try:
            st = parse_stream(b, t)
        except (ValueError, IndexError):
            return False
        return (len(st.tokens) == 1 and st.tokens[0].kind == "end") or _textlike(st)

    out = bytearray(b)
    fixed: dict[int, int] = {}
    for ins, t in leas:
        if t in starts or inner(t):
            out[ins + 2 : ins + 4] = struct.pack(">h", t - (ins + 2))
            fixed[ins] = t
    # 풀 안 `goto` 도 같은 만큼 낡았다(「会心」 뒤 goto 는 글자 한복판에 닿고, +shift 면 「痛恨」 뒤 「の 一撃」 머리)
    for s_ in starts:
        for tok in parse_stream(b, s_).tokens:
            if tok.ref == GOTO and tok.target not in starts:
                rel = struct.unpack(">h", tok.raw[1:3])[0]
                out[tok.off + 1 : tok.off + 3] = struct.pack(">h", rel + shift)
    return bytes(out), starts, fixed


def parse_module(b: bytes, hint: Module | None = None) -> Module:
    """`hint` = 원본 모듈 — 재조립한 새 바이트를 다시 읽을 때 원본이 찾은 **표 자리**(entries)를 알려 준다
    (새 바이트에선 표가 문안 바로 앞에 붙어 있지 않아 위치만으로는 못 찾는다)."""
    sha = hashlib.sha1(b).hexdigest()
    if (shift := STALE_SHIFT.get(sha)) is not None:
        b, pool, forced = fix_stale(b, shift)
    elif hint is not None and hint.forced:
        # 재조립한 새 바이트 — 원본이 고친 lea 자리를 그대로 뿌리로 읽고, 풀은 첫 lea 에서 다시 걷는다
        forced = {ins: ins + 2 + struct.unpack(">h", b[ins + 2 : ins + 4])[0] for ins in hint.forced}
        pool = _walk_pool(b, forced[hint.pool_ins])[0]
    else:
        pool, forced = [], {}
    roots = lea_roots(b) | forced
    tables = table_roots(b)
    streams: dict[int, Stream] = {}
    bad: list[int] = []
    cells: set[int] = set()
    codes: set[int] = set()
    badref: list[int] = []
    cov = bytearray(len(b))

    def visit(work: list[int]) -> None:
        while work:
            t = work.pop()
            if t in streams:
                continue
            try:
                st = parse_stream(b, t)
            except (ValueError, IndexError):
                badref.append(t)
                continue
            streams[t] = st
            cov[t : min(st.end, len(b))] = b"\x01" * (min(st.end, len(b)) - t)
            # 조건부(11·12·F2·F8) 뒤의 goto 는 「3B 건너뜀」으로 넘어갈 수 있다 — 그 뒤도 뿌리다
            if len(st.tokens) >= 2 and st.tokens[-1].code == 0x0F and st.tokens[-2].code in COND:
                work.append(st.end)
            for tok in st.tokens:
                if tok.ref in (GOTO, CALL):
                    work.append(tok.target)
                elif tok.ref == MULTI:
                    work.extend(tok.targets)
                elif tok.ref == CELL:
                    cells.add(tok.target)
                elif tok.ref == CODE:
                    codes.add(tok.target)

    work = []
    for ins, t in roots.items():
        try:
            parse_stream(b, t)
        except ValueError:
            bad.append(ins)
            continue
        work.append(t)
    orphans = list(ORPHANS.get(sha, []))
    work += [tr.target for tr in tables] + pool + orphans
    visit(work)

    def chain(q: int) -> list[Stream]:
        """q 에서 흐름(FLOW 코드)을 따라가는 스트림 사슬 — 아직 안 덮인 자리만."""
        out = []
        while 0 <= q < len(b) and not cov[q]:
            try:
                st = parse_stream(b, q)
            except (ValueError, IndexError):
                break
            if not _clean(b, st) or any(cov[st.start : min(st.end, len(b))]):
                break
            out.append(st)
            last = st.tokens[-1]
            if not (last.kind == "end" and last.code in FLOW):
                break
            q = st.end
        return out

    entries: dict[int, int] = {}
    if hint is not None:
        for p in hint.entries:
            v = struct.unpack(">H", b[p : p + 2])[0]
            entries[p] = v
            visit([v])
    # 흐름 이음 — 이미 찾은 스트림이 06·07·0A·0D 로 끝나고 바로 뒤에 문안이 이어진다
    # 사슬을 한 번에 더한다(새로 더한 스트림의 이음도 같은 사슬에서 처리된다)
    for _ in range(8):
        grew = False
        for st in list(streams.values()):
            last = st.tokens[-1]
            if last.kind == "end" and last.code in FLOW and st.end < len(b) and not cov[st.end]:
                ch = chain(st.end)
                if ch:
                    visit([c.start for c in ch])
                    grew = True
        if hint is None:
            grew |= _find_entries(b, cov, chain, visit, entries)
        if not grew:
            break
    if hint is not None and hint.orphans:
        # 새 바이트 — 꼬리는 스트림만 이어 붙인 영역이라, 덮이지 않은 자리가 곧 연속 스트림이다
        q = len(hint.data) + (len(hint.data) & 1)
        while q < len(b):
            if q in streams:
                q = streams[q].end
                continue
            if cov[q]:
                q += 1
                continue
            try:
                st = parse_stream(b, q)
            except (ValueError, IndexError):
                break
            orphans.append(q)
            visit([q])
            q = max(st.end, q + 1)
    return Module(
        b,
        {i: t for i, t in roots.items() if i not in bad},
        streams,
        bad,
        cells,
        codes,
        badref,
        tables,
        entries,
        forced,
        min(forced, key=lambda i: forced[i]) if forced and hint is None else (hint.pool_ins if hint else None),
        orphans,
    )


def _find_entries(b, cov, chain, visit, entries) -> bool:
    """문안 머리 바로 앞(`4E71` 은 건너뜀)에 이어 붙은 BE16 절대 오프셋 — 상점·NPC 의 「말 목록」 표.
    값이 사슬의 스트림 시작이면 표 항목이다(사슬 안 다른 값, 예: 표 뒤 자료를 가리키는 것은 건드리지 않는다)."""
    grew = False
    for q in range(4, len(b)):
        if cov[q]:
            continue
        r = q - 2 if b[q - 2 : q] == b"\x4e\x71" else q
        v = struct.unpack(">H", b[r - 2 : r])[0]
        if not q <= v < len(b):
            continue
        ch = chain(q)
        if not ch:
            continue
        starts = {st.start for st in ch}
        end = ch[-1].end
        ws = []
        extra = list(ch)
        p = r - 2
        while p >= 0:
            if cov[p] or cov[p + 1]:
                break  # 이미 문안인 자리는 표가 아니다
            v = struct.unpack(">H", b[p : p + 2])[0]
            if q <= v < end and v not in starts:
                pass  # 사슬 한복판 — 글자 둘째 바이트에서 읽히는 우연이다
            elif v in starts:
                ws.append((p, v))
            elif 0 < v < len(b) and not cov[v] and (c2 := chain(v)):
                ws.append((p, v))
                extra += c2
            elif q <= v <= end:
                pass  # 사슬 안/끝을 가리키는 자료 — 건드리지 않는다
            else:
                break
            p -= 2
        if q in {v for _, v in ws}:
            for p_, v in ws:
                entries[p_] = v
            visit([st.start for st in extra])
            grew = True
    return grew


def coverage(mod: Module) -> tuple[int, int]:
    """(화자 태그 수, 그중 스트림 안에 있는 수)."""
    cov = bytearray(len(mod.data))
    for st in mod.streams.values():
        for t in st.tokens:
            cov[t.off : t.off + len(t.raw)] = b"\x01" * len(t.raw)
    tags = list(SPEAKER.finditer(mod.data))
    return len(tags), sum(1 for m in tags if cov[m.start()])


# ── 재조립 ─────────────────────────────────────────────────────────────────────


GOTO_CODE = 0x0F
LAST_POS: dict[int, int] = {}


def _fall_successor(mod: Module, s: int) -> int | None:
    """스트림 `s` 가 끝난 뒤 **물리적으로 이어 읽힐 수 있는** 원본 스트림의 시작(없으면 None).

    이어 읽히는 끝 = 조건 분기(`11/12 xxxx` + `0F yyyy` — 조건이 맞으면 goto 를 건너뛴다)."""
    t = mod.streams[s].tokens
    if not (
        len(t) >= 2
        and t[-1].kind == "ctl"
        and t[-1].code == GOTO_CODE
        and t[-2].kind == "ctl"
        and t[-2].code in (0x11, 0x12)
    ):
        return None
    end = s + sum(len(x.raw) for x in t)
    return end if end in mod.streams else None


def _successor(mod: Module, s: int) -> int | None:
    """`s` 바로 뒤에 **물리적으로 붙어 읽혀야 하는** 원본 스트림의 시작 — 조건 분기 꼬리(`_fall_successor`) 또는
    **끝 코드(06·07·0A·0D) 사슬**(`FLOW` — 끝 코드로 돌아온 뒤 엔진이 다음 바이트를 이어 읽는다: 상점·NPC 대사 사슬).

    사슬을 안 챙기면 같은 끝을 나눠 쓰는 접미 스트림(앞 스트림 한복판에서 시작해 같은 곳에서 끝나는 것 — 154: 0x246 ⊃ 0x25b)이
    정렬 순서상 사이에 끼어 **바로 뒤가 엉뚱한 복사본**이 된다(구조 대조 10-22: 154 해적 문장 중복 · 41 끝 코드 06 이 하나 더).
    """
    if (fall := _fall_successor(mod, s)) is not None:
        return fall
    t = mod.streams[s].tokens
    if t and t[-1].kind == "end" and t[-1].code in FLOW:
        end = s + sum(len(x.raw) for x in t)
        return end if end in mod.streams else None
    return None


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
    # 1. 새 자리 — 방출 순서 = 원본 시작 순서 + **이어 읽기 꼬리 복사본**.
    #    조건 분기(`11/12 xxxx` + `0F yyyy`)는 조건이 맞으면 goto 를 건너뛰고 **물리적으로 바로 뒤 바이트**를 읽는다.
    #    원본에선 앞 스트림 둘이 같은 꼬리를 나눠 쓰기도 한다(뒤 스트림이 앞 스트림의 접미 — 195 보일 대사:
    #    0705 ⊃ 0733, 둘 다 끝이 0x7C5 꼬리). 여기선 스트림마다 따로 쓰므로 꼬리를 **그 스트림 바로 뒤에 한 벌 더** 둔다.
    emit: list[tuple[int | None, list[Token]]] = []
    for i, s in enumerate(order):
        emit.append((s, toks[s]))
        nxt = order[i + 1] if i + 1 < len(order) else None
        need, hops = _successor(mod, s), 0
        while need is not None and need != nxt and hops < 64:
            emit.append((None, toks[need]))  # 꼬리 복사본 — 참조되지 않는 익명 방출
            need, hops = _successor(mod, need), hops + 1
    # 게이트: 이어 읽기가 있는 스트림 바로 뒤 방출이 정말 그 원본 꼬리(토큰 그대로)인가 — 아니면 조건이 맞을 때 엉뚱한 글로 샌다.
    for i, (s, _tk) in enumerate(emit):
        if s is None:
            continue
        need = _successor(mod, s)
        if need is not None and (i + 1 >= len(emit) or emit[i + 1][1] is not toks[need]):
            raise ValueError(f"스트림 {s:#x} 의 이어 읽기 꼬리 {need:#x} 가 바로 뒤에 놓이지 않았다")
    for i, (s, tk) in enumerate(emit):  # 꼬리 복사본이 다시 이어 읽기를 가지면 그 꼬리도 바로 뒤여야 한다
        if s is not None:
            continue
        origin = next((k for k, v in toks.items() if v is tk), None)
        need = _successor(mod, origin) if origin is not None else None
        if need is not None and (i + 1 >= len(emit) or emit[i + 1][1] is not toks[need]):
            raise ValueError(f"꼬리 복사본 {origin:#x} 의 이어 읽기 꼬리 {need:#x} 가 바로 뒤에 놓이지 않았다")
    pos = {}
    cur = len(b)
    for s, tk in emit:
        if s is not None:
            pos[s] = cur
        cur += _emit_stream(tk)
    if cur > MODULE_MAX:
        raise ValueError(f"모듈이 {cur}B — 한도 {MODULE_MAX}B 를 넘는다")
    # 2. 내보내기
    out = bytearray()
    for _s, tk in emit:
        for t in tk:
            if t.ref is None:
                out += t.raw
                continue
            raw = bytearray(t.raw)
            tgt = pos.get(t.target, t.target) if t.ref in (GOTO, CALL) else t.target
            here = len(b) + len(out)
            if t.ref == MULTI:
                for k, old in enumerate(t.targets):
                    new = pos.get(old, old)
                    raw[1 + 2 * k : 3 + 2 * k] = struct.pack(">h", new - (here + 1 + 2 * k))
            elif t.code in (0xF5, 0xFB):
                rel = tgt - (here + 2)
                raw[2:4] = struct.pack(">h", rel)
            else:
                rel = tgt - (here + 1)
                raw[1:3] = struct.pack(">h", rel)
            out += raw
        if tk and tk[-1].kind == "eof":
            out.append(0)
    b += out
    LAST_POS.clear()
    LAST_POS.update(pos)  # 검수 도구용 — 원본 스트림 시작 → 새 자리
    # 3. 표 항목
    for tr in mod.tables:
        v = pos[tr.target] - tr.base
        if not 0 <= v < 0x10000:
            raise ValueError(f"표 오프셋 범위 초과 @{tr.word:#x}")
        b[tr.word : tr.word + 2] = struct.pack(">H", v)
    # 3b. 표 항목(절대 오프셋 BE16)
    for p, v in mod.entries.items():
        if not 0 <= pos[v] < 0x10000:
            raise ValueError(f"표 절대 오프셋 범위 초과 @{p:#x}")
        b[p : p + 2] = struct.pack(">H", pos[v])
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
    new = parse_module(new_bytes, orig)
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
    for p, v in orig.entries.items():
        remap[v] = struct.unpack(">H", new_bytes[p : p + 2])[0]
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
        if (tot["streams"], tot["hit"], tot["tags"], tot["badref"]) != (3452, 1436, 1437, 0):
            raise SystemExit("씬 모듈 분모가 갈렸다 (기대 3452 스트림 · 1436/1437 · 실패 0)")
        biggest = 0
        for _, b, _ in bl:
            mod = parse_module(b)
            new = reassemble(mod)
            verify_reassembly(mod, new)
            biggest = max(biggest, len(new))
        if biggest > MODULE_MAX:
            raise SystemExit(f"항등 재조립 모듈이 한도를 넘는다 {biggest}")
        print(f"  항등 재조립 225블록 검증 OK (최대 {biggest:,}B / 한도 {MODULE_MAX:,}B)")


def event_tables(b: bytes) -> list[bytes]:
    """모듈 안 이벤트 표 등록(`lea 표,a1; 46DF; 48E7 …; movea.w #$83E8|#$8428,a5`) 마다 표 바이트(항목 … 끝 FF 까지)."""
    out = []
    for m in re.finditer(rb"\x43\xfa(..)", b, re.DOTALL):
        if not EVENT_TABLE_REG.match(b, m.start() + 4):
            continue
        p = m.start() + 2 + struct.unpack(">h", m.group(1))[0]
        q = p
        # 항목 길이는 첫 바이트가 정한다(조회 루틴 `$1D4AA`: 비트5 → 12B · 비트6 → 8B · 아니면 6B, 첫 바이트 FF 가 끝)
        while 0 <= q < len(b) and b[q] != 0xFF and q - p < 12 * 300:
            q += 12 if b[q] & 0x20 else 8 if b[q] & 0x40 else 6
        out.append(bytes(b[p : q + 1]))
    return out


def verify_event_tables(orig_mods: list[bytes], new_mods: list[bytes]) -> int:
    """게이트 — 모든 모듈에서 이벤트 표가 원판과 한글 롬이 **바이트까지 같은가**(표가 문안 풀로 옮겨져 0 이 되거나 한글 바이트가
    섞이면 이벤트 조회가 맵 전체를 이벤트 타일로 읽는다 — 씬 179 LOAD 폭주). → 검사한 표 수."""
    n = 0
    for i, (jb, kb) in enumerate(zip(orig_mods, new_mods, strict=True)):
        jt, kt = event_tables(jb), event_tables(kb)
        if jt != kt:
            raise SystemExit(
                f"씬 {i} 이벤트 표가 원판과 다르다(표 {len(jt)}→{len(kt)}) — 재조립이 표를 문안으로 옮겼다"
            )
        n += len(jt)
    return n
