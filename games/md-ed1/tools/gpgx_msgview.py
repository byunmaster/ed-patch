"""전 씬 대사 일괄 — 디버그 롬의 「대사 보기」(우편함 `$FFE800`)를 헤드리스 genesis_plus_gx 로 돌린다.

씬 N 을 워프로 올리면(`$FF343C` = N, 모듈이 RAM `0xFF6650` 에 풀린다) 그 모듈의 모든 스트림이 RAM 에 있다.
`build.py` 의 디버그 스텁(`DEBUG_VIEW_*`)이 우편함의 스트림 주소·창 종류(a5)를 읽어 엔진 메시지 함수를 부르므로,
걸어가 말 걸기 없이 스트림마다 **실제 창**에 띄워 쪽(페이지)마다 PNG 로 낸다(화자 이름창·조사 훅·줄바꿈은 엔진이 그린다).

    python3 gpgx_msgview.py --rom <디버그 롬> --out <폴더> [--scenes 0-224] [--crop]

산출: `<out>/s<씬>_<오프셋>_<쪽>.png` · `index.json`(씬·스트림·쪽 수·상태·우리 문안 앞부분).
상태: ok · stuck(쪽을 넘겨도 안 끝남) · notrigger(걸음이 안 잡힘).
"""

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itertools

import archives
import scene
from gpgx_battle import boot_to_field, warp, win_hash
from gpgx_run import Genesis

BOX = 0xE800  # 우편함(시스템 램 $FFE800) — 스트림 주소 .l · 창 종류 .w · 끝 표식 .b($FFE806)
MODULE_BASE = 0xFF6650
DEFAULT_A5 = 0x85E3
STATE_NAME = "field_L1.state"
GAME = Path(__file__).resolve().parent.parent


def a5_by_target(b: bytes) -> dict[int, int]:
    """`lea x(pc),a1 [46df] movea.w #MSG,a5` — 스트림 시작 → 창 종류."""
    out = {}
    for m in re.finditer(rb"\x43\xfa(..)(?:\x46\xdf)?\x3a\x7c(..)", b, re.DOTALL):
        t = m.start() + 2 + struct.unpack(">h", m.group(1))[0]
        out.setdefault(t, struct.unpack(">H", m.group(2))[0])
    return out


def streams_of(rom: bytes, n: int):
    """(빌드 모듈 안 오프셋, 창 종류, 우리 문안) 목록 — 정본 JSON 의 스트림과 정렬 순서로 짝짓는다(개수가 다르면 문안은 비운다)."""
    _s, b, _e = archives.blocks(rom, archives.ARCHIVES["script"][0])[n]
    mod = scene.parse_module(b)
    offs = sorted(mod.streams)
    a5 = a5_by_target(b)
    p = GAME / "script" / f"{n:03d}.json"
    ours = []
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))["streams"]
        ours = [d[k].get("ours", "") for k in sorted(d, key=lambda x: int(x, 16))]
    if len(ours) != len(offs):
        ours = [""] * len(offs)
    return [(o, a5.get(o, DEFAULT_A5), ours[i]) for i, o in enumerate(offs)], len(b)


ITEM_BUF = 0x2028  # 엔진 메시지 버퍼 — `<0e>`(품목 이름)이 이 문자열(끝 06)을 찍는다
ITEM_NAMES = (
    "마법의 검",
    "마법 지팡이",
)  # 끝소리 있는 이름 · 없는 이름 — 조사 훅 두 갈래를 다 본다


def item_bytes(name: str) -> bytes:
    """한글 코드(2B)·ASCII 로 문자열을 엔진 글자 코드로 — 끝 06."""
    codes = json.loads((GAME / "textmap" / "hangul_codes.json").read_text(encoding="utf-8"))
    out = b""
    for ch in name:
        out += struct.pack(">H", codes[ch]) if ch in codes else ch.encode("ascii")
    return out + b"\x06"


def trigger(g: Genesis, ptr: int, a5: int):
    g.poke(BOX, struct.pack(">IH", ptr, a5))
    g.poke(BOX + 6, b"\x00")


