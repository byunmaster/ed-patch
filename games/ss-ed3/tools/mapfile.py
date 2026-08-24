"""`/MAP/MAP*.BIN` 구조 정본 — 헤더 · 포인터표 · 대사 블록.

실측(2026-08-24, disc1 88 파일 전량):

    0x00  매직  `ED3WW MAPDATbin\\x1a` — 88/88 동일
    0x10  포인터표 **37칸 고정**, BE 32비트 **절대 주소**(LWRAM `0x00200000` 기준)
    0xA4  맵 이름(SJIS, NUL 종료) — 예 `アンデラ城` · `鷹の爪号`

⚠ **주소가 절대값이다** — 재삽입에서 블록을 옮기면 이 표와 스크립트 안의 `FD 03 <주소>`
레코드를 같이 고쳐야 한다. 지금은 **읽기만** 한다.

대사 블록 = **SJIS 2바이트 + 제어(`0D` 개행 · `0F` 페이지)로 이어지는 최대 구간**이다.
옵코드 문법을 다 풀지 않고도 경계가 잡힌다 — 마커 8,770 건 중 **99.0% 포착**(2026-08-24).

⚠ **「머리 옵코드로 찾는다」로 시작했다가 84% 에서 멈췄다.** 여는 꼴이 `02 <서브>` 하나가
   아니라 `FF 00` 로 바로 시작하는 것도 있었다 — 문법을 다 풀기 전에는 **텍스트 자체를
   저본으로 삼는 쪽**이 정확하다. 옵코드는 `head`(앞 2바이트)로 **기록만** 한다.

오탐을 거르는 조건 둘 (그래픽 바이트가 한자로 디코드되는 걸 막는다 —
루트 `docs/ports-survey.md` 「측정 방법」):

  · **종료 바이트가 `10`·`0E`·`00`·`09`·`FF`·`FE` 중 하나** — 스크립트가 실제로 쓰는 것들
  · **가나가 한 자 이상** — 일본어 문장은 가나 없이 안 간다. 그래픽 오탐은 한자만 나온다

이 둘로 런 8,406 개를 버리고 마커 손실은 92건(1.0%)이었다.

⚠ **재삽입 전에 라운드트립을 본다** — `dump_map.py --check` 가 「블록을 도로 끼워 넣으면
   원본과 바이트 동일한가」를 전 파일에서 확인한다. 경계를 한 칸 잘못 잡으면 옆 바이트를
   조용히 먹는다.
"""

MAGIC = b"ED3WW MAPDATbin\x1a"
BASE = 0x00200000  # LWRAM — 포인터가 가리키는 기준
PTR_OFF = 0x10
PTR_N = 37
NAME_OFF = PTR_OFF + PTR_N * 4  # 0xA4

CTRL_NL = 0x0D  # 개행
CTRL_PAGE = 0x0F  # 페이지 넘김
BODY_CTRL = (CTRL_NL, CTRL_PAGE)

# 블록 뒤에 올 수 있는 바이트 — 이 밖이면 그래픽 오탐으로 본다
TERM_OK = frozenset({0x10, 0x0E, 0x00, 0x09, 0xFF, 0xFE})
MIN_CHARS = 2

_HIRA = (0x829F, 0x82F1)
_KATA = (0x8340, 0x8396)


def is_sjis_pair(b, i):
    return (
        i + 1 < len(b)
        and (0x81 <= b[i] <= 0x9F or 0xE0 <= b[i] <= 0xEF)
        and 0x40 <= b[i + 1] <= 0xFC
        and b[i + 1] != 0x7F
    )


def has_kana(body):
    """가나가 한 자라도 있는가 — 그래픽 오탐(한자만 나온다)을 거르는 자다."""
    for i in range(len(body) - 1):
        if is_sjis_pair(body, i):
            c = (body[i] << 8) | body[i + 1]
            if _HIRA[0] <= c <= _HIRA[1] or _KATA[0] <= c <= _KATA[1]:
                return True
    return False


