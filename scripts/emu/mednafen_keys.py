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

배치 — 방향은 방향키, 손가락은 왼손 홈포지션에 모은다.
🔴 **자는 「실물 패드 배치를 최대한 그대로」다**(유저 확정 2026-09-07):

    PS1        w=△  a=□  s=✕  d=○      q=L1 e=R1 z=L2 c=R2   (다이아몬드를 wasd 에)
    SS · MD    q w e / a s d = X Y Z / A B C  (6버튼 패드 두 줄 그대로)
    SFC        q w   / a s   = Y X / B A      (다이아몬드를 45도 돌려 2×2 에)  어깨는 z c
    PCE        q w e / a s d = IV V VI / III II I  (Avenue Pad 6 두 줄 그대로)
                             ED1·ED2 는 2버튼이라 아랫줄 오른쪽 둘(s=II · d=I)만 쓴다

⚠ **확인 키는 기종마다 다르다.** 종전 주석은 「확인은 어느 기종에서나 s」라고 했는데
  **실물 배치를 따르면 그럴 수가 없다** — 새턴은 확인이 A(=`a`), MD 는 C(=`d`) 다.
  틀린 채로 두면 다음 사람이 그 문장을 믿고 새턴 배치를 「고치려」 든다.

    PS1 ✕ = s     SFC A = s     SS A = a     MD C = d     PCE I = d
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
    # 🔴 다이아몬드를 45도 돌려 2×2 에 얹는다 — Y 왼쪽 · X 위 · B 아래 · A 오른쪽이
    #    q Y / w X / a B / s A 로 간다(유저 정정 2026-09-07).
    #    ⚠ 종전엔 반대로 돌아가 `s=B`(취소)였다 — **이 파일이 스스로 적어 둔
    #      「확인은 어느 기종에서나 s」를 어기고 있었다.** SFC 확인은 A 다.
    "snes.input.port1.gamepad": {
        **DPAD,
        "y": "q",
        "x": "w",
        "b": "a",
        "a": "s",
        "l": "z",
        "r": "c",
    },
    # PCE 6버튼(Avenue Pad 6)은 아랫줄이 왼쪽부터 **III II I** 다 — 그대로 얹는다
    # (유저 정정 2026-09-07). 2버튼 게임은 아랫줄의 오른쪽 둘(s=II · d=I)만 쓴다.
    "pce.input.port1.gamepad": {
        **DPAD,
        "iii": "a",
        "ii": "s",
        "i": "d",
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
# 실행기 공통 단축키(유저 요청 2026-09-07 — mednafen · np2kai · DOSBox-X 가 같은 손가락):
#   ⌘R = 재시작 · F5 = 퀵세이브 · F7 = 퀵로드 · ` = 빨리감기 토글 · Tab = 빨리감기 홀드 ·
#   ⌥- / ⌥+ = 창 크기 한 단계씩 · ⌥1~4 = 단계를 바로 (1 매우 작음 … 4 큼).
#   ⌥M = 소리 끄기/켜기.
#   ⌘R 은 `&&` 조합(왼/오른 ⌘ 둘 다, `||`)이고 F10 도 그대로 살려 둔다 — 조합 문법은 이 머신의
#   mednafen 1.32 에 넣어 파싱되는 걸 확인했다. F5·F7 은 mednafen 기본값이라 명시만 한다.
SETTINGS = {
    "ffspeed": "8",
    "fftoggle": "1",
    "ffnosound": "0",
    "sfspeed": "8",
    "sftoggle": "0",
    "command.fast_forward": "keyboard 0x0 53",  # `
    "command.slow_forward": "keyboard 0x0 43",  # Tab
    "command.reset": "keyboard 0x0 21 && keyboard 0x0 227 || keyboard 0x0 21 && keyboard 0x0 231 || keyboard 0x0 67",  # ⌘R · F10
    "command.save_state": "keyboard 0x0 62",  # F5
    "command.load_state": "keyboard 0x0 64",  # F7
    # 창 크기 ⌥-(작게) · ⌥+(크게) — 1 매우 작음 · 2 작음(기본) · 3 보통 · 4 큼.
    # ⚠ 이 명령들은 **패치가 들어간 mednafen 에만** 있다(scripts/emu/mednafen-winsize.patch).
    #   스톡 mednafen 에는 창 크기 명령이 없어서, 패치 없이 이 설정만 넣으면 조용히 무시된다.
    # 🔴 **숫자(⌘1~4)는 안 쓴다**(유저 실측 2026-09-07) — mednafen 기본이 `1`~`9` 를 **세이브
    #   스테이트 슬롯 선택**에 물려 두어, ⌘를 같이 눌러도 **그쪽이 먼저 먹는다**(수정자를
    #   배타적으로 안 본다). `-`·`=` 는 슬롯 증감인데 **⌘와 함께면 안 겹친다.**
    #   스캔코드: `-`=45 · `=`=46, ⌘는 227(왼쪽)·231(오른쪽).
    # 🔴 **창 크기는 ⌥(Option)이다 — ⌘로는 원리상 안 된다**(유저 실측 2026-09-07).
    #   mednafen 이 아는 수정자는 **alt·shift·ctrl 셋뿐**이고 **⌘(GUI)는 아예 안 센다**
    #   (`keyboard.cpp:RecalcModsCache`). 그런데 매칭은 `TestButtonWithMods` 에서
    #   **마스크 완전 일치**다 — 수정자를 안 적은 기본 바인딩은 「마스크가 0일 때만」 먹는다.
    #   ⌘를 눌러도 마스크는 0 이라 **기본 `-`/`=`(세이브 슬롯 증감)가 같이 먹었다.**
    #   ⌥를 쓰면 마스크가 ALT 가 되어 기본 것이 안 먹고, 우리 것만 먹는다 — **양방향으로 배타적**이다.
    #   ⚠ 숫자(⌘1~4)가 안 됐던 것과 **같은 뿌리**다. 그때는 「⌘가 배타적이지 않다」로 적었는데
    #     정확히는 **⌘가 수정자로 세어지지 않는다**. `-`/`=` 로 옮겨도 안 풀린 이유가 그것이다.
    "command.scale_down": "keyboard 0x0 45+alt",
    "command.scale_up": "keyboard 0x0 46+alt",
    # ⌥1~4 = 단계를 바로 지정. ⌥면 숫자도 살아난다 — 기본 `1~9`(슬롯 선택)는 마스크가
    # 0 일 때만 먹으므로 안 겹친다. ⌥⇧1~4(입력 설정)와도 마스크가 달라 안 겹친다.
    # ⚠ **여기 적어야 한다** — 패치의 기본값이 같더라도, 예전 회차가 이 이름에 ⌘ 조합을
    #   써 놓은 설정 파일이 유저 머신에 남아 있다. 안 덮으면 옛 값이 그대로 산다.
    "command.scale_1": "keyboard 0x0 30+alt",
    "command.scale_2": "keyboard 0x0 31+alt",
    "command.scale_3": "keyboard 0x0 32+alt",
    "command.scale_4": "keyboard 0x0 33+alt",
    # ⌥M = 소리 끄기/켜기 (유저 요청 2026-09-07). mednafen 에 mute 명령이 없어 우리가
    # 더했다 — `sound.volume` 은 프레임마다 다시 읽히므로 설정만 바꾸면 끊김 없이 먹는다.
    "command.toggle_mute": "keyboard 0x0 16+alt",
    # 🔴 **소리를 100 으로 되돌린다.** mute 로 끈 채 종료하면 mednafen 이 cfg 에
    #   `sound.volume 0` 을 써 놓고, 다음에 띄우면 **소리가 안 나는데 이유를 모른다.**
    #   끈 상태는 그 회차에서만 살고, 띄울 때는 늘 소리가 나게 한다(유저 확정 ㉠).
    #   ⚠ 그래서 「중간 볼륨을 정해 두는」 것은 안 된다 — 볼륨 단계 키를 안 만든 이유이기도 하다.
    "sound.volume": "100",
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
