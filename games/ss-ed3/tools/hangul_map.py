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
import glossary_src as GS
import mapfile as M

from shared.text import sjis

MAP_PATH = os.path.join(C.GAME_DIR, "hangul_map.json")

#   🔴 **0 행을 자르는 창 전용 배정** — 같은 글자를 **한 행 내려 그린 글리프**를 따로 든다.
#     기본 글리프는 원판 한자와 같은 자리(0~10 행)에 앉힌다. 그런데 **스탯 창은 글리프의
#     0 행을 버린다**(2026-08-27 실측) — 한자는 0 행이 1~2 화소라 티가 안 나지만
#     한글은 초성 윗변이 **가로획**이라 7~9 화소가 통째로 날아간다(공·구·마·지·정).
#     ⇒ 그 창에 나가는 문안만 **한 행 내린 판**으로 인코딩한다.
#   ⓘ 종전에는 반대로 했다 — 전역으로 한 행 내려 두고(`DY=-2`) 안 자르는 창에서 1 px 씩
#     손해를 봤다. 챕터 바에서 글자가 아래 테두리에 붙는 것으로 드러났다(2026-09-03).
#   ⚠ 이것도 정본이다(`--freeze-low`). 빈 슬롯 목록이 밀리면 이미 넣은 문안이 딴 글자가 된다.
LOW_PATH = os.path.join(C.GAME_DIR, "lowered_map.json")

#   🔴 **책 화면 전용 배정** — 읽을거리는 12 열 글리프를 **8 열로 더해서** 그린다(status 7 절).
#     합침이 깎는 건 폭이 아니라 **획 사이 틈**이라, 칸을 꽉 채우는 글꼴일수록 손해가 크다.
#     실측(2026-09-06): 원판 가나는 잉크 폭 9·화소 25 라 살아남고 한자는 11·53 이라 원문에서도
#     뭉갠다. 우리 Galmuri11 은 10·43 으로 **한자 쪽**이다. 같은 몸집의 `Galmuri9`(9·28)를
#     책에만 쓰면 자모가 갈린다.
#   ⚠ 이것도 정본이다 — 빈 슬롯이 밀리면 이미 넣은 문안이 딴 글자가 된다(`--freeze-book`).
#   ⓘ **파일이 없으면 책도 기본 글리프로 나간다** — 있고 없고로 두 판을 구워 견줄 수 있다.
BOOK_PATH = os.path.join(C.GAME_DIR, "book_map.json")


#   🔴 **크레딧 자막 전용 배정** — 크레딧 자막은 Galmuri9 로 작게 그린다(마스터 10-01). 같은 코드를
#     본 글리프와 나눠 쓸 수 없어 **남은 빈 슬롯**에 자막에 쓰인 음절만 따로 든다(글리프 폰트 한 장이라
#     크레딧 때만 바꿔 끼울 수 없다). 그리는 쪽은 글자 폭 10 으로 부른다(`subtitle_stub.draw_line9`).
#   ⚠ 이것도 정본이다(`--freeze-cred`). 빈 슬롯이 밀리면 이미 넣은 문안이 딴 글자가 된다.
CRED_PATH = os.path.join(C.GAME_DIR, "credits_map.json")
CRED_SRC = os.path.join(C.GAME_DIR, "script", "voice_credits.json")


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


def lowered_chars():
    """한 행 내린 판이 필요한 글자 — **0 행을 자르는 창에 나갈 수 있는 문안 전량**.

    갈래 셋이다: `/0.BIN` 시스템 표(정본·사전 → `system_src.py`, 챕터 바 포함 — 아래 🔴) ·
    이름 정본(공용 사전) · 설명문(`desc_*.json`).
    ⚠ **한글만** 든다. 반각·전각 숫자는 원본 자리가 0~9 행이라 0 행을 버려도 안 잘린다.
    """
    out = set()

    def take(txt):
        out.update(c for c in txt if "가" <= c <= "힣")

    import system_src as SYS

    for v in SYS.sections().values():
        for x in v.values():
            take(x)
    for tbl in GS.categories().values():
        for x in tbl.values():
            take(x)
    for n in ("desc_item", "desc_spell"):
        with open(os.path.join(C.GAME_DIR, "script", f"{n}.json"), encoding="utf-8") as f:
            for x in json.load(f).values():
                if isinstance(x, str):
                    take(x)
    #   지명 배너(`폴티아 루데라 관문`) — 한 행 내려야 막대 안에서 위 2 · 아래 1 이 된다(`banner.py`, 마스터 10-09).
    import glob

    import banner

    for path in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "MAP*.json"))):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        out.update(banner.chars(v for v in doc.values() if isinstance(v, str)))
    return sorted(out)


def load_low():
    """자르는 창 전용 배정. 없으면 빈 표 — **없어도 빌드는 돈다**(기본 자리로 그려진다)."""
    if not os.path.exists(LOW_PATH):
        return {}
    with open(LOW_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: i for ch, i in zip(doc["chars"], doc["slots"], strict=True)}


