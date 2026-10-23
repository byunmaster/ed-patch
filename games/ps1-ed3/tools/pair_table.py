"""롬에서 뽑은 번호별 대사집 짝 표 — 원판 이미지와 굽은 이미지의 **실제 바이트**를 디코드해 번호마다 원문|한글을 짝짓는다(마스터 10-20).

  python3 tools/pair_table.py --kr-cue <굽은 시험 롬 cue> --out <폴더>

대본 JSON 이 아니라 두 이미지에서 읽는다. 산출 `<out>/pairs.tsv`(번호 · 원판 · 한글 · 표시) + `manifest.md`.
번호: `맵#n`(맵 대사 창 n번째 — 시퀀스 `0F 90 …` 순서) · `맵@i`(창에 안 든 조각 i번) · `풀1#i`·`풀2#i`(읽을거리 풀 표 항목) · `UI@0x…`(실행파일 낱말·메뉴 문자열).
표기: ↵ = 줄(조각) 바꿈 · ⏎ = 이어지는 창(쪽) 경계(표에선 안 쓴다 — 창마다 한 행) · `{cXXX}` = 글자표에 없는 코드(변수·제어).
표시: 원판만(바이트가 원판 그대로 = 번역 안 됨) · 한글만(원판 빔) · 둘 다 빔 · 포인터 공유(한 조각을 여러 창이 가리킴). 비어 있으면 정상 짝.
"""

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import exetext
import hangul_map
import poolpack
import scriptmap
import textenc
import uitext

DISC = "ed3"
UNK = "{{c{:03x}}}"


def kr_decoder(table):
    rev = {}
    cm = textenc.charmap(DISC)
    for c, ch in cm.items():
        rev[c] = ch
    for c, ch in textenc.CONTROL.items():
        rev[c] = ch
    for ch, c in hangul_map.punct(DISC).items():
        rev[c] = ch
    for ch, c in table.items():  # 굽은 글리프가 마지막에 이긴다(시험 롬은 한자 자리를 빌린다)
        rev[c] = ch

    def dec(codes):
        out = []
        for w in codes:
            if w == textenc.TERM:
                break
            out.append(rev.get(w) if w in rev else UNK.format(w))
        return "".join(out)

    return dec


def mark(jp_codes, kr_codes, jp, kr, shared):
    if shared:
        return "포인터 공유"
    if jp_codes == kr_codes and jp.strip():
        # 원문이 가나·한자가 아니면(전각 영문·숫자·부호) 한국어도 같은 글자라 번역이 필요 없다
        if not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", jp):
            return ""
        return "원판만"
    if not jp.strip() and kr.strip():
        return "한글만"
    if not jp.strip() and not kr.strip():
        return "둘 다 빔"
    return ""


