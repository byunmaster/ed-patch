#!/usr/bin/env python3
"""키 대기(`[키]`, 제어값 9) 뒤에 **같은 창에서 이어 그려지는 블록**의 커서 위치를 대사 보기 캡처 색인에서 뽑아 `script/key_cont.json` 에 둔다.

    python3 tools/derive_key_cont.py <대사 보기 폴더> [<폴더> …]   # ED2: scene-ed2-r5 · ED1: scene-ed1-r2 (index.json)

🔴 왜 필요한가(2026-10-19 qa — 「보여라.죄수번호 8/93번」·「없잖아.응!?그/렇지!!」): 씬 스크립트는 `%c` 로 끝나는 블록을 **키 대기 뒤 같은 줄에서 폭 2.0 의 빈 칸 다음**에 이어 그린다. 블록은 따로
조판돼 **앞 줄이 어디서 끝났는지 모르므로** 첫 줄이 남은 폭을 넘으면 엔진이 낱말 한가운데서 접는다. 어디서 이어지는지는 스크립트(번호별 실행 결과)에만 있어서
**한 번 실측해 정본으로 박아 둔다**(제안은 비결정적이어도 빌드는 정본만 읽는다 — CLAUDE.md 제1원칙). 빌드는 `patch_scn.key_cont_fix` 가 이 파일만 읽는다.

산출 `{"<게임>": {"<원문 열쇠>": <커서 폭(전각 칸 — 앞 줄 폭. **키 대기는 빈 칸을 안 그린다**: 2026-10-19 캡처 실측 — ED2 S45 id051 「…」 열 개가 틈 없이 이어지고 ED1 S32 id002 「보여라.죄수번호」도 붙는다)>}}` — **그 블록이 나타난 모든 자리에서 키 대기 이음이고 폭이 같을 때만** 담는다(자리마다 갈리면 못 믿는다).
"""

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

OUT = os.path.join(HERE, "..", "script", "key_cont.json")
CTL = re.compile(r"\[끝\]|\[키\]|<0[0-9a-f]>|\[창\]")


def decode_fn():
    """스크립트 hex → 글자(`ss_scene_sweep` 와 같은 한글 슬롯 역표)."""
    import font

    m = json.load(open(os.path.join(HERE, "..", "hangul_map_11kanji.json"), encoding="utf-8"))["syllables"]
    rev = {bytes(font.sjis_of_index(v)): k for k, v in m.items()}

    def dec(hexs):
        b = bytes.fromhex(hexs)
        out, i = [], 0
        while i < len(b):
            c = b[i]
            if c < 0x80 or 0xA0 <= c <= 0xDF:
                out.append({0x0A: "⏎", 0x02: "[창]", 0x01: "[/이름]", 0x08: "[끝]", 0x09: "[키]"}.get(c, chr(c) if c >= 0x20 else f"<{c:02x}>"))
                i += 1
            else:
                p = b[i : i + 2]
                k = rev.get(p)
                if k is None:
                    try:
                        k = p.decode("cp932")
                    except UnicodeDecodeError:
                        k = "?"
                out.append(k)
                i += 2
        return "".join(out)

    return dec


def width(s):
    from font import HALF_QUOTES

    return sum(0.5 if c.isascii() or c in HALF_QUOTES else 1 for c in s)


def norm(t):
    return re.sub(r"%[a-zA-Z]|\[[^\]]*\]|<[0-9a-f]{2}>|[\s⏎]", "", t)


PAGE_ROWS_G = {"ED1": 6, "ED2": 5}  # 원판 창 — ED2 이름 + 본문 4줄(5행)·ED1 이름 + 본문 5줄(6행), 6째/7째 행은 ▽ 자리(2026-10-19 원판 JP 대조 jp-cmp/)
SENT_END = (".", "!", "?", "…", "」", "다")