def view_stream(
    g: Genesis,
    state: bytes,
    ptr: int,
    a5: int,
    out: Path,
    stem: str,
    maxf: int = 3000,
    item: str | None = None,
):
    """상태를 복원해 스트림 하나를 띄운다. 반환 (쪽 수, 상태)."""
    g.load_state(state)
    trigger(g, ptr, a5)
    ib = (
        item_bytes(item) if item else None
    )  # 게임이 매 프레임 버퍼를 다시 채우므로 매 프레임 덮어쓴다
    # 패드 읽기 자리(`$226D4`)가 매 프레임 우편함을 본다 — 비면 스텁이 불렀다.
    started = False
    for _ in range(90):
        if ib:
            g.poke(ITEM_BUF, ib)
        g.run(1)
        if g.ram(BOX, 4) == b"\x00\x00\x00\x00":
            started = True
            break
    if not started:
        return 0, "notrigger"
    pages, last_shot, idle_press = 0, None, 0
    # 글이 한 글자씩 찍히는 동안엔 해시가 계속 바뀌고, 쪽이 다 찍히면 대기 커서(▼)가 깜빡여 해시가 두 값 사이를 오간다.
    # 그래서 「최근 60프레임이 두 값이고 오간 횟수 ≥ 4」를 쪽 완성으로 본다. 커서가 없는 쪽(끝 쪽 등)은 한 값으로 150프레임 멈추면 찍는다.
    recent: list[str] = []
    for _f in range(maxf):
        if ib:
            g.poke(ITEM_BUF, ib)
        g.run(1)
        if g.ram(BOX + 6, 1) == b"\x01":
            return pages, "ok"
        recent.append(win_hash(g))
        del recent[:-150]
        tail = recent[-60:]
        blink = (
            len(tail) == 60
            and len(set(tail)) == 2
            and sum(a != b for a, b in itertools.pairwise(tail)) >= 4
        )
        flat = len(recent) == 150 and len(set(recent)) == 1
        if blink or flat:
            key = frozenset(tail)
            if last_shot is None or not (key & last_shot):
                pages += 1
                g.shot(out / f"{stem}_{pages}.png")
                last_shot = key
                idle_press = 0
            else:
                idle_press += 1
                if idle_press > 6:
                    return pages, "stuck"
            g.press("c", 8, 4)
            recent.clear()
    return pages, "stuck"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenes", default="0-224")
    ap.add_argument("--save", default="/root/save/md-ed1/md-ed1-slots.sav")
    ap.add_argument("--state")
    ap.add_argument(
        "--msg-speed",
        type=int,
        help="시스템 메뉴 메시지속도 바이트($FF1B05: 0 빠름 · 1 보통 · 2 느림 · 3 멈춤)",
    )
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rom = Path(a.rom).read_bytes()
    g = Genesis(a.rom, srm=Path(a.save).read_bytes())
    sp = Path(a.state) if a.state else out / STATE_NAME
    # 🔴 상태 파일은 롬을 바꿔도 옛 RAM(글리프 표·문안·코드)을 되살린다 — 만든 롬 sha1 을 옆에 적고 다르면 새로 만든다(ps1-ed3 10-20)
    rom_sha = hashlib.sha1(Path(a.rom).read_bytes()).hexdigest()
    shp = sp.with_name(sp.name + ".sha1")
    if sp.exists() and (not shp.exists() or shp.read_text().strip() != rom_sha):
        print(f"상태 파일을 만든 롬이 지금 롬과 다르다 — 새로 만든다 ({sp})", flush=True)
        sp.unlink()
    if sp.exists():
        base = sp.read_bytes()
    else:
        boot_to_field(g)
        if a.msg_speed is not None:
            g.poke(0x1B05, bytes([a.msg_speed]))
        base = g.save_state()
        sp.write_bytes(base)
        shp.write_text(rom_sha)
    tab = struct.unpack(">225H", rom[0x134DDC : 0x134DDC + 450])
    scenes = []
    for part in a.scenes.split(","):
        if "-" in part:
            x, y = part.split("-")
            scenes += list(range(int(x), int(y) + 1))
        else:
            scenes.append(int(part))
    ip = out / "index.json"
    index = json.loads(ip.read_text()) if ip.exists() else {}
    for n in scenes:
        if str(n) in index and index[str(n)].get("done"):
            continue
        rows, _blen = streams_of(rom, n)
        if not rows:
            index[str(n)] = {"done": True, "note": "스트림 없음", "streams": []}
            continue
        g.load_state(base)
        _s, mb, _e = archives.blocks(rom, archives.ARCHIVES["script"][0])[n]
        okw = warp(g, tab[n], expect=mb[:32])
        if a.msg_speed is not None:  # 워프(SAVE→LOAD)가 세이브의 설정값으로 되돌리므로 워프 뒤에 다시 쓴다
            g.poke(0x1B05, bytes([a.msg_speed]))
        cur = int.from_bytes(g.ram(0x343C, 2), "big")
        if not okw or cur != n:
            index[str(n)] = {"done": True, "note": f"워프 실패(씬 {cur})", "streams": []}
            print(
                f"scene {n}: 워프 실패 → {cur} (모듈 머리 {'일치' if okw else '불일치'})",
                flush=True,
            )
            continue
        sstate = g.save_state()
        res = []
        for o, a5, ours in rows:
            # 품목 이름 자리(<0e>)가 있는 스트림은 이름 둘(끝소리 유·무)로 두 번 — 나머지는 한 번
            items = ITEM_NAMES if "<0e>" in ours else (None,)
            for vi, item in enumerate(items):
                stem = f"s{n:03d}_{o:04x}" + (f"v{vi}" if len(items) > 1 else "")
                pages, st = view_stream(g, sstate, MODULE_BASE + o, a5, out, stem, item=item)
                res.append(
                    {
                        "off": f"{o:04x}",
                        "a5": f"{a5:04x}",
                        "item": item,
                        "pages": pages,
                        "status": st,
                        "ours": ours[:60],
                    }
                )
        index[str(n)] = {"done": True, "streams": res}
        ok = sum(r["status"] == "ok" for r in res)
        print(f"scene {n}: {ok}/{len(res)} ok", flush=True)
        ip.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
