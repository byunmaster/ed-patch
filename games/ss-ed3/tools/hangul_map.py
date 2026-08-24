"""한글 ↔ 글리프 슬롯 배정 — **커밋되는 정본**.

한글은 「원본이 안 쓰는 한자 슬롯을 덮어쓰고, 문안은 그 슬롯의 SJIS 코드로 인코딩」해서
넣는다. 새턴 ED1+2 와 같은 수법이고, 대상이 EXE 가 아니라 파일 하나라 훨씬 싸다.

🔴 **배정은 파생물이 아니라 정본이다.** 「안 쓰는 슬롯」은 덤프에서 나오는데, 소재를 하나
   더 열면 `used_indices` 가 늘어 **빈 슬롯 목록이 통째로 밀린다.** 그러면 이미 넣은 문안이
   전부 다른 글자로 읽힌다. 그래서 한 번 정하면 `hangul_map.json` 에 **박아 두고**,
   빌드는 그 파일만 읽는다(루트 `CLAUDE.md` 「제1 원칙 — 빌드는 결정적이어야 한다」).

   갱신은 `--freeze` 로 **명시적으로만** 한다. 그때 이미 넣은 문안은 다시 구워야 한다.

⚠ 앞쪽 구(1~15 기호·가나·로마자)는 안 쓴다 — `shared.text.sjis.kanji_start()` 참조.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common as C
import font as F
import mapfile as M

from shared.text import sjis

MAP_PATH = os.path.join(C.GAME_DIR, "hangul_map.json")


def ksc_syllables():
    """완성형(KS X 1001) 한글 음절 2,350자 — **가나다순**.

    코드 순서가 곧 가나다순이라 정렬이 따로 필요 없다.
    """
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes((hi, lo)).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if "가" <= ch <= "힣":
                out.append(ch)
    return out


def assign(free=None):
    """`{음절: 글리프 색인}` — 빈 슬롯 앞에서부터 가나다순으로."""
    syl = ksc_syllables()
    free = sorted(free if free is not None else F.free_slots())
    if len(free) < len(syl):
        raise SystemExit(f"빈 슬롯이 모자란다: {len(free)} < {len(syl)}")
    return dict(zip(syl, free[: len(syl)], strict=True))


def load():
    """정본 배정을 읽는다. 없으면 무엇을 해야 하는지 알려 준다."""
    if not os.path.exists(MAP_PATH):
        raise SystemExit(f"배정 정본이 없다: {MAP_PATH}\n  먼저: hangul_map.py --freeze")
    with open(MAP_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: i for ch, i in zip(doc["syllables"], doc["slots"], strict=True)}


def encode_kr(text, table=None):
    """문안 → 게임 바이트열. 한글은 슬롯 SJIS 로, 나머지는 그대로 SJIS 로.

    🔴 **제어코드는 `mapfile.encode_text` 가 처리한다** — 여기서 직접 인코딩하면
    `"\n"` 이 `0x0A` 로 나가는데 게임 개행은 `0x0D` 다. 길이가 같아 모든 검사를 통과하고
    **화면에서만 조판이 깨진다**(2026-08-24 실제로 물렸다).

    ⚠ 표에 없는 한글·SJIS 밖 글자면 **곧바로 운다** — 조용히 빠지면 화면에서만 사라진다.
    """
    table = table if table is not None else load()

    def one(ch):
        if "가" <= ch <= "힣":
            if ch not in table:
                raise KeyError(f"배정에 없는 음절: {ch!r}")
            return sjis.sjis_of_index(table[ch])
        try:
            return ch.encode("shift_jis")
        except UnicodeEncodeError:
            # ⚠ 비슷하게 생긴 글자에 잘 걸린다 — `·`(U+00B7) vs 게임이 쓰는 `・`(U+30FB),
            #   `…` vs `・・・`, `~` vs `〜`. 조용히 빠지면 화면에서만 사라진다.
            raise KeyError(
                f"SJIS 로 못 넣는 글자: {ch!r} (U+{ord(ch):04X}) — 게임이 쓰는 글자로 바꾼다"
            ) from None

    return M.encode_text(text, char=one)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true", help="배정을 정본으로 박는다")
    a = ap.parse_args()
    used = F.used_indices()
    free = F.free_slots(used)
    table = assign(free)
    syl = list(table)
    print(f"음절 {len(syl):,}  쓰는 글리프 {len(used):,}  빈 슬롯 {len(free):,}")
    print(f"  배정 {sjis.ku_ten(table[syl[0]])} ~ {sjis.ku_ten(table[syl[-1]])}")
    for ch in ("가", "한", "글", "히"):
        i = table[ch]
        print(
            f"  {ch} → 색인 {i} (구{sjis.ku_ten(i)[0]} 점{sjis.ku_ten(i)[1]}) SJIS {sjis.sjis_of_index(i).hex()}"
        )
    if not a.freeze:
        if os.path.exists(MAP_PATH):
            same = load() == table
            print(f"\n정본과 {'같다' if same else '❌ 다르다 — 소재가 바뀌었다'}")
        else:
            print(f"\n정본이 없다 — `--freeze` 로 박는다 ({MAP_PATH})")
        return
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_doc": "한글 음절 → 글리프 색인. 🔴 파생물이 아니라 정본이다 — 자세한 건 tools/hangul_map.py",
                "syllables": syl,
                "slots": [table[c] for c in syl],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(f"\n✅ 정본으로 박았다 → {MAP_PATH}")


if __name__ == "__main__":
    main()
