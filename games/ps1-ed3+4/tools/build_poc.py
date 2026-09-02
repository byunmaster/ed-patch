"""한글 PoC 빌드 — 폰트 슬롯 몇 개를 한글로 굽고 대사 한 줄을 그 코드로 바꾼다.

⚠ **이건 파이프라인이 아니라 증명이다.** 물어보는 것은 하나 —
   「우리가 그린 글리프가 우리가 쓴 코드로 화면에 나오는가」(도달성 ①②③, 체크리스트 10-B).
   본 빌드는 재삽입 구조(포인터·창 예산)가 서고 나서 따로 만든다.

⚠ 덮는 슬롯은 **대본이 한 번도 안 쓰는 코드**로 고른다. 그래도 시스템 UI(메뉴·아이템)는
   이 덤프에 안 들어 있어 확인 못 한 위험이 남는다 — PoC 라서 감수하고, 본 빌드에서는
   `hangul_map.json` 같은 **커밋되는 정본**으로 자리를 박는다.
"""

import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import textenc

# 바꿀 자리 — 첫 마을 첫 대사 (20코드)
TARGET = {
    "iso": "/SCE0/SC000.DAT",
    "member": "..\\DATA\\FT0000.BIN",
    "run_off": 4024,
    "expect": "クリスチーナ。明日の準備はできているの？",
}
# 20 글리프 정확히. 。(0x02)·？(0x04)는 원래 코드를 그대로 쓴다.
KR_LINE = "크리스티나。내일 갈 준비는 다 됐니？"


def pick_slots(exe, need, used):
    """대본이 안 쓰고 글리프가 실재하는 코드 — 낮은 것부터."""
    out = []
    for c in range(0x100, 0x900):
        if c in used:
            continue
        if font.read_glyph(exe, c).sum() == 0:
            continue
        out.append(c)
        if len(out) >= need:
            break
    return out


def script_used_codes():
    import glob
    import json

    used = set()
    for p in glob.glob(os.path.join(common.OUT_DIR, "ed3", "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            for r in json.load(f)["runs"]:
                used.update(r["codes"])
    return used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3", choices=("ed3",))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    common.verify_source(a.disc)

    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.EXE_PATH]
    sc_lba, sc_size = fs[TARGET["iso"]]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    sc = bytearray(common.read_lba(a.disc, sc_lba, sc_size))

    # ── 대상 런이 그 자리에 그대로 있나 (쓰기 사전조건) ──────────────────
    _, ents = common.arc_parse(bytes(sc))
    member = dict((n, (o, s)) for n, o, s in ents)[TARGET["member"]]
    run_abs = member[0] + TARGET["run_off"]
    cur = struct.unpack("<20H", bytes(sc[run_abs : run_abs + 40]))
    got = textenc.decode(cur, a.disc)
    if got != TARGET["expect"]:
        raise SystemExit(f"대상 런이 다르다 — 지금 「{got}」 (기대 「{TARGET['expect']}」)")
    print(f"대상 확인 ✓ /SCE0/SC000.DAT + 0x{run_abs:X}: {got}")

    # ── 글리프 자리 배정 ────────────────────────────────────────────────
    used = script_used_codes()
    m = textenc.charmap(a.disc)
    rev = {v: k for k, v in m.items()}
    need = [ch for ch in dict.fromkeys(KR_LINE) if ch not in rev]  # 이미 코드가 있는 부호는 그대로
    slots = pick_slots(exe, len(need), used)
    if len(slots) < len(need):
        raise SystemExit("빈 글리프 슬롯이 모자란다")
    assign = dict(zip(need, slots, strict=True))
    print("배정:", " ".join(f"{ch}→0x{c:03X}" for ch, c in assign.items()))

    codes = [assign.get(ch) or rev[ch] for ch in KR_LINE]
    if len(codes) != 20:
        raise SystemExit(f"길이가 안 맞는다: {len(codes)} 코드 (자리는 20)")

    # ── 폰트 굽기 ───────────────────────────────────────────────────────
    for ch, code in assign.items():
        bits = font.hangul_glyph(ch) if ch.strip() else font.hangul_glyph(" ")
        font.write_glyph(exe, code, bits)
    print(f"글리프 {len(assign)}개 구움")

    # ── 문안 넣기 ───────────────────────────────────────────────────────
    sc[run_abs : run_abs + 40] = struct.pack("<20H", *codes)
    print("문안:", textenc.decode(codes, a.disc, unknown="?"))

    if a.dry_run:
        print("(dry-run — 이미지는 안 굽는다)")
        return

    # ── 이미지 ──────────────────────────────────────────────────────────
    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = common.build_bin(a.disc)
    tmp = out + ".part"
    print(f"원본 복사 → {out}")
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    with open(tmp, "r+b") as f:
        n1 = common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="ED3.EXE 폰트")
        n2 = common.write_user_data(f, a.disc, sc_lba, bytes(sc), label="SC000.DAT 문안")
    os.replace(tmp, out)
    common.write_cue(common.build_cue(a.disc), os.path.basename(out))
    print(f"바뀐 섹터: 폰트 {n1} · 문안 {n2}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
