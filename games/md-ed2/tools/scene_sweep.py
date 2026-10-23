"""전 씬 대사 일괄 — 헤드리스(`headless.py`) 위에서 `test-battle` 롬의 대사 우편함 `SAY`($FF1A1C)로 스트림을 하나씩 띄워 화면을 남긴다.

    ED_BUILD_TAG=test-battle python3 tools/test_battle.py          # 후크 롬(대사 우편함 포함)
    python3 tools/scene_sweep.py [BBB-K ...] [--out DIR] [--limit N]

모듈(대본 블록 × 4)을 구운 롬에서 풀어 RAM `$FF6650` 에 올리고(필드 상태 위에), 그 모듈의 스트림마다 `SAY` = 스트림 주소를 쓴 뒤 한 걸음 걸어 후크가
메시지 서비스 `0x85E2`(a1 = 스트림)를 부르게 한다. 서비스가 도는 동안 `BUSY`($FF1A20) = 1. 화면이 가만히 서면(깜박이는 ▼ 는 무시) 캡처하고 확인 키로 넘긴다.
산출(`.local/work/inbox/md-ed2/sweep/scene/`, 한글 화면뿐): `BBB-K/<스트림오프셋>_NN.png` · `index.tsv`(모듈 | 오프셋 | 한글 문안 | 캡처 수 | 상태).
⚠ 스트림은 **맥락 없이** 띄운다 — 플래그 분기·이어지는 goto 는 그 자리에서 실제로 읽힌 만큼만 나온다. 서비스가 안 끝나는 스트림은 「시간 초과」로 기록한다.
"""

import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle_sweep as BS
import build
import common
import headless
import scene

SAY, BUSY = 0xFF1A1C, 0xFF1A20
MOD_AT = 0xFF6650


def built_modules(rom: bytes):
    """구운 롬의 (블록, 순번, 바이트) — 씬 크기 표는 꼬리로 옮겨져 있다(build.SCENE_TABLE_AT)."""
    out = []
    for i, (_, b, _) in enumerate(
        archives.blocks(rom, archives.ARCHIVES["script"][0])[: archives.SCENE_BLOCKS]
    ):
        sz = struct.unpack(
            ">4H", rom[build.SCENE_TABLE_AT + 8 * i : build.SCENE_TABLE_AT + 8 * i + 8]
        )
        if sum(sz) != len(b):
            raise SystemExit(f"블록 {i}: 크기 표 합 {sum(sz)} ≠ {len(b)}")
        o = 0
        for k, s in enumerate(sz):
            out.append((i, k, b[o : o + s]))
            o += s
    return out


def korean(raw: bytes, rev: dict) -> str:
    s, i = "", 0
    while i < len(raw):
        if raw[i : i + 2] in rev:
            s += rev[raw[i : i + 2]]
            i += 2
        elif 0x20 <= raw[i] < 0x7F:
            s += chr(raw[i])
            i += 1
        else:
            s += "·"
            i += 2 if raw[i] >= 0x80 else 1
    return s


def say(c, addr: int, outdir: Path, tag: str, maxf: int = 1500) -> tuple[int, str]:
    """스트림 하나를 띄워 화면을 남긴다 → (캡처 수, 상태)."""
    c.poke(SAY, struct.pack(">I", addr))
    c.hold("right")
    for _ in range(120):
        c.run(1)
        if c.ram(BUSY, 1)[0]:
            break
    else:
        c.hold("")
        return 0, "미호출"
    c.hold("")
    last = None
    shots = 0
    R = slice(120, 224)  # 대사창 영역(▼ 깜박임·스프라이트는 위쪽·작아서 쪽 구분에 쓰지 않는다)
    f = -1
    while f < maxf:
        f += 1
        c.run(1)
        if not c.ram(BUSY, 1)[0]:
            return shots, "끝"
        if f % 90 == 89:  # 90프레임마다: 글이 다 찍혔을 시간 — 달라졌으면 캡처하고 확인 키로 넘긴다
            cur = c.frame[R].copy()
            for _ in range(40):  # 아직 글이 찍히는 중이면(영역이 바뀌는 중) 멈출 때까지 더 기다린다
                c.run(6)
                nxt = c.frame[R].copy()
                moving = int((np.abs(nxt.astype(int) - cur.astype(int)).sum(axis=2) > 0).sum())
                cur = nxt
                if moving < 40:
                    break
            if (
                last is None
                or int((np.abs(cur.astype(int) - last.astype(int)).sum(axis=2) > 0).sum()) > 60
            ):
                shots += 1
                c.shot(str(outdir / f"{tag}_{shots:02d}.png"))
                last = cur
                maxf = min(maxf + 600, 20000)  # 쪽이 계속 나오는 긴 대화는 시간을 더 준다
            c.hold("c")
            c.run(5)
            c.hold("")
    return shots, "시간초과"


