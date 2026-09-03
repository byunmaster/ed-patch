#!/usr/bin/env python3
"""mednafen 키 배치를 정본대로 되돌린다 (유저 확정 2026-08-21).

    python3 scripts/emu/mednafen_keys.py            # 적용
    python3 scripts/emu/mednafen_keys.py --check    # 지금 상태만 보여준다

`scripts/emu.sh` 가 mednafen 을 띄우기 직전에 `--quiet` 로 부른다 — 덮여도 다음 실행에
되돌아온다. 끄려면 `emu.sh --no-keys`. 기전(cfg 되돌리기)은 `mednafen_cfg.py` — 영상 규격을
맞추는 `mednafen_video.py` 와 같은 것을 쓴다.

왜 스크립트인가 — mednafen 은 **종료할 때 cfg 를 다시 쓰고**, 게임 안 입력설정
(Alt+Shift+1)을 한 번 돌리면 그 기종 배치가 통째로 덮인다. 61개를 손으로 다시 넣는 건
못 할 짓이라 판단(배치)을 커밋되는 파일에 둔다 — 레포 원칙 그대로다.

⚠ **mednafen 을 끄고 돌린다.** 켜 둔 채 고치면 종료할 때 옛 값으로 덮인다.

배치 — 방향은 방향키, 손가락은 왼손 홈포지션에 모은다:

    PS1        w=△  a=□  s=✕  d=○      q=L1 e=R1 z=L2 c=R2
    SS · MD    q w e / a s d = 윗줄·아랫줄 그대로 (6버튼 패드의 물리 배치)
    SFC        q w   / a s   = X A / Y B          어깨는 z c
    PCE        a s           = II I  (2버튼이다 — ED1·ED2 도 둘만 쓴다)
                             6버튼 패드(III~VI)는 남는 자리에 얹어만 둔다

⚠ 확인(✕·B·I)은 어느 기종에서나 **s** 다. 기종을 오가며 QA 할 때 손이 안 헷갈리는 게
  물리 배치 재현보다 중요하다고 봤다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mednafen_cfg  # noqa: E402

# SDL 스캔코드
KEY = {
    "q": 20,
    "w": 26,
    "e": 8,
    "a": 4,
    "s": 22,
    "d": 7,
    "z": 29,
    "c": 6,
    "↑": 82,
    "↓": 81,
    "←": 80,
    "→": 79,
    "shift": 225,
    "tab": 43,
}

DPAD = {"up": "↑", "down": "↓", "left": "←", "right": "→"}

LAYOUT = {
    "psx.input.port1.gamepad": {
        **DPAD,
        "triangle": "w",
        "square": "a",
        "cross": "s",
        "circle": "d",
        "l1": "q",
        "r1": "e",
        "l2": "z",
        "r2": "c",
    },
    "ss.input.port1.gamepad": {
        **DPAD,
        "x": "q",
        "y": "w",
        "z": "e",
        "a": "a",
        "b": "s",
        "c": "d",
        "ls": "z",
        "rs": "c",
    },
    "md.input.port1.gamepad6": {**DPAD, "x": "q", "y": "w", "z": "e", "a": "a", "b": "s", "c": "d"},
    "md.input.port1.gamepad": {**DPAD, "a": "a", "b": "s", "c": "d"},
    "snes.input.port1.gamepad": {
        **DPAD,
        "x": "q",
        "a": "w",
        "y": "a",
        "b": "s",
        "l": "z",
        "r": "c",
    },
    "pce.input.port1.gamepad": {
        **DPAD,
        "ii": "a",
        "i": "s",
        "iii": "d",
        "iv": "q",
        "v": "w",
        "vi": "e",
    },
}

# ⚠ Select 를 **Tab 에서 뺀다** — Tab 은 빨리감기 홀드가 가져갔다(아래 SETTINGS). 겹쳐 두면
#   빨리감기를 누를 때마다 Select 가 같이 들어간다. 왼손 새끼로 닿는 왼쪽 Shift 로 옮긴다.
#   (새턴 패드엔 select 가 없어 대상이 아니다.)
for _sys in ("psx", "snes", "pce"):
    LAYOUT[f"{_sys}.input.port1.gamepad"]["select"] = "shift"

# 빨리감기 — **키마다 다르게** 준다(유저 확정 2026-08-22).
#   `   = 토글 : `fast_forward`. `fftoggle` 이 전역이라 이 명령은 토글 전용이 된다.
#   Tab = 홀드 : `slow_forward` 를 **빨리감기로 전용**한다. 자기 배속(sfspeed)·자기 토글
#                (sftoggle)을 따로 갖는 유일한 명령이라, 한 키는 토글 한 키는 홀드가 된다.
#                ⚠ 이름은 「slow」인데 8배속인 게 이상해 보이지만 sfspeed 는 그냥 승수다 —
#                  8 을 넣어도 클램프도 경고도 없다(2026-08-22 실측).
#   DOSBox 쪽은 Tab 홀드만 있다(staging 의 speedlock 은 홀드 전용이고 토글 설정이 없다).
SETTINGS = {
    "ffspeed": "8",
    "fftoggle": "1",
    "ffnosound": "0",
    "sfspeed": "8",
    "sftoggle": "0",
    "command.fast_forward": "keyboard 0x0 53",  # `
    "command.slow_forward": "keyboard 0x0 43",  # Tab
}


def settings() -> dict:
    """「이름 → 값」한 벌로 편다. 배치는 위 LAYOUT·SETTINGS 가 정본이다."""
    out = dict(SETTINGS)
    for prefix, buttons in LAYOUT.items():
        for btn, key in buttons.items():
            out[f"{prefix}.{btn}"] = f"keyboard 0x0 {KEY[key]}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="바꾸지 않고 현재 값만 본다")
    ap.add_argument("--quiet", action="store_true", help="바뀐 게 있을 때만 말한다")
    args = ap.parse_args()
    return mednafen_cfg.run(settings(), label="키 배치", check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
