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
#   🔴 **반각 숫자는 본문 한복판에 온다** — `あれはまだ10歳のころじゃないか。` 처럼.
#     이걸 런 밖으로 보면 거기서 블록이 끊겨 **앞쪽 일본어가 어느 블록에도 안 들어간다.**
#     그러면 번역해도 화면엔 `あれはまだ１０그럴 나이였잖아.` 로 반만 한글이 된다
#     (2026-08-27 유저 스크린샷으로 잡혔다. 71 블록 · 146 자가 그렇게 새고 있었다).
#     ⚠ 런을 **시작**하지는 못한다 — 숫자만 있는 데이터를 텍스트로 오인하면 안 된다.
BODY_ASCII = frozenset(range(0x30, 0x3A))  # 0-9

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
    # 🔴 헤더 구역(매직 + 포인터표 37칸)은 **텍스트가 아니다.** 여기서부터 훑으면 마지막
    #   포인터의 하위 2 바이트가 SJIS 짝으로 디코드돼(`00 21 9C 9E` 의 `9C 9E` = `悚`)
    #   바로 뒤 맵 이름 블록의 머리에 붙는다. 22 개 파일이 그랬다 — 그 상태로 재삽입하면
    #   **포인터가 깨진다.** 맵 이름 자체는 번역 대상이라 구역만 건너뛴다.
    i = NAME_OFF if b[: len(MAGIC)] == MAGIC else 0
    n = len(b)
    st = None
    nch = 0
    while i < n:
        # 🔴 여는 옵코드는 **`02` + 서브 1 바이트**인데, 서브가 SJIS 첫 바이트 영역
        #   (`0x81~0x9F`·`0xE0~0xEF`)과 겹친다. 그냥 훑으면 `02 81 82 C8`(= `02 81` + `な`)
        #   에서 `81 82` 를 한 글자로 삼켜 **본문 첫 글자가 통째로 사라진다.** 라운드트립은
        #   통과하고(바이트 총합은 맞다) 재삽입하면 사라진 글자가 `head` 로 보존돼
        #   **우리 문안 앞에 붙는다.** 그래서 옵코드는 **두 바이트로 한 번에** 건너뛴다 —
        #   ⚠ 「`02` 다음 한 바이트만 건너뛴다」로 짰다가 `02 02 81 69`(= `02 02` + `（`)
        #   에서 거꾸로 본문을 먹었다. 서브가 `02` 인 것도 있다.
        if st is None and b[i] == 0x02:
            #   ⚠ 「`02` 다음 한 바이트만 건너뛴다」로 짰다가 `02 02 81 69`(= `02 02` + `（`)
            #   에서 거꾸로 본문을 먹었고, 「무조건 두 바이트」로 바꿨더니 이번엔 본문 바로
            #   앞에 우연히 `02` 가 있는 자리(`19 02 8B 83` = `…` + `泣`)를 먹었다.
            #   **두 해석을 다 재 보고 텍스트가 길게 이어지는 쪽**을 고른다.
            i += 2 if _run(b, i + 2) >= _run(b, i + 1) else 1
            continue
        if is_sjis_pair(b, i):
            if st is None:
                st, nch = i, 0
            i += 2
            nch += 1
            continue
        if st is not None and (b[i] in BODY_CTRL or b[i] in BODY_ASCII):
            i += 1
            continue
        if st is not None:
            _emit(b, out, st, i, nch)
            st = None
        i += 1
    if st is not None:
        _emit(b, out, st, n, nch)
    #   ⚠ **내보내고 나서** 되찾는다 — 스캔 중에 오프셋을 흔들면 뒤 블록의 경계가 같이
    #     밀린다. 여기서 하면 블록 수·색인이 그대로다.
    for blk in out:
        if suspect_head(blk):
            _reclaim_head(b, blk)
    return out


