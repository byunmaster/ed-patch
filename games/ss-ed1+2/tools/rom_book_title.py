#!/usr/bin/env python3
"""오프닝·엔딩 **자막(`TITLE.BIN` 고정 폭 레코드)** 을 짝 표에 얹는다 — 원판 자막 ↔ 우리 자막, 레코드 번호별.

짝 표(`rom_book.py`)는 대사·전투·표를 포인터로 짝짓는다. 자막은 포인터가 아니라 **고정 폭 레코드**(`dump_title.py`)
라서 표에 안 들어 있었다(마스터 10-21: 오프닝·엔딩·후일담 자막은 전수 범위). 이 도구가 **같은 레코드 자리**를
원판 롬 바이트와 한글 정본(`script/title.json`, 롬 되읽기 게이트가 바이트와 같음을 증명)에서 읽어 행으로 더한다.

    python3 tools/rom_book_title.py --jp-bin <원판.bin> --kr-bin <한글.bin> --out <폴더>   # <폴더>/pairs.tsv 끝에 더한다

- 번호: `TITLE#<구간>:<화면 줄>@0x<파일 오프셋>` — 구간 = ED1 오프닝·ED2 오프닝·ED1 엔딩·ED2 엔딩, 줄 번호는 화면 순서(1부터).
  저장은 역순이라(화면이 아래에서 위로 흐른다) 레코드 오프셋은 줄 번호가 커질수록 앞이다.
- 스태프롤(`ＣＲＥＤＩＴＳ` 이후)은 번역 대상이 아니라 **행에서 뺀다**(수는 manifest 에).
- 좌우 전각 공백(중앙정렬 채움)은 떼어 보인다. 글자 없는 레코드는 행에 안 넣고 수만 센다.
- 이미 `TITLE#` 행이 든 표에 다시 돌려도 그 행만 새로 쓴다(멱등).
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

import common  # noqa: E402
import dump_title as T  # noqa: E402

MARK = "ＣＲＥＤＩＴＳ"  # 스태프롤 표지(title_payload.MARK 와 같다)

SHORT = {"ED1 오프닝": "ED1오프닝", "ED2 오프닝": "ED2오프닝", "ED1 엔딩·스태프롤": "ED1엔딩", "ED2 엔딩·스태프롤": "ED2엔딩"}


def _dec_jp(rec):
    """원판 레코드 바이트 → 문자열(앞 제어 2B 는 뗀다)."""
    if len(rec) >= 2 and rec[0] == 0x00:
        rec = rec[2:]
    return rec.decode("cp932").strip("　 ")


def rows_of(jp_bin, kr_bin):
    """`(행, 통계)` — 원판은 롬 바이트에서, 한글은 정본 `script/title.json` 에서 뽑는다.

    🔴 한글 칸을 롬 바이트로 못 읽는 까닭: 자막 글리프는 음절 슬롯(`hangul_map.json`)뿐 아니라 **조각 정본**
       (`hangul_tiles.json`)의 슬롯도 써서 코드 → 글자 역표가 한 장이 아니다. 대신 `check.sh` 의 「자막 되읽기」
       게이트가 **롬 바이트가 정본과 레코드·글리프 모두 어긋남 0** 임을 매번 증명한다 — 그래서 같은 값이다.
       줄 수가 롬 레코드 수와 다르면 여기서 멈춘다(어긋난 채 짝짓지 않는다).
    """
    with open(os.path.join(HERE, "..", "script", "title.json"), encoding="utf-8") as f:
        ko = json.load(f)
    _f, jm = common.open_image(jp_bin)
    jraw = T._load(jm)
    rows, stat = [], {"구간": 0, "글자 있는 줄": 0, "글자 없는 줄": 0, "스태프롤 제외": 0, "원판만 있음": 0, "한글만 있음": 0}
    for off, recs in T.runs(jraw):
        name = T.LABELS[off]
        stat["구간"] += 1
        ordered = list(reversed(recs))  # 화면 순서
        kl = ko[name]
        assert len(kl) == len(ordered), f"{name}: 롬 레코드 {len(ordered)} ≠ 정본 {len(kl)}줄 — 짝을 못 짓는다"
        staff = False
        for i, ((_t, o, n), k) in enumerate(zip(ordered, kl), 1):
            js = _dec_jp(jraw[o : o + n])
            ks = k.strip("　 ")
            if MARK in js:
                staff = True
            if staff:
                stat["스태프롤 제외"] += 1
                continue
            if not js and not ks:
                stat["글자 없는 줄"] += 1
                continue
            stat["글자 있는 줄"] += 1
            flag = []
            if js and not ks:
                flag.append("원판만 있음")
                stat["원판만 있음"] += 1
            if ks and not js:
                flag.append("한글만 있음")
                stat["한글만 있음"] += 1
            rows.append([f"TITLE#{SHORT[name]}:{i}@0x{o:X}", js, ks, ";".join(flag)])
    return rows, stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jp-bin", required=True)
    ap.add_argument("--kr-bin", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, stat = rows_of(a.jp_bin, a.kr_bin)
    p = os.path.join(a.out, "pairs.tsv")
    with open(p, encoding="utf-8") as f:
        head, *body = f.read().split("\n")
    body = [x for x in body if x and not x.startswith("TITLE#")]
    body += ["\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) for r in rows]
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + "\n" + "\n".join(body) + "\n")
    print(f"자막 행 {len(rows)} · {stat}")
    mp = os.path.join(a.out, "manifest.md")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            txt = f.read()
        txt = "\n".join(x for x in txt.split("\n") if not x.startswith("- 자막(TITLE")) + (
            "" if txt.endswith("\n") else "\n"
        )
        txt += (
            f"- 자막(TITLE.BIN 고정 폭 레코드, 마스터 10-21 범위 편입): 행 {len(rows)} · 글자 없는 줄 {stat['글자 없는 줄']} · "
            f"스태프롤(번역 대상 아님) 제외 {stat['스태프롤 제외']} · 구간 {stat['구간']} — 번호 `TITLE#<구간>:<화면 줄>@<오프셋>`, "
            f"방법은 tools/rom_book_title.py(원판은 롬 레코드 자리, 한글은 정본 title.json — 되읽기 게이트가 롬 바이트와 어긋남 0 임을 증명)\n"
        )
        with open(mp, "w", encoding="utf-8") as f:
            f.write(txt)


if __name__ == "__main__":
    main()
