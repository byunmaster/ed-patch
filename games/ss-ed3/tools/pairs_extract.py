#!/usr/bin/env python3
"""**롬에서 뽑은** 번호별 대사집 짝 표 — 원판 이미지와 제품 이미지의 같은 자리를 각각 디코드해 나란히 둔다(대본 JSON 이 아니다).

    python3 games/ss-ed3/tools/pairs_extract.py <출력폴더>        # pairs.tsv · manifest.md

열: 번호 · 원판 · 한글 · 표시.  표시: `원판만`(원판 글이 있는데 한글이 없다/일본어 그대로) · `한글만`(원판엔 글이 없다) ·
`둘 다 빔` · `포인터 공유`(같은 글을 맵 안 여러 자리에서 가리킨다 — 한 줄만 읽으면 된다). 정상 줄은 표시가 비었다.
표기: `⏎` 쪽 넘김 · `↵` 줄바꿈 · `{name:XX}` 런타임 주입 토큰 · `{ctl:XX}` 그 밖의 제어 바이트. 무동작 채움(`1A`)은 안 적는다.
연결 블록(`0E` 로 이어 붙은 글)은 한 줄로 잇는다(번호 `MAP001#223+224`).
⚠ 원판 문안이 든 파일이다 — 커밋하지 않는다(`.local/work/inbox`).
"""

import glob
import hashlib
import os
import re
import struct
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import check_no_loss as N
import common as C
import hangul_map as H
import json
import choice_tail as CT
import mapfile as M
import param as P
import reflow_script as RF
import reinsert as R
import reinsert_desc as RD
import reinsert_sys as RS
import strtab as ST
import typeset as T

FILL = R.FILL
TRAMP_ROWS = []  # (번호, 꼬리 바이트와 대조 통과 여부)
HANGUL = re.compile(r"[가-힣]")
KANA_KANJI = re.compile(r"[぀-ヿ一-鿿]")


def tidy(t):
    """줄 끝 칸 맞춤 공백(전각·반각)을 걷는다 — 재삽입이 예산을 채우려 붙인 것이다."""
    return re.sub(r"[ 　]+(?=↵|⏎|$)", "", t)


def show(text):
    """디코드한 글 → 표 칸 — 제어 표기를 사람이 읽는 꼴로."""
    t = text.replace("\f", "⏎").replace("\n", "↵")
    t = re.sub(r"<01><([0-9A-F]{2})>", r"{name:\1}", t)
    t = re.sub(r"<([0-9A-F]{2})>", r"{ctl:\1}", t)
    return tidy(t.replace("\t", " "))


def _plain(t):
    """제어 표기·공백만 걷은 꼴 — 비었는지 본다."""
    return re.sub(r"\{[^}]*\}|[⏎↵\s　]", "", t)


def _letters(t):
    """글자(가나·한자·한글·라틴·숫자)가 있나 — 부호만이면 없다."""
    return any(unicodedata.category(c)[0] in "LN" for c in _plain(t))


def mark(jp, kr, refs):
    pj, pk = _plain(jp), _plain(kr)
    if not pj and not pk:
        m = "둘 다 빔"
    elif not pk and pj:
        m = "원판만"
    elif _letters(jp) and not HANGUL.search(kr) and (KANA_KANJI.search(kr) or not _letters(kr)):
        m = "원판만"  # 원판 글이 있는데 한글이 없다(일본어 그대로이거나 부호만 남음)
    elif not pj and pk:
        m = "한글만"
    else:
        m = ""
    if refs >= 2 and m == "":
        m = "포인터 공유"
    return m


def ptr_refs(src, off):
    """맵 안에서 이 블록(머리 2B 앞)을 가리키는 BE32 자리 수 — 로드 주소 `0x200000 + 오프셋`."""
    n = 0
    for head in (off - 2, off):
        pat = struct.pack(">I", M.BASE + head)
        i = src.find(pat)
        while i >= 0:
            n += 1
            i = src.find(pat, i + 1)
    return n


