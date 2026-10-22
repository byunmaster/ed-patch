"""sfc-ed2 헤드리스 일괄 검수 — Mesen2 `--testRunner` + Lua. 롬은 **제품 롬 그대로**(패치 없음)이고 에뮬 호출(emucap) 0번으로 돈다.

    python3 sweep.py setup                          # Mesen 실행 사본 만들기(emucap 빌드를 복사 — vendor/ 는 읽기 전용이라)
    python3 sweep.py mkstate battle|dialog [--rom R]  # 부팅해서 시작 상태 파일을 만든다(battle = 필드 진입 직전 · dialog = 필드 첫 메시지 호출 입구)
    python3 sweep.py battle [--groups 0-98|1,5,50] [--seeds 1] [--frames 4000] [--jpp 3] [--procs 4]
    python3 sweep.py dialog [--limit N] [--maxf 900]
    python3 sweep.py report <out 폴더>              # 접촉 시트 + 표

⚠ 함정(10-18 실측)
  · `--testRunner` 는 기본 **벽시계 100초**에서 말없이 죽는다 → `--timeout=<초>`(sfc-ed1 이 찾음)로 늘린다. 그래도 한 프로세스에 작업을 많이 몰지 말고(`--jpp`) 상태 파일로 부팅을 건너뛴다.
  · 사이트 콜백(`SW_SITES`)이 많으면 프레임 속도가 반토막이다 — 기본은 끈다.
  · 병렬은 코어 − 다른 세션 몫만(8코어에서 4~6). 같이 돌면 100초 안에 못 끝나 작업이 통째로 사라진다(END 줄이 없는 작업 = 미완).
  · 상태 파일은 **롬이 바뀌면 다시 만든다**(번역·패치가 바뀌면 코드 주소·창 상태가 달라질 수 있다).
산출: work/review/headless/<battle|dialog>/ (원문·번역 캡처 — 커밋 금지, gitignore).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common

HERE = Path(__file__).resolve().parent
WORK = common.WORK / "derived" / "headless"
OUTROOT = common.WORK / "review" / "headless"
MESEN_SRC = common.ROOT / "vendor/emucap/adapters/mesen2/work/mesen/bin/linux-x64/Release/linux-x64/publish"
MESEN = WORK / "mesen" / "Mesen"
DEFAULT_ROM = common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
FLAGS = ["--timeout=1800", "--debug.scriptWindow.allowIoOsAccess=true", "--preferences.singleInstance=false", "--snes.port1.type=SnesController", "--donotSaveSettings"]


def parse_ids(s: str, hi: int) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [i for i in out if 0 <= i <= hi]


def run_mesen(rom: Path, lua: Path, env: dict) -> subprocess.Popen:
    e = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":99"), **env)
    return subprocess.Popen([str(MESEN), "--testRunner", str(rom), str(lua), *FLAGS], env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pool(tasks: list[tuple[Path, dict]], rom: Path, procs: int) -> None:
    running: list[subprocess.Popen] = []
    q = list(tasks)
    while q or running:
        running = [p for p in running if p.poll() is None]
        while q and len(running) < procs:
            lua, env = q.pop(0)
            running.append(run_mesen(rom, lua, env))
        time.sleep(2)


def setup() -> None:
    if MESEN.exists():
        print("이미 있다:", MESEN)
        return
    if not MESEN_SRC.exists():
        raise SystemExit(f"emucap 의 Mesen 빌드가 없다: {MESEN_SRC}")
    shutil.copytree(MESEN_SRC, MESEN.parent)
    print("Mesen 사본:", MESEN)


def mkstate(kind: str, rom: Path) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"S_{kind}.bin"
    tmp = WORK / "mk"
    tmp.mkdir(exist_ok=True)
    lua = HERE / ("battle_sweep.lua" if kind == "battle" else "dialog_sweep.lua")
    env = {"SW_OUT": str(tmp), "SW_MKSTATE": str(out), "SW_JOBS": "0:1"}
    run_mesen(rom, lua, env).wait()
    if not out.exists():
        raise SystemExit("상태 파일이 안 만들어졌다 — 부팅 입력 타이밍(프레임)이 롬과 맞는지 본다")
    print(out, out.stat().st_size, "B")


def battle(a) -> None:
    rom = Path(a.rom)
    st = WORK / "S_battle.bin"
    if not st.exists():
        raise SystemExit("먼저 mkstate battle")
    groups = parse_ids(a.groups, 98)
    seeds = [int(x) for x in a.seeds.split(",")]
    out = OUTROOT / "battle" / a.tag
    jobs = [(i, s) for s in seeds for i in groups]
    tasks = []
    for k in range(0, len(jobs), a.jpp):
        od = out / f"c{k // a.jpp:03d}"
        od.mkdir(parents=True, exist_ok=True)
        env = {"SW_OUT": str(od), "SW_STATE": str(st), "SW_FRAMES": str(a.frames), "SW_JOBS": ",".join(f"{i}:{s}" for i, s in jobs[k : k + a.jpp])}
        tasks.append((HERE / "battle_sweep.lua", env))
    pool(tasks, rom, a.procs)
    print("끝:", out)


def dialog(a) -> None:
    import script

    rom = Path(a.rom)
    st = WORK / "S_dialog.bin"
    if not st.exists():
        raise SystemExit("먼저 mkstate dialog")
    d = common.rom_bytes()
    units = [common.off2snes(s) for s, _e in script.all_units(d)]
    if a.limit:
        units = units[: a.limit]
    out = OUTROOT / "dialog" / a.tag
    tasks = []
    for k in range(0, len(units), a.per):
        od = out / f"c{k // a.per:04d}"
        od.mkdir(parents=True, exist_ok=True)
        lst = od / "list.txt"
        lst.write_text("\n".join(f"{u:06X}" for u in units[k : k + a.per]) + "\n")
        tasks.append((HERE / "dialog_sweep.lua", {"SW_OUT": str(od), "SW_STATE": str(st), "SW_LIST": str(lst), "SW_MAXF": str(a.maxf)}))
    pool(tasks, rom, a.procs)
    print("끝:", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    p = sub.add_parser("mkstate")
    p.add_argument("kind", choices=["battle", "dialog"])
    p.add_argument("--rom", default=str(DEFAULT_ROM))
    p = sub.add_parser("battle")
    p.add_argument("--rom", default=str(DEFAULT_ROM))
    p.add_argument("--groups", default="0-98")
    p.add_argument("--seeds", default="1")
    p.add_argument("--frames", type=int, default=4000)
    p.add_argument("--jpp", type=int, default=6)
    p.add_argument("--procs", type=int, default=4)
    p.add_argument("--tag", default="run")
    p = sub.add_parser("dialog")
    p.add_argument("--rom", default=str(DEFAULT_ROM))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--per", type=int, default=20, help="프로세스당 단위 수")
    p.add_argument("--maxf", type=int, default=900)
    p.add_argument("--procs", type=int, default=4)
    p.add_argument("--tag", default="run")
    p = sub.add_parser("report")
    p.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "setup":
        setup()
    elif a.cmd == "mkstate":
        mkstate(a.kind, Path(a.rom))
    elif a.cmd == "battle":
        battle(a)
    elif a.cmd == "dialog":
        dialog(a)
    else:
        subprocess.run([sys.executable, str(HERE / "report.py"), a.out, str(Path(a.out) / "sheets")], check=True)


if __name__ == "__main__":
    main()
