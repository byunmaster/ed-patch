#!/usr/bin/env python3
"""**무변경 구간** — 우리가 안 여는 자리가 정말 그대로인가.

    python3 tools/check_immutable.py

## 왜 있나 — 2026-09-06 점검에서 **이 층이 없다는 게 드러났다**

PS1 은 `build.py:IMMUTABLE` 로 「여기는 절대 안 바뀐다」를 오프셋 구간으로 선언하고 최종
이미지를 원본과 byte 대조한다(루트 CLAUDE.md 「빌드 규율」 — 클리어 범위를 잘못 잡아 남의
자료를 지운 사고에서 나왔다). **새턴엔 그 층이 없었다** — 안 건드려야 할 자리를 건드려도
아무도 안 울었다.

🔴 **새턴은 파일 단위 재삽입이라 오프셋 구간을 흉내 내지 않는다**(유저·관리자 판단
2026-09-06). 대신 **파일 단위로 선언**한다 — 재삽입기가 여는 파일의 **여집합**이 곧
무변경 구간이다. 덤으로 파일 밖의 둘(시스템 영역 · 오디오)을 따로 본다.

⚠ **LBA 는 바뀐다.** `relocate_files` 가 씬 파일을 뒤로 밀어 137개의 자리가 옮겨진다.
  그래서 판정은 이미지 오프셋이 아니라 **파일 내용의 sha1** 이다.

## 무엇을 보나

1. **우리가 안 여는 파일** — 내용 sha1 이 원본과 같아야 한다. 하나라도 다르면 실패.
2. **오디오 영역** — 트랙 02 시작(`AUDIO_LBA`) 이후 전부. 448MB 가 byte 동일해야 한다.
   ⚠ 여기가 바뀌면 **TOC 가 유지돼도 소리가 깨진다.**
3. **시스템 영역**(섹터 0~15) — 새턴 부트 헤더. GameID 가 여기 있어 **세이브 이름이 걸린다.**
4. ℹ **선언했는데 안 바뀐 파일** — 실패는 아니지만, 선언이 낡았다는 뜻이라 보고한다.
"""

import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

# 🔴 **우리가 여는 파일** — 이 목록 밖은 전부 무변경 구간이다. 늘릴 때는 **왜 여는지**를 적는다.
OPENED = [
    (r"^/BIN/ED[12]SCN\d+\.BIN$", "씬 대사 (patch_scn)"),
    (r"^/BIN/ED2MON\d+\.BIN$", "ED2 몬스터 이름·전투 문구 (patch_mon_names)"),
    (r"^/ED2?\.BIN$", "본체 둘 — 시스템 문구·UI 표·조사 훅·회심 복사"),
    (r"^/TITLE\.BIN$", "오프닝·엔딩 자막 (patch_title)"),
    (r"^/(11)?(KANJI|ASCII)\.FON$", "본편 폰트 — 한글 글리프를 굽는다 (patch_ui)"),
    (r"^/OPENEND/KANJI\.FON$", "오프닝·엔딩 폰트 사본 (patch_title)"),
    (r"^/(FRAME|STAT)\.DAT$", "HUD 스프라이트 시트 (patch_gfx_hud)"),
    (r"^/START/MENU[12]\.DAT$", "시작 화면 버튼 (patch_gfx_menu)"),
    (r"^/SCR[12]\.2D$", "타이틀 그림 (patch_gfx_title)"),
    (r"^/OPENEND/ED_STA\d\.DG2$", "챕터 판 (patch_gfx_cards)"),
]
# ⚠ **패턴을 넓게 잡지 않는다.** 처음엔 `\.FON$`·`\.2D$` 로 뭉뚱그렸다가 「선언했는데 안
#   바뀐 파일」이 186 이 됐다 — 그만큼 **무변경 구간에서 빠져 나가** 게이트가 무뎌진다.
#   좁히자 그 수가 0 이 된다. 새 파일을 열면 여기 한 줄을 더한다.

AUDIO_LBA = 15607  # 트랙 02 INDEX 01 = 03:28:07 → (3*60+28)*75+7
SYS_SECTORS = 16  # 새턴 부트 헤더 — GameID 가 여기 있다(세이브 이름이 걸린다)


def opened(name):
    return any(re.search(p, name) for p, _why in OPENED)


def _h(b):
    return hashlib.sha1(b).hexdigest()


def check():
    """`(선언 밖인데 바뀐 파일, 선언했는데 안 바뀐 파일, 영역 결과)`."""
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    f1, m1 = common.open_image()
    f2, m2 = common.open_image(dst)
    try:
        a = {n: (l, s) for n, l, s in common.iso_files(m1)}
        b = {n: (l, s) for n, l, s in common.iso_files(m2)}
        bad, idle, kept, wrote = [], [], 0, 0
        for n in sorted(a):
            if n not in b:
                bad.append((n, "빌드에서 사라졌다"))
                continue
            same = _h(common.read_extent(m1, *a[n])) == _h(common.read_extent(m2, *b[n]))
            if opened(n):
                wrote += 1
                if same:
                    idle.append(n)
            elif same:
                kept += 1
            else:
                bad.append((n, "선언 밖인데 바뀌었다"))
        for n in sorted(set(b) - set(a)):
            bad.append((n, "빌드에만 있다"))
        aud = AUDIO_LBA * common.SECTOR if hasattr(common, "SECTOR") else AUDIO_LBA * 2352
        area = [
            ("이미지 크기", len(m1) == len(m2), f"{len(m1):,}B"),
            ("오디오 영역", _h(m1[aud:]) == _h(m2[aud:]), f"{(len(m1) - aud) / 1e6:.0f}MB"),
            (
                "시스템 영역(섹터 0~15)",
                m1[: SYS_SECTORS * 2352] == m2[: SYS_SECTORS * 2352],
                "GameID 포함",
            ),
        ]
        return bad, idle, area, (len(a), kept, wrote)
    finally:
        f1.close()
        f2.close()


def main():
    bad, idle, area, (total, kept, wrote) = check()
    for name, ok, note in area:
        print(f"     {'✅' if ok else '❌'} {name} — {note}")
    print(
        f"     {'❌' if bad else '✅'} 무변경 파일 {kept:,} (전체 {total:,} 중 우리가 여는 "
        f"{wrote}) — 선언 밖에서 바뀐 파일 {len(bad)}"
    )
    for n, why in bad[:20]:
        print(f"        🔴 {n} — {why}")
    if idle:
        print(
            f"     ℹ 선언했는데 안 바뀐 파일 {len(idle)} — {' · '.join(idle[:6])}"
            " (선언이 낡았을 수 있다)"
        )
    if bad or not all(ok for _n, ok, _t in area):
        raise SystemExit("무변경 구간이 흔들렸다 — 우리가 안 여는 자리가 바뀌었다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
