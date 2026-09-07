#!/usr/bin/env python3
"""🔧 **화면 QA 하네스** — 세이브를 이식해 헤드리스로 띄우고, 키를 넣고, 찍는다.

공통 확인 눈금 스물둘(`docs/ed1-phases.md`) 중 **주황(`🔧`) 칸을 기계가 대신 본다.**
실측(2026-09-08): 열일곱 중 **열둘**이 여기로 넘어오고, 남는 다섯은 전부 전투다.

🔴 **DOSBox-X 는 「그리기」에만 믿는다 — 거동 판정에 쓰지 않는다.**
   2026-09-07 에 그 자리에서 오진했다: 원판이 np2kai 에서는 멀쩡히 싸우는데
   DOSBox-X 에서는 전투가 안 돌아서, 그걸 「원본에서도 재현된다」로 읽고 사흘치 계획을
   그 위에 세웠다. ⇒ **문자·정렬·빈칸은 여기서 보고, 「멈추나·뻗나」는 np2kai(유저)만**이
   판정한다. 하네스가 편해질수록 거동까지 여기서 보고 싶어진다 — 그때 이 줄을 읽어라.

🔴 **찍는 것은 기계지만 판정하는 것은 사람이다.** 정본과 대조되는 축(표기·조사·정렬·빈칸)은
   내가 화면을 보고 닫을 수 있다. 「보기 좋은가」는 못 한다 — 그건 유저 몫으로 남는다.

## 어떻게 도는가

    ⑴ 빌드 칸의 `program.d88` · `scenario.d88` 을 **짧은 경로**로 복사한다
       (DOSBox-X 는 긴 경로를 못 연다 — 실측)
    ⑵ 세이브 원본 디스크에서 **세이브 구역만** 떼어 그 사본에 얹는다
       (`SAVE_LO`~`SAVE_HI` = 논리 0~127 한 덩이. `scripts/emu/pc98.sh` 와 같은 규격)
    ⑶ Xvfb + dosbox-x(`machine=pc98`)로 띄운다 — conf 는 `scripts/emu/pc98.sh` 의
       템플릿에서 **화면 QA 에 필요한 것만** 추린 것이다
    ⑷ 대본대로 `xdotool` 로 키를 넣고 `import` 로 찍는다

⚠ **`--program` 부팅은 이어하기 전용**이다(공용 실행기 머리말). 세이브가 없으면 LOAD 가
   안 먹고 화면만 깜빡인다 — 그래서 ⑵ 가 먼저다.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# 세이브 구역 — d88 파일 오프셋. 논리 0~127 이 한 덩이로 붙어 있다(2026-09-07 두 번 정정).
SAVE_LO, SAVE_HI = 0x0002B0, 0x00020AB0
SAVE_SRC = Path("/root/save") / common.GAME  # 유저가 맥에서 올려 준 시나리오 디스크


def _run_dir() -> Path:
    """실행 사본을 둘 자리.

    🔴 **짧은 경로여야 한다** — 워크트리 경로(`.claude/worktrees/…`)로는 DOSBox-X 가
       이미지를 못 연다(실측).
    🔴 그리고 **쓸 수 있는 자리**여야 한다. `imgmount` 는 이미지를 **읽기·쓰기로** 연다 —
       샌드박스가 그 경로의 쓰기를 막으면 `Unable to open 'program.d88'` 로 죽는데,
       화면엔 그 한 줄만 뜨고 **경로가 틀린 것과 구분이 안 된다**(2026-09-08, 한 시간
       태웠다). 같은 파일을 다른 자리로 복사해 띄워 보면 그 자리에서 갈린다.
    """
    if v := os.environ.get("PC98_QA_DIR"):
        return Path(v)
    if job := os.environ.get("CLAUDE_JOB_DIR"):
        return Path(job) / "tmp" / "pc98-qa"
    return Path.home() / ".cache" / "pc98-qa"


RUN = _run_dir()


def _main_tree() -> Path:
    """🔴 캡처는 **메인 트리**의 `.local/inbox/<게임>/` 에 둔다 — 유저가 거기를 본다.
    워크트리 안에 떨어뜨리면 유저 화면에 안 나온다(관리자 지적 2026-09-08)."""
    import subprocess

    g = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
        cwd=common.ROOT,
    ).stdout.strip()
    return Path(g).parent if g else common.ROOT


SHOT_DIR = _main_tree() / ".local" / "inbox" / common.GAME

CONF = """[sdl]
output=surface
windowresolution=640x400
autolock=false
[dosbox]
machine=pc98
memsize=14
hostkey=ctrlalt
[cpu]
core=normal
cputype=386
cycles=fixed 8000
# `--turbo` 가 여기를 true 로 바꾼다 — 오프닝이 5분이라 새 게임 회차엔 필수다
turbo=@TURBO@
[render]
aspect=false
[keyboard]
controllertype=pc98
[autoexec]
"""


def has_save(disk: Path) -> bool:
    """세이브가 든 디스크인가 — 슬롯 표의 사용 칸 수가 0이 아니면 있다.

    ⚠ 「세이브 구역이 `0xFF` 가 아니다」로는 못 잰다 — 구역 전체가 처음부터 채워져 있다
      (실측: 여섯 장 다 128/128 이었다). 갈리는 건 슬롯 표 머리의 한 바이트다.
    """
    return disk.read_bytes()[SAVE_LO + 0x12] != 0


def pick_save() -> Path:
    cands = [p for p in sorted(SAVE_SRC.glob("*.d88")) if has_save(p)]
    if not cands:
        raise SystemExit(
            f"🔴 세이브가 든 디스크가 없다: {SAVE_SRC}\n  유저가 한 판 저장해 올려야 한다."
        )
    return max(cands, key=lambda p: p.stat().st_mtime)


def disks(tag: str) -> tuple[Path, Path, Path]:
    """`--build orig` 이면 **원본**을 쓴다 — 「우리 개입이 원인인가」를 가르는 대조군이다
    (`consult-skill-references` 의 그 축: 개입 결과가 이상하면 원본에 같은 개입으로 가른다)."""
    if tag == "orig":
        o = common.ORIG_DIR
        return (
            o / common.DISKS["program"][0],
            o / common.DISKS["scenario"][0],
            o / common.DISKS["event"][0],
        )
    src = common.GAME_DIR / "work" / "build" / tag
    return src / "program.d88", src / "scenario.d88", src / "event.d88"


def prepare(tag: str, save: Path, turbo: bool) -> Path:
    prog, scen, ev = disks(tag)
    for f in (prog, scen, ev):
        if not f.exists():
            raise SystemExit(f"🔴 디스크가 없다: {f}")
    RUN.mkdir(parents=True, exist_ok=True)
    shutil.copy2(prog, RUN / "program.d88")
    shutil.copy2(ev, RUN / "event.d88")
    blob = bytearray(scen.read_bytes())
    blob[SAVE_LO:SAVE_HI] = save.read_bytes()[SAVE_LO:SAVE_HI]
    (RUN / "scenario.d88").write_bytes(bytes(blob))
    (RUN / "pc98.conf").write_text(
        CONF.replace("@TURBO@", "true" if turbo else "false"), encoding="utf-8"
    )
    return RUN


def x(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default=common.BUILD_TAG, help="빌드 칸 이름")
    ap.add_argument("--save", help="세이브를 떼어 올 디스크(기본: /root/save 의 최신)")
    ap.add_argument("--display", default=":97")
    ap.add_argument(
        "--script",
        default="wait:22 shot:boot",
        help="대본 — `wait:N`(초) · `key:X` · `hold:X@초` · `swap`(디스크 교체) · `click:x,y` · `type:문자열` · `shot:이름`",
    )
    ap.add_argument(
        "--boot",
        default="program",
        choices=("program", "event"),
        help="event = **새 게임**(오프닝 ~5분, 뒤에 디스크 교체가 필요하다). "
        "드라이브 1에 두 장을 함께 물려 `swap` 으로 갈아 끼운다",
    )
    ap.add_argument("--turbo", action="store_true", help="오프닝을 빨리 감는다(새 게임 회차)")
    ap.add_argument("--keep", action="store_true", help="찍고 나서 에뮬을 안 죽인다")
    ap.add_argument(
        "--checkpoint",
        help="끝나고 **실행 사본의 세이브 구역**을 이 파일로 떼어 둔다 — 다음 회차의 `--save`. "
        "칸마다 도달 시퀀스가 10~30분이라 체크포인트가 있으면 처음부터 안 돈다",
    )
    a = ap.parse_args()

    common.check_originals()
    save = Path(a.save) if a.save else pick_save()
    run = prepare(a.build, save, a.turbo)
    print(f"빌드 칸 {a.build} · 세이브 {save.name} · 실행 자리 {run}")

    os.environ["DISPLAY"] = a.display
    if subprocess.run(["xdpyinfo"], capture_output=True, check=False).returncode != 0:
        subprocess.Popen(
            ["Xvfb", a.display, "-screen", "0", "1024x768x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

    # 🔴 루트 창을 먼저 지운다 — Xvfb 의 루트는 지난 실행 화면을 들고 있어서, 새 창이
    #    아직 안 그려졌으면 옛 화면을 찍는다(`scripts/emu/pc98.sh` 가 같은 자리에서 물렸다).
    subprocess.run(["xsetroot", "-solid", "black"], capture_output=True, check=False)

    proc = subprocess.Popen(
        [
            "dosbox-x",
            "-conf",
            "pc98.conf",
            "-defaultdir",
            str(run),
            "-c",
            (
                # 새 게임은 Event 로 뜨고, 오프닝이 끝나면 Program 으로 **갈아 끼운다**
                # (`swap` = 호스트키+O). 그래서 두 장을 한 드라이브에 함께 문다.
                f"imgmount 0 {run / 'event.d88'} {run / 'program.d88'} -t floppy -fs none"
                if a.boot == "event"
                else f"imgmount 0 {run / 'program.d88'} -t floppy -fs none"
            ),
            "-c",
            f"imgmount 1 {run / 'scenario.d88'} -t floppy -fs none",
            "-c",
            "boot -l a",
        ],
        cwd=run,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # 죽일 때 프로세스 그룹째 — `pkill -f` 는 내 셸까지 죽인다
    )
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    # 🔴 **Xvfb 에는 창 관리자가 없다.** `windowactivate` 는 WM 몫이라 안 먹고, 입력 포커스가
    #    `PointerRoot` 로 남아 **키가 게스트까지 안 간다.** 화면은 멀쩡히 도니까 「키가 안
    #    먹는다」와 「게임이 그 키를 안 받는다」가 구분이 안 된다 — 공용 실행기 머리말이
    #    경고한 바로 그 오진이다. ⇒ `windowfocus`(XSetInputFocus, WM 없이 된다) + 포인터를
    #    창 안으로 옮겨 둘 다 채운다. 실측(2026-09-08): 이걸 안 하면 방향키·텐키·Enter·
    #    Space 를 다 넣어도 화면이 **깜빡이는 커서 말고는 하나도 안 바뀐다.**
    wid = ""
    for _ in range(40):
        got = x("xdotool", "search", "--pid", str(proc.pid)).splitlines()
        if got:
            wid = got[-1]
            break
        time.sleep(0.5)
    if wid:
        subprocess.run(["xdotool", "windowfocus", "--sync", wid], capture_output=True, check=False)
        subprocess.run(
            ["xdotool", "mousemove", "--window", wid, "320", "200"],
            capture_output=True,
            check=False,
        )
    try:
        for step in a.script.split():
            kind, _, val = step.partition(":")
            if kind == "wait":
                time.sleep(float(val))
            elif kind == "key":
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", val], capture_output=True, check=False
                )
            elif kind == "type":
                subprocess.run(["xdotool", "type", val], capture_output=True, check=False)
            elif kind == "swap":
                # 디스크 교체 = 호스트키(Ctrl+Alt) + O. 오프닝이 끝나면 Program 을 부른다.
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "ctrl+alt+o"],
                    capture_output=True,
                    check=False,
                )
            elif kind == "hold":
                # 🔴 **누르는 시간이 있어야 먹는 자리가 있다.** `key` 는 눌렀다 떼는 게 한순간이라
                #    키보드 포트를 주기로 훑는 쪽(필드 이동 등)은 그걸 통째로 놓친다 —
                #    새턴 emucap 의 `press_frames` 와 같은 함정이다(메모리 2026-08-28).
                name, _, sec = val.partition("@")
                subprocess.run(["xdotool", "keydown", name], capture_output=True, check=False)
                time.sleep(float(sec or 0.4))
                subprocess.run(["xdotool", "keyup", name], capture_output=True, check=False)
            elif kind == "click":
                # ⚠ PC-98 게임은 마우스로 모는 것이 흔하다 — 키가 안 먹으면 여기부터 본다.
                cx, cy = val.split(",")
                subprocess.run(
                    ["xdotool", "mousemove", "--window", wid, cx, cy, "click", "1"],
                    capture_output=True,
                    check=False,
                )
            elif kind == "shot":
                out = SHOT_DIR / f"qa-{val}.png"
                subprocess.run(
                    ["import", "-window", wid or "root", str(out)], capture_output=True, check=False
                )
                print(f"  📸 {out}")
            else:
                raise SystemExit(f"🔴 모르는 대본 낱말: {step}")
    finally:
        if not a.keep:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    if a.checkpoint:
        # ⚠ 통째로 뜬다 — `--save` 가 여기서 **세이브 구역만** 다시 떼어 쓴다.
        #   빌드가 갈려도 그 세이브를 새 이미지에 얹을 수 있어야 하기 때문이다.
        out = Path(a.checkpoint)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / "scenario.d88", out)
        print(f"  💾 체크포인트 {out}  (세이브 있음: {has_save(out)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