def map_rows(disc, img, files, rev, rows, table=None):
    with C.open_disc(disc) as d:
        orig = {n: (l, s) for n, l, s in d.files()}
    for name in sorted(files):
        ok, stem = C.is_map_file(name)
        if not ok:
            continue
        with C.open_disc(disc) as d:
            src = d.read_extent(*orig[name])
        got = B.read_extent(img, *files[name])
        blocks = M.blocks(src)
        slots = R.name_slots(blocks, src)
        script, _ = R.load_script(stem)
        wides = set(R.wide(stem))
        covers = CT.covers(src, stem)
        skip = set()
        for i, blk in enumerate(blocks):
            if i in skip:
                continue
            ids, jps, krs = [i], [], []
            j = i
            while True:
                b = blocks[j]
                o, n = b["off"], len(b["body"])
                jp_body = src[o : o + n]
                if j in slots or o == M.NAME_OFF:
                    kr_body = got[o : got.index(b"\x00", o)]
                else:
                    kr_body = got[o : o + n]
                    #   무동작 패딩(`10 00 FF FF…` · `0E 00 FF FF…`)은 글 뒤다 — 종결부터 자른다(칸 끝에 걸칠 수 있어 4B 더 본다)
                    ext = got[o : o + n + 4]
                    cuts = [c for c in (ext.find(b"\x10\x00\xff\xff"), ext.find(b"\x0e\x00\xff\xff")) if 0 <= c <= n]
                    if cuts:
                        kr_body = ext[: min(cuts)]
                kr_body = kr_body.replace(FILL, b"")
                #   🔴 머리가 `02 xx` 가 아니라 ASCII 숫자 둘(`32 30` = 「20」)로 읽히는 블록(MAP021#25·37 「20年前は…」) — 숫자는 머리 자리에 그대로 남아 화면에 나오므로 글에 앞붙인다
                lead = src[o - 2 : o].decode("ascii") if b["head"][:1] in "3" and src[o - 2 : o].isdigit() else ""
                jps.append(lead + M.text_of(jp_body))
                krs.append(lead + N.decode(kr_body, rev))
                nxt = blocks[j + 1] if j + 1 < len(blocks) else None
                if src[o + n : o + n + 1] == b"\x0e" and nxt and nxt["off"] == o + n + 3:
                    j += 1
                    skip.add(j)
                    ids.append(j)
                    continue
                break
            #   🔴 트램펄린이 걸린 블록(선택지·간판·장 카드 — `choice_tail`)은 칸 안 글이 꼬리로 옮겨져 칸에서 직접 못 푼다 —
            #   대본의 그 문안을 꼬리 바이트와 대조해(`encode_kr` 결과가 맵 안에 있나) 받아들인다.
            tramp = [k for k in ids if str(k) in wides or str(k) in covers]
            if tramp:
                true = "".join(R.wide(stem).get(str(k)) or script.get(str(k), "") for k in ids)
                if true:
                    vk = [k for k in ids if str(k) in wides]
                    ok_all = all(H.encode_kr(R.IJ.resolve(script[str(k)] if str(k) not in wides else R.wide(stem)[str(k)]), table) in got for k in vk) if vk else True
                    krs = [R.wide(stem).get(str(k)) or script.get(str(k), "") for k in ids]
                    TRAMP_ROWS.append((f"{stem}#{ids[0]}", ok_all))
            jp, kr = show("\f".join(jps)), show("\f".join(krs))
            refs = ptr_refs(src, blk["off"])
            key = f"{stem}#{ids[0]}" + "".join(f"+{k}" for k in ids[1:])
            rows.append((key, jp, kr, mark(jp, kr, refs)))


def _dec(raw, rev):
    """NUL 문자열 바이트 → 표 칸 — 끝 표식(`10`)·채움은 걷는다."""
    t = N.decode(raw.replace(FILL, b""), rev)
    t = re.sub(r"(<10>)+$", "", t)
    return show(t.replace(T.DESC_NL, "\n"))


def _cstr(b, off, limit=None):
    e = b.find(b"\x00", off)
    e = len(b) if e < 0 else e
    if limit is not None:
        e = min(e, off + limit)
    return b[off:e]


