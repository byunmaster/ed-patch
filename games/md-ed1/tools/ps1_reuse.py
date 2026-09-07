"""PS1(ps1-ed1+2) 번역을 MD 대본에 물려받는다 — 같은 원문이면 같은 우리 문안(표기·어투 일관).

    python3 tools/ps1_reuse.py            # 전 블록: 전 페이지 일치 스트림 → script/NNN.json 의 빈 ours 채움
    python3 tools/ps1_reuse.py --stats    # 일치율만

- 원문 대조 키: 공백·중점·PS1 토큰(`{c}화자{c}`·`{n}`)을 걷어낸 NFKC 문자열. MD 쪽은 스트림을 페이지(05)로
  갈라 각 페이지를 PS1 창 하나와 맞댄다. **모든 페이지가 맞는 스트림만** 채운다(부분 일치는 review 로).
- 화자 머리 스트림(`<1e>이름<04><07>`)은 `shared/glossary` person 표로 채운다.
- 출처를 `src` 에 남긴다(`ps1:ED1SCN1:123`). 사람이 고친 `ours` 는 건드리지 않는다(빈 것만 채움).
- 미일치 스트림은 work/review/ps1_reuse/NNN.txt 에 원문·근접 후보를 낸다(원문 포함 — 커밋 금지).

⚠ PS1 문안은 14칸 창에 맞춘 것이라 MD(18칸)에선 빌드가 다시 조판한다. PS1 이 창 하나에 MD 두 페이지를
합친 경우는 아직 못 맞춘다(「남은 일」).
"""

import difflib
import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene
import textmap


def _find_ps1() -> Path:
    """ps1-ed1+2 워크트리 — 이 트리가 워크트리면 본 트리(.claude/worktrees 의 두 단계 위)에서 찾는다."""
    for root in (
        common.ROOT,
        common.ROOT.parents[2] if len(common.ROOT.parents) > 2 else common.ROOT,
    ):
        p = root / ".claude" / "worktrees" / "ps1-ed1+2" / "games" / "ps1-ed1+2"
        if (p / "script").exists():
            return p
    raise SystemExit("ps1-ed1+2 워크트리를 못 찾았다 (sh scripts/worktree.sh ps1-ed1+2)")


PS1 = _find_ps1()
GLOSSARY = common.ROOT / "shared" / "glossary" / "eiyuu.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\{c\}[^{}]*\{c\}", "", s)
    s = re.sub(r"\{[a-z]\}|<[^>]*>|%[a-z]|\\n", "", s)
    return re.sub(r"[\s　･·・…‥]", "", s)


def corpus() -> dict[str, tuple[str, int, str, str | None]]:
    out = {}
    for f in sorted(glob.glob(str(PS1 / "work" / "derived" / "scn_jp" / "ED1SCN*.json"))):
        scn = Path(f).stem
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        k = json.loads((PS1 / "script" / f"{scn}.json").read_text(encoding="utf-8"))
        for e in j["entries"]:
            if e.get("kind") == "header" or not e.get("text"):
                continue
            kv = k.get(str(e["entry_id"]))
            if kv and kv.get("t"):
                out.setdefault(norm(e["text"]), (scn, e["entry_id"], kv["t"], kv.get("s")))
    return out


def stream_pages(st: scene.Stream) -> tuple[str | None, list[str]]:
    """(화자, [페이지 원문…]). 화자는 1E…04 사이 텍스트."""
    speaker = None
    pages = [[]]
    in_name = False
    for t in st.tokens:
        if t.code == 0x1E:
            in_name = True
        elif t.code == 0x04:
            in_name = False
        elif t.kind == "text":
            s = t.raw.decode("cp932", "replace")
            if in_name:
                speaker = (speaker or "") + s
            else:
                pages[-1].append(s)
        elif t.code == 0x05:
            pages.append([])
    return speaker, ["".join(p) for p in pages if "".join(p).strip()]


def match_pages(pages: list[str], cp: dict) -> list[tuple] | None:
    """MD 페이지 열 → PS1 창 열. PS1 창 하나가 MD 페이지 1~4개를 합친 경우(`{p}`)도 이어 붙여 맞춘다.
    돌려주는 건 **MD 페이지마다 하나**의 (scn, id, kr, s) — 합친 창의 kr 은 `{p}` 로 갈라 페이지에 나눈다."""
    out: list[tuple] = []
    i = 0
    while i < len(pages):
        for k in (1, 2, 3, 4):
            if i + k > len(pages):
                break
            key = norm("".join(pages[i : i + k]))
            g = cp.get(key)
            if g is None:
                continue
            parts = re.split(r"\{p\}", g[2])
            if len(parts) != k:
                # 페이지 수가 안 맞으면 전부 첫 페이지에 몰아넣는다(빌드가 다시 조판한다)
                parts = ["\f".join(parts)] + [""] * (k - 1)
            out += [(g[0], g[1], parts[j], g[3]) for j in range(k)]
            i += k
            break
        else:
            return None
    return out