def static_pages(canon, chains):
    """🔴 쪽 가르기 표를 **체인 표와 현재 문안만으로** 새로 계산한다 — 낡은 캡처(옛 빌드가 이미 가른 쪽)에 기대지 않는다(10-19 qa r6).
    체인(한 창에 이어 그려지는 블록 열쇠 열)마다 문안을 이어 붙여(게이트 `check_page_rows` 와 같은 모양) 행 수가 한도를 넘거나(ED2 5·ED1 6)
    ED1 꽉 찬 쪽의 마지막 줄이 ▽ 칸을 넘으면, 쪽마다 컷을 **한 번만** 고른다 — 문장 끝 → 연결어미 → 고아 방지, 화자 머리 줄 뒤 금지·앞 최선
    (`patch_scn.best_cut`). 컷은 그 줄이 **시작되는** 블록의 줄 번호 j(j=0 이면 블록 머리 앞)로 적는다. → `{게임: {열쇠: [j]}}`."""
    import common
    import patch_scn as P
    import check_page_rows as CPR

    f, mm = common.open_image(os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin"))
    P._scn_cuts()  # 표 적재
    saved = P._KEY_CONT["pages"]
    P._KEY_CONT["pages"] = {}  # 컷 없는 문안으로 잰다
    try:
        by_key = {}
        for path, _l, _s in common.iso_files(mm):
            if not P.DIALOG_RE.match(path):
                continue
            got = P.load(path)
            if not got:
                continue
            sites = P.sites_for(path)
            for e in got[1]:
                jp = e.get("text", "")
                if jp:
                    off = int(e["file_offset"], 16)
                    k = P.line_key(jp)
                    if k not in by_key:
                        kr = P.canon_of(canon, jp, sites.get(off), path=path, off=off)
                        if kr:
                            by_key[k] = kr.replace("\x08", "\n")  # 블록 안 자동 컷도 줄 바꿈으로 — 컷을 처음부터 다시 고른다
    finally:
        P._KEY_CONT["pages"] = saved
    out = collections.defaultdict(dict)
    for game, cs in chains.items():
        limit, tri = P.PAGE_LIMIT[game], P.TRI_W.get(game)
        for keys in cs:
            if not all(k in by_key for k in keys):
                continue
            texts = [by_key[k] for k in keys]
            # 줄 번호 = 앞 블록들의 `\n` 수 — 화자 머리(`%c이름%c\n`)는 한 줄이다
            starts, acc, joined = [], 0, ""
            for tx in texts:
                starts.append(joined.count("\n"))
                joined += tx
            marked = CPR.HEADER.sub("§\n", joined.replace("%c", "%c"))
            body = marked.replace("%c", "")
            lines = body.split("\n")
            n = len(lines)
            hdr = {i for i, s in enumerate(lines) if "§" in s}
            tri_bad = tri is not None and n == limit and P._row_w(lines[-1].replace("§", "")) > tri
            if n <= limit and not tri_bad:
                continue
            c = P.best_cut([s.replace("§", "") for s in lines], 2, min(limit, n - 1), hdr)
            # 그 줄이 시작되는 블록 — 줄을 나눠 쓰는 이웃이면 앞 블록
            owner = max(i for i, s0 in enumerate(starts) if s0 <= c)
            if owner + 1 < len(starts) and starts[owner + 1] == c and texts[owner].endswith("\n"):
                owner += 1  # 앞 블록이 개행으로 끝나면 c 줄은 다음 블록에서 시작한다
            out[game].setdefault(keys[owner], set()).add(c - starts[owner])
    return {g: {k: sorted(v) for k, v in sorted(d.items()) if len(v) == 1} for g, d in out.items()}


def collect_pages(folders, canon, dec):
    """쪽(창 한 장)이 5행을 넘는 자리를 찾아 **어느 블록을 몇째 줄 앞에서 가를지** 뽑는다 → `{게임: {열쇠: [줄 번호, …]}}`.

    줄 번호 j = 그 블록의 j째 줄(0부터) **앞**에서 쪽을 가른다(`\x08` 창 끝 — 키 대기 뒤 새 쪽). j=0 이면 블록 머리에서.
    같은 열쇠가 여러 자리에 나오면 결정이 같을 때만 담는다."""
    import common
    import patch_scn as P

    dec_by = collections.defaultdict(lambda: collections.defaultdict(set))
    chains = collections.defaultdict(set)
    for folder in folders:
        idx = json.load(open(os.path.join(folder, "index.json"), encoding="utf-8"))
        game = "ED1" if "ed1" in os.path.basename(folder.rstrip("/")).lower() else "ED2"
        f, mm = common.open_image(os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin"))
        files = {n for n, _l, _s in common.iso_files(mm)}
        tab = {}
        seen = set()
        for e in idx:
            if e.get("args") not in ("a", None):
                continue
            path = f"/BIN/{game}SCN{e['scene']:02d}.BIN"
            if path not in files or e["script"] in seen:
                continue
            seen.add(e["script"])
            if path not in tab:
                m = collections.defaultdict(set)
                got = P.load(path)
                sites = P.sites_for(path)
                for b in got[1]:
                    jp = b.get("text", "")
                    if not jp:
                        continue
                    kr = P.canon_of(canon, jp, sites.get(int(b["file_offset"], 16)), path=path, off=int(b["file_offset"], 16))
                    if kr:
                        m[norm(kr)].add((P.line_key(jp), kr))
                tab[path] = m
            t = dec(e["script"])
            # 쪽 = [끝]/<0x> 사이. 쪽 안의 조각(= 블록)들을 모은다
            for page in re.split(r"\[끝\]|<0[0-9a-f]>", t):
                # 🔴 한 쪽 안의 글(`[창]`·`[키]` 로 갈린 조각)을 **블록 여럿의 이음**으로 풀어(가장 긴 앞머리 일치) 블록별 시작 줄을 센다 —
                #    체인 블록은 사이에 제어코드가 없어 한 조각에 이어 붙는다(씬 5 번호 4: 「왕자님.」+ 네 줄).
                body_all = re.sub(r"\[[^\]]*\]", "", page)
                PAGE_ROWS = PAGE_ROWS_G[game]
                flat = []  # (글자, 줄 번호) — 공백·개행 제외
                line_no = 0
                for ch in body_all:
                    if ch == "⏎":
                        line_no += 1
                    elif not ch.isspace():
                        flat.append((ch, line_no))
                text_norm = "".join(c for c, _ in flat)
                known = {}
                for nk, kv in tab[path].items():
                    if len(kv) == 1:
                        known[nk] = next(iter(kv))
                pos = 0
                spans = []
                while pos < len(text_norm):
                    best = None
                    for nk in known:
                        if nk and text_norm.startswith(nk, pos) and (best is None or len(nk) > len(best)):
                            best = nk
                    if best is None:
                        break
                    spans.append((best, pos, pos + len(best)))
                    pos += len(best)
                if pos < len(text_norm):
                    continue  # 풀리지 않는 쪽은 건드리지 않는다
                if len(spans) >= 2:  # 체인 구조(블록 열쇠 열) — 문안이 바뀌어도 구조는 스크립트가 정한다(게이트 `check_page_rows` 가 읽는다)
                    chains[game].add(tuple(known[nk][0] for nk, _a, _b in spans))
                lines_all = body_all.split("⏎")
                n_all = len(lines_all)
                import patch_scn as _P

                tri = _P.TRI_W.get(game)
                tri_bad = tri is not None and n_all == PAGE_ROWS and _P._row_w(lines_all[-1]) > tri  # ED1 꽉 찬 쪽의 마지막 줄이 ▽ 칸을 넘는다
                if n_all <= PAGE_ROWS and not tri_bad:
                    continue
                # 🔴 쪽마다 **컷을 한 번만** 고른다 — 새 쪽이 시작할 절대 줄 c. 문장 끝 → 연결어미 → 고아 방지, 화자 머리 줄 뒤는 금지·앞은 최선
                #    (`patch_scn.best_cut`). 블록마다 따로 고르면 블록 머리(j=0)·화자 교대 앞이 후보에서 빠진다(10-19 qa r6 「아무렇지 / 않게」).
                hdr = {i for i, s in enumerate(page.split("⏎")) if "[창]" in s}
                c = _P.best_cut(lines_all, 2, min(PAGE_ROWS, n_all - 1), hdr)
                hit = [(nk, flat[a][1]) for nk, a, b in spans if flat[a][1] <= c <= flat[b - 1][1]]
                if hit:
                    nk, l0 = hit[-1]  # 줄을 나눠 쓰는 이웃이면 뒤 블록(그 블록 머리에서 가른다)
                    dec_by[game][known[nk][0]].add(c - l0)
    out = {}
    for game, d in dec_by.items():
        out[game] = {k: sorted(v) for k, v in sorted(d.items()) if len(v) == 1}
    return out, {g: sorted(list(c) for c in v) for g, v in chains.items()}


def main():
    import common
    import patch_scn as P

    game_of = {"ED2": "ED2", "ED1": "ED1"}
    canon = P.load_canon(quiet=True)
    dec = decode_fn()
    obs = collections.defaultdict(lambda: collections.defaultdict(set))  # game → key → {폭, …}
    bad = collections.defaultdict(set)  # 키 대기 이음이 아닌 자리가 있는 열쇠
    nl_yes = collections.defaultdict(set)  # [창] 이 앞 글 끝에 바로 붙은 자리의 열쇠(새 화자 이름이 앞 줄 끝에 붙는다)
    nl_no = collections.defaultdict(set)  # [창] 이 줄 머리/창 시작인 자리
    for folder in sys.argv[1:]:
        idx = json.load(open(os.path.join(folder, "index.json"), encoding="utf-8"))
        # 블록 정규화 문안 → 열쇠(들) — 씬 파일별
        f, mm = common.open_image(os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin"))
        files = {n for n, _l, _s in common.iso_files(mm)}
        tab = {}
        for e in idx:
            if e.get("args") not in ("a", None):
                continue
            game = "ED1" if "ed1" in os.path.basename(folder.rstrip("/")).lower() else "ED2"
            path = f"/BIN/{game}SCN{e['scene']:02d}.BIN"
            if path not in files:
                continue
            if path not in tab:
                m = collections.defaultdict(set)
                got = P.load(path)
                sites = P.sites_for(path)
                for b in got[1]:
                    jp = b.get("text", "")
                    if not jp:
                        continue
                    kr = P.canon_of(canon, jp, sites.get(int(b["file_offset"], 16)), path=path, off=int(b["file_offset"], 16))
                    if kr:
                        m[norm(kr)].add(P.line_key(jp))
                tab[path] = m
            t = dec(e["script"])
            # 창 하나 = [창] 부터 [끝]/<0x> 까지. 안에서 [키] 로 갈린 조각을 순서대로 본다
            cur = 0.0
            line = 0.0
            pieces = re.split(r"(\[끝\]|\[키\]|<0[0-9a-f]>|\[창\])", t)
            prev_ctl = None
            for piece in pieces:
                if piece in ("<01>", "<02>", "<03>"):
                    continue  # 색 켜기/끄기 — 줄도 이음 상태도 안 바꾼다(`[키]<03>50000 Gold…` 이 이음으로 읽혀야 한다)
                if CTL.fullmatch(piece):
                    prev_ctl = piece
                    if piece == "[끝]" or piece.startswith("<"):
                        line = 0.0
                    continue
                body = piece
                keys = tab[path].get(norm(body))
                if prev_ctl == "[창]" and keys and len(keys) == 1:
                    kk = next(iter(keys))
                    (nl_yes if line > 0.0 else nl_no)[game].add(kk)
                if prev_ctl == "[키]" and keys and len(keys) == 1:
                    k = next(iter(keys))
                    # 🔴 키 대기 **바로 뒤가 개행**(`%c\n` — 앞 블록 끝의 개행)이면 이 블록은 새 줄에서 시작한다 — 커서 0. 앞 줄 폭을 이음 커서로 잡으면 첫 낱말만 앞 줄에
                    #    붙는 꼴로 잘못 접는다(ED1SCN26 id103 「그」 한 글자 줄, 2026-10-20 qa)
                    obs[game][k].add(0.0 if body.startswith("⏎") else round(line, 1))
                elif keys and len(keys) == 1:
                    bad[(game, next(iter(keys)))].add(1)
                # 이 조각이 끝난 뒤의 커서: 마지막 줄 폭(+ 이어진 줄이면 앞 폭)
                lines = body.split("⏎")
                lines = [re.sub(r"\[[^\]]*\]", "", x) for x in lines]
                if prev_ctl == "[키]" and len(lines) == 1:
                    line = line + width(lines[0])
                else:
                    line = width(lines[-1])
    print({g:(len(v),sum(1 for k in v if (g,k) in bad)) for g,v in obs.items()})
    print({g:sum(1 for k,v in d.items() if len(v)>1) for g,d in obs.items()})
    out = {}
    pages_sweep, chains = collect_pages(sys.argv[1:], canon, dec)
    # 🔴 폭 표도 **누적**이다 — 쪽을 가른 뒤 빌드의 캡처엔 그 블록이 이음으로 안 보여 다시 뽑으면 열쇠를 잃고(이음 공백이 사라진다),
    #    한 게임 폴더만 넣으면 다른 게임 표가 통째로 지워진다. 이번에 **관측된** 열쇠만 새 값이 이기고 나머진 옛 값을 둔다.
    try:
        oldw = json.load(open(OUT, encoding="utf-8"))
    except OSError:
        oldw = {}
    for game in ("ED1", "ED2"):
        got = {k: sorted(v)[0] for k, v in sorted(obs.get(game, {}).items()) if len(v) == 1 and (game, k) not in bad}
        keep = {k: v for k, v in oldw.get(game, {}).items() if k not in got}  # 관측이 갈려(옛 빌드·새 빌드) 못 정한 열쇠도 옛 값을 둔다
        out[game] = {**keep, **got}
    try:
        oldc = json.load(open(OUT, encoding="utf-8")).get("chains", {})
    except OSError:
        oldc = {}
    for g in set(oldc) | set(chains):
        merged = {tuple(c) for c in oldc.get(g, [])} | {tuple(c) for c in chains.get(g, [])}
        chains[g] = sorted(list(c) for c in merged)
    out["chains"] = chains
    # 🔴 쪽 가르기 표는 캡처가 아니라 **체인 표 + 현재 문안**에서 매번 새로 계산한다(`static_pages`) — 옛 빌드가 이미 가른 쪽의 캡처엔 컷이 안 보여
    #    누적으로 두면 낡은 컷(문장 한가운데)이 남는다.
    out["pages"] = static_pages(canon, chains)
    nl_new = {g: {k for k in nl_yes[g] if k not in nl_no[g]} for g in nl_yes}
    out["nl"] = {g: sorted(nl_new.get(g, set()) | set(oldw.get("nl", {}).get(g, []))) for g in ("ED1", "ED2") if nl_new.get(g) or oldw.get("nl", {}).get(g)}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(OUT, {g: len(v) for g, v in out.items() if g not in ("nl", "pages")}, {g: len(v) for g, v in out["pages"].items()})


if __name__ == "__main__":
    main()
