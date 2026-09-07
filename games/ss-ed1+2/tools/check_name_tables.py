#!/usr/bin/env python3
"""**고유명사 표 포인터가 제 이름을 가리키나** — 최종 이미지에서 되읽는다.

    python3 tools/check_name_tables.py

## 왜 있나 (2026-09-07 — 유저 인게임 캡처에서 왔다)

화면에 「c의 공격」·「陸를 얻었다」·「A아스의 말이 떠올랐다」가 떴다. 원인은 **뒤 단계가
앞 단계의 자리를 덮은 것**이었다 — `patch_ui` 가 이름 표를 통째로 다시 깔았는데,
`patch_scn` 의 이주 풀이 「비었나」를 **원본 덤프의 칸 경계**로 세는 바람에 살아 있는 한글
이름 위에 대사를 얹었다(`patch_scn._untouched` 가 그 구멍을 막는다).

🔴 **그때 게이트가 하나도 안 울었다.** 되읽기는 「내가 쓴 것이 그대로 있나」를 **자기가 쓴
   직후에** 묻고, 라운드트립은 덤프↔원본을, 무변경 구간은 **안 여는 파일**을 본다. 셋 다
   「앞 단계가 깔아 둔 것을 뒤 단계가 덮었나」는 안 본다.
⇒ 그래서 **체인이 다 끝난 이미지에서** 포인터를 따라가 이름을 되읽는다. 표는 화면에 가장
   자주 나오는 데이터(아이템·주문·몬스터)라 여기가 깨지면 전투·인벤토리·상점이 함께 깨진다.

⚠ 판정은 **원본에서 유도**한다 — 어느 칸이 어떤 이름이어야 하는지는 `patch_ui.name_rows`
  (원본 이미지)가 정본이고, 여기서는 그것을 **다시 계산하지 않는다.**
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import font
import patch_ui

MAXLEN = 64


def _inv_map():
    """슬롯 SJIS → 한글 한 글자."""
    syl = json.load(open(os.path.join(common.GAME_DIR, "hangul_map_11kanji.json")))["syllables"]
    return {font.sjis_of_index(i): c for c, i in syl.items()}


def _decode(b, inv):
    out, i = [], 0
    while i < len(b):
        two = b[i : i + 2]
        if two in inv:
            out.append(inv[two])
            i += 2
        elif 0x81 <= b[i] <= 0x9F or 0xE0 <= b[i] <= 0xEF:
            try:
                out.append(two.decode("cp932"))
            except UnicodeDecodeError:
                out.append(f"<{two.hex()}>")
            i += 2
        else:
            out.append(chr(b[i]))
            i += 1
    return "".join(out)


def check():
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        return None, []
    inv = _inv_map()
    f0, mm0 = common.open_image()
    try:
        rows = patch_ui.name_rows(mm0)
    finally:
        mm0.close()
        f0.close()
    f1, mm1 = common.open_image(img[0])
    bad, total = [], 0
    try:
        files = {p: (l, s) for p, l, s in common.iso_files(mm1)}
        for t in rows:
            d = common.read_extent(mm1, *files[t["path"]])
            for _at, jp, kr, ptrs in t["recs"]:
                want = kr or jp
                for p in ptrs:
                    total += 1
                    ram = int.from_bytes(d[p : p + 4], "big")
                    o = ram - patch_ui.NAME_PTR_BASE
                    if not (0 <= o < len(d)):
                        bad.append((t["path"], t["what"], want, p, "표 밖을 가리킨다"))
                        continue
                    z = d.find(b"\x00", o, o + MAXLEN)
                    got = _decode(d[o : z if z > 0 else o + MAXLEN], inv)
                    if got != want:
                        bad.append((t["path"], t["what"], want, p, got))
    finally:
        mm1.close()
        f1.close()
    return total, bad


def main():
    total, bad = check()
    if total is None:
        print("     ⏭ 빌드 이미지가 없다 — 건너뜀")
        return 0
    mark = "✅" if not bad else "❌"
    print(f"     {mark} 고유명사 포인터 되읽기 {total - len(bad):,}/{total:,}")
    for path, what, want, p, got in bad[:8]:
        print(f"        🔴 {path} {what} 0x{p:X}: {want!r} 인데 {got!r} 을 가리킨다")
    if bad:
        raise SystemExit("이름 포인터가 딴 것을 가리킨다 — 뒤 단계가 표를 덮었을 수 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