def parse_header(b):
    """`(포인터 37개, 맵이름)`. 매직·표가 안 맞으면 ValueError."""
    if b[: len(MAGIC)] != MAGIC:
        raise ValueError(f"매직 불일치: {bytes(b[:16])!r}")
    ptrs = []
    for i in range(PTR_N):
        o = PTR_OFF + i * 4
        v = int.from_bytes(b[o : o + 4], "big") - BASE
        if not 0 <= v <= len(b):
            raise ValueError(f"포인터 {i} 가 파일 밖이다: {v:#x} (크기 {len(b):#x})")
        ptrs.append(v)
    end = b.index(b"\x00", NAME_OFF)
    return ptrs, b[NAME_OFF:end].decode("shift_jis", "replace")


def blocks(b):
    """`[{off, head, body, term}]` — `body` 만이 길이가 바뀌는 자리다.

    `head` = 블록 **앞 2바이트**(여는 옵코드, 기록용) · `term` = 블록 **뒤 1바이트**.
    """
    out = []
    i = 0
    n = len(b)
    st = None
    nch = 0
    while i < n:
        if is_sjis_pair(b, i):
            if st is None:
                st, nch = i, 0
            i += 2
            nch += 1
            continue
        if st is not None and b[i] in BODY_CTRL:
            i += 1
            continue
        if st is not None:
            _emit(b, out, st, i, nch)
            st = None
        i += 1
    if st is not None:
        _emit(b, out, st, n, nch)
    return out


def _emit(b, out, st, end, nch):
    term = b[end] if end < len(b) else None
    if nch < MIN_CHARS or term not in TERM_OK:
        return
    body = bytes(b[st:end])
    if not has_kana(body):
        return
    out.append({"off": st, "head": bytes(b[max(0, st - 2) : st]).hex(), "body": body, "term": term})


def text_of(body):
    """본문 bytes → 사람이 읽는 꼴(`\n` 개행 · `\f` 페이지 넘김)."""
    out = []
    i = 0
    while i < len(body):
        if is_sjis_pair(body, i):
            # ⚠ SJIS 자리에 있어도 **표준 표에 없는 짝**이 있다(게임 전용 글자로 보인다).
            #   `replace` 로 뭉개면 되돌릴 수 없다 — 바이트 그대로 남긴다.
            try:
                out.append(body[i : i + 2].decode("shift_jis"))
            except UnicodeDecodeError:
                out.append(f"<{body[i]:02X}><{body[i + 1]:02X}>")
            i += 2
        elif body[i] == CTRL_NL:
            out.append("\n")
            i += 1
        elif body[i] == CTRL_PAGE:
            out.append("\f")
            i += 1
        else:
            out.append(f"<{body[i]:02X}>")
            i += 1
    return "".join(out)


def encode_text(s, char=None):
    """`text_of` 의 역 — 되끼울 때 쓴다(라운드트립이 이 짝을 본다).

    `char` 로 **글자 하나의 인코더**를 갈아끼운다(한글은 슬롯 SJIS 로 나간다).
    🔴 **제어코드 규약은 여기 한 곳에만 둔다.** 부르는 쪽이 각자 인코딩하면
    `"\n".encode("shift_jis")` 가 `0x0A` 를 내는데 게임 개행은 `0x0D` 라, **길이가 같아
    모든 검사를 통과하고 화면에서만 조판이 깨진다**(2026-08-24 실제로 물렸다).
    """
    enc = char or (lambda c: c.encode("shift_jis"))
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\n":
            out.append(CTRL_NL)
        elif c == "\f":
            out.append(CTRL_PAGE)
        elif c == "<" and i + 3 < len(s) and s[i + 3] == ">":
            out.append(int(s[i + 1 : i + 3], 16))
            i += 4
            continue
        else:
            out += enc(c)
        i += 1
    return bytes(out)
