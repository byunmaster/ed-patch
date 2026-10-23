"""조사 훅 「마지막 이름」 바이트($FF1A5E)가 **훅 말고는 아무도 안 쓰는** 빈 RAM 인지 동적으로 본다.

    python3 tools/lastname_watch.py [--out FILE]

방법: 시험 롬 사본에서 조사 훅의 쓰기 두 곳(`move.b d0,$FF1A5E` · `move.b (a3),$FF1A5E`)이 가리키는 주소를 **다른 빈 칸($FF1A5C)** 으로 바꾼다 — 그러면 $FF1A5E 는 훅이
더는 안 건드리니 게임이 쓰면 0 이 아닌 값이 보인다. 그 사본으로 새 게임(부팅·왕좌의 방) → 필드 이동·메뉴(세이브 화면) → 전투(일반 몬스터·보스)를 프레임마다 읽는다.
⚠ 쓴 PC 를 잡는 감시가 아니라 **프레임마다 표집**이다(한 프레임 안에서 썼다 되돌리는 쓰기는 못 잡는다) · 상점·세이브 실행·로드는 못 돌렸다(결과표에 적는다).
"""

import ctypes as C
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import common
import headless
import scene_sweep as S

WATCH, ALT = 0xFF1A5E, 0xFF1A5C


def patched_rom() -> Path:
    rom = bytearray(BS.ROM.read_bytes())
    old = struct.pack(">I", WATCH)
    new = struct.pack(">I", ALT)
    n = 0
    # 훅 본문(꼬리 영역, josa-code)의 모든 $FF1A5E 긴 참조를 ALT 로 — 쓰기·읽기 모두(읽기도 ALT 에서 하니 훅은 정상 동작한다)
    i = -1
    while True:
        i = rom.find(old, i + 1)
        if i < 0:
            break
        if i >= 0x1F0000 - 0x1000:  # 꼬리(josa-code) 안쪽만 — 원판 코드의 우연한 일치는 안 건드린다
            rom[i : i + 4] = new
            n += 1
    rom[0x18E:0x190] = struct.pack(">H", common.header_checksum(bytes(rom)))
    p = Path("/tmp/claude-0/sp/lastname-watch.bin")
    p.write_bytes(bytes(rom))
    print(f"훅 안의 $FF1A5E 참조 {n}곳을 $FF1A5C 로 바꾼 사본 {p}")
    return p


def main() -> None:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    p = patched_rom()
    c = headless.Core(str(p))
    base = c.ram_ptr
    log: list[str] = []
    seen: dict[str, set[int]] = {}
    phase = ["boot"]
    frames = {"n": 0}

    def sample() -> None:
        v = C.string_at(base + (WATCH & 0xFFFF ^ 1), 1)[0]
        frames["n"] += 1
        if v:
            seen.setdefault(phase[0], set()).add(v)

    orig_run = c.run

    def run(n: int = 1) -> None:
        for _ in range(n):
            orig_run(1)
            sample()

    c.run = run  # type: ignore[method-assign]
    # 1) 새 게임 → 왕좌의 방(대사 이벤트 포함)
    phase[0] = "새 게임·왕좌의 방 이벤트"
    st = S.new_game_state(c, Path("/tmp/claude-0/sp"))
    # 2) 필드 이동·메뉴(세이브 화면)
    phase[0] = "필드 이동·메뉴"
    c.load_state(st)
    run(30)
    for d, k in [("down", 50), ("right", 40), ("left", 40), ("up", 40)]:
        c.hold(d)
        run(k)
        c.hold("")
        run(10)
    for key in ["b"] + ["down"] * 6 + ["c", "c", "b", "b"]:
        c.press(key, 8, 24)
    # 3) 전투 — 일반 몬스터 몇 블록 + 보스(82)
    armed = BS.boot(c)
    ids = BS.ids()
    for n in (4, 20, 37, 41, 43, 52, 82):
        phase[0] = f"전투 블록 {n}" + (" (보스)" if n == 82 else "")
        c.load_state(armed)
        c.poke(0x1AFF, bytes([ids[n] >> 8]))
        c.poke(0x3606, bytes([ids[n] & 255]))
        c.poke(0xFF1A16, b"\x01")
        c.hold("right")
        run(30)
        c.hold("")
        for f in range(2400):
            run(1)
            if f % 60 == 0:
                c.hold("c")
            elif f % 60 == 6:
                c.hold("")
    lines = [f"감시 주소 ${WATCH:06X} · 표집 {frames['n']:,}프레임"]
    for ph in (
        ["새 게임·왕좌의 방 이벤트", "필드 이동·메뉴"]
        + [k for k in seen if k.startswith("전투")]
        + ["전투"]
    ):
        pass
    for ph, vs in seen.items():
        lines.append(f"  ⚠ {ph}: 0 이 아닌 값 {sorted(vs)} — 훅 말고 누가 쓴다")
    if not seen:
        lines.append("  쓰기 흔적 0 — 훅을 끈 사본에서 $FF1A5E 는 전 구간 0")
    print("\n".join(lines))
    if out:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(1 if seen else 0)


if __name__ == "__main__":
    main()
