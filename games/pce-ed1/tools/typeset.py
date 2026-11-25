"""대사 조판 — 공용 krwrap 을 이 창 규격(status.md 3·4절)에 맞춰 부른다.

폭 13칸(글자 = 12px 한 칸 · **공백 = 반각 4px = 1/3 칸**, 마스터 10-07) · 한 창 3줄(화자가 행 0) · 페이지는 `05`
🔴 화자가 있으면 **첫 줄 ≤ 10칸** — 넘은 만큼 화자 이름이 밀린다(실측). 기전을 풀면 넓힌다.

칸 수 = `px // 12`(런타임 `$38BB` + `hook._entry_asm` 의 나머지)다. 줄은 칸이 13 에 닿으면 인터프리터가 스스로 넘긴다 —
그래서 **한 줄은 156px(13.0칸) 이하**로 짠다(그 안에선 칸이 13 에 닿는 건 마지막 글자뿐이라 계획한 줄 = 런타임 줄이다).
"""

import itertools
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

RULE_2_16 = os.environ.get("ED_LINEBREAK", "1") != "0"  # 줄·쪽 나눔 규칙(2-16) — 지표의 「전」 값을 재려고 끌 수 있다(제품 빌드는 늘 켠다)
RUNTIME_GUARD = True  # 런타임 줄넘김 모델과 다른 쪽을 다시 짠다(g) — 끄는 건 「고치기 전」 값을 재는 때뿐
PAGE_EDGE_PENALTY = 8  # 쪽 경계가 절 경계가 아니면 더하는 벌점(지표 i) — 둘째 단계(`polish`)에서만 켠다
_PEN = 0
REJECT_REGRESSION = True  # 퇴행(지표 f)을 만드는 이동을 거부한다 — 끄는 건 「거부 전」 값을 재는 때뿐
FULL = 13  # 칸이 이 수에 닿으면 인터프리터가 자동으로 넘긴다
WIDTH = 13.0001  # 칸 단위 폭(px/12) — 156px. 부동소수 오차를 위 한 눈금(4px = 1/3 칸)보다 훨씬 작게 얹는다
FIRST_WITH_SPEAKER = 10.0001
ON_FLOW = False  # 음성 자막(비모달 ON) 조판 중 — `on_flow()` 로만 켠다(대사창 OFF 와 첫 쪽 처리가 다르다)
LINES = 3
SPACE_PX = 4  # 대사창 공백은 반각(`font.HALF_SPACE`) — 12px 글자 사이에서 4px 만 간다
NARROW = (
    " " + font.NARROW_PUNCT
)  # 반각 폭(4px) — 공백과 반각 부호(`. , ! ?`, 렌더러가 12px 에 그린 뒤 8px 되감는다)


# ── 원문이 한 창인 문안을 한 창에 채우기(마스터 11-05 「자막은 OFF문안을 최대한 따르기」) ──────────────────
# 2-10(문장마다 새 줄)을 지키면 「그래.」 한 줄 + 나머지 세 줄로 창이 둘이 된다 — 원문(한 창)과 같게 짧은 문장을 다음 문장과 한 줄에 붙여 한 창에 채운다.
# 대상은 `script/typeset_fit_one.json` 의 문안(`tools/fit_one_scan.py --write` 가 만든다 — 원문 1창·우리 2창+ 이고 풀면 한 창에 드는 것만).
FIT_ONE: set[str] | None = None  # None = 파일에서 읽는다(검사 도구는 빈 집합으로 덮어 「풀기 없음」 기준을 잰다)


def _fit_one_texts() -> set[str]:
    global FIT_ONE
    if FIT_ONE is None:
        import json

        import common

        f = common.GAME_DIR / "script" / "typeset_fit_one.json"
        FIT_ONE = set(json.loads(f.read_text("utf-8")).get("texts", [])) if f.exists() else set()
    return FIT_ONE


def fit_one_pages(text: str, *, speaker: bool) -> list[str] | None:
    """문장 단위 새 줄을 풀고 한 창(화자 창 3줄·첫 줄 10칸 / 화자 없는 창 4줄)에 채운 줄 목록. 안 들어가면 None."""
    cap = LINES if speaker else 4
    chunk = " ".join(text.split("\n"))
    if any(w.startswith("…") and len(w) > 1 and w[1].isalnum() for w in chunk.split(" ")[1:]):
        return None  # 문장 첫머리 「…난처하군」 이 앞 문장 뒤에 붙으면 2-11(… 뒤 공백) 위반 꼴이 된다 — 풀지 않는다
    first = FULL * 12 if speaker in ("nl", "nl=") or not speaker else FIRST_WITH_SPEAKER * 12
    # 첫 줄 끊는 자리를 후보로 모두 해 본다(첫 줄 폭이 다르다) — 나머지는 공용 조판기(줄 수 제한). 이음 갈림(`_bonded_breaks`)이 적은 안, 같으면 첫 줄이 긴 안
    words = chunk.split(" ")
    best = None
    for i in range(1, len(words) + 1):
        line = " ".join(words[:i])
        if px(line) > first:
            break
        rest = " ".join(words[i:])
        lines = [line] if not rest else [line, *krwrap.wrap(rest, WIDTH, cell_width=cell, max_lines=cap - 1)]
        if len(lines) > cap or any(px(x) > FULL * 12 for x in lines) or ink("".join(lines)) != ink(chunk):
            continue
        if not runtime_ok(lines):  # 런타임이 실제로 나눌 줄과 같아야 한다(지표 g)
            continue
        key = (_bonded_breaks(lines), -i)
        if best is None or key < best[0]:
            best = (key, lines)
    return best[1] if best else None


class Card(list):
    """장 끝 카드 쪽 — 줄을 그대로(빈 줄·앞 공백 포함) 내는 쪽. 일반 쪽은 그냥 list."""


KAGI = font.KAGI  # 「」 — 8px 전진(마스터 도안 D판 10-26). 게임 안 값이다 — 공용 krwrap 기본값은 안 건드린다


NUMCH = "\uE0F1"  # 인터프리터가 찍는 수치(`1F 22 04` 등)의 한 자리 — 반각 8px(11-04 마스터 캡처 실측: 「16포인트」 마침표가 틀 칸으로 나감). 검사기 전용 자리표시

def adv(ch: str) -> int:
    """글자 하나의 전진 px — 공백·반각 부호 4 · 「」·수치 자리 8 · 나머지 12."""
    return SPACE_PX if ch in NARROW or ch == TIE else 8 if ch in KAGI or ch == NUMCH or ch == "?" else 12


def cell(ch: str) -> float:
    return adv(ch) / 12


def px(line: str) -> int:
    """줄 폭(px) — 글자 12 · 공백·반각 부호 4 · 「」 8."""
    return sum(adv(c) for c in line)


def cols(line: str) -> int:
    """줄이 닿은 칸 수(`px // 12`) — 13 이면 인터프리터가 스스로 넘긴다(그 뒤 명시 줄바꿈은 빈 줄)."""
    return px(line) // 12


REFINE = os.environ.get("ED_REFINE", "0") == "1"  # 11-23 줄 나눔 보정(문장 끝 우선 · 더듬는 반복 묶음) — 끄는 건 「전」 값을 재는 때뿐
_SENT_END_RX = re.compile(r"[.!?…~]+$|[.!?]」$")


def _early_breaks(pg: list[str]) -> int:
    """문장이 아직 안 끝난 줄 끝(다음 줄에서 이어짐)인데 그 문장의 끝까지가 이 줄에 들어갔을 자리 수 — 마스터 11-23 「정말 도움이 / 됐어.」(문장 끝 우선)."""
    n = 0
    for i in range(len(pg) - 1):
        a = pg[i]
        if _SENT_END_RX.search(a):
            continue
        acc = a
        for w in " ".join(pg[i + 1 :]).split(" "):
            acc += " " + w
            if _SENT_END_RX.search(w):
                if px(acc) <= FULL * 12:
                    n += 1
                break
    return n


def _stutters(pg: list[str]) -> int:
    """더듬는 반복(「빛, / 빛의」 · 「이, / 이건」)이 줄 사이에서 갈린 수 — 줄 끝 「X,」 + 다음 줄 머리가 X 로 시작(마스터 11-23)."""
    n = 0
    for a, b in itertools.pairwise(pg):
        w = a.rsplit(" ", 1)[-1]
        if len(w) >= 2 and w.endswith(",") and b.startswith(w[:-1]) and not b.startswith(w):
            n += 1
        elif len(w) >= 2 and w.endswith(",") and b[:1] == w[:1] and len(w) <= 3:
            n += 1
    return n


