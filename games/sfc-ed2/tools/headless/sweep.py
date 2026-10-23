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
import hashlib
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


def rom_sha(rom: Path) -> str:
    return hashlib.sha1(Path(rom).read_bytes()).hexdigest()


def check_state(kind: str, rom: Path) -> None:
    """상태 파일은 옛 롬의 RAM(글리프 표·텍스트·코드)을 되살린다 — 만든 롬과 지금 롬이 다르면 촬영을 거부한다(ps1-ed3 에서 「줄」이 「앗」으로 나온 사고)."""
    sf = WORK / f"S_{kind}.sha1"
    if not sf.exists() or sf.read_text().strip() != rom_sha(rom):
        raise SystemExit(f"상태 파일 S_{kind}.bin 은 이 롬({rom_sha(rom)[:8]})으로 만든 것이 아니다 — `mkstate {kind}` 를 다시 돌린다")


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
    (WORK / f"S_{kind}.sha1").write_text(rom_sha(rom) + "\n")
    print(out, out.stat().st_size, "B", "rom", rom_sha(rom)[:8])


def battle(a) -> None:
    rom = Path(a.rom)
    st = WORK / "S_battle.bin"
    check_state("battle", rom)
    if not st.exists():
        raise SystemExit("먼저 mkstate battle")
    groups = parse_ids(a.groups, 98)
    seeds = [int(x) for x in a.seeds.split(",")]
    out = Path(a.out) if getattr(a, "out", "") else OUTROOT / "battle" / a.tag
    jobs = [(i, s) for s in seeds for i in groups]
    tasks = []
    for k in range(0, len(jobs), a.jpp):
        od = out / f"c{a.cbase + k // a.jpp:03d}"
        od.mkdir(parents=True, exist_ok=True)
        env = {"SW_OUT": str(od), "SW_STATE": str(st), "SW_FRAMES": str(a.frames), "SW_JOBS": ",".join(f"{i}:{s}" for i, s in jobs[k : k + a.jpp])}
        tasks.append((HERE / "battle_sweep.lua", env))
    pool(tasks, rom, a.procs)
    print("끝:", out)


def dialog(a) -> None:
    import script

    rom = Path(a.rom)
    st = WORK / "S_dialog.bin"
    check_state("dialog", rom)
    if not st.exists():
        raise SystemExit("먼저 mkstate dialog")
    d = common.rom_bytes()
    # 인라인 메시지 호출(`jml $C1:8F0B` = 5C 0B 8F C1)의 4바이트는 메시지가 아니라 호출 명령이다 — 포인터를 그 뒤로(실게임은 그 뒤를 읽는다. 안 그러면 화자 이름 머리가 두 번 그려진다)
    allu = [(s + 4 if d[s : s + 4] == b"\x5c\x0b\x8f\xc1" else s, e) for s, e in script.all_units(d)]
    units = [common.off2snes(s) for s, _e in allu]
    caps = {common.off2snes(s): 2 * (script.render(d, s).count("<05>") + 1) + 1 for s, _e in allu}  # 쪽 상한 — 원문 쪽 수의 두 배 + 1(번역이 쪽을 더 쪼갤 수 있다). 지난 뒤 이어지는 필드 이벤트 대사를 안 찍으려고
    if a.only:
        want = [int(x.split()[0], 16) for x in Path(a.only).read_text().split("\n") if x.strip()]
        for u in want:  # 단위 시작이 아닌 주소(단독 시작 메시지)는 그 자리에서 쪽 상한을 센다
            caps.setdefault(u, 2 * (script.render(d, common.snes2off(u)).count("<05>") + 1) + 1)
        units = want[a.skip :]  # 못 닿은 단위만 다시(--only 목록, --skip/--limit 은 그 목록 안에서)
    else:
        units = units[a.skip :]
    if a.limit:
        units = units[: a.limit]
    out = Path(a.out) if a.out else OUTROOT / "dialog" / a.tag
    tasks = []
    for k in range(0, len(units), a.per):
        od = out / f"c{(a.cbase if a.only else 0) + (a.skip + k) // a.per:04d}"
        od.mkdir(parents=True, exist_ok=True)
        lst = od / "list.txt"
        lst.write_text("\n".join(f"{u:06X} {caps[u]}" for u in units[k : k + a.per]) + "\n")
        tasks.append((HERE / "dialog_sweep.lua", {"SW_OUT": str(od), "SW_STATE": str(st), "SW_LIST": str(lst), "SW_MAXF": str(a.maxf), **({"SW_VARNAME": a.varname} if a.varname else {})}))
    pool(tasks, rom, a.procs)
    print("끝:", out)


def trace(a) -> None:
    """구조 흐름 추적(`trace_play.lua`) — 단위 목록(`--list`, 비면 필드 첫 장면 연속 재생)을 자연 진행으로 돌려 구조 토큰 (주소, 바이트) 열을 `<out>/trace.txt` 에 남긴다."""
    rom = Path(a.rom)
    check_state("dialog", rom)
    od = Path(a.out)
    od.mkdir(parents=True, exist_ok=True)
    (od / "trace.txt").unlink(missing_ok=True)
    env = {"SW_OUT": str(od), "SW_STATE": str(WORK / "S_dialog.bin"), "SW_MAXF": str(a.maxf)}
    if a.list:
        env["SW_LIST"] = a.list
    if a.all:
        env["SW_ALL"] = "1"
    run_mesen(rom, HERE / "trace_play.lua", env).wait()
    print("끝:", od / "trace.txt")


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
    p.add_argument("--out", default="")
    p.add_argument("--cbase", type=int, default=0)
    p = sub.add_parser("dialog")
    p.add_argument("--rom", default=str(DEFAULT_ROM))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--skip", type=int, default=0, help="앞에서 건너뛸 단위 수(--per 의 배수로 — 청크 번호가 이어진다)")
    p.add_argument("--per", type=int, default=20, help="프로세스당 단위 수")
    p.add_argument("--maxf", type=int, default=3000)
    p.add_argument("--only", default="", help="단위 주소 목록 파일(한 줄에 hex 하나) — 이 단위들만 찍는다")
    p.add_argument("--cbase", type=int, default=9000, help="--only 일 때 청크 번호 시작(회차마다 다르게)")
    p.add_argument("--varname", default="", help="이름 변수 버퍼($1201)에 넣을 대표 아이템 이름(hex 바이트, 끝 토큰 06 포함)")
    p.add_argument("--out", default="", help="산출 폴더(메인 트리 .local/work/inbox/... 에 직접 둘 때)")
    p.add_argument("--procs", type=int, default=4)
    p.add_argument("--tag", default="run")
    p = sub.add_parser("trace")
    p.add_argument("--rom", default=str(DEFAULT_ROM))
    p.add_argument("--list", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--maxf", type=int, default=2500)
    p.add_argument("--all", action="store_true", help="구조 토큰만이 아니라 읽는 토큰 전부")
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
    elif a.cmd == "trace":
        trace(a)
    else:
        subprocess.run([sys.executable, str(HERE / "report.py"), a.out, str(Path(a.out) / "sheets")], check=True)


if __name__ == "__main__":
    main()
