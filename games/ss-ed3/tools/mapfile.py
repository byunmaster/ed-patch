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

import json
import os
import re

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

CTRL_INJECT = 0x01  # 런타임 주입 — `01 <번호>` 두 바이트가 한 토큰이다
#   🔴 **본문 한복판에 온다** — `ジュリオは\n<01><87>を手に入れました。` 처럼 아이템 이름이
#     여기 끼어든다. 한 바이트짜리 제어로 보면 **거기서 런이 끊겨** 앞쪽(`ジュリオは`)이
#     어느 블록에도 안 들어가고, 뒤쪽만 블록이 된다 — 그래서 우리 문안이 「, 손에 넣었다.」
#     처럼 **쉼표로 시작**하고 있었다. 화면엔 `ジュリオは` 가 일본어로 남는다
#     (2026-08-28 유저 스크린샷으로 잡혔다. 40 블록이 그렇게 잘려 있었다).
#     ⚠ 런을 **시작**하지는 못한다 — 데이터 한복판의 `01` 을 텍스트로 오인하면 안 된다.

# 블록 뒤에 올 수 있는 바이트 — 이 밖이면 그래픽 오탐으로 본다
#   ⚠ 이 자가 좁으면 **블록이 조용히 사라진다.** 덤프에 아예 안 실리니 진척률에도 안 잡히고
#     (분모가 「파서가 찾은 것」이라 99.95% 로 보였다) 화면에만 일본어가 남는다.
#     빌드 이미지를 SJIS 로 훑어 되짚었더니 `MAP*.BIN` 에 **4,301자**가 그렇게 빠져 있었다
#     (2026-08-29). 종료 바이트별로 세어 위 넷을 더하니 **3,079자·260 블록**이 돌아왔다.
#   🔴 남은 1,222자는 **더하면 안 된다** — 종료가 `0xA5`·`0xA1`·`0x9D` 같은 SJIS 첫 바이트라
#     그래픽 한복판이다(런 몸통이 `焜焜焜焜` 꼴로 나온다). 이 자를 넓히는 판단은 **글자수가
#     아니라 몸통이 문장인가**로 한다.
#   ⚠ 넓히면 **블록 색인이 밀린다**(실측 7,148 건). `script/MAP*.json` 의 `_jp` 지문으로
#     재배치하고 `stamp_script.py --check` 로 확인한다 — 색인만 믿으면 번역이 엉뚱한 대사
#     자리에 조용히 들어간다.
#   ⓘ **2 차로 다섯을 더 열었다**(같은 날) — 남은 1,222자를 종료 바이트별로 **전량 눈으로**
#     확인해 갈랐다. `0x08`(16 런) · `0x28`(3) · `0x29`(4) · `0x2E`(1) 은 **전부 진짜**였고,
#     `0xA4`(7) 만 진짜 셋 + 그래픽 넷이 섞였다 — 그래픽 넷은 블록으로 잡히되 안 옮긴다
#     (`査烙ヨ` · `怎…` · `壕レ`×2). `0x07` 은 개발자 테스트 맵 전용이라 안 열었다.
TERM_OK = frozenset(
    #   3 차 — 남은 것을 다시 전량 확인해 넷을 더 열었다. `0x2C`·`0x5B`·`0xB6` 은 진짜뿐이고,
    #   `0xA1` 은 16 중 진짜 셋이라 **깨진 바이트 자**(`_MOJIBAKE`)를 같이 세웠다.
    {0x10, 0x0E, 0x00, 0x09, 0xFF, 0xFE, 0x06, 0x02, 0x19, 0x0A,
     0x08, 0x28, 0x29, 0x2E, 0xA4, 0x2C, 0x5B, 0xB6, 0xA1}
)
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


