#!/usr/bin/env python3
"""이어 붙는 메시지의 첫 줄 폭 게이트 — 키 대기(`%c`=9) 뒤 **앞 줄에 이어 그려지는 블록**의 첫 줄이 남은 폭에 드나.

    python3 tools/check_key_cont_width.py        # 실패면 종료코드 1

🔴 왜(2026-10-23, pce-ed1 10-22 실측 「앞 메시지가 쓴 폭을 조판기가 모른다」): 이 게임의 이음 구조는 `script/key_cont.json` 의 커서 폭(대사 보기 실측)을
`patch_scn.key_cont_fix` 가 첫 줄에서 빼 맞춘다. 이 게이트는 **그 결과를 전량 되읽어** `커서 + 첫 줄 폭 ≤ 14` 인지 잰다.
- 커서가 줄 끝(≥14)이면 엔진이 새 줄로 접으니 제외(설계 — `key_cont_fix.cont`). 블록이 개행으로 시작해도 제외.
- ⚠ 분모가 0 이면 실패한다 — 표를 못 읽고 「0건 통과」하는 걸 막는다(표 적재 순서 약점이 실제로 있었다).
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))


def main():
    import common
    import patch_scn as P
    from typeset_scn import COLS, width

    canon = P.load_canon(quiet=True)
    _f, mm = common.open_image(os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin"))
    P.key_cont_fix("x", "x", "/BIN/ED2SCN01.BIN")  # 표 적재
    kc = P._KEY_CONT or {}
    total, skipped, bad, seen = 0, 0, [], set()
    for path, _l, _s in common.iso_files(mm):
        if not P.DIALOG_RE.match(path):
            continue
        got = P.load(path)
        if not got:
            continue
        game = "ED1" if "/ED1SCN" in path else "ED2"
        sites = P.sites_for(path)
        for e in got[1]:
            jp = e.get("text", "")
            if not jp:
                continue
            w0 = kc.get(game, {}).get(P.line_key(jp))
            off = int(e["file_offset"], 16)
            if w0 is None or (path, off) in seen:
                continue
            seen.add((path, off))
            kr = P.canon_of(canon, jp, sites.get(off), path=path, off=off)
            if not kr:
                continue
            total += 1
            body = re.sub(r"^%c(?![^%\n]+%c\n)", "", kr)
            if body.startswith("\n") or w0 >= COLS:
                skipped += 1
                continue
            first = re.split(r"\n|\x08", body)[0].replace("%c", "")
            if w0 + width(first) > COLS + 0.001:
                bad.append((path[-12:], hex(off), w0, width(first), first[:24]))
    print(f"  ✅ 이음 첫 줄 폭 [이음 블록 {total}] — 줄 끝에서 시작/개행 시작 {skipped} · 넘침 {len(bad)}")
    for b in bad[:20]:
        print(f"     ❌ {b}")
    if total == 0:
        raise SystemExit("이음 블록 0 — 표를 못 읽었다(분모 0 은 통과가 아니다)")
    if bad:
        raise SystemExit(f"이음 첫 줄 넘침 {len(bad)}건")


if __name__ == "__main__":
    main()
