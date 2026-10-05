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
import engine_patch
import exetext
import font
import glossary
import graphics
import hangul_map
import patch_title_font
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
        font.write_glyph(exe, table[ch], font.glyph_bits(ch), disc)
        baked += 1
    # 마침표·쉼표는 **원본 자리(1=、 · 2=。)를 한국식 모양으로 다시 굽는다** — 자리를 안 쓴다.
    for ch, code in hangul_map.PUNCT.items():
        font.write_glyph(exe, code, font.hangul_glyph(ch), disc)
    return baked


def check_no_text_loss(where, newmem, lines, disc, table, report):
    """🔴 불변식 — **정본 글자 = 구운 글자**(공백·개행 빼고). 조판·인코딩·풀 재포장 어디서
    빠져도 여기서 멈춘다. 「넘치면 멈춤」(`typeset.wrap`)은 한 경로만 막는다 — 09-27 꼬리 잘림은
    검사기·지문·테스트가 다 초록인 채로 ED3 37줄 · ED4 59줄을 버렸다.
    건너뛴 조각(글리프 자리 없음 → 원문 그대로)은 이미 세어 알리므로 빼고 본다."""
    space = table.get(" ")
    got = scriptmap.parse(newmem)["segments"]
    for i, row in lines.items():
        want_text = "".join(row["kr"].split())
        try:
            want = hangul_map.encode(want_text, disc, table)
        except KeyError:
            continue  # 원문 그대로 남는 조각 — report["skipped"] 가 센다
        have = [c for c in got[i][1] if c != space]
        if have != want:
            raise SystemExit(
                f"🔴 {where} #{i}: 구운 글이 정본과 다르다(공백 빼고 {len(have)} vs {len(want)}자)\n"
                f"   정본: {row['kr']!r}"
            )
        report["loss_checked"] = report.get("loss_checked", 0) + 1


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
            jps = [(i, textenc.decode(c, disc)) for i, (_, c) in enumerate(info["segments"])]
            # 🔴 검사기(`script.py --check`)와 **같은 자**로 조판한다 — `floor` 를 빼먹어 넘친
            #    꼬리가 조용히 잘렸다(ED3 37줄 · ED4 59줄, 09-27).
            floors = script_canon.member_floors(jps)
            for i, row in sorted(lines.items()):
                jp = jps[i][1]
                try:
                    kr = typeset.wrap(row["kr"], disc, jp=jp, floor=floors.get(i, 0))
                except typeset.TypesetError as e:
                    raise SystemExit(
                        f"🔴 {path}!{nm} #{i}: 조판 예산 초과 — {e}\n"
                        f"   `script.py --check` 가 통과했다면 검사기와 빌드의 자가 다르다."
                    ) from e
                try:
                    segs[i] = hangul_map.encode(kr, disc, table)
                except KeyError:
                    # ⬜ 아직 자리를 못 받은 글자가 있다 — **원문 그대로 두고 센다.**
                    #    조용히 빼면 화면에서 그 줄만 사라진다(이 레포의 단골 사고).
                    report["skipped"] += 1
                    continue
            newmem, _ = scriptmap.rebuild(mem, segs)
            check_no_text_loss(f"{path}!{nm}", newmem, lines, disc, table, report)
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