#   가나 없이도 성립하는 자리 둘. 가나 필터는 그래픽 오탐을 거르는 **거친 자**라서,
#   진짜 문장까지 같이 버린다 — 실측 533 런·2,731자(2026-08-29).
#   ⚠ 통째로 열면 안 된다. 버려진 것의 대부분은 **연속 JIS 코드**(`巨拒朽求`)나 같은 글자
#     반복(`埴埴場壌`)이라 사람이 보면 바로 갈리지만 기계는 못 가른다.
_PUNCT = set("・。、！？…「」『』〜ー　．，")


def _punct_only(s):
    """부호만으로 된 「침묵」 대사인가 — `・・・・・。` 부류(실측 172 런)."""
    core = s.replace("\r", "").replace("\x0f", "")
    return bool(core) and all(c in _PUNCT for c in core)


#   🔴 **거꾸로도 샌다** — 그래픽 바이트가 가나로 디코드돼 필터를 통과한다. 그때 몸통엔
#     **키릴·그리스 자모**가 섞인다(`隻硯…ヤBВ`) — 이 게임 문안엔 그런 글자가 없다.
#   ⚠ **U+FFFD(디코드 실패)는 자로 쓰면 안 된다** — 이 게임엔 `0x8540` 처럼 표준 SJIS 에
#     없는 **게임 전용 짝**이 진짜 대사 안에 실재한다(`tests/test_mapfile.py`).
#     처음에 U+FFFD 를 넣었다가 그 테스트가 바로 울렸다.
_MOJIBAKE = re.compile("[\u0370-\u03ff\u0400-\u04ff]")

KANA_FREE = "kana_free_blocks.json"
_LISTS = None


def _load_lists():
    """가나 자를 넘어야/못 넘어야 하는 자리의 정본 — 이름표(`侍女`) · 장 표시(`弐章`).

    🔴 판단이 담긴 자료라 커밋되는 파일이다(루트 CLAUDE.md 「제1 원칙」).
    늘리려면 **사람이 눈으로 보고** 고른다 — 자동 판정은 아직 없다.
    """
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), KANA_FREE)
    if not os.path.exists(p):
        return frozenset(), frozenset()
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return frozenset(d.get("text", ())), frozenset(d.get("not_text", ()))


def is_text(body):
    """이 런을 대사로 볼 것인가 — 가나가 있거나, 부호만이거나, 정본에 있거나."""
    global _LISTS
    if _LISTS is None:
        _LISTS = _load_lists()
    ok, no = _LISTS
    s = body.decode("cp932", "replace")
    if s in no or _MOJIBAKE.search(s):
        return False
    if has_kana(body):
        return True
    return _punct_only(s) or s in ok


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
        if st is not None and b[i] == CTRL_INJECT and i + 1 < n:
            i += 2
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
        elif n and b[i] == CTRL_INJECT and i + 1 < len(b):
            i += 2
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
    if not is_text(body):
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
        #   🔴 **주입 토큰이 먼저다.** `01 <번호>` 를 한 바이트씩 보면 파라미터가 **옆 바이트와
        #     짝지어져** SJIS 로 읽힌다 — `01 87 82 F0`(=`<01><87>` + `を`)이 `<01>` + `87 82`(짝
        #     실패) + `<F0>` 가 됐다. 그러면 뒤 글자가 통째로 어긋난다.
        if body[i] == CTRL_INJECT and i + 1 < len(body):
            out.append(f"<{body[i]:02X}><{body[i + 1]:02X}>")
            i += 2
            continue
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
        elif (
            c == "<"
            and i + 3 < len(s)
            and s[i + 3] == ">"
            #   ⚠ **16진 두 자리일 때만** 이스케이프로 읽는다. 그냥 `<두 글자>` 로 보면
            #     `<추가>` 같은 우리 문안이 `int("추가", 16)` 에서 죽는다(에이전트 실측
            #     2026-08-28 — `<덧붙임>` 으로 피해 갔다). 표제·말머리에 꺾쇠를 쓸 수 있어야 한다.
            and all(x in "0123456789abcdefABCDEF" for x in s[i + 1 : i + 3])
        ):
            out.append(int(s[i + 1 : i + 3], 16))
            i += 4
            continue
        else:
            out += enc(c)
        i += 1
    return bytes(out)
