"""씬 포맷 조각 → 화면에 나가는 문자열 → 쪽.

`%c` 인자는 스크립트가 넘기는 제어 코드(2=이름색 시작 · 1=복귀 · 6/8/11/12=쪽 끝)이고, `%s` 는 이름 주입 자리다.
쪽은 종단 코드(6/8/11/12)에서 나뉜다 — 엔진 호출 하나가 쪽 하나다. 종단 코드 자체는 찍는 문자열에서 뗀다.
"""

PAGE_END = (6, 8, 11, 12)
HERO_NAME_ADDR = {"ED1": 0x801157AC, "ED2": 0x800F103C}  # 주인공 이름 버퍼(NUL 종단)


def read_cstr(peek, addr: int, n: int = 24) -> bytes:
    return peek(addr, n).split(b"\0")[0]


def evaluate(fmt: bytes, args, peek, game: str, name: bytes | None = None) -> bytes:
    """sprintf 흉내: `%c`→코드, `%s`→이름, `%d`→대표 수치.

    인자를 못 얻은 `%c` 는 이름창 직후면 1(복귀), 아니면 6(쪽 끝)으로 둔다.
    `%s` 는 name 이 주어지면 그것을, 아니면 인자 주소가 RAM 이면 그 문자열을, 아니면 주인공 이름을 쓴다.
    """
    hero = read_cstr(peek, HERO_NAME_ADDR[game])
    out = bytearray()
    i = k = 0
    prev = None
    while i < len(fmt):
        c = fmt[i]
        if c == 0x25 and i + 1 < len(fmt) and fmt[i + 1] in b"csd":
            kind = fmt[i + 1]
            a = args[k] if args and k < len(args) else None
            k += 1
            if kind == 0x63:  # %c
                if a is None:
                    a = 1 if prev == 2 else 6
                out.append(a & 0xFF)
                prev = a
            elif kind == 0x73:  # %s
                if name is not None:
                    out += name
                else:
                    out += read_cstr(peek, a) if (a and a > 0x80000000) else hero
            else:  # %d
                out += b"100"
            i += 2
        elif c >= 0x81:
            out += fmt[i : i + 2]
            i += 2
        else:
            out.append(c)
            i += 1
    return bytes(out)


def pages_of(full: bytes) -> list[bytes]:
    pages, cur, i = [], bytearray(), 0
    while i < len(full):
        c = full[i]
        if c >= 0x81:
            cur += full[i : i + 2]
            i += 2
            continue
        cur.append(c)
        i += 1
        if c in PAGE_END:
            cur.pop()  # 종단 코드는 내용이 아니라 제어다 — 실제 흐름에서 창을 닫거나 곧장 이어 버리므로 떼고 찍는다
            if cur:
                pages.append(bytes(cur))
            cur = bytearray()
    if cur:
        pages.append(bytes(cur))
    return pages
