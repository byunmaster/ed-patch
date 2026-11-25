"""음성 자막 스텁이 도는지 — 새 게임부터 확인 연타로 가다가 자막 창 깃발(`subtitle_stub` 변수 표 `flag`)이 서는 순간마다 화면을 남긴다.

    sh scripts/capture.sh python3 games/ss-ed3/tools/voice_probe.py <디스크1.cue> <출력폴더> [--frames 150000] [--max 12]

스텁 위치가 바뀌는 변경(코드 예약 칸 이전 등) 뒤에 「음성 자막이 아직 뜨는가」를 장면 하나라도 눈으로 보려는 회귀 도구다. 상태·RAM 쓰기 없음.
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ss_headless as H
import subtitle_stub as SS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cue")
    ap.add_argument("out")
    ap.add_argument("--frames", type=int, default=150000)
    ap.add_argument("--max", type=int, default=12)
    a = ap.parse_args()
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = H.Harness(core, a.cue, a.out)
    flag = SS.build()[2]["flag"]
    h.press("start", 10, 300)
    h.press("start", 10, 300)
    h.run(2205)
    h.press("start", 10, 120)
    last, got = -9999, 0
    for fr in range(a.frames):
        h.held = {H.BTN["c"]} if (fr // 8) % 8 == 0 else set()
        h.run(1)
        if fr % 20 == 0 and struct.unpack(">H", h.peek(flag, 2))[0] and fr - last > 600:
            h.shot(f"voice_{got:02d}_{fr:07d}")
            print(f"  자막 창 켜짐 @ {fr}", flush=True)
            last, got = fr, got + 1
            if got >= a.max:
                break
        if fr % 10000 == 0:
            h.shot(f"progress_{fr:07d}")
            print(f"  frame {fr}", flush=True)
    print(f"끝: 자막 창 {got} 번")


if __name__ == "__main__":
    main()
