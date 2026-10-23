"""전투 조건부 문구 강제 — `battle_sweep` 가 난수로 못 부른 문안(`unreached.tsv`)을 **실제 전투 창**에서 직접 띄운다.

    python3 tools/battle_force.py [--out DIR] [블록:오프셋 …]    # 인자 없으면 table.tsv 의 미도달 전부

시험 롬 렌더러 후크의 `FORCEMSG`($FF1A28)에 스트림 주소를 쓰면 **다음에 그려질 문안 대신** 그 스트림이 그려진다(전투 시작 첫 문구가 대체된다).
스트림 주소 = 전투 블록이 RAM 에 놓인 자리 + 블록 안 오프셋(블록 앞 16바이트를 RAM 에서 찾아 기준을 잡는다).
산출: DIR/force/bNN_<오프셋>.png + force-index.tsv(블록 | 오프셋 | 한글 문안 | 상태). 이름·대상 자리는 그 전투의 실제 몬스터·파티.
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import battle_sweep as BS
import headless
import scene_sweep as S

FORCEMSG = 0xFF1A28
NAME = False  # --name: 조각 앞에 이름 호출(`02 eb00`)을 붙인 합성 스트림으로 띄운다(이름 뒤 조사·공백 확인)
SCRATCH = 0xFF1A60
LATE = 0  # 자연 문구가 이만큼 나온 뒤에 강제(--late N)


def find_base(c, blk: bytes) -> int | None:
    """블록이 RAM 에 놓인 기준 주소. 앞 24바이트(0x40~)가 0 이 많아 여러 곳에 맞을 수 있다(블록 62 는 두 곳 — 첫 후보가 틀려 문구가 깨져 찍혔다) — 후보마다 블록 전체와 같은 바이트 수를 세어 가장 닮은 곳을 고른다."""
    ram = c.ram(0xFF0000, 0x10000)
    pat = blk[0x40:0x58]
    best, best_at = -1, None
    i = ram.find(pat)
    while i >= 0:
        at = i - 0x40
        if at >= 0:
            seg = ram[at : at + len(blk)]
            score = sum(1 for a, b in zip(seg, blk) if a == b)
            if score > best:
                best, best_at = score, at
        i = ram.find(pat, i + 1)
    return None if best_at is None else 0xFF0000 + best_at


def main() -> None:
    args = sys.argv[1:]
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "battle"
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        del args[i : i + 2]
    global LATE, NAME
    if "--name" in args:
        args.remove("--name")
        NAME = True
    if "--late" in args:
        i = args.index("--late")
        LATE = int(args[i + 1])
        del args[i : i + 2]
    rom = BS.ROM.read_bytes()
    bl = list(battle.blocks(rom))
    idl = BS.ids()
    want: list[tuple[int, int]] = []
    if args:
        want = [(int(a.split(":")[0]), int(a.split(":")[1], 16)) for a in args]
    else:
        for m in re.finditer(
            r"^(\d+)\t[0-9a-f]{4}\t.*?\t\d+\t\d+\t([^\t\n]*)\t\d+\s*$",
            (out / "table.tsv").read_text(encoding="utf-8"),
            re.MULTILINE | re.DOTALL,
        ):
            if m.group(2) != "-":
                want += [(int(m.group(1)), int(o, 16)) for o in m.group(2).split(",")]
    d = out / "force"
    d.mkdir(parents=True, exist_ok=True)
    tsv = d / ("force-index-name.tsv" if NAME else "force-index.tsv")
    done = (
        set(re.findall(r"^(\d+\t0x[0-9a-f]+)\t", tsv.read_text(encoding="utf-8"), re.MULTILINE))
        if tsv.exists()
        else set()
    )
    if not tsv.exists():
        tsv.write_text("블록\t오프셋\t문안\t상태\n", encoding="utf-8")
    c = headless.Core(str(BS.ROM))
    armed = BS.boot(c)
    for b, off in want:
        if f"{b}\t{off:#x}" in done:
            continue
        c.load_state(armed)
        S.set_speed(c)  # 기본 멈춤 — 글이 한 번에 떠야 쓰는 중 프레임(깨진 첫 글자)이 안 찍힌다
        c.poke(BS.FORCE, b"\x00\x00")  # 자연 난수
        c.poke(0x1AFF, bytes([idl[b] >> 8]))
        c.poke(0x3606, bytes([idl[b] & 255]))
        c.poke(0xFF1A16, b"\x01")
        c.hold("right")
        c.run(30)
        c.hold("")
        c.run(90)  # 블록이 RAM 에 풀릴 때까지
        base = find_base(c, bl[b][1])
        status, shot = "기준못찾음", 0
        txt = ""
        if base is not None:
            v = battle.refs(bl[b][1]).get(off)
            if v:
                import json

                import common

                codes = json.loads(
                    (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
                )
                rev = {x.to_bytes(2, "big"): k for k, x in codes.items() if isinstance(x, int)}
                txt = S.korean(b"".join(t.raw for t in v["stream"].tokens if t.kind == "text"), rev)
            # 보스 블록은 전투 시작 직후엔 보스 액터가 비어 있어(0HP) 이름 호출이 스트림을 통째로 비운다 — 자연 문구가 `late` 번 나온 뒤에 지정한다
            last = c.ram(BS.CAP, 2)
            seen = 0
            for f in range(60 * 40):
                if seen >= LATE:
                    break
                c.run(1)
                if f % 60 == 0:
                    c.hold("c")
                elif f % 60 == 6:
                    c.hold("")
                cur = c.ram(BS.CAP, 2)
                if cur != last:
                    last = cur
                    seen += 1
            tgt = base + off
            if (
                NAME
            ):  # [02 eb00 0f hh ll] — 이름 + 조사 훅 + 조각으로 goto(오프셋은 첫 인자 바이트 기준)
                # 조각이 이미 조사(「는 쉬고」·「의 혹이」)로 시작하면 조사 훅(eb00)을 뺀다 — 안 그러면 「아트라스는는」이 된다(첫 시험에서 겹쳤다)
                first = txt[:1]
                pre = b"\x02" + (b"" if first in "은는이가을를의에와과도" else b"\xeb\x00")
                c.poke(SCRATCH, pre + b"\x0f" + struct.pack(">h", tgt - (SCRATCH + len(pre) + 1)))
                tgt = SCRATCH
            c.poke(FORCEMSG, struct.pack(">I", tgt))
            last = c.ram(BS.CAP, 2)
            status = "시간초과"
            for f in range(1500):
                c.run(1)
                if f % 60 == 0:
                    c.hold("c")
                elif f % 60 == 6:
                    c.hold("")
                cur = c.ram(BS.CAP, 2)
                if cur != last:
                    c.run(45)
                    c.shot(str(d / f"b{b:02d}_{off:x}{'_name' if NAME else ''}.png"))
                    shot, status = 1, "찍음"
                    break
        with tsv.open("a", encoding="utf-8") as fh:
            fh.write(f"{b}\t{off:#x}\t{txt.replace(chr(10), ' ')[:80]}\t{status}\n")
        print(b, hex(off), status, flush=True)


if __name__ == "__main__":
    main()
