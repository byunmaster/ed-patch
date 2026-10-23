"""시스템·전투 메시지 — 자리표(`13 nn` 이름 · `1A` 항목 이름 · `1B` 수)가 낀 문장을 정본 문장으로 바꾼다.

원문 문자열을 **일본어 틀**로 읽는다: 이름·항목 자리 → `{name}`, 수 자리 → `{n}`, 가나 모드·창 제어(`0C` `12` `11 nn` …)는 틀에서 빠진다.
틀을 정규화(NFKC · `｜` → `!!` · 공백·줄바꿈·끝 `。` 제거 · 맨 앞 `{name}` 선택)해 정본 `battle`/`system`/`ui` 열쇠와 맞댄다.
걸리면 정본 한국어(`{name}`·`{n}` 자리표 + 줄바꿈)를 **같은 순서의 원문 자리표 제어**로 되돌려 조립한다 — 앞뒤 제어는 원문 그대로.
자리표 개수·순서가 안 맞거나 정본에 없으면 None(원문 유지 — 관리자 후보). 한국어 조사는 정본의 `은(는)` 같은 정적 꼴이다(동적 조사는 P2 훅).
"""

import hashlib
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
    ("かまえ", "体制"),  # PCE 「守りのかまえをとった」 = PS1 「守りの体制をとった」(같은 전투 문구의 표기차)
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
        for k, v in systext._extra().items():  # 시험 빌드 전용 후보 주입(정본 확정 전 검증용 — `systext._extra` 가 test- 꼬리표일 때만 연다)
            if "@" not in k:
                _idx.setdefault(norm(k), ("battle", k, v))
    return _idx


def split(raw: bytes, name_ctrl=NAME_CTRL, num_ctrl=NUM_CTRL):
    """원문 → (앞 제어 바이트, 내용 토큰, 뒤 제어 바이트). 내용 = 글리프·여백·이름/수 자리표(첫 내용부터 마지막 내용까지)."""
    toks = systext.tokens(raw)

    def is_content(t):
        k, b = t
        return k != "ctrl" or b[0] in name_ctrl | num_ctrl

    ids = [i for i, t in enumerate(toks) if is_content(t) and t[0] != "pad"]
    if not ids:
        return None
    first, last = ids[0], ids[-1]
    # 끝의 전각 공백 글자(`20`)가 제어(`12` 대기 · `0D` 줄바꿈) **뒤에** 붙은 줄(「が助けにきた{12}↵　」)은 그 공백을 내용으로 세지 않는다 — 내용으로 세면 가운데 낀 `12 0D` 가 내용 토큰으로
    # 들어가 틀(「…」)로 바뀔 때 통째 버려졌다(10-22 구조 대조에서 발견: 다섯 패키지의 「{name}이(가) 도우러 왔다.」 가 끝 대기(`12`)를 잃었다). 뒤 제어로 둬 그대로 이어 붙인다.
    while last > first and toks[last] == ("glyph", b" ") and toks[last - 1][0] == "ctrl" and toks[last - 1][1][0] not in name_ctrl | num_ctrl:
        last = max(i for i in ids if i < last)
    lead = b"".join(b for _k, b in toks[:first])
    trail = b"".join(b for _k, b in toks[last + 1 :])
    return lead, toks[first : last + 1], trail


def template(content, name_ctrl=NAME_CTRL, num_ctrl=NUM_CTRL) -> tuple[str, list[bytes], list[bytes]]:
    """내용 토큰 → (틀 문자열, 이름 자리표 제어 목록, 수 자리표 제어 목록)."""
    s = ""
    names: list[bytes] = []
    nums: list[bytes] = []
    kata = False
    for k, b in content:
        if k == "ctrl":
            c = b[0]
            if c in name_ctrl:
                s += "{name}"
                names.append(b)
            elif c in num_ctrl:
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


BATTLE_JOSA = "none"  # 이 덩이의 이름 버퍼 받침 부류 — "none"(영문 끝/받침 없음) · "yes"(받침) · "dyn"(섞임 — 병기 그대로 두어 런타임 훅이 푼다). `battle.edit_chunk` 가 덩이마다 정한다.


