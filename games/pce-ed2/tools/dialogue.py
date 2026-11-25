"""대사 줄 번역 — PCE 대사 줄 하나를 PS1 한국어 문안으로 다시 짠다.

짝(PCE 줄 ↔ PS1 블록)은 `data/align_map.json`(커밋되는 정본 — `align.py` 가 제안한 것 중 일본어끼리 닮음 ≥ 0.9 만 받아 `freeze()`)이 든다.
문안은 PS1 한국어 정본(`games/ps1-ed1+2/script/ED2SCN*.json`)에서 읽고, 화자는 정본 `canon`(speaker · person)에서 읽는다.
**단순한 줄만** 한다(`dialog.parse`: 연출 제어가 안 낀 줄) · PS1 문안에 값 넣기(`{n}` `\\x1b` 등)가 있으면 건너뛴다 · 글리프 예산 밖의 글자가 든 줄은 원문 유지.
"""

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import common
import dialog
import jptext
import package
import typeset

MAP = common.GAME_DIR / "data" / "align_map.json"
PS1 = common.ROOT / "games" / "ps1-ed1+2" / "script"
GOOD = 0.9
SPEAKER_CATS = ("speaker", "person", "item")  # item = 「{16}切符{14}を渡しました」처럼 화자 자리에 항목 이름이 오는 줄(10-16)
FALLBACK_SPEAKERS: dict = {}  # 정본에 없어 PS1 화자를 쓴 것(관리자 후보)
MISSING_SPEAKERS: Counter = Counter()  # 정본에 없는 화자(관리자 후보)

_ps1: dict | None = None
_map: dict | None = None


def freeze(align_json: Path) -> int:
    rows = [r for r in json.loads(align_json.read_text(encoding="utf-8")) if r["r"] >= GOOD and r["ps1"]]
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(
        json.dumps([[r["rel"], r["chunk"], r["line"], r["ps1"]] for r in rows], separators=(",", ":")),
        encoding="utf-8",
    )
    return len(rows)


def _load():
    global _ps1, _map
    if _map is None:
        _ps1 = {
            n: json.loads((PS1 / f"ED2SCN{n}.json").read_text(encoding="utf-8")) for n in range(1, 14)
        }
        _map = defaultdict(dict)
        for rel, chunk, line, ps1 in json.loads(MAP.read_text(encoding="utf-8")):
            _map[(rel, chunk)][line] = ps1
    return _ps1, _map


OWN_DIR = common.GAME_DIR / "data" / "dialogue_ko"
_own: dict | None = None


def own() -> dict:
    """우리가 직접 쓴 대사 — `data/dialogue_ko/*.tsv` 의 `rel:덩이:줄 <TAB> 문안(쪽 나눔 ¶) [<TAB> 화자]`. PS1 정본과 말이 다른 줄."""
    global _own
    if _own is None:
        _own = {}
        for f in sorted(OWN_DIR.glob("*.tsv")):
            for ln in f.read_text(encoding="utf-8").splitlines():
                if not ln.strip() or ln.startswith("#"):
                    continue
                cols = ln.split("\t")
                _own[cols[0]] = (cols[1].replace("¶", "\f"), cols[2] if len(cols) > 2 and cols[2] else None)
    return _own


OVERLAY = common.GAME_DIR / "data" / "ps1_overlay.tsv"
_overlay: dict | None = None


def ps1_kr(scn: int, i: int) -> str | None:
    """PS1 블록의 한국어 — `data/ps1_overlay.tsv`(PS1 역할군 등급 고침을 먼저 따르는 임시 층)가 있으면 그것, 없으면 PS1 script."""
    global _overlay
    if _overlay is None:
        _overlay = {}
        if OVERLAY.exists():
            for ln in OVERLAY.read_text(encoding="utf-8").splitlines():
                if ln and not ln.startswith("#"):
                    sc, bi, tx = ln.split("\t")[:3]
                    _overlay[(int(sc), int(bi))] = tx
    if (scn, i) in _overlay:
        return _overlay[(scn, i)]
    return _load()[0][scn].get(str(i), {}).get("t")


def kr_sentences(t: str) -> list[str]:
    """PS1 한국어 블록 → 문장 목록(`. ? !` 뒤 공백에서 끊는다) — 짝 정본의 문장 자르기(`refs` 의 `[씬, 번호, 시작, 끝)`)와 같은 칼이다(`align_check.jp_sentences` 와 문장 수가 같아야 쓴다)."""
    t = re.sub(r"\s+", " ", t.replace("\ue003", " ")).strip()
    return [x for x in re.split(r"(?<=[.?!])\s+(?=\S)", t) if x]