def _refine(pg: list[str], first_speaker: bool) -> list[str]:
    """문장 끝 우선 + 더듬는 반복 묶음 — 줄 수가 늘지 않고 공용 점수(`_score`)가 나빠지지 않을 때만 받는다."""
    best = list(pg)
    base = _score([best], first_speaker)
    if base is None:
        return pg
    for _ in range(3):
        cands = []
        # (가) 문장 끝까지 한 줄에 — 줄 i 에 뒤 낱말을 끌어올리고 나머지는 이어 채운다
        for i in range(len(best) - 1):
            a = best[i]
            if _SENT_END_RX.search(a):
                continue
            words = " ".join(best[i + 1 :]).split(" ")
            acc = a
            take = 0
            for w in words:
                acc += " " + w
                take += 1
                if _SENT_END_RX.search(w):
                    break
            else:
                continue
            if px(acc) > (round(FIRST_WITH_SPEAKER * 12) if (first_speaker and i == 0) else FULL * 12):
                continue
            rest = words[take:]
            tail = []
            if rest:
                for pgx in polish(_wrap_chunk(" ".join(rest), False, WIDTH, FIRST_WITH_SPEAKER), False):
                    tail += pgx
            cands.append(best[:i] + [acc] + tail)
        # (나) 더듬는 반복 — 「X,」 를 다음 줄로 내리거나 다음 줄 첫 낱말을 올린다
        for i in range(len(best) - 1):
            w = best[i].rsplit(" ", 1)[-1]
            if len(w) >= 2 and w.endswith(",") and best[i + 1][:1] == w[:1]:
                head = best[i][: -len(w)].rstrip()
                if head:
                    cands.append(best[:i] + [head, w + " " + best[i + 1]] + best[i + 2 :])
                nw = best[i + 1].split(" ", 1)
                rest = nw[1] if len(nw) > 1 else ""
                cands.append(best[:i] + [best[i] + " " + nw[0]] + ([rest] if rest else []) + best[i + 2 :])
        nxt = None
        cur = (_early_breaks(best), _stutters(best))
        for c in cands:
            if len(c) > len(best) or any(not ln for ln in c):
                continue
            sc = _score([c], first_speaker)
            if sc is None or sc > base:
                continue
            f = (_early_breaks(c), _stutters(c))
            if f < cur and (nxt is None or (f, sc) < nxt[0]):
                nxt = ((f, sc), c)
        if nxt is None:
            break
        best, base = nxt[1], nxt[0][1]
    return best


MANUAL = None  # 마스터가 줄 나눔을 직접 정한 쪽 — {쪽 평문(줄을 공백으로 이은 것): [줄…]} (`script/manual_lines.json`)


def _manual_lines() -> dict[str, list[str]]:
    global MANUAL
    if MANUAL is None:
        import json

        import common

        f = common.GAME_DIR / "script" / "manual_lines.json"
        MANUAL = {" ".join(pg): pg for pg in json.loads(f.read_text("utf-8")).get("pages", [])} if f.exists() else {}
    return MANUAL


TIE = "\uE0F2"  # 「1500만 Gold」 사이 공백 자리표시 — 어절 안(줄바꿈 후보 아님)이고 폭은 공백(4px). 조판이 끝나면 보통 공백으로 되돌린다(`pages`)
_TIE_RX = re.compile(r"([0-9][만천억]?) (Gold)")


_NAME_RX = None


def _name_rx():
    """공백 든 고유명사(`script/tie_names.json` — 정본 공백 이름 + 대사에서 띄어 쓰인 꼴 + 울프 빌) 한 정규식(긴 이름부터, 마스터 11-25)."""
    global _NAME_RX
    if _NAME_RX is None:
        import json

        f = Path(__file__).resolve().parent.parent / "script" / "tie_names.json"
        names = sorted(json.loads(f.read_text("utf-8"))["names"], key=lambda n: (-len(n), n)) if f.exists() else []
        _NAME_RX = re.compile("|".join(re.escape(n) for n in names)) if names else re.compile(r"(?!x)x")
    return _NAME_RX


def _tie(text: str) -> str:
    """금액 숫자와 단위 Gold 는 한 덩이(마스터 11-22 「1000만 Gold」 한 줄) · **공백 든 고유명사**는 한 낱말(11-25 「울프 빌」) — 사이 공백을 `TIE` 로 바꿔 조판기가 줄 사이에서 못 가르게 한다."""
    text = _TIE_RX.sub(lambda m: m.group(1) + TIE + m.group(2), text)
    for _ in range(2):  # 겹치는 이름(「대도 게일」+「게일 3세」)은 둘째 판에서 마저 묶는다
        text = _name_rx().sub(lambda m: m.group(0).replace(" ", TIE), text)
    return text


def pages(text: str, *, speaker: bool | str, lead_px: int = 0, _bounds: list | None = None, four: bool = False, keep_windows: bool = False) -> list[list[str]]:
    """조판 결과에서 마스터가 줄 나눔을 직접 정한 쪽(`script/manual_lines.json`, 11-23 씬 168 s2 #6·#11 「개행 수정」)만 그 줄로 바꾼다 — 쪽 평문이 같고 줄이 폭에 들 때만.
    음성 자막(ON)과 대사창(OFF)이 같은 함수를 쓰므로 같은 줄 나눔이 반영된다. 첫 줄은 화자 곁(`speaker is True`)이면 10칸, 아니면 13칸."""
    out = _pages_outer(_tie(text), speaker=speaker, lead_px=lead_px, _bounds=_bounds, four=four, keep_windows=keep_windows)
    out = [pg if isinstance(pg, Card) else [x.replace(TIE, " ") for x in pg] for pg in out]
    if REFINE and not lead_px:
        out = [_refine(pg, speaker is True and i == 0) if not isinstance(pg, Card) and len(pg) >= 2 else pg for i, pg in enumerate(out)]
    man = _manual_lines()
    if not man or lead_px:
        return out
    # 🔴 자연 조판이 쪽을 둘 이상으로 가른 문안을 마스터가 한 쪽으로 나눈 경우(11-25 씬 203 랄프 「울프 빌」 3줄=1쪽) — 이어진 쪽들의 평문이 마스터 쪽과 같으면 그 쪽들을 마스터 줄 하나로 합친다
    # (원문 창 수와 맞추는 방향이라 창 수 계약을 깨지 않는다 — 계약 씬은 `check_window_count` 가 원문 창 수 이상인지 본다)
    for i in range(len(out)):
        for j in range(i + 2, min(len(out), i + 3) + 1):
            span = out[i:j]
            if any(isinstance(x, Card) for x in span):
                continue
            hand = man.get(" ".join(" ".join(x) for x in span))
            if hand is not None and len(hand) <= LINES and all(px(x) <= FULL * 12 for x in hand) and not (i == 0 and speaker is True and px(hand[0]) > FIRST_WITH_SPEAKER * 12):
                out = [*out[:i], list(hand), *out[j:]]
                break
        else:
            continue
        break
    res = []
    for i, pg in enumerate(out):
        flat = " ".join(pg) if not isinstance(pg, Card) else None
        hand = man.get(flat) if flat is not None else None
        if flat is not None and hand is None:  # 대사창(OFF)은 앞 문장 한 줄이 같은 쪽에 붙는다(「자, 수다는 여기까지다.」 + 마스터 쪽) — 앞이 한 줄에 들면 앞 줄 + 마스터 줄
            for k, v in man.items():
                if flat.endswith(" " + k) and px(flat[: -len(k) - 1]) <= FULL * 12 and len(v) + 1 <= LINES + (1 if four else 0) and (i > 0 or not speaker):
                    hand = [flat[: -len(k) - 1], *v]
                    break
        if hand is not None and len(hand) <= (LINES if (i == 0 and speaker) else LINES + (1 if four else 0)) and all(px(x) <= FULL * 12 for x in hand) and not (i == 0 and speaker is True and px(hand[0]) > FIRST_WITH_SPEAKER * 12):
            pg = list(hand)
        res.append(pg)
    return res


