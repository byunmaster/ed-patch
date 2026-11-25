"""章間(장 사이) 데모 — 장 시작 패키지 45·48·51·54·57 의 평문 스크립트 번역과 자체 글리프 후킹(마스터 10-24 「章間 1~5 번역 진행해」).

장 시작 패키지(`$26E2` 챕터 변수 = 1~5 를 세운다 — 디버그 마을 「章間」 항목 · 정규 장 전환)는 **본 프로그램을 통째로 갈아 끼우는 A형 패키지**라 뱅크 0x68~ 의 우리 글리프 풀·후킹이 없다.
엔딩(`ending.py`)과 같은 길 — 패키지 안에 자체 후킹을 둔다. 다섯 패키지는 **코드 배치가 같다**(실측: `JSR $E060` 오프셋 0x161C·0x1C36, 스크립트 포인터 `BIT` 오프셋 0x22F9(54 만 0x22FE)):

  · 스크립트: **메시지마다** 장면 코드가 `JSR $56F5; BIT <포인터>`(인라인 포인터, 논리 `$4000 + 패키지 오프셋`)로 부른다 — 메시지는 서로 독립이고 `00` 으로 끝난다.
    그래서 새 메시지는 아무 빈 칸에 놓고 **그 호출의 `BIT` 피연산자를 하나하나** 새 주소로 바꾼다(처음엔 첫 메시지 하나만 바꿔 둘째부터 쓰레기를 읽었다).
  · 해석기(`$575A`): 바이트 ≥ 0x20 이면 **무조건 두 바이트**(`$F9`=리드 · `$F8`=트레일)를 읽어 BIOS 글꼴(`$5C36` 의 `JSR $E060`)로 그린다 — 한 글자 = 12px 한 칸, ASCII 한 바이트 글자는 없다.
    제어(< 0x20): `01` 줄바꿈 · `0C nn` nn 프레임 대기(음성 맞춤) · `15 pp` 얼굴 그림 · `17 이름 18` 화자 이름창 · `00` 메시지 끝.
  · 한글은 리드 `F0..` 두 바이트 코드 + 패키지 안 자체 글리프 표(24B, 후킹이 `($FA)` 로 복사). 공백은 원문과 같은 전각 공백 `81 40`(BIOS).

문안은 `data/kanma_ko.tsv`(키 `패키지:오프셋` · 화자 · 본문 표기) — 표기: `/`=`01` · `{wNN}`=`0C NN`(16진) · `{fNN}`=`15 NN` · 그 밖은 글자.
화자·고유명사는 정본(`shared/canon`)에서 읽는다(여기엔 JP→KR 표를 두지 않는다 — 화자 칸의 한글은 정본 값을 문안 파일이 적는다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import common
import font

PKGS = {  # 패키지 번호 → (스크립트 시작, 끝(마지막 메시지의 `00` 다음), 포인터 `BIT` 피연산자 오프셋)
    45: (0x273A, 0x2AF9, 0x22F9),
    48: (0x260E, 0x28C2, 0x22F9),
    51: (0x2636, 0x2C9F, 0x22F9),
    54: (0x26FB, 0x2A84, 0x22FE),
    57: (0x2EF9, 0x438F, 0x22F9),
}
BASE = 0x4000  # 패키지 오프셋 → 논리 주소(5개 뱅크가 `$4000~$DFFF` 에 이어 붙는다)
WINDOW_END = 0xA000  # 논리 창 끝(오프셋)
DIRECT_END = 0x6000  # 이 아래(뱅크 0~2)만 그냥 읽어도 된다(장1~4 실측) — 그 위는 뱅크를 걸어 읽는다
MAPPED_FROM = 0x8000  # 창 끝 뱅크(MPR6 `$C000`)
SEAM_OFF = 0x1C37  # `JSR $E060`(문자 그리기, 오프셋 0x1C36)의 피연산자
SEAM_OLD = bytes([0x60, 0xE0])
BIOS_GETFNT = 0xE060
LEAD, TRAIL0, PER_LEAD = font.LEAD0, font.TRAIL0, font.PER_LEAD
GLYPH_B = font.PACKED_BYTES  # 표 한 글리프 16B(11×11 묶음)
GBUF_LEN = 16  # 후킹 뒤에 붙는 작업칸
SPACE = bytes([0x81, 0x40])  # 전각 공백(BIOS 가 그린다)
DATA = common.GAME_DIR / "data" / "kanma_ko.tsv"

W_RE = re.compile(r"\{w([0-9a-fA-F]{2})\}")
F_RE = re.compile(r"\{f([0-9a-fA-F]{2})\}")


def pkg_rel(n: int) -> int:
    return 258 + 128 * n


def jp_notation(raw: bytes) -> str:
    """원문 바이트 → 표기(읽기용 — 번역 틀)."""
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if b == 0x01:
            out.append("/")
            i += 1
        elif b == 0x0C:
            out.append(f"{{w{raw[i + 1]:02x}}}")
            i += 2
        elif b == 0x15:
            out.append(f"{{f{raw[i + 1]:02x}}}")
            i += 2
        elif b >= 0x20:
            out.append(raw[i : i + 2].decode("cp932", "replace"))
            i += 2
        else:
            out.append(f"{{{b:02x}}}")
            i += 1
    return "".join(out)


def split_message(m: bytes) -> tuple[bytes, bytes | None, bytes]:
    """메시지 → (이름 앞 제어, 이름 바이트 | None, 나머지(이름 뒤 `01` 부터 — 이름 없으면 전체))."""
    mm = re.match(rb"((?:\x15.)*)\x17", m, re.DOTALL)
    if not mm:
        return b"", None, m
    q = m.index(b"\x18", mm.end())
    return mm.group(1), m[mm.end() : q], m[q + 1 :]


EXTRA = {
    54: (0x2356,)
}  # 스크립트 구간 밖(코드 사이)에 박힌 메시지 — 「…을 돌려드렸습니다」(바바라에게 용의 눈물을 돌려주는 알림)


def messages(pkg: bytes, n: int) -> list[tuple[int, bytes]]:
    """(오프셋, 메시지 바이트 — `00` 제외). 끝의 빈 메시지는 뺀다. 스크립트 구간 밖 메시지(`EXTRA`)는 뒤에 붙인다."""
    s, e, _bit = PKGS[n]
    out, off = [], s
    for m in pkg[s:e].split(b"\x00")[:-1]:
        out.append((off, m))
        off += len(m) + 1
    for o in EXTRA.get(n, ()):
        out.append((o, pkg[o : pkg.index(b"\x00", o)]))
    return out


def load_ko() -> dict[str, tuple[str, str]]:
    ko = {}
    if DATA.exists():
        for ln in DATA.read_text(encoding="utf-8").splitlines():
            if not ln.strip() or ln.startswith("#"):
                continue
            k, name, text = (ln.split("\t") + ["", ""])[:3]
            ko[k] = (name, text)
    return ko


class Glyphs:
    """패키지가 쓰는 한글 글자 → 글리프 번호(첫 등장 순)."""

    def __init__(self):
        self.idx: dict[str, int] = {}

    def code(self, ch: str) -> bytes:
        if ch not in self.idx:
            self.idx[ch] = len(self.idx)
        k = self.idx[ch]
        return bytes([LEAD + k // PER_LEAD, TRAIL0 + k % PER_LEAD])

    def chars(self) -> list[str]:
        return sorted(self.idx, key=self.idx.get)


DIGRAPHS = (
    "!!",
    "!?",
    "?!",
    "??",
)  # 한 칸(12px)에 두 부호 — 한 글자 한 칸 엔진이라 `! !` 로 벌어지는 걸 막는다
NOSPACE_AFTER = ".,!?"  # 이 부호 바로 뒤 공백은 만들지 않는다 — 부호 칸(12px, 점이 왼쪽)이 이미 다음 글자와 틈을 낸다


def tokenize(text: str) -> list[tuple]:
    """표기 → 토큰: ("nl",) · ("w", nn) · ("f", nn) · ("raw", nn) · ("sp",) · ("g", 글자 또는 겹부호)."""
    out: list[tuple] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "/":
            out.append(("nl",))
            i += 1
        elif c == "{":
            mw, mf = W_RE.match(text, i), F_RE.match(text, i)
            if mw:
                out.append(("w", int(mw.group(1), 16)))
                i = mw.end()
            elif mf:
                out.append(("f", int(mf.group(1), 16)))
                i = mf.end()
            elif re.match(
                r"\{[0-9a-fA-F]{2}\}", text[i:]
            ):  # 그 밖의 제어 바이트(예: `{02}`)는 원문 그대로
                out.append(("raw", int(text[i + 1 : i + 3], 16)))
                i += 4
            else:
                raise ValueError(f"알 수 없는 표기: {text[i : i + 8]!r}")
        elif c == " ":
            prev = out[-1] if out else None
            if prev and prev[0] == "g" and prev[1][-1] in NOSPACE_AFTER:
                i += 1  # 부호 뒤 공백은 부호 칸이 맡는다
            else:
                out.append(("sp",))
                i += 1
        elif c.isdigit() and text[i + 1 : i + 2] == "～" and text[i + 2 : i + 3].isdigit():
            out.append(
                ("g", c + "～")
            )  # 「5～6」 — 숫자+물결을 한 칸에, 뒤 숫자는 물결에 붙여 둘째 칸에
            out.append(("g", "^" + text[i + 2]))
            i += 3
        elif text[i : i + 2] in DIGRAPHS or (c.isdigit() and text[i + 1 : i + 2].isdigit()):
            out.append(("g", text[i : i + 2]))  # 겹부호 · 두 자리 숫자 — 한 칸에 둘
            i += 2
        else:
            out.append(("g", c))
            i += 1
    return out


def encode_text(text: str, g: "Glyphs") -> bytes:
    out = bytearray()
    for t in tokenize(text):
        if t[0] == "nl":
            out.append(0x01)
        elif t[0] == "w":
            out += bytes([0x0C, t[1]])
        elif t[0] == "f":
            out += bytes([0x15, t[1]])
        elif t[0] == "raw":
            out.append(t[1])
        elif t[0] == "sp":
            out += bytes([HALF_CODE])  # 반각 공백(4px) — 해석기 개조(`half_space_code`)
        else:
            out += g.code(t[1])
    return bytes(out)


# 좁은 숫자(5×11) — 글꼴의 숫자는 7px 라 한 칸(12px)에 둘이 안 들어가 「2 0억」처럼 벌어진다. 두 자리는 한 칸에 5+1+5, 낱자는 오른쪽(열 6~10 — 뒤의 단위 글자에 붙어 「2세」로 읽힌다).
DIGIT5 = {
    "0": ".###. #...# #...# #...# #...# #...# #...# #...# #...# #...# .###.",
    "1": "..#.. .##.. #.#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. ..#.. #####",
    "2": ".###. #...# ....# ....# ...#. ..#.. .#... #.... #.... #.... #####",
    "3": ".###. #...# ....# ....# ..##. ....# ....# ....# ....# #...# .###.",
    "4": "...#. ..##. ..##. .#.#. .#.#. #..#. #..#. ##### ...#. ...#. ...#.",
    "5": "##### #.... #.... #.... ####. ....# ....# ....# ....# #...# .###.",
    "6": ".###. #...# #.... #.... ####. #...# #...# #...# #...# #...# .###.",
    "7": "##### ....# ....# ...#. ...#. ..#.. ..#.. .#... .#... .#... .#...",
    "8": ".###. #...# #...# #...# .###. #...# #...# #...# #...# #...# .###.",
    "9": ".###. #...# #...# #...# #...# .#### ....# ....# ....# #...# .###.",
}

TILDE5 = (".#...", "#.#.#", "...#.")  # 좁은 물결(5×3) — 「5～6」 한 칸용


def _digit_rows(d: str, left: int) -> list[int]:
    """숫자 하나 → 12행(16비트 행 값, 열 0 = 비트 15) — `left` 열에서 시작."""
    rows = []
    for r in DIGIT5[d].split():
        v = sum(1 << (15 - left - c) for c, ch in enumerate(r) if ch == "#")
        rows.append(v)
    return rows + [0]


def glyph_of(tok: str) -> bytes:
    """토큰 → 24B 글리프. 겹부호는 앞 글자 잉크 폭 + 1칸 뒤에 둘째를 겹쳐 그린다. 숫자는 좁은 숫자(`DIGIT5`)."""
    if len(tok) == 2 and tok[1] == "～" and tok[0].isdigit():  # 숫자(열 0~4) + 좁은 물결(열 6~10)
        wave = [0] * 12
        for r, row in zip((5, 6, 7), TILDE5, strict=True):
            wave[r] = sum(1 << (15 - 6 - c) for c, ch in enumerate(row) if ch == "#")
        rows = [a | b for a, b in zip(_digit_rows(tok[0], 0), wave, strict=True)]
        return b"".join(v.to_bytes(2, "big") for v in rows)
    if len(tok) == 2 and tok[0] == "^" and tok[1].isdigit():  # 물결 뒤 숫자 — 물결에 가깝게(열 2~6)
        return b"".join(v.to_bytes(2, "big") for v in _digit_rows(tok[1], 2))
    if tok.isdigit() and len(tok) <= 2:
        rows = (
            _digit_rows(tok, 6)
            if len(tok) == 1
            else [
                a | b for a, b in zip(_digit_rows(tok[0], 0), _digit_rows(tok[1], 6), strict=True)
            ]
        )
        return b"".join(v.to_bytes(2, "big") for v in rows)
    if len(tok) == 1:
        return font.glyph(tok)
    a, b = font.glyph(tok[0]), font.glyph(tok[1])
    rows_a = [int.from_bytes(a[2 * r : 2 * r + 2], "big") for r in range(12)]
    rows_b = [int.from_bytes(b[2 * r : 2 * r + 2], "big") for r in range(12)]
    right = 0  # 앞 글자 잉크의 오른쪽 끝 열(0 = 맨 왼쪽)
    for v in rows_a:
        v12 = v >> 4
        if v12:
            right = max(right, 11 - ((v12 & -v12).bit_length() - 1))
    right_b = 0
    for v in rows_b:
        v12 = v >> 4
        if v12:
            right_b = max(right_b, 11 - ((v12 & -v12).bit_length() - 1))
    shift = min(
        right + 2, 10 - right_b
    )  # 앞 글자와 한 열 비운다(둘째가 열 10 을 넘으면 붙인다 — 11×11 묶음)
    assert shift >= right + 1, f"겹부호 {tok!r} 이 한 칸에 안 들어간다"
    out = bytearray()
    for ra, rb in zip(rows_a, rows_b, strict=True):
        v = ra | (rb >> shift)
        out += v.to_bytes(2, "big")
    return bytes(out)


def build_script(pkg: bytes, n: int, ko: dict, g: Glyphs) -> tuple[list[bytes], list[str]]:
    """새 메시지 바이트 목록(원래 순서, 각 `00` 끝) + 번역 못 한 메시지 키 목록(그 메시지는 원문 그대로)."""
    out = []
    missing = []
    for off, m in messages(pkg, n):
        key = f"{n}:{off:#x}"
        if key not in ko:
            out.append(m + b"\x00")
            missing.append(key)
            continue
        name_ko, text = ko[key]
        pre, name, _rest = split_message(m)
        b = bytearray(pre)
        if name is not None:
            b += b"\x17" + encode_text(name_ko, g) + b"\x18"
        b += encode_text(text, g) + b"\x00"
        out.append(bytes(b))
    return out, missing


def msg_refs(pkg: bytes) -> dict[int, list[int]]:
    """메시지 시작(오프셋) → 그 메시지를 부르는 `JSR $56F5; BIT <포인터>` 의 피연산자 오프셋들."""
    refs: dict[int, list[int]] = {}
    for m in re.finditer(rb"\x20\xf5\x56\x2c(..)", pkg[:WINDOW_END], re.DOTALL):
        refs.setdefault(int.from_bytes(m.group(1), "little") - BASE, []).append(m.start() + 4)
    return refs


HALF_CODE = 0x1F  # 반각 공백 제어 — 해석기 표(`$57DF`)의 빈 칸(0x19~0x1F 은 `$581F` 무동작)에 우리 루틴을 건다
HALF_TABLE_OFF = 0x17DF + 2 * HALF_CODE  # 패키지 오프셋(논리 `$57DF` + 2×코드)
HALF_TABLE_OLD = bytes([0x1F, 0x58])  # `$581F`


def half_space_code(org: int) -> bytes:
    """반각 공백(4px 전진) 루틴 — 글자 12px = 타일 1.5칸이라 해석기는 위상 `$33E6`(0 = 타일 경계 · 1 = 타일 안 4px)을 번갈며 그린다. 4px 전진도 위상만 뒤집고 타일 수만 다르다.
    위상 1 → 0: 패턴 포인터 `$76/$77` += 0x20(위·아래 타일 한 쌍 — 줄바꿈 `$58F1~$58F3` 과 같은 처리)·BAT 포인터 `$74` 는 그대로 · 위상 0 → 1: 빈 칸(`81 40`)을 보통 경로(`$5BA1`)로 한 번 그려
    위상 1 로 만든 뒤 `$74` −1 · `$76/$77` −0x20(밑으로 감으면 +0xEB0)·열 수 `$33E7` −1 로 되감는다 — 다음 글자는 앞 칸을 빈 칸과 합쳐(`$5C83`) 4px 안쪽에서 시작한다. X·Y 를 지킨다."""
    a = asm.Asm(org)
    a.op("PHX")
    a.op("PHY")
    a.op("LDA", "abs", 0x33E6)
    a.op("BNE", "rel", "s1")
    a.op("LDA", "imm", 0x81)
    a.op("STA", "zp", 0xF9)
    a.op("LDA", "imm", 0x40)
    a.op("STA", "zp", 0xF8)
    a.op("JSR", "abs", 0x5BA1)
    a.op("DEC", "abs", 0x33E7)
    a.op("LDA", "zp", 0x74)
    a.op("BNE", "rel", "n74")
    a.op("DEC", "zp", 0x75)
    a.label("n74")
    a.op("DEC", "zp", 0x74)
    a.op("SEC")
    a.op("LDA", "zp", 0x76)
    a.op("SBC", "imm", 0x20)
    a.op("STA", "zp", 0x76)
    a.op("LDA", "zp", 0x77)
    a.op("SBC", "imm", 0x00)
    a.op("STA", "zp", 0x77)
    a.op("CMP", "imm", 0x70)
    a.op("BCS", "rel", "done")
    a.op("CLC")
    a.op("LDA", "zp", 0x76)
    a.op("ADC", "imm", 0xB0)
    a.op("STA", "zp", 0x76)
    a.op("LDA", "zp", 0x77)
    a.op("ADC", "imm", 0x0E)
    a.op("STA", "zp", 0x77)
    a.op("BRA", "rel", "done")
    a.label("s1")
    a.op("LDA", "imm", 0x20)
    a.op("JSR", "abs", 0x5D21)
    a.op("STZ", "abs", 0x33E6)
    a.label("done")
    a.op("PLY")
    a.op("PLX")
    a.op("RTS")
    return a.bytes()


def hook_code(org: int, a_addr: int, n_a: int, b_adj: int, gbuf: int, b_bank: int = 0) -> bytes:
    """리드 F0~F8 → 글리프 번호 k = (리드−F0)×220 + (트레일−0x24). 16B 묶음(`font.pack`, 11×11) 표에서 꺼내 24B 로 풀어 `($FA)` 에 쓴다.
    k < n_a 는 `a_addr` 표(창 안 — 그냥 읽는다), 이상은 `b_adj`(= 둘째 표 주소 − 16×n_a) 를 더하고 **MPR6(`$C000`)에 물리 뱅크 `b_bank` 를 잠깐 걸어**(SEI) 읽는다 —
    패키지 창 끝 0 칸(`$CF30~`)은 그냥 읽으면 깨진다(실측: 장2 에 시험으로 놓으니 글자가 쓰레기) — 장면이 MPR6 을 딴 뱅크로 돌려 쓰기 때문이다. `gbuf` = 16B 작업칸(패키지 안 RAM).
    X·Y 를 지킨다(호출한 그리기 루틴이 쓴다) — 스크래치는 `$EC~$ED` 와 스택 · 풀기는 `hook.py` 정적 풀과 같은 꼴."""
    t16 = 16 * n_a
    a = asm.Asm(org)
    a.op("LDA", "zp", 0xF9)
    a.op("SEC")
    a.op("SBC", "imm", LEAD)
    a.op("CMP", "imm", font.MAX_LEADS)
    a.op("BCC", "rel", "go")
    a.op("JMP", "abs", BIOS_GETFNT)  # 우리 글자가 아니다 → BIOS
    a.label("go")
    a.op("PHX")
    a.op("PHY")
    a.op("TAX")  # X = 리드 − F0
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", TRAIL0)
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)  # (EC,ED) = 트레일 편이
    a.label("addk")
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "idx")
    a.op("DEX")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", PER_LEAD)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "addk")
    a.op("INC", "zp", 0xED)
    a.op("BRA", "rel", "addk")
    a.label("idx")  # (EC,ED) = k → 16k
    for _ in range(4):
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)
    a.op("LDA", "zp", 0xED)
    a.op("CMP", "imm", t16 >> 8)
    a.op("BCC", "rel", "lo")
    a.op("BNE", "rel", "hi")
    a.op("LDA", "zp", 0xEC)
    a.op("CMP", "imm", t16 & 0xFF)
    a.op("BCS", "rel", "hi")
    a.label("lo")
    a.op("LDX", "imm", 0)
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", a_addr & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", (a_addr >> 8) & 0xFF)
    a.op("STA", "zp", 0xED)
    a.op("BRA", "rel", "cpy")
    a.label("hi")
    a.op("LDX", "imm", 1)
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", b_adj & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", (b_adj >> 8) & 0xFF)
    a.op("STA", "zp", 0xED)
    a.label("cpy")  # 16B 를 작업칸으로(X=1 이면 MPR6 에 뱅크를 걸고)
    a.op("CPX", "imm", 0)
    a.op("BEQ", "rel", "dir")
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", 6)
    a.op("PHA")
    a.op("LDA", "imm", b_bank)
    a.op("TAM", "tam", 6)
    a.op("LDY", "imm", 15)
    a.label("cpm")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absy", gbuf)
    a.op("DEY")
    a.op("BPL", "rel", "cpm")
    a.op("PLA")
    a.op("TAM", "tam", 6)
    a.op("PLP")
    a.op("BRA", "rel", "un")
    a.label("dir")
    a.op("LDY", "imm", 15)
    a.label("cp")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "absy", gbuf)
    a.op("DEY")
    a.op("BPL", "rel", "cp")
    a.label("un")
    a.op("LDX", "imm", 0)
    a.op("LDY", "imm", 0)
    a.label("hh")  # 앞 11B = 행 0~10 의 위 8비트 → 출력 짝수 바이트
    a.op("LDA", "absx", gbuf)
    a.op("STA", "izpy", 0xFA)
    a.op("INX")
    a.op("INY")
    a.op("INY")
    a.op("CPX", "imm", 11)
    a.op("BCC", "rel", "hh")
    a.op("LDY", "imm", 15)
    a.label("pu")  # 뒤 5B 를 스택에 S4..S0 순으로 — 40비트 레지스터
    a.op("LDA", "absy", gbuf)
    a.op("PHA")
    a.op("DEY")
    a.op("CPY", "imm", 11)
    a.op("BCS", "rel", "pu")
    a.op("TSX")  # S0 = $2101,X … S4 = $2105,X
    a.op("LDY", "imm", 1)
    a.label("row")  # 행마다 위 3비트 → 출력 홀수 바이트(비트 7~5), 레지스터를 3비트 왼쪽으로
    a.op("LDA", "absx", 0x2101)
    a.op("AND", "imm", 0xE0)
    a.op("STA", "izpy", 0xFA)
    for _ in range(3):
        a.op("ASL", "absx", 0x2105)
        a.op("ROL", "absx", 0x2104)
        a.op("ROL", "absx", 0x2103)
        a.op("ROL", "absx", 0x2102)
        a.op("ROL", "absx", 0x2101)
    a.op("INY")
    a.op("INY")
    a.op("CPY", "imm", 23)
    a.op("BCC", "rel", "row")
    a.op("CLA")
    a.op("LDY", "imm", 22)
    a.op("STA", "izpy", 0xFA)  # 행 11 은 비어 있다
    a.op("INY")
    a.op("STA", "izpy", 0xFA)
    for _ in range(5):
        a.op("PLA")  # 스택의 40비트 레지스터 버리기
    a.op("PLY")
    a.op("PLX")
    a.op("RTS")
    return a.bytes()


def free_regions(pkg: bytes, n: int) -> list[tuple[int, int]]:
    """새 자료를 둘 수 있는 칸 (오프셋, 길이) — 옛 스크립트 자리 · 창 안 0xFF 런(200B↑)."""
    s, e, _ = PKGS[n]
    assert set(pkg[e : e + 18]) == {0}, "스크립트 뒤 0 채움이 다르다"
    regs = [(s, e + 18 - s)]
    for m in re.finditer(b"\xff{200,}", pkg[:DIRECT_END]):
        regs.append((m.start(), min(m.end(), DIRECT_END) - m.start()))
    return regs


def mapped_regions(pkg: bytes, n: int) -> list[tuple[int, int]]:
    """MPR6 뱅크 한 칸 안의 큰 0 칸(실행 중 안 쓰인다 — 장5 12,000프레임 RAM 비교) — 글리프 표 뒷부분을 여기 둔다."""
    out = []
    for m in re.finditer(b"\x00{1000,}", pkg[MAPPED_FROM:WINDOW_END]):
        out.append((MAPPED_FROM + m.start(), m.end() - m.start()))
    return out


def plan(pkg: bytes, n: int) -> dict:
    """한 패키지의 새 바이트 배치 — {쓰기 목록, 통계}. 번역 안 한 메시지는 원문 그대로 새 자리에 옮긴다."""
    _s, _e, _bit = PKGS[n]
    ko = {k: v for k, v in load_ko().items() if k.startswith(f"{n}:")}
    g = Glyphs()
    msgs, missing = build_script(pkg, n, ko, g)
    script = b"".join(msgs)
    chars = g.chars()
    table = b"".join(font.pack(glyph_of(c)) for c in chars)
    regs = sorted(free_regions(pkg, n), key=lambda r: r[0])
    hook_len = len(hook_code(0, 0, 0, 0, 0, 0)) + GBUF_LEN
    placed = []

    def take(size: int, why: str, prefer_big=False):
        cand = sorted(regs, key=lambda r: -r[1]) if prefer_big else regs
        for a, l in cand:
            if l >= size:
                regs.remove((a, l))
                if l > size:
                    regs.append((a + size, l - size))
                regs.sort()
                placed.append((a, size, why))
                return a
        raise ValueError(f"{n}: 자리가 모자란다 — {why} {size}B (남은 칸 {sorted(regs)})")

    s_off = take(len(script), "스크립트")
    h_off = take(hook_len, "후킹")
    half = half_space_code(0)
    sp_off = take(len(half), "반각 공백 루틴")
    gbuf = BASE + h_off + hook_len - GBUF_LEN
    total = len(table)
    big = max((l for _a, l in regs), default=0)
    b_bank = 0
    if total <= big:
        a_off = take(total, "글리프 표") if total else 0
        n_a, b_off = len(chars), 0
    else:
        n_a = big // GLYPH_B
        a_off = take(n_a * GLYPH_B, "글리프 표 앞", prefer_big=True) if n_a else 0
        rest = total - n_a * GLYPH_B
        mr = [r for r in mapped_regions(pkg, n) if r[1] >= rest]
        if not mr:
            raise ValueError(
                f"{n}: 자리가 모자란다 — 글리프 표 뒤 {rest}B (창 안 남은 칸 {sorted(regs)})"
            )
        b_off = mr[0][0]
        b_bank = 0x68 + (b_off >> 13)
        assert (b_off + rest - 1) >> 13 == b_off >> 13, "뒤 표가 뱅크 하나를 넘는다"
        placed.append((b_off, rest, "글리프 표 뒤(뱅크 걸어 읽기)"))
    hook = hook_code(
        BASE + h_off,
        BASE + a_off,
        n_a,
        (BASE + b_off - GLYPH_B * n_a) & 0xFFFF if b_off else 0,
        gbuf,
        b_bank,
    ) + bytes(GBUF_LEN)
    assert len(hook) == hook_len
    spans = [(s_off, script, "스크립트"), (h_off, hook, "후킹"), (sp_off, half_space_code(BASE + sp_off), "반각 공백 루틴"), (HALF_TABLE_OFF, (BASE + sp_off).to_bytes(2, "little"), "해석기 표 반각 공백")]
    if total:
        spans.append((a_off, table[: n_a * GLYPH_B], "글리프 표 앞"))
        if b_off:
            spans.append((b_off, table[n_a * GLYPH_B :], "글리프 표 뒤"))
    # 옮긴 옛 메시지는 지운다 — 포인터가 새 자리를 가리켜 안 읽히는 일본어가 롬에 남아 게이트·눈에 걸리지 않게(새 자료가 덮은 칸은 빼고 0 채움)
    used = sorted((o, o + len(d)) for o, d, _l in spans)
    for off, m in messages(pkg, n):
        lo, hi = off, off + len(m) + 1
        for uo, ue in used:
            if ue <= lo or uo >= hi:
                continue
            if uo > lo:
                spans.append((lo, bytes(uo - lo), f"옛 메시지 지움 {off:#x}"))
            lo = max(lo, ue)
        if lo < hi:
            spans.append((lo, bytes(hi - lo), f"옛 메시지 지움 {off:#x}"))
    refs = msg_refs(pkg)
    new_start = s_off
    for (off, _m), nm in zip(messages(pkg, n), msgs, strict=True):
        assert off in refs, f"{n}: 메시지 {off:#x} 를 부르는 호출을 못 찾았다"
        for r in refs[off]:
            spans.append((r, (BASE + new_start).to_bytes(2, "little"), f"포인터 {off:#x}"))
        new_start += len(nm)
    spans.append((SEAM_OFF, (BASE + h_off).to_bytes(2, "little"), "EX_GETFNT 이음매"))
    return {
        "spans": spans,
        "refs": refs,
        "chars": len(chars),
        "script": len(script),
        "missing": missing,
        "placed": placed,
        "table": total,
    }


def writes(n: int, pkg: bytes):
    """[(선형 오프셋, 새 바이트, 기대 원본, 라벨)] — 새 자료가 놓일 칸(옛 스크립트·0xFF 런)은 원본 그대로를 기대한다."""
    p = plan(pkg, n)
    base = pkg_rel(n) * common.USER
    s, e, _bit = PKGS[n]
    out = []
    for off, data, label in p["spans"]:
        if label.startswith("옛 메시지 지움"):
            expect = pkg[off : off + len(data)]
        elif label.startswith("포인터 "):
            expect = (BASE + int(label.split()[1], 16)).to_bytes(2, "little")
        elif label == "EX_GETFNT 이음매":
            expect = SEAM_OLD
        elif label.startswith("해석기 표"):
            expect = HALF_TABLE_OLD
        else:
            expect = pkg[off : off + len(data)]
            if off + len(data) <= s or off >= e + 18:  # 0xFF·0x00 런 안
                assert len(set(expect)) == 1 and expect[0] in (0x00, 0xFF), (n, label, hex(off))
        out.append((base + off, data, expect, f"章間 {n} {label}"))
    # 새 스크립트가 옛 자리보다 짧으면 남는 옛 바이트는 그대로 둔다(포인터가 새 자리를 가리킨다)
    return out, p


def apply(w) -> dict:
    info = {}
    for n in PKGS:
        ko_has = any(k.startswith(f"{n}:") for k in load_ko())
        if not ko_has:
            continue
        pkg = common.track_data(pkg_rel(n), 128)
        spans, p = writes(n, pkg)
        for linear, new, expect, label in spans:
            w.put(linear, new, expect, label)
        if p["missing"]:  # 번역 안 한 메시지 = 화면에 일본어가 남는다 — 빌드를 멈춘다
            raise ValueError(f"章間 {n}: 미번역 메시지 {p['missing']}")
        info[n] = p
        print(
            f"  章間 {n}: 글자 {p['chars']} · 스크립트 {p['script']}B · 글리프 표 {p['table']}B · 미번역 {len(p['missing'])}"
        )
    return info


SPACE_PX, CELL_PX = 4, 12  # 반각 공백 4px(해석기 개조) · 글자 한 칸 12px
MAX_CELLS = 18  # 줄 한 칸 = 12px · 해석기 열 수 `$6E`=18(넘으면 자동 줄바꿈 — 원문 줄도 18칸 이내)
MAX_ROWS_NAMED, MAX_ROWS_PLAIN = 3, 4  # 이름창 있는 메시지는 본문 3줄, 없는 메시지는 4줄


def check_ko() -> list[str]:
    """번역 표기의 줄 폭(칸)·줄 수를 잰다 — 넘으면 문제 목록. px = 글자·겹부호 12 · 공백 4(제어 표기 제외, 부호 뒤 공백은 안 센다)."""
    errs = []
    for k, (name, text) in load_ko().items():
        rows: list[int] = [0]
        for t in tokenize(text):
            if t[0] == "nl":
                rows.append(0)
            elif t[0] == "sp":
                rows[-1] += SPACE_PX
            elif t[0] == "g":
                rows[-1] += CELL_PX
        if text.startswith("/"):
            rows = rows[1:]
        named = bool(name)
        if len(rows) > (MAX_ROWS_NAMED if named else MAX_ROWS_PLAIN):
            errs.append(f"{k}: 줄 수 {len(rows)}")
        for r, c in enumerate(rows):
            if c > MAX_CELLS * CELL_PX:
                errs.append(f"{k}: {r + 1}째 줄 {c}px (한도 {MAX_CELLS * CELL_PX})")
    return errs
