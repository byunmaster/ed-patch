"""전 몬스터 전투 일괄 — 헤드리스(`headless.py`) 위에서 `test-battle` 롬(`test_battle.py` 후크)으로 전투 블록 99개를 차례로 띄우고
새 문구가 다 그려진 순간마다 화면을 PNG 로 남긴다. emucap 호출 0번.

    ED_BUILD_TAG=test-battle python3 tools/test_battle.py          # 후크 롬을 먼저 굽는다
    python3 tools/battle_sweep.py [블록...]  [--out DIR] [--frames N] [--retries K]

산출(`.local/work/inbox/md-ed2/battle-all-hl/`, 원문 커밋 금지): `bNN/KK.png` · `table.tsv`(블록 | 조우 id | 몬스터 | 참조 스트림 | 나온 수 | 미도달 오프셋 | 캡처 수) ·
`sheets/bNN.png`(블록별 접촉 인화지). 시험 롬 전용 — 제품·`debug` 롬 아님.

후크 규약(`test_battle.py`): `$FF1910` 본 문구 표(워드 개수 + 롱 해시) · `$FF1A10` 난수 순열 켬 · `$FF1A11` 순열 상태 · `$FF1A14` 캡처 카운터(워드).
조우 id 는 표 `0x18BEAE`(색인 = 블록) 의 값, `$FF1AFF` = 상위 · `$FF3606` = 하위.
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import common
import headless

ROM = common.WORK / "build" / "test-battle" / "ed2-kr (TESTBATTLE).bin"
SAVE = Path.home() / "save" / "md-ed2" / "ed2-kr (DEBUG).sav"
CAP, TABLE, FORCE = 0xFF1A14, 0xFF1910, 0xFF1A10
CONSTS = [0, 36, 72, 108, 144, 180, 216, 255]  # 난수표 상수 — 기술 8개까지 각각 고른다


def key(bs: bytes) -> int:
    """후크와 같은 해시 — 스트림 앞 10바이트의 회전 xor."""
    d6 = 0
    for x in (bs + bytes(10))[:10]:
        d6 = ((d6 << 5) | (d6 >> 27)) & 0xFFFFFFFF
        d6 ^= x
    return d6


def boot(c: "headless.Core") -> bytes:
    """타이틀 → 이어하기 슬롯 3 → 필드, 그리고 조우를 무장해 상태를 돌려준다(md-ed1 의 흐름과 같다)."""
    import ctypes as C

    sav = SAVE.read_bytes()
    C.memmove(
        c.lib.retro_get_memory_data(0), sav, len(sav)
    )  # 코어가 크기를 0/1024 로 보고해도 포인터는 64KB 세이브 램
    c.run(1601)
    c.press("start", 20, 400)
    c.press("down", 20, 20)
    c.press("c", 15, 200)
    c.run(100)
    c.press("down", 8, 14)
    c.press("down", 8, 14)
    c.press("c", 15, 300)
    c.run(300)
    for k in range(4):  # 파티 공격력 1(몬스터가 죽지 않게)
        c.poke(0x1DCC + 0x40 * k, b"\x00\x01")
    c.poke(0x3474, bytes.fromhex("00FFFF80"))
    c.poke(0x2076, bytes.fromhex("00FFFF80"))
    c.poke(0xFF80, bytes.fromhex("000000000000FF0000000000"))
    c.poke(0x1852, bytes.fromhex("0040"))
    c.poke(FORCE, b"\x01\x00")
    c.poke(TABLE, b"\x00\x00")
    c.poke(CAP, b"\x00\x00")
    return c.save_state()


def ids() -> list[int]:
    rom = common.rom()
    out, o = [], 0x18BEAE
    while struct.unpack(">H", rom[o : o + 2])[0] != 0xFFFF:
        out.append(struct.unpack(">H", rom[o : o + 2])[0])
        o += 2
    return out


def block_streams(rom: bytes, bl, n: int):
    b = bl[n][1]
    out = []
    for off, v in sorted(battle.refs(b).items()):
        raw = b"".join(t.raw for t in v["stream"].tokens)
        out.append((off, key(raw)))
    return out


def names(bl, n: int) -> str:
    import json

    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    outs = []
    for r in battle.records(bl[n][1]):
        nm, s, i = r["name"], "", 0
        while i < len(nm):
            if nm[i : i + 2] in rev:
                s += rev[nm[i : i + 2]]
                i += 2
            elif nm[i] < 0x80:
                s += chr(nm[i])
                i += 1
            else:
                s += "?"
                i += 2
        outs.append(s)
    return "/".join(outs)


PARTY_NAME = None  # --names a|b: 파티 레코드 넷의 이름을 받침 없는/있는 이름으로(조사 확인) — a=「란도플로라스」 b=「란도플로신」
NAMES_AB = {"a": "란도플로라스", "b": "란도플로신"}


def poke_names(c) -> None:
    if PARTY_NAME is None:
        return
    import json

    import common

    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    nm = b"".join(codes[ch].to_bytes(2, "big") for ch in NAMES_AB[PARTY_NAME]) + b"\x06\x00"
    for n in range(4):
        c.poke(0xFF1DBC + n * 0x40 + 0x30, nm)


def run_block(
    c,
    armed: bytes,
    n: int,
    bid: int,
    outdir: Path,
    frames: int,
    seed: int,
    merge_keys: set[int],
    shots: list[Path],
    start: int,
    force: int = 1,
    const: int | None = None,
):
    c.load_state(armed)
    poke_names(c)
    c.poke(
        FORCE, bytes([force])
    )  # 0 = 자연 난수 · 1 = 순열(기술은 고루 나오지만 보스 주문·대상 번호가 범위 밖으로 나가 글이 깨질 수 있다 — 실측)
    c.poke(0x1AFF, bytes([bid >> 8]))
    c.poke(0x3606, bytes([bid & 255]))
    c.poke(0xFF1A11, bytes([seed]))
    c.poke(0xFF1A16, b"\x01")  # 몬스터 HP 고정 켬(후크 `MONON`)
    c.hold("right")
    c.run(30)
    c.hold("")
    last = c.ram(CAP, 2)
    idle = 0
    k = start
    for f in range(frames):
        c.run(1)
        if (
            const is not None and f % 2 == 0
        ):  # 난수표 `$FF3480`(55B)을 한 값으로 — 행동 선택이 (값×기술 수)>>8 로 고정된다(md-ed1 gpgx_battle 방식)
            c.poke(0xFF3480, bytes([const]) * 55)
        if (
            f % 2 == 0 and k > start
        ):  # 몬스터가 한 방에 죽지 않게 매 두 프레임 HP 를 채운다(후크의 갱신은 렌더러 호출 때뿐이다)
            hp = c.ram(0x1EC0, 0x180)
            for m in range(4):
                v = int.from_bytes(hp[0x40 * m : 0x40 * m + 2], "big")
                mx = int.from_bytes(hp[0x40 * m + 2 : 0x40 * m + 4], "big")
                if 0 < v < 999 and mx < 999 and v <= mx:
                    c.poke(0x1EC0 + 0x40 * m, b"\x03\xe7\x03\xe7")
        if (
            k > start or f > 300
        ):  # 명령창이 뜨면 확인 키로 턴을 넘긴다(기본 「공격」 — 파티 공격력은 1). 등장 문구가 없는 보스전(블록 62·64·95)은 첫 문구가 나오기 전에 명령 대기라 300프레임 뒤부터 눌러 연다
            if f % 60 == 0:
                c.hold("c")
            elif f % 60 == 6:
                c.hold("")
        cur = c.ram(CAP, 2)
        if cur != last:
            last = cur
            idle = 0
            k += 1
            p = outdir / f"b{n:02d}" / f"{k:02d}.png"
            c.shot(str(p))
            shots.append(p)
            if k >= 40:
                break
        else:
            idle += 1
            if idle > 900:
                break
    cnt = min(int.from_bytes(c.ram(TABLE, 2), "big"), 60)
    d = c.ram(TABLE + 2, 4 * cnt)
    merge_keys.update(int.from_bytes(d[4 * i : 4 * i + 4], "big") for i in range(cnt))
    return k


def sheet(paths: list[Path], dst: Path, cols: int = 3):
    from PIL import Image

    if not paths:
        return
    ims = [Image.open(p) for p in paths[:12]]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), (40, 40, 40))
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "battle-all-hl"
    frames, retries = 4000, 8
    sel = []
    i = 0
    while i < len(args):
        if args[i] == "--out":
            out = Path(args[i + 1])
            i += 2
        elif args[i] == "--frames":
            frames = int(args[i + 1])
            i += 2
        elif args[i] == "--retries":
            retries = int(args[i + 1])
            i += 2
        elif args[i] == "--names":
            global PARTY_NAME
            PARTY_NAME = args[i + 1]
            i += 2
        else:
            sel.append(int(args[i]))
            i += 1
    out.mkdir(parents=True, exist_ok=True)
    rom = ROM.read_bytes()
    bl = list(battle.blocks(rom))
    idl = ids()
    c = headless.Core(str(ROM))
    armed = boot(c)
    todo = sel or list(range(1, 99)) + [0]
    tsv = out / "table.tsv"
    if not tsv.exists():
        tsv.write_text(
            "블록\t조우id\t몬스터\t참조 스트림\t나온 수\t미도달 오프셋\t캡처 수\n", encoding="utf-8"
        )
    have = {int(m) for m in re.findall(r"^(\d+)\t", tsv.read_text(encoding="utf-8"), re.MULTILINE)}
    for n in todo:
        if n in have:  # 끝낸 블록은 건너뛴다(묶음이 시간 제한에 잘려도 이어 받는다)
            continue
        refs = block_streams(rom, bl, n)
        keys: set[int] = set()
        shots: list[Path] = []
        k = 0
        for attempt in range(retries + 1):
            # 시도 0 = 순열, 1.. = 자연 난수 + 난수표 상수(CONSTS) — 몬스터 기술 전부를 한 번씩 고르게 한다
            cv = None if attempt == 0 else CONSTS[(attempt - 1) % len(CONSTS)]
            k = run_block(
                c,
                armed,
                n,
                idl[n],
                out,
                frames,
                (0x40 * attempt) & 255,
                keys,
                shots,
                k,
                1 if attempt == 0 else 0,
                cv,
            )
            miss = [o for o, kk in refs if kk not in keys]
            if not miss:
                break
        got = len(refs) - len(miss)
        row = f"{n}\t{idl[n]:04x}\t{names(bl, n)}\t{len(refs)}\t{got}\t{','.join(hex(o) for o in miss) or '-'}\t{k}\n"
        with tsv.open("a", encoding="utf-8") as f:
            f.write(row)
        sheet(shots, out / "sheets" / f"b{n:02d}.png")
        print(row.strip(), flush=True)


if __name__ == "__main__":
    main()
