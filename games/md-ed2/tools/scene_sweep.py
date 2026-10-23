"""전 씬 대사 일괄 — 헤드리스(`headless.py`) 위에서 `test-battle` 롬의 대사 우편함 `SAY`($FF1A1C)로 스트림을 하나씩 띄워 화면을 남긴다.

    ED_BUILD_TAG=test-battle python3 tools/test_battle.py          # 후크 롬(대사 우편함 포함)
    python3 tools/scene_sweep.py [BBB-K | BBB-K:오프셋 ...] [--out DIR] [--limit N]   # 오프셋을 주면 그 스트림만(고친 창 재촬영)

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
MSG_SPEED_AT = 0xFF1B05  # 시스템 설정 「메시지속도」 — 0 빠름 · 1 보통 · 2 느림 · 3 멈춤(한 번에 표시). 설정 메뉴 전후 RAM 비교로 찾음(10-19)


def set_speed(c, v: int | None = None) -> None:
    """메시지 속도 — 인자 없으면 환경변수 `MSG_SPEED`(0 빠름·1 보통·2 느림·3 멈춤), 그것도 없으면 **멈춤**(3: 글이 한 번에 뜬다, 마스터 10-19).
    멈춤 표본 검사(`speed_check.py`): 새 롬 79쪽 중 보통과 다른 15쪽·원판 41쪽 중 12쪽은 전부 ▼ 대기 커서 위상 차(글자 같음) — 결함 후보 0."""
    if v is None:
        import os

        v = int(os.environ.get("MSG_SPEED", MSG_STOP))
    c.poke(MSG_SPEED_AT, bytes([v]))


MSG_STOP = 3


def speed_for(st) -> int | None:
    """스트림 하나의 속도 — `end 06`(번호 찍고 뒤 글로 이어짐)으로 끝나는 조각은 멈춤에서 키 대기 없이 곧바로 이어 닫혀 글이 한 프레임도 안 남는다
    (표본 3/32, 원판도 같은 조각은 0쪽) → 그런 조각만 보통 속도로 찍는다."""
    t = st.tokens[-1] if st.tokens else None
    return 1 if t is not None and t.kind == "end" and t.code == 0x06 else None


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


def _ink(frame) -> int:
    """대사 영역의 글자색(흰색·주황) 픽셀 수 — `blank_pages.ink` 와 같은 잣대."""
    a = np.asarray(frame).astype(int)[146:206, 36:292]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    white = (r > 215) & (g > 215) & (b > 215)
    orange = (r > 215) & (g > 140) & (g < 215) & (b < 120)
    return int(white.sum() + orange.sum())


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
    base = c.frame[R].copy()
    cand, cand_ink = (
        None,
        -1,
    )  # 메시지 속도 「멈춤」: 글이 한 번에 뜨고 키 대기 없이 닫히는 스트림은 90프레임 주기에 못 잡힌다 — 글이 뜬 마지막 멈춘 화면을 남겨 둔다
    f = -1
    while f < maxf:
        f += 1
        c.run(1)
        if (
            shots == 0 and f < 400
        ):  # 한 프레임씩 — 「멈춤」은 글이 뜨자마자 창이 닫힐 수 있다(글이 있던 마지막 화면을 남긴다)
            now = c.frame[R]
            if int((np.abs(now.astype(int) - base.astype(int)).sum(axis=2) > 0).sum()) > 200:
                # 글자가 가장 많이 보이는 프레임을 남긴다 — 마지막 프레임은 창이 닫히는 중이라 줄이 반쯤 잘려 있었다(10-20 qa 못 읽음 7행)
                ink = _ink(c.frame)
                if cand is None or ink >= cand_ink:
                    cand, cand_ink = c.frame.copy(), ink
        if not c.ram(BUSY, 1)[0]:
            if shots == 0 and cand is not None:
                from PIL import Image

                Image.fromarray(cand).save(str(outdir / f"{tag}_01.png"))
                return 1, "끝(키 대기 없이 닫힘)"
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
    modsel = {x.split(":")[0] for x in sel}
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
        if (sel and key not in modsel) or key in done:
            continue
        mod = scene.parse_module(m)

        # 🔴 한글(또는 「…」)이 실제로 든 스트림만 — parse_module 이 코드 바이트(`40e7 46df` 따위)를 글로 읽은 가짜 스트림이 섞여 있다(캡처의 15% 가 빈 창·깨진 화면)
        def real(st):
            t = korean(b"".join(x.raw for x in st.tokens if x.kind == "text"), rev)
            return sum(1 for ch in t if "가" <= ch <= "힣") >= 2 or "…" in t

        todo = [(o, st) for o, st in sorted(mod.streams.items()) if real(st)]
        pick = {int(x.split(":")[1], 16) for x in sel if x.startswith(key + ":")}
        if pick:
            todo = [(o, st) for o, st in todo if o in pick]
        if limit:
            todo = todo[:limit]
        c.load_state(armed)
        set_speed(c, speed_for(mod.streams[todo[0][0]]) if todo else None)
        c.poke(MOD_AT, m)
        for n, (o, st) in enumerate(todo):
            if (
                n
            ):  # 스트림마다 상태를 되돌린다 — 끝난 뒤 이벤트(암전·이동)가 다음 스트림에 번지지 않게
                c.load_state(armed)
                set_speed(c, speed_for(st))
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
