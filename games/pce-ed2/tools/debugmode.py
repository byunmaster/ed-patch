"""디버그 빌드 — 원판에 숨어 있는 개발자 디버그 메뉴(WARP·LVL·GOLD·ITEM·MAGIC·PATH·ENTRY·MASK·ENCNT·SPOT·ABC·VISUAL)를 연다.

시험 빌드 전용이다 — `ED_DEBUG=1` **이고** 꼬리표가 `test-` 로 시작할 때만 켜지고(그렇지 않으면 BuildError), 제품 롬은 바이트 하나도 안 바뀐다.
분석은 `docs/debug-mode.md`. 세 곳만 고친다(본 프로그램 rel 130 = 뱅크 0x68~):
① 뱅크 0x68 `$41E4` `BBR7 $20,$41E9`(개발기 RAM 이 있을 때만 `$86` bit7 을 세운다) → NOP 3개 — 게이트(`$86` bit7)가 늘 선다.
② 뱅크 0x6A `$60AD` `BBR7 $86,$609B`(메뉴 입구의 게이트 검사) → NOP 3개 — ①만으로는 부팅 뒤 어딘가가 `$86` bit7 을 다시 지운다(실측: 부팅 직후 `$86`=0xBB 였다가 필드에서 0x3B).
③ 뱅크 0x6A `$609E` `TST #$04,$26E5`(SELECT, 그 프레임에 새로 눌림) → `TST #$02,$2228`(II, 누르는 중 — 두 버튼을 같이 눌러도 열린다) — RUN+SELECT 를 30프레임 누르면 게임이 소프트 리셋하는 함정(`$4159~`)을 피한다.
열기: 필드에서 RUN 과 II 를 같이 누른다(emucap: tap buttons [run, ii] press_frames 10).
"""

import os

import common

BANK0, BANK = 0x68, 8192
GATE = (
    (0x68, 0x1E4),
    bytes.fromhex("7f2002"),
    bytes.fromhex("eaeaea"),
    "디버그 — 개발기 게이트 해제(BBR7 $20 → NOP×3)",
)
GATE2 = (
    (0x6A, 0x0AD),
    bytes.fromhex("7f86eb"),
    bytes.fromhex("eaeaea"),
    "디버그 — 메뉴 입구의 게이트 검사 해제(BBR7 $86 → NOP×3)",
)
KEY = (
    (0x6A, 0x09F),
    bytes.fromhex("04e526"),
    bytes.fromhex("022822"),
    "디버그 — 메뉴 키 SELECT(눌림 `$26E5` bit2) → II(누르는 중 `$2228` bit1)",
)


def enabled() -> bool:
    """꼬리표 `debug`(마스터용 — 인게임 QA 도구, 파일서버 목록에 보인다)는 항상 켠다. 그 밖엔 `ED_DEBUG=1` + 꼬리표 `test-` 로 시작할 때만(제품 롬엔 안 들어간다)."""
    if common.BUILD_TAG == "debug":
        return True
    if os.environ.get("ED_DEBUG") != "1":
        return False
    if not common.BUILD_TAG.startswith("test-"):
        raise SystemExit(
            "ED_DEBUG=1 은 꼬리표가 test- 로 시작하는 시험 빌드에서만 쓴다(ED_BUILD_TAG=test-debug) — 마스터용은 꼬리표 debug"
        )
    return True


def apply(w) -> None:
    for (bank, off), orig, new, label in (GATE, GATE2, KEY):
        lin = 130 * common.USER + (bank - BANK0) * BANK + off
        w.put(lin, new, orig, label)
    print("  ⚠ 디버그 빌드 — 개발기 게이트 해제 · 메뉴 키 = RUN + II (제품 롬엔 없다)")
