#!/usr/bin/env python3
"""쪽 행 수 게이트 — **조판 결과 전량**에서 「이름 + 본문이 원판 한도를 넘는 쪽」이 0 인가.

    python3 tools/check_page_rows.py            # 실패면 종료코드 1

🔴 왜(2026-10-19 qa·원판 JP 대조): 원판 대화창은 **이름 + 본문 4줄(5행)** 까지이고 6째 행은 ▽ 자리다. 우리 6행 쪽은 ▽ 가 글자 위에 얹혔다.
쪽 가르기는 대사 보기 실측에서 뽑은 손 표(`script/key_cont.json` `pages`)에 기대므로 **표에 없는 쪽이 새면** 못 잡는다 — 이 게이트가 그 구멍을 막는다.

본다:
  ① 블록 하나가 만드는 쪽(창 끝 `\\x08` 과 화자 머리 `%c이름%c\\n` 로 가른다)의 행 수가 한도(`PAGE_ROWS`)를 넘나 — 화자 줄도 한 행이다.
  ② `pages` 표의 열쇠가 **실제로 가른 자리**가 있나(표 열쇠가 모호해 못 가른 쪽도 여기서 걸린다) — 가를 줄이 있는데 `\\x08` 이 없으면 실패.
⚠ 한 쪽이 **여러 블록에 걸치면**(앞 블록 끝 줄 뒤에 다음 블록이 이어 그려진다) 블록 하나로는 못 센다 — 그건 대사 보기 캡처의 스크립트 디코드(`derive_key_cont` · manifest)가 센다.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

PAGE_ROWS = None  # 값은 `patch_scn.PAGE_LIMIT`(ED2 5행·ED1 6행 — 원판 JP 대조) · `TRI_W`(ED1 6행 쪽 마지막 줄이 ▽ 칸을 넘으면 실패)
HEADER = re.compile(r"%c[^%\n]+%c\n")  # 화자 머리 — 이름 한 행


def page_rows(built, joined=False):
    """블록 하나가 만드는 쪽들의 `[(행 수, 마지막 줄 폭), …]` — 화자 머리(`%c이름%c\\n`)는 한 행이고, 머리가 아닌 `%c`(쪽 넘김·키 대기)와 창 끝 `\\x08` 이 쪽을 가른다."""
    import patch_scn as P

    t = HEADER.sub("§\n", built)
    out = []
    # joined: 이은 쪽 — `%c`(키 대기·이음)는 쪽을 가르지 않는다(같은 창에 이어 그려진다), 창 끝 `\\x08` 만 가른다
    for pg in re.split(r"\x08" if joined else r"%c|\x08", t.replace("%c", "") if joined else t):
        pg = pg.strip("\n")
        if not pg.strip("§\n "):
            continue
        lines = pg.split("\n")
        out.append((len(lines), P._row_w(lines[-1].replace("§", ""))))
    return out


def violations(built, game, joined=False):
    """한도 초과 행 수들 + ▽ 칸을 넘는 꽉 찬 쪽(`TRI_W`) — `[(행, 마지막 줄 폭, 사유), …]`."""
    import patch_scn as P

    limit, tri = P.PAGE_LIMIT[game], P.TRI_W.get(game)
    out = []
    # 🔴 화자 머리 **바로 뒤**의 창 끝(`%c이름%c\x08`)은 쪽을 못 가른다 — 이름만 앞 쪽에 붙고 본문이 같은 창에 이어 그려져 창 아래로 넘친다
    #    (ED1SCN23 m2 id101: 8행이 한 창에 — 머리 정규식이 `\n` 뒤만 보니 6행으로 세어 통과했다, 2026-10-19 qa r6)
    if re.search(r"%c[^%\n]+%c\x08", built):
        out.append((0, 0.0, "화자 머리 바로 뒤에서 가름(안 갈린다)"))
    for rows, w in page_rows(built, joined):
        if rows > limit:
            out.append((rows, w, "행 초과"))
        elif tri is not None and rows == limit and w > tri:
            out.append((rows, w, "마지막 줄이 ▽ 칸을 넘음"))
    return out


def main():
    import common
    import patch_scn as P

    canon = P.load_canon(quiet=True)
    f, mm = common.open_image(os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")) if os.path.exists(
        os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")
    ) else common.open_image()
    bad, table_miss, total = [], [], 0
    cuts_tab = P._scn_cuts()
    for path, _l, _s in common.iso_files(mm):
        if not P.DIALOG_RE.match(path):
            continue
        got = P.load(path)
        if not got:
            continue
        game = "ED1" if "/ED1SCN" in path else "ED2"
        sites = P.sites_for(path)
        for e in got[1]:
            jp = e.get("text", "")
            if not jp:
                continue
            off = int(e["file_offset"], 16)
            kr = P.canon_of(canon, jp, sites.get(off), path=path, off=off)
            if not kr:
                continue
            total += 1
            v = violations(kr, game)
            if v:
                bad.append((path, off, v, kr.replace("\n", "/")[:60]))
            cuts = cuts_tab.get(game, {}).get(P.line_key(jp))
            if cuts and any(j < len(kr.split("\n")) for j in cuts if j) and "\x08" not in kr:
                table_miss.append((path, off, cuts))
    # 🔴 체인(블록 여럿이 한 쪽에 이어 그려지는 꼴 — 씬 5 번호 4: 「왕자님.」+ 네 줄) — 구조는 **스크립트가 정한다**(문안이 바뀌어도 그대로).
    #    대사 보기 실측에서 뽑은 열쇠 열(`script/key_cont.json` `chains`)을 이어 붙인 결과로 행 수를 잰다(2026-10-19 manager: 체인 4쪽이 게이트를 샜다).
    chain_bad = []
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
                        by_key[k] = kr
    for game, chains in P._scn_chains().items():
        for keys in chains:
            if not all(k in by_key for k in keys):
                continue
            text = "".join(by_key[k] for k in keys)
            v = violations(text, game, joined=True)
            if v:
                chain_bad.append((game, keys, v, text.replace("\n", "/")[:70]))
    print(f"  쪽 행 수 [블록 {total:,}] — 한도 초과 {len(bad)} · 표대로 못 가른 {len(table_miss)} · 이은 쪽(체인) 초과 {len(chain_bad)}")
    for g, ks, v, t in chain_bad[:20]:
        print(f"     ❌ 체인 {g} {ks[0]}… 행 {v} — {t}")
    for p, o, v, t in bad[:15]:
        print(f"     ❌ {p[-12:]} {o:#x} 행 {v} — {t}")
    for p, o, c in table_miss[:15]:
        print(f"     ❌ 표 열쇠는 있는데 안 갈렸다 {p[-12:]} {o:#x} {c}")
    if bad or table_miss or chain_bad:
        raise SystemExit(f"쪽 행 수 {len(bad) + len(table_miss) + len(chain_bad)}건 — 위를 고친다")


if __name__ == "__main__":
    main()