def battle_josa(kr: str) -> str:
    """이름 버퍼는 **그 덩이의 이름 줄**이다 — 몬스터 이름 + 구별 문자(A~D)면 영문 끝 = 받침 없음(마스터 09-26), 구별 문자 없는 단독 몬스터(산산 · 파워앵글)는 이름 끝 글자의
    받침으로 푼다(qa 10-20 「산산가」 「파워앵글는」). 부류가 섞이면 병기를 그대로 둔다(런타임 훅). 이름 바로 뒤 병기 조사를 빌드 때 푼다."""
    if BATTLE_JOSA == "dyn":
        return kr
    for pair, no_batchim, batchim in (("은(는)", "는", "은"), ("이(가)", "가", "이"), ("을(를)", "를", "을"), ("과(와)", "와", "과")):
        if kr.startswith(pair):
            return (batchim if BATTLE_JOSA == "yes" else no_batchim) + kr[len(pair) :]
    return kr


_JOSA_HEAD = re.compile(r"^(은\(는\)|이\(가\)|을\(를\)|과\(와\)|와\(과\)|으로\(로\)|로\(으로\))")


def cover(piece: str) -> str | None:
    """정규화한 조각을 **정본 열쇠 둘 이상의 이어 붙임**으로 덮는다(「しかし」+「運良く」 …) — 가장 적게 쪼개는 덮개, 값은 공백으로 잇는다.
    열쇠가 `{` 자리표를 품은 것은 쓰지 않는다. 못 덮으면 None."""
    keys = {k: v[2] for k, v in index().items() if v[0] in ("battle", "system") and "{" not in v[2] and "{" not in k}
    n = len(piece)
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        if best[i] is None:
            continue
        for j in range(i + 1, n + 1):
            v = keys.get(piece[i:j])
            if v is not None and (best[j] is None or len(best[j]) > len(best[i]) + 1):
                best[j] = [*best[i], v]
    if best[n] is None or len(best[n]) < 2:
        return None
    out = best[n][0]
    for v in best[n][1:]:
        out += ("" if _JOSA_HEAD.match(v) else " ") + v  # 조사로 시작하는 조각(「은(는) 도망쳤다.」)은 앞 조각(「들」)에 붙인다 — 띄우면 「들 은」 이 된다(10-20 style 4909)
    return out