def fit_chunks(exe, t, ents, cur, krs, orig, disc, table, report):
    """칸 예산을 넘는 칸에서 **띄어쓰기부터** 빼고, 그래도 넘치면 **그 칸 안에서만** 되돌린다.

    🔴 실측(2026-09-27): 아이템 표의 한 칸이 12B, 다른 칸이 18B 넘쳐 되돌리기가 **47개를
       일본어로** 남겼다(「の」 한 글자가 「의 」 두 글자가 된다). 칸마다 띄어쓰기만 빼면 전부
       들어간다 — 화면에 일본어가 남는 것보다 띄어쓰기 하나 빠지는 편이 훨씬 낫다.
       넘친 **그 칸 안에서만**, 긴 이름부터 공백을 하나씩 뺀다(결정적). 다른 칸은 안 건드린다.
    🔴 되돌리기도 칸 단위다 — 예전엔 표 전체에서 「가장 많이 는 것」부터 되돌려, 공백이 없는
       칸 하나(1코드 초과)를 맞추려고 **다른 칸의 멀쩡한 이름 39개**를 일본어로 돌려놨다.
    반환: 되돌린 수.
    """
    reverted = 0
    tbl, base, n = t["table"], t["base"], t["n"]
    for lo, hi, starts in exetext.chunks(exe, tbl, base, n):
        idx = {s: [i for i, x in enumerate(ents) if base + x == s] for s in starts}
        need = sum((len(cur[ids[0]]) + 1) * 2 for ids in idx.values())
        while need > hi - lo:
            cand = [ids for ids in idx.values() if krs[ids[0]] and " " in krs[ids[0]]]
            if not cand:
                break
            ids = max(cand, key=lambda ids: (len(cur[ids[0]]), -ids[0]))
            kr = krs[ids[0]]
            k = kr.rindex(" ")
            kr = kr[:k] + kr[k + 1 :]
            for i in ids:
                krs[i], cur[i] = kr, hangul_map.encode(kr, disc, table)
            need -= 2
            report["squeezed"] = report.get("squeezed", 0) + 1
        while need > hi - lo:
            grown = [ids for ids in idx.values() if len(cur[ids[0]]) > len(orig[ids[0]])]
            if not grown:
                break
            ids = max(grown, key=lambda ids: (len(cur[ids[0]]) - len(orig[ids[0]]), -ids[0]))
            need -= (len(cur[ids[0]]) - len(orig[ids[0]])) * 2
            for i in ids:
                cur[i], krs[i] = orig[i], None
            reverted += len(ids)
    return reverted


def reinsert_names(exe, disc, table, report):
    """실행파일 낱말 표에 고유명사 정본을 넣는다. 표가 없는 구역은 **길이 고정**이라 건너뛴다."""
    cm = textenc.charmap(disc)
    words = dict(glossary.flat(disc))
    tables = exetext.scan_tables(bytes(exe), cm) + exetext.detached_tables(bytes(exe), disc)
    seen = set()
    # 고정폭 칸(인물 이름) — 표가 없어 자리째 바꾼다. 넘치면 원문 그대로 두고 센다.
    for off, n_words, codes in exetext.fixed_slots(bytes(exe), disc):
        jp = textenc.decode(codes, disc)
        kr = words.get(jp)
        if not kr:
            continue
        seen.add(jp)
        if kr == jp:
            continue
        try:
            exetext.write_fixed_slot(exe, off, n_words, hangul_map.encode(kr, disc, table))
            report["names"] += 1
        except KeyError:
            report["skipped_names"] += 1
        except exetext.ExeTextError:
            report["over_budget"] += 1
    for t in tables:
        tbl, base, n = t["table"], t["base"], t["n"]
        ents = struct.unpack_from(f"<{n}H", bytes(exe), tbl)
        cur, krs, changed = [], [], 0
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
                    krs.append(kr)
                    changed += 1
                    continue
                except KeyError:
                    report["skipped_names"] += 1
            cur.append(codes)
            krs.append(None)
        if not changed:
            continue
        # 🔴 예산을 넘으면 **그 칸 안에서** 띄어쓰기 → 긴 것 순으로 되돌린다 — 표 하나를 통째로
        #    버리면 이름 133개가 같이 날아간다. 되돌린 자리는 원문 그대로 남고 개수를 찍는다.
        orig = []
        for x in ents:
            codes, _ = exetext.raw_string(bytes(exe), base + x)
            orig.append(codes or [])
        back = fit_chunks(bytes(exe), t, ents, cur, krs, orig, disc, table, report)
        changed -= back
        report["over_budget"] += back
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


