"""탐침 글리프 — **비트가 화면의 어느 픽셀이 되는지**를 추론 말고 실측으로 읽는다.

빈 코드 몇 개에 「첫 비트 하나」·「첫 12비트」·「12비트마다 하나」 같은 패턴을 굽고,
대사 한 줄을 그 코드로 바꿔 인게임 VRAM 을 뜬다. 나오는 그림이 곧 매핑이다.

⚠ 원본 글리프를 읽어 맞추려던 시도가 11% 에서 안 좁혀졌다(한자는 두꺼워 티가 안 나고
   한글은 획이 얇아 무너진다). 「원본을 해석」하지 말고 **우리가 쓴 비트가 어디로 가나**를 본다.
"""

import argparse
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import scriptmap

ARCHIVE = "/SCE0/SC000.DAT"
MEMBER = "..\\DATA\\FT0000.BIN"
RUN_OFF = 4024  # 첫 대사 (20코드)

# (이름, 켤 비트 목록) — 18바이트(=144비트) 안의 비트 번호
PROBES = [
    ("bit0", [0]),
    ("bit0-11", list(range(12))),
    ("행머리", [i * 12 for i in range(12)]),
    ("bit0-10", list(range(11))),
    ("bit12", [12]),
    ("bit11", [11]),
]


def probe_bytes(idxs):
    a = np.zeros(144, dtype=np.uint8)
    for i in idxs:
        a[i] = 1
    return np.packbits(a).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3", choices=("ed3",))
    a = ap.parse_args()
    common.verify_source(a.disc)
    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    sc_lba, sc_size = fs[ARCHIVE]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    sc = bytearray(common.read_lba(a.disc, sc_lba, sc_size))
    _, ents = common.arc_parse(bytes(sc))
    mbase, msize = {n: (o, s_) for n, o, s_ in ents}[MEMBER]

    # 대본이 안 쓰는 코드 고르기
    import glob
    import json

    used = set()
    for p in glob.glob(os.path.join(common.OUT_DIR, a.disc, "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            for r in json.load(f)["runs"]:
                used.update(r["codes"])
    slots = [c for c in range(0x100, 0x900) if c not in used][: len(PROBES)]

    off = font.font_off(a.disc)
    for (name, idxs), code in zip(PROBES, slots, strict=True):
        exe[off + code * 18 : off + code * 18 + 18] = probe_bytes(idxs)
        print(f"  0x{code:03X} ← {name}")

    mem = bytes(sc[mbase : mbase + msize])
    info = scriptmap.parse(mem)
    seg = {s: i for i, (s, _) in enumerate(info["segments"])}
    segs = [list(c) for _, c in info["segments"]]
    segs[seg[RUN_OFF]] = slots  # 첫 대사를 탐침 글리프로
    newmem, _ = scriptmap.rebuild(mem, segs)
    sc[mbase : mbase + msize] = newmem + b"\x00" * (msize - len(newmem))

    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = os.path.join(common.BUILD_DIR, "probe.bin")
    tmp = out + ".part"
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    with open(tmp, "r+b") as f:
        common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="탐침 글리프")
        common.write_user_data(f, a.disc, sc_lba, bytes(sc), label="탐침 문안")
    os.replace(tmp, out)
    common.write_cue(os.path.join(common.BUILD_DIR, "probe.cue"), "probe.bin")
    print(f"→ {out}")
    print("  대사 첫 줄이 탐침 글리프 " + " ".join(n for n, _ in PROBES) + " 로 바뀐다")


if __name__ == "__main__":
    main()
