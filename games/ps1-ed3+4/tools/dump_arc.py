"""디스크의 GMF 아카이브를 전부 열어 멤버 목록·실물을 work/derived 로 뽑는다.

`--list` 만 주면 목록(멤버 이름·크기·머리 12B)만 찍고 아무것도 안 쓴다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def archives(disc):
    """아카이브로 볼 파일 — TOC 가 서면 아카이브다(확장자로 안 고른다)."""
    out = []
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if size < 64 or size > 64 << 20:
            continue
        head = common.read_lba(disc, lba, min(size, 2048))
        try:
            common.arc_parse(head if size <= 2048 else common.read_lba(disc, lba, size))
        except Exception:
            continue
        out.append((path, lba, size))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", help="이 문자열이 멤버 이름에 있는 것만 뽑는다 (예: DATA)")
    a = ap.parse_args()
    common.verify_source(a.disc)
    outdir = os.path.join(common.OUT_DIR, a.disc, "arc")
    index = {}
    nfile = nmem = nbyte = 0
    for path, lba, size in archives(a.disc):
        data = common.read_lba(a.disc, lba, size)
        unit, ents = common.arc_parse(data)
        nfile += 1
        index[path] = {"lba": lba, "size": size, "unit": unit, "members": []}
        for name, off, msz in ents:
            index[path]["members"].append([name, off, msz])
            if a.list:
                print(f"{path:<22} {name:<24} {msz:>9,}  {data[off : off + 12].hex(' ')}")
                continue
            if a.only and a.only not in name:
                continue
            short = name.replace("\\", "_").lstrip(".").lstrip("_")
            d = os.path.join(outdir, os.path.basename(path).split(".")[0])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, short), "wb") as f:
                f.write(data[off : off + msz])
            nmem += 1
            nbyte += msz
    if not a.list:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)
        print(f"{a.disc}: 아카이브 {nfile} · 멤버 {nmem:,} / {nbyte:,}B → {outdir}")
    else:
        print(f"# 아카이브 {nfile}")


if __name__ == "__main__":
    main()