def _pages_outer(text: str, *, speaker: bool | str, lead_px: int = 0, _bounds: list | None = None, four: bool = False, keep_windows: bool = False) -> list[list[str]]:
    """`speaker == "nl"` — 화자 머리 바로 뒤 개행(`01`)으로 글이 **둘째 줄부터** 시작하는 창(이름이 윗줄): 첫 글 줄도 13칸이다(엔진 규칙, 마스터 11-05 씬 41 줄 나눔·관리자 「일반 규칙으로」).
    머리 뒤에 글이 바로 이어지는 창(`True`)은 이름 곁이라 첫 줄 10칸. `messages.speaker_kind(m)` 이 둘을 가른다."""
    global FIRST_WITH_SPEAKER, FULL_LINE_NL
    if keep_windows and FULL_LINE_NL:  # 쪽 수가 구조 계약인 씬(`contract_scenes`) — 13칸 줄 허용으로 창 수가 달라지면 종전(13칸 줄 회피) 조판
        b_new: list = []
        new = pages(text, speaker=speaker, lead_px=lead_px, _bounds=b_new, four=four)
        FULL_LINE_NL = False
        try:
            b_old: list = []
            old = pages(text, speaker=speaker, lead_px=lead_px, _bounds=b_old, four=four)
        finally:
            FULL_LINE_NL = True
        res, bb = (new, b_new) if len(new) == len(old) else (old, b_old)
        if _bounds is not None:
            _bounds.extend(bb)
        return res
    if speaker in ("nl", "nl="):
        old_first = FIRST_WITH_SPEAKER
        FIRST_WITH_SPEAKER = WIDTH
        try:
            b13: list = []
            res = _pages_main(text, speaker=True, lead_px=lead_px, _bounds=b13, four=four)
        finally:
            FIRST_WITH_SPEAKER = old_first
        b10: list = []
        old = _pages_main(text, speaker=True, lead_px=lead_px, _bounds=b10, four=four)
        if len(res) > len(old) or (speaker == "nl=" and len(res) != len(old)):  # 첫 줄을 넓혔더니 창이 늘면 종전(10칸) 조판 — 원문 창 수를 늘리지 않는다. 쪽 수가 계약인 씬(`"nl="`)은 창 수가 달라져도 안 된다
            res, b13 = old, b10
        if _bounds is not None:
            _bounds.extend(b13)
        return res
    return _pages_main(text, speaker=speaker, lead_px=lead_px, _bounds=_bounds, four=four)


def _pages_main(text: str, *, speaker: bool, lead_px: int = 0, _bounds: list | None = None, four: bool = False) -> list[list[str]]:
    """`four` 는 씬 대사 조판만 켠다(시스템·전투 문구는 종전 3줄). 화자 없는 창은 4줄, 화자 창은 둘째 쪽부터 4줄 —
    원판이 그렇게 쓴다(짝 표: 화자 없는 4줄 쪽 893 · 화자 창 이어지는 4줄 쪽 571 · 화자 창 첫 쪽 4줄 0).
    🔴 화자 창 첫 쪽에 4줄을 넣으면 이름 줄이 창 밖으로 밀려 **이름이 안 보인다**(시험 롬 실측 10-29) — 그래서 3줄까지."""
    if not four:
        return _pages(text, speaker=speaker, lead_px=lead_px, _bounds=_bounds)
    global LINES
    old = LINES
    LINES = 4
    try:
        b4: list[int] = []
        pg = _pages(text, speaker=speaker, lead_px=lead_px, _bounds=b4)
    finally:
        LINES = old
    if speaker and pg and len(pg[0]) > old and ON_FLOW:  # 🔴 음성 자막(비모달)은 종전 그대로 — 마스터 11-11 「호흡에 맞춰 나누는 것도 나쁘지 않다」(쪽 나눔·시각표 바이트 불변)
        return _pages(text, speaker=speaker, lead_px=lead_px, _bounds=_bounds)
    if speaker and pg and len(pg[0]) > old:  # 화자 창의 첫 쪽은 이름 줄이 행 0 이라 3줄까지 — 넘으면 첫 조각(화자 쪽)만 3줄로 되돌린다
        b3: list[int] = []
        pg3 = _pages(text, speaker=speaker, lead_px=lead_px, _bounds=b3)
        if len(b4) > 1 and len(b3) > 1:  # 강제 쪽(`\f`) 조각이 여럿 — 화자가 있는 첫 조각만 3줄로 되돌리고 둘째 조각부터는 4줄 조판을 그대로 둔다(둘째 창부터는 화자 줄이 없다)
            res = pg3[: b3[1]] + pg[b4[1] :]
            if _bounds is not None:
                _bounds.extend([*b3[:1], *(x - b4[1] + b3[1] for x in b4[1:])])
            return res
        if _bounds is not None:
            _bounds.extend(b3)
        return pg3
    if _bounds is not None:
        _bounds.extend(b4)
    return pg


def _pages(text: str, *, speaker: bool, lead_px: int = 0, _bounds: list | None = None) -> list[list[str]]:
    """문안 → [[줄…], …]. `\\n` 은 하드 개행, `\\f` 는 강제 페이지.

    `lead_px` — 이 메시지가 **앞 메시지가 찍던 줄 끝에 이어 붙을 때** 그 줄이 이미 쓴 폭(px). 첫 줄은 남은 폭에 맞춰 짜고, 첫 낱말이 안 들어가면 첫 줄을 빈 줄('' = 명시 개행)로 둬
    본문 첫머리에서 줄을 넘긴다(씬 64 「세리/오스」 — 런타임 어절 검사는 앞 메시지가 쓴 폭을 몰라 낱말 가운데서 글자 단위로 끊는다).
    """
    out: list[list[str]] = []
    first_chunk = True
    if not lead_px and text in _fit_one_texts() and (text.rstrip("\f") == text or text.strip("\f").count("\f") == 0):  # 원문이 한 창인 문안 — 문장 단위 새 줄을 풀어 한 창에(위 FIT_ONE). `\f` 로 갈라 쓴 한 창 문안은 이어서 짠다
        one = fit_one_pages(text.replace("\f", " ").strip(), speaker=speaker)
        if one is not None:
            if _bounds is not None:
                _bounds.append(0)
            return [one]
    for chunk in text.split("\f"):
        if _bounds is not None:
            _bounds.append(len(out))  # 강제 쪽(`\f`) 조각이 시작하는 쪽 색인 — 지표가 조각 단위로 쪽 끝을 본다
        orig = chunk
        if not (first_chunk and lead_px) and "\f" in text and chunk in _fit_one_texts():  # `\f` 로 나뉜 문안의 한 쪽 조각 — 원문 쪽과 1:1 이면 그 쪽만 풀어 한 창에(위 FIT_ONE)
            one = fit_one_pages(chunk, speaker=speaker)
            if one is not None:
                first_chunk = False
                out.append(one)
                speaker = False
                continue
        chunk, header = soften_chunk(chunk)
        if first_chunk and lead_px and "\n" not in chunk:
            first_chunk = False
            out.extend(_pages_after_lead(chunk, lead_px))
            speaker = False
            continue
        first_chunk = False
        if header is not None:
            # 이름 머리(「착해 보이는 할머니」) 한 줄 + 본문 — 본문은 조판기가 두 줄 안에 짠다(안 들어가면 번역 줄 그대로 둔다)
            body = _wrap_chunk(chunk.split("\n", 1)[1], False, WIDTH, FIRST_WITH_SPEAKER)
            if len(body) == 1 and len(body[0]) <= LINES - 1:
                out.append([header] + body[0])
                speaker = False
                continue
            chunk, header = orig, None
        if "\n" in chunk and not speaker:
            # 🔴 **하드 개행이 든 창은 줄을 그대로 둔다**(빈 줄·앞 공백 포함) — krwrap 은
            #    protect_hard 여도 빈 줄과 줄머리 공백을 지워 장 끝 「완」 카드가 「…여행 완」 한 줄로
            #    붙었다(2026-09-24, 여섯 장 모두). 원문도 전각 공백으로 가운데를 맞춘 카드다.
            #    정본에서 `\n` 을 쓰는 건 그 카드뿐이라 대사 조판은 안 바뀐다.
            lines = chunk.split("\n")
            # ⚠ 창은 세 줄이다. 그리고 **빈 줄은 전각 공백 하나를 넣어 적는다** — 개행(`01`)은 「다음 글자 전에
            #   줄 바꿈」 표시라 둘을 잇달아 써도 한 줄만 넘어간다(종장 카드 화면 2026-09-25)
            #   줄 폭은 **px 로** 잰다(전각 공백 12px · ASCII 공백 4px) — 칸 수(글자 수)로 재면 반 칸 공백으로 가운데를 맞춘 카드가 막힌다
            assert len(lines) <= LINES and all(px(x) <= FULL * 12 for x in lines), chunk
            # 장 끝 카드는 빈 줄·앞 공백이 든다 → 개행을 그대로 낸다(`Card`). 그 밖은 정본이 줄을 직접 짠 **줄 계획**(띄어 쓴 아이템 이름을
            # 줄 사이에서 안 갈리게)이라 일반 줄처럼 다룬다 — 꽉 찬 줄 뒤엔 개행을 안 낸다(`translate`).
            card = any(not x or x[0] in " \u3000" for x in lines)
            out.append(Card(lines) if card else lines)
            speaker = False
            continue
        if "\n" in chunk and speaker:
            # 🔴 **화자 창의 하드 개행은 의도적 줄 지정이다**(재검 11, 10-21 — 「길모아의 / 별이라는 건가?」처럼 띄어 쓴 아이템 이름이
            #    줄 사이에서 갈릴 때 정본에서 `\n` 으로 이름 뒤에서 끊는다). krwrap 의 균형 짜기가 지워 버리므로 줄을 그대로 둔다 —
            #    첫 줄은 화자 이름 곁이라 10칸, 나머지는 13칸, 창은 세 줄.
            lines = chunk.split("\n")
            if len(lines) <= LINES and px(lines[0]) <= FIRST_WITH_SPEAKER * 12 and all(px(x) <= FULL * 12 for x in lines[1:]):
                out.append(lines)
                speaker = False
                continue
            # 줄 계획이 창에 안 맞으면(편집기가 여러 메시지를 `\n` 으로 이어 보여 줄 때 등) 종전대로 조판기에 맡긴다.
        pg = _wrap_chunk(chunk, speaker, WIDTH, FIRST_WITH_SPEAKER)
        if _fused_boundary(pg) or (RUNTIME_GUARD and not all(runtime_ok(p) for p in pg)):
            # 🔴 **줄 끝이 반각 부호로 칸 13 에 딱 닿은 줄 뒤에 다음 줄이 이어지면**(우리는 개행·공백을 안 낸다 — 인터프리터가 스스로 넘기므로) 런타임 어절 검사(`wordck`)가
            #    「부호.다음줄첫말」을 **공백 없는 한 어절**로 보고 통째로 아랫줄로 내려 계획과 다른 줄이 된다(「구원받았습니다.감사드립니다.」「하던데,당신들도」 — 마스터 qa 10-22).
            #    반 칸 좁혀 다시 짠다 — 그러면 그 줄은 칸 12 라 명시 개행이 나가고 어절이 안 붙는다.
            pg = _wrap_chunk(chunk, speaker, WIDTH - 0.5, FIRST_WITH_SPEAKER - 0.5)
        pre = pg
        pg = polish(pg, speaker)
        if REJECT_REGRESSION and regressions(pre, pg):
            pg = pre  # 마지막 안전망 — 다듬은 쪽에 새 나쁜 끊김이 하나라도 있으면 공용 조판 그대로(이동 거부가 놓친 것)
        if orig != chunk and header is None and _bonded_breaks(_flat(pg)) >= 1:
            # 손 개행을 공백으로 읽어 다시 짠 결과에 이음 갈림이 남으면(첫 줄이 짧은 화자 창 등) 번역 줄이 그보다 낫거나 같을 때 번역 줄을 둔다 —
            # 규칙이 갈림을 다른 곳으로 옮기기만 하는 퇴행을 막는다(「별이라는⏎건가?」→「길모아의⏎별이라는 건가?」)
            hand = orig.split("\n")
            if len(hand) <= LINES and all(px(x) <= _limit(0, i, speaker) for i, x in enumerate(hand)) and _bonded_breaks(hand) <= _bonded_breaks(_flat(pg)):
                pg = [hand]
        out.extend(pg)
        speaker = False  # 둘째 창부터는 화자 줄이 없다
    for p in out:
        for line in p:
            assert px(line) <= FULL * 12, (line, px(line))
    # 🔴 **글 소실 없음** — 조판 전후 글자(공백·개행·페이지 제외)가 같아야 한다. 폭·위반만 보는 검사는 꼬리 글이
    #    조용히 사라지는 결함을 못 잡는다(PS1·ps1-ed3+4 실측, 관리자 공유 2026-09-27).
    assert ink(text) == ink("".join(l for p in out for l in p)), ("조판이 글을 잃었다", text)
    return out


