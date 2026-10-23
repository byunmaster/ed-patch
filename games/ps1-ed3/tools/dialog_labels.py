"""대사 하네스 색인(`index.tsv`)에 **씬·줄 열쇠**(`SC000_FT0000#26`)를 붙인다 — 캡처 한 장이 어느 번역 줄인지 찾게.

  python3 tools/dialog_labels.py --index <폴더>/index.tsv --cue <굽은 시험 롬 cue> > <폴더>/labels.tsv

하네스가 주입한 시퀀스의 `0F 90 <V>` 는 **굽은** 멤버의 풀 오프셋이다(`TEXT_BASE + (V & ~1)`) — 원판 V 와 다르니 굽은 이미지의 멤버에서 조각 번호를 찾는다.
열 = 맵 · 번호 · 줄열쇠(`;` 로 이은 조각들, 한 시퀀스가 여러 조각이면 `01 90` 줄) · 첫 조각 글.
"""

import argparse
import glob
import json
import os
import pathlib
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import scriptmap

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PTR = re.compile(rb"[\x0f\x01]\x90", re.DOTALL)


def member_index(disc):
    """{맵 이름: (아카이브 경로, 멤버 이름, 번역 json 파일)}"""
    out = {}
    for f in glob.glob(os.path.join(GAME, "script", disc, "*.json")):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        nm = d["member"]
        key = os.path.basename(nm.replace("\\", "/")).split(".")[0]
        out.setdefault(key, []).append((d["archive"], nm, os.path.basename(f)[:-5], d))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--cue", required=True)
    ap.add_argument("--disc", default="ed3")
    a = ap.parse_args()
    idx = member_index(a.disc)
    cache = {}
    binp = os.path.splitext(a.cue)[0] + ".bin"
    tree = common.iso_tree(binp)[0]

    def segs_of(arch, nm):
        k = (arch, nm)
        if k not in cache:
            lba, size = tree[arch]
            data = common.read_lba(a.disc, lba, size, path=binp)
            _, ents = common.arc_parse(data)
            off, sz = next((o, s) for n, o, s in ents if n == nm)
            info = scriptmap.parse(data[off : off + sz])
            cache[k] = {s: i for i, (s, _c) in enumerate(info["segments"])}, info["base"]
        return cache[k]

    print("맵\t번호\t줄열쇠\t첫조각")
    for ln in pathlib.Path(a.index).read_text(encoding="utf-8").splitlines()[1:]:
        c = ln.split("\t")
        name, k, seq, off = (
            c[0],
            c[1],
            bytes.fromhex(c[3]),
            int(c[2]) - (2 if c[3].startswith("12") else 0),
        )
        keys = []
        for arch, nm, stem, d in idx.get(name, []):
            starts, base = segs_of(arch, nm)
            keys = []
            for m in PTR.finditer(seq):
                # 포인터 피연산자는 0x90 다음 위치를 짝수로 올려 읽는다 — 짝수 기준이 멤버 안 오프셋인지 RAM 주소인지 몰라 둘 다 본다
                i = None
                for extra in ((off + m.end()) & 1, 1 - ((off + m.end()) & 1)):
                    at = m.end() + extra
                    v = struct.unpack("<H", seq[at : at + 2].ljust(2, b"\0"))[0]
                    i = starts.get(base + (v & ~1))
                    if i is not None:
                        break
                if i is None:
                    keys = []
                    break
                keys.append(f"{stem}#{i}")
            if keys:
                first = d["lines"].get(keys[0].split("#")[1], {}).get("kr", "")
                break
        print(
            f"{name}\t{k}\t{';'.join(keys) or '?'}\t{first.replace(chr(10), '/')[:40] if keys else ''}"
        )


if __name__ == "__main__":
    main()
