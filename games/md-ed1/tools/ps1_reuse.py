"""PS1(ps1-ed1+2) 번역을 MD 대본에 물려받는다 — 같은 원문이면 같은 우리 문안(표기·어투 일관).

    python3 tools/ps1_reuse.py --stats      # 일치율만 (정본 안 건드림)
    python3 tools/ps1_reuse.py --propose    # ⭐ 제안 파일 + 검토표만 (정본 안 건드림)
    python3 tools/ps1_reuse.py --apply      # 제안 파일 → 정본 (⚠ 대량 변경, 유저 판정 뒤)
    python3 tools/ps1_reuse.py --block 104  # 위 어느 것에나 붙는다 — 그 블록만
    python3 tools/ps1_reuse.py              # (모드 없이) 훑으며 바로 정본에 — 한 블록씩 쓸 때만

- 원문 대조 키: 공백·중점·PS1 토큰(`{c}화자{c}`·`{n}`)을 걷어낸 NFKC 문자열. MD 쪽은 스트림을 페이지(05)로
  갈라 각 페이지를 PS1 창 하나와 맞댄다. **모든 페이지가 맞는 스트림만** 채운다(부분 일치는 review 로).
- 화자 머리 스트림(`<1e>이름<04><07>`)은 `shared/glossary` person 표로 채운다.
- 출처를 `src` 에 남긴다(`ps1:ED1SCN1:123`). 사람이 고친 `ours` 는 건드리지 않는다(빈 것만 채움).
- 미일치 스트림은 work/review/ps1_reuse/NNN.txt 에 원문·근접 후보를 낸다(원문 포함 — 커밋 금지).

⚠ **전 블록 채우기는 대량 변경이다**(정본 225 파일). 그 전에 `--block` 으로 **한 블록만 채워
인게임까지** 본다 — 「연쇄 스트림」(한 뿌리 뒤로 물리적으로 이어지는 대사)이 실물로 있는지는 그렇게만
확인된다(`docs/status.md` 「남은 일」 12).

⚠ PS1 문안은 14칸 창에 맞춘 것이라 MD(18칸)에선 빌드가 다시 조판한다. PS1 이 창 하나에 MD 두 페이지를
합친 경우는 아직 못 맞춘다(「남은 일」).
"""

import collections
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


def names_table() -> dict[str, str]:
    """이름 자리에 올 수 있는 것 = **사람 + 물건**. `<1e>…<04>` 는 화자 전용이 아니다.

    「촛대를 손에 넣었다」류에서 아이템 이름이 그 자리에 온다(실측: しょく台 · 王家のつるぎ ·
    ギルモアの涙 …). 사람 용어집만 보면 그 스트림이 통째로 후보에서 빠진다.
    """
    out = {
        k: v
        for cat in json.loads(GLOSSARY.read_text(encoding="utf-8"))["categories"].values()
        if isinstance(cat, dict)
        for k, v in cat.items()
        if isinstance(v, str)
    }
    tbl = json.loads((common.GAME_DIR / "textmap" / "names.json").read_text(encoding="utf-8"))
    for name in ("item", "spell", "place_a", "place_b"):
        for e in tbl.get(name, {}).values():
            if isinstance(e, dict) and e.get("jp") and e.get("ours"):
                out.setdefault(e["jp"], e["ours"])
    return out


def norm(s: str) -> str:
    """대조 키 — 원문이 「같은 대사인가」만 남긴다.

    ⚠ 세 자리를 안 걷어내면 **같은 대사가 안 맞는다**(2026-09-07 실측: 69.1% → 80.1%):

    1. **PS1 덤프의 `\\xNN` 이스케이프** — PS1 추출기는 SJIS 로 못 읽은 바이트를 escape 로 남긴다.
       그중엔 평범한 반각 `!`(0x21) · `?`(0x3F) · **이름 자리 `%s`**(0x25 0x73)가 섞여 있어, MD 의
       `!!` 와 PS1 의 `\\x21\\x21` 이 다른 글자가 된다(이것만으로 +216 스트림).
    2. **문장 부호** — 리메이크가 `。`·`、`·`!` 를 넣거나 뺀 자리가 있다(+25). 뜻은 같다.
    3. `{c}…{c}`(화자) · `{n}`(개행) · `<…>`(MD 제어코드) — 표현 계층이라 대조에 안 쓴다.
    """
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\\x([0-9A-Fa-f]{1,2})", lambda m: chr(int(m.group(1), 16)), s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\{c\}[^{}]*\{c\}", "", s)
    s = re.sub(r"\{[a-z]\}|<[^>]*>|%[a-z]|\\n", "", s)
    s = re.sub(r"[。、！？!?,.・]", "", s)
    return re.sub(r"[\s　･·・…‥]", "", s)


