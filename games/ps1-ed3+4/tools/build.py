"""빌드 — 정본 셋을 이미지 하나로. **이게 유일한 굽는 자리다.**

    폰트(hangul_map)  +  대사(script/)  +  낱말(glossary_)  →  work/build/<꼬리표>/*.bin

읽는 것은 **커밋되는 정본뿐**이다(제1 원칙: 같은 입력이면 같은 바이트). `work/` 를 지웠다
다시 만들어도 결과가 같다.

## 🔴 멤버는 안 커진다

아카이브도 멤버도 **여유가 0바이트**다(실측: ED3 452/452 · ED4 355/356 이 끝과 딱 맞고,
아카이브 파일 끝 여유도 최대 3B). 그래서 **멤버 총량이 예산**이다 — 멤버 안에서는 조각
길이가 자유지만(짧은 줄에서 빌려 긴 줄에), 총량을 넘으면 아카이브를 다시 싸야 하고
그건 ISO 배치까지 건드린다.

⚠ 다행히 넘칠 일이 드물다 — **한국어가 일본어보다 짧다.** 같은 작품의 새턴 번역에서
   짝 17,200개를 재니 글자 수 비가 **중앙 0.82 · 90% 0.93** 이었다. 그래도 예산은 매번 센다.

## 실패하면 산출물을 무효화한다

낡은 이미지를 정상으로 오해하고 조사하면 엉뚱한 결론이 나온다(이 레포의 단골 사고).
`*.failed` 로 리네임한다.
"""

import argparse
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import exetext
import font
import glossary
import hangul_map
import script as script_canon
import scriptmap
import textenc
import typeset
import uitext


def bake_font(exe, disc, chars, table):
    """쓰는 글자만 굽는다 — 안 쓰는 자리는 원본 그대로 둔다(무변경 구간을 넓게 지킨다).

    ⚠ **배정은 인자로 받는다.** 안에서 정본을 다시 읽으면 시험 빌드(`--test`)가 정본 자리에
      구워져 화면이 안 나온다 — 실제로 그렇게 한 번 헛돌았다.
    """
    baked = 0
    for ch in sorted(chars):
        if ch not in table:
            continue
        font.write_glyph(exe, table[ch], font.hangul_glyph(ch), disc)
        baked += 1
    return baked


def reinsert_script(disc, canon, table, report):
    """{아카이브 경로: 새 바이트열} — 대사 재삽입. 멤버 크기는 그대로."""
    out = {}
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = bytearray(common.read_lba(disc, lba, size))
        try:
            _, ents = common.arc_parse(bytes(data))
        except common.ArchiveError:
            continue
        touched = False
        for nm, off, sz in ents:
            lines = canon.get((path, nm))
            if not lines:
                continue
            mem = bytes(data[off : off + sz])
            info = scriptmap.parse(mem)
            segs = [list(c) for _, c in info["segments"]]
            for i, row in sorted(lines.items()):
                jp = textenc.decode(info["segments"][i][1], disc)
                kr = typeset.wrap(row["kr"], disc, jp=jp)
                try:
                    segs[i] = hangul_map.encode(kr, disc, table)
                except KeyError:
                    # ⬜ 아직 자리를 못 받은 글자가 있다 — **원문 그대로 두고 센다.**
                    #    조용히 빼면 화면에서 그 줄만 사라진다(이 레포의 단골 사고).
                    report["skipped"] += 1
                    continue
            newmem, _ = scriptmap.rebuild(mem, segs)
            if len(newmem) > sz:
                raise SystemExit(
                    f"🔴 {path}!{nm}: 멤버가 {len(newmem) - sz:+d}B 커졌다 — 예산 {sz}B\n"
                    f"   문안을 줄이거나 아카이브 재배치가 필요하다(지금은 안 한다)."
                )
            data[off : off + sz] = newmem + b"\x00" * (sz - len(newmem))
            report["members"] += 1
            report["slack"] += sz - len(newmem)
            touched = True
        if touched:
            out[path] = bytes(data)
    return out


