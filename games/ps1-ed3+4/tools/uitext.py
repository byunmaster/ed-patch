"""실행파일 UI 문안 정본 — 메뉴 · HUD · 전투 · 시스템 메시지.

대사(`script/`)와 갈라 둔 이유는 **자리가 다르기** 때문이다. UI 는 아카이브 멤버가 아니라
실행파일 안에 산다. 키는 **그 문자열의 실행파일 오프셋**이다 — 표가 있든 없든 통하고,
구역 라벨을 손봐도 안 밀린다.

```
ui_<disc>.json   {"strings": {"0x0A10B4": {"jp": "지문8자", "kr": "공격력"}}}
```

🔴 **원문은 안 담고 지문만 담는다.** 고유명사 정본(`glossary_`)은 원문을 키로 쓰는데 그건
   **낱말**이라 저작권 대상이 아니어서다(루트 CLAUDE.md). UI 엔 문장급이 섞여 있으므로
   (「メモリーカードが差されていません。」) 대사와 같은 규율로 간다.

## 길이 규칙이 자리마다 다르다

- **표가 있는 자리**는 칸(빈틈으로 끊긴 구간)이 예산이다 — 짧은 항목에서 빌려 쓸 수 있다.
  ED3 에선 메모리카드 문구 14개가 여기다(표 `0x0A13C8`).
- **표가 없는 자리**는 **길이 고정**이다(`len(kr) <= len(jp)`). ED3 메뉴·HUD 190개가 여기다.
  ⚠ 짧게 쓰면 뒤에 죽은 바이트가 남는데, 아무도 안 가리키므로 안전하다.
  ⚠ 한국어가 대개 짧아서(중앙 0.82) 이 제약이 실제로 아픈 자리는 드물다.

```bash
python3 tools/uitext.py --disc ed3 --review   # 검토표 (⚠ 커밋 금지 — 원문이 있다)
python3 tools/uitext.py --disc ed3 --sync     # 검토표 → 정본
python3 tools/uitext.py --disc ed3 --check    # 지문·길이 (게이트)
```
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_names
import exetext
import script as script_canon
import textenc

KINDS = ("menu", "text")  # 낱말(고유명사)은 `glossary_` 가 든다 — 여기는 UI 문안 + 실행파일 속 글(주문 설명·메모·읽을거리)


def canon_path(disc):
    return os.path.join(common.ROOT, f"ui_{disc}.json")


def exe_bytes(disc):
    lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
    return common.read_lba(disc, lba, size)


def sites(disc):
    """{오프셋: {"jp":…, "len":코드수, "table":(주소,base,N)|None, "budget":칸 바이트}}"""
    cm = textenc.charmap(disc)
    data = exe_bytes(disc)
    labels = dump_names.REGIONS[disc]
    tables = exetext.scan_tables(data, cm)
    # 표 항목의 오프셋 → (표, 칸 예산)
    in_table = {}
    for t in tables:
        tbl, base, n = t["table"], t["base"], t["n"]
        chunks = exetext.chunks(data, tbl, base, n)
        for lo, hi, starts in chunks:
            for off in starts:
                in_table[off] = ((tbl, base, n), hi - lo)
    out = {}
    # ⚠ max_len 64 — 기본 24 는 낱말 표용이라 주문 설명(최대 ~25) · 메모·읽을거리(~30)가 잘린다
    for r in dump_names.split(dump_names.regions(dump_names.strings(data, cm, max_len=64, newline=True)), labels):
        if labels.get(r["start"]) not in KINDS:
            continue
        for off, jp in zip(r["offs"], r["items"], strict=True):
            if not jp.strip():
                continue
            codes, _ = exetext.raw_string(data, off)
            tb, budget = in_table.get(off, (None, 0))
            out[off] = {"jp": jp, "len": len(codes or []), "table": tb, "budget": budget}
    return data, out


def load(disc):
    p = canon_path(disc)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    return {int(k, 16): v for k, v in doc["strings"].items()}


def save(disc, rows):
    rows = {f"0x{o:06X}": v for o, v in sorted(rows.items()) if v.get("kr")}
    p = canon_path(disc)
    if not rows:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"disc": disc, "strings": rows}, f, ensure_ascii=False, indent=1)


def review_path(disc):
    return os.path.join(common.REVIEW_DIR, f"ui_{disc}.json")


def write_review(disc):
    """검토표 — 원문 + 우리 문안 + **쓸 수 있는 길이**. ⚠ 커밋 금지."""
    _, ss = sites(disc)
    have = load(disc)
    out = {}
    for off, s in sorted(ss.items()):
        out[f"0x{off:06X}"] = {
            "jp": s["jp"],
            "kr": have.get(off, {}).get("kr", ""),
            "limit": f"{s['len']}자" if s["table"] is None else f"칸 {s['budget']}B",
        }
    os.makedirs(os.path.dirname(review_path(disc)), exist_ok=True)
    with open(review_path(disc), "w", encoding="utf-8") as f:
        json.dump({"disc": disc, "strings": out}, f, ensure_ascii=False, indent=1)
    return len(out)


def sync(disc):
    _, ss = sites(disc)
    p = review_path(disc)
    if not os.path.exists(p):
        raise SystemExit(f"검토표가 없다: {p}\n  먼저: uitext.py --disc {disc} --review")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    rows, n = {}, 0
    for k, row in doc["strings"].items():
        kr = (row.get("kr") or "").strip()
        if not kr:
            continue
        off = int(k, 16)
        if off not in ss:
            raise SystemExit(f"0x{off:06X} 가 원본에 없다 — 검토표가 낡았다")
        rows[off] = {"jp": script_canon.stamp(ss[off]["jp"]), "kr": kr}
        n += 1
    save(disc, rows)
    return n


def check(disc):
    """(옮긴 줄, 전체, [사유])"""
    _, ss = sites(disc)
    canon = load(disc)
    bad = []
    for off, row in sorted(canon.items()):
        s = ss.get(off)
        if s is None:
            bad.append(f"0x{off:06X}: 원본에 없는 자리")
            continue
        if script_canon.stamp(s["jp"]) != row["jp"]:
            bad.append(f"0x{off:06X}: 원문 지문이 다르다 — 번역이 남의 자리에 붙었다")
            continue
        if s["table"] is None and len(row["kr"]) > s["len"]:
            bad.append(
                f"0x{off:06X}: 길이 초과 {len(row['kr'])} > {s['len']} — 표가 없는 자리는 고정이다"
            )
    return len(canon), len(ss), bad


def apply(exe, disc, encode):
    """실행파일 bytearray 에 정본을 넣는다. `encode(kr) -> [코드]`.

    반환: (넣은 수, 자리가 없어 건너뛴 수). 🔴 **건너뛴 건 원문 그대로 남는다** —
    조용히 빼면 화면에서 그 줄만 사라진다.
    """
    _, ss = sites(disc)
    canon = load(disc)
    put = skipped = 0
    by_table = {}
    for off, row in sorted(canon.items()):
        s = ss.get(off)
        if s is None or script_canon.stamp(s["jp"]) != row["jp"]:
            skipped += 1
            continue
        try:
            codes = encode(row["kr"])
        except KeyError:
            skipped += 1
            continue
        if s["table"] is None:
            if len(codes) > s["len"]:
                skipped += 1
                continue
            struct.pack_into(f"<{len(codes)}H", exe, off, *codes)
            struct.pack_into("<H", exe, off + len(codes) * 2, exetext.TERM_FFFF)
            put += 1
        else:
            by_table.setdefault(s["table"], {})[off] = codes
    for (tbl, base, n), want in by_table.items():
        ents = struct.unpack_from(f"<{n}H", bytes(exe), tbl)
        cur = []
        for x in ents:
            codes, _ = exetext.raw_string(bytes(exe), base + x)
            cur.append(want.get(base + x, codes or []))
        try:
            new, _ = exetext.rebuild(bytes(exe), tbl, base, n, cur)
        except exetext.ExeTextError:
            skipped += len(want)
            continue
        exe[:] = bytearray(new)
        put += len(want)
    return put, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    common.verify_source(a.disc)
    if a.review:
        print(f"{a.disc}: UI 검토표 {write_review(a.disc)}줄 → {review_path(a.disc)}  ⚠ 커밋 금지")
        return 0
    if a.sync:
        print(f"{a.disc}: 정본으로 옮긴 줄 {sync(a.disc)}")
        return 0
    n, total, bad = check(a.disc)
    print(f"{a.disc}: UI 문안 {n}/{total}줄 ({n * 100 // max(total, 1)}%)")
    for m in bad[:10]:
        print(f"  🔴 {m}")
    if a.check:
        print(f"{a.disc}: UI 문안 — {'🔴 어긋났다' if bad else '✅ 원본과 맞는다'}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
