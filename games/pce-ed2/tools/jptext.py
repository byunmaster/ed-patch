"""원문 대본 바이트 → 일본어 문자열(읽기용 뷰) — 정본 열쇠와 맞대고 문안을 읽기 위한 것이다.

인코딩(2026-10-12 실측 — 인터프리터 뱅크 0x71 `$672F`, 글자표 뱅크 0x71 `+0xA02`):
  · `$80~$9F` · `$E0~` = 리드 → SJIS 2바이트(한 칸)
  · `$A0~$DF` = 단일 바이트 가나(**한 칸**, 12px 글리프) — 히라가나 표(`A1 。` `A6 を` … `DF ゜`), `0E` 이후엔 가타카나, `0F` 로 복귀
  · `$20~$7F` = 단일 바이트 표(전각 ASCII · `$61~$79` 탁음 가나 `が…ぽ` · `$7A …`) — 단 `$60` 은 공백
  · `$00` 줄 끝 · `$0D` 줄바꿈 · 그 밖의 `<$20` 은 제어 — 인자 수는 `ARGS`(핸들러 디스어셈블로 확정)
제어는 `{xx}`(인자가 있으면 `{xx yy}`)로 적는다. 알 수 없는 바이트는 `{xx}`.
"""

import unicodedata

# 0x11 = 아숫자 둘(대기 시간) — 뒤 바이트의 상위 니블이 120/128 로 3(ASCII 숫자)이었다
ARGS = {0x02: 1, 0x03: 1, 0x10: 1, 0x11: 2, 0x15: 1, 0x18: 4, 0x1C: 1, 0x1D: 1, 0x1E: 1}
# 0x16(말머리·이름창)은 인자 4바이트가 곧 이름 글자다 — 글자로 읽히게 두고 `{16}` 만 적는다.

_VOICED = [
    "か",
    "き",
    "く",
    "け",
    "こ",
    "さ",
    "し",
    "す",
    "せ",
    "そ",
    "た",
    "ち",
    "つ",
    "て",
    "と",
    "は",
    "ひ",
    "ふ",
    "へ",
    "ほ",
]


def _hira_table() -> dict[int, str]:
    t: dict[int, str] = {0xA0: "　"}
    for i, cp in enumerate(range(0xFF61, 0xFFA0), start=0xA1):
        k = unicodedata.normalize("NFKC", chr(cp))
        if "ァ" <= k <= "ン":
            k = chr(ord(k) - 0x60)
        t[i] = {"ﾞ": "゛", "ﾟ": "゜"}.get(chr(cp), k)
    t[0xDE], t[0xDF] = "゛", "゜"
    return t


def _ascii_table() -> dict[int, str]:
    t = {}
    for b in range(0x20, 0x60):
        t[b] = "　" if b == 0x20 else {0x22: "”", 0x27: "’", 0x5C: "￥"}.get(b, chr(b + 0xFEE0))
    t[0x60] = "　"  # 게임이 앞서 공백으로 처리한다
    voiced = [unicodedata.normalize("NFC", c + "゙") for c in _VOICED]
    voiced += [unicodedata.normalize("NFC", c + "゚") for c in "はひふへほ"]
    for i, c in enumerate(voiced[:19]):  # が ぎ ぐ げ ご ざ じ ず ぜ ぞ だ ぢ づ で ど ば び ぶ べ
        t[0x61 + i] = c
    t[0x74], t[0x75], t[0x76], t[0x77], t[0x78], t[0x79] = "ぼ", "ぱ", "ぴ", "ぷ", "ぺ", "ぽ"
    t[0x7A], t[0x7B], t[0x7C], t[0x7D], t[0x7E] = "…", "｛", "｜", "｝", "～"
    return t


HIRA = _hira_table()
ASC = _ascii_table()


def _kata(ch: str) -> str:
    return chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ん" else ch


def decode(b: bytes) -> str:
    """바이트열 → 읽기용 일본어(제어는 `{..}`)."""
    out = []
    i = 0
    kana = False
    while i < len(b):
        a = b[i]
        if a < 0x20:
            if a == 0x0E:
                kana = True
                out.append("{0E}")
            elif a == 0x0F:
                kana = False
                out.append("{0F}")
            elif a == 0x0D:
                out.append("\n")
            elif a == 0x00:
                out.append("{00}")
            else:
                n = ARGS.get(a, 0)
                out.append("{" + " ".join(f"{x:02X}" for x in b[i : i + 1 + n]) + "}")
                i += n
            i += 1
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            try:
                out.append(b[i : i + 2].decode("cp932"))
            except UnicodeDecodeError:
                out.append("{" + b[i : i + 2].hex().upper() + "}")
            i += 2
        elif a >= 0xA0:
            ch = HIRA.get(a, f"{{{a:02X}}}")
            out.append(_kata(ch) if kana else ch)
            i += 1
        else:
            ch = ASC.get(a, f"{{{a:02X}}}")
            out.append(_kata(ch) if kana else ch)
            i += 1
    return "".join(out)