_SCENE: int | None = None
_CONTRACT: set[int] | None = None


def set_scene(sid: int | None) -> None:
    """지금 조판하는 씬 번호 — `grow_allowed()` 가 본다. 안 정하면(None) 쪽을 늘리지 않는다(음성·게이트 소비자는 늘 그쪽)."""
    global _SCENE
    _SCENE = sid


def keep_windows(sid: int | None) -> bool:
    """이 씬은 대사 창 수를 바꾸면 안 되나(음성 시각표·게이트 구조 계약)."""
    return sid is not None and sid in contract_scenes()


def contract_scenes() -> set[int]:
    """쪽 수가 구조 계약인 씬 — 나레이션 게이트(`narration_gates.SITES`)와 음성 시각표·창(voice_sched(초안 포함)·voice_gwin)이 걸린 씬.
    그 씬의 메시지는 쪽마다 음성 시각·게이트 대기 프레임이 묶여 쪽 수가 바뀌면 싱크·이벤트가 어긋난다."""
    global _CONTRACT
    if _CONTRACT is None:
        import json

        import common
        import narration_gates

        sc = set(narration_gates.SITES)
        for name in ("voice_sched", "voice_gwin"):
            f = common.GAME_DIR / "script" / f"{name}.json"
            if f.exists():
                for k, v in json.loads(f.read_text("utf-8")).get("scenes", {}).items():
                    segs = v if isinstance(v, list) else [v]
                    if any(seg.get("draft") for seg in segs):  # 초안(`draft`, 11-01 voice_draft)은 계약이 아니다 — 제품에 안 들고, 쪽이 갈리면 초안을 다시 만든다
                        continue
                    sc.add(int(k))
        _CONTRACT = sc
    return _CONTRACT


def grow_allowed() -> bool:
    """이 씬은 대사 쪽을 늘려도 되나 — 음성·게이트와 무관한 일반 대사창만(쪽은 `05` 한 바이트 + 창 한 번 더 열기)."""
    return RULE_2_16 and _SCENE is not None and _SCENE not in contract_scenes()


def _limit(pi: int, li: int, speaker: bool) -> int:
    return round(FIRST_WITH_SPEAKER * 12) if (speaker and pi == 0 and li == 0) else FULL * 12


def _score(pg: list[list[str]], speaker: bool) -> int | None:
    """후처리 후보의 벌점(낮을수록 좋다). 하드 위반(줄 폭 초과·빈 줄·반각 부호 붙음)이면 None.
    지표 a/b/d/e 와 같은 판정(위 부품)에 이음 검사(본용언+보조용언 등이 줄 사이에서 갈림)·짧게 남은 줄을 더한다."""
    flat: list[str] = []
    for pi, p in enumerate(pg):
        for li, ln in enumerate(p):
            if not ln or px(ln) > _limit(pi, li, speaker):
                return None
            flat.append(ln)
    if _fused_boundary(pg) or (RUNTIME_GUARD and not all(runtime_ok(p) for p in pg)):
        return None
    sc = 4 * clause_splits(flat) + 4 * glued_splits(flat)
    for a, b in itertools.pairwise(flat):
        wa, wb = a.rsplit(" ", 1)[-1], b.split(" ", 1)[0]
        if not ends_sentence(a) and _bonded(wa, wb):
            sc += 6
    for pi, p in enumerate(pg):
        last = p[-1]
        one = " " not in last
        if pi < len(pg) - 1 and not ends_sentence(last) and not page_edge_ok(last.rsplit(" ", 1)[-1], pg[pi + 1][0].split(" ", 1)[0]):
            sc += _PEN  # 지표 i — 문장 끝·절 경계가 아닌 곳에서 쪽이 끊김(2-16)
        if pi < len(pg) - 1 and not ends_sentence(last):
            sc += 8  # 쪽 사이에서 문장이 갈림 — 공용 조판기는 문장 단위로 쪽을 짠다. 줄 옮기기가 새로 만들지 못하게 무겁게 센다
        if pi < len(pg) - 1 and one and not ends_sentence(last):
            sc += 5  # b — 문장 중간 한 낱말로 끝나는 쪽
        if pi == len(pg) - 1 and len(pg) > 1 and len(p) == 1 and one:
            sc += 5  # a/h — 마지막 창에 한 어절만 남음(앞 창이 문장 끝이어도 새로 만들지 않는다 — 있던 것은 벌점이 같아 안 건드린다)
    for pi in range(len(pg) - 1):
        if not ends_sentence(pg[pi][-1]):  # 같은 문장이 이어지는 창끼리 줄 수가 골고루(차 ≤ 1) — 지표 h2
            sc += 3 * max(0, abs(len(pg[pi]) - len(pg[pi + 1])) - 1)
    sc += 2 * sum(1 for ln in flat[:-1] if px(ln) < MIN_LEFT_PX)
    return sc + 3 * len(pg) + len(flat)  # 쪽 하나 3점 · 줄 하나 1점 — 짧은 꼬리를 괜히 두 줄로 쪼개는 후보는 받지 않는다  # 쪽 하나는 3점 — 쪽을 늘리는 후보는 그만큼 이득이 있어야 받는다


