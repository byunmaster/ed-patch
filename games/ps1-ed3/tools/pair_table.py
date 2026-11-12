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
import font
import hangul_map
import poolpack
import scriptmap
import textenc
import uitext

DISC = "ed3"
UNK = "{{c{:03x}}}"
KAGI_BACK = str.maketrans(font.KAGI)


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
        return "".join(out).translate(KAGI_BACK)  # 반 칸 낫표 글리프(사설 글자) → 「」『』

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


def picture_rows(cnt):
    """그림에 박힌 글(오프닝·엔딩 내레이션 · 크레딧 라벨 · 장 끝 띠) — 대사 바이트가 아니라 **그림**이라 코드열이 없다.

    한글 = 커밋된 정본(`narration_ed3.json` · `graphics_ed3.json` · 정본 장 제목). 원판 = 내레이션은 `work/review/narration_draft.md`(로컬 전용 — 없으면 빈칸),
    크레딧·띠는 원판이 그림 픽셀이라 글로 없다(자리만 적는다). 일본어 글자가 없어도(별밭·빈 장 포함) 행을 둔다.
    """
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import json

    out = []
    nar = json.load(open(os.path.join(here, "narration_ed3.json"), encoding="utf-8"))["groups"]
    by = {g["name"]: g["lines"] for g in nar}
    # 원판 = 초벌 대조표(로컬)에서 절마다 원문 열을 읽는다
    jp_sec = {}
    draft = os.path.join(here, "work", "review", "narration_draft.md")
    if os.path.exists(draft):
        sec = None
        for ln in open(draft, encoding="utf-8"):
            ln = ln.rstrip("\n")
            m = re.match(r"## (오프닝 [①②③④]|엔딩 액자|엔딩)", ln)
            if m:
                sec = m.group(1)
                jp_sec[sec] = []
            elif sec and ln.startswith("|") and not ln.startswith("| ---") and "원문" not in ln:
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if len(cells) >= 3:  # 엔딩 표: 자리 | 원문 | 한국어
                    jp_sec[sec].append((cells[0].strip("`"), cells[1]))
                else:
                    jp_sec[sec].append(("", cells[0]))

    def jp_of(sec, key=None):
        r = jp_sec.get(sec)
        if r is None:
            return ""
        if key is None:
            return "↵".join(x for _a, x in r)
        cur, res = None, []
        for a_, x in r:
            if a_:
                cur = a_
            if cur == key:
                res.append(x)
        return "↵".join(res)

    pics = [
        ("오프닝①(DATA3_0)", "opening_intro", jp_of("오프닝 ①")),
        ("오프닝②(DATA3_1)", "opening_legend", jp_of("오프닝 ②")),
        ("오프닝③두루마리앞(DATA2_3+4)", "opening_scroll_1", jp_of("오프닝 ③")),
        ("오프닝④두루마리뒤(DATA2_6+7)", "opening_scroll_2", jp_of("오프닝 ④")),
    ]
    for i in (1, 3, 4, 5, 6, 7, 8, 9):
        pics.append((f"엔딩_{i}(ENDDATA1_{i})", f"ending_{i}", jp_of("엔딩", f"_{i}")))
    pics.append(("엔딩 액자(ENDDATA2_1)", "ending_frame", jp_of("엔딩 액자")))
    for label, name, jp in pics:
        kr = "↵".join(by[name])
        rows_ = (f"그림:{label}", jp or "(원문 초벌 대조표 없음)", kr, "그림 글")
        out.append(rows_)
        cnt["그림 내레이션"] += 1

    g = json.load(open(os.path.join(here, "graphics_ed3.json"), encoding="utf-8"))["images"]
    for im in g:
        if im.get("kind") != "credits":
            continue
        tag = f"그림:크레딧({im['member'].split('!')[-1]}[{im['index']}])"
        labels = im.get("labels")
        if not labels:
            out.append((tag, "(그림 — 글자 없는 빈 장)", "(그대로)", "그림 글 · 원판 빈 장"))
            cnt["그림 크레딧 빈 장"] += 1
            continue
        for y0, y1, kr in labels["rows"]:
            out.append((f"{tag}y{y0}-{y1}", "(그림 픽셀 — 원판 일본어)", kr, "그림 글"))
            cnt["그림 크레딧 줄"] += 1

    # 장 끝 띠 — 정본 장 제목(원문|한글)으로 「…おわり」·「次章…」 두 줄을 짝으로
    import chapter_end

    titles = chapter_end.chapter_titles()
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
    import canon

    jp_t = {}
    for jp, kr in canon.table("ui", DISC).items():
        if "〜" in jp:
            continue
        if jp.startswith("序章　"):
            jp_t[0] = jp.split("　", 1)[1]
        elif jp.startswith("第") and len(jp) > 3 and jp[2] == "章" and jp[3] == "　" and jp[1] in "１２３４５６７":
            jp_t["１２３４５６７".index(jp[1]) + 1] = jp.split("　", 1)[1]
    for n in range(7):
        a_kr, b_kr = chapter_end.line_parts(n, titles)
        txt = lambda parts: "".join(v if k in ("text", "q") else " " for k, v in parts if k != "gap" or v >= 7)
        pre = "序章" if n == 0 else f"第{'１２３４５６７'[n - 1]}章"
        out.append((f"그림:장끝띠{n}A", f"{pre}「{jp_t.get(n, '?')}」…おわり (띠 그림)", " ".join(txt(a_kr).split()), "그림 글 · 원판 문구는 정본 제목으로 복원"))
        out.append((f"그림:장끝띠{n}B", f"次章「{jp_t.get(n + 1, '?')}」 (띠 그림)", " ".join(txt(b_kr).split()), "그림 글 · 원판 문구는 정본 제목으로 복원"))
        cnt["그림 장끝 띠"] += 2
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr-cue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--product", action="store_true", help="제품 롬 — 글리프 배정을 정본(hangul_map_ed3.json)에서 읽는다(시험 롬이 아니다)")
    a = ap.parse_args()
    binp = os.path.splitext(a.kr_cue)[0] + ".bin"
    tree = common.iso_tree(binp)[0]
    if a.product:
        table = hangul_map.load(DISC)
    else:
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
    # 영문 대문자·숫자는 반각 훅(HUD 글꼴·전각 Ｌ 등)이 다른 그림으로 구워 정본 글자 그림과 다른 게 정상이다 — 한글·부호가 어긋날 때만 멈춘다
    skew = [ch for ch in skew if not (a.product and ch.isascii())]
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
    # 🔴 사전(DTE)은 풀 문안 전체에서 짜이므로 빌드와 **같은 입력**이어야 같은 사전이 나온다 — 빌드는 풀 본문의 「」『』 를 반 칸 글리프로 바꿔 넣는다(build.py `pool_enc`).
    #    이걸 빠뜨리면 사전이 달라져 풀 380행이 낱말째 엉뚱하게 읽힌다(10-28 검수에서 「폴티아국」→「움직국」).
    kagi_tr = str.maketrans({v: k for k, v in font.KAGI.items()})
    pl = poolpack.apply(work, DISC, uitext.pool_rows(DISC), lambda kr: uitext.ui_codes(enc, kr.translate(kagi_tr)))
    # 풀 사전이 맞는지 — 새로 짠 사전이 굽은 이미지의 사전 자리와 같아야 한다(다르면 멈춘다)
    dsz = 4 * len(pl["merges"])
    if bytes(work[pl["dict_off"] : pl["dict_off"] + dsz]) != bytes(k_exe[pl["dict_off"] : pl["dict_off"] + dsz]):
        raise SystemExit("🔴 풀 사전이 굽은 이미지와 다르다 — 풀 행을 못 믿는다(문안·글자표가 이미지와 같은 시점인지)")
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

    for r in picture_rows(cnt):
        rows.append(r)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "pairs.tsv"), "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        for r in rows:
            f.write("\t".join(clean(x) if k else x for k, x in enumerate(r)) + "\n")
    print(len(rows), dict(cnt))
    return rows, cnt


if __name__ == "__main__":
    main()
