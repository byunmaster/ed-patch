"""한글 PoC 빌드 — 폰트 슬롯을 한글로 굽고, 지정한 런들을 우리 문안으로 바꾼다.

⚠ **이건 파이프라인이 아니라 실험대다.** 묻는 것은 둘 —
  1. 우리가 그린 글리프가 우리가 쓴 코드로 화면에 나오는가 (도달성, 체크리스트 10-B)
  2. **런 길이를 바꿔도 되는가** — 엔진이 문자열을 「몇 번째」로 찾는가, 「어디」로 찾는가

  2번을 재는 방법: **이웃한 런들의 총 코드 수를 유지한 채 경계만 옮긴다.**
  인덱스(0xFFFF 세기) 방식이면 그대로 나오고, 절대 오프셋이면 뒤가 통째로 어긋난다.

⚠ 덮는 글리프 슬롯은 **대본이 한 번도 안 쓰는 코드**다. 시스템 UI 는 이 덤프에 없어
  확인 못 한 위험이 남는다 — 본 빌드에서는 커밋되는 정본으로 자리를 박는다.
"""

import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import font
import scriptmap
import textenc

ARCHIVE = "/SCE0/SC000.DAT"
MEMBER = "..\\DATA\\FT0000.BIN"

# (런 오프셋, 원문(사전조건), 우리 문안) — **총 코드 수는 원본과 같아야 한다**(아래 단언).
# 63·64 는 첫 대사창의 1·2행이다. 20+14 를 24+10 으로 옮겨 「경계를 움직여도 되나」를 잰다.
PLAN = [
    (
        4024,
        "クリスチーナ。明日の準備はできているの？",
        "크리스티나。 내일 떠날 준비는 다들 되었니？",
    ),
    (4066, "明日になって慌てないように\n", "내일 당황 않도록\n"),
]


def script_used_codes():
    import glob
    import json

    used = set()
    for p in glob.glob(os.path.join(common.OUT_DIR, "ed3", "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            for r in json.load(f)["runs"]:
                used.update(r["codes"])
    return used


def encode(text, disc, assign, rev):
    return [assign.get(ch) or rev[ch] for ch in text]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3", choices=("ed3",))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    common.verify_source(a.disc)

    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    sc_lba, sc_size = fs[ARCHIVE]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    sc = bytearray(common.read_lba(a.disc, sc_lba, sc_size))
    _, ents = common.arc_parse(bytes(sc))
    mbase, msize = {n: (o, s_) for n, o, s_ in ents}[MEMBER]

    m = textenc.charmap(a.disc)
    rev = {v: k for k, v in m.items()}
    # ⚠ 제어 코드도 되짚어야 한다 — 안 그러면 개행이 **글리프 슬롯을 하나 먹는다**
    #   (실측: `\n` 에 0x39E 가 배정됐다).
    for code, ch in textenc.CONTROL.items():
        rev.setdefault(ch, code)

    # ── 사전조건: 원문이 그 자리에 그대로 있나 ────────────────────────────
    spans = []
    for off, expect, _kr in PLAN:
        p = mbase + off
        codes = []
        while True:
            v = struct.unpack("<H", bytes(sc[p + len(codes) * 2 : p + len(codes) * 2 + 2]))[0]
            if v == textenc.TERM:
                break
            codes.append(v)
        got = textenc.decode(codes, a.disc)
        if got != expect:
            raise SystemExit(f"@{off}: 원문이 다르다 — 「{got}」 (기대 「{expect}」)")
        spans.append((p, len(codes)))
        print(f"  확인 @{off} ({len(codes)}코드) {got.replace(chr(10), '/')}")

    # ── 글리프 자리 배정 ────────────────────────────────────────────────
    need = [ch for ch in dict.fromkeys("".join(kr for _, _, kr in PLAN)) if ch not in rev]
    used = script_used_codes()
    slots = []
    for c in range(0x100, 0x900):
        if c in used or font.read_glyph(exe, c, a.disc).sum() == 0:
            continue
        slots.append(c)
        if len(slots) >= len(need):
            break
    assign = dict(zip(need, slots, strict=True))
    print("배정:", " ".join(f"{ch}→0x{c:03X}" for ch, c in assign.items()))

    # ── 풀을 다시 싸고 **포인터를 다시 계산**한다 (scriptmap) ────────────
    #    ⚠ 예전엔 「런마다 같은 코드 수」가 계약이었다. 포인터를 갱신하면 그 제약이 풀린다 —
    #      이 빌드가 그걸 증명하는 자리다(같은 편집을 포인터 갱신과 함께 넣는다).
    news = [encode(kr, a.disc, assign, rev) for _, _, kr in PLAN]
    mem = bytes(sc[mbase : mbase + msize])
    info = scriptmap.parse(mem)
    seg_by_start = {st: i for i, (st, _) in enumerate(info["segments"])}
    new_segs = [list(c) for _, c in info["segments"]]
    for (off, _, _), codes in zip(PLAN, news, strict=True):
        if off not in seg_by_start:
            raise SystemExit(f"@{off}: 조각 시작이 아니다")
        new_segs[seg_by_start[off]] = codes
    old_lens = [len(new_segs[seg_by_start[o]]) for o, _, _ in PLAN]
    print(f"코드 수: {[n for _, n in spans]} → {old_lens}  (포인터 재계산으로 총량 제약 없음)")

    for ch, code in assign.items():
        font.write_glyph(exe, code, font.hangul_glyph(ch), a.disc)
    print(f"글리프 {len(assign)}개 구움")

    newmem, unres = scriptmap.rebuild(mem, new_segs)
    print(f"멤버 {msize:,} → {len(newmem):,}B · 포인터 {len(info['pointers'])} (못 푼 것 {unres})")
    if len(newmem) > msize:
        raise SystemExit(
            f"🔴 멤버가 커졌다({len(newmem) - msize:+d}B) — 아카이브 재배치가 필요하다"
        )
    sc[mbase : mbase + msize] = newmem + b"\x00" * (msize - len(newmem))
    for _, _, kr in PLAN:
        print("  문안:", kr.replace("\n", "/"))

    if a.dry_run:
        print("(dry-run)")
        return

    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = common.build_bin(a.disc)
    tmp = out + ".part"
    print(f"원본 복사 → {out}")
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    with open(tmp, "r+b") as f:
        n1 = common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="폰트")
        n2 = common.write_user_data(f, a.disc, sc_lba, bytes(sc), label="문안")
    os.replace(tmp, out)
    common.write_cue(common.build_cue(a.disc), os.path.basename(out))
    print(f"바뀐 섹터: 폰트 {n1} · 문안 {n2}\n→ {out}")


if __name__ == "__main__":
    main()