def _guard(pg: list[list[str]]) -> tuple[int, int, int, int, int, int]:
    """지표 a/h · e · h2 · 한 줄 한 어절 꼬리 — 후처리 후보가 **새로 키우지 못하게** 하는 값(쪽 경계 이동이 다른 지표를 올리는 것을 막는다)."""
    flat = [ln for p in pg for ln in p]
    tail = int(len(pg) > 1 and len(pg[-1]) == 1 and " " not in pg[-1][0] and not ends_sentence(pg[-2][-1]))
    uneven = int(any(not ends_sentence(x[-1]) and abs(len(x) - len(y)) >= 2 for x, y in itertools.pairwise(pg) if x and y))
    oneword = sum(1 for p in pg[:-1] if p and " " not in p[-1] and not ends_sentence(p[-1]))  # 지표 b
    thin = sum(1 for p in pg[:-1] if len(p) == 1 and not ends_sentence(p[-1]))  # 문장 중간인데 한 줄뿐인 쪽(쪽을 거의 비우는 이동 금지)
    return (tail, glued_splits(flat), uneven, clause_splits(flat), oneword, thin)


def _locate(P: list[list[list[str]]]) -> list[tuple[int, int]]:
    return [(pi, li) for pi, p in enumerate(P) for li in range(len(p))]


def _join(P: list[list[list[str]]]) -> list[list[str]]:
    return [[" ".join(w) for w in p] for p in P]


def _move_tail(pg: list[list[str]], pi: int, li: int, k: int, speaker: bool) -> list[list[str]] | None:
    """줄 (pi, li) 의 끝 낱말 k 개를 다음 줄 앞으로 내린다(줄 전체면 그 줄이 없어진다). 넘치면 그 줄 끝 낱말을 다시 아래로 — 마지막 줄까지 가면 마지막 쪽에 줄을 더한다(쪽당 3줄 이내)."""
    P = [[ln.split(" ") for ln in p] for p in pg]
    line = P[pi][li]
    if k > len(line) or (pi, li) == _locate(P)[-1] and k == len(line):
        return None
    carry, rest = line[-k:], line[:-k]
    if rest:
        P[pi][li] = rest
        start = _locate(P).index((pi, li)) + 1
    else:
        del P[pi][li]
        if not P[pi]:
            return None
        start = _locate(P).index((pi, li)) if li < len(P[pi]) else None
        if start is None:
            start = _locate(P).index((pi, li - 1)) + 1
    locs = _locate(P)
    for n in range(start, len(locs)):
        qi, qj = locs[n]
        P[qi][qj] = carry + P[qi][qj]
        lim = _limit(qi, qj, speaker)
        carry = []
        while px(" ".join(P[qi][qj])) > lim and len(P[qi][qj]) > 1:
            carry.insert(0, P[qi][qj].pop())
        if not carry:
            break
    if carry:
        if len(P[-1]) >= LINES:
            if not grow_allowed():
                return None
            P.append([carry])  # 쪽 하나 더 — 계약 없는 씬에서만
        else:
            P[-1].append(carry)
    return _join(P)


def _move_head(pg: list[list[str]], pi: int, li: int, k: int, speaker: bool) -> list[list[str]] | None:
    """줄 (pi, li) 의 앞 낱말 k 개를 앞 줄 끝으로 올린다(줄 전체면 그 줄이 없어진다). 앞 줄이 폭을 넘으면 `_score` 가 거른다."""
    P = [[ln.split(" ") for ln in p] for p in pg]
    locs = _locate(P)
    n = locs.index((pi, li))
    if n == 0 or k > len(P[pi][li]):
        return None
    qi, qj = locs[n - 1]
    P[qi][qj] = P[qi][qj] + P[pi][li][:k]
    if k == len(P[pi][li]):
        del P[pi][li]
        if not P[pi]:
            return None
    else:
        P[pi][li] = P[pi][li][k:]
    return _join(P)


def _words(flat: list[str]) -> list[str]:
    return [w for ln in flat for w in ln.split(" ")]


def _line_of(flat: list[str]) -> list[int]:
    return [i for i, ln in enumerate(flat) for _w in ln.split(" ")]


_DEP_NOUN_HEAD = re.compile(r"^(거|것|중|수|줄|데|때문|뿐|만큼|터|리|바|채|적|듯|양|척|지|뒤|때|동안|따름|김|셈|참|쪽)(이|가|은|는|을|를|의|에|에서|로|으로|도|만|까지|라|라고|지요|죠|인|입니다|이다|이에요|예요|인데|이라|이니|인가|처럼)?[,.!?…]*$")  # 관형형 뒤 의존명사 — 줄머리로 가면 꾸밈말과 갈린다


def modifier_end(w: str) -> bool:
    """관형형 꾸밈말로 끝나는 어절인가(「유일한」「쉰」「있을」) — 줄·쪽 끝에 새로 오면 꾸밈받는 말과 갈린다. 조사 은/는/이/가 … 로 끝나는 체언은 아니다(「는」은 주어 뒤라 같이 막는다)."""
    if w.endswith(",") or len(w) < 2:
        return False
    return w.endswith(("는", "던")) or (_adnominal(w) and w[-1] not in _JOSA)


def edge_ok(prev: str, nxt: str) -> bool:
    """여기서 쪽을 끊어도 되나 — 절 경계(문장 끝·쉼표·연결어미, 이음 갈림 아님)이거나, 뒤가 관형형 꾸밈말의 머리이고 앞이 조사로 끝나지 않는 부사어 같은 말(「아주｜좋아하시는 비프 스튜」, 관리자 10-26).
    관형어·목적어·주어(조사로 끝남) 뒤는 안 된다."""
    if bkind(prev) and not _bonded(prev, nxt):
        return True
    return bool(prev) and prev[-1] not in _JOSA and not _adnominal(prev) and _adnominal(nxt.rstrip(SENT_END + ",")) and not _bonded(prev, nxt)


def page_edge_ok(prev: str, nxt: str) -> bool:
    """쪽 경계로 **엄격히** 되나 — 문장 끝·쉼표·연결어미 경계(이음 갈림 아님)만. 꾸밈말·관형어·목적어·주어 뒤는 안 된다(규칙 2-16, 지표 i).
    `edge_ok` 는 줄 옮기기 후보를 거를 때 쓰는 너그러운 판정(부사어 뒤 허용)이라 따로 둔다."""
    return bool(bkind(prev)) and not _bonded(prev, nxt)


def _bonded_breaks(flat: list[str]) -> int:
    return sum(1 for a, b in itertools.pairwise(flat) if a and b and not ends_sentence(a) and _bonded(a.rsplit(" ", 1)[-1], b.split(" ", 1)[0]))