def sys_rows(files, img, rev, rows):
    """`/0.BIN` · `/RLTPRG.BIN` · `/BLACK.BIN` — 원판 문자열 표를 포인터 자리(없으면 같은 오프셋)로 따라가 제품 이미지에서 푼다."""
    for f in RS.FILES:
        if f not in files:
            continue
        with C.open_disc(1) as d:
            orig = d.read(f)
        got = B.read_extent(img, *files[f])
        base = ST.load_base(f)
        targets = ST.ptr_targets(orig, base) if base is not None else {}
        seen = set()
        for s in ST.strings(orig, base):
            off = s["off"]
            new = off
            slots = targets.get(off) or []
            for at in slots:
                v = int.from_bytes(got[at : at + 4], "big") - base
                if v != off and 0 <= v < len(got):
                    new = v
                    break
            if (new, off) in seen:
                continue
            seen.add((new, off))
            jp = show(ST.text_of(s["raw"]).replace("<10>", "") if False else ST.text_of(s["raw"]))
            jp = re.sub(r"(\{ctl:10\})+$", "", jp)
            kr = _dec(_cstr(got, new), rev)
            #   🔴 원판 문자열 자리를 **패치 코드가 덮은** 경우(디버그 메뉴 구역 — 훅·스텁이 쓴다, 화면에 안 나오는 죽은 메뉴)는 글이 아니다 — 칸을 비운다
            if _cstr(got, new) != s["raw"] and not HANGUL.search(kr) and not re.search(r"[A-Za-z]{3}", kr):
                kr = ""  # 원판과 다른데 한글도 영문도 아니다 — 코드 바이트다
            rows.append((f"SYS:{f}+{off:#x}", jp, kr, mark(jp, kr, len(slots))))


def param_rows(img, files, rev, rows):
    """`PARAM.BIN` — 이름(적·아이템·마법)은 레코드 칸에서, 아이템 설명은 레코드 포인터를 따라, 마법 설명은 조각 순서로."""
    got = B.read_extent(img, *files[P.PATH])
    src = P.load()
    for label, tbl in (("적", P.ENEMY), ("아이템", P.ITEM), ("마법", P.SPELL)):
        base, stride, count = tbl
        for k in range(count):
            o = base + k * stride
            jp = P._at(src, o, stride)
            if not jp or jp in P.MARKS:
                continue
            kr = _dec(_cstr(got, o, stride), rev)
            rows.append((f"PARAM:{label}#{k}", show(jp), kr, mark(jp, kr, 1)))
    # 아이템 설명 — 레코드 +0x40 포인터(옛·새)를 따른다
    off, st, cnt = P.ITEM
    area = P.DESC_ITEM
    for i in range(cnt):
        nm = P._at(src, off + i * st, st)
        if not nm or nm in P.MARKS:
            continue
        a_old = int.from_bytes(src[off + i * st + 0x40 : off + i * st + 0x44], "big") + off - area[0]
        a_new = int.from_bytes(got[off + i * st + 0x40 : off + i * st + 0x44], "big") + off
        if not 0 <= a_old < len(src) or a_old < area[0] or a_old >= area[1]:
            continue
        jp = _cstr(src, a_old).decode("shift_jis", errors="replace")
        if jp.isascii():
            continue
        jp = show(jp.replace(T.DESC_NL, "\n"))
        kr = _dec(_cstr(got, a_new), rev)
        rows.append((f"PARAM:아이템 설명#{i}", jp, kr, mark(jp, kr, 1)))
    # 마법·기술 설명 — 같은 규약(NUL 조각 순서)
    area = P.DESC_SPELL
    ps, pg = src[area[0] : area[1]].split(b"\x00"), got[area[0] : area[1]].split(b"\x00")
    k = 0
    for raw, now in zip(ps[:-1], pg[:-1], strict=False):
        if not raw:
            continue
        try:
            t = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if t.isascii():
            continue
        jp = show(t.replace(T.DESC_NL, "\n"))
        kr = _dec(now, rev)
        rows.append((f"PARAM:마법 설명#{k}", jp, kr, mark(jp, kr, 1)))
        k += 1


