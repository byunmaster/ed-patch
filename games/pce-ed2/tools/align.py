"""PCE 원문 쪽(대사 창) ↔ PS1 일본어 블록 정렬 — PS1 번역 정본(`games/ps1-ed1+2/script/`)을 PCE 줄에 잇기 위한 다리.

PCE ED2 대본은 PS1 ED2 일문과 거의 같다(첫 마을은 쪽 단위로 유사도 1.00 이 대부분). 그래서 **원문 일본어끼리** 맞대
PS1 블록의 `entry_id`(= PS1 번역 정본의 열쇠)를 찾는다 — 한국어와 일본어를 맞대는 게 아니다.
쪽 = 덩이 한 줄 안에서 `13 nn`(쪽 넘김)으로 나뉜 조각. 화자는 `16 …… 14`. PS1 블록은 `{c}화자{c}{n}본문`.
⚠ PS1 일문은 **원본에서 뽑은 파생물**이라 커밋하지 않는다 — `python3 games/ps1-ed1+2/tools/extract_scn.py` 가 `work/derived/scn_jp/` 에 만든다
(이 도구는 그 폴더가 없으면 멈춘다). 정렬 결과도 `work/derived/align.json`(gitignore) — 매핑(쪽 → PS1 씬·항목)만 커밋하는 `script/map.json` 은 다음 단계.
"""

import difflib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import jptext
import package

PS1_DIR = common.ROOT / "games" / "ps1-ed1+2"
SCN_JP = PS1_DIR / "work" / "derived" / "scn_jp"
PS1_KR = PS1_DIR / "script"
OUT = common.OUT_DIR / "align.json"
MIN_LEN = 4
GOOD = 0.85  # 같은 문장으로 보는 유사도


def norm(t: str) -> str:
    t = re.sub(r"\{[^}]*\}", "", t)
    t = unicodedata.normalize("NFKC", t)
    return re.sub(r"[\s・･、。,.!?！？\-～~…ー]", "", t)


def load_ps1() -> list[dict]:
    if not SCN_JP.exists():
        raise SystemExit(f"PS1 일문 덤프가 없다 — python3 {PS1_DIR / 'tools' / 'extract_scn.py'} 를 먼저 돌린다")
    out = []
    for n in range(1, 14):
        doc = json.loads((SCN_JP / f"ED2SCN{n}.json").read_text(encoding="utf-8"))
        for e in doc["entries"]:
            if e.get("kind") != "block":
                continue
            m = re.match(r"\{c\}([^{]*)\{c\}(.*)", e["text"], re.S)
            spk, body = (m.group(1), m.group(2)) if m else ("", e["text"])
            out.append({"scn": n, "id": e["entry_id"], "spk": spk, "n": norm(body)})
    return out


def pages_of(line: bytes) -> tuple[str, list[str]]:
    """덩이 한 줄 → (화자 원문, 쪽 일본어 목록). 화자 없는 줄(이어 가는 쪽)은 ''."""
    j = jptext.decode(line)
    m = re.match(r"\{16\}(.*?)\{14\}\n?(.*)", j, re.S)
    spk, body = (m.group(1), m.group(2)) if m else ("", j)
    return re.sub(r"\{[^}]*\}", "", spk), re.split(r"\{13[^}]*\}\n?", body)


def grams(s: str, k: int = 3):
    return {s[i : i + k] for i in range(max(1, len(s) - k + 1))}


class Index:
    def __init__(self, ps1):
        self.ps1 = ps1
        self.inv: dict[str, list[int]] = defaultdict(list)
        for i, b in enumerate(ps1):
            for g in grams(b["n"]):
                self.inv[g].append(i)

    def best(self, text: str, prefer=None) -> tuple[int, float]:
        votes: dict[int, int] = defaultdict(int)
        for g in grams(text):
            for i in self.inv.get(g, ()):
                votes[i] += 1
        cands = sorted(votes, key=lambda i: -votes[i])[:25]
        best, br = -1, 0.0
        for i in cands:
            r = difflib.SequenceMatcher(None, text, self.ps1[i]["n"]).ratio()
            if r > br + 1e-9 or (abs(r - br) < 1e-9 and prefer is not None and abs(i - prefer) < abs(best - prefer)):
                best, br = i, r
        return best, br


def line_text(line: bytes) -> tuple[str, str, str]:
    """덩이 한 줄 → (화자, 정규화한 전체 본문, 쪽 수). 쪽은 `13 nn` 으로 나뉘나 PS1 의 창 단위와 다르다 — 말(줄) 전체로 맞댄다."""
    spk, pgs = pages_of(line)
    return spk, norm("".join(pgs)), str(len(pgs))


def best_span(idx: "Index", text: str, prefer=None, max_k: int = 4):
    """말 전체와 가장 닮은 **이어진 PS1 블록 구간**(i, k, 유사도). 시작 후보는 n-그램 투표, 구간은 같은 씬 안에서 k 개까지 붙여 본다."""
    votes: dict[int, int] = defaultdict(int)
    for g in grams(text):
        for i in idx.inv.get(g, ()):
            votes[i] += 1
    starts = sorted(votes, key=lambda i: -votes[i])[:30]
    cand = set(starts)
    for i in starts:  # 뒷 블록이 본체일 수 있으니 앞쪽 이웃도 시작 후보로
        cand |= {i - 1, i - 2}
    best, br = (-1, 0), 0.0
    for i in sorted(c for c in cand if 0 <= c < len(idx.ps1)):
        joined = ""
        for k in range(max_k):
            j = i + k
            if j >= len(idx.ps1) or idx.ps1[j]["scn"] != idx.ps1[i]["scn"]:
                break
            joined += idx.ps1[j]["n"]
            r = difflib.SequenceMatcher(None, text, joined).ratio()
            if r > br + 1e-9 or (abs(r - br) < 1e-9 and prefer is not None and best[0] >= 0 and abs(i - prefer) < abs(best[0] - prefer)):
                best, br = (i, k + 1), r
    return best, br


def run(rels: list[int]) -> list[dict]:
    idx = Index(load_ps1())
    rows = []
    for rel in rels:
        pkg = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(pkg):
            if pkg[a : a + 8] == package.SENTINEL:
                continue
            d, _ = package.decode_chunk(pkg, a, b)
            prev = None
            for li, line in enumerate(d.split(b"\x00")[:-1]):
                spk, t, npg = line_text(line)
                if len(t) < MIN_LEN:
                    continue
                (i, k), r = best_span(idx, t, prev)
                if r >= GOOD and i >= 0:
                    prev = i
                rows.append(
                    {"rel": rel, "chunk": a, "line": li, "spk": spk, "pages": int(npg), "r": round(r, 3),
                     "ps1": [[idx.ps1[j]["scn"], idx.ps1[j]["id"]] for j in range(i, i + k)] if i >= 0 else []}
                )
    return rows


if __name__ == "__main__":
    rels = [int(x) for x in sys.argv[1:]] or [386]
    rows = run(rels)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    good = sum(1 for r in rows if r["r"] >= GOOD)
    print(f"말 {len(rows)} · 같은 문장(≥{GOOD}) {good} · 못 맞춘 {len(rows) - good} → {OUT}")