def corpus() -> dict[str, tuple[str, int, str, str | None]]:
    """{원문 키: (scn, id, 우리 문안, 화자)} — PS1 정본 전량.

    🔴 **같은 원문에 다른 문안이 붙은 자리가 126 있다.** 예전엔 먼저 만난 것을 썼는데(`setdefault`),
    그게 하필 PS1 의 **복제 방지 부활절 달걀**이었다 — 신부의 「困ったことが あったら…」 50 항목 중
    하나만 문안이 「하느님도 불법 복제만큼은…」이라, MD 의 신부 **52 자리**가 통째로 그 문장이 됐다
    (2026-09-07 시험 적용에서 잡았다). ⇒ **가장 많이 쓰인 문안**을 고른다. 동수면 scn·id 순 —
    입력이 같으면 결과가 같아야 한다(「빌드는 결정적이어야 한다」).
    """
    cand: dict[str, dict[str, tuple[str, int, str, str | None]]] = {}
    count: dict[str, collections.Counter] = {}
    for f in sorted(glob.glob(str(PS1 / "work" / "derived" / "scn_jp" / "ED1SCN*.json"))):
        scn = Path(f).stem
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        k = json.loads((PS1 / "script" / f"{scn}.json").read_text(encoding="utf-8"))
        for e in j["entries"]:
            if e.get("kind") == "header" or not e.get("text"):
                continue
            kv = k.get(str(e["entry_id"]))
            if not (kv and kv.get("t")):
                continue
            key = norm(e["text"])
            cand.setdefault(key, {}).setdefault(kv["t"], (scn, e["entry_id"], kv["t"], kv.get("s")))
            count.setdefault(key, collections.Counter())[kv["t"]] += 1
    out = {}
    for key, byt in cand.items():
        best = min(byt, key=lambda t: (-count[key][t], byt[t][0], byt[t][1]))
        out[key] = byt[best]
    return out


def stream_pages(st: scene.Stream) -> tuple[list[str], list[str]]:
    """([화자…], [페이지 원문…]). 화자는 `1E…04` 사이 텍스트 — **여럿일 수 있다.**

    ⚠ 한 스트림에 화자가 둘 이상인 자리가 106 있다(두 사람이 주고받는 대화). 예전엔 이걸 이어
    붙여 한 이름으로 돌려줘서 `アクダムセリオスアクダム` 같은 값이 나왔고, 용어집에 없으니
    **112 스트림이 통째로 후보에서 빠졌다**(2026-09-07).
    """
    speakers: list[str] = []
    pages = [[]]
    in_name = False
    for t in st.tokens:
        if t.code == 0x1E:
            in_name = True
            speakers.append("")
        elif t.code == 0x04:
            in_name = False
        elif t.kind == "text":
            s = t.raw.decode("cp932", "replace")
            if in_name:
                speakers[-1] += s
            else:
                pages[-1].append(s)
        elif t.code == 0x05:
            pages.append([])
    return speakers, ["".join(p) for p in pages if "".join(p).strip()]


def name_changes_midpage(st: scene.Stream) -> bool:
    """쪽 넘김 없이 화자가 바뀌는가 — 그런 자리(5)는 **채우지 않는다**.

    한 쪽에 본문이 두 토막이면 어느 토막에 어느 문안을 넣을지 정할 근거가 없다(원문 쪽 수와
    우리 쪽 수가 1:1 이 아니게 된다). 잘못 넣느니 원문으로 남긴다.
    """
    body = False
    for t in st.tokens:
        if t.code == 0x1E:
            if body:
                return True
        elif t.code == 0x05:
            body = False
        elif t.kind == "text":
            body = True
    return False


def kr_text(s: str) -> str:
    """PS1 문안 → MD 에 넣을 문안. **PS1 표기 계층을 걷어낸다.**

    PS1 은 14칸 창에 맞춰 `{n}`(줄바꿈)을 문안에 박아 두는데, MD 는 18칸이라 빌드가 다시 조판한다.
    그대로 넣으면 `{`·`}` 가 **화면에 나갈 글자**가 되어 「반각 글리프가 없다」로 빌드가 죽는다
    (2026-09-07 전 블록 시험 적용에서 5건). `{c}화자{c}` 도 남아 있으면 걷는다.
    """
    s = re.sub(r"\{c\}[^{}]*\{c\}", "", s)
    s = re.sub(r"\{n\}", " ", s)
    s = re.sub(r"\{[a-z]\}", "", s)
    # PS1 은 늘임표에 반각 `~` 를 쓰는데 MD 반각 글꼴(리소스 1)엔 그 글리프가 없다 —
    # 원본이 쓰는 **전각 `～`**(표 0 에 살아 있다)로 바꾼다. 안 바꾸면 빌드가 죽는다(21건).
    s = s.replace("~", "～")
    return re.sub(r"  +", " ", s).strip()


