"""고친 스트림만 다시 찍는다 — 새 롬(`n`)과 원판 롬(`o`, 같은 후크)을 **원판 오프셋** 열쇠로 짝지어 나란히 남긴다.

    python3 tools/fix_shoot.py shoot o|n LIST [--out DIR]     # LIST: 「BBB-K/원판오프셋(16진)」 공백·줄바꿈 구분 파일

새 롬 쪽 오프셋은 `scene.pair_streams` 로 원판→새 짝을 지어 얻는다(옮겨졌어도 같은 스트림). 코어는 프로세스마다 하나라 o·n 을 따로 부른다(`condtail_sweep` 와 같은 이유).
산출 `sweep/fix-final/BBB-K/<원판오프셋>_<o|n>_NN.png` + `index-<o|n>.tsv`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle_sweep as BS
import common
import condtail_sweep as CT
import headless
import scene
import scene_sweep as S

OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "fix-final"


def shoot(side: str, items: list[tuple[str, int]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rom_path = CT.orig_hook_rom() if side == "o" else BS.ROM
    c = headless.Core(str(rom_path))
    st = CT.throne(c, rom_path, out)
    new_mods = {f"{b:03d}-{k}": m for b, k, m in S.built_modules(BS.ROM.read_bytes())}
    orig_mods = {f"{b:03d}-{k}": m for b, k, m in archives.modules(common.rom())}
    tsv = out / f"index-{side}.tsv"
    if not tsv.exists():
        tsv.write_text("모듈\t원판오프셋\t실제오프셋\t쪽\t상태\n", encoding="utf-8")
    cache: dict[str, tuple] = {}
    for key, off in items:
        om = orig_mods[key]
        if side == "o":
            m, at = om, off
        else:
            if key not in cache:
                cache[key] = scene.pair_streams(scene.parse_module(om), new_mods[key])
            at = cache[key][1].get(off)
            m = new_mods[key]
            if at is None:
                with tsv.open("a", encoding="utf-8") as f:
                    f.write(f"{key}\t{off:04x}\t-\t0\t짝없음\n")
                continue
        d = out / key
        d.mkdir(exist_ok=True)
        c.load_state(st)
        S.set_speed(c, 1)  # 보통(원판 대조는 같은 속도로)
        c.poke(S.MOD_AT, m)
        n, status = S.say(c, S.MOD_AT + at, d, f"{off:04x}_{side}")
        with tsv.open("a", encoding="utf-8") as f:
            f.write(f"{key}\t{off:04x}\t{at:04x}\t{n}\t{status}\n")
        print(side, key, f"{off:04x}", n, status, flush=True)


def main() -> None:
    a = sys.argv[1:]
    if len(a) < 3 or a[0] != "shoot":
        sys.exit(__doc__)
    out = OUT
    if "--out" in a:
        i = a.index("--out")
        out = Path(a[i + 1])
        del a[i : i + 2]
    items = []
    for tok in Path(a[2]).read_text().split():
        k, o = tok.split("/")
        items.append((k, int(o, 16)))
    shoot(a[1], items, out)


if __name__ == "__main__":
    main()
