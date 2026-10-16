"""직접 번역할 대사 줄 목록 — PS1 과 말이 다르거나 못 맞춘 줄을 검수용 TSV 로 낸다.

`work/review/dialogue_todo_<rel>.tsv`(원문 포함이라 커밋 안 함): 열쇠 · 화자(원문) · 원문 · 닮음 · 가장 가까운 PS1 한국어 · 우리 문안(빈칸).
우리 문안은 `data/dialogue_ko.json`(커밋 — 우리가 쓴 한국어뿐)에 `rel:덩이:줄` 열쇠로 둔다. 쪽 나눔은 `\\f`.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import chapter
import common
import dialog
import dialogue
import font
import jptext
import labels
import package
import systext

_ps1_best: dict | None = None


def best_ps1():
    global _ps1_best
    if _ps1_best is None:
        _ps1_best = {}
        p = common.OUT_DIR / "align.json"
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")):
                _ps1_best[(r["rel"], r["chunk"], r["line"])] = (r["r"], r["ps1"])
    return _ps1_best


def todo_lines(rel: int):
    """[(열쇠, 화자 원문, 원문 본문(제어 {..}), Frame)] — 번역 대상(PS1 짝 없음 · 라벨/장 카드 아님 · 줄 구조 가능)."""
    mp = dialogue._load()[1]
    tab = font.GlyphTable()
    miss: set = set()
    pkg = bytes(common.track_data(rel, 128))
    own = dialogue.own()
    out = []
    for a, b in package.chunks(pkg):
        if pkg[a : a + 8] == package.SENTINEL:
            continue
        d = package.decode_chunk(pkg, a, b)[0]
        if chapter.is_chapter_chunk(d) or systext.is_menu_chunk(d):
            continue
        d2 = labels.edit_chunk(d, tab, miss)
        l1, l2 = d.split(b"\x00"), d2.split(b"\x00")
        for li, l in enumerate(l1[:-1]):
            key = f"{rel}:{a}:{li}"
            if li in mp.get((rel, a), {}) or key in own or l2[li] != l:
                continue
            t = jptext.decode(l)
            if not re.search("[ぁ-ヿ一-鿿]", re.sub(r"\{[^}]*\}", "", t)):
                continue
            if "　　　" in t:  # 장 끝 카드 따위 가운데 맞춘 판 — 따로
                continue
            f = dialog.parse_frame(l)
            if f is None:
                continue
            if any(c in f.head + f.post + f.tail for c in b"\x0c\x1a\x1b\x1d\x06"):  # 시스템 창·전투 문장 — 대사가 아니다(메시지 쪽 몫)
                continue
            out.append((key, f, t))
    return out


def write(rel: int) -> int:
    ps1, _ = dialogue._load()
    rows = []
    for key, f, t in todo_lines(rel):
        _rel, a, li = (int(x) for x in key.split(":"))
        r, refs = best_ps1().get((_rel, a, li), (0.0, []))
        kr = ""
        if refs:
            kr = " / ".join(ps1[s].get(str(i), {}).get("t", "").replace("\n", " ") for s, i in refs[:2])
        spk = dialog.page_jp(f.speaker).replace("{0E}", "") if f.speaker else ""
        body = re.sub(r"\{(0F|0E|13|14|10 [0-9A-F]{2}|11 [0-9A-F ]+)\}", "", t.split("{14}", 1)[-1]) if f.speaker else t
        rows.append("\t".join([key, spk, body.replace("\n", "|").replace("\t", " "), f"{r:.2f}", kr, ""]))
    out = common.REVIEW_DIR / f"dialogue_todo_{rel}.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    rels = [int(x) for x in sys.argv[1:]] or sorted({r for r, _ in dialogue._load()[1]})
    for rel in rels:
        print(rel, write(rel))


def write_review_own() -> int:
    """우리가 직접 쓴 줄 전부 → 검수 TSV(`work/review/dialogue_own_review.tsv`) — 열쇠 · 화자 · 원문 · 닮음 · 가장 가까운 PS1 한국어 · 우리 문안."""
    ps1, _ = dialogue._load()
    rows = []
    by_rel: dict = {}
    for key in dialogue.own():
        by_rel.setdefault(int(key.split(":")[0]), []).append(key)
    for rel in sorted(by_rel):
        pkg = bytes(common.track_data(rel, 128))
        ch = dict(package.chunks(pkg))
        for key in sorted(by_rel[rel], key=lambda k: tuple(int(x) for x in k.split(":"))):
            _r, a, li = (int(x) for x in key.split(":"))
            d = package.decode_chunk(pkg, a, ch[a])[0]
            line = d.split(b"\x00")[li]
            f = dialog.parse_frame(line)
            t = jptext.decode(line)
            spk = dialog.page_jp(f.speaker).replace("{0E}", "").replace("{0F}", "") if f and f.speaker else ""
            body = re.sub(r"\{(0F|0E|13|14|10 [0-9A-F]{2}|11 [0-9A-F ]+)\}", "", t.split("{14}", 1)[-1]) if f and f.speaker else t
            r, refs = best_ps1().get((_r, a, li), (0.0, []))
            kr = " / ".join(ps1[s].get(str(i), {}).get("t", "").replace("\n", " ") for s, i in refs[:2]) if refs else ""
            mine = dialogue.own()[key][0].replace("\f", "¶")
            rows.append("\t".join([key, spk, body.replace("\n", "|").replace("\t", " "), f"{r:.2f}", kr, mine]))
    out = common.REVIEW_DIR / "dialogue_own_review.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def write_seg(rel: int) -> int:
    """한 줄에 말이 여럿인 연출 줄(`parse_segments`) → `work/review/dialogue_seg_<rel>.tsv`: 열쇠 · 구간 수 · 원문(구간은 ` § ` 로, 화자는 `<..>`)."""
    mp = dialogue._load()[1]
    tab = font.GlyphTable()
    pkg = bytes(common.track_data(rel, 128))
    own = dialogue.own()
    rows = []
    for a, b in package.chunks(pkg):
        if pkg[a : a + 8] == package.SENTINEL:
            continue
        d = package.decode_chunk(pkg, a, b)[0]
        if chapter.is_chapter_chunk(d) or systext.is_menu_chunk(d):
            continue
        d2 = labels.edit_chunk(d, tab, set())
        l1, l2 = d.split(b"\x00"), d2.split(b"\x00")
        for li, l in enumerate(l1[:-1]):
            key = f"{rel}:{a}:{li}"
            if key in own or l2[li] != l or dialog.parse_frame(l) is not None:
                continue
            seg = dialog.parse_segments(l)
            if seg is None:
                continue
            cells = []
            for it in seg.items:
                if it[0] == "s":
                    cells.append("<" + dialog.page_jp(it[1]).replace("{0E}", "").replace("{0F}", "") + ">")
                elif it[0] == "t":
                    t = re.sub(r"\{(0F|0E|13|14|10 [0-9A-F]{2}|11 [0-9A-F ]+)\}", "", it[3]).replace("\n", "|")
                    cells.append(t)
            n = sum(1 for it in seg.items if it[0] == "t")
            rows.append(f"{key}\t{n}\t" + " § ".join(cells))
    out = common.REVIEW_DIR / f"dialogue_seg_{rel}.tsv"
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)
