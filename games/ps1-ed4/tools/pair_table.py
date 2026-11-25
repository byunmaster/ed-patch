"""롬에서 뽑은 번호별 대사집 짝 표 — 원판 이미지와 제품 이미지의 **실제 바이트**를 디코드해 번호마다 원문|한글을 짝짓는다(문안 검수용, 마스터 10-20 꼴).

  python3 tools/pair_table.py [--kr-bin <제품 이미지 bin>] --out <폴더>

산출 `<out>/pairs.tsv`(번호 · 원판 · 한글 · 표시) + `manifest.md`. ⚠ 원문 포함 — 저장소 밖(`.local/work/inbox/`)에만 낸다.
번호: `<아카이브>_<멤버>#n`(대사 쪽 n번째 — `dialog_render` 시트 번호와 같다) · `<아카이브>_<멤버>@i`(쪽에 안 든 조각 i번) · `UI@0x…`(실행파일 낱말·메뉴, 원판 오프셋).
표기: ↵ = 조각(줄) 바꿈 · ⏎ = 이 쪽 뒤에 같은 메시지의 다음 쪽이 이어진다(쪽 넘김) · `⟦n⟧` = 숫자 그리기 연산 · `{cXXX}` = 글자표에 없는 코드(변수·제어).
표시: 원판만(바이트가 원판 그대로 = 번역 안 됨) · 한글만(원판 빔) · 둘 다 빔 · 포인터 공유(한 조각이 여러 쪽에 나옴) · 자리 이동(UI 표가 옮겨짐). 비어 있으면 정상 짝.
일본어 글자가 없는 원문(전각 영문·숫자·부호뿐) 조각도 행에 넣는다 — `표시` 가 비어 있고 한글 열이 원판과 같거나 번역돼 있다.
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dialog_render
import hangul
import reinsert
import textenc
import typeset
import uitext

from shared.ps1 import gmf_arc

JPCH = re.compile(
    "[\u3040-\u30fa\u30fc-\u30ff\u3400-\u9fff]"
)  # 가운뎃점 ・(U+30FB)는 한국어 문안도 쓴다


def rev_tables():
    jp = dict(textenc.charmap())
    jp.update(textenc.CONTROL)
    kr = dict(jp)
    for ch, c in hangul.load().items():
        kr[c] = ch
    return jp, kr


def view(codes, rev):
    out, i = [], 0
    while i < len(codes):
        w = codes[i]
        if w == textenc.TERM:
            break
        if w == 0xEEEE and i + 2 < len(codes):
            out.append(f"⟦{codes[i + 1] + codes[i + 2]}⟧")
            i += 3
            continue
        out.append(rev.get(w, f"{{c{w:03x}}}"))
        i += 1
    return "".join(out)


def mark(jp_codes, kr_codes, jp, kr, shared):
    if shared:
        return "포인터 공유"
    if not jp.strip() and not kr.strip():
        return "둘 다 빔"
    if not jp.strip():
        return "한글만"
    if jp_codes == kr_codes:
        return "원판만" if JPCH.search(jp) else ""
    return "일본어 남음" if JPCH.search(kr) else ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr-bin", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    kr_bin = a.kr_bin or os.path.join(common.BUILD_DIR, "Eiyuu Densetsu IV (KR).bin")
    common.verify_source()
    jp_bin = common.orig_bin()
    jp_rev, kr_rev = rev_tables()
    os.makedirs(a.out, exist_ok=True)
    rows, stats = [], Counter()
    jp_files = common.iso_files(jp_bin)
    with common.open_disc(kr_bin) as dk, common.open_disc(jp_bin) as dj:
        for path, lba, size in dk.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            try:
                _, ents_ = gmf_arc.arc_parse(dk.read_extent(lba, size))
                jl, js = jp_files[path]
                _, jents = gmf_arc.arc_parse(dj.read_extent(jl, js))
            except (gmf_arc.ArchiveError, KeyError):
                continue
            kdata, jdata = dk.read_extent(lba, size), dj.read_extent(jl, js)
            jmap = {nm: (off, sz) for nm, off, sz in jents}
            for nm, off, sz in ents_:
                if "\\BIN\\" not in nm or not nm.endswith(".BIN") or sz < 8 or nm not in jmap:
                    continue
                mem = kdata[off : off + sz]
                joff, jsz = jmap[nm]
                jmem = jdata[joff : joff + jsz]
                try:
                    ksegs = reinsert.member_segments(mem)
                    jsegs = reinsert.member_segments(jmem)
                    streams = typeset.message_streams(mem)
                except Exception:  # noqa: BLE001, S112 — 파서가 못 읽는 멤버(풀 규격)는 대사 표 밖
                    continue
                tag = f"{path.split('/')[-1][:-4]}_{nm.split(chr(92))[-1][:-4]}"
                pages = []
                for si, st in enumerate(streams):
                    pp = dialog_render.pages_of(mem, st, ksegs)
                    for k, (ids, _rows) in enumerate(pp):
                        pages.append((si, ids, k + 1 < len(pp)))
                use = Counter(i for _s, ids, _c in pages for i in ids)
                inpage = set(use)
                for n, (_si, ids, more) in enumerate(pages, 1):
                    jc = [jsegs[i] for i in ids if i < len(jsegs)]
                    kc = [ksegs[i] for i in ids if i < len(ksegs)]
                    jt = "↵".join(view(c, jp_rev) for c in jc)
                    kt = "↵".join(view(c, kr_rev).rstrip() for c in kc)
                    shared = any(use[i] > 1 for i in ids)
                    m = mark(jc, kc, jt, kt, shared)
                    if more:
                        jt, kt = jt + "⏎", kt + "⏎"
                    rows.append((f"{tag}#{n}", jt, kt, m))
                    stats["대사 쪽"] += 1
                    stats[m or "정상"] += 1
                for i in range(min(len(ksegs), len(jsegs))):
                    if i in inpage:
                        continue
                    jt, kt = view(jsegs[i], jp_rev), view(ksegs[i], kr_rev).rstrip()
                    if not jsegs[i] and not ksegs[i]:
                        continue
                    m = mark(jsegs[i], ksegs[i], jt, kt, False)
                    rows.append((f"{tag}@{i}", jt, kt, m))
                    stats["창 밖 조각"] += 1
                    stats[m or "정상"] += 1
        # UI·낱말 — 실행파일
        jexe = bytes(common.read_file(common.EXE_PATH, jp_bin))
        kexe = bytes(common.read_file(common.EXE_PATH, kr_bin))
        ss = uitext.sites(jexe)
        uitext.apply(
            bytearray(jexe)
        )  # 사본에 굽기만 — 옮겨진 표 주소(`RELOC`)를 채운다(제품 빌드와 같은 계산)
        maps = {}
        for off, s in sorted(ss.items()):
            at = off
            if s["table"] is not None:
                if s["table"] not in maps:
                    try:
                        maps[s["table"]] = uitext.moved(jexe, kexe, s["table"])
                    except SystemExit:
                        maps[s["table"]] = {}
                at = maps[s["table"]].get(off, off)
            kc, _ = uitext.raw_string(kexe, at)
            kc = kc or []
            jt, kt = view(s["codes"], jp_rev), view(kc, kr_rev).rstrip()
            m = mark(s["codes"], kc, jt, kt, False)
            if at != off:
                m = (m + " · " if m else "") + "자리 이동"
            rows.append((f"UI@0x{off:06X}", jt, kt, m))
            stats["UI·낱말"] += 1
            stats[m or "정상"] += 1
    with open(os.path.join(a.out, "pairs.tsv"), "w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        f.writelines(
            "\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n" for r in rows
        )
    sha = hashlib.sha1()
    with open(kr_bin, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            sha.update(blk)
    head = subprocess.run(
        ["git", "rev-parse", "--short=9", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    with open(os.path.join(a.out, "stats.txt"), "w", encoding="utf-8") as f:
        f.write(f"rows {len(rows)}\nsha1 {sha.hexdigest()}\nhead {head}\n")
        for k, v in stats.most_common():
            f.write(f"{k}\t{v}\n")
    print(len(rows), sha.hexdigest()[:12], head)
    for k, v in stats.most_common():
        print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