def book_rows(files, img, rev, rows):
    """읽을거리(`BOOK*.BIN`) — 문단(줄 묶음) 단위. 원판 줄 칸에 그대로 구운 한글을 같은 오프셋에서 푼다."""
    import book as BK

    for f in sorted(files):
        if not re.fullmatch(r"/SYSTEM/BOOK\d+\.BIN", f):
            continue
        with C.open_disc(1) as d:
            orig = d.read(f)
        got = B.read_extent(img, *files[f])
        lines = [dict(s, text=ST.text_of(s["raw"])) for s in ST.strings(orig, ST.load_base(f))]
        for pi, (at, rws) in enumerate(BK.paragraphs(lines)):
            seg = lines[at : at + len(rws)]
            jp = "↵".join(show(x["text"]).rstrip("　 ") for x in seg)
            kr = "↵".join(_dec(got[x["off"] : x["off"] + len(x["raw"])], rev).rstrip("　 ") for x in seg)
            rows.append((f"{f[8:-4]}#{pi}", jp, kr, mark(jp, kr, 1)))


def video_rows(rows):
    """무비 자막(하드서브)·크레딧 자막 — 원판엔 자막이 없다(영상·음성만). 제품에 굽는 줄을 `movie.json`·`voice_credits.json` 에서 읽는다."""
    with open(os.path.join(C.GAME_DIR, "script", "movie.json"), encoding="utf-8") as f:
        m = json.load(f)
    for mid, lines in m.items():
        if mid.startswith("_") or not isinstance(lines, list):
            continue
        for k, (_a, _b, t) in enumerate(lines, 1):
            rows.append((f"{mid}#{k}", "", show(t), mark("", t, 1)))
    with open(os.path.join(C.GAME_DIR, "script", "voice_credits.json"), encoding="utf-8") as f:
        v = json.load(f)
    seen = {}
    for sub in v.get("subs", []):
        t = "\n".join(sub["lines"])
        seen[sub["n"]] = seen.get(sub["n"], 0) + 1
        #   같은 번호가 시각만 다르게 두 번 나오는 줄(35·48·63·77 — 그림이 바뀌는 자리에서 같은 문안을 다시 띄운다)은 뒤에 `b` 를 붙여 가른다
        key = f"V20#{sub['n']}" + ("b" if seen[sub["n"]] > 1 else "")
        rows.append((key, "", f"[{sub.get('who', '')}] " + show(t), "한글만"))


def voice_rows(rows):
    """음성 자막 — 원판엔 자막이 없다(음성만). 제품 이미지에 구워 넣은 줄과 같은 값을 `voice.json` 에서 읽는다(롬 디코드는 스텁 슬롯 파서가 필요해 안 했다)."""
    with open(os.path.join(C.GAME_DIR, "script", "voice.json"), encoding="utf-8") as f:
        v = json.load(f)
    for vid, e in v.items():
        if vid.startswith("_") or not isinstance(e, dict):
            continue
        its = (e.get("items") or []) + [h for h in e.get("hooks", []) if h.get("lines") and not h.get("preload")]
        for k, h in enumerate(its, 1):
            kr = show("\n".join(h["lines"]))
            who = f"[{h['who']}] " if h.get("who") else ""
            rows.append((f"{vid}#{k}", "", who + kr, mark("", kr, 1)))


DEBUG_JP = re.compile(r"デバ[ッグ]|テスト|設定くん|本[０-９]{2}|ＦＬＧ|ムービー|エンディング|エフェクト|セレクトマップ|ルーレット$|^タイトル$|^ティ変更$|パーティ構成|すべて無くしました|零")
JUNK = re.compile(r"^[^\u3041-\u3096\u30a1-\u30fa]*[A-Za-z%/!][^\u3041-\u3096]*$")