PLACEHOLDER = re.compile(r"[\x00-\x1f]")


def has_placeholder(s: str) -> bool:
    """PS1 문안에 **자리표시자 제어바이트**가 남았나 — 남았으면 물려받지 않는다.

    PS1 은 이름(`\x1a`)·아이템(`\x17`)·수(`\x1b`)를 문안 안에 제어바이트로 심고, 굳은 줄바꿈에
    `\n` 을 쓴다. MD 는 같은 뜻을 **자기 제어코드**(`<0b>`·`<0e>`·`<09 nn>`)로 내고 줄바꿈은 조판기가
    다시 잡으므로, 그대로 옮기면 자리표시자가 **두 벌**이 되거나 글리프가 없어 빌드가 죽는다.
    17 스트림뿐이라 **손으로 쓸 자리**로 넘긴다(2026-09-07 전 블록 시험에서 잡았다).
    """
    return bool(PLACEHOLDER.search(s))


def match_pages(pages: list[str], cp: dict) -> list[tuple] | None:
    """MD 페이지 열 → PS1 창 열. PS1 창 하나가 MD 페이지 1~4개를 합친 경우(`{p}`)도 이어 붙여 맞춘다.
    돌려주는 건 **MD 페이지마다 하나**의 (scn, id, kr, s) — 합친 창의 kr 은 `{p}` 로 갈라 페이지에 나눈다."""
    out: list[tuple] = []
    i = 0
    while i < len(pages):
        # ⚠ 「자리가 모자라 못 맞춘 것」과 「안 맞은 것」을 같이 처리해야 한다 — 예전엔 `break` 가
        # for…else 를 건너뛰어 같은 i 로 while 이 계속 돌았다(마지막 페이지에서 **무한 루프**, 2026-09-06).
        matched = False
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
            out += [(g[0], g[1], kr_text(parts[j]), g[3]) for j in range(k)]
            i += k
            matched = True
            break
        if not matched:
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


def header_ours(st: scene.Stream, kr: str) -> str:
    """화자 머리 스트림 → 정본 문안. 이름만 갈고 **나머지 토큰은 전부 그대로** 둔다.

    🔴 예전엔 `<1e>이름<04>` 에 끝 코드만 붙여 새로 지었는데, 머리 스트림에도 **참조·인자 딸린 제어가
    붙는 자리**가 있다(블록 104 의 `0xc36` = `<1e>빵집<04><01><120001><0f:0d9c>`). 그걸 버리면
    빌드가 「원본의 참조가 정본에 없다」로 죽는다(2026-09-07).
    """
    out = []
    for t in st.tokens:
        if t.kind == "text":
            out.append(kr)
        elif t.kind == "eof":
            pass
        elif t.kind == "end":
            out.append(f"<{t.code:02x}>")
        elif t.ref:
            out.append(f"<{t.code:02x}:{t.target:04x}>")
        else:
            out.append(f"<{t.raw.hex()}>")
    return "".join(out)


