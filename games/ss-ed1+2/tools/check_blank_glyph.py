#!/usr/bin/env python3
"""빈 글리프 게이트 — 씬 문안 전량에서 **화면에 나가는 글자 중 빌드 폰트(11KANJI.FON)의 칸이 비어 있는 것**이 0 인가.

    python3 tools/check_blank_glyph.py            # 실패면 종료코드 1

🔴 왜(2026-10-19 qa r6 「빛의 엘리베이터　　를」): ‘ ’ 는 cp932 로 인코딩되지만 원판 폰트 칸이 비어 있어 **조용히 빈 칸으로** 나갔다. 빌드도 단위 테스트도
   통과했다 — 폰트 구멍 채우기(`patch_ui.kanji_gaps`)가 씬 문안을 입력으로 못 받았기 때문이다. 이 게이트가 **결과**(빌드 폰트의 그 칸이 비었나)를 본다.
본다: 씬 문안 전량(`patch_scn.all_texts`)의 전각 글자(한글은 슬롯 정본, 나머지는 cp932 2B) → 빌드 이미지의 `11KANJI.FON` 칸에 잉크가 있나. 전각 공백(0x8140)은 빈 글리프가 정답이다.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))


def main():
    import common
    import font
    import patch_scn

    img = os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.bin")
    if not os.path.exists(img):
        raise SystemExit("빈 글리프: 빌드 이미지가 없다 — 먼저 빌드한다")
    _f, mm = common.open_image(img)
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
    kan = common.read_extent(mm, *files["/11KANJI.FON"])
    asc = common.read_extent(mm, *files["/11ASCII.FON"])  # 반각 곡선 따옴표(`font.HALF_QUOTES`)는 이쪽 칸을 본다
    with open(os.path.join(common.GAME_DIR, "hangul_map_11kanji.json"), encoding="utf-8") as f:
        hmap = json.load(f)["syllables"]
    texts = patch_scn.all_texts()
    seen, bad = set(), {}
    for kr in texts:
        for ch in kr or "":
            if ch in seen or ch.isascii() or ch.isspace() or ch == "　":
                continue
            seen.add(ch)
            if ch in font.HALF_QUOTES:
                code = font.HALF_QUOTES[ch]
                if not any(asc[code * 11 : code * 11 + 11]):
                    bad[ch] = f"빌드 11ASCII 칸 {code:#x} 이 비었다"
                continue
            if "가" <= ch <= "힣":
                idx = hmap.get(ch)
            else:
                try:
                    b = ch.encode("cp932")
                except UnicodeEncodeError:
                    bad[ch] = "cp932 로 못 쓴다·슬롯도 없다"
                    continue
                if len(b) != 2:
                    continue
                idx = font.game_index(b)
            if idx is None:
                bad[ch] = "슬롯 정본에 없다"
            elif not any(kan[idx * font.GLYPH_STRIDE :][: font.GLYPH_STRIDE]):
                bad[ch] = f"빌드 폰트 칸 {idx} 이 비었다"
    # 🔴 **서로 같은 비트맵인 반각 글자 쌍이 없나**(2026-10-20 qa r5: 쉼표가 마침표와 같은 비트맵 — 굽는 단계에서 꼬리 행이 잘려 쉼표 3,983곳이 마침표로 그려졌다).
    #    문안에서 쓰는 반각 글자 전부(ASCII + 곡선 따옴표 코드)의 **빌드 11ASCII 글리프**를 서로 비교한다 — 한 쌍이라도 같으면 화면에서 구별이 안 된다.
    orig_asc = common.extract("/11ASCII.FON")  # 원판 반각 폰트 — 원판이 처음부터 같은 모양인 쌍(숫자 0 과 영문 O)은 우리가 굽다 생긴 게 아니다
    half = {}
    for ch in sorted({c for kr in texts for c in (kr or "")}):
        if ch in font.HALF_QUOTES:
            code = font.HALF_QUOTES[ch]
        elif 0x21 <= ord(ch) < 0x7F:
            code = ord(ch)
        else:
            continue
        g = bytes(asc[code * 11 : code * 11 + 11])
        if any(g):
            half.setdefault(g, []).append((ch, g != bytes(orig_asc[code * 11 : code * 11 + 11])))
    same = [chs for chs in half.values() if len(chs) > 1 and any(baked for _c, baked in chs)]
    for chs in same:
        bad[chs[0][0]] = f"{''.join(c for c, _b in chs)!r} 가 같은 비트맵 — 화면에서 구별이 안 된다(반각 글리프 굽기)"
    print(f"  빈 글리프 [씬 문안 글자 {len(seen):,}종 · 반각 {sum(len(v) for v in half.values())}종] — 빈 칸으로 나가는 글자 {len(bad) - len(same)} · 같은 비트맵 쌍 {len(same)}")
    for ch, why in sorted(bad.items()):
        print(f"     ❌ {ch!r} U+{ord(ch):04X} — {why}")
    if bad:
        raise SystemExit(f"빈 글리프 {len(bad)}종 — 폰트에 구워 넣는다(`patch_ui.kanji_gaps`)")


if __name__ == "__main__":
    main()
