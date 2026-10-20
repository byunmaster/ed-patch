#!/usr/bin/env python3
"""**롬에서 뽑은 번호(포인터)별 대사집 짝 표** — 원판 롬과 구운 한글 롬의 바이트를 같은 포인터 자리에서 읽어 디코드해 나란히 둔다.

    python3 tools/rom_book.py --jp-bin <원판.bin> --kr-bin <한글 롬.bin> --out <sweep/pair>
산출: <out>/pairs.tsv (번호 · 원판 대사 · 한글 대사 · 표시) · <out>/manifest.md

## 방법 (촬영 없음 — 마스터 판정 「원문캡쳐는 중단」 10-20)
- **자리 목록**: `work/derived/scn_jp/*.json` 의 엔트리가 든 `ptr_at`(코드 리터럴 풀 안의 BE32 포인터 자리, 파일 오프셋)만 쓴다. **글은 안 쓴다.**
- **원판 대사**: 원판 롬 파일의 그 자리에서 BE32 포인터를 읽고 → 가리키는 곳의 NUL 종단 바이트를 cp932 로 디코드.
- **한글 대사**: 구운 롬 파일의 **같은 자리**에서 포인터를 읽고(이주·재배치로 목표가 옮겨졌어도 포인터가 따라간다) → 가리키는 NUL 종단 바이트를 디코드 —
  한글은 슬롯 SJIS 이므로 `hangul_map_11kanji.json` 의 역으로, 나머지는 cp932. 반각 곡선 따옴표 코드는 원 글자로.
  ⇒ 대본 JSON 이 아니라 **빌드가 실제로 넣은 바이트**다(배정 어긋남·누락·덮어쓰기·옛 칸 잔재가 그대로 드러난다).
- **표기**: 줄 바꿈 `/` · 쪽 넘김(`%c` 키 대기·창 끝) `⏎` · 화자 머리 `%c이름%c` → `【이름】` · 이름·아이템·수치 변수 `%s`·`%d` → `{name}`·`{num}` · 색 켜고 끄기 `%c…%c` 안의 변수는 변수만.
- **표시**: 원판만 있음 / 한글만 있음 / 둘 다 빔 / 포인터가 다른 번호와 같은 곳을 가리킴(구운 롬에서 서로 다른 두 번호의 포인터가 같은 목표 — 원판은 달랐던 것).
"""

import argparse
import glob
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

import common  # noqa: E402

DUMP = os.path.join(HERE, "..", "work", "derived", "scn_jp")


def _sha1(p):
    import hashlib

    h = hashlib.sha1()
    with open(p, "rb") as f:
        while b := f.read(1 << 24):
            h.update(b)
    return h.hexdigest()


def iso_path(table_id):
    if table_id in ("ED", "ED2"):
        return f"/{table_id}.BIN"
    return f"/BIN/{table_id}.BIN"


def cstr(d, off):
    if off < 0 or off >= len(d):
        return None
    end = d.find(b"\x00", off)
    return d[off : end if end >= 0 else len(d)]


def decode(raw, korean, rev, quotes):
    """바이트 → 대사집 표기. 한글 슬롯 SJIS·반각 따옴표 코드는 원 글자로."""
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c >= 0x80 and not (0xA0 <= c <= 0xDF):
            two = raw[i : i + 2]
            ch = rev.get(bytes(two)) if korean else None
            if ch is None:
                try:
                    ch = bytes(two).decode("cp932")
                except UnicodeDecodeError:
                    ch = "〓"
            out.append(ch)
            i += 2
            continue
        if c == 0x25 and i + 1 < len(raw) and raw[i + 1] in (0x73, 0x63, 0x64):  # %s %c %d
            out.append("%" + chr(raw[i + 1]))
            i += 2
            continue
        if c == 0x0A:
            out.append("\n")
        elif c < 0x20:
            out.append(f"⟨{c:02x}⟩")
        else:
            ch = quotes.get(c) if korean else None
            if ch is None:
                try:
                    ch = bytes([c]).decode("cp932")
                except UnicodeDecodeError:
                    ch = "〓"
            out.append(ch)
        i += 1
    return "".join(out)


def notate(s):
    """디코드 문자열 → 대사집 표기(줄 `/` · 쪽 `⏎` · 화자 `【】` · 변수 `{…}`)."""
    s = re.sub(r"^%c([^%\n]*)%c\n?", lambda m: f"【{m.group(1)}】", s)  # 화자 머리
    s = re.sub(r"%c(%[sd])%c", lambda m: "{name}" if m.group(1) == "%s" else "{num}", s)  # 색 안의 변수
    s = s.replace("%s", "{name}").replace("%d", "{num}")
    s = s.replace("%c", "⏎").replace("⟨08⟩", "⏎").replace("⟨09⟩", "⏎")  # 창 끝(08)·창 안 키 대기(09) 도 쪽 넘김
    s = s.replace("\n", "/")
    return s


