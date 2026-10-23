"""조사 훅 「마지막 이름」 바이트($FF1A5E) 주변 `$FF1A58~$FF1A67` 의 **쓰기 PC 감시**(md-ed1 의 wshim 방식 — 작업 RAM 페이지를 읽기 전용으로 잠가 쓰기를 명령 단위로 잡는다).

    python3 tools/lastname_wwatch.py [--out FILE]

감시기 본체 `wshim.c`·`wlib.py` 는 md-ed1 세션의 scratchpad 도구를 복사해 쓴다(`/tmp/claude-0/sp/ww`, 저장소에 안 올린다 — 커밋 금지 바이너리·경로). 68000 PC 는 코어 내부 구조체를 메모리 스캔으로 찾아 읽는다.
시나리오: 새 게임(오프닝·왕좌의 방) → 필드 이동 → 메뉴(주문·사용·장비·상태·기타→세이브 화면) → 전투(일반 몬스터·보스 82) → 코드 영역 문안(상점·시스템 메시지 스트림 샘플).
결과는 쓴 PC 별 집계 — 우리 훅(`josa-code` 꼬리 안)의 쓰기만 `$FF1A5E` 에 있어야 하고, 그 밖의 PC 가 $FF1A58~$FF1A67 에 쓰면 표에 나온다.
⚠ 한계: 상점 구매·세이브 실행·로드 확인 창은 시나리오에 없다(메시지 서비스까지만) · Z80·코어 내부 memcpy 쓰기는 호스트 PC 만 믿을 수 있다.
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/claude-0/sp/ww")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_sweep as BS
import headless
import scene_sweep as S
import sysmsg
import wlib

LO, HI = 0x1A58, 0x1A68
NAMES = {0x1A5E: "LASTNAME($FF1A5E)"}


class G:
    """wlib.Watch 가 원하는 하니스 모양 — `_mem(2)` = 작업 RAM (호스트 포인터, 크기)."""

    def __init__(self, core):
        self.core = core

    def _mem(self, i):
        assert i == 2
        return self.core.ram_ptr, self.core.ram_size


def decode(r):
    pc, ppc, off, bef, aft, rip, code, b2, a2 = r
    sz, txt = wlib.width(code)
    sz = sz or 16
    touched = sorted(((LO + off + k) ^ 1) for k in range(sz))
    return dict(
        ppc=ppc, pc=pc, sz=sz, txt=txt, m68=[t for t in touched if LO <= t < HI], bef=bef, aft=aft
    )


def main() -> None:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    rom_path = BS.ROM
    rom = rom_path.read_bytes()
    c = headless.Core(str(rom_path))
    w = wlib.Watch(G(c), lo=LO, hi=HI)
    for nm in ("poke", "load_state"):  # 하니스의 자기 쓰기는 감시 밖
        f = getattr(c, nm)

        def mk(f):
            def h(*a, **k):
                w.enable(False)
                try:
                    return f(*a, **k)
                finally:
                    w.enable(True)

            return h

        setattr(c, nm, mk(f))
    w.enable(True)
    phases: dict[str, list] = collections.OrderedDict()
    cur = ["boot"]
    mark = [0]

    def phase(n):
        flush()
        cur[0] = n

    def flush():
        r = w.recs()
        phases.setdefault(cur[0], []).extend(r[mark[0] :])
        mark[0] = len(r)
        if len(r) > 150000:
            w.clear()
            mark[0] = 0

    # 1) 새 게임 → 왕좌의 방
    phase("새 게임·왕좌의 방")
    st = S.new_game_state(c, Path("/tmp/claude-0/sp/ww"))
    # 2) 필드 이동
    phase("필드 이동")
    c.load_state(st)
    c.run(30)
    for d, k in [("down", 50), ("right", 40), ("left", 40), ("up", 40), ("down", 40), ("left", 40)]:
        c.hold(d)
        c.run(k)
        c.hold("")
        c.run(10)
    # 3) 메뉴 — 주문·사용·장비·버린다·상태·기타(SAVE/LOAD/시스템/전투설정)
    phase("메뉴")
    for i in range(6):
        c.press("b", 8, 24)
        for _ in range(i + 1):
            c.press("down", 8, 12)
        for k in ["c", "c", "b", "b", "b"]:
            c.press(k, 8, 24)
    for key in ["b"] + ["down"] * 7 + ["c", "c", "c", "b", "b", "b", "b"]:  # 기타 → SAVE 칸에서 c
        c.press(key, 8, 24)
    c.run(60)
    # 4) 코드 영역 문안 스트림 샘플(상점·시스템·아이템·주문 메시지 서비스)
    phase("코드 영역 문안(상점·시스템 메시지 샘플)")
    streams = sorted(sysmsg.streams(rom).items())[::3]
    for a, _e in streams:
        c.load_state(st)
        S.say(c, a, Path("/tmp/claude-0/sp/ww/shots"), f"{a:06x}", maxf=300)
    # 5) 전투 — 일반 6블록 + 보스
    armed = BS.boot(c)
    ids = BS.ids()
    for n in (4, 20, 37, 41, 43, 52, 82):
        phase(f"전투 블록 {n}" + (" (보스)" if n == 82 else ""))
        c.load_state(armed)
        c.poke(0x1AFF, bytes([ids[n] >> 8]))
        c.poke(0x3606, bytes([ids[n] & 255]))
        c.poke(0xFF1A16, b"\x01")
        c.hold("right")
        c.run(30)
        c.hold("")
        for f in range(2400):
            c.run(1)
            if f % 60 == 0:
                c.hold("c")
            elif f % 60 == 6:
                c.hold("")
    phase("끝")
    lines = [
        f"감시 ${0xFF0000 + LO:06X}~${0xFF0000 + HI - 1:06X} · 쓰기 기록 {sum(len(v) for v in phases.values()):,}건 · 경고 PC 폴트 {wlib.sh.shim_faults()}"
    ]
    # 우리 훅 코드 범위(josa-code, 꼬리)
    hook_lo = 0x1F0000 - 0x1000
    agg = collections.OrderedDict()
    for ph, recs in phases.items():
        for r in recs:
            d = decode(r)
            for t in d["m68"]:
                key = (t, d["ppc"], d["txt"].split()[0])
                agg.setdefault(key, [0, set(), set()])
                agg[key][0] += 1
                agg[key][1].add(d["aft"])
                agg[key][2].add(ph)
    outside = 0
    byval = collections.OrderedDict()  # (PC, 값) → 단계들 — 훅이 번호 아닌 값을 쓰는 단계를 가린다
    for ph, recs in phases.items():
        for r in recs:
            d = decode(r)
            for t in d["m68"]:
                if t == 0x1A5E:
                    byval.setdefault((d["ppc"], d["aft"]), collections.Counter())[ph] += 1
    for (t, ppc, op), (n, vals, phs) in sorted(agg.items()):
        mine = ppc >= hook_lo
        tag = "우리 훅" if mine else "⚠ 원판/그 밖"
        outside += not mine
        lines.append(
            f"  ${0xFF0000 + t:06X} ← PC {ppc:#08x}({tag}) {n:,}회 값 {sorted(vals)[:6]} · {', '.join(sorted(phs))[:80]}"
        )
    lines.append("$FF1A5E 에 쓴 값 — (PC, 값) → 단계별 횟수")
    for (ppc, v), cnt in sorted(byval.items()):
        lines.append(f"  PC {ppc:#08x} 값 {v}: " + ", ".join(f"{k} {n}" for k, n in cnt.items()))
    lines.append(f"결과: 우리 훅 밖에서 쓴 PC {outside}곳")
    print("\n".join(lines))
    if out:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