def regressions(before: list[str], after: list[str]) -> int:
    """규칙이 **새로 만든** 나쁜 끊김 수(지표 f) — ① 전에 없던 줄 끝에서 `krwrap.split_reason`(보조용언·의존명사·관형사 고아 …)에 걸리는 끊김
    ② 전에는 한 줄이던 문장(두 낱말 이상)이 줄 사이로 갈림 ③ 절 경계로 끝나던 줄이 단위 안에서 줄어듦(순감소분). 낱말 열이 다르면(글이 바뀐 경우) 비교 못 하고 0."""
    bp = [before] if before and isinstance(before[0], str) else before  # 줄 목록이면 쪽 하나로 본다
    ap = [after] if after and isinstance(after[0], str) else after
    before, after = _flat(bp), _flat(ap)
    wb, wa = _words(before), _words(after)
    if wb != wa:
        return 0
    lb, la = _line_of(before), _line_of(after)
    b0 = {i for i in range(1, len(wb)) if lb[i] != lb[i - 1]}
    b1 = {i for i in range(1, len(wa)) if la[i] != la[i - 1]}

    def bad(i: int) -> bool:
        w = wa[i - 1]
        # 🔴 11-21 마스터 지정 「자신의 장원이 있는｜낫슈 마을로」: 한 줄이 세 어절 이상인 관형절로 끝나면 꾸밈말 고아가 아니라 절 하나가 줄을 이룬 것이다(한 어절 꾸밈말만 고아로 센다)
        # (11-21 관리자: 뒤가 의존명사(거·중·수·것…)면 관형절이 길어도 붙임 — 완화는 뒤가 자립명사일 때만)
        return not ends_sentence(w) and (_bonded(w, wa[i]) or (modifier_end(w) and (_DEP_NOUN_HEAD.match(wa[i]) is not None or sum(1 for x in la if x == la[i - 1]) < 3)))

    # 새로 생긴 이음 갈림은 없어진 갈림과 자리를 바꾼 것이어도 센다(「수⏎있다」→「마실⏎수」는 나쁨에서 나쁨 — 관리자 10-26)
    n = sum(1 for i in b1 - b0 if bad(i))
    # ③ 절 경계(문장 끝·쉼표·연결어미)로 끝나던 줄이 경계 아닌 곳에서 끝나는 줄로 바뀐 만큼 — 「있으면 좋으련만⏎」→「있으면⏎좋으련만 …」 꼴
    n += max(0, sum(1 for i in b0 if bkind(wb[i - 1]) and not _bonded(wb[i - 1], wb[i])) - sum(1 for i in b1 if bkind(wa[i - 1]) and not _bonded(wa[i - 1], wa[i])))
    # ④ 쪽 경계(관리자 10-26): 문장 끝이던 쪽 경계를 문장 중간으로 옮기면 퇴행 · 새 쪽 경계는 절 경계(문장 끝·쉼표·연결어미)에서만 — 관형어·목적어·주어 뒤에서 쪽을 끊지 않는다
    def page_starts(pgs: list[list[str]]) -> set[int]:
        out, c = set(), 0
        for p in pgs[:-1]:
            c += sum(len(ln.split(" ")) for ln in p)
            out.add(c)
        return out

    pb0, pb1 = page_starts(bp), page_starts(ap)
    n += sum(1 for i in pb0 if ends_sentence(wb[i - 1]) and i not in pb1)
    n += sum(1 for i in pb1 - pb0 if not edge_ok(wa[i - 1], wa[i]))
    n += max(0, glued_splits(after) - glued_splits(before))  # 띄어 쓴 이름·굳은 명사구를 새로 가르면 퇴행
    # ② 전에는 한 줄이던 절(문장 끝·쉼표·연결어미 경계 사이)이 줄 사이로 갈림 — 문장 하나가 한 줄이던 경우를 포함한다(「거대한 성이⏎서 있다.」)
    start = 0
    for i, w in enumerate(wb):
        last = i == len(wb) - 1
        if last or (bkind(w) and not _bonded(w, wb[i + 1])):
            if i > start and lb[start] == lb[i] and la[start] != la[i]:
                n += 1
            start = i + 1
    return n


def _shift_line(pg: list[list[str]], pi: int, down: bool) -> list[list[str]] | None:
    """쪽 `pi` 와 `pi+1` 사이에서 줄 하나를 통째로 옮긴다(down: 앞 쪽 끝 줄 → 뒤 쪽 첫 줄, 아니면 반대) — 창 줄 수를 고르게(h2)."""
    P = [list(p) for p in pg]
    a, b = P[pi], P[pi + 1]
    if down:
        if len(a) < 2 or len(b) >= LINES:
            return None
        b.insert(0, a.pop())
    else:
        if len(b) < 2 or len(a) >= LINES:
            return None
        a.append(b.pop(0))
    return P


def _move_clause(pg: list[list[str]], pi: int, j: int, speaker: bool) -> list[list[str]] | None:
    """쪽 `pi` 의 낱말 `j` 번부터 끝까지(꾸밈말 덩이)를 다음 쪽 앞으로 **통째로** 내리고 두 덩이를 다시 감는다(쪽이 늘 수 있다 — 계약 없는 씬만)."""
    words_prev = [w for ln in pg[pi] for w in ln.split(" ")]
    words_next = [w for ln in pg[pi + 1] for w in ln.split(" ")]
    if not 0 <= j < len(words_prev):
        return None
    head = words_prev[:j]
    tail = words_prev[j:] + words_next
    out: list[list[str]] = [list(p) for p in pg[:pi]]
    first = not out
    if head:
        out += _wrap_chunk(" ".join(head), speaker and first, WIDTH, FIRST_WITH_SPEAKER)
        first = False
    out += _wrap_chunk(" ".join(tail), speaker and first, WIDTH, FIRST_WITH_SPEAKER)
    out += [list(p) for p in pg[pi + 2 :]]
    return out


def polish(pg: list[list[str]], speaker: bool) -> list[list[str]]:
    """두 단계 — ① 종전 후처리(줄·쪽 수 불변) ② 쪽 경계를 절 경계로 옮기는 탐색(지표 i): ① 의 결과를 기준으로 다른 지표(꼬리 한 어절·이음 갈림·창 고름·절 갈림)가 하나도 안 늘 때만 받는다."""
    global _PEN
    _PEN = 0
    pg = _polish(pg, speaker, None)
    if not PAGE_EDGE_PENALTY or isinstance(pg, Card) or not pg or not all(pg) or not RULE_2_16 or len(pg) < 2:
        return pg
    _PEN = PAGE_EDGE_PENALTY
    try:
        return _polish(pg, speaker, _guard(pg))
    finally:
        _PEN = 0


def _polish(pg: list[list[str]], speaker: bool, ref: tuple | None) -> list[list[str]]:
    """2-16 ②③④ — 공용 조판기가 짠 줄·쪽을 **지표 판정**으로 다듬는다. 줄 끝 낱말을 옆 줄로 옮기는 후보를 벌점(`_score`)으로 견주어 줄어드는 쪽만 받는다(결정적, 쪽·줄 수 불변).
    공용 `krwrap` 은 안 건드린다(동결) — 이 게임 창에서 쓰는 규칙만 여기 둔다."""
    if isinstance(pg, Card) or not pg or not all(pg) or not RULE_2_16:
        return pg
    best = _score(pg, speaker)
    if best is None:
        return pg
    base = pg
    g0 = ref if ref is not None else (9, 9, 9, 9, 9, 9)  # 첫 단계는 제한 없음
    for _ in range(12):
        cand = None
        for pi, p in enumerate(pg):
            for li, ln in enumerate(p):
                for k in (1, 2, 3, 4):
                    for mv in (_move_tail, _move_head):
                        new = mv(pg, pi, li, k, speaker)
                        if new is None:
                            continue
                        sc = _score(new, speaker)
                        if sc is not None and sc < best and not (REJECT_REGRESSION and regressions(base, new)) and all(x <= y for x, y in zip(_guard(new), g0)) and (cand is None or sc < cand[0]):
                            cand = (sc, new)
        if grow_allowed():
            for pi in range(len(pg) - 1):
                wp = [w for ln in pg[pi] for w in ln.split(" ")]
                for j in range(len(wp)):
                    if j and not edge_ok(wp[j - 1], wp[j]):
                        continue
                    new = _move_clause(pg, pi, j, speaker)
                    if new is None or new == pg:
                        continue
                    sc = _score(new, speaker)
                    if sc is not None and sc < best and not (REJECT_REGRESSION and regressions(base, new)) and all(x <= y for x, y in zip(_guard(new), g0)) and (cand is None or sc < cand[0]):
                        cand = (sc, new)
        for pi in range(len(pg) - 1):
            for down in (True, False):
                new = _shift_line(pg, pi, down)
                if new is None:
                    continue
                sc = _score(new, speaker)
                if sc is not None and sc < best and not (REJECT_REGRESSION and regressions(base, new)) and all(x <= y for x, y in zip(_guard(new), g0)) and (cand is None or sc < cand[0]):
                    cand = (sc, new)
        if cand is None:
            break
        best, pg = cand
    return pg


def _flat(pg: list[list[str]]) -> list[str]:
    return [ln for p in pg for ln in p]


def soften_chunk(chunk: str) -> tuple[str, str | None]:
    """`_soften` + 문장 끝 개행으로 남은 줄이 한 줄에 안 들면 번역 줄 그대로(지표 c 가 이 결과의 남은 문장 중간 개행을 센다)."""
    out, header = _soften(chunk)
    if header is None and "\n" in out and any(px(x) > FULL * 12 for x in out.split("\n")):
        return chunk, None
    return out, header


def _soften(chunk: str) -> tuple[str, str | None]:
    """2-16 ① 문장 중간의 손 개행은 공백으로 읽는다 — 번역 원고의 줄 맞춤 개행이 「성에⏎도둑이」 같은 토막을 만든다.
    문장 끝 부호 뒤 개행·장 끝 카드(빈 줄·앞 공백)는 둔다. 첫 줄이 정본 이름 머리(「착해 보이는 할머니」)면 그 줄은 떼어 돌려준다(header)."""
    if "\n" not in chunk or not RULE_2_16:
        return chunk, None
    lines = chunk.split("\n")
    if any(not x or x[0] in " \u3000" for x in lines):
        return chunk, None  # 카드
    header = None
    if len(lines) >= 2 and lines[0] in glue_phrases():
        header, lines = lines[0], lines[1:]
    out = lines[0]
    for ln in lines[1:]:
        out += ("\n" if ends_sentence(out.rsplit("\n", 1)[-1]) else " ") + ln
    return (header + "\n" + out if header is not None else out), header