def read_ptr(d, site, base):
    if site + 4 > len(d):
        return None
    v = struct.unpack(">I", d[site : site + 4])[0]
    t = v - base
    return t if 0 <= t < len(d) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jp-bin", required=True)
    ap.add_argument("--kr-bin", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    import font

    rev = {bytes(font.sjis_of_index(v)): k for k, v in json.load(open(os.path.join(HERE, "..", "hangul_map_11kanji.json"), encoding="utf-8"))["syllables"].items()}
    quotes = {v: k for k, v in font.HALF_QUOTES.items()}
    _f, jm = common.open_image(a.jp_bin)
    _f2, km = common.open_image(a.kr_bin)
    rows, shas = [], {}
    shared_orig = multi = multi_split = 0
    stats = {"원판만 있음": 0, "한글만 있음": 0, "둘 다 빔": 0, "포인터가 다른 번호와 같은 곳을 가리킴": 0}
    for dp in sorted(glob.glob(os.path.join(DUMP, "*.json"))):
        dd = json.load(open(dp, encoding="utf-8"))
        tid = dd["table_id"]
        if a.only and not re.search(a.only, tid):
            continue
        path = iso_path(tid)
        try:
            jd, kd = common.extract(path, jm), common.extract(path, km)
        except Exception:
            continue
        base = int(dd["source"]["base"], 16)
        per = []  # (entry, jt, kt, jraw, kraw)
        for e in dd["entries"]:
            site = int(e["ptr_at"][0], 16)
            jt, kt = read_ptr(jd, site, base), read_ptr(kd, site, base)
            jraw = cstr(jd, jt) if jt is not None else None
            kraw = cstr(kd, kt) if kt is not None else None
            per.append((e, site, jt, kt, jraw, kraw))
        # 구운 롬에서 목표를 공유하는 번호 — 원판 목표는 서로 달랐던 것만
        by_kt = {}
        for e, site, jt, kt, jraw, kraw in per:
            if kt is not None:
                by_kt.setdefault(kt, set()).add(jt)
        for e_ in dd["entries"]:
            if len(e_["ptr_at"]) > 1:
                multi += 1
                if len({read_ptr(kd, int(s_, 16), base) for s_ in e_["ptr_at"]}) > 1:
                    multi_split += 1
        shared_orig_here = sum(1 for kt_, js_ in by_kt.items() if len(js_) == 1 and sum(1 for x in per if x[3] == kt_) > 1)
        shared_orig += shared_orig_here
        for e, site, jt, kt, jraw, kraw in per:
            js = notate(decode(jraw, False, rev, quotes)) if jraw is not None else ""
            ks = notate(decode(kraw, True, rev, quotes)) if kraw is not None else ""
            flag = []
            if jraw is not None and jraw and not kraw:
                flag.append("원판만 있음")
            if kraw is not None and kraw and not jraw:
                flag.append("한글만 있음")
            if not js.strip("/ ⏎") and not ks.strip("/ ⏎"):
                flag.append("둘 다 빔")
            if kt is not None and len(by_kt.get(kt, ())) > 1:
                flag.append("포인터가 다른 번호와 같은 곳을 가리킴")
            for f in flag:
                stats[f] += 1
            rows.append([f"{tid}#{e['entry_id']}@{e['ptr_at'][0]}", js, ks, ";".join(flag)])
    # ── 고정 간격 표(메뉴 라벨·지명·파티 기본 이름) — 포인터가 아니라 표 칸이다. 두 롬의 같은 파일 오프셋 칸을 읽는다(표는 제자리에서 고친다).
    import dump_ui

    for key, path in dump_ui.FILES.items():
        jd, kd = common.extract(path, jm), common.extract(path, km)
        col = 1 if key == "ED" else 2
        specs = [(nm, e1, e2, st, n1, n2) for nm, e1, e2, st, n1, n2 in dump_ui.TABLES]
        specs += [(nm, e1, e2, st, n1, n2) for nm, e1, e2, st, n1, n2, _c in dump_ui.GLOSSARY_TABLES]
        for name, ed, ed2, stride, n, n2 in specs:
            off = (ed, ed2)[col - 1]
            if off is None:
                continue
            cnt = n2 if (col == 2 and n2) else n
            for i in range(cnt):
                p_ = off + i * stride
                jraw, kraw = cstr(jd, p_), cstr(kd, p_)
                js = notate(decode(jraw[:stride], False, rev, quotes)) if jraw is not None else ""
                ks = notate(decode(kraw[:stride], True, rev, quotes)) if kraw is not None else ""
                flag = []
                if js and not ks:
                    flag.append("원판만 있음")
                if ks and not js:
                    flag.append("한글만 있음")
                if not js and not ks:
                    flag.append("둘 다 빔")
                for f in flag:
                    stats[f] += 1
                rows.append([f"{key}표/{name}[{i}]@0x{p_:X}", js, ks, ";".join(flag)])
        if key in ("ED", "ED2"):
            for fk, o_, ln in dump_ui.PERSON_SLOTS:
                if fk != key:
                    continue
                jraw, kraw = cstr(jd, o_), cstr(kd, o_)
                js = notate(decode(jraw[:ln], False, rev, quotes)) if jraw is not None else ""
                ks = notate(decode(kraw[:ln], True, rev, quotes)) if kraw is not None else ""
                flag = ["둘 다 빔"] if not js and not ks else []
                for f in flag:
                    stats[f] += 1
                rows.append([f"{key}표/파티 기본 이름@0x{o_:X}", js, ks, ";".join(flag)])
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "pairs.tsv"), "w", encoding="utf-8") as f:
        f.write("번호\t원판 대사\t한글 대사\t표시\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    cats = {"씬 대사(ED1SCN·ED2SCN)": 0, "본체 포인터(ED·ED2)": 0, "몬스터 파일(ED2MON)": 0, "고정 간격 표": 0}
    for r in rows:
        k = r[0]
        if "표/" in k:
            cats["고정 간격 표"] += 1
        elif k.startswith("ED2MON"):
            cats["몬스터 파일(ED2MON)"] += 1
        elif "SCN" in k:
            cats["씬 대사(ED1SCN·ED2SCN)"] += 1
        else:
            cats["본체 포인터(ED·ED2)"] += 1
    print(f"행 {len(rows)} · 표시 {stats} · 분모 {cats} · 원판에서도 같은 곳을 가리키던 목표 {shared_orig}")
    with open(os.path.join(a.out, "manifest.md"), "w", encoding="utf-8") as f:
        f.write(
            f"""# 롬에서 뽑은 번호(포인터)별 대사집 짝 표
- 원판 롬: `{os.path.basename(a.jp_bin)}` sha1 {_sha1(a.jp_bin)}
- 한글 롬: `{os.path.basename(a.kr_bin)}` sha1 {_sha1(a.kr_bin)} (제품 롬 — 이 롬을 만든 HEAD)
- 분모: 행 {len(rows):,} — {', '.join(f'{k} {v:,}' for k, v in cats.items())} · 덤프 파일 {len(glob.glob(os.path.join(DUMP, '*.json')))}개
- 표시별 수: {', '.join(f'{k} {v}' for k, v in stats.items())} · (참고) 원판에서도 같은 곳을 가리키던 번호 묶음 {shared_orig} · 포인터 자리가 여럿인 번호 {multi} 중 구운 롬에서 자리마다 목표가 갈린 것 {multi_split}
- 방법: 모듈 주석(tools/rom_book.py) 참조 — 포인터 자리(`work/derived/scn_jp` 의 ptr_at)만 목록에서 쓰고, 글은 두 롬 이미지의 그 자리 BE32 포인터를 따라 읽은 바이트를 디코드한 것이다.
- 표기: 줄 바꿈 `/` · 쪽 넘김 `⏎`(%c 키 대기·창 끝 08·창 안 키 대기 09) · 화자 머리 `【이름】` · 변수 `{{name}}`(%s)·`{{num}}`(%d).
- 한계: ① 포인터 한 개당 한 줄이다 — 조건 분기(⟨조건⟩)는 코드 안에 있어 정적으로 가르지 않았다(분기마다 다른 포인터를 가리키면 번호가 따로 나온다). ② 화자 스킵 체인(블록 중간을 가리키는 포인터)과 호출 조각·이어 붙는 꼬리는 펼치지 않고 포인터별로 둔다. ③ 포인터 없는 고정 간격 표(메뉴 라벨·지명·파티 기본 이름)는 두 롬의 같은 오프셋 칸을 읽었다. ④ 그림 문자(타이틀·챕터 카드·HUD 판 그림)는 글이 아니라 이 표 밖이다. ⑤ 덤프가 문자열로 본 `ED#1262`·`ED#1266` 은 바이너리 데이터라 두 칸이 같다.
"""
        )


if __name__ == "__main__":
    main()
