"""런타임 조사 — **변수(아이템 이름·숫자) 바로 뒤 조각 첫머리의 조사**를 훅이 고르게 하는 빌드 쪽 절반.

배경: 메시지 VM 은 대사 조각 사이에 `0x04`(아이템 이름)·`0x05`(숫자)·`0x07`(합계)를 끼워 한 줄로 잇는다.
변수 값은 게임 중에야 정해지니 그 뒤 조사(「…을(를) 건네받았다.」)는 **빌드 때 못 고른다**. 그래서
- 빌드 때: 변수 뒤(= 조각 첫머리)의 조사 병기를 **표지 글자**(사설 영역 `\\ue000`~)로 바꾼다.
- 런타임: 글자 그리기 훅(`engine_patch`)이 표지를 보면 **직전에 그려진 글자의 받침**으로 실제 조사 글리프를 갈아 끼운다.
- 그 밖의 병기(고정 문자열 뒤)는 **빌드 때** 앞 글자 받침으로 확정한다(`shared/text/josa`).

🔴 표지는 **조각 첫머리에서만** 쓴다 — 거기가 「변수 바로 뒤」다. 앞이 한글이 아니고 변수도 아닌 병기(라틴·숫자 꼬리)는
   그대로 병기로 남는다(잘못 고르는 것보다 병기가 안전하다 — 공용 josa 방침). 상주 검사: `check_josa.py`.
⚠ 「으로/로」: 표지 `(으)` + 「로」 — 받침이 있으면(ㄹ 제외) 「으」를 그리고, 아니면 **안 그리고 전진 0**.
"""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "shared")
)
from text import josa as _josa  # noqa: E402

# (표지 글자, 받침 있을 때 글자, 없을 때 글자(None = 안 그림), 플래그) — 플래그 bit0: 없으면 전진 0 · bit1: ㄹ 을 「없음」으로 본다
MARKERS = [
    ("", "은", "는", 0),
    ("", "이", "가", 0),
    ("", "을", "를", 0),
    ("", "과", "와", 0),
    ("", "으", None, 3),
]
MARKER_CHARS = {m[0] for m in MARKERS}
PAIR_MARKER = {"은/는": 0, "이/가": 1, "을/를": 2, "과/와": 3, "와/과": 3}
_PAIRS = {
    "은(는)": "은/는",
    "는(은)": "은/는",
    "이(가)": "이/가",
    "가(이)": "이/가",
    "을(를)": "을/를",
    "를(을)": "을/를",
    "과(와)": "과/와",
    "와(과)": "과/와",
}
_TOKEN = re.compile("|".join(re.escape(k) for k in sorted(_PAIRS, key=len, reverse=True)))
_EU_RO = re.compile(r"^(?:\(으\)로|으\(로\)|으로\(로\))")

# 숫자는 **읽는 소리**의 받침이다(1 일 · 2 이 · 3 삼 · 4 사 · 5 오 · 6 육 · 7 칠 · 8 팔 · 9 구 · 0 영/십/백/천/만) — 마스터 09-26.
DIGIT_BATCHIM = {"0": 1, "1": 2, "2": 0, "3": 1, "4": 0, "5": 0, "6": 1, "7": 2, "8": 2, "9": 0}  # 0 없음 · 1 받침 · 2 ㄹ


def klass(ch):
    """글자의 받침 부류 — 0 없음 · 1 받침 · 2 ㄹ 받침 · None 한글 아님(숫자는 읽는 소리)."""
    if ch in DIGIT_BATCHIM:
        return DIGIT_BATCHIM[ch]
    f = _josa.batchim(ch)
    if f is None:
        return None
    return 0 if f == 0 else (2 if f == 8 else 1)


def convert(kr):
    """번역 문안의 조사 병기를 확정/표지로 바꾼다.

    조각 **첫머리**의 병기·「(으)로」는 런타임 표지, 그 밖의 병기는 앞 글자 받침으로 지금 고른다(못 고르면 병기 그대로).
    """
    head, rest = "", kr
    m = _EU_RO.match(kr)
    if m:
        head, rest = MARKERS[4][0] + "로", kr[m.end() :]
    else:
        m = _TOKEN.match(kr)
        if m:
            head, rest = MARKERS[PAIR_MARKER[_PAIRS[m.group(0)]]][0], kr[m.end() :]
    out, last = [], 0
    for mo in _TOKEN.finditer(rest):
        out.append(rest[last : mo.start()])
        out.append(fix_in(head + rest, len(head) + mo.start(), mo.group(0)))
        last = mo.end()
    out.append(rest[last:])
    return head + "".join(out)


def fix_in(text, pos, tok):
    """text[pos:] 의 병기 `tok` 를 앞 글자로 확정한 조사(못 정하면 병기 그대로)."""
    before = text[:pos]
    pair = _PAIRS[tok]
    ch = before.rstrip()[-1:]
    if not ch or ch in MARKER_CHARS:
        return tok
    if ch in DIGIT_BATCHIM:  # 숫자는 읽는 소리
        a, b = _josa.PAIRS[pair]
        return a if DIGIT_BATCHIM[ch] else b
    j = _josa.josa(before, pair)
    return tok if "(" in j else j


def runtime_glyphs():
    """[글자] — 훅이 쓰는 글자: 조사 표지(굽지 않음) + 조사 글리프(굽는다)."""
    out = [m[0] for m in MARKERS]
    for _mk, w, wo, _fl in MARKERS:
        out += [c for c in (w, wo) if c and c not in out]
    return out


def baked_glyphs():
    """[글자] — 위 중 실제로 굽는 것(표지 제외)."""
    return [c for c in runtime_glyphs() if c not in MARKER_CHARS]


def runtime_chars(items):
    """런타임에 조사 앞에 올 수 있는 한글 끝 음절 — 아이템 이름의 마지막 글자들(받침 부류 있는 것만 표에 든다)."""
    out = {}
    for name in items:
        ch = name.rstrip()[-1:]
        k = klass(ch)
        if k:  # 받침 없음(0)은 기본값이라 표에 안 둔다
            out[ch] = k
    return out


def runtime(table, items, digit_codes):
    """훅에 줄 자료 {markers, blist} — 글리프 코드로. 표지·조사 글자가 배정표에 없으면 None(= 훅을 안 넣는다).

    `digit_codes`: {'0': 코드…} 숫자 글리프 코드(원본 전각 숫자 자리). 아이템 끝 음절이 배정표에 없으면 KeyError —
    조용히 빼면 그 아이템 뒤 조사가 틀린다(상주 게이트 `check_josa`).
    """
    if any(m[0] not in table for m in MARKERS):
        return None
    markers = []
    for mk, w, wo, flags in MARKERS:
        markers.append((table[mk], table[w], table[wo] if wo else table[" "], flags))
    blist = []
    for ch, k in sorted(runtime_chars(items).items()):
        if ch not in table:
            raise KeyError(f"조사 앞에 올 수 있는 글자 {ch!r} 가 글리프 배정표에 없다")
        blist.append(table[ch] | (0x8000 if k == 2 else 0))
    for d, k in DIGIT_BATCHIM.items():
        if k:
            blist.append(digit_codes[d] | (0x8000 if k == 2 else 0))
    return {"markers": markers, "blist": blist}