def _pages_after_lead(chunk: str, lead_px: int) -> list[list[str]]:
    """앞 줄에 `lead_px` 가 이미 찍힌 채 이어 붙는 쪽 — 첫 줄을 남은 폭에, 나머지는 보통 폭에 짠다."""
    rem = FULL * 12 - lead_px - SPACE_PX  # 칸 13 에 닿으면 인터프리터가 스스로 넘기므로 한 눈금(4px) 덜 쓴다
    words = chunk.split()
    first: list[str] = []
    acc = 0
    for w in words:
        add = px(w) + (SPACE_PX if first else 0)
        if acc + add > rem:
            break
        first.append(w)
        acc += add
    rest = " ".join(words[len(first) :])
    head = " ".join(first)  # 비면 '' — 명시 개행(compose 가 빈 줄 뒤 줄 앞에 개행을 낸다)
    for width in (WIDTH, WIDTH - 0.5):  # 런타임 줄넘김과 다르면(꽉 찬 줄 끝 어절이 다음 줄 첫 어절과 공백 없이 붙어 한 어절로 읽힘 — 씬 41 「녀석에게앙갚음하게」, 11-05) 반 칸 좁혀 다시 짠다
        flat: list[str] = []
        if rest:
            for p in krwrap.wrap_pages(rest, width, 1000, cell_width=cell):
                flat += p
        take = LINES - 1
        pages_out = [[head] + flat[:take]]
        flat = flat[take:]
        while flat:
            pages_out.append(flat[:LINES])
            flat = flat[LINES:]
        if all(_lead_runtime_ok(pg, lead_px if i == 0 else 0) for i, pg in enumerate(pages_out)):
            break
    return pages_out


def _lead_runtime_ok(page: list[str], lead_px: int) -> bool:
    """앞 줄에 `lead_px` 가 이미 찍혀 있다고 보고 `runtime_ok` 와 같이 런타임 줄넘김 모델로 대조한다(앞 글은 같은 폭의 자리표시 글자)."""
    import typeset_check

    filler = "가" * (lead_px // 12) + " " * ((lead_px % 12) // SPACE_PX)
    got, _ = typeset_check.wrap(filler + emit_stream(page))
    page = [x.replace(TIE, " ") for x in page]
    want = [filler + page[0], *page[1:]] if lead_px else list(page)
    return [x.strip(" ") for x in got if x.strip(" ")] == [x.strip(" ") for x in want if x.strip(" ")]


def _wrap_chunk(chunk: str, speaker: bool, width: float, first: float) -> list[list[str]]:
    pg = krwrap.wrap_pages(chunk, width, LINES, cell_width=cell, unsplit_fill=True)
    if speaker and pg and pg[0] and px(pg[0][0]) > first * 12:
        # 첫 줄만 좁히면 되지만 krwrap 엔 줄별 폭이 없다 — 첫 창을 10칸으로 다시 짠다
        fp = krwrap.wrap_pages(chunk, first, LINES, cell_width=cell, unsplit_fill=True)
        pg = (
            fp[:1]
            + krwrap.wrap_pages(
                "\n".join(l for p in fp[1:] for l in p),
                width,
                LINES,
                cell_width=cell,
                protect_hard=False,
                unsplit_fill=True,
            )
            if len(fp) > 1
            else fp
        )
    return pg


# 꽉 찬 13칸 줄 뒤에도 명시 개행(`01`)을 낸다(관리자 11-05 — PCE 실화면 헤드리스 시험: 한글로 끝나는 13칸 줄·부호로 끝나는 13칸 줄·셋째 줄이 꽉 찬 쪽 넘김 모두 빈 줄·틀 칸 잔상 없음,
# `.local/work/inbox/pce-ed1/fullnl-test/`). 꽉 찬 줄 끝 어절이 다음 줄 첫 어절과 공백 없이 붙어 어절째 내려가던 결함(씬 41 「녀석에게앙갚음하게」·씬 77 「같지가않았어요」)이 구조적으로 사라지고
# 13칸 줄을 쓸 수 있어 줄·창이 줄어든다(2-17). 끄면(False) 종전 동작 — 변경 전 값을 재는 때만.
FULL_LINE_NL = True


def emit_stream(page: list[str]) -> str:
    """한 쪽을 게임에 내는 글 흐름 — `translate.compose` 와 같다: 줄 사이 개행은 앞 줄이 13칸 미만일 때만(꽉 찬 줄은 인터프리터가 스스로 넘긴다)."""
    out = ""
    for i, ln in enumerate(page):
        if i and (FULL_LINE_NL or cols(page[i - 1]) < FULL):
            out += "\n"
        out += ln.replace(TIE, " ")  # 런타임은 보통 공백이다 — 줄 안 공백이면 한 줄에 든다
    return out


def runtime_ok(page: list[str]) -> bool:
    """계획한 줄 = 런타임이 실제로 나눌 줄인가 — 넘침 지표(g). 런타임 줄넘김 모델은 `typeset_check.wrap`(후킹 `wrap`·`wordck` 을 흉내) 하나다.
    꽉 찬 줄 끝 어절이 다음 줄 첫 어절과 **공백 없이 붙어** 한 어절로 읽히면(「…열쇠라고 하는｜라누라…」) 어절째 아랫줄로 내려가 줄이 넘친다(씬 115, 10-26 화면 실측)."""
    if isinstance(page, Card):
        return True
    import typeset_check

    got, _cuts = typeset_check.wrap(emit_stream(page))
    return [x.strip(" ") for x in got if x.strip(" ")] == [x.replace(TIE, " ").strip(" ") for x in page if x.strip(" ")]


def _fused_boundary(pg: list[list[str]]) -> bool:
    """뒤에 줄이 이어지는데 반각 부호로 끝나 칸 13 에 닿은 줄이 있나(`translate.compose` 가 꽉 찬 줄 뒤에 개행을 안 낼 때만 문제 — `FULL_LINE_NL` 이면 해당 없음)."""
    if FULL_LINE_NL:
        return False
    for p in pg:
        for j, ln in enumerate(p[:-1]):
            if ln and ln[-1] in NARROW and ln[-1] != " " and cols(ln) >= FULL:
                return True
    return False


def ink(s: str) -> str:
    """글자만 — 공백(반각·전각)·개행·페이지를 뺀다."""
    return "".join(c for c in s if c not in " \u3000\n\f")


# ── 줄·쪽 나눔 지표 부품(공통 번역 규칙 2-16) ────────────────────────────────────────────────────────────────────────
#   지표 검사기 `linebreak_metrics.py` 와 조판 후처리(`polish`)가 **같은 판정**을 쓴다 — 고친다는 것과 남았다고 세는 것이 어긋나지 않게(DRY).
SENT_END = ".!?…~」』"
MIN_LEFT_PX = 60  # 절째 내릴 때 앞 줄에 남는 글이 이보다 짧으면(낱말 하나쯤) 거기선 안 끊는다 — sfc-ed2 MIN_LEFT 20/50 단위를 이 창 폭(156px)에 맞춘 값
_CONJ = {
    "그리고", "하지만", "그러나", "그래서", "게다가", "그러면", "그런데", "그러니", "그렇다면", "그러므로", "따라서", "그렇지만", "그래도", "그러자",
}  # 문장 머리 접속어 — 뒤 말에 붙는다(경계 아님)
_CONN_RE = re.compile(r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|고|며|면)$")


def ends_sentence(s: str) -> bool:
    return bool(s) and s.rstrip()[-1:] in SENT_END


def bkind(word: str) -> int:
    """줄 나눔 경계의 세기 — 3 문장 끝 > 2 쉼표(「오,」 같은 두 음절 이하는 제외) > 1 연결어미(문장 머리 접속어 제외) > 0 아님."""
    if not word:
        return 0
    if word[-1] in SENT_END:
        return 3
    if word.endswith(","):
        return 2 if len(word.rstrip(",")) > 2 else 0
    return 1 if (word not in _CONJ and _CONN_RE.search(word)) else 0


_TITLE_RE = re.compile(r"^(공작|왕자|왕비|왕|공주|공|경|백작|장군|대장|선장|사제|신부|씨|님|폐하|전하|할아범|국왕|박사|선생|도령|마스터)(님|께서|께|의|은|는|이|가|을|를|도|에게|과|와|으로|로)?[,.!?…]*$")


# 🔴 11-21 마스터 「와 / 계십니다」 · 「자신의 장원이 / 있는」류 31곳 일괄 판정 — 공용 `krwrap.split_reason` 이 못 잡는 보조용언(계시다·드리다·버리다·주다 …)과
# 의존명사 뒤 있다·없다, 예정 어미(테니·텐데·걸세)가 줄 머리로 밀리는 갈림을 이음으로 본다(공용 규칙은 동결 — 이 게임 쪽 규칙).
_PLACE_HEAD = re.compile(r"^(마을|항구|성|탑|동굴|왕국|광산|요새)(은|는|이|가|을|를|에|에서|로|으로|의|과|와|도|만|까지)?[,.!?…]*$")  # 띄어 쓴 지명(「낫슈 마을」·「네리아 항구」)이 줄 사이에서 갈리지 않게
_AUX_HEAD = re.compile(r"^(테니|텐데|걸세|계시|드려|드립|드릴|드리겠|버려|버렸|버리겠|계십|계셔|주겠|주시|주었|주지|주세|주신)")
_DEP_PREV = re.compile(r"(적이|것이|수가|리가|줄이|바가|적도|수도|것도|뿐이|따름이|말씀이|필요가)$")
_EXIST_HEAD = re.compile(r"^(있|없)")


def _bonded(prev_word: str, next_word: str) -> bool:
    # 🔴 11-21 마스터 지정 「프라토 국왕께서｜와 계십니다」: 공용은 「…께서｜와」를 본용언+보조용언으로 읽지만, 주격·목적격 조사로 끝난 어절 뒤 「와」는 동사 줄기(오다)라 「와 계십니다」가 한 덩이다 — 그 앞에서 끊는 게 맞다
    if next_word == "와" and prev_word.endswith(("께서", "이", "가", "은", "는", "을", "를")):
        return False
    if krwrap.split_reason(prev_word, next_word):
        return True
    p, n = prev_word.rstrip(",.!?…"), next_word
    if prev_word[-1:] not in SENT_END and _AUX_HEAD.match(n):
        return True
    if prev_word[-1:] not in SENT_END and _PLACE_HEAD.match(n) and len(p) >= 2 and p[-1] not in "은는이가을를의에도로와과만" and not krwrap.split_reason(p, n):
        return True
    if prev_word[-1:] in SENT_END:
        return False
    if _TITLE_RE.match(n) and p[-1:] not in _JOSA:  # 이름+칭호가 갈림(제스톤｜공작의)
        return True
    return False


def clause_move(lines: list[str], i: int) -> tuple[int, int] | None:
    """`lines[i]` 에서 `lines[i+1]` 로 절째 내릴 자리 — (나눌 낱말 색인 j, 내릴 글 폭 px) 또는 None.
    줄 끝이 이미 경계면 None. 센 경계부터 보고, 내릴 글(이 줄 j 번째 낱말부터 + 다음 줄 첫 경계까지)이 한 줄(156px)에 들면 후보다."""
    L = lines[i].split(" ")
    if not L or not lines[i + 1] or bkind(L[-1]) >= 1:
        return None
    for kind in (3, 2, 1):
        j = next((j for j in range(len(L) - 1, 0, -1) if bkind(L[j - 1]) == kind), None)
        if j is None or px(" ".join(L[:j])) < MIN_LEFT_PX or _bonded(L[j - 1], L[j]):
            continue
        run = px(" ".join(L[j:]))
        done = False
        for nxt in lines[i + 1 :]:  # 내릴 절은 다음 줄들을 넘어 첫 경계(없으면 글 끝)까지다
            for x in nxt.split(" "):
                run += SPACE_PX + px(x)
                if bkind(x):
                    done = True
                    break
            if done or run > FULL * 12:
                break
        if run <= FULL * 12:
            return j, px(" ".join(L[j:]))
    return None


def clause_splits(flat: list[str]) -> int:
    """절째 내리면 들어가는데 쪼갠 줄 쌍의 수(지표 d)."""
    return sum(1 for i in range(len(flat) - 1) if flat[i] and flat[i + 1] and clause_move(flat, i))


PLACE_SUFFIX = ("공화국", "왕국", "공국", "마을", "광산", "항구", "호수", "요새", "수용소", "휴게소")  # 대화에서 띄우는 지명 종류 말
_GLUE: list[str] = []


def glue_phrases() -> list[str]:
    """줄·쪽 사이에서 갈리면 안 되는 띄어 쓴 이름 — 정본(`canon`)의 공백 든 고유명사."""
    if not _GLUE:
        import canon

        cats = canon.nouns("eiyuu")["categories"]
        ph = {v for c in cats.values() for v in c.values() if isinstance(v, str) and " " in v}
        # 지명은 정본이 붙임 꼴(「파렌왕국」)이고 대화는 종류 말을 띄운다(「파렌 왕국」·「네리아 항구 마을」, 성·섬은 붙임 — docs/naming.md) — 띄운 꼴도 이름이다
        for v in cats.get("place", {}).values():
            if isinstance(v, str) and " " not in v:
                for suf in PLACE_SUFFIX:
                    if v.endswith(suf) and len(v) > len(suf):
                        ph.add(v[: -len(suf)] + " " + suf)
                        if suf in ("항구", "광산"):
                            ph.add(v[: -len(suf)] + " " + suf + " 마을")
        _GLUE.extend(sorted(ph, key=len, reverse=True))
    return _GLUE


# [명사+명사] 굳은 구(「게임 상대」「노예 상인」)를 줄 사이에서 가르지 않는다(2-16 ④) — 형태소 분석기 없이 앞 어절이 조사·어미·관형형·부사가 아닌 꼴이면 명사로 보고,
# 같은 이음이 대사 전량에 두 번 이상 나와야 구로 친다(반복이 구라는 증거). 판정은 md-ed1 `linebreak.py` 와 같다.
_NOT_NOUN_END = set("은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들")
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리", "또다시", "냉큼", "모조리",
    "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써", "이미", "결코", "반드시", "제발", "어서", "함께", "같이", "그냥",
}  # fmt: skip
_JOSA = "은는이가을를의에도로와과만"
_PHRASES: set | None = None