def reinsert_names(exe, disc, table, report):
    """실행파일 낱말 표에 고유명사 정본을 넣는다. 표가 없는 구역은 **길이 고정**이라 건너뛴다."""
    cm = textenc.charmap(disc)
    words = dict(glossary.flat(disc))
    tables = exetext.scan_tables(bytes(exe), cm)
    seen = set()
    for t in tables:
        tbl, base, n = t["table"], t["base"], t["n"]
        ents = struct.unpack_from(f"<{n}H", bytes(exe), tbl)
        cur, changed = [], 0
        for x in ents:
            codes, _ = exetext.raw_string(bytes(exe), base + x)
            codes = codes or []
            jp = textenc.decode(codes, disc)
            kr = words.get(jp)
            if kr:
                seen.add(jp)
            if kr and kr != jp:
                try:
                    cur.append(hangul_map.encode(kr, disc, table))
                    changed += 1
                    continue
                except KeyError:
                    report["skipped_names"] += 1
            cur.append(codes)
        if not changed:
            continue
        # 🔴 예산을 넘으면 **긴 것부터 되돌린다** — 표 하나를 통째로 버리면 이름 133개가
        #    같이 날아간다. 되돌린 자리는 원문 그대로 남고 개수를 찍는다.
        orig = []
        for x in ents:
            codes, _ = exetext.raw_string(bytes(exe), base + x)
            orig.append(codes or [])
        over = sorted(
            (i for i in range(n) if len(cur[i]) > len(orig[i])),
            key=lambda i: len(orig[i]) - len(cur[i]),
        )
        while True:
            try:
                new, _ = exetext.rebuild(bytes(exe), tbl, base, n, cur)
                break
            except exetext.ExeTextError:
                if not over:
                    new = None
                    break
                i = over.pop(0)
                cur[i] = orig[i]
                changed -= 1
                report["over_budget"] += 1
        if new is None:
            report["over_budget"] += changed
            continue
        exe[:] = bytearray(new)
        report["names"] += changed
    # 🔴 **표가 없는 구역은 아직 못 넣는다** — 화면에 일본어가 남는다는 뜻이라 세어서 알린다.
    #    (그 구역은 길이 고정이라, 우리 표기가 원문과 글자 수가 같을 때만 넣을 수 있다.)
    report["names_left"] = sorted(set(words) - seen)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--test",
        action="store_true",
        help="🔴 시험 빌드 — 폰트 자리를 전부 빌린다(안 옮긴 문안이 깨진다). 배포물이 아니다",
    )
    a = ap.parse_args()
    common.verify_source(a.disc)

    canon = script_canon.load(a.disc)
    if a.test:
        # 🔴 시험 빌드 — 「지금 보려는 것만 제대로 나오면 된다」. 안 옮긴 문안은 깨진다.
        #    자리가 닭·달걀이라(대사를 옮겨야 한자가 물러난다) 이게 없으면 초반에
        #    **아무것도 화면에서 확인할 수 없다.**
        need = list(hangul_map.EXTRA) + hangul_map.needed_chars(a.disc)
        table, short = hangul_map.assign(a.disc, hangul_map.test_slots(a.disc), chars=need)
        if short:
            print(f"  ⬜ 시험 빌드에서도 자리가 모자라다 {len(short)}자")
    elif not os.path.exists(hangul_map.map_path(a.disc)):
        raise SystemExit(
            f"⏭ {a.disc}: 글리프 자리 정본이 없다 — 쓸 수 있는 자리가 모자라 아직 못 박았다.\n"
            f"   `--test` 로 시험 빌드는 지금도 구울 수 있다(배포물은 아니다)."
        )
    else:
        table = hangul_map.load(a.disc)
    report = {
        "members": 0,
        "slack": 0,
        "names": 0,
        "skipped": 0,
        "skipped_names": 0,
        "over_budget": 0,
    }

    # 굽을 글자 — 대사 + 낱말에 실제로 쓰인 것만
    chars = set()
    for lines in canon.values():
        for row in lines.values():
            chars.update(row["kr"])
    for kr in glossary.flat(a.disc).values():
        chars.update(kr)
    for row in uitext.load(a.disc).values():
        chars.update(row["kr"])
    chars = {c for c in chars if c in table}

    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    baked = bake_font(exe, a.disc, chars, table)
    ui_put, ui_skip = uitext.apply(exe, a.disc, lambda kr: hangul_map.encode(kr, a.disc, table))
    report["skipped"] += ui_skip
    reinsert_names(exe, a.disc, table, report)
    arcs = reinsert_script(a.disc, canon, table, report)

    lines = sum(len(v) for v in canon.values())
    skipped = report["skipped"] + report["skipped_names"]
    left = report.get("names_left", [])
    print(
        f"{a.disc}: 대사 {lines:,}줄 / 멤버 {report['members']} (남는 자리 {report['slack']:,}B) · "
        f"낱말 {report['names']}/{report['names'] + len(left)} · UI {ui_put} · 글리프 {baked}"
    )
    if a.test:
        print("  🔴 **시험 빌드다** — 안 옮긴 문안은 엉뚱한 글자로 나온다. 배포물이 아니다.")
    if left:
        print(f"  ⬜ 아직 못 넣는 낱말 {len(left)} (표가 없는 구역 — 길이 고정)")
        print("     " + " · ".join(left[:10]))
    if report["over_budget"]:
        print(
            f"  ⬜ 칸 예산을 넘어 되돌린 낱말 {report['over_budget']} (원문 그대로 남는다)\n"
            f"     ⚠ 표기를 줄이거나, 같은 칸의 다른 이름을 줄여 자리를 만든다."
        )
    if skipped:
        print(
            f"  ⬜ 글리프 자리가 없어 건너뛴 것 — 대사 {report['skipped']} · 낱말 "
            f"{report['skipped_names']} (원문 그대로 남는다)\n"
            f"     ⚠ 대사를 더 옮기면 한자가 물러나 자리가 는다 → `hangul_map.py --freeze`"
        )
    if a.dry_run:
        print("(dry-run)")
        return 0

    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = common.build_bin(a.disc)
    if a.test:  # 이름으로 갈라 둔다 — 시험물을 정상으로 오해하는 사고가 이 레포의 단골이다
        out = out.replace(".bin", " (TEST).bin")
    tmp = out + ".part"
    shutil.copyfile(common.orig_bin(a.disc), tmp)
    try:
        with open(tmp, "r+b") as f:
            n = common.write_user_data(f, a.disc, exe_lba, bytes(exe), label="실행파일")
            for path, data in sorted(arcs.items()):
                lba, size = fs[path]
                n += common.write_user_data(f, a.disc, lba, data, label=path)
    except Exception:
        os.replace(tmp, out + ".failed")  # 🔴 실패한 빌드는 산출물을 무효화한다
        raise
    os.replace(tmp, out)
    cue = common.build_cue(a.disc)
    if a.test:
        cue = cue.replace(".cue", " (TEST).cue")
    common.write_cue(cue, os.path.basename(out))
    print(f"바뀐 섹터 {n:,}\n→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