def classify_only_jp(rows):
    """`원판만` 줄을 셋으로 — 디버그·개발용 / 파서 오탐(코드 바이트가 일본어처럼 읽힌 것) / 번역 누락 의심."""
    dbg, junk, sus = [], [], []
    for r in rows:
        if r[3] != "원판만":
            continue
        k, jp, kr = r[0], r[1], r[2]
        m = re.match(r"SYS:/0\.BIN\+(0x[0-9a-f]+)", k)
        in_dbg_zone = bool(m) and 0x12000 <= int(m.group(1), 16) < 0x16000  # `/0.BIN` 디버그 메뉴·개발용 구역(훅·스텁도 여기 산다)
        if k.startswith("MAP000#") or DEBUG_JP.search(jp) or in_dbg_zone or k == "MAP002#1" or (k.startswith("SYS:") and kr == ""):
            dbg.append(r)
        elif k.startswith("SYS:") and JUNK.match(jp) and len(jp) < 12:
            junk.append(r)
        elif k.startswith("SYS:") and not re.search(r"[\u3041-\u3096\u30a1-\u30fa]{2}", jp):
            junk.append(r)
        elif k.startswith("MAP") and (jp.count("・") + jp.count("！") + jp.count("？") + jp.count("　")) >= len(jp) - 1:
            junk.append(r)  # 부호뿐인 줄(・・・？ 류) — 번역이 부호만 남은 것이 아니라 한글 칸이 부호만이다
        else:
            sus.append(r)
    return dbg, junk, sus


def classify_hangul_only(rows):
    """`한글만` 줄을 부류로 — 자막 대본(음성·크레딧·무비) / 재조판으로 쪽이 늘어난 맵 대사 / 그 밖."""
    sub = other = 0
    rest = []
    for r in rows:
        if r[3] != "한글만":
            continue
        if re.match(r"(V\d+|M\d+)#", r[0]):
            sub += 1
        else:
            other += 1
            rest.append(r)
    return sub, other, rest


JOSA_HEAD = re.compile(r"^(은|는|이|가|을|를|의|에게|에서|에|와|과|도|만|으로|로|라고|이라고|라는|이다|입니다|요)(?=[\s.,!?…~〜]|$)")


def reflow_report():
    """어절 재조판을 **안 한 쪽**(줄 수 제한으로 원문 구조를 둔 것)을 센다 — `(전체 여러 줄 쪽, 둔 쪽, 예 목록, 낱말 갈림 의심 줄바꿈 수)`."""
    names = RF._names()
    pages = kept = cut = 0
    ex, reasons = [], {"3줄 초과": 0, "줄이 늚": 0}
    for f in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "MAP*.json"))):
        doc = json.load(open(f, encoding="utf-8"))
        for k, v in doc.items():
            if not isinstance(v, str) or "\n" not in v or T.is_narration(v):
                continue
            for pg in v.split(T.PAGE):
                lines = [x for x in pg.split("\n") if x.strip()]
                ideal = RF.ideal_lines(pg, names)
                if ideal is None:
                    continue
                pages += 1
                if ideal != lines:
                    kept += 1
                    reasons["3줄 초과" if len(ideal) > T.WIN_ROWS else "줄이 늚"] += 1
                    if len(ex) < 6:
                        ex.append((os.path.basename(f)[:-5], k, lines, ideal))
                    for a, b in zip(lines, lines[1:], strict=False):
                        if JOSA_HEAD.match(b) and a and "가" <= a[-1] <= "힣":
                            cut += 1
    return pages, kept, reasons, ex, cut