def book_chars():
    """읽을거리 본문에 실제로 쓰인 음절 — 가나다순."""
    import glob

    out = set()
    for path in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "book", "BOOK*.json"))):
        with open(path, encoding="utf-8") as f:
            for v in json.load(f).values():
                if isinstance(v, str):
                    out |= {c for c in v if "가" <= c <= "힣"}
    return sorted(out)


def load_book():
    """책 화면 전용 배정을 **본 배정 위에 얹은** 표. 파일이 없으면 본 배정 그대로."""
    table = load()
    if not os.path.exists(BOOK_PATH):
        return table
    with open(BOOK_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    table = dict(table)
    table.update(zip(doc["chars"], doc["slots"], strict=True))
    return table


def freeze_book(free):
    """책 전용 배정을 박는다 — 본 배정·내려앉은 배정이 쓰고 **남은** 빈 슬롯에서."""
    chars = book_chars()
    taken = set(load().values()) | set(load_low().values())
    rest = [i for i in sorted(free) if i not in taken]
    if len(rest) < len(chars):
        raise SystemExit(f"빈 슬롯이 모자란다: {len(rest)} < {len(chars)}")
    table = dict(zip(chars, rest[: len(chars)], strict=True))
    with open(BOOK_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_doc": "책 화면 전용 글리프 배정(작고 성근 글꼴). "
                "🔴 파생물이 아니라 정본이다 — 자세한 건 tools/hangul_map.py 의 BOOK_PATH 주석",
                "chars": chars,
                "slots": [table[c] for c in chars],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(f"✅ 책 전용 배정 {len(chars)}자 → {BOOK_PATH}")
    print(f"   남은 빈 슬롯 {len(rest) - len(chars):,}")


#   부호도 **전각 칸 글리프**로 둔다 — 엔진 반각은 전진량이 4px(글자 폭 10 의 1/4 올림 내림)인데 글리프는 6px 라
#   다음 글자가 부호 꼬리를 덮어 「?」가 잘린다(마스터 10-01). 부호 뒤 공백은 그 칸이 대신한다(voice_credits).
CRED_PUNCT = ".,?!~"


def cred_chars():
    """크레딧 자막에 쓰인 음절 + 부호 — 가나다순."""
    with open(CRED_SRC, encoding="utf-8") as f:
        doc = json.load(f)
    out = set()
    for sub in doc["subs"]:
        for line in sub["lines"]:
            out |= {c for c in line if "가" <= c <= "힣" or c in CRED_PUNCT}
    return sorted(out)


def load_cred():
    """크레딧 전용 배정 `{음절: 슬롯}`. 파일이 없으면 빈 표."""
    if not os.path.exists(CRED_PATH):
        return {}
    with open(CRED_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: i for ch, i in zip(doc["chars"], doc["slots"], strict=True)}


def freeze_cred(free, force=False):
    """크레딧 전용 배정을 박는다 — 본·내려앉은·책 배정이 쓰고 **남은** 빈 슬롯에서.

    이미 있으면 **없는 글자만 덧붙인다**(이미 박힌 자리는 그대로 — 옛 빌드와 같은 코드를 지킨다).
    """
    have = load_cred()
    chars = cred_chars()
    taken = set(load().values()) | set(load_low().values())
    if os.path.exists(BOOK_PATH):
        with open(BOOK_PATH, encoding="utf-8") as f:
            taken |= set(json.load(f)["slots"])
    taken |= set(have.values())
    rest = [i for i in sorted(free) if i not in taken]
    new = [c for c in chars if c not in have]
    if len(rest) < len(new):
        raise SystemExit(f"빈 슬롯이 모자란다: {len(rest)} < {len(new)}")
    table = dict(have)
    table.update(zip(new, rest[: len(new)], strict=True))
    keys = sorted(table)
    with open(CRED_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_doc": "크레딧 자막 전용 글리프 배정(Galmuri9). "
                "🔴 파생물이 아니라 정본이다 — 자세한 건 tools/hangul_map.py 의 CRED_PATH 주석",
                "chars": keys,
                "slots": [table[c] for c in keys],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(f"✅ 크레딧 전용 배정 {len(keys)}자(새로 {len(new)}) → {CRED_PATH}")
    print(f"   남은 빈 슬롯 {len(rest) - len(new):,}")


def encode_kr(text, table=None):
    """문안 → 게임 바이트열. 한글은 슬롯 SJIS 로, 나머지는 그대로 SJIS 로.

    🔴 **제어코드는 `mapfile.encode_text` 가 처리한다** — 여기서 직접 인코딩하면
    `"\n"` 이 `0x0A` 로 나가는데 게임 개행은 `0x0D` 다. 길이가 같아 모든 검사를 통과하고
    **화면에서만 조판이 깨진다**(2026-08-24 실제로 물렸다).

    ⚠ 표에 없는 한글·SJIS 밖 글자면 **곧바로 운다** — 조용히 빠지면 화면에서만 사라진다.
    """
    table = table if table is not None else load()

    def one(ch):
        #   ⚠ **표를 한글 밖에도 본다** — 챕터 줄은 전각 숫자까지 대체 슬롯으로 간다.
        #     기본 표에는 한글밖에 없으니 여기서 달라지는 건 대체 표를 준 자리뿐이다.
        if ch in table:
            return sjis.sjis_of_index(table[ch])
        if "가" <= ch <= "힣":
            raise KeyError(f"배정에 없는 음절: {ch!r}")
        try:
            return ch.encode("shift_jis")
        except UnicodeEncodeError:
            # ⚠ 비슷하게 생긴 글자에 잘 걸린다 — `·`(U+00B7) vs 게임이 쓰는 `・`(U+30FB),
            #   `…` vs `・・・`, `~` vs `〜`. 조용히 빠지면 화면에서만 사라진다.
            raise KeyError(
                f"SJIS 로 못 넣는 글자: {ch!r} (U+{ord(ch):04X}) — 게임이 쓰는 글자로 바꾼다"
            ) from None

    return M.encode_text(text, char=one)


def freeze_low(free):
    """자르는 창 전용 배정을 정본으로 박는다 — **이미 박힌 자리는 그대로, 없는 글자만 빈 슬롯에 덧붙인다.**

    ⚠ 종전엔 매번 처음부터 다시 배정했다 — 문안이 늘 때마다 **다른 글자의 슬롯이 밀릴** 수 있었다.
    그리고 **갱신을 잊으면 새 글자가 본 글리프(한 행 높은 것)로 나간다**(2026-10-01 실측: 승리 문구의
    「승」만 1px 높았다 — 정본이 낡아 있었다).
    """
    have = load_low()
    chars = lowered_chars()
    taken = set(load().values()) | set(have.values())
    if os.path.exists(BOOK_PATH):
        with open(BOOK_PATH, encoding="utf-8") as f:
            taken |= set(json.load(f)["slots"])
    if os.path.exists(CRED_PATH):
        taken |= set(load_cred().values())
    rest = [i for i in sorted(free) if i not in taken]
    new = [c for c in chars if c not in have]
    if len(rest) < len(new):
        raise SystemExit(f"빈 슬롯이 모자란다: {len(rest)} < {len(new)}")
    table = dict(have)
    table.update(zip(new, rest[: len(new)], strict=True))
    keys = list(have) + new
    with open(LOW_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_doc": "0 행을 자르는 창 전용 글리프 배정(한 행 내려 그린 같은 글자). "
                "🔴 파생물이 아니라 정본이다 — 자세한 건 tools/hangul_map.py 의 LOW_PATH 주석",
                "chars": keys,
                "slots": [table[c] for c in keys],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(f"✅ 내려앉은 배정 {len(keys)}자(새로 {len(new)}: {''.join(new)}) → {LOW_PATH}")
    print(f"   남은 빈 슬롯 {len(rest) - len(new):,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true", help="배정을 정본으로 박는다")
    ap.add_argument(
        "--force",
        action="store_true",
        help="이미 있는 정본을 **바꿔** 박는다 — 옛 세이브·옛 빌드가 깨진다",
    )
    ap.add_argument("--freeze-low", action="store_true", help="자르는 창 전용 배정을 박는다")
    ap.add_argument("--freeze-book", action="store_true", help="책 화면 전용 배정을 박는다")
    ap.add_argument("--freeze-cred", action="store_true", help="크레딧 자막 전용 배정을 박는다")
    a = ap.parse_args()
    used = F.used_indices()
    free = F.free_slots(used)
    if a.freeze_low:
        return freeze_low(free)
    if a.freeze_book:
        return freeze_book(free)
    if a.freeze_cred:
        return freeze_cred(free)
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
    #   🔴 **세이브에 이 코드가 그대로 적힌다**(2026-09-06 실측 — 백업 RAM 에서 파티 이름과
    #     지명이 우리 배정으로 디코드됐다). 자리가 밀리면 **옛 세이브의 이름이 깨지고 옛
    #     빌드의 문안이 전부 딴 글자**가 된다. 그래서 이미 있는 정본을 바꾸려면 명시해야 한다.
    if os.path.exists(MAP_PATH) and load() != table and not a.force:
        moved = sum(1 for ch, i in load().items() if table.get(ch) != i)
        raise SystemExit(
            f"❌ 정본을 바꾸려 한다 — {moved:,}자가 딴 칸으로 간다.\n"
            "   세이브에 이 코드가 적히므로 **옛 세이브의 이름이 깨지고 옛 빌드의 문안이**\n"
            "   **전부 딴 글자가 된다.** 소재를 새로 열었더라도 배정은 그대로 두는 게 맞다\n"
            "   (빈 칸은 남아 있다). 정말 바꾸려면 `--freeze --force`."
        )
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
