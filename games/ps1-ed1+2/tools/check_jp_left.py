"""빌드 이미지에 일본어가 남았는지 센다 — 전투 화면 기준.

⚠ **한글은 SJIS 한자 슬롯을 빌려 쓴다**(`hangul_map`). 그래서 이미지를 그냥 SJIS 로 읽으면
우리 한글이 전부 한자로 보여 오탐이 쏟아진다(실측 1,832건). 슬롯 표로 먼저 되돌린 뒤에
남는 가나·한자만 일본어로 센다.

⚠ **널 구분으로 훑지 말 것.** 포인터 테이블의 주소 바이트가 우연히 SJIS 로 디코드돼
문자열처럼 잡힌다(실측 39건). 전투 코퍼스는 **코드 참조를 따라가는** `corpus_strings` 가
정본이다.

🔴 **이 파일은 전각 SJIS만 본다 — 반각 가타카나(JIS X 0201, `0xA1~0xDF`)는 원리상 못
본다**(2026-09-14, 마스터 QA 051 — HUD 지명이 반각으로만 있어 전각 검색 전부가 0건을
찍었다. `check_scn_jp_left.py`의 `check_mon_name_no_live_jp`엔 반각 축을 추가했지만,
**여기(ED.EXE 전용 구조 — `patch_items` 테이블·전투 코퍼스)는 아직 안 넓혔다** — 범위가
커서 이번 라운드엔 보류했다. **여기 초록불을 "전각+반각 다 깨끗하다"로 읽지 말 것.**

    python3 tools/check_jp_left.py            # 요약
    python3 tools/check_jp_left.py -v         # 남은 문자열까지
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
import patch_items as P
import patch_sys_ui as U
from common import BUILD_DIR, extract

IMG = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
ED_LBA, ED_SIZE = 257, 1021952
JA = re.compile(r"[぀-ゟ゠-ヿｦ-ﾟ一-鿿]")
_SLOT = {H.syllable_sjis(c): c for c in H.SYLLABLES}


def decode(b):
    """게임 텍스트 바이트 → 문자열(한글 슬롯 우선, 나머지는 SJIS)."""
    out, i = [], 0
    while i < len(b):
        if b[i] < 0x80:
            out.append(chr(b[i]))
            i += 1
            continue
        if i + 1 < len(b) and (b[i] << 8 | b[i + 1]) in _SLOT:
            out.append(_SLOT[b[i] << 8 | b[i + 1]])
            i += 2
            continue
        for n in (2, 1):
            try:
                out.append(bytes(b[i : i + n]).decode("shift_jis"))
                i += n
                break
            except (UnicodeDecodeError, IndexError):
                continue
        else:
            out.append("�")
            i += 1
    return "".join(out)


def _cstr(ed, off, limit=200):
    j = off
    while j < min(off + limit, len(ed)) and ed[j]:
        j += 1
    return decode(ed[off:j])


# 이름 테이블은 널 구분이 안전하다(포인터가 섞이지 않는 순수 문자열 블롭).
TABLES = [
    ("장비·도구", P.BLOB_EQ),
    ("마법", P.BLOB_MAGIC),
    ("아이템·마법(구 stride)", P.SEC),
    ("몬스터명", P.MONSTER),
    ("챕터 클리어", P.CHAPTER),
    ("격투장 상품", P.ARENA),
    ("전투 메시지", P.BTL_MSG),
    ("파티 접미", P.FRAG_TACHI),
    ("전투 조각", P.FRAG),
    ("이벤트 전투명", P.EVT),
]


def scan(verbose=False):
    ed = extract(ED_LBA, ED_SIZE, path=IMG)
    rows, total = [], 0

    # ── 전투 코퍼스 — 코드 참조 정본을 따라간다 ──────────────────────────────
    bad = []
    for fo, _end, _jp in P.corpus_strings(ed):
        s = _cstr(ed, fo)
        if JA.search(s):
            bad.append((fo, s))
    rows.append(("전투 코퍼스", len(list(P.corpus_strings(ed))), bad))

    # ── 이름·메시지 테이블 ───────────────────────────────────────────────────
    for name, (lo, hi) in TABLES:
        bad, n, i = [], 0, lo
        while i < hi:
            if not ed[i]:
                i += 1
                continue
            j = i
            while j < hi and ed[j]:
                j += 1
            n += 1
            s = decode(ed[i:j])
            if JA.search(s):
                bad.append((i, s))
            i = j
        rows.append((name, n, bad))

    # ── 시스템·전투 UI ───────────────────────────────────────────────────────
    bad, n = [], 0
    for src in (U.UI, U.HERO):
        for off in src:
            n += 1
            s = _cstr(ed, off, 40)
            if JA.search(s):
                bad.append((off, s))
    rows.append(("시스템·전투 UI", n, bad))

    for name, n, bad in rows:
        mark = "✅" if not bad else "⚠"
        print(f"  {mark} {name:<22} {n:>4}개 중 일본어 {len(bad)}")
        for off, s in bad[: (None if verbose else 5)]:
            print(f"        0x{off:06X} {s[:60]!r}")
        total += len(bad)
    print(f"\n{'✅ 전투 화면에 일본어 없음' if not total else f'⚠ 일본어 {total}건 남음'}")
    return total


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
