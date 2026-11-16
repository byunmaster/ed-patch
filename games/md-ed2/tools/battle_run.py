"""전 몬스터·보스 전투 완료 동작 시험 — 전투가 멈추지 않고 끝나는가만 본다(문안·촬영 아님). 헤드리스 위에서 `test-battle` 롬으로 블록 99개를 하나씩 띄운다.

    ED_BUILD_TAG=test-battle python3 tools/test_battle.py          # 후크 롬을 먼저 굽는다(debug 빌드 위)
    python3 tools/battle_run.py [블록...] [--out DIR] [--frames N] [--rom 파일]   # --rom 에 원판 롬을 주면 같은 개입을 원판에 건다(우리 탓인지 가른다)

파티는 L99·HP 9999·공격 4000 으로 올리고(몬스터 HP 고정은 끈다) 확인 키를 60프레임마다 눌러 자동으로 싸운다. 챕터 버퍼 `$FF1B3C` 는 비운다(세이브의 「ED2-END」 후크가
전투 뒤 엔딩을 부르므로). 통과 = 전투 플래그 `$FF1852`(조우 무장 0x0040)가 내려가고 뒤 화면이 까맣지 않으며 방향키로 화면이 움직인다.
못 내려가거나(멈춤) 끝 화면이 까맣거나 안 움직이면 이상 — 화면 한 장과 상태를 `<out>/stuck/` 에 남긴다.
산출(`.local/work/inbox/md-ed2/battle-run/`): `table.tsv`(블록 | 조우 id | 몬스터 | 결과 | 끝난 프레임 | 끝 플래그 | 메모) · `stuck/bNN.png`.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import battle_sweep as BS
import common
import headless

FLAG = 0x1852
ARMED = b"\x00\x40"


def lit(c) -> float:
    return float(np.asarray(c.frame).mean())


def run_block(c, armed: bytes, bid: int, frames: int, out: Path, n: int):
    c.load_state(armed)
    c.poke(0xFF1A16, b"\x00")  # 몬스터 HP 고정 끔
    c.poke(0xFF1A10, b"\x00")  # 난수 순열 끔
    c.poke(0xFF1B3C, bytes(16))  # 엔딩 후크 끔
    c.poke(0x1AFF, bytes([bid >> 8]))
    c.poke(0x3606, bytes([bid & 255]))
    for k in range(4):
        c.poke(0x1DCC + 0x40 * k, b"\x0f\xa0")
    c.hold("right")
    c.run(30)
    c.hold("")
    started = False
    done = None
    for f in range(frames):
        c.run(1)
        if f % 60 == 0:
            c.hold("c")
        elif f % 60 == 6:
            c.hold("")
        w = c.ram(FLAG, 2)
        if w == ARMED:
            started = True
        elif started and done is None:
            done = f
            break
    if done is None:
        shot = out / "stuck" / f"b{n:02d}.png"
        c.shot(str(shot))
        return "멈춤", None, c.ram(FLAG, 2).hex(), "플래그가 안 내려감" if started else "전투가 안 시작됨"
    flag = c.ram(FLAG, 2).hex()
    hs = set()
    for f in range(600):
        c.run(1)
        if f % 60 == 0:
            c.hold("c")
        elif f % 60 == 6:
            c.hold("")
        if f % 100 == 0:
            hs.add(hashlib.md5(np.asarray(c.frame).tobytes()).hexdigest())
    c.hold("")
    c.run(20)
    l0 = lit(c)
    h0 = hashlib.md5(np.asarray(c.frame).tobytes()).hexdigest()
    c.hold("right")
    c.run(40)
    c.hold("")
    c.run(10)
    moved = hashlib.md5(np.asarray(c.frame).tobytes()).hexdigest() != h0
    ev = "플래그 남음" if c.ram(FLAG, 2) != b"\x00\x00" else ""
    memo = f"밝기 {l0:.0f}" + (" · 움직임" if moved else " · 안 움직임") + (f" · {ev}" if ev else "")
    if l0 < 15 or not moved:
        c.shot(str(out / "stuck" / f"b{n:02d}.png"))
        return "이상", done, c.ram(FLAG, 2).hex(), memo
    return "통과", done, c.ram(FLAG, 2).hex(), memo


def main() -> None:
    args = sys.argv[1:]
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "battle-run"
    frames, sel, i, rom_path = 8000, [], 0, BS.ROM
    while i < len(args):
        if args[i] == "--out":
            out, i = Path(args[i + 1]), i + 2
        elif args[i] == "--rom":
            rom_path, i = Path(args[i + 1]), i + 2
        elif args[i] == "--frames":
            frames, i = int(args[i + 1]), i + 2
        else:
            sel.append(int(args[i]))
            i += 1
    out.mkdir(parents=True, exist_ok=True)
    rom = BS.ROM.read_bytes()  # 블록 표·이름은 시험 롬 것(원판과 블록 순서가 같다)
    bl = list(battle.blocks(rom))
    idl = BS.ids()
    c = headless.Core(str(rom_path))
    armed = BS.boot(c)
    c.poke(0xFF1A16, b"\x00")
    tsv = out / "table.tsv"
    if not tsv.exists():
        tsv.write_text("블록\t조우id\t몬스터\t결과\t끝난 프레임\t끝 플래그\t메모\n", encoding="utf-8")
    have = {int(r.split("\t")[0]) for r in tsv.read_text(encoding="utf-8").splitlines()[1:]}
    todo = sel or list(range(1, 99)) + [0]
    for n in todo:
        if n in have:
            continue
        res, done, flag, memo = run_block(c, armed, idl[n], frames, out, n)
        row = f"{n}\t{idl[n]:04x}\t{BS.names(bl, n)}\t{res}\t{done}\t{flag}\t{memo}\n"
        with tsv.open("a", encoding="utf-8") as fh:
            fh.write(row)
        print(row.strip(), flush=True)


if __name__ == "__main__":
    main()