def ps1_text(refs) -> str | None:
    """PS1 블록들 → 한국어 문안(블록 사이 `\\f`, 블록 안 개행은 공백). 값 넣기가 있으면 None."""
    ps1, _ = _load()
    parts = []
    for scn, i, *cut in refs:
        t = ps1_kr(scn, i)
        if t is None or re.search(r"\{[^}]*\}|[\x00-\x1f]", t.replace("\n", " ")):
            return None
        lead = not parts and t.startswith("\ue003")  # 항목 이름 변수 뒤에 이어 붙는 머리(「{변수}\ue003말이군요」) — 사이 공백은 살린다(10-28 검수: 「약초말이군요」 → 「약초 말이군요」)
        t = t.replace("\ue003", " ")  # PS1 붙임 공백(사설 영역) — 그대로 두면 이쪽 글리프 표지(JOSA_MARK)로 읽혀 엉뚱한 글자로 구워진다
        t = re.sub(r" +", " ", t.replace("\n", " ")).strip()
        if cut:  # 블록의 일부 문장만(`[씬, 번호, 시작, 끝]`) — PS1 이 이웃 대사까지 한 블록에 묶은 곳
            ks = kr_sentences(t)
            assert cut[1] <= len(ks), f"PS1 {scn}:{i} 문장 자르기 {cut} — 한글 문장 {len(ks)}개(짝 정본과 어긋났다 — align_check --apply)"
            t = " ".join(ks[cut[0] : cut[1]])
        parts.append(" " + t if lead else t)
    return "\f".join(parts)


def speaker_kr(jp: str, refs=None) -> str | None:
    """정본(speaker · person) → 없으면 같은 블록의 PS1 화자(`s`). 열쇠 꼴: 장음 ー · 「역할 이름」은 ASCII 공백 한 칸 · 전각 숫자는 NFKC."""
    base = jp.replace("－", "ー").replace("\u3000", " ")
    kata = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in base)  # 가나 모드 꺼진 화자 이름(「りーだー」)도 같은 이름이다
    for cand in (base, unicodedata.normalize("NFKC", base), kata):
        for cat in SPEAKER_CATS:
            v = canon.lookup(cand, cat, "ed2")
            if v:
                return v
    if refs:
        ps1, _ = _load()
        v = ps1[refs[0][0]].get(str(refs[0][1]), {}).get("s")
        if v:
            FALLBACK_SPEAKERS[jp] = v
            return v
    return None


def covered(rel: int, chunk: int) -> set[int]:
    """이 덩이에서 대사 번역이 맡은 줄 번호(PS1 짝 + 우리 문안)."""
    out = set(_load()[1].get((rel, chunk), {}))
    out |= {int(k.split(":")[2]) for k in own() if k.startswith(f"{rel}:{chunk}:")}
    return out


def windows(jp: str) -> int:
    """원판 줄(디코드 문자열)의 창(쪽) 수 — 쪽 끝 제어(`{13}`·`{12}`) 수, 맨 끝의 것은 마지막 창을 닫을 뿐이라 센다 않는다."""
    body = re.sub(r"(?:\{1[23]\}|\{[0-9A-F]{2}(?: [0-9A-F]{2})*\}|\s)+$", "", jp)
    body = re.sub(r"^(?:\{1[23]\}|\s)+", "", body)  # 줄 머리의 대기(`{12}`)는 쪽 끝이 아니다 — 「{12}しかし…」 은 한 창이다
    return body.count("{13}") + body.count("{12}") + 1


def merge_short_windows(txt: str, headed: bool, target: int | None) -> str:
    """PS1 블록 사이 쪽 가름(`\\f`)이 원문 창 수보다 쪽을 늘리면, 블록을 이어 붙여(공백) 원문 창 수로 되돌린다
    (번역 규칙 2-10 · 2-17 맨 앞 「원문 칸은 최대한 유지」, 마스터 11-05 — 「문장마다 새 줄」·PS1 의 이웃 블록 가름이 짧은 대답·감탄·문장 앞 토막을 따로 창으로 내보내던 곳).
    이음 조합 중 쪽 수가 `target` 이하이면서 가장 큰 것(원문 창 수에 가장 가까운 것) → 이음이 가장 적은 것을 쓴다. 어느 조합도 target 에 못 미치면 쪽이 가장 적은 것."""
    if not target or "\f" not in txt:
        return txt
    parts = txt.split("\f")
    if len(parts) > 9 or len(typeset.pages(txt, headed=headed, target=target)) <= target:
        return txt
    best, key = txt, None
    for mask in range(1 << (len(parts) - 1)):  # 비트 i = parts[i] 와 parts[i+1] 을 잇는다
        cand = parts[0]
        for i in range(1, len(parts)):
            cand += (" " if mask >> (i - 1) & 1 else "\f") + parts[i].lstrip() if mask >> (i - 1) & 1 else "\f" + parts[i]
        n = len(typeset.pages(cand, headed=headed, target=target))
        k = (n > target, -n if n <= target else n, bin(mask).count("1"))
        if key is None or k < key:
            best, key = cand, k
    return best



_CUR_KEY = ""
SPLIT_KEYS: set[str] = set()  # 원문 창 수대로 쪽을 더 가른 줄의 열쇠(rel:덩이:줄) — 재촬영 대상 뽑기용(점검)


