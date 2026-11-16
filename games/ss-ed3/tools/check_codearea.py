"""코드 예약 칸(`codearea.py`)이 지켜지나 — 우리 스텁·표가 사는 폰트 RAM 칸에 글리프가 앉지 않았나, 메뉴 구역은 원판 그대로인가.

🔴 **조용히 틀리는 「빈 자리」 판정을 막는다**(이 레포에서 0 런이 실은 사운드 뱅크 안이었던 사고 — pce-ed2 `GAME_SCRATCH` 와 같은 장치).

  1. 글리프 배정 정본 넷(`hangul_map` · `lowered_map` · `book_map` · `credits_map`)이 예약 칸에 앉지 않았다 — 앉으면 그 글자가 우리 코드 바이트로 읽힌다.
  2. 원판 문안이 쓰는 글리프(`font.used_indices`)가 예약 칸에 없다 — 있으면 남은 일본어 글자가 코드로 그려진다.
  3. 빌드가 폰트에 얹은 코드는 전부 예약 칸 안이고 서로 겹치지 않는다(`codearea.apply` 의 단언) — 그리고 **폰트 이미지 안 그 바이트가 그대로다.**
  4. 디버그 메뉴 구역(`/0.BIN` `0x06016420~0x06019200`)이 **원판 바이트 그대로다** — 우리 코드가 그 자리를 다시 차지하면 메뉴가 조용히 깨진다.
     예외는 문자열 덤프(`sys_jp/0.json`)에 든 문자열 자리뿐이다(라벨 번역). 문자열 구역 `0x06016080~0x06016420` 은 이 검사 밖이다.

    python3 games/ss-ed3/tools/check_codearea.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import codearea as CA
import common as C
import font as F

BASE = 0x06004000
MENU = (0x06016420, 0x06019200)  # 메뉴 본체·처리기 — 원판 그대로여야 한다
MAPS = ("hangul_map.json", "lowered_map.json", "book_map.json", "credits_map.json", "liga_map.json")


def allowed_spans(b0):
    """번역으로 바뀌어도 되는 자리 — `/0.BIN` 문자열 덤프(`sys_jp/0.json`)의 문자열마다 `[시작, 종결 NUL 까지)`."""
    with open(os.path.join(C.OUT_DIR, "sys_jp", "0.json"), encoding="utf-8") as f:
        doc = json.load(f)
    spans = []
    for st in doc["strings"]:
        a = st["off"]
        z = b0.find(b"\x00", a)
        spans.append((a, z + 1 if z >= 0 else a))
    return spans


def main():
    bad = []
    maps = []
    for f in MAPS:
        p = os.path.join(C.GAME_DIR, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                maps.append((f, json.load(fh)["slots"]))
    bad += CA.check_reserved(*maps)
    hit = sorted(CA.RESERVED_SLOTS & F.used_indices())
    if hit:
        bad.append(f"원판 문안이 쓰는 글리프가 예약 칸에 있다 {len(hit)}개 (예 {hit[:3]})")
    n_side = 0
    for disc in C.DISCS:
        fon = None
        b0_new = b0_old = None
        for name, _lba, _size, old, new, _cnt in build.patched(disc):
            if name == "/SYSTEM/KANJI12.FON":
                fon = new
            elif name == "/0.BIN":
                b0_old, b0_new = old, new
        if fon is None or b0_new is None:
            bad.append(f"disc{disc}: 폰트나 /0.BIN 이 patched() 에 없다")
            continue
        n_side = len(CA.SIDE)
        for addr, blob in CA.SIDE:
            off = addr - CA.FON_BASE
            if fon[off : off + len(blob)] != blob:
                bad.append(f"disc{disc}: 폰트 이미지의 {addr:#x} 가 쓴 코드와 다르다")
        lo, hi = MENU
        ok = allowed_spans(b0_old)
        diff = [
            i
            for i in range(lo - BASE, hi - BASE)
            if b0_old[i] != b0_new[i] and not any(a <= i < b for a, b in ok)
        ]
        if diff:
            bad.append(
                f"disc{disc}: 디버그 메뉴 구역이 원판과 다르다 {len(diff)}B (처음 {BASE + diff[0]:#x}) — 번역된 문자열 밖이다"
            )
    if bad:
        print("  ❌ 코드 예약 칸")
        for b in bad:
            print(f"     {b}")
        return 1
    print(
        f"  코드 예약 칸 — 글리프 배정 {len(maps)}종·원판 사용 글리프와 겹침 0 · 폰트에 얹은 코드 {n_side}조각 전부 예약 안 · 메뉴 구역 원판 그대로"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
