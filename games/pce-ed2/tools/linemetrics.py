"""줄·쪽 나눔 지표 (번역 규칙 2-16) — 조판 결과(쪽 → 줄 목록)에서 규칙을 어긴 자리를 센다.

 (a) 쪽 끝 한 어절 고아 — 줄 바꿈으로 생긴 쪽 경계에서 앞 쪽 끝 줄이 한 어절뿐(앞 줄이 있는 쪽)
 (b) 문장 중간에서 한 낱말로 끝나는 쪽 — 쪽이 문장 한가운데서 끝나는데, 그 쪽에 놓인 그 문장의 몫이 한 어절이거나,
     쪽 끝 어절과 다음 쪽 첫 어절이 본용언+보조용언 같은 한 덩어리
 (c) 문장 중간 손 개행 — 문안에 든 `\\n` 이 문장 끝·쪽 표지 옆이 아닌 자리
 (e) [명사+명사] 굳은 구가 줄 끝·첫머리로 갈림 — 앞 어절이 조사·어미·관형형·부사가 아니고 같은 이음이 대사 전량에 2회 이상
 (d) 절째 내리면 들어가는데 쪼갠 줄 — 이 줄에서 시작한 절(문장 끝 > 쉼표 > 연결어미 뒤부터)이 다음 줄과 합쳐 한 줄에 들어가는데 줄이 그 안에서 갈렸다

세는 법의 정본은 여기 하나다 — 조판기(`typeset.py`)가 고치는 자리와 검사기가 남았다고 세는 자리가 같은 판정을 쓴다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from text import krwrap

import font

LINE_PX = 14 * 12
MIN_LEFT_PX = 80  # 절째 내리고도 앞 줄에 이만큼은 남아야 한다 — 낱말 하나 정도만 남는 자리에서는 안 끊는다(sfc 20/50 단위를 이 창 폭으로)
_END = ".!?…~」』"
_CONJ = {"그리고", "하지만", "그러나", "그래서", "게다가", "그러면", "그런데", "그러니", "그렇다면", "그러므로", "따라서", "그렇지만", "그래도", "그러자"}
_CONN_RE = re.compile(r"(?:아서|어서|여서|해서|려서|러서|라서|워서|니까|으니|면서|으며|하며|지만|는데|인데|으나|다가|도록|려고|므로|고|며|면)$")
NBSP = " "  # 띄어 쓴 굳은 명사구 속 공백 자리표시


# (e) [명사+명사] 굳은 구 — 형태소 분석기 없이, 앞 어절이 조사·어미·관형형·부사가 아닌 꼴이면 명사로 본다. 같은 이음(앞 어절 + 뒤 어절 줄기)이
# 대사 전량에 두 번 이상 나와야 굳은 구로 친다(반복이 구라는 증거). 오탐은 줄 수가 안 늘 때만 묶으니 해가 작다.
_NOT_NOUN_END = set("은는이가을를의에도로와과만서고며면니다요죠까나네데지자게어아해라러든께야군걸들")
_NOT_NOUN = {
    "가장", "특히", "모두", "한층", "우선", "역시", "대체", "여태", "지금", "이제", "계속", "완전히", "원래", "여기", "그리", "또다시",
    "냉큼", "모조리", "빨리", "우리", "너희들", "여러분", "정말", "아주", "매우", "너무", "다시", "아직", "벌써", "이미", "결코",
    "반드시", "제발", "어서", "함께", "같이", "그냥",
}  # fmt: skip
_JOSA = "은는이가을를의에도로와과만"
PHRASES: set[tuple[str, str]] = set()  # `set_phrases` 가 채운다


def _adnominal(w: str) -> bool:
    c = w[-1]
    if c in "던는":
        return True
    o = ord(c) - 0xAC00
    return 0 <= o < 11172 and o % 28 in (4, 8)  # 받침 ㄴ·ㄹ(관형형)


def noun_noun(wa: str, wb: str) -> bool:
    if len(wa) < 2 or not wb or wa in _NOT_NOUN or wa[-1] in "기히리쯤것곳" or wa[-1] in _NOT_NOUN_END or wa[-1] in ".,!?…」』)" or _adnominal(wa):
        return False
    return not (wb[-1] in "다요죠까" or wb[0] in "그이저")  # 서술어·지시어로 시작하는 뒤는 구가 아니다


def _stem(w: str) -> str:
    return w.rstrip(_JOSA + ".,!?…」") or w


def set_phrases(texts) -> None:
    """대사 전량(문자열들)에서 같은 [명사+명사] 이음이 두 번 이상 나온 것을 굳은 구로 등록한다."""
    import collections
    import itertools

    cnt: collections.Counter = collections.Counter()
    for t in texts:
        for x, y in itertools.pairwise(t.replace("\n", " ").replace("\f", " ").replace("§", " ").split()):
            if noun_noun(x, y):
                cnt[(x, _stem(y))] += 1
    PHRASES.clear()
    PHRASES.update(k for k, n in cnt.items() if n >= 2)


def fixed_phrase(wa: str, wb: str) -> bool:
    return bool(wa and wb and (wa, _stem(wb)) in PHRASES and noun_noun(wa, wb))


def local_glue(a: str, b: str) -> str | None:
    """공용 `split_reason` 에 아직 없는 이음 — 갈리면 읽기 어려운 구문(마스터 10-26 표본 셋)."""
    if a.endswith("고") and len(a) >= 3 and b.startswith("해") and not b.startswith("해야"):
        return "-고 해서"  # 「납치되고 / 해서」
    if a.endswith(("리라", "으리라")) and b[:1] == "여":
        return "-리라 여기다"  # 「알아들으리라 / 여겨」
    if a.endswith(("는데", "은데", "인데")) and b.startswith("말이"):
        return "-는데 말이야"  # 「했는데 / 말이야,」
    # 🔴 11-22 마스터 「또 / 하나의 목적」 · PCE I 11-21 줄머리 규칙 — 공용 `split_reason` 이 못 잡는 부류(게임 쪽 규칙, 공용 동결)
    if a.rstrip(",") in ADV_BEFORE_NUM and _NUM_HEAD.match(b):
        return "꾸밈말 + 수 관형어"  # 「그리고 여행에는 또 / 하나의 목적」
    if a in ("한", "두", "세", "네") and b[:1] in "번명개마":
        return "수 관형사 + 단위"  # 「일 년에 한 / 번뿐」
    if a[-1:] not in ".!?…」』" and _AUX_HEAD.match(b):
        return "예정 어미·보조용언 줄머리"  # 「합류할 / 테니」 · 「찾아 / 주시다니」
    if _DEP_PREV.search(a.rstrip(",")) and _EXIST_HEAD.match(b):
        return "의존명사 + 있다·없다"
    if _DEP_NOUN.match(b) and _adnominal(a):
        return "관형형 + 의존명사"  # 「믿고 있었던 / 만큼」 · 「들어갈 / 수 있었던」
    return None


_DEP_NOUN = re.compile(r"^(거|것|수|줄|뿐|만큼|따름|바|터|리|채|듯|양|척|셈)(이|가|은|는|을|를|의|에|에서|로|으로|도|만|까지|라|라고|지요|죠|인|입니다|이다|이에요|예요|인데|이라|이니|인가|처럼)?[,.!?…]*$")


def _adnominal(w: str) -> bool:
    """관형형 어미(ㄴ·ㄹ 받침 — 은/는/던/을 따위)로 끝나는 어절인가."""
    w = w.rstrip(",")
    c = w[-1:]
    return bool(c) and "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 in (4, 8)


ADV_BEFORE_NUM = {"또", "단", "딱", "겨우", "오직", "꼭"}
_NUM_HEAD = re.compile(r"^(하나|한\s*번|한\s*가지|두|세|네)")
_AUX_HEAD = re.compile(r"^(테니|텐데|걸세|계시|드려|드립|드릴|드리겠|버려|버렸|버리겠|계십|계셔|주겠|주시|주었|주지|주세|주신)")
_DEP_PREV = re.compile(r"(적이|것이|수가|리가|줄이|바가|적도|수도|것도|뿐이|따름이|말씀이|필요가)$")
_EXIST_HEAD = re.compile(r"^(있|없)")


def glued(a: str, b: str) -> bool:
    """두 어절 사이에서 줄·쪽을 끊으면 갈리는 한 덩어리인가 — 본용언+보조용언 등(krwrap) 또는 굳은 명사 구."""
    return bool(krwrap.split_reason(a, b)) or bool(local_glue(a, b)) or fixed_phrase(a, b)


def wpx(s: str) -> int:
    return sum(font.adv_dlg(c) if c != NBSP else font.adv(" ") for c in s)


def kind(word: str | None) -> int:
    """줄 나눔 후보의 세기 — 3 문장 끝 > 2 쉼표(「오,」 처럼 두 음절 이하 제외) > 1 연결어미(문장 머리 접속어 제외) > 0 아님."""
    if not word:
        return 0
    if word[-1] in _END:
        return 3
    if word.endswith(","):
        return 2 if len(word.rstrip(",")) > 2 else 0
    return 1 if (word not in _CONJ and _CONN_RE.search(word)) else 0


def clause_fits(line_words: list[str], next_words: list[str]) -> int | None:
    """줄 `line_words` 의 끝 절을 다음 줄 앞부분과 합쳐도 한 줄(168px)에 들어가는데 줄이 갈렸나 — 갈렸으면 절이 시작하는 어절 색인(없으면 None).
    경계는 센 것부터(문장 끝 > 쉼표 > 연결어미), 절의 끝은 다음 줄에서 처음 만나는 경계 어절."""
    if len(line_words) < 2 or not next_words or kind(line_words[-1]):
        return None  # 줄이 문장 끝·쉼표·연결어미로 끝났으면 절이 그 줄에서 끝난 것이다
    for k in (3, 2, 1):
        kk = next((j for j in range(len(line_words) - 1, 0, -1) if kind(line_words[j - 1]) == k), None)
        if kk is None:
            continue
        left = wpx(" ".join(line_words[:kk]))
        if left < MIN_LEFT_PX or krwrap.split_reason(line_words[kk - 1], line_words[kk]):
            continue  # 앞에 너무 짧게 남거나, 경계 자리가 본용언+보조용언 같은 한 덩어리면 거기서 끊지 않는다
        run = line_words[kk:]
        for w in next_words:
            run = run + [w]
            if kind(w):
                break
        if wpx(" ".join(run)) <= LINE_PX:
            return kk
        return None  # 가장 센 경계에서 안 들어가면 약한 경계로 내려가지 않는다(문장째 내리면 한 줄을 넘기는 절)
    return None


def _words(line: str) -> list[str]:
    return [w for w in line.replace(NBSP, " ").split(" ") if w]


def chunk_metrics(pgs: list[list[str]]) -> dict[str, list[str]]:
    """한 구간(손 쪽 표지 `\\f` 로 갈린 한 덩이)의 쪽 목록 → 지표별 어긴 자리 설명. 마지막 쪽 아래는 쪽 경계가 아니라 건너뛴다."""
    out: dict[str, list[str]] = {"a": [], "b": [], "d": [], "e": [], "g": []}
    flat = [(pi, ln) for pi, pg in enumerate(pgs) for ln in pg]
    for (pi, x), (_pj, y) in zip(flat, flat[1:]):
        wx, wy = _words(x), _words(y)
        if len(wx) >= 2 and wy and fixed_phrase(wx[-1], wy[0]):
            out["e"].append(f"p{pi}: {x} / {y}")
        if len(wx) >= 2 and wy and local_glue(wx[-1], wy[0]):  # 게임 쪽 줄머리 규칙(꾸밈말+수·예정 어미·보조용언 — 11-22)
            out["g"].append(f"p{pi}: {x} / {y}")
    for pi, pg in enumerate(pgs):
        for li in range(len(pg) - 1):
            kk = clause_fits(_words(pg[li]), _words(pg[li + 1]))
            if kk is not None:
                out["d"].append(f"p{pi}l{li}: {pg[li]} / {pg[li + 1]}")
        if pi == len(pgs) - 1:
            continue
        last = _words(pg[-1])
        nxt = _words(pgs[pi + 1][0])
        if len(last) == 1 and len(pg) >= 2:
            out["a"].append(f"p{pi}: …{pg[-2]} / {pg[-1]}")
        # 문장 중간에서 끝나는 쪽
        if last and last[-1][-1:] not in _END:
            body = " ".join(" ".join(p) for p in pgs[pi : pi + 1])
            tail = re.split(r"(?<=[.!?…~」』]) ", body)[-1]
            bonded = bool(nxt and glued(last[-1], nxt[0]))
            if len(_words(tail)) == 1 or bonded:
                out["b"].append(f"p{pi}: {pg[-1]} | {pgs[pi + 1][0]}")
    return out


def hand_newlines(text: str) -> list[str]:
    """문안에 든 `\\n` 가운데 문장 중간(앞이 문장 끝 부호가 아닌) 것."""
    res = []
    for m in re.finditer(r"\n", text):
        before = text[: m.start()].rstrip()
        if before and before[-1] not in _END:
            res.append(text[max(0, m.start() - 12) : m.end() + 12].replace("\n", "⏎"))
    return res


def count(m: dict[str, list[str]]) -> int:
    return sum(len(v) for v in m.values())


PAGE_LINES = 3  # 지금 짜는 쪽의 줄 수 상한 — `typeset._lay` 가 쪽 종류(화자 머리 쪽 3 · 머리 없는 쪽 4)에 맞춰 바꿔 끼운다


def flow(words: list[str], fit, pbreaks: frozenset[int] = frozenset(), lines_per_page: int | None = None) -> list[list[str]]:
    """어절 열 → 쪽 목록(줄 문자열). 규칙 2-16 ② — 줄이 넘칠 때 이 줄에서 시작한 절이 다음 줄에 통째로 들어가면 절째 내리고(경계: 문장 끝 > 쉼표 > 연결어미),
    본용언+보조용언은 함께 내린다. `pbreaks` = 이 색인의 어절에서 새 쪽을 시작한다(③ 쪽 끝 고아·낱말 쪽을 고치는 쪽 나눔 자리)."""
    pages: list[list[list[str]]] = [[[]]]

    def ok(ws):
        return fit(" ".join(ws))

    for i, w in enumerate(words):
        if i in pbreaks and (pages[-1][-1] or len(pages[-1]) > 1):
            pages.append([[]])
        line = pages[-1][-1]
        if not line or ok(line + [w]):
            line.append(w)
            continue
        # 넘쳤다 — 같이 내릴 꼬리: 본용언+보조용언 사슬, 절째 내리기
        k = len(line)
        first = w
        while k > 1 and glued(line[k - 1], first):
            k -= 1
            first = line[k]
        if k < len(line) and not ok(line[k:] + [w]):
            k = len(line)
        kk = clause_fits(line, words[i : i + 8])
        if kk is not None and kk < k and ok(line[kk:] + [w]):
            k = kk
        carry = line[k:]
        del line[k:]
        if len(pages[-1]) >= (PAGE_LINES if lines_per_page is None else lines_per_page):
            pages.append([[]])
        else:
            pages[-1].append([])
        pages[-1][-1].extend(carry + [w])
    return [[" ".join(ln) for ln in pg if ln] for pg in pages if any(pg)]


def repage(words: list[str], fit, base: list[list[str]]) -> list[list[str]]:
    """`flow`(`fit` = 줄 문자열이 창에 들어가는가) 로 짜고, 쪽 끝 고아(a)·낱말 쪽(b)이 나면 그 쪽을 더 일찍(앞 쪽에서 문장 중간의 경계) 끊어 본다. 쪽 수가 `base` 보다 늘면 그 고침은 버린다."""
    pb: frozenset[int] = frozenset()
    k = 0
    seeds = set()  # 문장 끝에서 시작하는 쪽은 그대로 둔다 — 문장 끝 쪽 경계를 문장 중간으로 옮기는 퇴행을 막는다
    for pg in base:
        if k and kind(words[k - 1]) == 3:
            seeds.add(k)
        k += sum(len(ln.split(" ")) for ln in pg)
    pb = frozenset(seeds)
    best = flow(words, fit, pb)
    for _ in range(40):
        m = chunk_metrics(best)
        bad = m["a"] or m["b"]
        if not bad:
            break
        # 첫 어긋난 쪽 경계의 앞 쪽 어절 범위 안에서 가장 늦은 안전한 경계를 찾는다
        n = 0
        target = None
        pg_starts = []
        for pgs in best:
            pg_starts.append(n)
            n += sum(len(ln.split(" ")) for ln in pgs)
        pi = int(re.match(r"p(\d+)", bad[0]).group(1))
        lo, hi = pg_starts[pi], pg_starts[pi + 1]
        cand = [
            j
            for j in range(hi - 1, lo + 2, -1)
            if (kind(words[j - 1]) or True)
            and not glued(words[j - 1], words[j])
            and wpx(" ".join(words[lo:j])) >= LINE_PX  # 앞 쪽에 적어도 한 줄 이상은 남긴다
        ]
        if not cand:
            break
        trial = None
        for j in cand:
            t = flow(words, fit, pb | {j})
            if len(t) <= len(base) and count(chunk_metrics(t)) < count(m):
                trial = (j, t)
                break
        if trial is None:
            break
        pb |= {trial[0]}
        best = trial[1]
    return fix_tail_orphans(best, fit)


def fix_tail_orphans(pgs: list[list[str]], fit) -> list[list[str]]:
    """쪽 끝 줄이 한 어절(a)이면 앞 줄 끝 어절을 내려 두 어절로 만든다 — 「본선은 곧 다도해로 / 들어서겠습니다.」 → 「본선은 곧 / 다도해로 들어서겠습니다.」(마스터 11-22 줄 끝 매다는 부호 허용으로 새로 생긴 고아).
    앞 줄이 한 어절만 남거나 이음(`glued`)을 가르거나 내린 줄이 창에 안 들어가면 그대로 둔다. 마지막 쪽은 안 건드린다(쪽 끝이 아니다)."""
    out = [list(p) for p in pgs]
    for pi in range(len(out) - 1):
        pg = out[pi]
        if len(pg) < 2:
            continue
        last = _words(pg[-1])
        prev = _words(pg[-2])
        if len(last) != 1 or len(prev) < 3 or prev[-1][-1:] in _END:
            continue
        for k in (1, 2):  # 어절 하나를 내리고, 이음에 걸리면 이음 쌍째(둘)
            if len(prev) - k < 1:
                break
            moved = prev[-k:]
            if glued(prev[-k - 1], moved[0]) and k == 1:
                continue
            if glued(prev[-k - 1], moved[0]) or glued(moved[-1], last[0]):
                continue
            new_last = " ".join(moved) + " " + last[0]
            if fit(new_last):
                pg[-2] = " ".join(prev[:-k])
                pg[-1] = new_last
                break
    return out


def _flat(pgs: list[list[str]]) -> tuple[list[str], set[int]]:
    """쪽 목록 → (어절 열, 줄·쪽이 갈리는 자리 = 그 색인 어절 앞에서 새 줄)."""
    ws: list[str] = []
    brk: set[int] = set()
    for pg in pgs:
        for ln in pg:
            if ws:
                brk.add(len(ws))
            ws.extend(_words(ln))
    return ws, brk


def regress(before: list[list[str]], after: list[list[str]]) -> list[str]:
    """(f) 규칙이 오히려 나쁘게 만든 자리 — 조판 후에 **새로 생긴** 끊김이 한 덩어리(`glued`: 보조용언·의존명사·관형사 고아·굳은 구)를 가르거나,
    전에는 한 줄이던 문장이 갈렸다. 어절 열이 다르면(글이 바뀜) 비교할 수 없으니 전부 어긴 것으로 친다."""
    wb, bb = _flat(before)
    wa, ba = _flat(after)
    if wb != wa:
        return ["어절 열이 다르다"]
    out = []
    for i in sorted(ba - bb):
        if glued(wa[i - 1], wa[i]):
            out.append(f"새 끊김이 덩어리를 가름: {wa[i - 1]} | {wa[i]}")
    for i in sorted(ba - bb):  # 목적어·주어(을/를/이/가)만 줄 끝에 새로 남음 — 서술어와 갈린다
        if len(wa[i - 1]) >= 2 and wa[i - 1][-1] in "을를이가" and not kind(wa[i - 1]):
            out.append(f"새 끊김이 목적어·주어만 줄 끝에 남김: {wa[i - 1]} | {wa[i]}")
    lost = [i for i in sorted(bb - ba) if kind(wb[i - 1])]  # 전에 절 경계(문장 끝·쉼표·연결어미)에서 끝나던 줄이 후엔 경계가 아닌 자리에서 이어진다
    gained = [i for i in sorted(ba - bb) if kind(wa[i - 1])]
    lost3 = [i for i in lost if kind(wb[i - 1]) == 3]
    gained3 = [i for i in gained if kind(wa[i - 1]) == 3]
    if len(lost3) > len(gained3):
        out.append("문장 끝 경계가 문장 중간으로 옮겨감: " + " | ".join(f"{wb[i - 1]} {wb[i]}" for i in lost3[:2]))
    if len(lost) > len(gained):  # 절 경계로 끝나는 줄이 순감하면 거부(절째 내리는 고침이 경계 줄을 하나 만들며 하나를 잃는 것은 허용)
        out.append("절 경계 줄 끝이 사라짐: " + " | ".join(f"{wb[i - 1]} {wb[i]}" for i in lost[:2]))
    s = 0
    for i, w in enumerate(wa + ["."]):
        if i == len(wa) or w[-1:] in _END:
            span = range(s + 1, i + 1)
            if i < len(wa) and not any(j in bb for j in span) and any(j in ba for j in span):
                out.append("한 줄이던 문장이 갈림: " + " ".join(wa[s : i + 1]))
            s = i + 1
    return out

# ───────── 창(쪽) 분배 (마스터 10-26) ─────────


def window_stats(pgs: list[list[str]]) -> tuple[bool, bool]:
    """(h 마지막 창이 한 어절뿐, 줄 수 차가 2 이상) — 창이 둘 이상인 구간에서만."""
    if len(pgs) < 2:
        return False, False
    last = sum(len(_words(ln)) for ln in pgs[-1])
    sizes = [len(p) for p in pgs]
    return last == 1, max(sizes) - min(sizes) >= 2


def rebalance(words: list[str], fit, base: list[list[str]]) -> list[list[str]] | None:
    """창 수를 안 늘리고 마지막 창의 한 어절 고아·창 줄 수 차 2 이상을 없애는 조판을 찾는다 — 없으면 None.
    원래 쪽 시작 어절은 두고, 뒤쪽 경계(마지막, 안 되면 마지막 둘)를 옮겨 보며 `flow` 로 다시 짠다."""
    n = len(base)
    if n < 2:
        return None
    starts, k = [], 0
    for pg in base:
        starts.append(k)
        k += sum(len(ln.split(" ")) for ln in pg)
    h0, s0 = window_stats(base)
    if not (h0 or s0):
        return None
    m0 = {k: len(v) for k, v in chunk_metrics(base).items()}
    best = None
    W = len(words)

    def good(t):
        if len(t) > n or any(len(p) > PAGE_LINES for p in t):
            return False
        h, s = window_stats(t)
        m = chunk_metrics(t)
        return not h and not s and all(len(m[k]) <= m0[k] for k in m0)  # 다른 지표는 하나도 나빠지지 않아야 한다

    def score(t):
        return (count(chunk_metrics(t)), len(t))

    def okb(j, orig):  # 쪽 경계는 문장 끝 > 절 경계로만 옮긴다 — 관형어·목적어·주어 뒤는 안 끊고, 문장 끝이던 경계는 문장 끝으로만 옮긴다
        if kind(words[j - 1]) == 0 or glued(words[j - 1], words[j]):
            return False
        return kind(words[orig - 1]) < 3 or kind(words[j - 1]) == 3

    for j in range(max(starts[-1] - 40, starts[-2] + 1), W):
        if not okb(j, starts[-1]):
            continue
        pb = frozenset(starts[1:-1]) | {j}
        t = flow(words, fit, pb)
        if good(t) and (best is None or score(t) < score(best)):
            best = t
    if best is None and n >= 3:
        for i in range(starts[-2] - 30, starts[-2] + 30):
            if i <= starts[-3] or i >= W:
                continue
            for j in range(i + 1, W):
                if not (okb(i, starts[-2]) and okb(j, starts[-1])):
                    continue
                pb = frozenset(starts[1:-2]) | {i, j}
                t = flow(words, fit, pb)
                if good(t) and (best is None or score(t) < score(best)):
                    best = t
    return best