def _adnominal(w: str) -> bool:
    if w[-1] in "던는":
        return True
    o = ord(w[-1]) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형 -ㄴ/-ㄹ)


def noun_noun(wa: str, wb: str) -> bool:
    if not wa or not wb or wa in _NOT_NOUN or wa[-1] in SENT_END + ",":
        return False
    if wa[-1] in _NOT_NOUN_END or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")  # 서술어·지시어로 시작하는 뒤는 구가 아니다


def _stem(w: str) -> str:
    return w.rstrip(_JOSA + ".,!?…」") or w


def phrases() -> set:
    """대사 전량(정본 문안)에서 같은 [앞 어절, 뒤 어절 줄기] 이음이 두 번 이상 나온 명사 구."""
    global _PHRASES
    if _PHRASES is None:
        import collections

        import common
        import messages as M

        cnt: collections.Counter = collections.Counter()
        for p in sorted((common.GAME_DIR / "script").glob("scn*.json")):
            for v in M.load_translations(int(p.stem[3:])).values():
                t = v.get("t", "")
                if not t or v.get("raw"):
                    continue
                ws = t.replace("\n", " ").replace("\f", " ").split()
                for x, y in itertools.pairwise(ws):
                    if noun_noun(x, y):
                        cnt[(x, _stem(y))] += 1
        _PHRASES = {k for k, n in cnt.items() if n >= 2}
    return _PHRASES


def nounphrase_splits(flat: list[str]) -> int:
    """[명사+명사] 굳은 구가 줄 끝·첫머리로 갈린 자리 수(지표 e 의 둘째 몫)."""
    n = 0
    for a, b in itertools.pairwise(flat):
        if a and b and not ends_sentence(a):
            wa, wb = a.rsplit(" ", 1)[-1], b.split(" ", 1)[0]
            if noun_noun(wa, wb) and (wa, _stem(wb)) in phrases():
                n += 1
    return n


def glued_splits(flat: list[str]) -> int:
    """띄어 쓴 이름이 줄 사이에서 갈린 자리 수(지표 e 의 첫 몫) + [명사+명사] 굳은 구."""
    n = nounphrase_splits(flat)
    for i in range(len(flat) - 1):
        a, b = flat[i], flat[i + 1]
        if not a or not b:
            continue
        joined = a + " " + b
        for ph in glue_phrases():
            at = joined.find(ph)
            while at >= 0:
                if at < len(a) < at + len(ph):  # 경계 위치(len(a))가 이름 속 공백을 지난다
                    n += 1
                    break
                at = joined.find(ph, at + 1)
    return n


import contextlib  # noqa: E402


@contextlib.contextmanager
def on_flow():
    """음성 자막(비모달) 조판 구간 — 화자 창 첫 쪽이 넘칠 때 전체를 종전(3줄)으로 짠다. OFF 대사창은 첫 쪽만 3줄·둘째부터 4줄."""
    global ON_FLOW
    old, ON_FLOW = ON_FLOW, True
    try:
        yield
    finally:
        ON_FLOW = old