def _run(b, i):
    """`i` 부터 이어지는 텍스트 길이(글자 수) — 옵코드 경계를 가르는 자다."""
    n = 0
    while i < len(b):
        if is_sjis_pair(b, i):
            i += 2
            n += 1
        elif n and (b[i] in BODY_CTRL or b[i] in BODY_ASCII):
            i += 1
        else:
            break
    return n


def _emit(b, out, st, end, nch):
    term = b[end] if end < len(b) else None
    if nch < MIN_CHARS or term not in TERM_OK:
        return
    body = bytes(b[st:end])
    if not has_kana(body):
        return
    out.append({"off": st, "head": bytes(b[max(0, st - 2) : st]).hex(), "body": body, "term": term})


def suspect_head(blk):
    """머리가 **유효 SJIS 짝**인가 — 블록 시작이 한두 글자 밀렸다는 신호다.

    이 파서는 옵코드 문법을 다 풀지 않고 텍스트 런으로 경계를 잡는다. 본문 바로 앞이
    데이터면 정렬이 밀려 **첫 글자가 머리로 넘어간다**(전체의 0.1%, 대개 이름표).
    라운드트립은 통과하니 조용하고, 그 자리에 번역을 넣으면 **먹힌 글자가 우리 문안
    앞에 남는다**(`ラッ` + 「랩 할아버지」).

    ⚠ 맵 이름 블록(`NAME_OFF`)은 앞이 포인터표라 늘 걸린다 — 그건 오탐이다.

    ⓘ 이제 `_reclaim_head` 가 이 자리를 **되찾으므로** 남는 건 오탐뿐이다. 그래도 이
    함수를 남겨 둔다 — 되찾기가 못 미치는 자리를 다시 막는 그물이다.
    """
    h = bytes.fromhex(blk["head"])
    return blk["off"] != NAME_OFF and len(h) == 2 and is_sjis_pair(h, 0)


def _reclaim_head(b, blk):
    """머리로 넘어간 글자를 **본문으로 되찾는다** — 블록 수와 색인은 안 건드린다.

    🔴 왜 이게 필요한가. 본문 바로 앞 데이터가 **우연히 SJIS 짝**이면(`EC 95` · `88 83`)
    스캐너가 거기서 런을 시작했다가 두세 글자 만에 버린다. 버릴 때 **런의 시작이 아니라
    끝에서** 이어 가므로 그 사이의 진짜 시작을 지나친다. 결과가 `武器屋のベロネ` →
    `のベロネ` 다(실측 18 자리, 대개 화자 이름표라 **화면에 일본어로 남는다**).

    ⚠ 「버린 런의 시작 + 1 로 되감기」로도 고쳐지지만, 그러면 **없던 블록이 10 개
      생긴다**(`辟ロ`·`あ蕈` 같은 그래픽 오독). 블록이 늘면 색인이 밀려 **이미 넣은
      17,574 블록의 자리가 전부 어긋난다.** 그래서 되감지 않고 **밀린 블록만 뒤로**
      늘린다 — 블록 수·색인이 그대로다.

    멈추는 자리는 「머리가 더는 SJIS 짝이 아닐 때」다. 실측 18 자리가 전부 뜻이 서는
    일본어로 복원됐다(`ラップじいさん` · `ルドルフ王` · `を手に入れました。`).
    """
    st = old = blk["off"]
    end = old + len(blk["body"])
    while st >= 2 and st != NAME_OFF and is_sjis_pair(b, st - 2):
        st -= 2
    if st == old:
        return blk
    blk["off"] = st
    blk["body"] = bytes(b[st:end])
    blk["head"] = bytes(b[max(0, st - 2) : st]).hex()
    return blk


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
        elif body[i] in BODY_ASCII:
            out.append(chr(body[i]))
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
        elif "0" <= c <= "9":
            out.append(ord(c))
        elif c == "<" and i + 3 < len(s) and s[i + 3] == ">":
            out.append(int(s[i + 1 : i + 3], 16))
            i += 4
            continue
        else:
            out += enc(c)
        i += 1
    return bytes(out)
