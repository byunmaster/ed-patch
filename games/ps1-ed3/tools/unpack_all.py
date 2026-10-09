"""디스크의 압축 멤버를 전부 풀어 work/derived/<disc>/unpacked 로 내린다.

⚠ 산출물이지 소스가 아니다 — `rm -rf work/` 로 지워도 다시 만들어진다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import gmfz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    a = ap.parse_args()
    common.verify_source(a.disc)
    outdir = os.path.join(common.OUT_DIR, a.disc, "unpacked")
    os.makedirs(outdir, exist_ok=True)
    ok = shortn = 0
    seen = {}
    for path, (lba, size) in sorted(common.iso_files(a.disc).items()):
        if size < 64 or size > 8 << 20:
            continue
        data = common.read_lba(a.disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        tag = os.path.basename(path).split(".")[0]
        for name, o, s in ents:
            blk = data[o : o + s]
            if gmfz.parse_header(blk) is None:
                continue
            raw, short = gmfz.decompress(blk)
            key = raw[:64]
            if key in seen:  # 같은 자산이 여러 아카이브에 중복된다
                continue
            seen[key] = 1
            shortn += 1 if short else 0
            fn = f"{tag}_{name.split(chr(92))[-1]}"
            with open(os.path.join(outdir, fn), "wb") as f:
                f.write(raw)
            ok += 1
    print(f"{a.disc}: 푼 자산 {ok:,} (모자랐던 것 {shortn:,}) → {outdir}")


if __name__ == "__main__":
    main()
