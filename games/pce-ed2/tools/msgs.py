"""시스템·전투 메시지 — 자리표(`13 nn` 이름 · `1A` 항목 이름 · `1B` 수)가 낀 문장을 정본 문장으로 바꾼다.

원문 문자열을 **일본어 틀**로 읽는다: 이름·항목 자리 → `{name}`, 수 자리 → `{n}`, 가나 모드·창 제어(`0C` `12` `11 nn` …)는 틀에서 빠진다.
틀을 정규화(NFKC · `｜` → `!!` · 공백·줄바꿈·끝 `。` 제거 · 맨 앞 `{name}` 선택)해 정본 `battle`/`system`/`ui` 열쇠와 맞댄다.
걸리면 정본 한국어(`{name}`·`{n}` 자리표 + 줄바꿈)를 **같은 순서의 원문 자리표 제어**로 되돌려 조립한다 — 앞뒤 제어는 원문 그대로.
자리표 개수·순서가 안 맞거나 정본에 없으면 None(원문 유지 — 관리자 후보). 한국어 조사는 정본의 `은(는)` 같은 정적 꼴이다(동적 조사는 P2 훅).
"""

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import jptext
import systext

NAME_CTRL = {0x13, 0x1A}
NUM_CTRL = {0x1B}
_idx: dict[str, tuple[str, str, str]] | None = None


def norm(s: str) -> str:
    s = s.replace("｜", "!!")
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s　]", "", s)
    s = s.replace("、", "").replace(",", "")  # 읽점은 같은 문장으로 본다
    s = s.rstrip("。.")
    while s.endswith("!"):  # 끝의 「!!」 유무도 같은 문장(PS1 정본이 느낌표를 더했다)
        s = s[:-1]
    return canon_form(s)


# 같은 문장의 표기차(한자↔가나) — PS1 정본과 PCE 원문이 같은 말을 다르게 적은 것. 정규화 때 한 꼴로 모은다(번역표가 아니다).
ORTHO = [
    ("おぼえ", "覚え"),
    ("起こ", "起"),
    ("光り", "光"),
    ("素早さ", "すばやさ"),
    ("既に", "すでに"),
    ("起ら", "起"),
    ("包まれ", "包まれ"),
]


def canon_form(s: str) -> str:
    for a, b in ORTHO:
        s = s.replace(a, b)
    return s


def index() -> dict[str, tuple[str, str, str]]:
    global _idx
    if _idx is None:
        _idx = {}
        for cat in ("battle", "system", "ui"):
            for k, v in canon.table(cat, "ed2").items():
                _idx.setdefault(norm(k), (cat, k, v))
    return _idx


def split(raw: bytes):
    """원문 → (앞 제어 바이트, 내용 토큰, 뒤 제어 바이트). 내용 = 글리프·여백·이름/수 자리표(첫 내용부터 마지막 내용까지)."""
    toks = systext.tokens(raw)

    def is_content(t):
        k, b = t
        return k != "ctrl" or b[0] in NAME_CTRL | NUM_CTRL

    ids = [i for i, t in enumerate(toks) if is_content(t) and t[0] != "pad"]
    if not ids:
        return None
    first, last = ids[0], ids[-1]
    lead = b"".join(b for _k, b in toks[:first])
    trail = b"".join(b for _k, b in toks[last + 1 :])
    return lead, toks[first : last + 1], trail


def template(content) -> tuple[str, list[bytes], list[bytes]]:
    """내용 토큰 → (틀 문자열, 이름 자리표 제어 목록, 수 자리표 제어 목록)."""
    s = ""
    names: list[bytes] = []
    nums: list[bytes] = []
    kata = False
    for k, b in content:
        if k == "ctrl":
            c = b[0]
            if c in NAME_CTRL:
                s += "{name}"
                names.append(b)
            elif c in NUM_CTRL:
                s += "{n}"
                nums.append(b)
            elif c == 0x0E:
                kata = True
            elif c == 0x0F:
                kata = False
            elif c == 0x0D:
                s += "\n"
        elif k == "glyph":
            s += jptext.decode((b"\x0e" if kata else b"") + b).replace("{0E}", "")
        elif k == "pad":
            s += "　"
        else:
            s += " "
    return s, names, nums


def translate(raw: bytes, tab) -> bytes | None:
    sp = split(raw)
    if sp is None:
        return None
    lead, content, trail = sp
    tmpl, names, nums = template(content)
    if not re.search(r"[぀-ヿ一-鿿]", tmpl):
        return None
    key = norm(tmpl)
    hit = index().get(key)
    prefix_name = b""
    if hit is None and key.startswith("{name}") and names:
        hit = index().get(
            key[len("{name}") :]
        )  # 정본 열쇠가 이름 자리표 없이 시작한다 → 원문 맨 앞 이름 자리를 한국어 앞에 그대로 둔다
        if hit is not None:
            prefix_name = names[0]
            names = names[1:]
    if hit is None:
        return None
    kr = hit[2]
    n_name, n_num = kr.count("{name}"), kr.count("{n}")
    if n_name != len(names) or n_num != len(nums):
        return None
    out = bytearray(lead) + prefix_name
    ni = ki = 0
    for piece in re.split(r"(\{name\}|\{n\})", kr):
        if piece == "{name}":
            out += names[ni]
            ni += 1
        elif piece == "{n}":
            out += nums[ki]
            ki += 1
        elif piece:
            out += tab.enc(piece, space=systext.SPACE)
    out += trail
    return bytes(out)
