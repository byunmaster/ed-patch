"""화면 일본어 잔존 게이트(기준선 래칫) — 이미지의 대본 조각 중 **가나·한자가 든 조각 수**가 기준선보다 **늘면 실패**.

    python3 tools/check_jp_left.py [--image 경로] [--freeze]

🔴 번역 전(지금)의 기준선 = 원본 전량이다. 번역이 진행되면 수가 줄고, 줄면 `--freeze` 로 기준선을 내린다(래칫).
늘면 — 재삽입이 조용히 조각을 원문으로 되돌렸거나(`size`·`fmt_drop` 탈락) 정본이 깨졌다는 뜻이라 서 있는 자리에서 막는다
(루트 CLAUDE.md 「화면에 나가는 바이트를 게이트로 본다」 — 빌드도 단위 테스트도 통과하는 부류).
⚠ 이건 **대본**만 잰다 — 실행파일 문자열(UI)·그림 글자는 아직 범위 밖이다(`status.md`).
`--image` 를 안 주면 원본을 잰다(= 기준선 자체의 재현). 제품 이미지는 `--image` 로.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import hangul
import textenc

from shared.ps1 import gmf_arc
from shared.ps1 import gmf_script as scriptmap

BASELINE = os.path.join(common.ROOT, "jp_left_baseline.json")


def is_jp(ch):
    o = ord(ch)
    return 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or ch == "々"


def screen_map():
    """{코드: 화면에 나가는 글자} — 원본 코드표 위에 **한글 자리 정본을 덮는다**.

    🔴 한글이 앉은 자리는 원래 한자 코드라, 원본 코드표로만 읽으면 한글을 한자로 센다(시험 빌드가 줄어들지 않았다).
    """
    m = dict(textenc.charmap())
    for ch, code in hangul.load().items():
        m[code] = ch
    return m


def scan(image=None):
    """{segments: 가나·한자가 든 조각 수, chars: 그 글자 수, total: 전체 조각 수}"""
    seg = chars = total = 0
    cm = screen_map()
    with common.open_disc(image) as d:
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if "\\BIN\\" not in nm or not nm.endswith(".BIN") or sz < 8:
                    continue
                for _, codes in scriptmap.parse(data[off : off + sz])["segments"]:
                    total += 1
                    n = sum(1 for c in codes if c in cm and is_jp(cm[c]))
                    if n:
                        seg += 1
                        chars += n
    return {"segments": seg, "chars": chars, "total": total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    got = scan(a.image)
    if a.freeze:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(got, f, indent=1)
        print(f"기준선을 {got} 로 박았다")
        return 0
    if not os.path.exists(BASELINE):
        print("🔴 기준선이 없다 — `--freeze` 로 먼저 박는다")
        return 1
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    if got["total"] != base["total"]:
        print(f"🔴 조각 총수가 다르다 {got['total']} (기준선 {base['total']}) — 구조가 바뀌었다")
        return 1
    up = got["segments"] > base["segments"] or got["chars"] > base["chars"]
    print(
        f"화면 일본어 잔존 — 조각 {got['segments']:,}/{got['total']:,} · 글자 {got['chars']:,} "
        f"(기준선 {base['segments']:,} · {base['chars']:,})" + (" 🔴 늘었다" if up else "")
    )
    if not up and (got["segments"] < base["segments"] or got["chars"] < base["chars"]):
        print("  ↓ 줄었다 — `--freeze` 로 기준선을 내린다(래칫)")
    return 1 if up else 0


if __name__ == "__main__":
    sys.exit(main())