def name_splits(rows):
    """맵 대사 한글 칸에서 **띄어 쓴 정본 이름**이 줄·쪽 경계에서 갈린 곳 수."""
    names = RF._names()
    n, ex = 0, []
    for r in rows:
        if not r[0].startswith("MAP"):
            continue
        for nm in names:
            w = nm.split(" ")
            for i in range(len(w) - 1):
                for sep in ("↵", "⏎"):
                    if w[i] + sep + w[i + 1] in r[2]:
                        n += 1
                        if len(ex) < 5:
                            ex.append((r[0], nm))
    return n, ex


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    rev = N.reverse(H.load(), H.load_low())
    img = build.out_paths(1)[0]
    files = {n: (l, s) for n, l, s, *_ in build.patched(1)}
    rows = []
    map_rows(1, img, files, rev, rows, H.load())
    sys_rows(files, img, rev, rows)
    param_rows(img, files, rev, rows)
    book_rows(files, img, rev, rows)
    voice_rows(rows)
    video_rows(rows)
    with open(os.path.join(out, "pairs.tsv"), "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    import collections

    cnt = collections.Counter(r[3] or "정상" for r in rows)
    fam = collections.Counter()
    for r in rows:
        k = r[0]
        fam["맵 대사" if k.startswith("MAP") else "시스템 문자열" if k.startswith("SYS:") else "PARAM(이름·설명)" if k.startswith("PARAM:") else "읽을거리" if k.startswith("BOOK") else "무비 자막" if re.match(r"M\d+#", k) else "음성·크레딧 자막"] += 1

    def sha1(path):
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                h.update(chunk)
        return h.hexdigest()

    dbg, junk, sus = classify_only_jp(rows)
    sub, other, rest = classify_hangul_only(rows)
    pages, kept, reasons, rex, cut = reflow_report()
    nsplit, nex = name_splits(rows)
    extra = [
        "## ① `한글만` " + str(cnt["한글만"]) + " 줄의 부류",
        f"- 자막 대본에서 읽은 것(음성·크레딧·무비 — 원판에 글이 없다): {sub}",
        "- 재조판으로 쪽이 늘어난 것: 0 — 재조판은 쪽 넘김(`⏎`)을 그대로 두고 쪽 안에서만 줄을 다시 짠다(쪽 수 불변). 맵 대사 `한글만` 은 " + str(sum(1 for r in rest if r[0].startswith('MAP'))) + " 줄이다.",
        f"- 그 밖: {other}" + ("" if not rest else " — " + ", ".join(r[0] for r in rest[:12])),
        "  - 그 밖 줄은 원판 디코드가 빠진 것이 아니다 — `/0.BIN` 디버그 메뉴 구역(0x12000~)에서 원판 쪽은 공백뿐인 줄이고, 제품 쪽은 훅·스텁 코드 바이트가 글자처럼 읽힌 것이다(화면에 안 나오는 죽은 메뉴)." if rest else "",
        "",
        f"## ② `원판만` {cnt['원판만']} 줄의 부류",
        f"- 디버그·개발용 문자열(MAP000 개발용 블록 · `/0.BIN` 0x12000~0x16000 디버그 메뉴 구역 · 훅 코드가 덮은 자리 · 零號機 시험 레코드 · MAP002#1 시험 이름): {len(dbg)}",
        f"- 파서 오탐(코드 바이트가 일본어처럼 읽힌 `dよ`·`/割` 류 · 부호뿐인 줄): {len(junk)}",
        f"- **번역 누락 의심: {len(sus)}**" + ("" if not sus else " — " + " · ".join(f"{r[0]}「{r[1][:14]}」" for r in sus[:30])),
        "",
        "## ③ 어절 재조판을 안 한 쪽(줄 수 제한으로 원문 구조 유지)",
        f"- 여러 줄 쪽 {pages} 중 원문 구조로 둔 쪽: **{kept}** (3줄 초과 {reasons['3줄 초과']} · 줄이 늚 {reasons['줄이 늚']})",
        *[f"  - 예 {k}[{b}]: {a!r} → 이상형 {i!r}" for k, b, a, i in rex],
        f"- 원 구조로 남은 쪽의 줄 시작이 조사로 보이는(낱말이 줄 가운데서 끊겼을 의심) 줄바꿈: {cut} 곳(휴리스틱 — 원문 구조가 어절 사이에서 끊겼으면 0)",
        "",
        f"## ④ 띄어 쓴 정본 이름이 줄·쪽 사이에서 갈린 곳(맵 대사 한글 칸, 롬 디코드): {nsplit}" + ("" if not nex else " — " + ", ".join(f"{a}({b})" for a, b in nex)),
    ]
    extra = [x for x in extra if x != ""]
    orig = C.DISC_BIN
    prod = {d: build.out_paths(d)[0] for d in (1, 2)}
    lines = [
        "# pairs.tsv manifest (ss-ed3)",
        "",
        "열: 번호 · 원판 · 한글 · 표시. 표시 — `원판만`(원판 글이 있는데 한글이 없다/일본어 그대로) · `한글만`(원판엔 글이 없다) · `둘 다 빔` · `포인터 공유`(맵 안 둘 이상의 자리가 같은 블록을 가리킨다). 정상 줄은 비었다.",
        "표기: `⏎` 쪽 넘김 · `↵` 줄바꿈 · `{name:XX}` 런타임 주입 토큰 · `{ctl:XX}` 그 밖의 제어 바이트. 무동작 채움(`1A`·`FF FF` 패딩)은 안 적었다. 연결 블록(`0E` 로 이어 붙은 글)은 한 줄로 잇고 번호를 `MAP001#223+224` 로 적었다.",
        "",
        "## 이미지",
        f"- 원판 Disc1 `{os.path.basename(orig[1])}` sha1 {sha1(orig[1])}",
        f"- 원판 Disc2 `{os.path.basename(orig[2])}` sha1 {sha1(orig[2])}",
        f"- 제품 Disc1 `{os.path.basename(prod[1])}` sha1 {sha1(prod[1])}",
        f"- 제품 Disc2 `{os.path.basename(prod[2])}` sha1 {sha1(prod[2])}",
        "",
        f"## 분모 {len(rows)} 줄",
    ]
    lines += [f"- {k}: {v}" for k, v in fam.most_common()]
    lines += ["", "## 표시별"] + [f"- {k}: {v}" for k, v in cnt.most_common()]
    lines += [
        "",
        *extra,
        "## 방법",
        "- **맵 대사**: 원판 이미지의 맵 블록(`mapfile.blocks`)마다 원판 바이트를 `mapfile.text_of` 로, 제품 이미지의 **같은 오프셋**을 배정표 역변환(`check_no_loss.decode`)으로 푼다. 대본 JSON 이 아니다.",
        "- **시스템 문자열**(`/0.BIN` · `/RLTPRG.BIN` · `/BLACK.BIN`): 원판 문자열 표(`strtab.strings`)를 포인터 자리(없으면 같은 오프셋)로 따라 제품 이미지에서 푼다(옮긴 문자열은 새 포인터를 따른다).",
        "- **PARAM**: 이름(적·아이템·마법)은 레코드 칸에서, 아이템 설명은 레코드 `+0x40` 포인터(옛·새)를 따라, 마법·기술 설명은 NUL 조각 순서로 푼다.",
        "- **읽을거리**: `BOOK*.BIN` 을 원판 줄 오프셋 그대로 푼다(문단 단위, 줄은 `↵`).",
        "",
        "## 한계 — 읽을 때 알아 둘 것",
        f"- **음성 자막·무비 자막·크레딧 자막은 원판에 글이 없다**(음성·영상뿐) — 원판 칸이 비고 `한글만` 으로 표시한다. 한글 칸은 제품에 굽는 줄을 `voice.json`·`movie.json`·`voice_credits.json` 에서 읽었다(ROM 의 자막 슬롯 파서가 따로 필요해 디코드하지 않았다). 일본어 원문은 `work/review` 받아쓰기(재청취 포함)에 있고 초벌이다.",
        f"- **트램펄린 블록 {len(TRAMP_ROWS)} 줄**(선택지·간판·장 카드): 칸 안 글이 맵 꼬리로 옮겨져 칸에서 직접 못 푼다. 대본의 그 문안을 `encode_kr` 해 맵 바이트 안에 있는지 대조했고 {sum(1 for _, o in TRAMP_ROWS if o)}/{len(TRAMP_ROWS)} 통과했다.",
        "- **디버그 메뉴·개발용 문자열**은 번역 대상이 아니다(화면에 안 나온다 — design.md): `원판만` 대부분이 이것이다(MAP000 개발용 블록 · `/0.BIN` 디버그 메뉴 `本００~` · `ＦＬＧ設定` 등). 원판 자리를 훅·스텁 코드가 덮은 문자열은 한글 칸을 비웠다.",
        "- **디스크 2** 의 맵·시스템 파일은 디스크 1 과 바이트 같다(두 장 계약 — `check_discs`)고 보고 디스크 1 만 뽑았다.",
        "- **그림으로 된 글자**(책 표지 · HP 이름판 · 화면 그림 · 지명 배너 그림)와 **스태프롤**(정본 대상 아님)은 뺐다.",
        "- 쉼표·마침표 등 부호 칸은 폭 때문에 전각 공백이 붙어 있을 수 있다(`쥬리오　`) — 칸 맞춤이다.",
    ]
    with open(os.path.join(out, "manifest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(len(rows), dict(cnt), dict(fam))


if __name__ == "__main__":
    main()
