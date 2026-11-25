"""글리프 읽기 감시(`glyph_guard`) 긴 구간 — 새 게임 오프닝~초반 · 시스템 메뉴 · 이자벨 전투~엔딩 크레딧.

    sh scripts/capture.sh python3 games/ss-ed3/tools/guard_run.py <시나리오> <이미지.cue> <출력폴더> [--ranges 6636-7115,7231-7804,7807-7808] [--frames N]

시나리오: `newgame`(디스크 1 — 타이틀 → New Game → 확인 연타) · `menus`(New Game 뒤 시스템 메뉴 화면을 돌며 ·) · `ending`(디스크 2 세이브 7번 → 이자벨 전투 → 엔딩까지 확인 연타).
감시 구간을 글자 그리기가 한 번이라도 읽으면(`hits` > 0) 또는 구간 바이트가 바뀌면 실패(rc 1). 2천 프레임마다 로그와 화면 일부를 남긴다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glyph_guard as G
import ss_headless as H

CUE_BKR = "/root/save/ss-ed3/Shiroki Majo (KR) (Disc 2) - before_isabel.bkr"


def mash(h, n, step=2000, log=None, shots=None, every=20000, writes=True):
    for fr in range(n):
        h.held = {H.BTN["c"]} if (fr // 8) % 8 == 0 else set()
        h.run(1)
        if fr % step == 0:
            hit = G.hits(h)
            print(f"  frame {fr} hits {hit[0]} unchanged {G.unchanged(h)}", flush=True)
            if hit[0] or (writes and not G.unchanged(h)):
                return False
        if shots and fr % every == 0:
            h.shot(f"{shots}_{fr:07d}")
    return True


def boot_to_title(h):
    h.press("start", 10, 300)
    h.press("start", 10, 300)
    h.run(2205)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("cue")
    ap.add_argument("out")
    ap.add_argument("--ranges", default="6636-7115,7231-7804,7807-7808")
    ap.add_argument("--frames", type=int, default=30000)
    ap.add_argument(
        "--hits-only",
        action="store_true",
        help="쓰기 감시를 끈다 — 코드 예약 칸에 코드가 앉은 빌드(변수가 쓰인다)",
    )
    ap.add_argument("--shot-every", type=int, default=20000)
    a = ap.parse_args()
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    bkr = CUE_BKR if a.scenario == "ending" else None
    h = H.Harness(core, a.cue, a.out, bkr=bkr)
    ok = True
    if a.scenario in ("newgame", "menus"):
        boot_to_title(h)
        G.install(h, G.parse(a.ranges))  # 본체가 올라온 뒤에 얹는다(부팅 직후엔 코드가 아직 없다)
        h.press("start", 10, 120)
        ok = mash(h, a.frames, shots="newgame", every=a.shot_every, writes=not a.hits_only)
        if ok and a.scenario == "menus":
            # 시스템 메뉴(B) → 화면을 돌며 확인·취소 — 항목 이름 목록 · 상태 · 장비 · 도구 등
            for k in range(60):
                h.press("b", 6, 60)
                for d in ("down", "right", "down", "left", "up"):
                    h.press(d, 4, 20)
                    h.press("c", 6, 40)
                    h.press("a", 6, 40)
                h.shot(f"menu_{k:02d}")
                hit = G.hits(h)
                print(f"  menu round {k} hits {hit[0]} unchanged {G.unchanged(h)}", flush=True)
                if hit[0] or (not a.hits_only and not G.unchanged(h)):
                    ok = False
                    break
    elif a.scenario == "ending":
        boot_to_title(h)
        G.install(h, G.parse(a.ranges))
        h.press("start", 10, 120)
        h.press("c", 10, 120)
        h.press("c", 10, 120)
        for _ in range(6):
            h.press("down", 6, 10)
        h.press("c", 10, 300)
        h.press("c", 10, 300)
        h.held = {H.BTN["up"]}
        h.run(400)
        h.held = set()
        ok = mash(h, a.frames, shots="ending", every=a.shot_every, writes=not a.hits_only)
    else:
        raise SystemExit(f"시나리오를 모른다: {a.scenario}")
    n, last = G.hits(h)
    print(
        f"최종: hits={n} last={last:#x} unchanged={G.unchanged(h)} → {'통과' if ok and n == 0 else '실패'}"
    )
    raise SystemExit(0 if ok and n == 0 else 1)


if __name__ == "__main__":
    main()
