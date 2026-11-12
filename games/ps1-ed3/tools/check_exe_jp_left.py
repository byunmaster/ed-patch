"""ED3.EXE 안에 **원문 그대로 남은 일본어 문자열**이 있나 — 제품 롬 게이트(11-07 관리자 「코드가 복사·붙이기로 낼 수 있는 일본어」).

🔴 왜: 제품 롬은 한글 글리프를 **원래 한자·가나 코드 자리에 재배정**한다. 그래서 안 옮긴 문자열은 일본어로 남는 게 아니라
   **엉뚱한 한글 + 남은 가나**로 나간다(「무기를 はずす」 → 깨진 글자). 11-07 에 장비 해제 명령 셋(`0x9D0C8` 꼴)이 구역 라벨이 noise 라
   스캐너·UI 정본·검사 어디에도 안 걸린 채 이 상태였다.
방법: 원판 `ED3.EXE` 에서 종결(`0`·`FFFF`·최상위 비트)로 갈린 **전부 아는 코드** 조각 중 가나 비율 60%↑·4자↑인 것이
   제품에서 바이트까지 같으면 실패. 기계어·애니 자료가 우연히 가나로 읽히는 자리는 `KNOWN_DATA`(오프셋 + 이유)에 둔다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_names
import textenc

KNOWN_DATA = {
    0x99BAE: "몬스터 표 사이 스프라이트 자료(ヤリュリュ 꼴 반복 — 코드 4개가 번갈아 반복되는 애니 표)",
}
MIN_LEN = 4


def kana(c):
    return "ぁ" <= c <= "ヿ"


def find(orig, built, cm):
    out = []
    for off, n, s in dump_names.strings(orig, cm, max_len=200, newline=True):
        t = s.replace("\n", "")
        if len(t) < MIN_LEN or sum(map(kana, t)) / len(t) < 0.6:
            continue
        if any(c in "ＢＨＦ３７４６９ＯＰ井育域越吸" for c in t) or len(set(t)) < 2:
            continue
        if built[off : off + 2 * n] == orig[off : off + 2 * n]:
            out.append((off, n))
    return out


def main():
    built_path = sys.argv[sys.argv.index("--built") + 1]
    cm = textenc.charmap("ed3")
    lba, sz = common.iso_files("ed3")["/ED3.EXE"]
    o = common.read_lba("ed3", lba, sz)[0x800:]
    tree, _ = common.iso_tree(built_path)
    lba, sz = tree["/ED3.EXE"]
    b = common.read_lba("ed3", lba, sz, path=built_path)[0x800:]
    hits = find(o, b, cm)
    bad = [(off, n) for off, n in hits if off not in KNOWN_DATA]
    print(
        f"EXE 원문 그대로 남은 문자열 [ed3] — 후보 {len(hits)} · 자료로 알려진 {len(hits) - len(bad)} · 미정 {len(bad)}"
    )
    for off, n in bad:
        print(
            f"  🔴 ED3.EXE 파일 +0x{off + 0x800:X} ({n}코드) 가 제품에도 원문 그대로다 — ui_ed3 에 올리거나(KNOWN_DATA 는 자료일 때만)"
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
