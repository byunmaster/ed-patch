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
SPEAKER_CATS = ("speaker", "person")
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


def ps1_text(refs) -> str | None:
    """PS1 블록들 → 한국어 문안(블록 사이 `\\f`, 블록 안 개행은 공백). 값 넣기가 있으면 None."""
    ps1, _ = _load()
    parts = []
    for scn, i in refs:
        t = ps1[scn].get(str(i), {}).get("t")
        if t is None or re.search(r"\{[^}]*\}|[\x00-\x1f]", t.replace("\n", " ")):
            return None
        parts.append(re.sub(r" +", " ", t.replace("\n", " ")).strip())
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
        out.append((li, p, spk, txt))
    return out


def _arg18(head: bytes) -> int | None:
    """머리 제어열에서 `18` 의 위치(인자 4바이트가 뒤따르는 것만)."""
    i = 0
    while i < len(head):
        a = head[i]
        if a == 0x18:
            return i if i + 5 <= len(head) else None
        i += 1 + (jptext.ARGS.get(a, 0) if a < 0x20 else 0)
    return None


_BOUND = set(",.?!…~)」』")
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
            return flat[i - 1] in " \n" or prev in _BOUND

        for n, b in marks:
            t = max(1, min(k, round(n / jp_n * k)))
            best = min((q for q in range(max(1, t - 6), min(k, t + 6) + 1) if bound(q)), key=lambda q: (abs(q - t), q), default=t)
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
    for it in seg.items:
        if it[0] == "c":
            out += it[1]
        elif it[0] == "s":
            jp = dialog.page_jp(it[1]).replace("{0E}", "").replace("{0F}", "")
            out += b"\x16" + tab.enc(speaker_kr(jp)) + b"\x14"
        else:
            _k, lead, tail, _jp, marks, jn = it
            pgs = typeset.pages(next(parts))
            out += lead.replace(b"\x0e", b"").replace(b"\x0f", b"") + _encode(pgs, marks, jn, tab) + tail
    return bytes(out)


def chars_of(rels_chunks) -> Counter:
    """줄마다 쓰는 글자 수(줄 수 기준) — 글리프 예산 배분용."""
    c: Counter = Counter()
    for _rel, _chunk, _li, _p, spk, txt in rels_chunks:
        c.update(set(typeset.ink(txt + (spk or ""))))
    return c


def edit_chunk(rel: int, chunk: int, decoded: bytes, tab, allowed: set[str] | None) -> bytes:
    """덩이 안의 번역 가능한 줄을 한국어로 바꾼다. `allowed` = 글리프 풀에 넣을 글자(None 이면 전부)."""
    lines = decoded.split(b"\x00")
    for li, p, spk, txt in candidates(rel, chunk, decoded):
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
        pgs = typeset.pages(txt)
        body = _encode(pgs, p.marks, p.jp_n, tab)
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
    for ch, _n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        if ch not in allowed and added < budget:
            allowed.add(ch)
            added += 1
    return allowed
