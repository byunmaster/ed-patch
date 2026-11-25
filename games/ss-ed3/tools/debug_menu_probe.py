"""디버그 메뉴 15항목을 하나씩 열어 **백업 RAM(세이브)이 바뀌나** 잰다 — 「세이브 훼손 위험」 목록의 근거(롬·세이브 파일 불변).

    sh scripts/capture.sh python3 games/ss-ed3/tools/debug_menu_probe.py <디스크2.cue> <백업RAM.bkr> <필드 상태> <출력폴더>

필드 상태 = 같은 롬으로 만든 세이브 7번 불러온 필드(`X+Y+Z` 가 먹는 자리). 항목마다 상태를 되돌리고 `X+Y+Z` → 항목 선택 → `c` 연타 700 프레임 → 백업 RAM 32KB 를 처음과 견준다.
`세이브 로드` 는 SAVE 를 골라 슬롯까지 눌러야 쓰기가 나므로 따로 한 번 더 돈다(`c` 다섯 번).
"""

import ctypes as C
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ss_headless as H

LABELS = [
    "파티 구성", "플래그 설정", "맵 설정", "MUSIC TEST", "타이틀", "엔딩", "세이브 로드", "debug",
    "책 읽기 시험", "룰렛", "블랙잭", "맵 선택", "이펙트", "엔딩(GRP)", "무비",
]  # fmt: skip


def bkr(h):
    p, n = h.core.retro_get_memory_data(0), h.core.retro_get_memory_size(0)
    return C.string_at(p, n)


def main():
    cue, bk, state, out = sys.argv[1:5]
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = H.Harness(core, cue, out, bkr=bk)
    h.load(state)
    h.run(5)
    base = h.snap()
    ref = bkr(h)
    print(f"백업 RAM {len(ref)}B", flush=True)
    for k, name in enumerate(LABELS):
        h.restore(base)
        h.run(2)
        h.press("x+y+z", 10, 90)
        if k < 8:
            for _ in range(k):
                h.press("down", 4, 12)
        else:
            h.press("right", 4, 12)
            for _ in range(k - 8):
                h.press("down", 4, 12)
        presses = 5 if name == "세이브 로드" else 1
        for _ in range(presses):
            h.press("c", 6, 140)
        for fr in range(560):
            h.held = {H.BTN["c"]} if (fr // 8) % 8 == 0 else set()
            h.run(1)
        h.held = set()
        now = bkr(h)
        diff = sum(1 for a, b in zip(ref, now, strict=True) if a != b)
        print(f"{k:2d} {name:10s} 백업 RAM 바뀐 바이트 {diff}", flush=True)
        h.shot(f"item_{k:02d}")


if __name__ == "__main__":
    main()
