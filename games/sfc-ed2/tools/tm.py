"""sfc-ed2 번역 문안 도구 — 구간(`segs`) 덤프·병합·현황. 문안 정본은 `textmap/segments.json`(주소 + 원문 해시 + 한국어).

    python3 games/sfc-ed2/tools/tm.py dump [--bank C2] [--todo]   # work/derived/segs/segs.tsv — id · 바이트 · 원문(개행 `⏎`) · PS1 제안
    python3 games/sfc-ed2/tools/tm.py put <파일>                    # `id<TAB>번역` 줄(개행 `⏎`)을 textmap/segments.json 에 병합(해시 계산)
    python3 games/sfc-ed2/tools/tm.py stats                          # 번역 진도(구간·글자)

덤프는 **원문이 들어 있어 커밋하지 않는다**(`work/derived`). PS1 제안은 같은 일본어 문장이 PS1 ED2 대본에 있을 때 그 한국어 문장이다(저본 — 원문이 같으면 PS1 문안 그대로).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import kr
import segs

OUT = common.OUT_DIR / "segs"
PS1 = common.ROOT.parent / "ps1-ed1+2" / "games" / "ps1-ed1+2"  # 워크트리 형제 폴더 — 원문 덤프(work/derived/scn_jp)는 거기 있다


def norm(s: str) -> str:
    s = re.sub(r"\{[^}]*\}|<[^>]*>", "", s)
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s・·\.、，,…ー\-]", "", s)


def ps1_index() -> dict[str, str]:
    """정규화한 PS1 일본어 문장 → PS1 한국어 문장(문장 수가 같은 블록만 쌍으로, 블록 통째도 함께)."""
    import glob

    idx: dict[str, str] = {}
    base = PS1 / "work" / "derived" / "scn_jp"
    if not base.exists():
        return idx
    for f in sorted(glob.glob(str(base / "ED2SCN*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        kj = json.load(open(PS1 / "script" / f"{j['table_id']}.json", encoding="utf-8"))
        for e in j["entries"]:
            if e.get("kind") != "block" or not e.get("text"):
                continue
            k = kj.get(str(e["entry_id"]))
            if not k or not k.get("t"):
                continue
            js = [x for x in re.split(r"(?<=[。！？!?])", re.sub(r"\{n\}|\{c\}", " ", e["text"])) if x.strip()]
            ks = [x for x in re.split(r"(?<=[.!?…])\s+", k["t"].replace("\n", " ")) if x.strip()]
            if len(js) == len(ks):
                for a, b in zip(js, ks):
                    idx.setdefault(norm(a), b.strip())
            idx.setdefault(norm(e["text"]), k["t"].replace("\n", " "))
    return idx


def dump(bank: str | None, todo: bool) -> None:
    d = common.rom_bytes()
    done = kr.load("segments")
    idx = ps1_index()
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    with (OUT / "segs.tsv").open("w", encoding="utf-8") as f:
        for a, b in segs.segments(d):
            sid = segs.seg_id(a)
            if bank and not sid.startswith("$" + bank.upper()):
                continue
            if todo and sid in done:
                continue
            jp = segs.notation(d, a, b)
            sug = ""
            for sent in re.split(r"(?<=[。！？!?])", re.sub(r"<[^>]*>", "", jp).replace("\n", " ")):
                k = idx.get(norm(sent)) if len(norm(sent)) >= 3 else None
                if k:
                    sug += k + " | "
            f.write(f"{sid}\t{b - a}\t{jp.replace(chr(10), '⏎')}\t{sug.rstrip(' |')}\n")
            n += 1
    print(f"{n:,}개 → {OUT / 'segs.tsv'}")


_SENT = re.compile(r"(?<=[。！？!?])")


def draft_text(jp: str, idx: dict[str, str]) -> tuple[str, int, int]:
    """원문 구간 → 초안. PS1 에 같은 문장이 있으면 그 한국어, 없으면 `〔원문〕` 표식. 줄바꿈(⏎)은 버리고(자동 조판) `<05>` 는 쪽 경계로 남긴다."""
    out, hit, tot = [], 0, 0
    # 쪽 경계 `<05>`·화자 머리 `<1e>…<04>` 는 그대로 두고 그 사이 본문을 문장으로 쪼갠다
    parts = re.split(r"(<[0-9a-fA-F]{2}[^>]*>|<E[01]:\d+>)", jp)
    for part in parts:
        if re.fullmatch(r"<[0-9a-fA-F]{2}[^>]*>|<E[01]:\d+>", part or ""):
            out.append(part)
            continue
        for sent in _SENT.split(part.replace("\n", " ")):
            if not sent.strip():
                continue
            tot += 1
            k = idx.get(norm(sent)) if len(norm(sent)) >= 3 else None
            if k:
                hit += 1
                out.append(k + " ")
            else:
                out.append(f"〔{sent.strip()}〕 ")
    return "".join(out).replace(" <05>", "<05>").rstrip(), hit, tot


def draft(bank: str, lo: str | None, hi: str | None) -> None:
    d = common.rom_bytes()
    done = kr.load("segments")
    idx = ps1_index()
    n = 0
    rows = []
    for a, b in segs.segments(d):
        sid = segs.seg_id(a)
        if not sid.startswith("$" + bank.upper()) or sid in done:
            continue
        if lo and sid < lo or hi and sid > hi:
            continue
        txt, h, t = draft_text(segs.notation(d, a, b), idx)
        rows.append((sid, b - a, h, t, segs.notation(d, a, b).replace("\n", "⏎"), txt))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "draft.tsv").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    print(f"{len(rows)}개 → {OUT / 'draft.tsv'}")


def autogen_appear() -> list[tuple[str, str]]:
    """`X(とY)が現れた。` 형 출현 문장 → 정본 몬스터 이름으로 자동 생성(정적 조사 `{이/가}` `{과/와}` 는 빌드가 푼다). 정본에 없는 이름이 있으면 건너뛴다."""
    import canon
    import monsters

    d = common.rom_bytes()
    ent = {(t, n): j for t, n, j in __import__("script").dict_entries(d)}
    out = []
    for a, b in segs.segments(d):
        jp = segs.notation(d, a, b).replace("\n", "")
        m = re.fullmatch(r"(.+?)が現れた。?", jp)
        if not m:
            continue
        body = re.sub(r"<E([01]):(\d+)>", lambda x: ent.get((f"E{x.group(1)}", int(x.group(2))), "?"), m.group(1)).replace("-", "ー")
        parts = body.split("と")
        krs = []
        for pn in parts:
            k = canon.lookup(pn, "monster", "ed2") or canon.lookup(pn, None, "ed2")
            if not k:
                krs = None
                break
            krs.append(k)
        if not krs:
            continue
        if len(krs) == 1:
            text = f"{krs[0]}{{이/가}} 나타났다."
        elif len(krs) == 2:
            text = f"{krs[0]}{{과/와}} {krs[1]}{{이/가}} 나타났다."
        else:
            continue
        out.append((segs.seg_id(a), text))
    return out


def put(path: str) -> None:
    d = common.rom_bytes()
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(d)}
    cur = kr.load("segments")
    n = 0
    missing: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sid, _, text = line.partition("\t")
        sid = sid.strip()
        if sid not in sg:
            missing.append(sid)
            continue
        a, b = sg[sid]
        cur[sid] = {"h": segs.src_hash(d, a, b), "kr": text.replace("⏎", "\n")}
        n += 1
    p = kr.TEXTMAP / "segments.json"
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{n}개 병합 · 총 {len(cur):,}개" + (f" · 없는 구간 {len(missing)}: {' '.join(missing[:20])}" if missing else ""))


def stats() -> None:
    d = common.rom_bytes()
    sg = segs.segments(d)
    done = kr.load("segments")
    tot = sum(1 for a, b in sg)
    ch = sum(sum(1 for i in range(a, b) if segs.is_char(d[i])) for a, b in sg)
    dc = sum(sum(1 for i in range(a, b) if segs.is_char(d[i])) for a, b in sg if segs.seg_id(a) in done)
    print(f"구간 {len(done):,}/{tot:,} · 글자 바이트 {dc:,}/{ch:,}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "dump":
        dump(next((sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--bank"), None), "--todo" in sys.argv)
    elif cmd == "draft":
        draft(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "autogen":
        rows = autogen_appear()
        outp = OUT / "auto_appear.tsv"
        outp.write_text("".join(f"{i}\t{t}\n" for i, t in rows), encoding="utf-8")
        print(f"{len(rows)}개 → {outp}")
    elif cmd == "put":
        put(sys.argv[2])
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
