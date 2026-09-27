"""sfc-ed1 한글 인코더 — textmap 번역문(토큰·조사 자리표시자 포함) → 게임 코드 열.

코드 설계(D3, 제안 → 구현 선택 2026-09-05):
  · 한글·`…`(전각) = **2바이트** `[선두][색인]`. 선두는 `$C5~$CE`(원본이 시트 밖 기호 타일 $1D6~$1DF 에 쓰던 10코드)
    → 글리프 자리 9×256 = 2,304(수요 ~1,100). **가나 코드는 그대로 두므로** 번역 안 된 조각(가나)과 번역된 조각이
    한 롬에 섞일 수 있다(개발 빌드). 원문의 `$C5~$CE` 기호(240자리)는 번역이 끝나면 사라진다.
  · 반각 1칸: 공백 `$10` · 숫자 `$00~$09` · `!` `$0C` · `?` `$0F` · `ー` `$0B` · **`.`→`$83`(。자리) `,`→`$84`(、자리)** —
    글리프만 갈아 끼운다 · `「」` `$85/$86` · 영문은 원본에 있는 H M E P G O L D C A B 뿐(그 밖은 실패).
  · 조사 자리표시자 `{은/는}` 류: 앞이 **사전 토큰·글자**면 여기서 받침으로 확정, **런타임 치환**(`{D6}` 등)이면 조사
    코드 `[$CE][$F0+k]` 로 내려 렌더러 훅이 고른다(글리프 색인 상위 16자리를 조사에 예약 → 글리프 2,544).
  · 개행 `\\n` = `$CF`. 그 밖의 글자는 **실패**한다(조용히 빼지 않는다 — 스킬 규칙).
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import text  # noqa: I001
from shared.text import josa as josa_mod

# 🔴 **선두는 「원본이 글자로 한 번도 안 쓰는 코드」여야 한다**(2026-09-06 실측 정정).
# 안 그러면 **안 옮긴 문안이 일본어로 남는 게 아니라 엉뚱한 한글로 깨진다** — 그 코드를 선두로 읽고
# 다음 바이트를 색인으로 삼기 때문이다(pc98-ed1 이 같은 부류로 물렸다, 관리자 중계).
# 처음엔 `$C5~$CE` 10개를 썼는데 그중 **셋이 실제로 쓰인다**: `$CA`($0B:E8DE) · `$C8`($0B:FD26·$0B:FDAE)
# · `$CC`($0B:FD80). 대본 전량(140,787항목)에서 `kind == "char"` 로 세어 **한 번도 안 쓰이는 12개**로 갈았다.
# ⚠ 선두는 **우리가 반각으로 쓰는 코드**여도 안 된다 — `$8F`=C · `$C3`=A · `$C4`=B 는 `KR_TABLE` 이
# 쓰던 자리라, 문안에 영문이 하나만 들어가도 그 바이트가 **선두로 읽혀 뒤 글자를 삼킨다**(2026-09-07).
LEADS = [0x74, 0xAC, 0xC5, 0xC6, 0xC7, 0xC9, 0xCB, 0xCD, 0xCE]  # 9 · 전수 실측 ∖ 반각 영문
JOSA_LEAD = 0xCE
JOSA_BASE = 0xF0
JOSA_PAIRS = [
    "은/는",
    "이/가",
    "을/를",
    "와/과",
    "으로/로",
    "이라/라",
    "이다/다",
    "이/",
]  # 런타임 조사 코드 k = 색인
GLYPH_CAPACITY = len(LEADS) * 256 - (256 - JOSA_BASE)  # 2,288
_PAIR_FORMS = {  # (받침 있음, 없음) — shared 에 없는 것만 여기서
    "와/과": ("과", "와"),
    "이라/라": ("이라", "라"),
    "이다/다": ("이다", "다"),
    "이/": ("이", ""),
}

KR_TABLE: dict[str, int] = {str(i): i for i in range(10)}
KR_TABLE.update(
    {
        " ": 0x10,
        "!": 0x0C,
        "?": 0x0F,
        "ー": 0x0B,
        ".": 0x83,
        ",": 0x84,
        "「": 0x85,
        "」": 0x86,
        "\n": text.NEWLINE,
    }
)
KR_TABLE.update(
    {
        c: k
        for k, c in {
            0x87: "H",
            0x88: "M",
            0x89: "E",
            0x8A: "P",
            0x8B: "G",
            0x8C: "O",
            0x8D: "L",
            0x8E: "D",
            0x8F: "C",
            0xC3: "A",
            0xC4: "B",
        }.items()
    }
)
TOKEN_RE = re.compile(
    r"(\{[0-9A-F]{2}(?::[0-9A-F]{2})?\}|<[0-9A-F]{2}(?::[0-9A-F]+)?>|<@>|\{(?:은/는|이/가|을/를|와/과|으로/로|이라/라|이다/다|이/)\})"
)


# 🔴 한국식 문장부호(마스터 지시 2026-09-20) — 코드는 원본 `。`·`、`·`!`·`?` 그대로 쓰되 **시트 타일을
# 한글 글꼴 글리프로 덮는다**(`build.punct_bake`). 글리프가 칸 왼쪽에 붙어 오른쪽이 비므로 **뒤따르는
# 공백 한 칸은 안 낸다**(부호 공백 = 반각). 인게임·오프닝 공통이다(시트·인코더가 하나).
HALF_PUNCT = set(".,!?")

# 2칸(16×16) 글리프로 가는 기호 — 반각 8px 글리프가 없는 것들. 글꼴(Neo둥근모)에서 굽는다.
GLYPH_SYMBOLS = set("…~()·『』【】〜―")
# 스태프롤 「J.D.K.」 — J·K 는 반각 영문 표에 없고, D 는 표에 있지만 시트의 굵은 D 라 J·K 와 굵기가
# 갈린다(마스터 지적 2026-09-26). 셋 다 글꼴 글리프로 굽는다 — 대사 인코더는 D 를 계속 표로 쓴다.
CREDIT_GLYPHS = set("JDK")


def is_glyph(ch: str) -> bool:
    return ("가" <= ch <= "힣") or ch in GLYPH_SYMBOLS


def bad_index(i: int) -> bool:
    """🔴 색인 하위가 `$FF` 면 안 된다 — **사전 문자열은 `$FF` 로 끝난다**(`$02:E066` 의 복사 루프).
    그런 색인의 글자가 이름에 들어가면 문자열이 **거기서 잘린다**. 대본은 `$E0` 로 끝나 안 걸리지만
    사전은 걸린다 ⇒ 그 자리를 **비워 둔다**(32B 짜리 구멍 셋, 850 글리프 기준)."""
    return (i & 0xFF) == 0xFF


def repertoire(texts) -> list[str | None]:
    """번역문의 글자를 코드포인트순으로 늘어놓은 **자리 목록**(= 글리프 색인, 결정적).
    쓸 수 없는 색인은 `None` 으로 비워 둔다 — 자리와 색인이 1:1 이어야 표가 단순해진다."""
    chars = sorted({ch for t in texts for ch in t if is_glyph(ch) or ch in CREDIT_GLYPHS})
    slots: list[str | None] = []
    for ch in chars:
        while bad_index(len(slots)):
            slots.append(None)
        slots.append(ch)
    if len(slots) > GLYPH_CAPACITY:
        raise ValueError(f"글리프 {len(slots)} > 자리 {GLYPH_CAPACITY}")
    return slots


def index_map(slots: list[str | None]) -> dict[str, int]:
    return {ch: i for i, ch in enumerate(slots) if ch is not None}


def glyph_code(idx: int) -> bytes:
    return bytes([LEADS[idx >> 8], idx & 0xFF])


def pick_josa(prev_word: str, pair: str) -> str:
    """앞말(한글로 끝나는 표기)로 조사를 확정한다."""
    if pair in _PAIR_FORMS:
        a, b = _PAIR_FORMS[pair]
        tail = prev_word.rstrip()[-1:]
        f = josa_mod.batchim(tail)
        if f is None:
            raise ValueError(f"받침을 알 수 없는 앞말: {prev_word!r} + {pair}")
        return a if f else b
    out = josa_mod.josa(prev_word, pair)
    if "(" in out:
        raise ValueError(f"받침을 알 수 없는 앞말: {prev_word!r} + {pair}")
    return out


@dataclass
class Encoded:
    parts: list = field(default_factory=list)  # ("bytes", b) | ("ctrl", token) | ("label",)
    runtime_josa: int = 0

    def byte_len(self, ctrl_len) -> int:
        n = 0
        for kind, *v in self.parts:
            if kind == "bytes":
                n += len(v[0])
            elif kind == "dict":
                n += len(v[1])
            elif kind == "ctrl":
                n += ctrl_len(v[0])
        return n


def encode(kr: str, rep_index: dict[str, int], dict_kr: dict[str, str] | None = None) -> Encoded:
    """번역문 → 조각. 사전 토큰은 바이트로(2B), 치환 토큰은 1B, 제어 토큰은 원본 항목을 그대로 쓰도록 표시만 한다.
    `dict_kr` = {"D3:08": "병사", …} — 사전 토큰 뒤 조사 확정에 쓴다."""
    out = Encoded()
    buf = bytearray()
    prev_word = ""  # 조사 판정용 — 직전 글자열 또는 사전 토큰의 표기
    prev_runtime = False

    def flush():
        if buf:
            out.parts.append(("bytes", bytes(buf)))
            buf.clear()

    for piece in TOKEN_RE.split(kr):
        if not piece:
            continue
        if piece == "<@>":
            flush()
            out.parts.append(("label",))
            continue
        if piece.startswith("<"):
            flush()
            out.parts.append(("ctrl", piece))
            continue
        if piece.startswith("{") and re.fullmatch(r"\{[0-9A-F]{2}(?::[0-9A-F]{2})?\}", piece):
            # 사전·치환 토큰은 **따로 낸다** — 분기 목표가 이 항목을 가리킬 수 있어 원문 오프셋을 이어받아야 한다
            flush()
            body = piece[1:-1]
            if ":" in body:  # 사전
                code, idx = body.split(":")
                out.parts.append(("dict", piece, bytes([int(code, 16), int(idx, 16)])))
                prev_word = (dict_kr or {}).get(body, "") or ""
                prev_runtime = not prev_word
            else:  # 런타임 치환
                out.parts.append(("dict", piece, bytes([int(body, 16)])))
                prev_word = ""
                prev_runtime = True
            continue
        if piece.startswith("{"):  # 조사 자리표시자
            pair = piece[1:-1]
            if prev_runtime or not prev_word:
                buf += bytes([JOSA_LEAD, JOSA_BASE + JOSA_PAIRS.index(pair)])
                out.runtime_josa += 1
            else:
                for ch in pick_josa(prev_word, pair):
                    buf += glyph_code(rep_index[ch])
            continue
        # 글자열
        prev_ch = ""
        for ch in piece:
            if is_glyph(ch):
                if ch not in rep_index:
                    raise ValueError(f"글리프 없음: {ch!r}")
                buf += glyph_code(rep_index[ch])
                prev_word += ch
                prev_runtime = False
            elif ch == " " and prev_ch in HALF_PUNCT:
                pass  # 부호 뒤 공백은 반각 — 부호 글리프가 칸 왼쪽에 붙어 남는 오른쪽이 곧 공백이다
            elif ch in KR_TABLE:
                buf.append(KR_TABLE[ch])
                if ch not in " \n":
                    prev_word = ""
            else:
                raise ValueError(f"매핑 없는 글자: {ch!r} (U+{ord(ch):04X})")
            prev_ch = ch
    flush()
    return out


def decode_kr(b: bytes, rep: list[str]) -> str:
    """검증용 역변환 — 2바이트 글리프·조사 코드·반각을 되돌린다(제어는 <XX>)."""
    inv = {v: k for k, v in KR_TABLE.items()}
    out = []
    i = 0
    while i < len(b):
        c = b[i]
        if c in LEADS and i + 1 < len(b):
            j = b[i + 1]
            if c == JOSA_LEAD and j >= JOSA_BASE:
                out.append("{" + JOSA_PAIRS[j - JOSA_BASE] + "}")
            else:
                out.append(rep[(LEADS.index(c) << 8) | j] or "\ufffd")
            i += 2
        elif c in inv:
            out.append(inv[c])
            i += 1
        else:
            out.append(f"<{c:02X}>")
            i += 1
    # 인코더가 뺀 「부호 뒤 공백」을 되살린다 — 뒤에 글자가 이어질 때만(줄 끝·닫는 괄호·제어 앞은 원래 없다)
    res = []
    for k, tok in enumerate(out):
        res.append(tok)
        nxt = out[k + 1] if k + 1 < len(out) else ""
        if (
            tok in HALF_PUNCT
            and nxt
            and nxt not in (" ", "\n", "」")
            and nxt not in HALF_PUNCT
            and not nxt.startswith("<")
        ):
            res.append(" ")
    return "".join(res)