def split_to_windows(txt: str, headed: bool, target: int | None) -> str:
    """우리 문안이 원문 창 수보다 쪽이 **적으면**(원문 창 내용을 합친 꼴) 원문 창 수로 쪽을 더 가른다 — 번역 규칙 2-17(원문 창을 줄이는 것도 막는다, 마스터 11-05).
    이미 있는 쪽 가름(`\\f`)은 그대로 두고, 더 가를 자리는 문장 끝 → 쉼표 → 어절 순으로 고른다. 쪽 수가 `target` 이 되는 조합 중 길이가 고른 것을 쓴다. 가를 자리가 모자라면 그대로 둔다."""
    if not target or target < 2:
        return txt
    if len(typeset.pages(txt, headed=headed, target=target)) >= target:
        return txt
    import itertools

    forced = txt.count("\f")
    k = target - 1 - forced
    if k < 1:
        return txt
    spots: list[tuple[int, int]] = []  # (글 위치, 순위) — 순위 0 문장 끝 · 1 쉼표 · 2 어절
    for m in re.finditer(r"[ ]+", txt):
        before = txt[: m.start()]
        rank = 0 if before.endswith((".", "!", "?", "…", ".」", "!」", "?」", ".”", ".’", ".)")) else (1 if before.endswith((",", "，", "、")) else 2)
        spots.append((m.end(), rank))
    if len(spots) < k:
        return txt
    best, key = txt, None
    for tier in (0, 1, 2):
        pool = [sp for sp in spots if sp[1] <= tier]
        if len(pool) < k:
            continue
        combos = itertools.combinations(pool, k) if len(pool) <= 24 else [tuple(pool[(i + 1) * len(pool) // (k + 1) - 1] for i in range(k))]
        for cut in combos:
            out, prev = [], 0
            for c in cut:
                out.append(txt[prev : c[0]].rstrip(" "))
                prev = c[0]
            out.append(txt[prev:])
            cand = "\f".join(out)
            if any(not x.strip() for x in cand.split("\f")):
                continue
            pg = typeset.pages(cand, headed=headed, target=target)
            n = len(pg)
            lens = [len(x) for x in cand.split("\f")]
            orphan = sum(1 for p_ in pg if len(p_) > 1 and " " not in p_[-1].strip())  # 쪽 끝 줄이 낱말 하나뿐인 쪽(게이트 page_orphan)
            kk = (abs(n - target), sum(1 for x in lens if x < 5) + orphan, sum(c[1] for c in cut), max(lens) - min(lens))  # 한두 낱말만 남은 쪽(고아)을 먼저 피하고, 그다음 문장 끝 → 쉼표 → 어절 순
            if key is None or kk < key:
                best, key = cand, kk
    if best != txt:
        SPLIT_KEYS.add(_CUR_KEY)
    return best


ALIGN_LOG: dict[str, int] = {}  # 사유별 못 맞춘 수(점검용)


def _fail(why: str, txt: str) -> str:
    ALIGN_LOG[why] = ALIGN_LOG.get(why, 0) + 1
    return txt


_JP_END = re.compile(r"[。！？]+")
_KO_END = re.compile(r"(?<=[.!?])(?=\s|$)|(?<=[.!?][」』”’)])(?=\s|$)")
_KO_END_ELL = re.compile(r"(?<=[.!?])(?=\s|$)|(?<=[.!?][」』”’)])(?=\s|$)|(?<=…)(?=\s)")


def _jp_plain(jp: str) -> list[str]:
    """원판 줄(디코드 문자열)을 창 목록으로 — 제어·줄바꿈·전각 공백을 걷고 `{13}`·`{12}` 로 가른다(맨 끝 쪽 끝 제어는 창을 더하지 않는다)."""
    s = re.sub(r"\{(?!1[23]\})[^}]*\}", "", jp).replace("\n", "").replace("\u3000", "")
    s = re.sub(r"(?:\{1[23]\})+$", "", s)
    return re.split(r"\{1[23]\}", s)


def _align_by_ratio(txt: str, K: list[str], W: list[str], offs: list[int], full: str) -> str:
    """문장 수가 안 맞는 줄(원판은 쉼표로 이은 말을 한글은 마침표로 끊은 꼴 등) — 한글 문안에 쪽 가름이 없을 때만, 원판 창 경계의 글자 위치 비율에 가장 가까운
    한글 문장 끝·쉼표 뒤에 `\\f` 를 넣는다(비율 차 0.2 이내). 마지막 창이 한 어절이 되면 안 한다."""
    if len(K) != 1 or not full:
        return _fail("ratio_marks", txt)
    s = K[0]
    bs = [m.end() for m in re.finditer(r"(?<=[.!?,])(?=\s)|(?<=[.!?][」』”’)])(?=\s)", s)]
    ink = [i for i, ch in enumerate(s) if ch not in " "]
    if not bs or not ink:
        return _fail("ratio_no_boundary", txt)
    cum = [sum(1 for i in ink if i < b) / len(ink) for b in bs]
    used: list[int] = []
    for o in offs:
        r = o / len(full)
        j = min(range(len(bs)), key=lambda x: abs(cum[x] - r))
        if abs(cum[j] - r) > 0.2 or (used and bs[j] <= used[-1]):
            return _fail("ratio_far", txt)
        used.append(bs[j])
    parts, prev = [], 0
    for b in used + [len(s)]:
        parts.append(s[prev:b].strip())
        prev = b
    if not all(parts) or len(parts[-1].split()) == 1:
        return _fail("ratio_far", txt)
    return "\f".join(parts)


def align_windows(txt: str, jp: str) -> str:
    """번역 규칙 2-17(마스터 10-31 「대사 여러 칸은 최대한 칸 안의 원문을 유지하되 마지막 칸 고아 어절만 방지」) — 한글 문안의 창(`\\f`)이 원판 창보다 적으면 **원판 창 경계**에 맞춰 `\\f` 를 더한다.
    원판 창 경계가 문장 끝이면 한글 문장 수를 세어 같은 자리에 넣고, 문장 중간(쉼표 등)이면 그 문장 안의 쉼표 가운데 원판 위치 비율에 가장 가까운 곳에 넣는다.
    문장 수가 안 맞거나 기존 `\\f` 가 원판 경계와 다르거나 쉼표가 없으면 문안을 그대로 둔다(그 행은 창이 합쳐진 채 남는다 — check_layout 이 사유를 센다)."""
    W = _jp_plain(jp)
    K = txt.split("\f")
    if len(K) >= len(W):
        return txt
    full = "".join(W)
    offs, c = [], 0
    for w in W[:-1]:
        c += len(w)
        offs.append(c)  # 원판 창 경계 글자 위치
    ends = [m.end() for m in _JP_END.finditer(full)]
    ellipsis_end = set()
    for m in re.finditer(r"(?:・・・|…)+", full):
        if not full[m.end() : m.end() + 1] or full[m.end() : m.end() + 1] not in "。！？":
            ellipsis_end.add(m.end())
    ends = sorted(set(ends) | ellipsis_end)
    if not ends:
        return _fail("no_jp_end", txt)
    sj = len(ends) + (0 if ends[-1] == len(full) else 1)

    def ko_split(rx):
        return [[t.strip() for t in rx.split(k) if t.strip()] for k in K]

    ks = None
    for rx in (_KO_END, _KO_END_ELL):
        cand = ko_split(rx)
        if sum(len(x) for x in cand) == sj:
            ks = cand
            break
    if ks is None:
        return _align_by_ratio(txt, K, W, offs, full)
    flat = [s for x in ks for s in x]
    bounds = [0] + ends + ([len(full)] if ends[-1] != len(full) else [])  # JP 문장 경계(문장 i = bounds[i]..bounds[i+1])
    cuts: dict[int, str] = {}  # 한글 문장 번호 → 그 문장 뒤(또는 안)에서 가를 위치
    plan: list[tuple[int, int | None]] = []  # (문장 번호, 문장 안 쉼표 번호|None)
    for o in offs:
        if o in bounds:
            plan.append((bounds.index(o), None))  # 문장 끝에서 가른다 — 문장 번호 o 앞
        else:
            i = max(j for j in range(len(bounds) - 1) if bounds[j] < o)  # 문장 i 안
            plan.append((i, (o - bounds[i]) / max(1, bounds[i + 1] - bounds[i])))
    have, c = [], 0
    for x in ks[:-1]:
        c += len(x)
        have.append(c)
    # 기존 `\f` 가 원판 경계(문장 끝)와 어긋나면 손대지 않는다
    sent_cuts = {i for i, r in plan if r is None}
    if not set(have) <= sent_cuts:
        return _fail("cut_conflict", txt)
    out_sents = list(flat)
    marks: set[int] = set()
    for i, r in plan:
        if r is None:
            marks.add(i)
        else:
            s = flat[i]
            import linemetrics

            commas = [m.end() for m in re.finditer(r",(?=\s)", s)]
            conn = [m.end() for m in re.finditer(r"\S+(?=\s)", s) if linemetrics.kind(m.group(0)) >= 1]  # 연결어미 끝(절 경계 — 2-16 ②)
            near = lambda cs: min(cs, key=lambda e: abs(e / len(s) - r)) if cs else None  # noqa: E731
            pos = near([e for e in commas if abs(e / len(s) - r) <= 0.25]) or near([e for e in conn if abs(e / len(s) - r) <= 0.25])
            if pos is None:  # 호격(「신디,」)처럼 짧은 앞머리 쉼표뿐이라 원판 위치와 멀면 맞추지 않는다
                return _fail("ratio_far" if commas or conn else "no_comma", txt)
            out_sents[i] = s[:pos].rstrip() + "\u0001" + s[pos:].lstrip()
    parts, cur = [], []
    for i, s in enumerate(out_sents):
        cur.append(s)
        if i + 1 in marks:
            parts.append(" ".join(cur))
            cur = []
    parts.append(" ".join(cur))
    res = "\f".join(parts).replace(" \u0001", "\f").replace("\u0001", "\f")
    ws = res.split("\f")
    if not all(p.strip() for p in ws) or len(ws) < len(W):
        return _fail("bad_split", txt)
    if len(ws[-1].split()) == 1 and len(K[-1].split()) != 1:
        return _fail("orphan_last_window", txt)  # 원판 경계대로 두면 마지막 창에 한 어절만 남는다 — 2-17 이 계속 막는다(예외 ①)
    return res


def candidates(rel: int, chunk: int, decoded: bytes):
    """이 덩이에서 번역할 수 있는 줄 → [(줄 번호, 원문 파싱, 화자 한국어|None, 문안)]."""
    _, mp = _load()
    out = []
    lines = decoded.split(b"\x00")
    mine = {int(k.split(":")[2]): v for k, v in own().items() if k.startswith(f"{rel}:{chunk}:")}
    for li in sorted(set(mp.get((rel, chunk), {})) | set(mine)):
        p = dialog.parse_frame(lines[li])
        if p is None and li in mine:  # 한 줄에 말이 여럿(`16`·`1C`·`12` 로 갈림) — 구간별 번역(`§` 로 가른다)
            seg = dialog.parse_segments(lines[li])
            names = []
            if seg is not None:
                for it in seg.items:
                    if it[0] == "s":
                        jp = dialog.page_jp(it[1]).replace("{0E}", "").replace("{0F}", "")
                        names.append(speaker_kr(jp))
                        if names[-1] is None:
                            MISSING_SPEAKERS[jp] += 1
                            UNFIT[f"{rel}:{chunk}:{li}"] = f"화자 정본 없음: {jp}"
                            seg = None
                            break
            if seg is None:
                continue
            txt = mine[li][0]
            if txt.count("§") + 1 != sum(1 for it in seg.items if it[0] == "t"):
                UNFIT[f"{rel}:{chunk}:{li}"] = f"구간 수 불일치(원문 {sum(1 for it in seg.items if it[0] == 't')})"
                continue
            if ALIGN:
                pieces = txt.split("§")
                its = [it for it in seg.items if it[0] == "t"]
                txt = "§".join(align_windows(pc, it[3]) for pc, it in zip(pieces, its, strict=True))
            out.append((li, seg, "".join(names), txt))
            continue
        if p is None:
            continue
        if li in mine:  # 우리가 쓴 문안이 PS1 짝보다 앞선다
            txt, spk_over = mine[li]
            refs = None
        else:
            refs = mp[(rel, chunk)][li]
            txt, spk_over = ps1_text(refs), None
        if txt is None or not txt:
            continue
        spk = None
        if p.speaker is not None:
            jp = dialog.page_jp(p.speaker).replace("{0E}", "").replace("{0F}", "")
            spk = spk_over or speaker_kr(jp, refs)
            if spk is None:
                MISSING_SPEAKERS[jp] += 1
                UNFIT[f"{rel}:{chunk}:{li}"] = f"화자 정본 없음: {jp}"
                continue
        if spk and p.speaker is not None and txt.startswith(spk) and txt[len(spk) : len(spk) + 1] in "은는이가을를의도와과":  # `{16}항목 이름{14}는…` — 머리 상자가 이름을 이미 그린다. PS1 문안은 이름을 글에 또 담아 「{16}격파의 검{14}격파의 검은…」 이 된다(10-20 qa 1538:14:23) — 글 머리의 이름을 걷고 조사만 남긴다
            txt = txt[len(spk) :]
        if ALIGN:
            txt = align_windows(txt, jptext.decode(lines[li]))
        out.append((li, p, spk, txt))
    return _shop_verbs(out)


# 번역 규칙 4-15(마스터 11-07): 상점 주인의 존댓말 물음 「사시겠습니까?」·「파시겠습니까?」 → 「구매하시겠습니까?」·「판매하시겠습니까?」.
# 고유 말투 상인은 예외 — 덩이(상점 한 곳) 안에 「…입쇼·…습죠·…니까요」 같은 사투리·밀매상 말투가 하나라도 있으면 그 덩이는 건드리지 않는다. 「…사시겠어요?」(해요체)·메뉴 라벨(「살래요」)은 규칙 밖.
_SHOP_DIALECT = re.compile(r"입쇼|옵쇼|습죠|입죠|입니다요|십니다요|[습입십뭡]니까요")  # 「…하니까요」 같은 보통 해요체 이유 꼬리(「니까요」)는 사투리가 아니다
_SHOP_BUY = re.compile(r"사시겠습니까(?!요)")
_SHOP_SELL = re.compile(r"파시겠습니까(?!요)")


def _shop_verbs(out: list) -> list:
    if not out or any(_SHOP_DIALECT.search(t) for _li, _p, _s, t in out):
        return out
    fixed = []
    for li, p, spk, t in out:
        t2 = _SHOP_SELL.sub("판매하시겠습니까", _SHOP_BUY.sub("구매하시겠습니까", t))
        fixed.append((li, p, spk, t2))
    return fixed


def _arg18(head: bytes) -> int | None:
    """머리 제어열에서 `18` 의 위치(인자 4바이트가 뒤따르는 것만)."""
    i = 0
    while i < len(head):
        a = head[i]
        if a == 0x18:
            return i if i + 5 <= len(head) else None
        i += 1 + (jptext.ARGS.get(a, 0) if a < 0x20 else 0)
    return None


ALIGN = True  # 한글 창을 원판 창 경계에 맞춘다(규칙 2-17)
MARK_FAVOR = (1282,)  # 멈춤을 일부만 살리는 패키지(빌드 로그 「연출 타이밍 제어를 일부만 살린 패키지」) — 정적 풀의 남는 자리를 이 패키지의 글자에 먼저 준다
_BOUND = set(",.?!…~～)」』")
_SENT_PUNCT = set(".?!")
_PUNCT_RUN = set("!?.…")  # 문장 끝 부호 덩어리를 이루는 글자 — 덩어리 안에서는 멈추지 않는다
_DET = frozenset("이 그 저 이런 그런 저런 어떤 무슨 어느 새 헌 첫 온 모든 각 매 한 두 세 네 옛 웬 아무 다른 여러 온갖 이러한 그러한 저러한".split())  # 관형사 — 뒤에 명사가 와야 말이 되는 낱말
KEEP_MARKS = True  # 연출 타이밍 제어 보존 — 패키지 공간이 모자라면 빌드가 그 패키지만 끈다(`build._plan_with_local`)
MARK_LINES: int | None = None  # 타이밍 제어를 살릴 줄 수 상한(앞 줄부터) — None 이면 전부. 공간이 모자란 패키지가 가능한 만큼만 살리게 한다
_marks_used = 0  # 이번 계획에서 타이밍 제어를 살린 줄 수


def reset_marks() -> None:
    global _marks_used
    _marks_used = 0


def _encode(pgs: list[list[str]], marks, jp_n: int, tab) -> bytes:
    """조판된 쪽을 바이트로 — 원문 본문 한복판의 연출 타이밍 제어(`10 nn` 속도 · `11 nn nn` 멈춤)를 **구절 경계**에 되살린다.
    위치 = 원문에서 그 제어 앞에 있던 글자 수의 비율을 번역문 글자 수에 옮기고, 가장 가까운 어절·부호 경계로 당긴다(±6자)."""
    flat = "".join(ch for pg in pgs for line in pg for ch in line + "\n")  # 줄 끝 \n 포함 평탄화
    ink_pos = [i for i, ch in enumerate(flat) if ch not in " \n"]
    k = len(ink_pos)
    at: dict[int, list[bytes]] = {}
    global _marks_used
    if KEEP_MARKS and marks and jp_n > 0 and k > 0 and (MARK_LINES is None or _marks_used < MARK_LINES):
        _marks_used += 1
        def bound(p):  # p = 「p 번째 글자 앞」 — 글자 사이 경계인가
            if p <= 0 or p >= k:
                return p >= k
            i = ink_pos[p]
            prev = flat[ink_pos[p - 1]]
            if flat[i - 1] not in " \n" and prev not in _BOUND:
                return False
            if prev in _PUNCT_RUN and flat[i] in _PUNCT_RUN:  # 「!!」 「?!」 「…!」 한가운데는 경계가 아니다 — 멈춤이 느낌표 둘 사이에 끼었다(10-21 style 514:21:64)
                return False
            w = ""  # 바로 앞 어절 — 관형사(「이」 「그」 …) 뒤에서는 멈추지 않는다(「이 {멈춤} 사람들과」 — 원판은 「この人たちと」 뒤에서 멈춘다, 10-20 style 898:23:56)
            j = ink_pos[p - 1]
            while j >= 0 and flat[j] not in " \n":
                w = flat[j] + w
                j -= 1
            return w not in _DET

        sent_ends = [q for q in range(1, k + 1) if bound(q) and flat[ink_pos[q - 1]] in _SENT_PUNCT]  # 한글 문장 끝 뒤 경계

        taken: set[int] = set()  # 이미 멈춤이 놓인 경계 — 둘째 멈춤이 같은 자리에 붙으면(「{멈춤}{멈춤}마스터는」) 다음으로 가까운 경계로 민다(10-21 style 재검 15, 1282:22:19)
        for mk in marks:
            n, b, after_end = (*mk, False)[:3]  # 2-튜플(문장 끝 정보 없음)도 받는다
            if b[:1] == b"\x11" and len(b) == 3 and not 0x30 <= b[2] <= 0x39:
                b = b[:2] + b"0"  # 멈춤 `11 nn nn` 의 둘째 인자가 숫자가 아닌 원문(`11 35 74`)은 엔진이 첫 인자까지만 읽고 둘째를 글자로 찍는다 — 한글 앞에 낱자가 찍혔다(실화면 2690:16120:13 「ㅗ우리한테」, 10-19 전수 촬영)
            t = max(1, min(k, round(n / jp_n * k)))
            if after_end and sent_ends:  # 원문 멈춤이 문장 끝 뒤(「むかえられるんだ。{p}」)면 글자 비율이 아니라 **한글 문장 끝 뒤**에 놓는다 — 비율로만 가면 「황제 {멈춤}폐하께」처럼 명사구 안에 떨어진다(10-20 style 1282:22:64)
                best = min(sent_ends, key=lambda q: (abs(q - t), q))
            else:
                best = min((q for q in range(max(1, t - 6), min(k, t + 6) + 1) if bound(q) and q not in taken), key=lambda q: (abs(q - t), q), default=t)
            taken.add(best)
            at.setdefault(best, []).append(b)
    out = bytearray()
    ink = 0
    for pi, pg in enumerate(pgs):
        if pi:
            out += b"\x13\x0d"
        for li, line in enumerate(pg):
            if li:
                out += b"\x0d"
            for ch in line:
                if ch == " ":
                    out += tab.enc(" ")
                    continue
                for b in at.pop(ink, ()):
                    out += b
                out += tab.enc(ch)
                ink += 1
    for q in sorted(at):  # 끝(k) 위치 — 마지막 글자 뒤
        for b in at[q]:
            out += b
    return bytes(out)


def _build_seg(seg: dialog.Seg, txt: str, tab) -> bytes:
    """구간 열을 다시 짠다 — 화자는 정본, 글 덩이는 `§` 로 가른 한국어를 조판해 머리·꼬리 제어 사이에 넣는다."""
    parts = iter(txt.split("§"))
    out = bytearray()
    headed = False  # 화자 머리(`16`)를 막 낸 뒤의 첫 글 덩이만 본문 3줄 — 머리 없는 덩이는 4줄
    prev_sp = False
    glue = False  # 바로 앞 글 덩이가 `…` 로 끝났고 사이에 다른 항목이 없다 — 다음 덩이가 말로 이어지면 반각 공백(규칙 2-11, 11-06 「에휴…§정말이지」)
    for it in seg.items:
        if it[0] != "t" and not (it[0] == "c" and it[1][:1] in (b"\x10", b"\x11", b"\x12")):  # 속도·멈춤·기다림 제어는 같은 줄에서 말이 이어진다 — 쪽·화자·줄 제어만 끊는다
            glue = False
        if it[0] == "c":
            out += it[1]
        elif it[0] == "s":
            jp = dialog.page_jp(it[1]).replace("{0E}", "").replace("{0F}", "")
            out += b"\x16" + tab.enc(speaker_kr(jp)) + b"\x14"
            headed = True
        else:
            _k, lead, tail, _jp, marks, jn = it
            tgt = windows(it[3])
            blk = next(parts)
            pgs = typeset.pages(split_to_windows(merge_short_windows(blk, headed, tgt), headed, tgt), headed=headed, target=tgt)
            headed = False
            enc = _encode(pgs, marks, jn, tab)
            if glue and not prev_sp and b"\x0d" not in lead and b"\x13" not in lead and re.match(r"[가-힣A-Za-z0-9]", blk.lstrip("\n ")[:1] or " "):  # 머리 제어에 줄바꿈·쪽 넘김이 있으면 새 줄 첫머리라 공백을 넣지 않는다
                enc = tab.enc(" ") + enc
            glue = blk.rstrip().endswith("…")
            if _jp.endswith("\u3000") and not enc.endswith(b"\x60"):  # 원문 조각이 전각 공백으로 끝나면(뒤에 이름 변수가 이어 붙는 줄) 우리도 공백으로 끝낸다
                enc += b"\x60"
            out += lead.replace(b"\x0e", b"").replace(b"\x0f", b"") + enc + tail
            prev_sp = enc.endswith(b"\x60")  # 앞 덩이가 이미 공백으로 끝났으면 다음 덩이 머리에 또 넣지 않는다(「없을… {12} 터이니」 두 칸, 11-11)
    return bytes(out)


def chars_of(rels_chunks) -> Counter:
    """줄마다 쓰는 글자 수(줄 수 기준) — 글리프 예산 배분용."""
    c: Counter = Counter()
    for _rel, _chunk, _li, _p, spk, txt in rels_chunks:
        c.update(set(typeset.ink(txt + (spk or ""))))
    return c


HEAD_ONLY = re.compile(r"^(?:\{[0-9A-F ]+\})*\{16\}[^{]*(?:\{0[EF]\}[^{]*)*\{14\}\u21b5?$")  # 화자 머리만 있는 줄


def edit_chunk(rel: int, chunk: int, decoded: bytes, tab, allowed: set[str] | None) -> bytes:
    """덩이 안의 번역 가능한 줄을 한국어로 바꾼다. `allowed` = 글리프 풀에 넣을 글자(None 이면 전부)."""
    lines = decoded.split(b"\x00")
    global _CUR_KEY
    for li, p, spk, txt in candidates(rel, chunk, decoded):
        _CUR_KEY = f"{rel}:{chunk}:{li}"
        if isinstance(p, dialog.Seg):
            if allowed is not None and not set(typeset.ink(txt + (spk or ""))) <= allowed:
                STATS["예산 밖"] += 1
                UNFIT[f"{rel}:{chunk}:{li}"] = "글리프 예산 밖: " + "".join(sorted(set(typeset.ink(txt + (spk or ""))) - allowed))
                continue
            STATS["번역"] += 1
            lines[li] = _build_seg(p, txt, tab)
            continue
        if allowed is not None and not set(typeset.ink(txt + (spk or ""))) <= allowed:
            STATS["예산 밖"] += 1
            UNFIT[f"{rel}:{chunk}:{li}"] = "글리프 예산 밖: " + "".join(sorted(set(typeset.ink(txt + (spk or ""))) - allowed))
            continue
        STATS["번역"] += 1
        head = p.head
        if 0x18 in head:  # `18 + 인자 4바이트` = 이름 글자가 인자로 실린 알림 문장(「~가 동료가 되었습니다」) — 인자를 문안 첫 두 글자로 바꾼다
            k = _arg18(head)
            if k is None or " " in txt[:2] or len(tab.enc(txt[:2])) != 4:
                STATS["18 인자 불가"] += 1
                UNFIT[f"{rel}:{chunk}:{li}"] = "18 인자(이름 두 글자) 불가"
                continue
            head = head[: k + 1] + tab.enc(txt[:2]) + head[k + 5 :]
            txt = txt[2:]
        lead_sp = txt.startswith(" ")  # 변수 뒤 첫 공백 — 조판기가 머리 공백을 지우니 따로 낸다
        tgt = windows(jptext.decode(lines[li]))
        # 앞 줄이 화자 머리뿐(`16 이름 14 0D`)이면 이 줄의 첫 쪽에 이름 줄이 같이 뜬다 — 본문 3줄(원판은 이 자리에 4줄이 한 번도 없다. 11-06 642:22:6 이름이 밀려 올라갔다)
        headed = p.speaker is not None or (li > 0 and HEAD_ONLY.match(jptext.decode(lines[li - 1])) is not None)
        txt = split_to_windows(merge_short_windows(txt, headed, tgt), headed, tgt)
        pgs = typeset.pages(txt.lstrip(" "), headed=headed, target=tgt)
        body = (tab.enc(" ") if lead_sp else b"") + _encode(pgs, p.marks, p.jp_n, tab)
        if jptext.decode(lines[li]).endswith("\u3000") and not body.endswith(b"\x60"):  # 원문이 전각 공백으로 끝나면 뒤에 이름 변수·표 글자가 이어 붙는 줄이다(「ここは　」+지명+「への出口だ」) — 우리 줄도 공백으로 끝나야 「여기는큐베라」 가 안 붙는다(마스터 11-05)
            body += b"\x60"
        if p.speaker is not None:
            head += b"\x16" + tab.enc(spk) + b"\x14" + p.post
        lines[li] = head + body + p.tail
    return b"\x00".join(lines)


STATS: Counter = Counter()  # 번역함 · 글리프 예산 밖으로 원문 유지
UNFIT: dict = {}  # 열쇠 → 원문 유지 사유(마지막 계획의 것)


def _chunks_with_work() -> list[tuple[int, int]]:
    ks = set(_load()[1])
    for k in own():
        rel, chunk, _li = (int(x) for x in k.split(":"))
        ks.add((rel, chunk))
    return sorted(ks)


def package_chars() -> dict[int, set[str]]:
    """패키지별로 번역할 수 있는 줄이 쓰는 글자 모음."""
    out: dict[int, set[str]] = {}
    pk: dict = {}
    for rel, a in _chunks_with_work():
        if rel not in pk:
            p = bytes(common.track_data(rel, 128))
            pk[rel] = (p, dict(package.chunks(p)))
        p, ch = pk[rel]
        d = package.decode_chunk(p, a, ch[a])[0]
        for _li, _pf, spk, txt in candidates(rel, a, d):
            out.setdefault(rel, set()).update(typeset.ink(txt + (spk or "")))
    import codestr

    for rel, cs in codestr.chars_by_pkg().items():  # 메시지 표 밖 코드 문장(10-18)도 그 패키지가 쓰는 글자다
        out.setdefault(rel, set()).update(cs)
    return out


def choose(have: set[str], budget: int, caps: dict[int, int] | None = None) -> set[str]:
    """글리프 예산 안에서 정적 풀에 넣을 글자를 정한다.
    ① `caps`(패키지별 지역 글리프 수용량)가 있으면 **용량을 넘는 패키지의 넘침을 가장 많이 줄이는 글자**부터(넘친 패키지 수 · 줄 수 · 코드포인트순)
    ② 그다음 줄 수 많은 글자부터 채운다. 결정적이다."""
    pc = package_chars()
    cands = []
    for rel, a in _chunks_with_work():
        pass
    freq: Counter = Counter()
    pk: dict = {}
    for rel, a in _chunks_with_work():
        if rel not in pk:
            p = bytes(common.track_data(rel, 128))
            pk[rel] = (p, dict(package.chunks(p)))
        p, ch = pk[rel]
        d = package.decode_chunk(p, a, ch[a])[0]
        for _li, _pf, spk, txt in candidates(rel, a, d):
            freq.update(set(typeset.ink(txt + (spk or ""))))
    allowed = set(have)
    added = 0
    if caps is not None:
        miss = {rel: len(cs - allowed) for rel, cs in pc.items()}
        while added < budget:
            over = {rel for rel, m in miss.items() if m > caps.get(rel, 255)}
            if not over:
                break
            gain: Counter = Counter()
            for rel in over:
                for ch in pc[rel] - allowed:
                    gain[ch] += 1
            if not gain:
                break
            best = max(gain, key=lambda c: (gain[c], freq[c], -ord(c)))
            allowed.add(best)
            added += 1
            for rel, cs in pc.items():
                if best in cs:
                    miss[rel] -= 1
    # 남는 자리는 **연출 멈춤을 일부만 살린 패키지**(`MARK_FAVOR` — 꼬리 자리가 모자라 멈춤을 못 살리는 곳)가 쓰는 글자부터 — 그 글자가 정적 풀에 있으면 그 패키지의 지역 글리프(16B 씩)가 줄어 그만큼 멈춤(3B 씩)이 산다(10-20 1282 멈춤 7개 소실)
    def favor(ch: str) -> int:
        return sum(1 for rel in MARK_FAVOR if ch in pc.get(rel, ()))

    for ch, _n in sorted(freq.items(), key=lambda kv: (-favor(kv[0]), -kv[1], kv[0])):
        if ch not in allowed and added < budget:
            allowed.add(ch)
            added += 1
    return allowed