def new_game_state(c, cache: Path) -> bytes:
    """새 게임 → 오프닝 자막 → 첫 필드(왕좌의 방) 대사가 끝난 상태. 🔴 디버그 세이브(엘아스타 필드)에서는 대사창이 HUD 칸(오른쪽 아래 작은 상자)으로 뜬다 —
    창 기하가 씬 맥락에서 정해지므로 **씬 안**에서 부른다. 같은 롬이면 상태를 캐시한다."""
    import hashlib

    tag = hashlib.sha1(BS.ROM.read_bytes()).hexdigest()[:10]
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


def main() -> None:
    args = sys.argv[1:]
    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "sweep" / "scene"
    sel, limit, i = [], None, 0
    while i < len(args):
        if args[i] == "--out":
            out, i = Path(args[i + 1]), i + 2
        elif args[i] == "--limit":
            limit, i = int(args[i + 1]), i + 2
        else:
            sel.append(args[i])
            i += 1
    out.mkdir(parents=True, exist_ok=True)
    rom = BS.ROM.read_bytes()
    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v.to_bytes(2, "big"): k for k, v in codes.items() if isinstance(v, int)}
    c = headless.Core(str(BS.ROM))
    armed = new_game_state(c, out)
    tsv = out / "index.tsv"
    if not tsv.exists():
        tsv.write_text("모듈\t오프셋\t문안\t캡처\t상태\n", encoding="utf-8")
    mods = built_modules(rom)
    done_f = out / "done.txt"  # 끝낸 모듈 — 묶음이 시간 제한에 잘려도 다음 묶음이 이어 받는다
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    for bi, k, m in mods:
        key = f"{bi:03d}-{k}"
        if (sel and key not in sel) or key in done:
            continue
        mod = scene.parse_module(m)
        # 🔴 한글(또는 「…」)이 실제로 든 스트림만 — parse_module 이 코드 바이트(`40e7 46df` 따위)를 글로 읽은 가짜 스트림이 섞여 있다(캡처의 15% 가 빈 창·깨진 화면)
        def real(st):
            t = korean(b"".join(x.raw for x in st.tokens if x.kind == "text"), rev)
            return sum(1 for ch in t if "가" <= ch <= "힣") >= 2 or "…" in t

        todo = [(o, st) for o, st in sorted(mod.streams.items()) if real(st)]
        if limit:
            todo = todo[:limit]
        c.load_state(armed)
        c.poke(MOD_AT, m)
        for n, (o, st) in enumerate(todo):
            if (
                n
            ):  # 스트림마다 상태를 되돌린다 — 끝난 뒤 이벤트(암전·이동)가 다음 스트림에 번지지 않게
                c.load_state(armed)
                c.poke(MOD_AT, m)
            txt = korean(b"".join(t.raw for t in st.tokens if t.kind == "text"), rev)
            d = out / key
            d.mkdir(exist_ok=True)
            cnt, status = say(c, MOD_AT + o, d, f"{o:04x}")
            with tsv.open("a", encoding="utf-8") as f:
                f.write(f"{key}\t{o:04x}\t{txt.replace(chr(10), ' ')[:80]}\t{cnt}\t{status}\n")
        with done_f.open("a") as f:
            f.write(key + "\n")
        print(key, len(todo), flush=True)


if __name__ == "__main__":
    main()
