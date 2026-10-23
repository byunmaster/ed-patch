"""조건 분기 꼬리 화면 대조 — 조건 분기(11·12·F2·F6·F8 + 0F) 스트림이 조건이 맞아 goto 를 건너뛰면 **물리적으로 바로 뒤**의 꼬리를 읽는다.
그 꼬리를 원판 롬과 새 롬에서 같은 하네스로 띄워 나란히 남긴다(`_o_` 원판 · `_n_` 새 롬). 정적 게이트(`scene.verify_cond_tails`)가 못 보는 이음새를 화면으로 본다.

    python3 tools/condtail_sweep.py list [--shared]     # 대상 표만 (에뮬 없음)
    python3 tools/condtail_sweep.py shoot o|n [BBB-K ...]   # 촬영(칸 하나·프로세스 하나 — 원판 o, 새 롬 n 을 따로)

대상: 한 모듈에서 **같은 꼬리 T 를 둘 이상의 조건 분기가 이어받는** 자리(옮겨진 바깥 S 와 안쪽 S′ — 재조립이 꼬리를 하나에만 붙이던 부류, 30곳).
산출 `sweep/condtail/`: `BBB-K/<S원판오프셋>_o_NN.png` · `_n_NN.png` + `index-o.tsv`·`index-n.tsv`(모듈 | 원판 S | 원판 꼬리 | 새 꼬리 자리 | 쪽 수 | 상태).
"""

import hashlib
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle_sweep as BS
import common
import headless
import scene
import scene_sweep as S
import test_battle as T

OUT = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "condtail"
SCRATCH = Path("/tmp/claude-0/sp")


def sites(shared_only: bool = True):
    """[(모듈키, 원판 모듈 바이트, 새 모듈 바이트, [(S, T, S′, 새꼬리)])]"""
    rom = BS.ROM.read_bytes()
    new_mods = {(b, k): m for b, k, m in S.built_modules(rom)}
    out = []
    for b, k, om in archives.modules(common.rom()):
        orig = scene.parse_module(om)
        rows: list = []
        scene.cond_tail_report(orig, new_mods[(b, k)], None, rows)
        by_t = defaultdict(list)
        for r in rows:
            by_t[r[1]].append(r)
        pick = [r for t, rs in by_t.items() if len(rs) > 1 or not shared_only for r in rs]
        if pick:
            out.append((f"{b:03d}-{k}", om, new_mods[(b, k)], sorted(pick)))
    return out


def orig_hook_rom() -> Path:
    """원판 롬 + 같은 렌더러 후크(대사 우편함) — orig_say 와 같은 방식. 시험 칸이라 `test-` 도구 폴더에 둔다."""
    rom = bytearray(common.rom())
    old = bytes(rom[T.ENTRY : T.ENTRY + 6])
    code, rngf, exit_off, tick_off = T.hook_code(old)
    rom[T.HOOK_AT : T.HOOK_AT + len(code)] = code
    rom[T.RAND_AT + 2 : T.RAND_AT + 6] = struct.pack(">I", T.HOOK_AT + rngf)
    rom[T.EXIT_AT : T.EXIT_AT + 6] = bytes.fromhex("4ef9") + struct.pack(">I", T.HOOK_AT + exit_off)
    rom[T.TICK_AT : T.TICK_AT + 6] = bytes.fromhex("4ef9") + struct.pack(">I", T.HOOK_AT + tick_off)
    rom[T.ENTRY : T.ENTRY + 6] = bytes.fromhex("4ef9") + struct.pack(">I", T.HOOK_AT)
    rom[0x18E:0x190] = struct.pack(">H", common.header_checksum(bytes(rom)))
    p = SCRATCH / "orig-hook.bin"
    p.write_bytes(bytes(rom))
    return p


def throne(c, rom_path: Path, cache: Path) -> bytes:
    tag = hashlib.sha1(rom_path.read_bytes()).hexdigest()[:10]
    f = cache / f"throne-{tag}.state"
    if f.exists():
        c.run(2)
        return f.read_bytes()
    c.run(1601)
    c.press("start", 20, 400)
    c.press("c", 15, 200)
    for _ in range(560):
        c.press("c", 4, 50)
    st = c.save_state()
    f.write_bytes(st)
    return st


def korean(raw, rev):
    return S.korean(raw, rev)


def shoot(side, sel):
    """한 프로세스에 코어 하나 — libretro 코어는 같은 .so 를 두 번 올리면 상태를 공유한다. 원판(o)·새 롬(n)은 따로 부른다."""
    OUT.mkdir(parents=True, exist_ok=True)
    rom_path = orig_hook_rom() if side == "o" else BS.ROM
    c = headless.Core(str(rom_path))
    st = throne(c, rom_path, OUT)
    tsv = OUT / f"index-{side}.tsv"
    if not tsv.exists():
        tsv.write_text("모듈\t원판S\t원판꼬리\t새꼬리\t쪽\t상태\n", encoding="utf-8")
    done_f = OUT / f"done-{side}.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    for key, om, nm, rows in sites():
        if (sel and key not in sel) or key in done:
            continue
        d = OUT / key
        d.mkdir(exist_ok=True)
        m = om if side == "o" else nm
        for s, t, _sn, tail in rows:
            c.load_state(st)
            c.poke(S.MOD_AT, m)
            off = t if side == "o" else tail
            n, status = S.say(c, S.MOD_AT + off, d, f"{s:04x}_{side}_{off:04x}")
            with tsv.open("a", encoding="utf-8") as f:
                f.write(f"{key}\t{s:04x}\t{t:04x}\t{tail:04x}\t{n}\t{status}\n")
        with done_f.open("a") as f:
            f.write(key + "\n")
        print(side, key, len(rows), flush=True)


def main():
    a = sys.argv[1:]
    if a and a[0] == "list":
        n = 0
        for key, _o, _n, rows in sites("--all" not in a):
            n += len(rows)
            print(key, len(rows), " ".join(f"{s:x}→{t:x}" for s, t, _a, _b in rows))
        print("total", n)
    elif a and a[0] == "shoot":
        shoot(a[1], a[2:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