def segments(raw: bytes, tab, name_ctrl, num_ctrl) -> bytes | None:
    """문장 전체가 정본에 없을 때 — 이름·수 자리표로 **조각**을 나눠 조각마다 정본 조각(「は」 「を使った」 …)을 맞댄다.
    자리표 사이의 줄바꿈으로만 갈린 글(「には」⏎「当たらなかった」)은 **한 문장으로 이어** 맞추고, 한국어를 첫 어절 뒤에서 다시 나눈다.
    조각이 하나라도 없으면 None(원문 유지). 자리표·그 밖의 제어는 원문 그대로 둔다. 조사는 병기 꼴 그대로 낸다(`tab.enc` 가 앞 글자로 풀거나 훅 토큰으로)."""
    toks = systext.tokens(raw)
    if not any(k == "ctrl" and b[0] in name_ctrl | num_ctrl for k, b in toks):
        return None  # 자리표 없는 문장은 조각 맞춤을 안 한다(오탐 방지)
    out = bytearray()
    runs: list[list] = [[]]  # 0D 로 갈린 글 조각들(자리표·그 밖 제어에서 묶음이 끝난다)
    raws: list[list[bytes]] = [[]]
    pieces = 0

    def flush() -> bool:
        nonlocal pieces
        if not any(runs):
            runs[:] = [[]]
            raws[:] = [[]]
            return True
        flat = [t for r in runs for t in r]
        jp, _n, _m = template(flat, name_ctrl, num_ctrl)
        if not re.search(r"[぀-ヿ一-鿿]", jp):  # 가나·한자 없는 조각(여백만)은 그대로
            for i, r in enumerate(raws):
                out.extend(b"".join(r))
                if i < len(raws) - 1:
                    out.extend(b"\r")
            runs[:] = [[]]
            raws[:] = [[]]
            return True
        hit = index().get(norm(jp))
        if hit is not None and "{" not in hit[2]:
            kr = hit[2]
        else:
            kr = cover(norm(jp))
            if kr is None:
                return False
        n_runs = len([r for r in runs if r])
        if n_runs > 1 and " " in kr:  # 원문 줄 수만큼 어절 경계에서 나눈다
            parts = kr.split(" ", n_runs - 1)
            out.extend(b"\r".join(tab.enc(p, space=systext.SPACE) for p in parts))
        else:
            out.extend(tab.enc(kr, space=systext.SPACE))
        pieces += 1
        runs[:] = [[]]
        raws[:] = [[]]
        return True

    for k, b in toks:
        if k == "ctrl" and b[0] == 0x0D:
            runs.append([])
            raws.append([])
        elif k == "ctrl" and b[0] not in (0x0E, 0x0F):
            # 자리표·그 밖의 제어 — 묶음 끝. 묶음 뒤에 남은 줄바꿈은 flush 가 처리한다
            tail_nl = len(runs) > 1 and not runs[-1]
            if tail_nl:
                runs.pop()
                raws.pop()
            had_text = any(runs)
            if not flush():
                return None
            if tail_nl:
                out.extend(b"\r")
            elif had_text and b[0] in name_ctrl and out and out[-1] not in (0x20, 0x60, 0x0D, 0xA0):
                out.extend(b"\x60")  # 글 뒤에 이름이 붙으면 어절 사이 공백(「운 좋게 아트라스」)
            out.extend(b)
        else:
            runs[-1].append((k, b))
            raws[-1].append(b)
    tail_nl = len(runs) > 1 and not runs[-1]
    if tail_nl:
        runs.pop()
        raws.pop()
    if not flush() or pieces == 0:
        return None
    if tail_nl:
        out.extend(b"\r")
    return bytes(out)


BATTLE_NAME = {0x07, 0x13, 0x1A, 0x1B}  # 전투 덩이에서는 `1B` 가 행동한 쪽 이름(이름 라벨 줄이 먼저 채운 버퍼)이고 `07` 이 대상 쪽 이름이다


_long: dict[str, str] | None = None


def long_lines() -> dict[str, str]:
    """긴 전투 행동 문장(원문 20자↑ — 정본·소스에 못 둔다) — `data/battle_long.tsv` 의 해시 열쇠 → 한국어."""
    global _long
    if _long is None:
        _long = {}
        f = Path(__file__).resolve().parents[1] / "data" / "battle_long.tsv"
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                if ln and not ln.startswith("#"):
                    k, v = ln.split("\t", 1)
                    _long[k] = v
    return _long


def long_hit(key: str) -> str | None:
    return long_lines().get(hashlib.sha1(key.encode()).hexdigest()[:12])


