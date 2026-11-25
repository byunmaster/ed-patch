#!/usr/bin/env python3
"""구운 조판 전수(마스터 10-31) — **실제로 굽는 바이트의 조판 결과**(`build.encode_member` 와 같은 길)를 전 대사 창에서 센다.

    python3 tools/check_baked_layout.py [--show]

`check_typeset_rules` 는 조각 하나를 `typeset.wrap` 에 태워 보고, `wrap_metrics` 는 쪽 나눔 지표(고아 어절·균등 분배·손 개행)를
센다. 여기는 **창 전체**(이어지는 조각·변수·쪽 opcode 까지)로 아래 축을 센다 — 둘이 못 보는 자리다.

  첫 칸 공백(2-5)   줄 첫머리가 공백(변수 뒤에 이어 붙는 조각은 제외 — 거기 공백은 어절 경계다)
  고아 부호(2-3)    줄·쪽 첫머리가 부호(`, . ! ? ) 」 』`)로 시작
  빈 줄(2-4)        창 한가운데 빈 조각/빈 줄(꼬리의 빈 조각은 창 줄 수 채움이라 정상)
  부호 뒤 공백(2-1) `, . ! ?` 바로 뒤에 글자가 붙음(숫자 소수점·「…」 제외)
  낱말 속 접힘(2-6) 변수 없는 창에서 구운 어절 열이 원 문안의 어절 열과 다름(어절이 쪼개지거나 붙음)
  넘침              구운 줄이 창 폭 칸을 넘음

균등 분배(마지막 창 한 어절 · 줄 수 치우침)는 `wrap_metrics --check` 가 이미 센다(재사용).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common
import josa_rt
import script as script_canon
import scriptmap
import textenc
import typeset
from check_typeset_rules import line_problems
from check_var_spacing import chains

ORPHAN = tuple(",.!?)」』")
AXES = (
    "첫 칸 공백",
    "고아 부호",
    "빈 줄",
    "부호 뒤 공백",
    "부호 앞 공백",
    "표기 규칙",
    "낱말 속 접힘",
    "넘침",
    "쪽 비어 있음",
)
PUNCT_GLUE = re.compile(r"[,.!?][가-힣A-Za-z]")


def window_problems(pieces, pre_ops, src, width):
    """창 하나의 위반 [(축, 조각 순번, 글)].

    pieces: 구운 조각 글(`\\n` 포함 가능) · pre_ops: 조각 앞 opcode 열 · src: 원 문안 조각들 · width: 줄 칸 상한."""
    out = []
    has_var = any(4 <= o <= 7 for ops in pre_ops for o in ops)
    # 규칙 2-17 「적음」 — 쪽(op 02)이 원문 쪽보다 줄어드는 합침. 쪽 수는 구조 계약이 고정하니, 합치면 한 쪽이 통째로 비어 나온다
    #   (원문 쪽은 비어 있지 않은데 구운 쪽이 빔). 원문 쪽이 원래 빈 것은 뺀다.
    pg = [[]]
    for k, ops in enumerate(pre_ops):
        if 2 in ops and k:
            pg.append([])
        pg[-1].append(k)
    for ks in pg:
        if not any(pieces[k].strip() for k in ks) and any(src[k].strip() for k in ks):
            out.append(("쪽 비어 있음", ks[0], ""))
            continue
        # 엔진은 한 쪽에 3줄(이름표 있음)·4줄(없음)까지 보이고 넘치면 알아서 쪽을 넘긴다 — 글 있는 줄이 앞에 몰려 **빈 조각만으로 쪽이 서면**
        #   글 없는 쪽이 뜨고 확인 키를 한 번 더 누른다(11-06 화면 실측: 5조각에 3~4줄). 원문 쪽에 글이 있던 자리만 센다.
        for per in typeset.PAGE_ROWS:
            hit = next(
                (
                    c * per
                    for c in range(1, len(ks))
                    if c * per < len(ks)
                    and not any(pieces[k].strip() for k in ks[c * per : (c + 1) * per])
                    and any(src[k].strip() for k in ks[c * per : (c + 1) * per])
                ),
                None,
            )
            if hit is not None:
                out.append(("쪽 비어 있음", ks[hit], f"{per}줄 쪽"))
                break
    for k, (t, pre) in enumerate(zip(pieces, pre_ops, strict=True)):
        after_var = bool(pre) and 4 <= pre[-1] <= 7
        for r, row in enumerate(t.split("\n")):
            lead_ok = r == 0 and after_var
            if row[:1] == " " and not lead_ok and row.strip():
                out.append(("첫 칸 공백", k, row[:14]))
            body = row.lstrip(" ")
            if body[:1] in ORPHAN and body and not lead_ok and (r > 0 or k > 0):
                out.append(("고아 부호", k, row[:14]))
            if PUNCT_GLUE.search(row) and not re.search(r"\d[.,]\d", row):
                out.append(("부호 뒤 공백", k, row[:14]))
            if re.search(r"(?<=\S) [,.!?](?!\.)", row.rstrip()) and not lead_ok:
                out.append(("부호 앞 공백", k, row[:14]))  # 2-2
            if typeset.width_cells(row.rstrip(" ")) > width:
                out.append(("넘침", k, row[:14]))
    # 말줄임·물결표·물음표 겹침 등 표기 규칙(2-11·2-12 …) — check_typeset_rules 와 같은 자.
    # 단 두 꼴은 조각 이음이라 규칙 밖이다: 「…」 로 끝난 줄 뒤에 이어 붙은 「…말」(앞 문장 말줄임 + 새 문장 앞 말줄임) ·
    # 원문이 「……」 만인 조각 뒤의 공백(말없음 줄 다음 말).
    lone = any(x.strip() and not x.strip("…") for x in src)
    for k, t in enumerate(pieces):
        for m in line_problems(re.sub(r"…\s+(?=…)", "」 ", t)):
            if m.startswith("줄 머리에 부호"):  # 고아 부호는 위에서 센다
                continue
            if lone and m.startswith("문장 맨 앞 「…」 뒤에 공백"):
                continue
            out.append(("표기 규칙", k, m[:40]))
    # 빈 줄 — 같은 쪽 안에서 비지 않은 조각 사이에 빈 조각
    seen_blank = None
    for k, (t, pre) in enumerate(zip(pieces, pre_ops, strict=True)):
        if 2 in pre:
            seen_blank = None
        if not t.strip():
            if seen_blank is None:
                seen_blank = k
        elif seen_blank is not None:
            out.append(("빈 줄", seen_blank, f"조각 {seen_blank} 뒤에 글 {k}"))
            seen_blank = None
        if t.strip() and (t.startswith("\n") or "\n\n" in t):
            # 2-18 — 조각 머리의 개행(= 창 첫 줄이 빔)·조각 안 연속 개행(= 빈 줄)
            out.append(("빈 줄", k, t[:14].replace("\n", "⏎")))
    if not has_var:
        # 「…」 둘레 공백은 조판이 규칙(2-11)대로 고르므로 같게 본다 — 어절이 쪼개지거나 붙은 것만 잡는다
        a = re.sub(r"\s*…\s*", " … ", " ".join(src)).split()
        b = re.sub(r"\s*…\s*", " … ", " ".join(pieces)).split()
        if a != b:
            out.append(("낱말 속 접힘", 0, " ".join(b)[:20]))
    return out


def baked_pieces(disc="ed3"):
    """{멤버: {조각: 구울 글}} — `build.encode_member` 와 같은 분기(창 재조판 · 단일 wrap)."""
    canon, _ = script_canon.load_effective(disc)
    iso = common.iso_files(disc)
    res = {}
    for (path, nm), lines in sorted(canon.items()):
        lba, size = iso[path]
        data = common.read_lba(disc, lba, size)
        _, ents = common.arc_parse(data)
        off, sz = next((o, s) for n, o, s in ents if n == nm)
        mem = data[off : off + sz]
        info = scriptmap.parse(mem)
        jps = [(i, textenc.decode(c, disc)) for i, (_, c) in enumerate(info["segments"])]
        floors = script_canon.member_floors(jps)
        reflowed = build.reflow_windows(mem, info, lines, disc) if disc == "ed3" else {}
        key = (
            os.path.basename(path).split(".")[0]
            + "_"
            + nm.replace("\\", "/").split("/")[-1].split(".")[0]
        )
        d = {}
        for i, row in lines.items():
            if i in reflowed:
                d[i] = reflowed[i]
                continue
            try:
                d[i] = typeset.wrap(
                    josa_rt.convert(row["kr"]), disc, jp=jps[i][1], floor=floors.get(i, 0)
                )
            except typeset.TypesetError:
                continue
        res[key] = d
    return res


def windows(disc="ed3"):
    """[(멤버, 조각 번호들, 조각 앞 opcode 열(머리 포함), 구운 조각들, 원 문안 조각들)] — 구울 글이 다 있는 대사 창."""
    baked = baked_pieces(disc)
    out = []
    for member, head, chain, kr in chains(disc):
        b = baked.get(member, {})
        ids = [p for p, _ in chain]
        if any(p not in b for p in ids):
            continue
        pre = [head] + [ops for _p, ops in chain[:-1]]
        out.append((member, ids, pre, [b[p] for p in ids], [josa_rt.convert(kr[p]) for p in ids if p in kr]))
    return out


def scan(disc="ed3"):
    width = typeset.LIMITS[disc]["width"]
    bad, nwin, npiece = [], 0, 0
    for member, ids, pre, pieces, src in windows(disc):
        nwin += 1
        npiece += len(ids)
        for axis, k, txt in window_problems(pieces, pre, src, width):
            bad.append((axis, member, ids[min(k, len(ids) - 1)], txt))
    return bad, nwin, npiece


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    try:
        bad, nwin, npiece = scan(a.disc)
    except (OSError, SystemExit, KeyError) as e:
        print(f"구운 조판 전수 — 안 쟀다(원판 디스크를 못 읽음: {e})")
        return 1
    cnt = {ax: sum(1 for b in bad if b[0] == ax) for ax in AXES}
    print(
        f"구운 조판 전수 [{a.disc}] — 창 {nwin} · 조각 {npiece} · 위반 {len(bad)} "
        + "("
        + " · ".join(f"{ax} {n}" for ax, n in cnt.items())
        + ")"
    )
    for ax, member, p, txt in bad[: (len(bad) if a.show else 20)]:
        print(f"  🔴 {ax} {member}@{p}: {txt!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