def clean(s):
    return s.replace("\t", " ").replace("\n", "↵")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr-cue", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    binp = os.path.splitext(a.kr_cue)[0] + ".bin"
    tree = common.iso_tree(binp)[0]
    need = list(hangul_map.EXTRA) + hangul_map.needed_chars(DISC)
    table, _short = hangul_map.assign(DISC, hangul_map.test_slots(DISC), chars=need)
    kdec = kr_decoder(table)
    # 🔴 디코더 글자표 = 굽은 글리프 — 이미지가 **다른 시점의 배정**으로 구워졌으면 글자가 돌려 읽힌다(10-20: 검→허→좀 순환, 롬이 문안 수정 전이었다).
    #    굽은 글리프 비트맵을 이 표의 글자 그림과 대조해 어긋나면 멈춘다.
    import numpy as np

    import font

    k_font = common.read_lba(DISC, *tree[font.FONTS[DISC]["exe"]], path=binp)
    skew = []
    for ch, code in table.items():
        if ch == " ":
            continue
        want = np.asarray(font.glyph_bits(ch))
        got = np.asarray(font.read_glyph(k_font, code))
        w = np.zeros((12, 12), dtype=got.dtype)
        w[: want.shape[0], : want.shape[1]] = want
        if not (w == got).all():
            skew.append(ch)
    if len(skew) > 5:
        raise SystemExit(f"🔴 굽은 이미지의 글리프가 이 코드의 배정과 다르다({len(skew)}자: {''.join(skew[:20])}) — 롬을 지금 HEAD 로 다시 굽는다")
    jdec = lambda codes: textenc.decode(codes, DISC, unknown=UNK)
    rows, cnt = [], collections.Counter()
    fs = common.iso_files(DISC)

    # ── 맵 대사(번역 대상 스크립트 멤버 전부 — 범위는 정본 JSON 의 멤버 목록으로만 잡고, 내용은 두 이미지에서 읽는다)
    import glob
    import json

    scope = set()
    for jf in glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script", DISC, "*.json")):
        with open(jf, encoding="utf-8") as fh:
            d = json.load(fh)
        scope.add((d["archive"], d["member"]))
    for path, (lba, size) in sorted(fs.items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        orig = common.read_lba(DISC, lba, size)
        try:
            _, oents = common.arc_parse(orig)
        except common.ArchiveError:
            continue
        klba, ksize = tree[path]
        kdata = common.read_lba(DISC, klba, ksize, path=binp)
        _, kents = common.arc_parse(kdata)
        kmap = {n: (o, s) for n, o, s in kents}
        for nm, off, sz in oents:
            mem = orig[off : off + sz]
            try:
                oinfo = scriptmap.parse(mem)
            except Exception:
                continue
            if (path, nm) not in scope or oinfo.get("layout") != scriptmap.LAYOUT_POOL or nm not in kmap:
                continue
            ko, ks = kmap[nm]
            kmem = kdata[ko : ko + ks]
            kinfo = scriptmap.parse(kmem)
            osegs = [c for _s, c in oinfo["segments"]]
            ksegs = [c for _s, c in kinfo["segments"]]
            while len(ksegs) > len(osegs) and not any(ksegs[-1]):  # 풀 뒤 0 채움이 조각 하나로 읽힌다
                ksegs.pop()
            if len(osegs) != len(ksegs):
                cnt["구조 불일치 멤버"] += 1
                continue
            m = os.path.basename(nm.replace("\\", "/")).split(".")[0]
            chains = scriptmap.window_chains(mem, oinfo)
            use = collections.Counter(i for c in chains for i in c)
            inwin = set(use)
            for n, c in enumerate(chains):
                jc = [osegs[i] for i in c]
                kc = [ksegs[i] for i in c]
                jp = "↵".join(x for x in (jdec(s) for s in jc) if x)
                kr = "↵".join(x for x in (kdec(s) for s in kc) if x)
                shared = any(use[i] > 1 for i in c)
                tag = mark(jc, kc, jp, kr, shared)
                rows.append((f"{m}#{n}", jp, "(번역 안 됨)" if tag == "원판만" else kr, tag))
                cnt[tag or "정상"] += 1
            for i, (jc, kc) in enumerate(zip(osegs, ksegs)):
                if i in inwin:
                    continue
                jp, kr = jdec(jc), kdec(kc)
                tag = mark(jc, kc, jp, kr, False)
                rows.append((f"{m}@{i}", jp, "(번역 안 됨)" if tag == "원판만" else kr, tag))
                cnt["창 밖 조각 " + (tag or "정상")] += 1

    # ── 읽을거리 풀(책·설명·메모) — 표 항목마다 펼친 코드열
    import font

    elba, esize = fs[font.FONTS[DISC]["exe"]]
    exe_o = bytes(common.read_lba(DISC, elba, esize))
    k_exe = common.read_lba(DISC, *tree[font.FONTS[DISC]["exe"]], path=binp)
    enc = lambda kr: hangul_map.encode(kr, DISC, table)
    pre = bytearray(exe_o)
    uitext.apply(pre, DISC, enc)
    work = bytearray(pre)
    pl = poolpack.apply(work, DISC, uitext.pool_rows(DISC), lambda kr: uitext.ui_codes(enc, kr))
    got = poolpack.read_streams(k_exe, DISC, pl["merges"])
    L = poolpack.LAYOUT[DISC]
    for pi, pool in enumerate(L["pools"]):
        segs = poolpack.segments(exe_o, pool)
        for i, v in enumerate(poolpack.table_entries(exe_o, pool)):
            if v >= 0x8000:
                continue
            seq = []
            for k in poolpack.chain_from(segs, pool["base"] + v):
                seq += list(segs[k][1]) + [segs[k][2]]
            jc, kc = seq, got[(pi, i)]
            jp = jdec(seq)
            kr = kdec(kc)
            tag = mark(jc, kc, jp, kr, False)
            rows.append((f"풀{pi + 1}#{i}", clean(jp), "(번역 안 됨)" if tag == "원판만" else clean(kr), tag))
            cnt["풀 " + (tag or "정상")] += 1

    # ── 실행파일 낱말·메뉴·전투 문구 등(읽을거리 풀 밖) — 같은 표·같은 오프셋을 두 이미지에서 읽는다
    #    ⚠ 굽기가 가운데 정렬로 앞에 0x0000(빈 글리프) 패드를 두므로 종결은 0xFFFF·최상위 비트만으로 본다.
    _tbls, sites = uitext.sites(DISC)

    def codes_at(data, off):
        out, p = [], off
        for _ in range(400):
            if p + 1 >= len(data):
                return None
            w = int.from_bytes(data[p : p + 2], "little")
            if w == 0xFFFF or w & 0x8000:
                break
            out.append(w)
            p += 2
        while out and out[0] == 0:
            out.pop(0)
        while out and out[-1] == 0:
            out.pop()
        return out

    seen_tables, singles = set(), []
    for off in sorted(sites):
        if uitext.in_pool(DISC, off):
            continue
        t = sites[off]["table"]
        if t is None:
            singles.append(off)
        elif t not in seen_tables:
            seen_tables.add(t)
            tbl, base, n = t
            for i in range(n):
                ent = int.from_bytes(exe_o[tbl + 2 * i : tbl + 2 * i + 2], "little")
                kent = int.from_bytes(k_exe[tbl + 2 * i : tbl + 2 * i + 2], "little")
                jc, kc = codes_at(exe_o, base + ent), codes_at(k_exe, base + kent)
                if jc is None or kc is None:
                    cnt["UI 읽기 실패"] += 1
                    continue
                jp, kr = jdec(jc), kdec(kc)
                tag = mark(jc, kc, jp, kr, False)
                rows.append((f"UI표{tbl:#x}#{i}", clean(jp), "(번역 안 됨)" if tag == "원판만" else clean(kr), tag))
                cnt["UI " + (tag or "정상")] += 1
    # 낱말 표(몬스터·아이템·주문·지명·메뉴 이름) — 표 전체를 두 이미지에서 읽는다
    cm = textenc.charmap(DISC)
    for t in exetext.scan_tables(exe_o, cm) + exetext.detached_tables(exe_o, DISC):
        tbl, base, n = t["table"], t["base"], t["n"]
        if (tbl, base, n) in seen_tables:
            continue
        seen_tables.add((tbl, base, n))
        for i in range(n):
            ent = int.from_bytes(exe_o[tbl + 2 * i : tbl + 2 * i + 2], "little")
            kent = int.from_bytes(k_exe[tbl + 2 * i : tbl + 2 * i + 2], "little")
            jc, kc = codes_at(exe_o, base + ent), codes_at(k_exe, base + kent)
            if jc is None or kc is None:
                cnt["낱말 읽기 실패"] += 1
                continue
            jp, kr = jdec(jc), kdec(kc)
            tag = mark(jc, kc, jp, kr, False)
            rows.append((f"낱말표{tbl:#x}#{i}", clean(jp), "(번역 안 됨)" if tag == "원판만" else clean(kr), tag))
            cnt["낱말 " + (tag or "정상")] += 1
    # 고정 칸(시스템 메뉴 라벨 등)은 굽기가 **이어 붙여 다시 깔아** 라벨이 원판 오프셋에서 안 읽힌다(엔진은 종결마다 다음 문자열로 걷는다 — 10-20 실측:
    # 메뉴 화면은 정상). 그래서 원판 오프셋 ±0x40 안에서 **굽은 이미지의 같은 번역 코드열**을 찾아 그 자리의 바이트를 읽는다.
    import json as _json

    ui_kr = _json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui_ed3.json"), encoding="utf-8"))["strings"]
    for off in singles:
        jc, kc = codes_at(exe_o, off), codes_at(k_exe, off)
        if jc is None or kc is None:
            cnt["UI 읽기 실패"] += 1
            continue
        moved = ""
        row = ui_kr.get(f"0x{off:06X}")
        if row:
            try:
                want = bytes(b for w in hangul_map.encode(row["kr"].strip("\u3000"), DISC, table) for b in w.to_bytes(2, "little"))
            except KeyError:
                want = b""
            if want:
                at = k_exe.find(want, max(0, off - 0x40), off + 0x80)
                if at >= 0 and at != off:
                    kc, moved = codes_at(k_exe, at), f"자리 이동 {at - off:+#x}"
        jp, kr = jdec(jc), kdec(kc)
        tag = mark(jc, kc, jp, kr, False)
        rows.append((f"UI@{off:#x}", clean(jp), "(번역 안 됨)" if tag == "원판만" else clean(kr), tag or moved))
        cnt["UI " + (tag or moved.split(" ")[0] or "정상")] += 1

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "pairs.tsv"), "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        for r in rows:
            f.write("\t".join(clean(x) if k else x for k, x in enumerate(r)) + "\n")
    print(len(rows), dict(cnt))
    return rows, cnt


if __name__ == "__main__":
    main()
