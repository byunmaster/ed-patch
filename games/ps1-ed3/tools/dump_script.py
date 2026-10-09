"""대본 덤프 — 아카이브 → `..\\DATA\\*.BIN`(ED3) · `..\\BIN\\*.BIN`(ED4) 안의 텍스트 런.

런은 `0xFFFF` 로 갈린다. 스크립트 코드와 텍스트가 **같은 16비트 스트림에 섞여 있어**
「텍스트인가」를 밀도로 가른다 — ⚠ 이건 판정이 아니라 **후보 좁히기**다(잘못 세면 조용히
빠지므로, 빠진 양을 늘 같이 찍는다).

산출: work/derived/<disc>/script/<아카이브>_<멤버>.json
  {"member": …, "runs": [{"off": 바이트오프셋, "codes": [...]}, …]}
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

TEXT_MEMBER = {"ed3": "\\DATA\\", "ed4": "\\BIN\\"}
KANA_LO, KANA_HI = 0x3F, 0x100  # 카나 대역 (밀도 판정용)
TEXT_HI = 0x800  # 이 위는 스크립트 인자로 본다


def runs_of(data):
    """[(바이트오프셋, [코드…])] — 0xFFFF 로 갈린 조각 전부(밀도 판정 전)."""
    n = len(data) // 2
    words = struct.unpack(f"<{n}H", data[: n * 2])
    out, cur, start = [], [], 0
    for i, w in enumerate(words):
        if w == textenc.TERM:
            if cur:
                out.append((start * 2, cur))
            cur, start = [], i + 1
        else:
            if not cur:
                start = i
            cur.append(w)
    if cur:
        out.append((start * 2, cur))
    return out


def is_text(codes, min_len=4, min_kana=0.35):
    if len(codes) < min_len:
        return False
    kana = sum(1 for w in codes if KANA_LO <= w < KANA_HI)
    return kana / len(codes) >= min_kana


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--min-kana", type=float, default=0.35)
    a = ap.parse_args()
    common.verify_source(a.disc)
    outdir = os.path.join(common.OUT_DIR, a.disc, "script")
    os.makedirs(outdir, exist_ok=True)
    key = TEXT_MEMBER[a.disc]
    nrun = nsym = nmem = 0
    drop_run = drop_sym = 0
    for path, (lba, size) in sorted(common.iso_files(a.disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(a.disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        tag = os.path.basename(path).split(".")[0]
        for name, off, msz in ents:
            if key not in name:
                continue
            member = name.split("\\")[-1]
            body = data[off : off + msz]
            keep = []
            for roff, codes in runs_of(body):
                if is_text(codes, min_kana=a.min_kana):
                    keep.append({"off": roff, "codes": codes})
                    nrun += 1
                    nsym += len(codes)
                else:
                    drop_run += 1
                    drop_sym += len(codes)
            if not keep:
                continue
            nmem += 1
            doc = {"archive": path, "member": member, "arc_off": off, "size": msz, "runs": keep}
            with open(os.path.join(outdir, f"{tag}_{member}.json"), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
    print(
        f"{a.disc}: 멤버 {nmem:,} · 텍스트 런 {nrun:,} / 심볼 {nsym:,}"
        f"   (밀도로 뺀 것: 런 {drop_run:,} / 심볼 {drop_sym:,})"
    )
    print(f"→ {outdir}")


if __name__ == "__main__":
    main()