def sweep(d, keep):
    """🔴 **칸에는 이미지 하나만 남긴다**(유저 확정 2026-09-04).

    빌드가 끝날 때마다 이 칸의 다른 이미지를 지운다 — 정상·시험(`(TEST)`)·실패(`*.failed`)·
    다른 디스크 것까지 전부. 남겨 두면 **낡은 것을 정상으로 오해하고 조사하는** 이 레포의
    단골 사고가 난다(실측 2026-09-04: 한 칸에 넷 1.9GB 가 쌓여 있었다).
    ⚠ 지우는 건 **성공한 뒤**다. 실패하면 옛 이미지가 남아야 손에 아무것도 없는 상태를 면한다.
    """
    keep = {os.path.abspath(p) for p in keep}
    gone = []
    for name in os.listdir(d):
        f = os.path.join(d, name)
        if os.path.abspath(f) in keep or not os.path.isfile(f):
            continue
        if not name.endswith((".bin", ".cue", ".iso", ".img", ".failed", ".part")):
            continue
        os.remove(f)
        gone.append(name)
    return gone


MOVIE_ARCHIVES = {"M01": "/M01.DAT", "M02": "/M02.DAT"}  # 오프닝+타이틀 · 엔딩+크레딧


def movie_swap(disc, out):
    """🔬 **검증 전용** — 동영상 아카이브를 통째로 갈아 **부팅 직후 엔딩을 본다**.

        ED_BUILD_TAG=ps1-ed3-ending-qa ED_MOVIE_SWAP=M01=M02 python3 tools/build.py --disc ed3 --test

    ps1-ed1+2 는 동영상 EXE 넷이 물리 크기까지 같아 자리를 그대로 맞바꿨다. ED3 는
    `M01.DAT`(오프닝+타이틀, 3,682,304B)·`M02.DAT`(엔딩+크레딧, 2,365,440B) 크기가 달라
    **같은 조건은 아니다** — 그런데 `write_user_data` 가 원본 길이만큼만 쓰고 자리 전체를
    안 지우므로, **작은 쪽을 큰 쪽 자리에 얹는 건 된다**(M02 가 M01 보다 작아 방향이 맞다,
    반대는 안 된다). emucap 실측(2026-09-15, `M01=M02`): 부팅 후 첫 내레이션부터 **엔딩
    내레이션 → 크레딧 롤**까지 재생됐다 — 화면 문안이 「2人は白き魔女の残した希望の道を
    通ってきた」등 엔딩 특유의 과거형 회고체였다. ⚠ 타이틀 화면을 구성하는 단계(M01 전용
    `DATA5.BIN` 자리)에서 한 프레임 깨진 그림이 지나갔다 — M02 에 그 멤버가 없어서고,
    **진행을 막지는 않는다**(그 뒤로도 계속 돈다). 반대 방향(`M02=M01`)은 큰 걸 작은 자리에
    얹는 셈이라 **안 해 봤다** — 자리를 넘는지부터 다시 재야 한다.

    🔴 **`src` 는 `FINAL`(이미 구운 이미지)에서 읽는다** — originals 가 아니다. 우리가 옮긴
    한국어 엔딩 문안(그림 속 글자 포함)이 이미 빌드에 구워져 있으므로, 그걸 그대로 봐야
    검증이 된다. originals 에서 읽으면 미번역 일본어를 보게 된다(첫 실험에서 실수로 그랬다).
    🔴 배포 빌드에 절대 켜지 않는다. 환경변수라 커밋물에 안 남고, 꼬리표를 갈라 짓는다.
    """
    spec = os.environ.get("ED_MOVIE_SWAP", "")
    pairs = [kv.split("=", 1) for kv in spec.split(",") if "=" in kv]
    if not pairs:
        return
    fs = common.iso_files(disc)
    for dst, src in pairs:
        assert dst in MOVIE_ARCHIVES and src in MOVIE_ARCHIVES, (
            f"모르는 동영상 아카이브: {dst}={src}"
        )
        dst_lba, _dst_size = fs[MOVIE_ARCHIVES[dst]]
        src_lba, src_size = fs[MOVIE_ARCHIVES[src]]
        data = common.read_lba(disc, src_lba, src_size, path=out)  # 이미 구운 FINAL 에서
        with open(out, "r+b") as f:
            n = common.write_user_data(f, disc, dst_lba, bytes(data), label=f"🔬 {dst} ← {src}")
        print(f"  🔬 동영상 구획 교체: {dst}(LBA {dst_lba}) ← {src} — 섹터 {n}")


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

    gfx_files, gfx_arcs = graphics.apply(a.disc)
    fs = common.iso_files(a.disc)
    exe_lba, exe_size = fs[font.FONTS[a.disc]["exe"]]
    exe = bytearray(common.read_lba(a.disc, exe_lba, exe_size))
    baked = bake_font(exe, a.disc, chars, table)
    engine = engine_patch.apply(exe, a.disc, table)  # 공백 8px — 그 디스크에 패치가 있으면
    exe_orig = bytes(exe)
    enc = lambda kr: hangul_map.encode(kr, a.disc, table)
    ui_put, ui_skip = uitext.apply(exe, a.disc, enc)
    report["skipped"] += ui_skip
    reinsert_names(exe, a.disc, table, report)
    # 🔴 불변식 — 구운 UI 글이 정본과 같은가(공백 빼고). 낱말 재포장이 표를 같이 쓰므로 그 뒤에 본다.
    lost = uitext.lost_text(exe_orig, bytes(exe), a.disc, enc)
    if lost:
        raise SystemExit("🔴 UI 글 소실:\n  " + "\n  ".join(lost[:10]))
    arcs = reinsert_script(a.disc, canon, table, report)
    for path, data in gfx_arcs.items():  # 그림이 든 파일도 같이 쓴다
        arcs.setdefault(path, data)
    title_font_n, title_font_arcs = patch_title_font.apply(a.disc, base_arcs=arcs)
    arcs.update(title_font_arcs)  # 그림 위에 문자열을 얹는다(같은 M01.DAT 일 수 있다)

    lines = sum(len(v) for v in canon.values())
    skipped = report["skipped"] + report["skipped_names"]
    left = report.get("names_left", [])
    print(
        f"{a.disc}: 대사 {lines:,}줄 / 멤버 {report['members']} (남는 자리 {report['slack']:,}B) · "
        f"낱말 {report['names']}/{report['names'] + len(left)} · UI {ui_put} · "
        f"그림 {gfx_files} · 글리프 {baked}"
    )
    print(f"  엔진: {engine or '⏭ 패치 없음 (공백도 12px)'}")
    if title_font_n:
        print(f"  타이틀 폰트: SLPS_012.01 BIOS 리다이렉트 · M01.DAT 문자열 {title_font_n}")
    if a.test:
        print("  🔴 **시험 빌드다** — 안 옮긴 문안은 엉뚱한 글자로 나온다. 배포물이 아니다.")
    if left:
        print(f"  ⬜ 아직 못 넣는 낱말 {len(left)} (표가 없는 구역 — 길이 고정)")
        print("     " + " · ".join(left[:10]))
    if report.get("squeezed"):
        print(f"  ⬜ 칸 예산 때문에 뺀 띄어쓰기 {report['squeezed']} (이름은 들어갔다)")
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
                lba, _size = fs[path]
                n += common.write_user_data(f, a.disc, lba, data, label=path)
    except Exception:
        os.replace(tmp, out + ".failed")  # 🔴 실패한 빌드는 산출물을 무효화한다
        raise
    os.replace(tmp, out)
    cue = common.build_cue(a.disc)
    if a.test:
        cue = cue.replace(".cue", " (TEST).cue")
    common.write_cue(cue, os.path.basename(out))
    common.write_build_manifest(a.disc, "kr", out)
    movie_swap(a.disc, out)
    dropped = sweep(common.BUILD_DIR, {out, cue})
    print(f"바뀐 섹터 {n:,}\n→ {out}")
    if dropped:
        print(f"  🧹 낡은 산출물 {len(dropped)}개를 지웠다 — " + " · ".join(sorted(dropped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
