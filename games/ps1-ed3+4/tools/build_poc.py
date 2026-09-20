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
import build  # sweep() 만 빌려 쓴다 — 「칸엔 이미지 하나만」 설계는 어느 스크립트가 굽든 지킨다
import common
import font
import hangul_map
import scriptmap
import textenc

ARCHIVE = "/SCE0/SC000.DAT"
MEMBER = "..\\DATA\\FT0000.BIN"

# ED4 는 **실행파일 안 문자열**로 잰다 — 타이틀 화면 메뉴라 부팅하면 바로 보인다.
# ⇒ 씬을 찾아 들어갈 필요가 없어 「폰트 저장 규약이 맞나」만 딱 떼어 물을 수 있다.
# ⚠ 실행파일 문자열은 **길이 고정**이다(표가 연속으로 붙어 있다) — 같은 코드 수로만 바꾼다.
EXE_PLAN = {
    "ed4": [
        (0x06DC72, "最初から始める", "처음부터 시작"),
        (0x06DC82, "続きから始める", "계속해서 시작"),
    ],
}

# (런 오프셋, 원문(사전조건), 우리 문안) — **총 코드 수는 원본과 같아야 한다**(아래 단언).
# 63·64 는 첫 대사창의 1·2행이다. 20+14 를 24+10 으로 옮겨 「경계를 움직여도 되나」를 잰다.
PLAN = [
    (4024, "クリスチーナ。明日の準備はできているの？", "크리스티나。내일 떠날 준비는 다 했니？"),
    (4066, "明日になって慌てないように\n", "내일 허둥대지 않도록\n"),
    (4096, "必要なものは今日中に用意しておきなさい。", "필요한 건 오늘 안에 챙겨 두렴。"),
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


def _rev(disc):
    m = textenc.charmap(disc)
    rev = {v: k for k, v in m.items()}
    for code, ch in textenc.CONTROL.items():
        rev.setdefault(ch, code)
    return rev


def _free_slots(exe, disc, n, used=()):
    """대본이 안 쓰고 그림도 없는 글리프 자리 n 개."""
    out = []
    for c in range(0x100, 0x900):
        if c in used or font.read_glyph(exe, c, disc).sum() == 0:
            continue
        out.append(c)
        if len(out) >= n:
            return out
    raise SystemExit("빈 글리프 자리가 모자라다")


def exe_poc(a, exe, exe_lba):
    """실행파일 문자열만 바꾸는 PoC — **길이 고정**(같은 코드 수).

    🔴 이 PoC 가 묻는 건 하나다: **ED4 의 폰트 저장 규약(`font.LAYOUT`)이 맞나.**
       ED3 과 달라서(열 짝 교환 X · 몸통 1~11행) 글리프 대조로 유도만 해 뒀다 —
       화면으로 확인하기 전에는 한글을 본 빌드에 굽지 않는다(체크리스트 10-B 도달성).
    """
    rev = _rev(a.disc)
    plan = EXE_PLAN[a.disc]
    for off, expect, kr in plan:
        n = len(expect)
        got = textenc.decode(struct.unpack_from(f"<{n}H", exe, off), a.disc)
        if got != expect:
            raise SystemExit(f"@0x{off:06X}: 원문이 다르다 — 「{got}」 (기대 「{expect}」)")
        if len(kr) != n:
            raise SystemExit(
                f"@0x{off:06X}: 길이가 다르다 {len(kr)} (원본 {n}) — 실행파일은 고정이다"
            )
        print(f"  확인 @0x{off:06X} ({n}코드) 「{got}」 → 「{kr}」")

    # 🔴 **자리는 정본에서 온다**(`hangul_map_<disc>.json`). 그때그때 「빈 자리 앞에서부터」로
    #    잡으면 소재를 하나 더 열 때마다 자리가 밀려 **이미 넣은 문안이 다른 글자로 읽힌다.**
    table = hangul_map.load(a.disc)
    need = dict.fromkeys(ch for _, _, kr in plan for ch in kr if ch in table)
    for ch in need:
        font.write_glyph(exe, table[ch], font.hangul_glyph(ch), a.disc)
    for off, _, kr in plan:
        codes = hangul_map.encode(kr, a.disc, table)
        struct.pack_into(f"<{len(codes)}H", exe, off, *codes)
    print("배정(정본):", " ".join(f"{ch}→0x{table[ch]:03X}" for ch in need))
    print(f"글리프 {len(need)}개 구움")

    if a.dry_run:
        print("(dry-run)")
        return
    os.makedirs(common.BUILD_DIR, exist_ok=True)
    # ⚠ build.py 와 같은 BUILD_DIR/파일명을 쓰면 **어느 스크립트가 만들었는지 안 남는다**
    #   (sfc-ed1 실측 — build()/build_kr() 가 같은 파일명에 써서 지문을 다른 함수끼리 비교하고도
    #   몰랐다). 접미로 사람이 보고, manifest 로 자동화가 본다(main docs/patcher-checklist.md 3-B).
    out = common.build_bin(a.disc).replace(".bin", " (POC).bin")
    tmp = out + ".part"
    print(f"원본 복사 → {out}")
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    with open(tmp, "r+b") as f:
        n1 = common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="폰트+문안")
    os.replace(tmp, out)
    cue = common.build_cue(a.disc).replace(".cue", " (POC).cue")
    common.write_cue(cue, os.path.basename(out))
    common.write_build_manifest(a.disc, "poc", out)
    build.sweep(common.BUILD_DIR, {out, cue})
    print(f"바뀐 섹터: {n1}\n→ {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3", choices=("ed3", "ed4"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    common.verify_source(a.disc)

    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    if a.disc in EXE_PLAN:
        return exe_poc(a, exe, exe_lba)
    sc_lba, sc_size = fs[ARCHIVE]
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
    out = common.build_bin(a.disc).replace(".bin", " (POC).bin")
    tmp = out + ".part"
    print(f"원본 복사 → {out}")
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    with open(tmp, "r+b") as f:
        n1 = common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="폰트")
        n2 = common.write_user_data(f, a.disc, sc_lba, bytes(sc), label="문안")
    os.replace(tmp, out)
    cue = common.build_cue(a.disc).replace(".cue", " (POC).cue")
    common.write_cue(cue, os.path.basename(out))
    common.write_build_manifest(a.disc, "poc", out)
    build.sweep(common.BUILD_DIR, {out, cue})
    print(f"바뀐 섹터: 폰트 {n1} · 문안 {n2}\n→ {out}")


if __name__ == "__main__":
    main()
