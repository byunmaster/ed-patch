"""
DOS 정발판(만트라) 대사에서 사용 한글 음절 집계.

목적: 한글 인코딩 설계 — PS1 폰트의 한자 슬롯(약 2,965개)에 어떤 음절을
몇 개나 배정해야 하는지 산정. 완성형(CP949) 음절 블록(리드 0xB0~0xC8)을
스캔해 게임별 사용 음절과 빈도를 집계한다.

사용: python census_syllables.py [DOS정발판루트]  (기본: ../../originals/kr)
      (루트 아래 dos-ed1/SINDLL/*.DLL, dos-ed2/SCENA/*.DLL을 읽음)
출력: out/syllable_census.txt (음절 목록·빈도), 콘솔 요약
"""

import os
import re
import sys
from collections import Counter

from common import OUT_DIR

# 완성형 음절: 리드 0xB0~0xC8, 트레일 0xA1~0xFE (KS X 1001 2,350자 영역)
HANGUL_RUN = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe]){2,}")

SOURCES = {
    "ED1": ("dos-ed1", "SINDLL"),
    "ED2": ("dos-ed2", "SCENA"),
}


def census_dir(path):
    counter = Counter()
    files = 0
    for name in sorted(os.listdir(path)):
        if not name.upper().endswith(".DLL"):
            continue
        data = open(os.path.join(path, name), "rb").read()
        files += 1
        for m in HANGUL_RUN.finditer(data):
            try:
                s = m.group().decode("cp949")
            except UnicodeDecodeError:
                continue
            counter.update(s)
    return counter, files


def main():
    default_root = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "originals", "kr"
    )
    root = sys.argv[1] if len(sys.argv) > 1 else default_root

    per_game = {}
    total = Counter()
    for game, parts in SOURCES.items():
        path = os.path.join(root, *parts)
        if not os.path.isdir(path):
            print(f"{game}: {path} 없음 — 건너뜀")
            continue
        counter, files = census_dir(path)
        per_game[game] = counter
        total += counter
        print(
            f"{game}: DLL {files}개, 총 음절 수 {sum(counter.values()):,}, 고유 음절 {len(counter):,}"
        )

    print(f"\n합계: 고유 음절 {len(total):,}자 (완성형 2,350자 중 {len(total) * 100 // 2350}%)")
    print(f"PS1 한자 1급 슬롯 약 2,965개 대비 여유: {2965 - len(total):,}")
    print("최빈 20:", "".join(ch for ch, _ in total.most_common(20)))

    out = os.path.join(OUT_DIR, "syllable_census.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# DOS 정발판 사용 음절 집계 — 고유 {len(total)}자\n")
        for game, counter in per_game.items():
            f.write(f"\n[{game}] 고유 {len(counter)}자\n")
            f.write("".join(sorted(counter)) + "\n")
        f.write("\n[합계 빈도순]\n")
        f.writelines(f"{ch}\t{n}\n" for ch, n in total.most_common())
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
