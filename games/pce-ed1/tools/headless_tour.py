"""헤드리스 씬 순회 — 씬 번호마다 점프 세이브(`savefile.py goto`)를 굽고 libretro 하네스(`headless_pce.py`)로 부팅 → 이어하기 → 슬롯 3 → 대사를 I 로 넘기며 캡처한다(emucap 호출 0번).

  python3 tools/headless_tour.py scenes 16 224 [--base <sav>] [--presses 12] [--gap 120] [--out <폴더>]

산출 — `<메인 트리>/.local/work/inbox/pce-ed1/tour/scenes/scnNNN/` 에 `p00.png`(입장) · `p01.png`… (I 를 누른 뒤 `--gap` 프레임마다) + 요약 `tour.json`(씬별 화면이 바뀐 장수 · 점프 가능 여부).
⚠ 점프가 안 열리는 씬(플래그 의존 — 6·32·41·151)은 `goto` 가 실패하거나 입장 화면이 필드로 남는다 — 요약에 「입장 화면 변화 없음」으로 적힌다.
⚠ 코어(.local/cache/libretro/mednafen_pce_libretro.so)가 있어야 한다(`headless_pce.py` 머리말).
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common

BOOT = [
    ["wait", 2500],
    ["press", "run", 30, 1900],
    ["press", "run", 30, 1500],  # 타이틀
    ["press", "right", 20, 30],  # Continue
    ["press", "i", 20, 400],  # 파일 선택 목록
]


def main_tree() -> Path:
    cd = subprocess.run(
        ["git", "-C", str(common.ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(cd).parent


def script(slot: int, presses: int, gap: int) -> list:
    st = [*BOOT]
    for _ in range(slot - 1):
        st.append(["press", "down", 20, 20])
    st += [["press", "i", 20, 900], ["shot", "p00"]]
    for k in range(1, presses + 1):
        st += [["press", "i", 10, gap], ["shot", f"p{k:02d}"]]
    return st


def tour_scene(sid: int, base: Path, out: Path, presses: int, gap: int) -> dict:
    d = out / f"scn{sid:03d}"
    d.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        sav = Path(tmp) / "g.sav"
        g = subprocess.run(
            [
                sys.executable,
                str(HERE / "savefile.py"),
                "goto",
                str(base),
                str(sid),
                "--out",
                str(sav),
                "--slot",
                "3",
            ],
            capture_output=True,
            text=True,
        )
        if g.returncode != 0:
            return {
                "scene": sid,
                "ok": False,
                "why": "점프 세이브를 못 굽는다: "
                + (g.stderr or g.stdout).strip().splitlines()[-1],
            }
        sc = Path(tmp) / "s.json"
        sc.write_text(json.dumps(script(3, presses, gap)))
        cue = common.BUILD_DIR / common.BUILD_TAG / "ed1.cue"
        r = subprocess.run(
            [sys.executable, str(HERE / "headless_pce.py"), str(cue), str(sc), str(d), str(sav)],
            capture_output=True,
            text=True,
        )
    if r.returncode != 0:
        return {"scene": sid, "ok": False, "why": "하네스 실패 rc=%d" % r.returncode}
    import numpy as np
    from PIL import Image

    shots = sorted(d.glob("p*.png"))
    arr = [np.array(Image.open(p)).astype(int) for p in shots]
    changed = sum(1 for a, b in zip(arr, arr[1:], strict=False) if abs(a - b).mean() > 1.0)
    entered = abs(arr[0] - arr[-1]).mean() > 1.0 if len(arr) > 1 else False
    return {
        "scene": sid,
        "ok": True,
        "shots": len(shots),
        "changed": changed,
        "dir": str(d),
        "note": ""
        if entered
        else "I 입력 뒤 화면 변화 없음 — 자동 이벤트 없는 입구(걸어서 말을 걸어야 한다)",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scenes")
    s.add_argument("ids", type=int, nargs="+")
    s.add_argument("--base", type=Path, default=Path("/root/save/pce-ed1/ed1.sav"))
    s.add_argument("--presses", type=int, default=12)
    s.add_argument("--gap", type=int, default=120)
    s.add_argument("--out", type=Path)
    a = ap.parse_args()
    out = a.out or main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "tour" / "scenes"
    res = [tour_scene(i, a.base, out, a.presses, a.gap) for i in a.ids]
    out.mkdir(parents=True, exist_ok=True)
    (out / "tour.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    for r in res:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