def translate(raw: bytes, tab, battle: bool = False) -> bytes | None:
    """`battle` = 전투 덩이의 줄 — `1B` 를 수가 아니라 이름 자리로 읽는다(원문 「{1B}の攻撃」 = 「<이름>の攻撃」)."""
    if not battle:
        sp_ = special(raw, tab)
        if sp_ is not None:
            return sp_
    name_ctrl, num_ctrl = (BATTLE_NAME, set()) if battle else (NAME_CTRL, NUM_CTRL)
    sp = split(raw, name_ctrl, num_ctrl)
    if sp is None:
        return None
    lead, content, trail = sp
    tmpl, names, nums = template(content, name_ctrl, num_ctrl)
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
    if hit is None and battle:  # 긴 행동 문장 — 해시 열쇠(원문이 소스에 없다). 이름 자리 머리를 뺀 꼴과 통째 꼴 둘 다 본다
        v = long_hit(key) or (long_hit(key[len("{name}") :]) if key.startswith("{name}") and names else None)
        if v is not None:
            hit = ("battle", "", v)
            if long_hit(key) is None:
                prefix_name = names[0]
                names = names[1:]
    if hit is None:
        return segments(raw, tab, name_ctrl, num_ctrl)
    kr = hit[2]
    if battle:
        kr = battle_josa(kr.replace("\n", " "))  # 로그성 메시지 — 개행을 빼고 엔진이 어절 단위로 넘긴다(`wrap.py`, 마스터 10-18)
    elif "\n" in tmpl and "\n" not in kr and " " in kr:  # 원문이 줄을 나눴으면(이름 + 조사 ⏎ 나머지) 한국어도 첫 어절 뒤에서 나눈다 — 한 줄로 이으면 창 폭을 넘는다
        kr = kr.replace(" ", "\n", 1)
    n_name, n_num = kr.count("{name}"), kr.count("{n}")
    if n_name != len(names) or n_num != len(nums):
        return None
    out = bytearray(lead) + prefix_name
    if prefix_name and tmpl.startswith("{name}\n"):  # 원문이 이름 자리 바로 뒤에서 줄을 바꾼다(보스 대사의 이름 머리 — `{0C}{name}↵본문`) — 한국어도 이름 뒤에서 바꾼다. 안 하면 본문이 이름에 붙어 나온다(10-21 재검 13 1026:40:6)
        out += b"\x0d"
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


_EP = re.compile(rb"^(\r?EP`\x15\x85\x1b\x06)\x0e(.{4})\x0f(\x14\x04`)(.{4})(\r?)$", re.S)
_GOLD = re.compile(rb"^(\x15\x85\x1b\x06`)GOLD(\x14\x04)`(.+?)(\x12\r?)$", re.S)


def special(raw: bytes, tab) -> bytes | None:
    """승리 보상 줄 둘 — 수(`1B`)·색 스타일(`06`…`04`)이 글 가운데 끼어 일반 틀로는 못 맞춘다. 구조를 확인하고 **글만** 정본으로 바꾼다.
    ① 「EP <수> ポイント 獲得」 → 정본 「포인트 획득」(`battle` 「ﾎﾟｲﾝﾄ かくとく。」) ② 「<수> GOLD 手に入れました」 → 정본 「Gold를 얻었다.」(`system`)."""
    m = _EP.match(raw)
    if m and jptext.decode(b"\x0e" + m.group(2)).replace("{0E}", "") == "ポイント" and jptext.decode(m.group(4)) == "獲得":
        kr = canon.lookup("ﾎﾟｲﾝﾄ かくとく。", "battle", "ed2")
        if kr and len(kr.split()) == 2:
            a, b = kr.split()
            head = m.group(1)[:-1]  # 끝의 `06`(스타일) 제거 — 글자를 좁은 숫자 글꼴로 그려 한글이 깨진다(10-13 화면)
            head = head.replace(b"EP`", tab.enc("ＥＰ"), 1)  # ＥＰ 는 전각, 뒤 반각 공백은 뺀다(마스터 10-13 「ＥＰ1 포인트 획득」 — 규칙 1-4 · 2-9)
            return head + tab.enc(" ") + tab.enc(a) + m.group(3) + tab.enc(b) + m.group(5)  # 「EP n 포인트 획득」 — 수와 단위를 띄운다(규칙 1-5 · 2-9)
    m = _GOLD.match(raw)
    if m and jptext.decode(m.group(3)) == "手に入れました":
        kr = canon.lookup("Gold 手に入れました。", "system", "ed2")
        if kr and kr.startswith("Gold"):
            # 「GOLD」 4글자는 원문 바이트(ASCII 단일 바이트)를 그대로 둔다 — 글리프 코드(2B)로 바꾸면 이 뱅크의 문자열 자리가 모자라 다른 승리 문구가 일본어로 남는다(10-13)
            return m.group(1) + b"GOLD" + m.group(2) + tab.enc(kr[4:]) + m.group(4)
    return None