def header_text(st: scene.Stream) -> str | None:
    """화자 머리 스트림이면 이름을, 아니면 None."""
    toks = [t for t in st.tokens if t.kind != "eof"]
    if len(toks) >= 3 and toks[0].code == 0x1E and toks[1].kind == "text" and toks[2].code == 0x04:
        rest = toks[3:]
        if all(t.kind != "text" for t in rest):
            return toks[1].raw.decode("cp932", "replace")
    return None


def ours_for(st: scene.Stream, kr_pages: list[str]) -> str:
    """스트림의 참조/제어 골격은 원본 순서대로, 본문 자리에 PS1 문안을 페이지(\\f)로 넣는다."""
    out = []
    page_i = 0
    text_seen = False
    for t in st.tokens:
        if t.kind == "text":
            if not text_seen:
                out.append(kr_pages[page_i] if page_i < len(kr_pages) else "")
                text_seen = True
        elif t.code == 0x05:
            page_i += 1
            text_seen = False
            out.append("\f")
        elif t.code == 0x01:
            pass
        elif t.kind == "end":
            out.append(f"<{t.code:02x}>")
        elif t.kind == "eof":
            pass
        elif t.ref:
            out.append(f"<{t.code:02x}:{t.target:04x}>")
        else:
            out.append(f"<{t.raw.hex()}>")
    return "".join(out)


def main(stats_only: bool) -> None:
    cp = corpus()
    persons = json.loads(GLOSSARY.read_text(encoding="utf-8"))["categories"]["person"]
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    tot = hit = filled = names = named_miss = 0
    review_dir = common.REVIEW_DIR / "ps1_reuse"
    review_dir.mkdir(parents=True, exist_ok=True)
    textmap.SCRIPT_DIR.mkdir(exist_ok=True)
    for n, (_, b, _) in enumerate(bl):
        mod = scene.parse_module(b)
        p = textmap.SCRIPT_DIR / f"{n:03d}.json"
        cur = (
            json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"block": n, "streams": {}}
        )
        review = []
        changed = False
        for off in sorted(mod.streams):
            st = mod.streams[off]
            key = f"{off:04x}"
            ent = cur["streams"].setdefault(key, {"jp": textmap.jp_key(st), "ours": ""})
            name = header_text(st)
            if name is not None:
                names += 1
                if name in persons:
                    if not ent["ours"] and not stats_only:
                        ent["ours"] = (
                            f"<1e>{persons[name]}<04>"
                            + ("<07>" if any(t.code == 0x07 for t in st.tokens) else "")
                            + ("<00>" if any(t.code == 0x00 for t in st.tokens) else "")
                        )
                        ent["src"] = "glossary"
                        changed = True
                else:
                    named_miss += 1
                    review.append(f"{key}\t화자 미등록\t{name}")
                continue
            _, pages = stream_pages(st)
            if not pages:
                continue
            tot += 1
            got = match_pages(pages, cp)
            if got is not None:
                hit += 1
                if not ent["ours"] and not stats_only:
                    ent["ours"] = ours_for(st, [g[2] for g in got])
                    ent["src"] = "ps1:" + ",".join(f"{g[0]}:{g[1]}" for g in got)
                    filled += 1
                    changed = True
            else:
                for pg in pages:
                    if norm(pg) not in cp:
                        near = difflib.get_close_matches(norm(pg), list(cp), n=1, cutoff=0.6)
                        cand = cp[near[0]][2] if near else ""
                        review.append(f"{key}\t{pg}\t→ {cand}")
        if changed:
            p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        if review:
            (review_dir / f"{n:03d}.txt").write_text("\n".join(review), encoding="utf-8")
    print(
        f"  본문 스트림 {hit}/{tot} 전 페이지 일치 · 이번에 채움 {filled} · 화자 머리 {names}(미등록 {named_miss})"
    )
    print(f"  미일치 후보: {review_dir}")


if __name__ == "__main__":
    main("--stats" in sys.argv)
