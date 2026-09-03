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


def bake_font(exe, disc, chars):
    """쓰는 글자만 굽는다 — 안 쓰는 자리는 원본 그대로 둔다(무변경 구간을 넓게 지킨다)."""
    table = hangul_map.load(disc)
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
                segs[i] = hangul_map.encode(kr, disc, table)
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
                except KeyError as e:
                    raise SystemExit(f"🔴 낱말 「{jp}」→「{kr}」: {e}") from None
            cur.append(codes)
        if not changed:
            continue
        try:
            new, _ = exetext.rebuild(bytes(exe), tbl, base, n, cur)
        except exetext.ExeTextError as e:
            raise SystemExit(f"🔴 낱말 표 0x{tbl:06X}: {e}") from None
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
    a = ap.parse_args()
    common.verify_source(a.disc)

    canon = script_canon.load(a.disc)
    if not os.path.exists(hangul_map.map_path(a.disc)):
        raise SystemExit(
            f"⏭ {a.disc}: 글리프 자리 정본이 없다 — 쓸 수 있는 자리가 모자라 아직 못 박았다.\n"
            f"   폰트 배열을 넓히는 게 선행 과제다(docs/status.md)."
        )
    table = hangul_map.load(a.disc)
    report = {"members": 0, "slack": 0, "names": 0}

    # 굽을 글자 — 대사 + 낱말에 실제로 쓰인 것만
    chars = set()
    for lines in canon.values():
        for row in lines.values():
            chars.update(row["kr"])
    for kr in glossary.flat(a.disc).values():
        chars.update(kr)
    chars = {c for c in chars if c in table}

    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    baked = bake_font(exe, a.disc, chars)
    reinsert_names(exe, a.disc, table, report)
    arcs = reinsert_script(a.disc, canon, table, report)

    lines = sum(len(v) for v in canon.values())
    left = report.get("names_left", [])
    print(
        f"{a.disc}: 대사 {lines:,}줄 / 멤버 {report['members']} (남는 자리 {report['slack']:,}B) · "
        f"낱말 {report['names']}/{report['names'] + len(left)} · 글리프 {baked}"
    )
    if left:
        print(f"  ⬜ 아직 못 넣는 낱말 {len(left)} (표가 없는 구역 — 길이 고정)")
        print("     " + " · ".join(left[:10]))
    if a.dry_run:
        print("(dry-run)")
        return 0

    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = common.build_bin(a.disc)
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
    common.write_cue(common.build_cue(a.disc), os.path.basename(out))
    print(f"바뀐 섹터 {n:,}\n→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