def ours_for(st: scene.Stream, kr_pages: list[str], speakers_kr: list[str] | None = None) -> str:
    """스트림의 참조/제어 골격은 원본 순서대로, 본문 자리에 문안을 페이지(\\f)로 넣는다.

    🔴 **화자가 스트림 안에 있는 자리가 있다** — `<1e>라이아스<04><01>` 뒤에 본문이 이어진다
    (머리 스트림으로 갈려 있는 자리와 섞여 있다). 그 이름 토큰을 「첫 본문」으로 세면 **1쪽이 이름
    칸에 들어가고 마지막 쪽이 통째로 사라진다.** 2026-09-07 인게임 실측: 라이아스의 훈계가 이름
    자리에 박혀 쪽 넘김 없이 네 줄이 흘렀다. 이름 뒤의 `<01>`(이름과 본문을 가르는 줄바꿈)도
    같이 살린다 — 본문 안의 `<01>` 은 조판기가 다시 넣으므로 버린다.
    """
    out = []
    page_i = 0
    name_i = 0
    text_seen = False
    in_name = False
    prev_text = False
    for t in st.tokens:
        was_text = t.kind == "text"
        if t.kind == "text":
            if in_name:
                # 화자는 **자리마다** 다르다(한 스트림에 둘 이상)
                kr = (speakers_kr or [])[name_i] if name_i < len(speakers_kr or []) else None
                out.append(kr or t.raw.decode("cp932", "replace"))
                name_i += 1
            elif not text_seen:
                out.append(kr_pages[page_i] if page_i < len(kr_pages) else "")
                text_seen = True
        elif t.kind == "eof":
            pass
        elif t.kind == "end":
            out.append(f"<{t.code:02x}>")
        elif t.ref:
            out.append(f"<{t.code:02x}:{t.target:04x}>")
        elif t.code == 0x1E:
            in_name = True
            out.append("<1e>")
        elif t.code == 0x04:
            in_name = False
            out.append("<04>")
        elif t.code == 0x05:
            page_i += 1
            text_seen = False
            out.append("\f")
        elif t.code == 0x01:
            if not prev_text:
                out.append("<01>")
        else:
            out.append(f"<{t.raw.hex()}>")
        prev_text = was_text
    return "".join(out)


PROPOSAL = common.REVIEW_DIR / "ps1_reuse" / "proposal.json"


def main(mode: str, only: set[int] | None = None) -> None:
    """mode: stats(재기만) · propose(제안 파일만) · apply(제안을 정본에) · fill(훑으며 바로 정본에).

    🔴 **정본을 바꾸는 건 `apply`·`fill` 뿐이다.** `propose` 는 `work/review/` 에만 쓴다 —
    대량 채우기는 유저 판정이 필요한데(정본 225 파일), 판정을 기다리는 동안에도 **재 놓을 수는**
    있어야 하기 때문이다. 판정이 나면 `--apply` 가 그 제안을 그대로 넣는다(다시 대조하지 않는다 →
    같은 입력이면 같은 결과, 「빌드는 결정적이어야 한다」).
    """
    stats_only = mode == "stats"
    if mode == "apply":
        return apply_proposal(only)
    cp = corpus()
    cp_keys = list(cp)  # difflib 후보 — 한 번만 만든다
    persons = names_table()
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    tot = hit = filled = names = named_miss = 0
    review_dir = common.REVIEW_DIR / "ps1_reuse"
    review_dir.mkdir(parents=True, exist_ok=True)
    textmap.SCRIPT_DIR.mkdir(exist_ok=True)
    proposal: dict[str, dict[str, dict[str, str]]] = {}
    for n, (_, b, _) in enumerate(bl):
        if only is not None and n not in only:
            continue
        mod = scene.parse_module(b)
        p = textmap.SCRIPT_DIR / f"{n:03d}.json"
        cur = (
            json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"block": n, "streams": {}}
        )
        review = []
        changed = False

        def put(key, ours, src, *, cur=cur, n=n):
            """제안이면 제안 파일에, 아니면 정본에."""
            if mode == "propose":
                proposal.setdefault(f"{n:03d}", {})[key] = {"ours": ours, "src": src}
                return False
            cur["streams"][key]["ours"] = ours
            cur["streams"][key]["src"] = src
            return True

        for off in sorted(mod.streams):
            st = mod.streams[off]
            key = f"{off:04x}"
            ent = cur["streams"].setdefault(key, {"jp": textmap.jp_key(st), "ours": ""})
            name = header_text(st)
            if name is not None:
                names += 1
                if name in persons:
                    if not ent["ours"] and not stats_only:
                        changed |= put(key, header_ours(st, persons[name]), "glossary")
                else:
                    named_miss += 1
                    review.append(f"{key}\t화자 미등록\t{name}")
                continue
            speakers, pages = stream_pages(st)
            # 화자가 스트림 안에 있는 자리 — 용어집에 없으면 **채우지 않는다**(이름이 원문으로 남는다)
            speakers = [sp for sp in speakers if sp]  # `<1e><04>` 빈 이름은 이름이 아니다
            miss = [sp for sp in speakers if sp not in persons]
            if miss:
                named_miss += 1
                review.append(f"{key}\t스트림 안 화자 미등록\t{' · '.join(miss)}")
                continue
            if len(speakers) > 1 and name_changes_midpage(st):
                named_miss += 1
                review.append(f"{key}\t쪽 넘김 없이 화자가 바뀐다\t{' · '.join(speakers)}")
                continue
            speakers_kr = [persons[sp] for sp in speakers]
            if not pages:
                continue
            tot += 1
            got = match_pages(pages, cp)
            if got is not None and any(has_placeholder(g[2]) for g in got):
                review.append(f"{key}\tPS1 자리표시자가 남았다 — 손으로\t{got[0][2][:40]!r}")
                got = None
            if got is not None:
                hit += 1
                if not ent["ours"] and not stats_only:
                    src = "ps1:" + ",".join(f"{g[0]}:{g[1]}" for g in got)
                    changed |= put(key, ours_for(st, [g[2] for g in got], speakers_kr), src)
                    filled += 1
                if mode == "propose":
                    for pi, pg in enumerate(pages):
                        review.append(
                            f"{key}\t쪽{pi}\t{pg}\t✅ {got[pi][2] if pi < len(got) else ''}"
                        )
            elif not stats_only:
                # ⚠ 근사 후보는 **검토표용**이라 통계에선 만들지 않는다 — 페이지마다 3,600 후보와
                # difflib 를 돌리면 전 블록에 몇 시간이 든다(2026-09-06 실측: --stats 가 40분 넘게 안 끝났다).
                for pi, pg in enumerate(pages):
                    if norm(pg) not in cp:
                        near = difflib.get_close_matches(norm(pg), cp_keys, n=1, cutoff=0.6)
                        cand = cp[near[0]][2] if near else ""
                        review.append(
                            f"{key}\t쪽{pi}\t{pg}\t{'≈ ' + cand if cand else '(후보 없음)'}"
                        )
        if changed:
            p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        if review:
            (review_dir / f"{n:03d}.txt").write_text("\n".join(review), encoding="utf-8")
    if mode == "propose":
        PROPOSAL.write_text(json.dumps(proposal, ensure_ascii=False, indent=1), encoding="utf-8")
        cnt = sum(len(v) for v in proposal.values())
        print(f"  제안 {cnt} 스트림 · 블록 {len(proposal)} → {PROPOSAL}")
        print("  ⚠ 정본은 안 건드렸다 — 판정이 나면 `--apply`")
    print(
        f"  본문 스트림 {hit}/{tot} 전 페이지 일치 · 채움 {filled} · 화자 머리 {names}(미등록 {named_miss})"
    )
    print(f"  검토표: {review_dir}")


