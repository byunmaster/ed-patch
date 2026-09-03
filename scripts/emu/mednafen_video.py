#!/usr/bin/env python3
"""mednafen 영상 출력을 **실기 규격**으로 되돌린다 (유저 확정 2026-09-02).

    python3 scripts/emu/mednafen_video.py            # 적용
    python3 scripts/emu/mednafen_video.py --check    # 지금 상태만 보여준다

`scripts/emu.sh` 가 mednafen 을 띄우기 직전에 `--quiet` 로 부른다 — `mednafen_keys.py` 와
같은 자리·같은 이유다(mednafen 은 종료할 때 cfg 를 다시 쓴다). 끄려면 `emu.sh --no-video`.
기전은 `mednafen_cfg.py`.

⚠ **mednafen 을 끄고 돌린다.** 켜 둔 채 고치면 종료할 때 옛 값으로 덮인다.

── 무엇을 「실기 규격」으로 보는가 ────────────────────────────────────────────
**TV 로 내보내던 그림 그대로**다 — 화면비 · 보이던 영역 · 지역. **CRT 흉내는 안 낸다**
(주사선·컴포지트 블렌드·goat 셰이더는 실기가 아니라 실기를 **찍은 사진**에 가깝고,
글리프·조판 검수에서는 오히려 방해가 된다).

    correct_aspect   1     4:3 로 바로잡는다. ⚠ SFC 는 **0 이었다** — 256×224 를 정사각
                           픽셀로 그려 8:7 로 홀쭉했다(2026-09-02 발견)
    h_overscan       1     좌우 오버스캔까지 보여 준다. ⚠ PCE 는 **0 이었다** — 실기에서
                           보이던 좌우가 잘려 있었다
    slstart/slend    전역  세로도 자르지 않는다(NTSC 240 · PAL 288/256)
    stretch          aspect 전체화면에서 화면비를 지키며 채운다. `aspect_mult2` 는 정수배로
                           묶느라 4:3 을 못 채우고 검은 띠가 남는다 — TV 는 그러지 않는다
    videoip          0     쌍선형 보간을 끈다. 실기 픽셀 그대로가 검수에 옳다
                           (전체화면에서 줄이 고르지 않으면 `x` 도 답이다 — 가로만 보간)
    scanlines/shader/special/tblur  전부 끈다 — 후처리는 실기에 없다
    region_default   jp    ⚠ 소장 원본이 일본판인 기종만(PS1·SS). PCE-ED1 은 미국판이다
    smpc.autortc.lang japanese  일본 새턴의 BIOS 언어. ⚠ **english 였다**

⚠ **PCE 의 slstart/slend 는 안 건드린다.** PS1·SS 는 NTSC 활성영역이 240줄로 고정이라
  「전역 = 0..239」가 곧 실기지만, PCE 는 VDC 가 세로 출력줄 수 자체를 프로그램한다 —
  0..239 로 열면 실기엔 없던 위아래 여백이 딸려 온다. mednafen 기본값(4..235)이 낫다.

⚠ **`video.driver` 는 안 건드린다.** 이 맥은 `softfb` 인데, 그건 OpenGL 이 이 OS 에서
  말썽이라 고른 값일 수 있다(같은 이유로 Geargrafx 가 아예 안 떴다 — `emu.sh` 머리말).
  실행기를 못 뜨게 만드는 설정은 「규격」보다 무겁다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mednafen_cfg  # noqa: E402

# 기종 무관 — 후처리를 얹지 않는다.
COMMON = {
    "videoip": "0",
    "scanlines": "0",
    "shader": "none",
    "special": "none",
    "tblur": "0",
    "stretch": "aspect",
}

MODULES = {
    "psx": {
        **COMMON,
        "correct_aspect": "1",
        "h_overscan": "1",
        "slstart": "0",
        "slend": "239",
        "slstartp": "0",
        "slendp": "287",
        "region_default": "jp",
    },
    "ss": {
        **COMMON,
        "correct_aspect": "1",
        "h_overscan": "1",
        "h_blend": "0",
        "slstart": "0",
        "slend": "239",
        "slstartp": "0",
        "slendp": "255",
        "region_default": "jp",
        "smpc.autortc.lang": "japanese",
    },
    # PCE 는 correct_aspect 설정이 없다 — mednafen 이 늘 바로잡는다. slstart/slend 는 위 ⚠.
    "pce": {**COMMON, "h_overscan": "1", "nospritelimit": "0"},
    "snes": {**COMMON, "correct_aspect": "1", "h_blend": "0"},
    "md": {**COMMON, "correct_aspect": "1"},
}


def settings(modules=None) -> dict:
    """「모듈.설정 → 값」으로 편다. `modules` 를 주면 그 기종만."""
    out = {}
    for mod in modules or MODULES:
        for name, value in MODULES[mod].items():
            out[f"{mod}.{name}"] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="바꾸지 않고 현재 값만 본다")
    ap.add_argument("--quiet", action="store_true", help="바뀐 게 있을 때만 말한다")
    ap.add_argument("module", nargs="*", choices=list(MODULES), help="이 기종만 (기본: 전부)")
    args = ap.parse_args()
    return mednafen_cfg.run(
        settings(args.module or None), label="영상 규격", check=args.check, quiet=args.quiet
    )


if __name__ == "__main__":
    raise SystemExit(main())
