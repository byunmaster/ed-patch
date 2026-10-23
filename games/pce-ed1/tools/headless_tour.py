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


def script(slot: int, presses: int, gap: int, view: int = 0, start: int = 0, prefix: str = "m") -> list:
    st = [*BOOT]
    for _ in range(slot - 1):
        st.append(["press", "down", 20, 20])
    st += [["press", "i", 20, 900], ["shot", "p00"]]
    if view:  # 대사 보기 빌드(ED_VIEWER=1) — 닫힌 고리로 쪽마다 찍는다(headless_pce `view`)
        return [*st, ["view", prefix, view]]
    for k in range(1, presses + 1):
        st += [["press", "i", 10, gap], ["shot", f"p{k:02d}"]]
    return st


_FAKE = {}


def _fake_sources(sid: int) -> list:
    """씬 sid 블록이 든 컨테이너마다 — 진짜 워프(위치 깨끗)를 가진 다른 씬과 그 좌표. (씬, (x, y)) 후보 목록."""
    import containers
    import savefile

    if not _FAKE:
        blocks = [(c["rel"], b["id"], b["data"]) for c in containers.scan() for b in c["blocks"]]
        _FAKE["blocks"] = blocks
        by_rel = {}
        for rel, bid, _d in blocks:
            by_rel.setdefault(rel, set()).add(bid)
        _FAKE["by_rel"] = by_rel
        _FAKE["warps"] = {}
    out = []
    for rel, ids in _FAKE["by_rel"].items():
        if sid not in ids:
            continue
        for cand in sorted(ids):
            if cand in (0, sid):
                continue
            if cand not in _FAKE["warps"]:
                w = savefile.find_warps(cand, _FAKE["blocks"])
                _FAKE["warps"][cand] = w[0] if w and savefile.chapter_of(w[0]["from"][0]) is not None else None
            w = _FAKE["warps"][cand]
            if w and w["from"][0] == rel and w["xy"][0] < 64 and w["xy"][1] < 64 and len(out) < 6:  # 좌표 칸은 6비트 — 거짓 워프(글 바이트) 거름
                out.append((cand, w["xy"]))
    return out


def tour_scene(sid: int, base: Path, out: Path, presses: int, gap: int, view: int = 0) -> dict:
    d = out / f"scn{sid:03d}"
    if view and (d / "done").exists():  # 배치가 시간 제한으로 끊겨도 이어서 — 끝낸 씬은 건너뛴다
        return {"scene": sid, "ok": True, "skipped": True}
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
        if g.returncode != 0:  # 들어가는 워프가 없는(또는 가짜 워프뿐인) 씬 — 같은 컨테이너의 진짜 워프를 베껴 씬 번호만 바꾼다(savefile --fake)
            for fs, xy in _fake_sources(sid):
                g = subprocess.run(
                    [sys.executable, str(HERE / "savefile.py"), "goto", str(base), str(sid), "--out", str(sav),
                     "--slot", "3", "--fake", f"{sid}:{xy[0]},{xy[1]}", "--from-scene", str(fs)],
                    capture_output=True,
                    text=True,
                )
                if g.returncode == 0:
                    break
        if g.returncode != 0:
            return {
                "scene": sid,
                "ok": False,
                "why": "점프 세이브를 못 굽는다: "
                + (g.stderr or g.stdout).strip().splitlines()[-1],
            }
        cue = common.BUILD_DIR / common.BUILD_TAG / "ed1.cue"
        start, hangs, out_all = 0, [], ""
        for rerun in range(1):  # 닫히지 않는 메시지(상점 메뉴 등)에서 멈추면 그 번호를 hangs.txt 에 적는다 — 호출부가 ED_VIEWER_SKIP 으로 빼고 롬을 다시 굽는다
            sc = Path(tmp) / "s.json"
            sc.write_text(json.dumps(script(3, presses, gap, view, start, "m" if not rerun else f"r{rerun}_")))
            r = subprocess.run(
                [sys.executable, str(HERE / "headless_pce.py"), str(cue), str(sc), str(d), str(sav)],
                capture_output=True,
                text=True,
            )
            out_all += r.stdout
            if r.returncode != 0 or not view:
                break
            hang = None
            for ln in r.stdout.splitlines():
                if ln.startswith("stall 300 mk "):
                    hang = int.from_bytes(bytes.fromhex(ln.split()[3]), "little")
                elif ln.startswith("view loop mk "):
                    hang = int(ln.split()[3])
            if hang is None:
                break
            hangs.append(hang)
            break
        (d / "hangs.txt").write_text(" ".join(map(str, hangs)))
    if r.returncode != 0:
        return {"scene": sid, "ok": False, "why": "하네스 실패 rc=%d" % r.returncode}
    (d / "done").write_text(out_all[-300:])
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
    s.add_argument("--view", type=int, default=0, help="대사 보기 빌드용 — 최대 쪽 수(0 이면 기존 순회)")
    a = ap.parse_args()
    out = a.out or main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "tour" / "scenes"
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for i in a.ids:  # 씬마다 한 줄씩 바로 적는다(시간 제한에 끊겨도 남는다)
        r = tour_scene(i, a.base, out, a.presses, a.gap, a.view)
        res.append(r)
        print(r, flush=True)
        with open(out / "tour.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / "tour.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