def apply_proposal(only: set[int] | None = None) -> None:
    """제안 파일 → 정본. **빈 `ours` 에만** 넣는다(사람이 고친 문안은 안 건드린다)."""
    if not PROPOSAL.exists():
        raise SystemExit(f"제안 파일이 없다: {PROPOSAL} — 먼저 `--propose`")
    prop = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    # 손으로 쓴 초벌도 같이 넣는다(`tools/draft.py --propose`) — PS1 이 못 닿은 자리다.
    # ⚠ 겹치지 않는다: 초벌은 **PS1 이 못 맞춘 스트림**에만 나온다.
    extra = common.REVIEW_DIR / "draft" / "draft_proposal.json"
    if extra.exists():
        for bn, ss in json.loads(extra.read_text(encoding="utf-8")).items():
            prop.setdefault(bn, {}).update(ss)
        print(f"  초벌 제안도 같이 읽었다: {extra}")
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    put = skip = 0
    for bn, streams in sorted(prop.items()):
        n = int(bn)
        if only is not None and n not in only:
            continue
        p = textmap.SCRIPT_DIR / f"{bn}.json"
        mod = scene.parse_module(bl[n][1])
        cur = (
            json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"block": n, "streams": {}}
        )
        for key, v in sorted(streams.items()):
            st = mod.streams[int(key, 16)]
            ent = cur["streams"].setdefault(key, {"jp": textmap.jp_key(st), "ours": ""})
            if ent["ours"]:
                skip += 1
                continue
            ent["ours"], ent["src"] = v["ours"], v["src"]
            put += 1
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  정본에 넣음 {put} · 이미 차 있어 건너뜀 {skip} · 파일 {len(prop)}")


def _only() -> set[int] | None:
    if "--block" not in sys.argv:
        return None
    i = sys.argv.index("--block")
    if i + 1 >= len(sys.argv):
        raise SystemExit("--block 뒤에 블록 번호를 준다 (쉼표로 여럿)")
    return {int(x) for x in sys.argv[i + 1].split(",")}


if __name__ == "__main__":
    _mode = "stats"
    for _m in ("propose", "apply", "stats"):
        if f"--{_m}" in sys.argv:
            _mode = _m
            break
    else:
        _mode = "fill"
    main(_mode, _only())
