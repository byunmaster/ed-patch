"""조판 — 번역문을 대사창(17칸)에 맞게 어절 단위로 개행하고(빌드가 부른다), 결과를 실제 후보로 흘려 검사한다.

🔴 **폭은 px 로 잰다**(2026-10-08, 마스터 Q5 — 대사창 가변 폭 `hook_vwf.py`): 공백·`. , ? !` 는 **4px**, 그 밖의 글자는
8px, 한 줄은 17칸 = **136px**. 칸 번호(엔진) 규칙은 그대로고, 훅이 반 칸 글자를 칸 안에 합성한다. 새 위반 ⑤ = 8px 글자가
줄 끝 칸 경계에 걸쳐 두 줄에 갈라지는 것(한 어절이 줄보다 길 때만 생긴다).

SFC 대사창은 **17칸 × 4줄 칸 배열**이고 엔진이 글자마다 칸 번호를 하나씩 올린다(`$02:DE73`) — 17칸째에서
**단어와 상관없이 기계적으로** 다음 줄로 넘어가고, 68칸을 넘으면 한 줄 올린다(`$02:DE23`). 개행 `$CF`(`\\n`)는
칸 번호를 「지금 줄의 끝 칸」으로 옮길 뿐이라(`$02:DE4F`) **17칸을 꽉 채운 직후의 개행은 빈 줄을 안 만든다**
(2026-09-27 코드 판독). 그래서 조판 위반은 거의 다 「줄이 넘쳐 기계적으로 넘어간 자리」에서 생긴다:
  ① 고아 온점 — 줄 첫 칸이 `. , ! ? …` 류          ② 빈 줄 — 겹친 개행(엔진이 무시해 의도가 샌다) · 쪽 첫머리 개행
  ③ 줄 첫 칸 공백 — 넘친 자리가 공백                 ④ 묶음 끊김 — 넘친 자리가 **어절 한가운데**
⇒ **조판기(`wrap`)**: 명시 개행 사이의 한 줄을 어절로 채우다가 17칸을 넘을 어절 앞 공백을 개행으로 바꾼다.
런타임 치환(`{D6}` 인물 · `{D7}` 대상 · `{D8}` 파티 · `{D9}` 도구 · `{DB}` 주문+레벨 · `{DC}` 수 · `{DD}` 장소)은
**가장 긴 후보 폭**으로 센다 — 짧은 이름이면 줄이 조금 일찍 꺾일 뿐 넘치지 않는다(결정적 · 정본 `textmap` 은 안 바꾼다).
부호는 어절에 붙어 있으니 ① 은 넘침이 없으면 안 생긴다. 한 어절이 17칸을 넘으면 조판기로도 못 막는다(보고).
오프닝·엔딩 크롤(`$0B:E8E5~$0B:F337`)은 다른 엔진(`open_fetch`)이고 줄을 손으로 맞춰 마스터 확인을 받았다 — 안 건드린다.

🔴 **마스터 최종 판정(2026-10-07, 전 기종 공통) — 09-27③ 번복.** 로그성 메시지(도구·주문 사용 등,
`FIELD`)도 **다른 영역과 똑같이 어절 단위 개행을 한다.** 09-27③ 「엔진 글자 단위 개행만, 어절 조판은
영구 취소」는 대체됐다 — `Typesetter.__call__`·`check_all()` 둘 다 이제 `FIELD` 를 안 건너뛰고 `wrap()`
을 건다(다만 FIELD 는 런타임 치환 후보가 **파티원뿐**이라 후보 폭표를 따로 쓴다 — `ml_field`). 엔진의
①③ 훅(`kinsoku_carry`·재진입, hook.py)은 **그대로 둔다** — 어절 조판이 못 막는 나머지 자리(한 어절이
17칸을 넘는 극단값 등)의 안전망이다. ④ 묶음 끊김은 더 이상 FIELD 라고 봐주지 않는다 — 다른 영역과
같이 0이어야 한다.

    python3 tools/typeset.py            # 전 영역 위반 수(시스템·전투·씬) + 예
    python3 tools/typeset.py --check    # tm-draft 제외 「본질 위반」이 있으면 실패
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001
import common
import hook
import namesrc
from shared.text.krwrap import split_reason  # 이어지는 어절 판정 정본(마스터 10-21) — 규칙을 다시 짓지 않는다

COLS = 17
LINE_PX = COLS * 8  # 한 줄 폭(px)
VWF = common.VWF  # 가변 폭 엔진을 켠 빌드인가(꺼져 있으면 모든 글자 8px = 예전 칸 모델)
HALF = set(" .,\u00a0")  # 4px 글자(VWF 일 때만) — hook_vwf.HALF_CODES 와 같다
NO_HEAD = set(".,!?…:;)」』")


KAGI = set("「」『』")  # 반각 글리프 · 5px 진행(hook_vwf.KAGI_ADV — 마스터 도안 F판 10-26)


def pxw(ch: str) -> int:
    if VWF and ch in KAGI:
        return 5
    return 4 if (VWF and ch in HALF) else 8


def px(s: str) -> int:
    return sum(pxw(c) for c in s)


CRAWL = (0x0BE8E5, 0x0BF337)  # 오프닝·엔딩 크롤 — 다른 엔진, 조판하지 않는다
FIELD = {
    0x07A740,
    0x07A7FB,
    0x07A81F,
    0x07A84F,
    0x07A865,
    0x07A876,
    0x07A887,
    0x07A89D,
    0x07A8B3,
    0x07A8F8,
    0x07A910,
    0x07A99F,
    0x07A9B1,
    0x07A9BF,
    0x07AA5F,
    0x07AAAD,
    0x07AB61,
    0x07AC5D,
    0x07AD1A,
    0x07AD2E,
    0x07AD44,
}  # fmt: skip — 필드에서 도구·주문을 쓸 때 나오는 조립형(`field-use-messages.md` ★) — 게이트
BATTLE = (0x07A721, 0x07C7FF)  # 시스템·전투 메시지 덩이(필드 ★ 를 뺀 나머지는 전투 쪽으로 센다)


def _dict() -> dict[str, str]:
    d = namesrc.dict_map()
    return {k: v["kr"] for k, v in d.items()}


def candidates(dm: dict[str, str] | None = None, field: bool = False) -> dict[str, list[str]]:
    """런타임 치환 후보. `field=True` 면 필드 도구·주문 메시지용 — 쓰는 이도 받는 이도 **파티원뿐**이다.
    ⚠ 전투용 후보(몬스터 이름 포함)로 필드 문장을 재면 「아크담의 부하」 폭에 맞춰 짧은 이름도 일찍 꺾인다
    (2026-09-27 마스터 판정 — 로그성 메시지는 넘칠 때만 꺾는다)."""
    dm = dm or _dict()
    party = ["세리오스", "류난", "로우", "게일", "소니아"]
    monsters = sorted({v for k, v in dm.items() if k.startswith("D3:")})
    items = sorted({v for k, v in dm.items() if k.startswith("D2:")})
    spells = sorted({v for k, v in dm.items() if k.startswith("D4:")})
    places = namesrc.places_map()
    people = party if field else party + monsters
    return {
        "D6": people,
        "D7": people + ["자신"],
        "D8": [p + " 일행" for p in party],  # 엔진이 이름 뒤에 붙이는 「 일행」(`hook.SUFFIX_TEXT`)까지
        "D9": items,
        "DB": [s + str(n) for s in spells for n in (1, 2, 3)],
        "DC": ["1", "2", "5", "10", "12", "99", "120", "999", "1285", "9999", "65535"],
        "DD": sorted(set(places["names"].values())),
    }


def representatives(vals: list[str]) -> list[str]:
    """길이마다 받침 있음/없음 대표 하나씩 — 조판은 길이와 조사 길이만 탄다."""
    seen: dict[tuple[int, bool], str] = {}
    for v in vals:
        seen.setdefault((px(v), hook.has_batchim(v[-1])), v)
    return list(seen.values())


def maxlens(cand: dict[str, list[str]]) -> dict[str, int]:
    return {k: max(px(v) for v in vals) for k, vals in cand.items()}


TOK = re.compile(
    r"\{(D[6-9A-F])\}|\{(D[0-5]:[0-9A-F]{2})\}|\{([^}]*/[^}]*)\}|<[^>]*>|\n|.", re.DOTALL
)


def _txt(atom: tuple[str, int]) -> str:
    """어절 판정에 쓰는 글 — 폭 0 제어 토큰(`<E0>` 등)은 뺀다(안 빼면 「있다.<E0>」 가 보조용언 목록에 안 걸린다)."""
    s, w = atom
    return "" if s.startswith("<") and w == 0 else s


def _word(atoms: list[tuple[str, int]], i: int) -> str:
    """atoms[i] 부터 다음 공백·줄 초기화 앞까지의 글."""
    t = ""
    while i < len(atoms) and atoms[i][0] != " " and atoms[i][1] != -1:
        t += _txt(atoms[i])
        i += 1
    return t


# ── 조판기 ─────────────────────────────────────────────────────────────────────────────
def atoms_of(kr: str, dm: dict[str, str], maxlen: dict[str, int]) -> list[tuple[str, int]]:
    """번역문 → (원문 조각, 폭) 열. 폭 -1 = 줄 초기화(개행·페이지·창 지움), 0 = 제어."""
    atoms: list[tuple[str, int]] = []
    for m in TOK.finditer(kr):
        s = m.group(0)
        if m.group(1):
            atoms.append((s, maxlen[m.group(1)]))
        elif m.group(2):
            atoms.append((s, px(dm.get(m.group(2), ""))))
        elif m.group(3):
            atoms.append((s, max(px(x) for x in m.group(3).split("/"))))
        elif s == "\n" or s in ("<EF>", "<FF>", "<FE>"):  # <FE> = 호출된 조각의 끝 — 다음 조각은 새 메시지다
            atoms.append((s, -1))
        elif s.startswith("<"):
            atoms.append((s, 0))
        else:
            atoms.append((s, pxw(s)))
    return atoms


# ── 줄·쪽 나눔 전면 규칙(번역 규칙 2-16, 마스터 10-26) ─────────────────────────────────────
NBSP = "\u00a0"  # 띄어 쓴 고유명사·굳은 명사구 속 공백 자리표시 — 어절로 안 갈라지고 폭은 반각 공백(4px)
_GLUE_LOCAL = ["슬라임 괴롭히기"]  # 정본 고유명사는 아니지만 한 덩어리로 읽히는 이 게임의 명사구(2-6)
_GLUE: list[str] = []
MIN_LEFT_NP_PX = 32  # 명사구를 묶어 내릴 때 앞 줄에 남는 글의 최소 폭(절째 내림보다 낮다 — 구가 갈리는 쪽이 더 거슬린다)
MIN_LEFT_PX = 54  # 절째 내릴 때 앞 줄에 남는 글이 이보다 짧으면(낱말 하나 정도) 그 자리에서는 끊지 않는다(줄 폭의 약 40%)
_CONJ = {"그리고", "하지만", "그러나", "그래서", "게다가", "그러면", "그런데", "그러니", "그렇다면", "그러므로", "따라서", "그렇지만", "그래도", "그러자"}
_CONN_RE = re.compile(r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|련만|건만|다만|고|며|면)$")
_SENT_END = ".!?…」』~"
_TOKEN_LINE = re.compile(r"(?:\{D[0-9A-F](?::[0-9A-F]{2})?\}|\{[^}]*/[^}]*\})+[.,!?…]*")
_AUX_AFTER_GO = ("있","계시","말","싶","않","버","보","주","드","나","오","가","두","놓")
_HANGUL = re.compile(r"[가-힣]")
_TAGLINE = re.compile(r"\{D0:8[0-4]\}")


def _glue_phrases() -> list[str]:
    if not _GLUE:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
        import canon  # 정본 고유명사 — 규칙을 다시 짓지 않는다

        cats = canon.nouns("eiyuu")["categories"]
        _GLUE.extend(sorted({v for c in cats.values() for v in c.values() if isinstance(v, str) and " " in v}
                            | set(_GLUE_LOCAL), key=len, reverse=True))  # fmt: skip
    return _GLUE


def glue(kr: str) -> str:
    for ph in _glue_phrases():
        if ph in kr:
            kr = kr.replace(ph, ph.replace(" ", NBSP))
    return kr


_SOFT_RE = re.compile(r"(?<=[^" + re.escape(_SENT_END) + r">\n :,;])(?<!\{D0:8[0-4]\})\n(?=[^<\n ])")  # 파티 화자 표지 `{D0:80~84}⏎` 뒤 개행은 머리 줄이다


def soften(kr: str) -> str:
    """① 문장 중간의 손 개행은 공백으로 읽는다 — 번역 원고의 줄 맞춤 개행이 「이야기할⏎수 있는」 같은 토막을 만든다.
    문장 끝·쪽 넘김·화자 머리(`<E3>이름⏎<E1>`) 뒤 개행과 제어 코드 앞뒤 개행은 둔다. 장 제목 카드(「제Ｎ장⏎제목⏎클리어」)도 둔다."""
    return _SOFT_RE.sub(lambda m: m.group(0) if _keep_nl(kr, m.start()) else " ", kr)


def _keep_nl(kr: str, i: int) -> bool:
    """개행 i 를 공백으로 읽지 않고 둘 자리인가 — 장 제목 카드, 또는 **앞 어절이 절 경계(쉼표·연결어미)**인 줄 끝(절째 줄을 나눈 손 개행은 조판기가 만들 줄과 같다)."""
    if _in_card(kr, i):
        return True
    a = kr.rfind("\n", 0, i) + 1
    b = kr.find("\n", i + 1)
    if _TOKEN_LINE.fullmatch(re.sub(r"<[^>]*>", "", kr[a:i]).strip()) or _TOKEN_LINE.fullmatch(re.sub(r"<[^>]*>", "", kr[i + 1 : b if b >= 0 else len(kr)]).strip()):
        return True  # 상점·시스템 조각(`{D5:xx}` 등)만으로 된 줄 — 화면에서 어떤 글인지 모르는 채 합치면 넘침·꼴 깨짐이 난다(관리자 10-26)
    m = re.search(r"(\S+)$", re.sub(r"<[^>]*>", "", kr[max(0, i - 40) : i]))
    n = re.match(r"\s*([^\s<]+)", kr[i + 1 :])
    return bool(m and bclass(m.group(1), n.group(1) if n else "") >= 1)


_CARD = re.compile(r"제[０-９0-9]+장|클리어")


def _in_card(kr: str, i: int) -> bool:
    """개행 i 가 장 제목 카드(「제Ｎ장 ⏎ 제목 ⏎ 클리어」·「… 전설 ⏎ 클리어」) 줄 사이인가 — 카드는 줄이 연출이다(`<EF>` 없이 앞 조각에서 열린 경우)."""
    a = kr.rfind("\n", 0, i)
    b = kr.find("\n", i + 1)
    prev = kr[a + 1 : i]
    nxt = kr[i + 1 : b if b >= 0 else len(kr)]
    return bool(re.search(r"제[０-９0-9]+장\s*$", prev) or re.match(r"[^\n]*\n? *클리어", nxt) or re.match(r" *클리어", nxt) or prev.endswith("클리어"))


def bclass(word: str, nxt: str = "") -> int:
    """절 경계 세기 — 3 문장 끝 · 2 쉼표 · 1 연결어미 · 0 아님. 두 음절 이하 쉼표(「오,」)·문장 머리 접속어·본용언+보조용언은 경계가 아니다."""
    w = re.sub(r"<[^>]*>", "", word)
    if "{" in w:
        w = expand_static(w)  # 사전 문장 토큰(`{D5:29}`=「나타났다.」)의 끝 부호·어미로 경계를 본다
    if not w:
        return 0
    if w[-1] in _SENT_END:
        return 3
    if w.rstrip(",") in _CONJ:
        return 0
    if w[-1] == ",":
        return 2 if len(re.sub(r"\{[^}]*\}", "xxx", w).rstrip(",")) > 2 else 0
    if len(w) >= 3 and _CONN_RE.search(w) and not (nxt and split_reason(w, nxt)):
        if w.endswith("고") and nxt.startswith(_AUX_AFTER_GO):  # 「놓치고 말아서」·「하고 있다」 — 본용언+보조용언
            return 0
        return 1
    return 0


def _clause_cut(words: list[tuple[int | None, int, str]], tail: list[tuple[int, str]], col: int) -> int | None:
    nxt_first = tail[0][1]
    """줄이 넘치는 자리에서 절째 내릴 단어 번호(words 안) — 없으면 None.
    words = 지금 줄의 (앞 공백 out 번호, 시작 col, 글), tail = 넘치는 어절부터 이어지는 (폭, 글) 열(절 끝 경계까지)."""
    if words and bclass(words[-1][2], nxt_first):  # 이미 절 경계에서 끊는다 — 그대로 둔다
        return None
    for cat in (3, 2, 1):
        for t in range(len(words) - 1, 0, -1):
            if bclass(words[t - 1][2], words[t][2]) != cat:
                continue
            sc = words[t][1]
            if sc - pxw(" ") < MIN_LEFT_PX:
                continue
            total = col - sc + sum(pxw(" ") + w for w, _t in tail)
            if total <= LINE_PX:
                return t
    return None


def _tail(atoms: list[tuple[str, int]], j: int, first_w: int, first_t: str) -> list[tuple[int, str]] | None:
    """넘치는 어절(폭 first_w)부터 절 끝 경계까지의 (폭, 글) 열. 절이 줄 폭을 넘도록 이어지면 None."""
    out = [(first_w, first_t)]
    cur = first_t
    n = len(atoms)
    while bclass(cur) == 0 and j < n and atoms[j][0] == " ":
        k, w2, t2 = j + 1, 0, ""
        while k < n and atoms[k][0] != " " and atoms[k][1] != -1:
            w2 += atoms[k][1]
            t2 += _txt(atoms[k])
            k += 1
        if not t2:
            break
        out.append((w2, t2))
        if sum(w for w, _t in out) + pxw(" ") * (len(out) - 1) > LINE_PX:
            return None
        cur, j = t2, k
    return out


def wrap(kr: str, dm: dict[str, str], maxlen: dict[str, int], rules: bool = False) -> str:
    """`_wrap` + 줄·쪽 나눔 규칙(2-16). 규칙마다 켜고 끈 변형을 **쪽 단위로** 차례로 시도해, 쪽마다 퇴행이 없는(새 나쁜 끊김 · 한 줄이던 문장 쪼갬 ·
    절 경계 상실 · 목적어/주어 줄 끝 · 고아가 늘지 않는) 첫 변형을 쓴다. 쪽 구분(`<FF>` `<EF>` `<FE>` `<E0>`)은 번역이 정한 것이라 변형이 바꾸지 않고,
    조판기는 쪽마다 줄을 새로 시작하므로 쪽을 따로 판정해도 서로 안 번진다. 절째 내림 한 번이 아래 줄 전체를 다시 감아 멀쩡한 문장을 쪼개는 일이 있다(관리자 표본 10-26)."""
    global LAST_SPANS
    LAST_SPANS = []
    if not (rules and LINERULES):
        return _wrap(kr, dm, maxlen, False, False, False, False)
    out, pos = [], 0
    for part in _PAGE_SPLIT.split(kr):
        if part in ("<FF>", "<EF>", "<FE>", "<E0>") or not part.strip():
            out.append(part)
            pos += len(part)
            continue
        res, soft = _best_page(part, dm, maxlen)
        res = one_line_sentences(res)  # 2-10 한 줄에 들어가는 문장은 한 줄로
        LAST_SPANS.append((pos, pos + len(part), soft))
        out.append(res)
        pos += len(part)
    res = "".join(out)
    bal = _balance_windows(res)  # 창(쪽) 분배 — 마지막 창에 한 어절만 남지 않게, 창 줄 수가 골고루
    return bal if _same_text(res, bal) else res


_LEAD_TAGS = re.compile(r"^(?:<(?:E1|F[0-9A](?::[0-9A-Fa-f]+)?)>)+")  # 줄머리 색 닫기·조건/분기 코드(`<E1><F2:15><FA:3700>`) — 폭이 없고 글 앞에 붙은 채 따라간다. 네이티브 호출(`<EE:…>`)·이름 머리(`<E3>`)는 줄 위치가 뜻이라 뺀다


_STATIC_TOK = re.compile(r"\{(D[0-5]):([0-9A-F]{2})\}")
_DM_CACHE: dict[str, str] = {}


def expand_static(s: str) -> str:
    """사전 토큰(`{D0:xx}`~`{D5:xx}`)과 조사 토큰(`{이/가}`)을 **정적으로 펼친다** — 엔진은 사전 문자열을 버퍼(`$174C`)에 복사해 일반 글자처럼 칸에 찍고(`hook.BUF_BASE`),
    조사는 앞 글자 받침으로 고른다(`expand`). 그 결과 문자열을 되만든다. 파티 화자 표지(`{D0:80~84}`)·표기 없는 사전·개행이 든 사전은 그대로 둔다.
    런타임 치환(`{D6}`~`{DD}`)은 폭을 모르니 남긴다 — 남으면 폭을 모르는 문장이다."""
    if not _DM_CACHE:
        _DM_CACHE.update({k: v for k, v in _dict().items() if v})

    def sub(m: re.Match) -> str:
        if m.group(1) == "D0" and m.group(2) in ("80", "81", "82", "83", "84"):
            return m.group(0)
        v = _DM_CACHE.get(f"{m.group(1)}:{m.group(2)}")
        return m.group(0) if not v or "\n" in v else v

    s = _STATIC_TOK.sub(sub, s)

    def josa(m: re.Match) -> str:
        prev = s[: m.start()].rstrip()[-1:]
        if not prev or not re.match(r"[가-힣A-Za-z0-9]", prev):
            return m.group(0)
        a, b = m.group(1).split("/")
        return a if hook.has_batchim(prev) else b

    return re.sub(r"\{([^{}/]+/[^{}/]+)\}", josa, s)


def _sentence_spans(lines: list[str]) -> list[tuple[int, int, int, int]]:
    """줄 목록에서 둘 이상의 줄에 걸친 문장 (시작 줄, 시작 어절, 끝 줄, 끝 어절). 제어 코드·사전 토큰이 든 줄과 들여쓴 줄은 문장을 끊는다(폭을 모른다)."""
    out, cur = [], None
    for k, ln in enumerate(lines):
        if "<" in _LEAD_TAGS.sub("", ln) or ln.startswith(" ") or ln.endswith(" ") or "  " in ln:  # 화자 머리 줄(`<E3>이름`)·네이티브 호출 줄도 글이 아니다
            cur = None
            continue
        for wi, w in enumerate(ln.split(" ")):
            if cur is None:
                cur = (k, wi, False)
            if "{" in expand_static(w):  # 런타임 변수 토큰이 든 문장은 폭을 모른다 — 후보에서 뺀다(문장 끝 부호가 붙은 토큰 어절은 그 문장을 닫는다)
                cur = (cur[0], cur[1], True)
            if bclass(expand_static(w)) == 3:
                if cur[0] != k and not cur[2]:
                    out.append((cur[0], cur[1], k, wi))
                cur = None
    return out


def one_line_sentences(page: str) -> str:
    """2-10 — 창 한 줄에 들어가는 문장은 두 줄로 쪼개지 않고 **새 줄에서 시작**한다(「…올랐다. MP가 / 5포인트 올랐다.」 → 「MP가 5포인트 올랐다.」를 새 줄에).
    문장 앞 글(같은 줄 앞머리)은 앞 줄에 남고, 문장 뒤 글은 같은 줄에 들어가면 잇고 아니면 새 줄로 간다. **줄이 늘어 창 높이(4줄)를 넘으면 안 한다** ·
    쪽 끝 한 어절 고아가 늘면 안 한다 · 글자는 그대로(공백·개행만 바뀐다 — 문안을 줄이지 않는다, 규칙 2-17)."""
    if not (LINERULES and ONELINE):
        return page
    lines = page.split("\n")
    for _ in range(12):
        for f, wf, k, wk in _sentence_spans(lines):
            if any(_TOKEN_LINE.fullmatch(re.sub(r"<[^>]*>", "", ln).strip()) for ln in lines[f : k + 1]):
                continue  # 토큰만으로 된 줄(사전 문장 한 줄씩 — 상점·시스템)과 맞닿은 개행은 지킨다(관리자 10-26 `token_nl_lost`) — 합침 여부는 마스터 판정 몫으로 남긴다
            fw = lines[f].split(" ")
            kw = lines[k].split(" ")
            sent = fw[wf:] + [w for ln in lines[f + 1 : k] for w in ln.split(" ")] + kw[: wk + 1]
            if px(_CTRL_TOK.sub("", expand_static(" ".join(sent)))) > LINE_PX:
                continue
            prefix, rest = fw[:wf], kw[wk + 1 :]
            if "{" in expand_static(" ".join(rest)):  # 뒤 글 폭을 모르면 같은 줄에 잇지 않고 새 줄로 둔다
                rest_fit = False
            else:
                rest_fit = True
            new = []
            if prefix:
                new.append(" ".join(prefix))
            tail = " ".join(sent)
            if rest and rest_fit and px(_CTRL_TOK.sub("", expand_static(tail + " " + " ".join(rest)))) <= LINE_PX:
                new.append(tail + " " + " ".join(rest))
            else:
                new.append(tail)
                if rest:
                    new.append(" ".join(rest))
            cand = lines[:f] + new + lines[k + 1 :]
            rows = lambda ls: sum(len(p) for p in page_rows("\n".join(ls))) + (1 if ls and _TAGLINE.fullmatch(re.sub(r"<[^>]*>", "", ls[0]).strip()) else 0)  # noqa: E731  파티 화자 줄도 창 한 줄
            if len(new) > k - f + 1 and rows(cand) > _WINDOW_ROWS:  # 줄이 늘어도 창 높이(4줄) 안이어야 한다
                continue
            if orphan_count("\n".join(cand)) > orphan_count("\n".join(lines)):
                continue
            # 줄 수가 줄면(문장이 한 줄로 합쳐지면) 빈 칸은 두지 않는다 — 합친 만큼 뒤 글이 올라오지 않는다(다음 줄은 그대로)
            lines = cand
            break
        else:
            break
    return "\n".join(lines)


def _logical(res: str) -> list[str]:
    """쪽·화자 머리 단위의 글(개행 포함) 목록 — 한 쪽 안에서 줄 나눔을 본다."""
    res = _HEADER.sub("", res)
    return [p for p in re.split(r"<FF>|<EF>|<FE>|<E0>", res) if p.strip()]


def _wpx(word: str, dm: dict[str, str], ml: dict[str, int]) -> int:
    return sum(w for _s, w in atoms_of(word, dm, ml) if w > 0)


def clause_misses(res: str, dm: dict[str, str], ml: dict[str, int]) -> list[str]:
    """(d) 줄이 넘쳐 이어진 문장에서, 그 줄이 시작한 절(앞 경계 뒤)이 다음 줄 첫 경계까지 합쳐 한 줄에 들어가는데 쪼갠 자리."""
    out = []
    sp = pxw(" ")
    for page in _logical(res):
        rows = [ln.split() for ln in _CTRL_TOK.sub("", page).split("\n") if ln.split()]
        raw = [ln.split() for ln in re.sub(r"<(?!\w+:|[A-Z0-9]{2}>)[^>]*>", "", page).split("\n") if ln.split()]
        for k in range(len(rows) - 1):
            line, nxt = rows[k], rows[k + 1]
            if bclass(line[-1], nxt[0]):  # 절 경계에서 끊은 줄은 그대로 둔다
                continue
            # 다음 줄에서 절 끝 경계까지
            end = next((m for m in range(len(nxt)) if bclass(nxt[m], nxt[m + 1] if m + 1 < len(nxt) else "")), None)
            if end is None:
                continue
            tail = sum(_wpx(w, dm, ml) for w in nxt[: end + 1]) + sp * end
            starts, col = [], 0
            for w in line:
                starts.append(col)
                col += _wpx(w, dm, ml) + sp
            col -= sp
            hit = False
            for cat in (3, 2, 1):
                for t in range(len(line) - 1, 0, -1):
                    if bclass(line[t - 1], line[t]) != cat or starts[t] - sp < MIN_LEFT_PX:
                        continue
                    if col - starts[t] + sp + tail <= LINE_PX:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out.append(" / ".join(" ".join(r) for r in rows[k : k + 2]))
    return out


def noun_splits(res: str) -> list[str]:
    """(e) 줄 끝 어절과 다음 줄 첫 어절이 [명사+명사] 굳은 구인데 줄이 갈린 자리."""
    out = []
    for page in _logical(res):
        rows = [ln.split() for ln in _CTRL_TOK.sub("", page).split("\n") if ln.split()]
        for a, b in zip(rows, rows[1:], strict=False):
            if len(a) >= 2 and noun_noun(a[-1], b[0]) and (a[-1], _stem(b[0])) in phrases():
                out.append(f"{a[-1]} / {b[0]}")
    return out


def _same_text(a: str, b: str) -> bool:
    """글 보존 — 공백·개행·쪽 넘김 위치를 빼고 같고 쪽 넘김 수도 같다."""
    f = lambda x: re.sub(r"[ \n\u00a0]|<FF>", "", x)  # noqa: E731
    return f(a) == f(b) and a.count("<FF>") == b.count("<FF>") and len(a) == len(b)


def _split_head(chunk: str) -> tuple[str, str]:
    m = re.search(r"<E3>.*?<E1>", chunk, re.S)
    return (chunk[: m.end()], chunk[m.end() :]) if m else ("", chunk)


def _body_lines(body: str) -> tuple[list[str], bool]:
    trail = body.endswith("\n")
    return body.rstrip("\n").split("\n"), trail


_WINDOW_ROWS = 4  # 대사창 한 쪽에 들어가는 줄 수


PROTECT_FF: frozenset = frozenset()  # 이 글에서 건드리면 안 되는 `<FF>` 의 차례 — 바로 뒤가 점프·분기 목표(`units.segments` 의 ff_targets)


def _window_pairs(parts: list[str]):
    """(앞 창 번호, 뒤 창 번호, 뒤 창이 이 글의 마지막 창인가) — `<FF>` 로만 이어지고 뒤 창에 화자 머리·이름 상자·카드가 없는 이웃 창 쌍."""
    idx = [k for k in range(0, len(parts), 2) if parts[k].strip()]
    ffn = {}  # 구분자 위치 → `<FF>` 차례
    for k in range(1, len(parts), 2):
        if parts[k] == "<FF>":
            ffn[k] = len(ffn)
    for a in range(len(idx) - 1, 0, -1):
        ip, inn = idx[a - 1], idx[a]
        if inn != ip + 2 or parts[ip + 1] != "<FF>" or ffn[ip + 1] in PROTECT_FF:
            continue
        pc, nc = parts[ip], parts[inn]
        if any(x in pc + nc for x in ("<E2>", "클리어")) or "<E3>" in nc or _TAGLINE.match(nc.lstrip("\n").split("\n")[0].strip() or "x"):
            continue
        yield ip, inn, a == len(idx) - 1


def _window_move(pc: str, nc: str, last: bool) -> tuple[str, str] | None:
    """앞 창 마지막 줄을 뒤 창 머리로 옮겨야 하고 옮길 수 있으면 (새 앞 창, 새 뒤 창). 쪽 수는 그대로다."""
    head, body = _split_head(pc)
    lp, trail = _body_lines(body)
    ln, _t = _body_lines(nc)
    if len(lp) < 2 or any(not x.strip() for x in lp + ln) or "<" in lp[-1] or ln[0].startswith(("<", "{D0:8")) or _TOKEN_LINE.fullmatch(lp[-1].strip()) or _TOKEN_LINE.fullmatch(ln[0].strip()):
        return None
    orphan = last and len(ln) == 1 and len(ln[0].split()) == 1 and bool(_HANGUL.search(ln[0]))
    # 여러 창 대사는 창마다 원문 창의 내용을 그대로 둔다(규칙 2-17, 마스터 10-31) — 옮기는 건 마지막 창에 고아 어절 하나만 남는 경우뿐이다.
    # 창 줄 수 차이(h2)를 줄이려고 줄을 옮기지 않는다.
    if not orphan or len(ln) + 1 > _WINDOW_ROWS:
        return None
    qn, qo = bclass(re.sub(r"<[^>]*>", "", lp[-2].split(" ")[-1])), bclass(re.sub(r"<[^>]*>", "", lp[-1].split(" ")[-1]))
    # 창 경계는 문장 끝 > 절 경계로만 옮긴다 — 전에 문장 끝이던 경계를 문장 중간으로 옮기지 않고(「백성을¶버리려 하셨습니다」), 관형어·목적어·주어 뒤에서 끊지 않는다
    if qn < 1 or qn < qo or _poor_end(re.sub(r"<[^>]*>", "", lp[-2].split(" ")[-1])):
        return None
    return head + "\n".join(lp[:-1]) + ("\n" if trail else ""), lp[-1] + "\n" + nc


def _balance_windows(res: str) -> str:
    """창(쪽) 분배 — 마지막 창에 한 어절만 남은 꼴을 없애고(앞 창 마지막 줄을 뒤 창 머리로), 이웃 창 줄 수 차가 2 이상이면 줄여 준다.
    창 수·글은 그대로이고 `<FF>` 위치만 한 줄 앞으로 온다. 뒤 창이 새 화자(머리)·이름 상자·카드이거나 옮길 줄에 제어 코드가 있으면 안 한다."""
    parts = _PAGE_SPLIT.split(res)
    for _ in range(3):
        moved = False
        for ip, inn, last in _window_pairs(parts):
            mv = _window_move(parts[ip], parts[inn], last)
            if mv:
                parts[ip], parts[inn] = mv
                moved = True
        if not moved:
            break
    return "".join(parts)


def window_boundaries(res: str) -> tuple[int, int]:
    """(문장 끝으로 끝나는 창 경계 수, 관형어·목적어·주어 뒤에서 끊긴 창 경계 수) — `<FF>` 로만 이어진 이웃 창 사이."""
    parts = _PAGE_SPLIT.split(res)
    sent = poor = 0
    for ip, _inn, _last in _window_pairs(parts):
        lp = [x for x in re.sub(r"<[^>]*>", "", _split_head(parts[ip])[1]).split("\n") if x.strip()]
        w = lp[-1].split()[-1] if lp and lp[-1].split() else ""
        sent += bclass(w) == 3
        poor += _poor_end(w)
    return sent, poor


def window_issues(res: str) -> tuple[list[str], list[str]]:
    """(h 마지막 창이 한 어절 · h2 창 수를 안 늘리고 고르게 나눌 수 있는데 이웃 창 줄 수 차가 2 이상) — 해당 창의 마지막 줄 글."""
    parts = _PAGE_SPLIT.split(res)
    h, h2 = [], []
    for ip, inn, last in _window_pairs(parts):
        ln, _t = _body_lines(parts[inn])
        lp, _t2 = _body_lines(_split_head(parts[ip])[1])
        if last and len(ln) == 1 and len(ln[0].split()) == 1 and _HANGUL.search(ln[0]) and len(lp) >= 2:
            h.append(" / ".join(re.sub(r"<[^>]*>", "", x) for x in (lp[-1], ln[0])))
        if len(lp) - len(ln) >= 2 and _window_move(parts[ip], parts[inn], last):
            h2.append(" / ".join(re.sub(r"<[^>]*>", "", x) for x in (lp[-1], ln[0])))
    return h, h2


def token_nl_lost(kr: str, res: str) -> int:
    """제어 조각 합침 — 원고에서 `{Dx:..}` 토큰만으로 된 줄과 맞닿은 개행이 조판 결과에서 사라진 수(0 이어야 한다)."""
    if len(kr) != len(res):
        return 0
    n = 0
    for m in re.finditer(r"\n", kr):
        i = m.start()
        a, b = kr.rfind("\n", 0, i) + 1, kr.find("\n", i + 1)
        if (_TOKEN_LINE.fullmatch(re.sub(r"<[^>]*>", "", kr[a:i]).strip()) or _TOKEN_LINE.fullmatch(re.sub(r"<[^>]*>", "", kr[i + 1 : b if b >= 0 else len(kr)]).strip())) and res[i] != "\n":
            n += 1
    return n


def _cost(kr: str, res: str, dm: dict[str, str], ml: dict[str, int]) -> int:
    """변형의 나쁨 점수(낮을수록 좋다) — 쪽 끝 고아 10 · 갈리면 안 되는 이음 8 · 명사구 갈림 6 · 목적어·주어만 줄 끝에 남은 줄 4 · 절째 내림 놓침 4 ·
    문장 중간에 남은 손 개행 3 (손 개행 하나를 지우고 목적어 줄 끝 하나가 생기면 지는 쪽 — 관리자 표본 2d7607)."""
    poor = sum(1 for a, _b in break_pairs(res) if _poor_end(a))
    hand = sum(1 for i, c in enumerate(kr) if c == "\n" and i < len(res) and res[i] == "\n" and _mid_sentence_nl(kr, i))
    bad = sum(1 for a, b in break_pairs(res) if _bad_break(a, b))
    return 10 * orphan_count(res) + 8 * bad + 6 * len(noun_splits(res)) + 4 * poor + 4 * len(clause_misses(res, dm, ml)) + 3 * hand


def _mid_sentence_nl(kr: str, i: int) -> bool:
    before = re.sub(r"<[^>]*>", "", kr[:i])[-1:]
    after = kr[i + 1 : i + 2]
    if not before or before in _SENT_END or before in " \n:,;" or after in ("<", "", " ", "\n") or kr[i - 1 : i] == ">":
        return False
    return not _keep_nl(kr, i)


_DP_HEAD = re.compile(r"((?:<E3>[^\n<]*\n?<E1>)?(?:<(?:E1|F[0-9A](?::[0-9A-Fa-f]+)?)>)*)(.*)", re.S)
_DP_MAXWORDS = 26


def _obj(res: str) -> int:
    """객관 결함 점수 — 쪽 끝 고아 10 · 갈리면 안 되는 이음 8 · 명사구 갈림 6 (취향 쪽 항목은 뺀다)."""
    return 10 * orphan_count(res) + 8 * sum(1 for a, b in break_pairs(res) if _bad_break(a, b)) + 6 * len(noun_splits(res))


def _dp_page(kr: str, dm: dict[str, str], maxlen: dict[str, int], bar: int) -> str | None:
    """줄 나눔 전수 탐색 — 어절 열(`_DP_MAXWORDS` 이하)의 모든 개행 배치 가운데 객관 결함 점수(`_obj`)가 `bar` 보다 낮고 나쁨 점수(`_cost`)가 가장 낮은 것을 낸다. 탐욕 조판이 닿지 못하는 자리(사전 토큰을 펼쳐 보니
    [명사+의+명사]·고아·관형사 고아를 피하는 배치가 있는 쪽)를 구한다. 글자는 그대로 — 공백↔개행만 바뀐다. 줄 폭 ≤136px · 창 높이 ≤4줄.
    제어 코드가 줄 가운데 끼거나 토큰만으로 된 줄이 있거나 화자 표지·장 제목 카드·이름 상자 쪽이면 안 한다(None)."""
    if "<E2>" in kr or "클리어" in kr or "\n\n" in kr:
        return None
    m = _DP_HEAD.fullmatch(kr)
    head, body = m.group(1), m.group(2)
    rows_left = _WINDOW_ROWS
    mt = _TAGLINE.match(body)  # 맨 앞 파티 화자 줄(`{D0:80~84}`)은 머리로 두되 창 한 줄을 쓴다(원판 창도 그 줄을 센다)
    if mt and body[mt.end() : mt.end() + 1] == "\n":
        head, body, rows_left = head + body[: mt.end() + 1], body[mt.end() + 1 :], rows_left - 1
    if _TAGLINE.search(body):
        return None
    core = body.rstrip(" \n")
    tail = body[len(core) :]
    if "<" in core or not core or any(_TOKEN_LINE.fullmatch(ln.strip()) for ln in core.split("\n")):
        return None
    words = re.split(r"[ \n]", core)
    n = len(words)
    if n < 3 or n > _DP_MAXWORDS or not all(words):
        return None
    wpx = [px(expand_static(w)) for w in words]
    if any("{" in expand_static(w) for w in words):
        return None  # 런타임 변수 — 폭을 모른다
    sp = pxw(" ")
    best, best_cost = None, 1 << 30

    def layouts(i: int, rows: int):
        """i 번째 어절부터 남은 줄 수 `rows` 안에 담는 모든 배치 — 줄 폭으로 가지를 친다."""
        if i == n:
            yield []
            return
        if rows == 0:
            return
        w = 0
        for j in range(i, n):
            w += wpx[j] + (sp if j > i else 0)
            if w > LINE_PX:
                break
            for rest in layouts(j + 1, rows - 1):
                yield [words[i : j + 1]] + rest

    for lines in layouts(0, rows_left):
        cand = head + "\n".join(" ".join(ln) for ln in lines) + tail
        if len(cand) != len(kr) or _obj(cand) >= bar:
            continue
        c = _cost(kr, cand, dm, maxlen)
        if c < best_cost or (c == best_cost and best is not None and cand.count("\n") < best.count("\n")):
            best, best_cost = cand, c
    return best


def _rows_over(res: str) -> bool:
    """분기 코드 없는 쪽이 창 높이(`_WINDOW_ROWS`줄)를 넘나 — 화자 줄을 포함해 센다."""
    if re.search(r"<(?:@|F\w:|FA:)", res):
        return False
    body = re.sub(r"^(?:<E3>[^\n<]*\n?<E1>)", "", res)  # 화자 이름 머리만 뺀다 — 파티 화자 줄(`{D0:80~84}`)은 창 한 줄이다
    return sum(1 for ln in body.split("\n") if re.sub(r"<[^>]*>", "", ln).strip()) > _WINDOW_ROWS


def _best_page(kr: str, dm: dict[str, str], maxlen: dict[str, int]) -> tuple[str, bool]:
    """쪽 하나의 변형 가운데 하드 퇴행(새 나쁜 끊김 · 한 줄 문장 쪼갬 · 절 경계 상실 · 고아 증가)이 없고 나쁨 점수가 가장 낮은 것. 규칙 전 조판도 후보다."""
    orig = _wrap(kr, dm, maxlen, False, False, False, False)  # 규칙 전 조판 — 퇴행의 기준
    best, best_cost, best_soft = orig, _cost(kr, orig, dm, maxlen), False
    for soft in (True, False):  # 손 개행 공백화까지 / 손 개행은 두고 나머지 규칙만
        for clause, np, orph in ((1, NOUNPHRASE, 1), (1, 0, 1), (0, NOUNPHRASE, 1), (0, 0, 1), (1, NOUNPHRASE, 0), (1, 0, 0), (0, NOUNPHRASE, 0), (0, 0, 0)):
            if not soft and not (clause or np or orph):
                continue
            v = _wrap(kr, dm, maxlen, True, bool(clause), bool(np), bool(orph), soft)
            reg = regressions(orig, v)
            # 쪽 끝 고아(2-16 ③, 객관 결함)를 없애는 대신 줄 끝 절 경계(②, 취향 쪽)를 하나 잃는 건 받는다 — 다른 퇴행이 없을 때만
            if reg and not (orphan_count(v) < orphan_count(orig) and all(r.startswith(("절 경계 상실", "문장 쪼갬")) for r in reg)):
                continue
            if v == orig or token_nl_lost(kr, v):
                continue
            c = _cost(kr, v, dm, maxlen)
            if c < best_cost:
                best, best_cost, best_soft = v, c, soft
    over = _rows_over(best)
    if "{" in kr and (_obj(best) > 0 or over):  # 사전 토큰이 든 쪽에 객관 결함(고아·나쁜 끊김·명사구 갈림)이 남았거나 창 높이(4줄)를 넘으면 줄 나눔 전수 탐색(탐욕 조판이 못 닿는 배치) — 문장 단위 줄바꿈 탓에 넘긴 쪽을 4줄 안으로 되돌린다(2-10, 마스터 11-05)
        dp = _dp_page(kr, dm, maxlen, 1 << 30 if over else _obj(best))  # 넘친 쪽은 4줄 안의 배치가 먼저다 — 결함 점수는 `_cost` 가 가른다
        if dp is not None and (over or not regressions(orig, dp)) and not token_nl_lost(kr, dp):  # 넘친 쪽은 4줄 안이 우선 — 명사구 갈림 같은 취향 쪽 결함을 받는다(마스터 11-05 「한 칸에 표시할 수 있음에도 문장 단위 개행으로 넘어가는 경우는 없어야」)
            best, best_soft = dp, True
    return best, best_soft


def _wrap(kr: str, dm: dict[str, str], maxlen: dict[str, int], rules: bool, clause: bool, nounphrase: bool, orphans: bool, soft: bool = True) -> str:
    """명시 개행·페이지 사이 한 줄을 어절로 채우다가 17칸을 넘을 어절 앞 공백을 `\\n` 으로 바꾼다.
    `rules=True` 면 줄·쪽 나눔 전면 규칙(2-16)을 더한다: ① 손 개행 공백화 ② 절째 내림 ③ 쪽 끝 한 어절 고아 ④ 고유명사 한 줄."""
    src = kr
    if rules and LINERULES:
        kr = glue(soften(kr) if soft else kr)
    atoms = atoms_of(kr, dm, maxlen)
    out: list[str] = []
    col = 0
    prev = ""  # 지금 어절의 글(split_reason 입력)
    words: list[tuple[int | None, int, str]] = []  # 지금 줄의 (앞 공백 out 번호, 시작 col, 글)
    wstart, wspace = 0, None
    for i, (s, w) in enumerate(atoms):
        if w == -1:
            out.append(s)
            col = 0
            prev = ""
            words, wstart, wspace = [], 0, None
        elif s == " ":
            if prev:
                words.append((wspace, wstart, prev))
            j, ww, nxt = i + 1, 0, ""  # 다음 어절 폭
            while j < len(atoms) and atoms[j][0] != " " and atoms[j][1] != -1:
                ww += atoms[j][1]
                nxt += _txt(atoms[j])
                j += 1
            nxt0 = nxt  # 넘치는 어절 자신(묶음 이음을 따라가기 전)
            # 앞뒤 어절이 한 덩어리(본용언+보조용언 등)면 뒤 어절까지 한 단위로 센다 — 단위가 한 줄보다 길면 포기
            while j < len(atoms) and atoms[j][0] == " " and (bonded(nxt, _word(atoms, j + 1)) if rules and LINERULES else split_reason(nxt, _word(atoms, j + 1))):
                k, w2, t2 = j + 1, 0, ""
                while k < len(atoms) and atoms[k][0] != " " and atoms[k][1] != -1:
                    w2 += atoms[k][1]
                    t2 += _txt(atoms[k])
                    k += 1
                if ww + pxw(" ") + w2 > LINE_PX:
                    break
                ww += pxw(" ") + w2
                nxt, j = t2, k
            if col and col + pxw(" ") + ww > LINE_PX:
                cut = None
                if clause and rules and LINERULES:
                    tail = _tail(atoms, j, ww, nxt)
                    if tail:
                        cut = _clause_cut(words, tail, col)
                if cut is None and nounphrase and len(words) >= 2:
                    last = words[-1][2]
                    if (noun_noun(last, nxt0) and (last, _stem(nxt0)) in phrases() and words[-1][1] - pxw(" ") >= MIN_LEFT_NP_PX
                            and not _bad_break(words[-2][2], last)
                            and col - words[-1][1] + pxw(" ") + ww <= LINE_PX):  # fmt: skip
                        cut = len(words) - 1
                if cut is None:
                    out.append("\n")
                    col = 0
                    words = []
                else:  # 절째 내린다 — 이 줄에서 시작한 절 앞 공백을 개행으로, 그 뒤 글은 새 줄로
                    sc = words[cut][1]
                    out[words[cut][0]] = "\n"
                    words = [(a, b - sc, t) for a, b, t in words[cut:]]
                    words[0] = (None, 0, words[0][2])
                    col -= sc
                    out.append(" ")
                    col += pxw(" ")
            else:
                out.append(" ")
                col += pxw(" ")
            prev = ""
            wstart, wspace = col, len(out) - 1
        else:
            out.append(s)
            col += w
            prev += _txt((s, w))
    res = "".join(out)
    if rules and LINERULES:
        if orphans:
            res = _fix_orphans(res, kr, dm, maxlen)
        res = res.replace(NBSP, " ")
    lossless(soften(src) if rules and LINERULES and soft else src, res, join=rules and LINERULES)
    return res


NOUNPHRASE = os.environ.get("ED_NOUNPHRASE", "1") != "0"  # ⑥ 명사구 묶기 끄기(전·후 지표 비교용)
LAST_SPANS: list[tuple[int, int, bool]] = []  # 마지막 wrap 의 쪽별 (시작, 끝, 손 개행 공백화를 썼는가) — 지표 c 가 읽는다
LINERULES = os.environ.get("ED_LINERULES", "1") != "0"  # 2-16 규칙 끄기(전·후 지표 비교용)
ONELINE = os.environ.get("ED_ONELINE", "1") != "0"  # 2-10 한 줄 문장 규칙 끄기(전·후 지표 비교용 — 지표 f 가 이 규칙이 치른 절 경계 상실을 가른다)
# ── ⑥ [명사+명사] 굳은 구(「노예 상인」) — 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사로 안 끝나면 명사로 보고
# 같은 이음이 대사 전량에 2회 이상 나오면 구로 본다(오탐은 줄 수가 안 늘 때만 묶으니 해가 작다). md-ed1 `linebreak.py` 와 같은 판정.
_NOT_NOUN_END = set("은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들")
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리",
    "또다시", "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써",
    "이미", "결코", "반드시", "제발", "어서", "함께", "같이", "그냥",
}  # fmt: skip
_JOSA_TAIL = "은는이가을를의에도로와과만"
_PHRASES: set | None = None


def _adnominal(w: str) -> bool:
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa: str, wb: str) -> bool:
    if not wa or not wb or "{" in wa or "{" in wb or "<" in wa or "<" in wb or wa in _NOT_NOUN:
        return False
    if wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」』~" or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")  # 서술어·지시어로 시작하는 뒤는 구가 아니다


def _stem(w: str) -> str:
    return w.rstrip(_JOSA_TAIL + ".,!?…」』~") or w


def phrases() -> set:
    """대사 전량에서 같은 [앞 어절, 뒤 어절 줄기] 이음이 두 번 이상 나온 명사 구(반복이 구라는 증거)."""
    global _PHRASES
    if _PHRASES is None:
        import collections
        import itertools

        segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
        cnt: collections.Counter = collections.Counter()
        for e in segs.values():
            t = e.get("kr")
            if not t:
                continue
            for part in re.split(r"<[^>]*>", t.replace("\n", " ")):
                for x, y in itertools.pairwise(part.split()):
                    if noun_noun(x, y):
                        cnt[(x, _stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


_PAGE_SPLIT = re.compile(r"(<FF>|<EF>|<FE>|<E0>)")


_DET = {"이런", "그런", "저런", "어떤", "무슨", "이", "그", "저", "모든", "여러", "새", "헌", "다른", "어느"}  # 관형사 — 줄 끝에 홀로 남기지 않는다
_DEP_NOUN = ("쪽", "것", "수", "줄", "때", "적", "지", "뿐", "대로", "만큼", "듯", "채", "척", "양", "바", "리", "데", "터", "편", "중", "군데", "번", "거", "게", "나름", "따름")  # 의존명사 — 앞 관형형과 갈리지 않는다
_AUX_STEM = ("줬", "주", "봤", "보", "둬", "두", "놓", "버", "내", "드리", "줄", "볼", "둘", "줘")  # 연결어미 -아/어 뒤 보조용언 어두


def local_bond(a: str, b: str) -> bool:
    """krwrap `split_reason` 이 못 거르는 한 덩어리 — 관형사+체언(「이런 물건」), 「해 줬잖아」 꼴 -아/어+보조용언(공백 둔 표기)."""
    if a in _DET and b:
        return True
    if re.fullmatch(r"[0-9][0-9,]*", a) and re.match(r"[A-Za-z가-힣]", b):  # 수 + 단위(「50000 GOLD」)
        return True
    if len(a) <= 3 and a.endswith(("해", "아", "어", "여", "와", "워")) and b.startswith(_AUX_STEM):
        return True
    if a.endswith(("는", "은", "ㄴ", "을", "던")) and re.match(r"(" + "|".join(_DEP_NOUN) + r")(이|가|은|는|을|를|도|에|의|으로|로)?[.,!?…]*$", b):
        return True  # 관형형 + 의존명사(「늘어놓는 쪽」·「할 수」·「먹은 것」)
    return False  # 「-기로 되다·하다」·「-게 되다」·「-다고 하다」·「-지 뭐야」는 공용 krwrap `split_reason` 이 정본이다(10-26)


def bonded(a: str, b: str) -> bool:
    return bool(split_reason(a, b)) or local_bond(a, b)


_HEADER = re.compile(r"<E3>.*?\n?<E1>", re.S)
_CTRL_TOK = re.compile(r"<[^>]*>")


def page_rows(res: str) -> list[list[list[str]]]:
    """조판 결과 → 쪽 목록(쪽 = 줄 목록, 줄 = 어절 목록). 화자 머리·제어 코드·빈 줄·파티 화자 표지 줄을 뺀다.
    장 제목 카드(「클리어」 쪽)와 이름 상자 조각(`<E2>`)은 줄이 연출·구조라 뺀다."""
    res = expand_static(_HEADER.sub("", res))  # 사전 토큰은 펼쳐서 어절·줄 수를 센다(엔진은 사전 문자열을 일반 글자처럼 찍는다)
    pages = []
    for p in _PAGE_SPLIT.split(res):
        if p in ("<FF>", "<EF>", "<FE>", "<E0>") or "<E2>" in p or "클리어" in p:
            continue
        lines = [ln.split() for ln in _CTRL_TOK.sub("", p).split("\n") if ln.split() and not _TAGLINE.fullmatch(ln.strip())]
        if lines:
            pages.append(lines)
    return pages


def _poor_end(w: str) -> bool:
    """목적어·주어만 줄 끝에 남은 어절(을/를/이/가 — 술어와 갈렸다)."""
    return len(w) >= 2 and w.endswith(("을", "를", "{을/를}", "{이/가}", "가", "이")) and bclass(w) == 0


def orphan_count(res: str) -> int:
    """두 줄 이상인 쪽의 마지막 줄이 한 어절(한글)인 쪽 수."""
    return sum(1 for lines in page_rows(res) if len(lines) >= 2 and len(lines[-1]) == 1 and _HANGUL.search(lines[-1][0]))


def break_pairs(res: str) -> list[tuple[str, str]]:
    out = []
    for lines in page_rows(res):
        out += [(a[-1], b[0]) for a, b in zip(lines, lines[1:], strict=False)]
    return out


def sentence_lines(res: str) -> dict[str, int]:
    """문장(문장 끝 어절까지) → 걸친 줄 수."""
    out: dict[str, int] = {}
    for lines in page_rows(res):
        cur, first = [], 0
        for k, ln in enumerate(lines):
            for w in ln:
                if not cur:
                    first = k
                cur.append(w)
                if bclass(w) == 3:
                    out[" ".join(cur)] = k - first + 1
                    cur = []
    return out


def regressions(before: str, after: str) -> list[str]:
    """규칙 전에 없던 나쁜 끊김 · 전에 한 줄이던 문장이 갈린 것."""
    import collections

    new = collections.Counter(break_pairs(after)) - collections.Counter(break_pairs(before))
    out = [f"{a} / {b}" for (a, b), n in new.items() if _bad_break(a, b) for _ in range(n)]
    bb = sum(1 for a, b in break_pairs(before) if bclass(a, b))
    ba = sum(1 for a, b in break_pairs(after) if bclass(a, b))
    if ba < bb:
        out.append(f"절 경계 상실: 줄 끝 절 경계 {bb} → {ba}")
    if orphan_count(after) > orphan_count(before):
        out.append("쪽 끝 고아가 늘었다")
    sb, sa = sentence_lines(before), sentence_lines(after)
    out += [f"문장 쪼갬: {t[:40]}" for t, n in sa.items() if n > 1 and sb.get(t) == 1]
    return out


def _bad_break(a: str, b: str) -> bool:
    """줄 사이로 갈리면 안 되는 이음 — krwrap `split_reason`(본용언+보조용언·의존명사·관형사 고아) 또는 [명사+명사] 굳은 구."""
    ta, tb = expand_static(re.sub(r"<[^>]*>", "", a)), expand_static(re.sub(r"<[^>]*>", "", b))
    if "{" in ta or "{" in tb:
        return False  # 런타임 변수(`{D6}`…) — 어떤 말인지 모른다
    return bonded(ta, tb) or (noun_noun(ta, tb) and (ta, _stem(tb)) in phrases())


def _fix_orphans(res: str, kr: str, dm: dict[str, str], maxlen: dict[str, int]) -> str:
    """③ 쪽 끝 줄이 한 어절이면(문장이 이어지는 경우) 앞 줄 마지막 어절을 내려 두 어절로 만든다 — 앞 줄 끝이 조판기가 낸 개행일 때만."""
    chunks = _PAGE_SPLIT.split(res)
    pos = 0
    for ci, ch in enumerate(chunks):
        if ch in ("<FF>", "<EF>", "<FE>", "<E0>") or not ch.strip():
            pos += len(ch)
            continue
        hm = re.search(r"<E3>.*?<E1>", ch, re.S)
        body0 = hm.end() if hm else 0
        body = ch[body0:]
        lines = body.split("\n")
        real = [k for k, ln in enumerate(lines) if re.sub(r"<[^>]*>", "", ln).strip()]
        real = [k for k in real if not _TAGLINE.fullmatch(lines[k].strip())]  # 파티 화자 표지 줄은 본문이 아니다
        if len(real) >= 2 and "클리어" not in ch:  # 장 제목 카드는 줄이 연출이다
            lk, pk = real[-1], real[-2]
            last, pl = lines[lk], lines[pk]
            lt = expand_static(re.sub(r"<[^>]*>", "", last).strip())  # 사전 문장 토큰 한 어절(`{D5:29}`=「나타났다.」)도 고아다
            if " " not in lt and "{" not in lt and _HANGUL.search(lt) and pk == lk - 1 and " " in pl.strip() and not _TOKEN_LINE.fullmatch(pl.strip()):
                nl_at = pos + body0 + sum(len(x) + 1 for x in lines[:lk]) - 1  # 마지막 줄 앞 개행의 절대 위치
                plw = pl.split(" ")
                # 내릴 어절 수: 앞 줄 끝에 한 문장이 통째로 들어 있으면 그 문장째(문장을 쪼개지 않는다),
                # 아니면 한 어절 — 새로 생기는 끊김이 본용언+보조용언·관형사 고아·[명사+명사] 구를 가르면 같이 내린다.
                ends = [i for i, w in enumerate(plw[:-1]) if bclass(re.sub(r"<[^>]*>", "", w)) == 3]
                last_ends = bclass(re.sub(r"<[^>]*>", "", plw[-1])) == 3
                started_here = len(real) < 3 or bclass(re.sub(r"<[^>]*>", "", lines[real[-3]].split(" ")[-1])) == 3
                if not last_ends:
                    m = 1  # 문장이 고아 줄로 이어진다 — 어절 하나를 내려 두 어절로
                elif ends:
                    m = len(plw) - 1 - ends[-1]  # 앞 줄 끝 문장이 통째로 들어 있다 — 문장째 내린다(쪼개지 않는다)
                elif started_here:
                    # 한 줄이 한 문장이다 — 쪼개지 않는 게 원칙이지만, 다음 줄이 한 어절 문장으로 쪽을 끝내는 고아(2-16 ③)가 더 나쁘다:
                    # 앞 줄 안에 쉼표 절 경계가 있으면 거기서 쪼갠다(없으면 포기)
                    cs = [i for i, w in enumerate(plw[:-1]) if bclass(re.sub(r"<[^>]*>", "", w)) == 2]
                    if not cs:
                        pos += len(ch)
                        continue
                    m = len(plw) - 1 - cs[-1]
                else:
                    m = 1
                while m < 6 and len(plw) > m + 1 and _bad_break(plw[-m - 1], plw[-m]):
                    m += 1
                if m >= 6 or len(plw) <= m:
                    pos += len(ch)
                    continue
                # 절 중간에서 가르지 않는다 — 이 줄에서 시작한 절을 통째로 내릴 수 있으면(맞으면) 그 길을 먼저, 안 들어가면 최소 어절만
                m2 = m
                while m2 + 1 < len(plw) and m2 < 6 and bclass(re.sub(r"<[^>]*>", "", plw[-m2 - 1])) == 0:
                    m2 += 1
                for mm in dict.fromkeys((m2, m)):
                    if mm != m and (len(plw) - mm < 2 or _bad_break(plw[-mm - 1], plw[-mm])):
                        continue  # 절째 내리느라 앞 줄이 한 어절만 남거나 새 나쁜 끊김이 생기면 최소 어절 쪽으로
                    ws = [" ".join(plw[:-mm]), " ".join(plw[-mm:])]
                    pw = re.sub(r"<[^>]*>", "", ws[1])
                    if not (nl_at < len(res) and ws[0] and ws[1] and pw
                            and sum(w for _s, w in atoms_of(ws[1] + " " + last, dm, maxlen) if w > 0) <= LINE_PX):  # fmt: skip
                        continue
                    sp_at = pos + body0 + sum(len(x) + 1 for x in lines[:pk]) + len(ws[0])
                    if res[sp_at] == " " and res[nl_at] == "\n":
                        res = res[:sp_at] + "\n" + res[sp_at + 1 : nl_at] + " " + res[nl_at + 1 :]
                        break
        pos += len(ch)
    return res


class TextLost(RuntimeError):
    """조판이 글을 잃거나 바꿨다 — 빌드를 멈춘다(`build.py` 의 `except ValueError` 에 안 먹히게 따로 둔다)."""


def lossless(kr: str, res: str, join: bool = False) -> None:
    """🔴 「글 소실 없음」 불변식 — 조판기가 하는 일은 **공백 하나를 개행 하나로 바꾸는 것뿐**이다.

    그래서 길이가 같고, 다른 자리는 전부 `' ' → '\\n'` 이어야 한다(공백·개행을 뺀 글자 열이 같다는 것보다 세다).
    PS1 에서 어절 단위로 물러나 끊는 수정이 특정 폭에서 꼬리 글을 잃었는데 검사기가 폭·위반만 봐서 못 잡았다(09-27 관리자 공유).
    """
    bad = len(kr) != len(res) or any(
        a != b and (a, b) != (" ", "\n") and not (join and (a, b) == ("\n", " "))
        for a, b in zip(kr, res, strict=False)
    )
    if bad:
        raise TextLost(f"조판이 글을 바꿨다: {kr!r} → {res!r}")


def indent_quotes(kr: str) -> str:
    """크롤·엔딩 인물 대사 — 「 로 열린 말은 **둘째 줄부터 한 칸(8px) 들여** 첫 글자가 「 다음 글자와 세로로 맞게 한다(마스터 10-08).
    들임 = 반각 공백 둘(4px×2, 줄에 이미 있던 앞 공백은 갈음). 「 와 」 를 글자 단위로 따라가므로 `」<FF>「` 처럼 쪽 사이에서
    다시 열려도 이어진다. 명시 개행 뒤 공백은 훅이 건너뛰지 않는다(`V_NLF`)."""
    out, inq = [], False
    for line in kr.split("\n"):
        if inq and line.strip():
            line = "  " + line.lstrip(" ")
        out.append(line)
        for ch in line:
            if ch == "「":
                inq = True
            elif ch == "」":
                inq = False
    return "\n".join(out)


RUNTIME_WIDTH = re.compile(r"\{D[6-9A-D]\}")  # 폭이 런타임에 정해지는 치환 토큰(파티원·몬스터·아이템·주문·숫자·지명)


def join_space(kr: str) -> str:
    """로그성 조각(전투 결과·시스템)이 `.`·`!`·`?` 로 끝나면 끝에 반각 공백을 하나 둔다.

    이 메시지들은 조각 하나가 한 문장이고 **엔진이 조각을 이어 한 창에 찍는다**(「회심의 일격!」 +
    「슬라임에게 65의 피해!」 …). 일본어는 문장 사이에 공백이 없지만 한글은 번역 규칙 2-1 (부호 뒤에는 반각 공백)이
    걸린다 — 가변 폭(VWF)에서 `!`·`.` 가 4px 라 공백이 없으면 「일격!슬라임에게」 로 붙어 보였다(2026-10-09 C3 실기).
    문안마다 손대지 않고 **이어 붙는 자리**(조각 끝)에서 한 번에 넣는다. 조각 끝 공백은 줄 끝이면 개행으로 바뀐다.
    """
    return re.sub(r"([.!?])(<E[04]>)$", r"\1 \2", kr)


class Typesetter:
    """빌드가 쓰는 입구 — 사전·후보 폭을 한 번만 읽는다."""

    def __init__(self) -> None:
        self.dm = _dict()
        self.ml = maxlens(candidates(self.dm))
        self.ml_field = maxlens(candidates(self.dm, field=True))

    def __call__(self, kr: str, addr: int) -> str:
        global PROTECT_FF
        if CRAWL[0] <= addr <= CRAWL[1]:
            return indent_quotes(kr)
        PROTECT_FF = _ff_targets().get(addr, frozenset()) if "<FF>" in kr else frozenset()
        # 마스터 최종 판정(2026-09-30, 전 기종 공통) — 로그성 메시지도 어절 단위 개행을 한다
        # (09-27③ 「엔진 기계적 개행만」을 대체). FIELD 는 후보 폭이 파티원뿐이라 더 좁다.
        ml = self.ml_field if addr in FIELD else self.ml
        if BATTLE[0] <= addr <= BATTLE[1]:
            kr = join_space(kr)
            if RUNTIME_WIDTH.search(kr):
                # 이름·주문·숫자 치환이 낀 로그는 **정적 개행을 안 건다** — 후보 중 가장 긴 이름으로 재면 짧은 이름도 일찍 꺾인다(「그러나 운 좋게 / 세리오스에게는」,
                # 마스터 10-10). 어절 개행은 런타임 훅(`vwf_wrapchk`)이 실제 이름 폭으로 한다.
                return kr
        return wrap(kr, self.dm, ml, rules=True)  # 줄·쪽 나눔 규칙은 전 영역(전투·시스템 포함 — 쪽 끝 한 어절 고아 2-16 ③, 마스터 10-31)


# ── 검사 ───────────────────────────────────────────────────────────────────────────────
def return_newlines(jp: str) -> frozenset[int]:
    """원판 조각에서 호출 복귀(`<RETURN>`) **뒤 첫 글자가 개행**인 복귀의 차례 — 우리 `<FE>` 차례와 같다.
    그 개행은 쪽 첫머리가 아니라 호출한 쪽 문장(사전 문장)에 이어지는 줄바꿈이다(마스터 10-30 — 원판 대조 조건으로만 예외)."""
    return frozenset(k for k, frag in enumerate(jp.split("<RETURN>")[1:]) if frag.startswith("\n"))


def expand(
    kr: str, vals: dict[str, str], dm: dict[str, str], ret_nl: frozenset[int] = frozenset()
) -> list[tuple[str, str]]:
    """번역문 → (글자, 묶음 표지) 열. 같은 표지의 이웃 사이에서 넘치면 ④. `ret_nl` = 원판도 복귀 뒤 개행으로 시작하는 `<FE>` 차례(쪽 나눔이 아니다)."""
    out: list[tuple[str, str]] = []
    unit = 0
    fe = -1
    for m in TOK.finditer(kr):
        s = m.group(0)
        if m.group(1) or m.group(2):
            unit += 1
            src = vals[m.group(1)] if m.group(1) else dm.get(m.group(2), "?")
            out += [(ch, f"u{unit}") for ch in src]
        elif m.group(3):
            prev = next((c for c, _u in reversed(out) if c.strip()), "")
            a, b = m.group(3).split("/")
            pick = a if prev and hook.has_batchim(prev) else b
            tag = out[-1][1] if out else "j"
            out += [(ch, tag) for ch in pick]
        elif s == "\n":
            out.append(("\n", ""))
        elif s.startswith("<"):
            if s == "<FE>":
                fe += 1
            if s in ("<EF>", "<FF>", "<FE>"):
                out.append(("\f", "RET" if s == "<FE>" and fe in ret_nl else ""))  # RET = 복귀 뒤 개행(호출 문장에 잇는 줄바꿈)
        else:
            out.append((s, ""))
    word, res = 0, []
    for ch, u in out:
        if ch in (" ", "\n", "\f"):
            word += 1
            res.append((ch, u))
        else:
            res.append((ch, u or f"w{word}"))
    return res


def newline_cursor(c: int) -> int:
    """개행 `$CF` 가 칸 번호 `$173B`(마지막으로 쓴 칸)를 옮기는 값 — `$02:DE53~DE6D` 를 8비트 그대로 옮겼다.

    `c // 17` 줄의 끝 칸으로 간다. 쪽 첫머리는 `$173B = $FF` 라 **15**(다음 글자가 첫 줄 16칸째)가 된다.
    """
    x, a = -1, c
    while True:
        x += 1
        if a - 17 < 0:
            break
        a -= 17
    a = 0
    for _ in range(x + 1):
        a += 17
    return (a - 1) & 0xFF


def layout_cells(chars: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """엔진처럼 흘린다 → (줄들, 위반 목록).

    칸 번호는 엔진과 같게 센다 — 글자는 +1(17칸째를 넘으면 기계적으로 다음 줄), 개행은 `newline_cursor`.
    ⇒ **꽉 찬 줄 뒤 개행은 빈 줄을 안 만들고**, 겹친 개행 `\\n\\n` 도 둘째가 아무 일도 안 한다(같은 끝 칸) —
    SFC 에선 개행으로 빈 줄을 **못** 만든다. 그래서 ② 는 「빈 줄을 의도했는데 화면엔 안 생기는」 자리와
    「쪽 첫머리 개행(다음 글자가 16칸째로 튄다)」을 잡는다.

    🔴 **마스터 최종 판정(2026-09-27④) — 엔진 훅(`hook.kinsoku_carry` · `h_kspace`/`hb_kspace`)이
    ①③을 실제로 막는다.** 이 시뮬레이션도 같은 규칙으로 움직인다: 줄 첫 칸이 될 공백은 칸을 안 쓰고
    버리고, 줄 첫 칸이 될 부호(`NO_HEAD`)는 **겹쳐 그리기 없이** 이전 줄 마지막 글자를 새 줄 첫 칸으로
    옮기고 부호는 그 다음 칸에 놓는다(이전 줄은 한 칸 짧아진 채 끝) — 값으로 확인: `hook.py` 의
    `kinsoku_carry` 라이브 트레이스, `r5-kinsoku-*.png`.
    """
    lines: list[list[tuple[str, str]]] = [[]]
    bad: list[str] = []
    c = 0xFF  # 쪽 첫머리(`$173B = $FF`)
    explicit = False  # 방금 줄이 개행으로 끝났나(기계적 넘침과 가른다)
    i = 0
    n = len(chars)
    while i < n:
        ch, u = chars[i]
        if ch == "\f":
            lines.append([])
            c, explicit = 0xFF, False
            i += 2 if u == "RET" and i + 1 < n and chars[i + 1][0] == "\n" else 1  # 복귀 뒤 개행은 쪽 첫머리 개행이 아니다
            continue
        if ch == "\n":
            if c == 0xFF:
                bad.append("② 쪽 첫머리 개행")
            elif i and chars[i - 1][0] == "\n":
                bad.append("② 빈 줄(겹친 개행 — 엔진은 무시한다)")
            c = newline_cursor(c)
            explicit = True
            i += 1
            continue
        nc = (c + 1) & 0xFF
        if nc == 4 * COLS:
            nc = 3 * COLS  # 68칸째면 한 줄 올리고 마지막 줄 첫 칸에 쓴다(`$DE79`→`$DE23`)
        col = nc % COLS
        if col == 0 and lines[-1]:
            if ch == " ":  # 훅: 줄 첫 칸 공백 — 칸을 안 쓰고 버린다(c 는 그대로)
                i += 1
                continue
            if ch in NO_HEAD:  # 훅: 이전 줄 마지막 글자를 새 줄 첫 칸으로, 부호는 다음 칸
                prev = lines[-1].pop()
                lines.append([prev])
                c2 = (nc + 1) & 0xFF
                if c2 == 4 * COLS:
                    c2 = 3 * COLS
                lines[-1].append((ch, u))  # 부호를 직접 놓는다 — col==0 재검사를 안 거친다
                c = c2
                i += 1
                continue
        c = nc
        if col == 0 and lines[-1]:
            prev_ch, prev_u = lines[-1][-1]
            lines.append([])
            if not explicit and prev_ch != " " and prev_u == u:
                bad.append("④ 묶음 끊김")
        while len(lines[-1]) < col:
            lines[-1].append((" ", ""))  # 쪽 첫머리 개행이 건너뛴 칸
        lines[-1].append((ch, u))
        explicit = False
        i += 1
    return ["".join(ch for ch, _u in ln) for ln in lines], bad


def layout_px(chars: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """훅(가변 폭)이 하는 대로 흘린다 → (줄들, 위반 목록).

    px 커서 `X` — 글자는 `pxw` 만큼 간다. 줄 번호는 `X // 136`(엔진은 17칸마다 줄을 넘긴다). 줄 끝에 걸치는 8px 글자는
    두 칸에 갈라져 그려지므로 ⑤. 개행은 줄을 마감하고 다음 줄 첫머리로 간다(꽉 찬 줄 뒤의 개행은 빈 줄을 안 만든다).
    줄 첫머리가 될 공백은 훅이 버린다(`vr_sp`) — 화면에 안 남고 위반도 아니다.
    """
    lines: list[list[tuple[str, str]]] = [[]]
    bad: list[str] = []
    X = 0  # 쪽 안 px 커서
    page_start = True
    explicit = False  # 방금 줄이 개행으로 끝났나(기계적 넘침과 가른다)
    i = 0
    n = len(chars)
    while i < n:
        ch, u = chars[i]
        if ch == "\f":
            lines.append([])
            X, page_start, explicit = 0, True, False
            i += 2 if u == "RET" and i + 1 < n and chars[i + 1][0] == "\n" else 1  # 복귀 뒤 개행은 쪽 첫머리 개행이 아니다
            continue
        if ch == "\n":
            if (
                page_start
            ):  # 쪽 첫머리 개행 — 엔진은 칸 번호를 $FF→15 로 보낸다: 다음 글자가 16칸째로 튄다
                bad.append("② 쪽 첫머리 개행")
                lines[-1] += [(" ", "")] * 16
                X = 128
            else:
                if i and chars[i - 1][0] == "\n":
                    bad.append("② 빈 줄(겹친 개행 — 엔진은 무시한다)")
                if X % LINE_PX:  # 줄 끝으로 — 꽉 찬 줄이면 그대로(빈 줄을 안 만든다)
                    X = ((X - 1) // LINE_PX + 1) * LINE_PX
                if lines[-1]:
                    lines.append([])
            explicit = True
            page_start = False
            i += 1
            continue
        w = pxw(ch)
        at_line_start = X % LINE_PX == 0
        if ch == " " and at_line_start:
            i += 1  # 훅: 줄 첫 칸 공백은 버린다
            continue
        if (
            at_line_start and X and not explicit and lines[-1]
        ):  # 기계적 넘침으로 새 줄 첫머리가 됐다
            prev_ch, prev_u = lines[-1][-1]
            lines.append([])
            if ch in NO_HEAD:
                bad.append("① 고아 부호")
            if prev_ch != " " and prev_u == u:
                bad.append("④ 묶음 끊김")
        elif (X % LINE_PX) + w > LINE_PX:
            bad.append("⑤ 줄 끝 걸침")
        lines[-1].append((ch, u))
        X += w
        explicit = False
        page_start = False
        i += 1
    return ["".join(ch for ch, _u in ln) for ln in lines], bad


def layout(chars: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """빌드 모드에 맞는 흘리기 — 가변 폭(기본, `ED_VWF=0` 이면 꺼짐)이면 px 모델, 아니면 옛 칸 모델(엔진 훅의 고아 부호 끌어오기 포함)."""
    return layout_px(chars) if VWF else layout_cells(chars)


def region(addr: int) -> str:
    if addr in FIELD:
        return "시스템(필드)"
    if BATTLE[0] <= addr <= BATTLE[1]:
        return "전투·시스템"
    return "씬"


def _units() -> list[dict]:
    """조각 목록(id·주소) — **원판 롬에서 바로** 뽑는다. 예전엔 untracked 파생물 `work/derived/units/segments.json` 을 읽어서
    그 파일이 낡거나 머신마다 다르면 조판 지문이 조용히 달랐다(10-24 — 동결 값이 옛 트리에서도 재현이 안 됐다)."""
    import units as _u

    rom = common.rom_bytes()
    items, _ = _u.extract(rom)
    return _u.segments(items, text.resolver(rom), _u.table_targets(rom))


_FF_TARGETS: dict[int, frozenset] | None = None


def _ff_targets() -> dict[int, frozenset]:
    """조각 주소 → 바로 뒤가 점프·분기 목표인 `<FF>` 의 차례. 원판 롬에서 한 번만 뽑는다(`_units` 와 같은 길)."""
    global _FF_TARGETS
    if _FF_TARGETS is None:
        _FF_TARGETS = {int(u["addr"], 16): frozenset(u["ff_targets"]) for u in _units() if u["ff_targets"]}
    return _FF_TARGETS


def targets() -> list[dict]:
    segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    units = _units()
    out = []
    for u in units:
        a = int(u["addr"], 16)
        e = segs.get(u["id"]) or {}
        if not e.get("kr") or CRAWL[0] <= a <= CRAWL[1]:
            continue
        out.append({"id": u["id"], "addr": a, "kr": e["kr"], "state": e.get("state"), "jp": u["jp"]})
    return out


def check_all(typeset: bool = True) -> list[dict]:
    dm = _dict()
    sets = {f: candidates(dm, field=f) for f in (False, True)}  # 조판기와 같은 후보로 잰다
    reps_by = {f: {k: representatives(v) for k, v in c.items()} for f, c in sets.items()}
    ml_by = {f: maxlens(c) for f, c in sets.items()}
    rep = []
    for s in targets():
        f = s["addr"] in FIELD
        reps, ml = reps_by[f], ml_by[f]
        # 마스터 최종 판정(2026-09-30, 전 기종 공통) — 로그성 메시지도 어절 단위 개행(빌드와 같은 경로).
        global PROTECT_FF
        PROTECT_FF = _ff_targets().get(s["addr"], frozenset()) if "<FF>" in s["kr"] else frozenset()  # 빌드(`Typesetter`)와 같게 — 점프 목표 `<FF>` 는 안 건드린다
        kr = wrap(s["kr"], dm, ml, rules=True) if typeset else s["kr"]
        if BATTLE[0] <= s["addr"] <= BATTLE[1] and kr.startswith("\n"):
            kr = kr[1:]  # 앞 조각에 이어 찍는 로그의 「새 줄에서 시작」 개행 — 이 검사는 조각을 따로 재서 쪽 첫머리로 오인한다(승리 로그 「ＥＰ n 포인트 획득」)
        toks = sorted(set(re.findall(r"\{(D[6-9A-F])\}", kr)))
        combos = [{}]
        for t in toks:
            combos = [dict(c, **{t: v}) for c in combos for v in reps[t]]
        accepted: set[str] = set()
        worst, worst_hard, n_bad, n_hard = None, None, 0, 0
        for c in combos:
            lines, bad = layout(expand(kr, c, dm, return_newlines(s["jp"])))
            if bad:
                n_bad += 1
                if worst is None:
                    worst = (lines, bad, c)
                if set(b[:1] for b in bad) - accepted:
                    n_hard += 1
                    if worst_hard is None:
                        worst_hard = (lines, bad, c)
        rep.append({**s, "region": region(s["addr"]), "combos": len(combos), "bad": n_bad,
                    "hard": n_hard, "worst": worst_hard or worst, "typeset": kr})  # fmt: skip
    return rep


def summary(rep: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for reg in ("시스템(필드)", "전투·시스템", "씬"):
        rs = [r for r in rep if r["region"] == reg]
        bad = [r for r in rs if r["bad"]]
        hard = [r for r in rs if r["hard"]]
        kinds = Counter(b[:1] for r in bad for b in set(r["worst"][1]))
        out[reg] = {"조각": len(rs), "위반": len(bad), "본질위반": len(hard),
                    "tm-draft": sum(r["state"] == "tm-draft" for r in hard),
                    "종류": dict(kinds)}  # fmt: skip
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="tm-draft 아닌 위반이 한 영역이라도 있으면 실패"
    )
    ap.add_argument("--raw", action="store_true", help="조판기를 안 거친 정본 그대로 검사(비교용)")
    ap.add_argument("--show", type=int, default=12, help="예를 몇 개 보일지")
    a = ap.parse_args()
    rep = check_all(typeset=not a.raw)
    for reg, s in summary(rep).items():
        hard = s["본질위반"] - s["tm-draft"]
        mark = "🔴" if hard else ("⚠" if s["위반"] else "✅")
        print(
            f"{mark} {reg}: 조각 {s['조각']} · 위반 {s['위반']}(본질 {s['본질위반']}·그중 tm-draft {s['tm-draft']}) {s['종류']}"
        )
    shown = 0
    for r in sorted(rep, key=lambda r: (r["region"] != "시스템(필드)", r["addr"])):
        if not r["bad"] or shown >= a.show:
            continue
        shown += 1
        lines, bad, c = r["worst"]
        print(f"  ${r['addr'] >> 16:02X}:{r['addr'] & 0xFFFF:04X} {r['id']} [{r['region']}] "
              f"{sorted(set(bad))} {c}")  # fmt: skip
        for ln in lines:
            print(f"      |{ln:<17}|")
    # 🔴 필드만 막으면 전투·씬이 되돌아가도 초록이다(2026-09-27① 전 세션 점검 — ss-ed1+2 에서 일본어가
    #   남은 빌드가 ✅ 로 끝났다). tm-draft 꼬리(P4 대사 라운드 몫)만 할 일로 두고 나머지는 전 영역에서 막는다.
    # 10-07 번복 뒤로는 FIELD 도 다른 영역과 똑같이 전부(①②③④) 막는다 — 예외가 없다.
    hard = [r for r in rep if r["hard"] and r["state"] != "tm-draft"]
    if a.check and hard:
        print(f"🔴 조판 위반 {len(hard)}건(tm-draft 제외) — 커밋 불가")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
