"""전투 문안의 **부르는 쪽 문맥** — 어느 몬스터 행동 루틴이 어떤 분기를 지나 그 조각의 `lea` 에 닿는가(정적, 68000 흐름 추적) + 그 문맥을 전투 화면에 되살리는 러너.

    python3 tools/battle_ctx.py [블록 …]               # 표 → work/battle_ctx.tsv (인자 없으면 전 블록)
    python3 tools/battle_ctx.py --run 블록:오프셋 …     # 그 문맥을 시험 롬 전투에 재현(에뮬 하나 — `sh scripts/capture.sh …` 로), 되는 전략을 battle_ctx_ledger.json 에 남긴다
    python3 tools/battle_ctx.py --edges                # 재현한 화면의 글자 오른끝(합성 줄 넘침) → work/battle_ctx_edges.tsv
    python3 tools/battle_ctx.py [--kill] --probe 블록 …  # 진입 루틴이 자연 전투에서 불리는지(표지 프로브) — `--kill` 은 몬스터가 쓰러지게

전투 블록 = 헤더 워드 6(`[?][자료 A][자료 B][코드 데이터][점프 표][길이]` — ⚠ 빌더가 한글 블록의 다섯째 워드(표 시작)를 새 길이로 덮어 70블록은 `table_start` 가 원판 헤더로 되살린다)
+ 몬스터 레코드(0x40 간격) + 자료 A + **자료 B** + 코드. 점프 표(`표 시작 + 워드` = 루틴 시작)는 블록이 가진 루틴 전부(서브루틴 포함)다.
엔진 진입은 둘이다 — **자료 B**: 몬스터 종류(`&7 − 4`)로 줄(워드 4개)을 고르고 사건 칸(슬롯 0 = 행동, 1~3 = 훅 — 대개 `rts`)의 워드를 부른다(`0x29E5E`·`0x29EA6`) ·
**자료 A**: 사건 훅 — 엔진 호출처가 오프셋(0xa·0xc·0xe·0x10·0x12·0x14)을 넘겨 `0x29E4E` 로 부른다(몬스터가 쓰러질 때·승리 등, 자연 자동 전투에선 0회 — 몬스터 HP 를 고정하고 공격력 1 이라 사건이 안 난다).
둘 다 `$FF1853` 비트 6 이 서 있어야 불린다(전투 중엔 서 있음).
`lea x(pc),aN` 이 문안(`battle.refs`)을 가리키니, 진입 루틴 → `lea` 까지 가장 짧은 길의 **조건 분기**가 곧 그 문안이 나오는 조건이다.
분기 앞 비교(`cmpi`·`btst`·`jsr` 뒤 플래그)는 몬스터 상태·엔진 호출 결과라 값으로 풀지 않고, 재현할 땐 **길 위 분기만 고정**한다(taken → `bra`, fall → `nop`).

분류(`상태`): `B` 자료 B 가 가리키는 루틴에서 닿음 · `A` 자료 A(사건 훅)가 가리키는 루틴에서 닿음 · `T` 점프 표에만 있고 B·A 어느 쪽도 안 가리키는 루틴에서만 닿음(미참조) ·
`죽음` 어느 루틴에서도 안 닿음(`lea` 가 든 조각의 시작을 가리키는 워드·분기가 블록 어디에도 없음 = 미사용 코드) · `연쇄` `lea` 없이 다른 조각의 call/goto 로 닿는 조각(부모 조각의 문맥으로 닿는다).
"""

import re
import struct
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import common

NOTBR = ("btst", "bchg", "bclr", "bset", "bf")
_md = None


def _disasm():
    global _md
    if _md is None:
        from capstone import CS_ARCH_M68K, CS_MODE_M68K_000, Cs

        _md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
    return _md


def built_rom() -> bytes:
    """한글 빌드 롬(시험 롬과 전투 블록이 같다) — 재배치된 조각의 오프셋은 이쪽 것이다(원판 롬으로 재면 어긋난다)."""
    import battle_sweep as BS

    return BS.ROM.read_bytes()


def table_start(b: bytes, orig: bytes) -> int:
    """점프 표 시작 — 원판 헤더의 다섯째 워드(`t[4]`)에 레코드 구역이 자란 만큼(`t[1]` 차)을 더한다. 빌더가 한글 블록의 다섯째 워드를 새 길이로 덮어(70블록) 헤더로는 못 읽는다."""
    return battle.sections(orig)[4] + battle.sections(b)[1] - battle.sections(orig)[1]


def entries(b: bytes, t4: int) -> tuple[dict[int, list[int]], dict[int, list[int]], list[int]]:
    """({진입 주소 → [자료 B 인덱스…]}, {진입 주소 → [자료 A 오프셋…]}, 점프 표 루틴 주소 목록).
    자료 A 의 워드 중 점프 표 루틴을 가리키는 것은 **전투 사건 훅**이다(엔진이 `$FF346C`(블록 기준) + 구역 A + 오프셋의 워드를 읽어 부른다 — 예: `0x27FCC` 가 +0x10)."""
    t = battle.sections(b)
    t = (*t[:4], t4)
    bw: dict[int, list[int]] = {}
    for i in range((t[3] - t[2]) // 2):
        w = struct.unpack(">H", b[t[2] + 2 * i : t[2] + 2 * i + 2])[0]
        if t[4] <= w < len(b):
            bw.setdefault(w, []).append(i)
    tab, p, lim = [], t[4], None
    while p < len(b) - 1 and (lim is None or p < lim):
        a = t[4] + struct.unpack(">H", b[p : p + 2])[0]
        if lim is None:
            lim = a
        if not t[4] <= a < len(b):
            break
        lim = min(lim, a)
        tab.append(a)
        p += 2
    aw: dict[int, list[int]] = {}
    for i in range(0, t[2] - t[1], 2):
        w = struct.unpack(">H", b[t[1] + i : t[1] + i + 2])[0]
        if w in tab:
            aw.setdefault(w, []).append(i)
    return bw, aw, tab


def graph(b: bytes, roots) -> dict:
    """주소 → (크기, 니모닉, 피연산자, [(다음, 종류)]) — 종류: fall · taken · jump · call · ret · loop."""
    md, g, work = _disasm(), {}, list(roots)
    while work:
        a = work.pop()
        while 0 <= a < len(b) and a not in g:
            ins = list(md.disasm(b[a : a + 12], a, count=1))
            if not ins:
                g[a] = None
                break
            i = ins[0]
            m = i.mnemonic.split(".")[0]
            nxt = a + i.size
            mm = re.fullmatch(r"\$([0-9a-f]+)", i.op_str.split(",")[-1].strip())
            tg = int(mm.group(1), 16) if mm else None
            succ, stop = [], False
            if m == "bra":
                succ, stop = ([(tg, "jump")] if tg is not None else []), True
            elif m == "bsr":
                succ = [(nxt, "ret")] + ([(tg, "call")] if tg is not None else [])
            elif m.startswith("db"):
                succ = [(nxt, "fall")] + ([(tg, "loop")] if tg is not None else [])
            elif m[0] == "b" and not m.startswith(NOTBR):
                succ = [(nxt, "fall")] + ([(tg, "taken")] if tg is not None else [])
            elif m in ("rts", "rte", "rtr", "jmp"):
                stop = True
            else:
                succ = [(nxt, "fall")]
            g[a] = (i.size, i.mnemonic, i.op_str, succ)
            work += [s for s, _ in succ if s is not None and s not in g and 0 <= s < len(b)]
            if stop or len(succ) != 1 or succ[0][1] != "fall":
                break
            a = nxt
    return g


def path(g: dict, root: int, target: int):
    """root → target 가장 짧은 길 — [(주소, 다음으로 간 종류)]. 없으면 None."""
    prev = {root: None}
    q = deque([root])
    while q:
        a = q.popleft()
        if a == target:
            out = []
            while prev[a] is not None:
                p, k = prev[a]
                out.append((p, k))
                a = p
            return out[::-1]
        for s, k in (g.get(a) or (0, 0, 0, []))[3]:
            if s in g and s not in prev:
                prev[s] = (a, k)
                q.append(s)
    return None


def reads_monster(g: dict, a: int, depth: int = 5) -> bool:
    """분기 바로 앞(곧은 길 5명령 안)에서 몬스터 레코드(`(a2)`)를 읽었고 엔진 호출(`jsr`·`bsr`)은 없나 — 몬스터 상태를 보는 분기만 고정 대상이다."""
    back = {s: x for x, n in g.items() if n for s, k in n[3] if k == "fall"}
    seen = False
    for _ in range(depth):
        a = back.get(a)
        if a is None:
            break
        if g[a][1].startswith(("jsr", "bsr")):
            return False
        seen = seen or "(a2)" in g[a][2]
    return seen


def guard_patches(b: bytes, g: dict, steps, state_only: bool = False) -> list[tuple[int, bytes]]:
    """길 위 조건 분기를 그 길로 고정 — taken 은 `bra`(워드/바이트 꼴 유지), fall 은 `nop`. 전략 둘:
    `전부`(기본) = 길 위 모든 조건 분기 · `상태` = **몬스터 상태**를 보는 분기(`reads_monster`)만.
    둘 다 필요하다 — 서비스 결과·임시 레지스터를 보는 분기까지 고정하면 스택·창 상태가 어긋나 예외가 나는 루틴이 있고(블록 10 훅 2a0: `jsr` 뒤 `bne`·`and.w` 뒤 `beq` 를 고정하면 예외 화면, 상태 분기 둘만 고정하면 문구가 찍힌다),
    반대로 난수·서비스 분기를 고정해야 길이 열리는 루틴도 있다(블록 29 행동 0x174: 상태 분기만으론 안 열린다). 러너는 차례로 시도해 되는 것을 장부에 남긴다."""
    out = []
    for a, k in steps:
        size, mn, _ops, _ = g[a]
        m = mn.split(".")[0]
        if (
            k not in ("taken", "fall")
            or not (m[0] == "b" and not m.startswith(NOTBR))
            or m == "bra"
        ):
            continue
        if state_only and not reads_monster(g, a):
            continue
        if k == "taken":
            out.append((a, bytes([0x60, b[a + 1] if size == 2 else 0x00])))
        else:
            out.append((a, b"\x4e\x71" * (size // 2)))
    return out


def contexts(n: int, bl=None, bo=None) -> list[dict]:
    """블록 n 의 문안 조각마다 {off, lea, root, 상태, slots, guards, patches}. 조각이 `lea` 로 안 불리면(연쇄·고정 참조) 빈 목록 대신 `상태` 만 채운다."""
    b = (bl or list(battle.blocks(built_rom())))[n][1]
    t4 = table_start(b, (bo or list(battle.blocks(common.rom())))[n][1])
    bw, aw, tab = entries(b, t4)
    g = graph(b, set(bw) | set(aw) | set(tab))
    hooks = sorted(set(bw) | set(aw))
    rows = []
    for off, e in sorted(battle.refs(b).items()):
        if not e["lea"]:
            rows.append({"off": off, "상태": "연쇄", "lea": None, "root": None})
            continue
        best = None
        for lp in e["lea"]:
            for root in hooks + [a for a in tab if a not in bw and a not in aw]:
                st = path(g, root, lp)
                if st is not None:
                    c = {
                        "off": off,
                        "lea": lp,
                        "root": root,
                        "상태": "B" if root in bw else ("A" if root in aw else "T"),
                        "slots": bw.get(root, []),
                        "hookA": aw.get(root, []),
                        "guards": [
                            (a, g[a][1], g[a][2], k)
                            for a, k in st
                            if k in ("taken", "fall")
                            and g[a][1].startswith("b")
                            and not g[a][1].startswith(NOTBR)
                        ],
                        "patches": guard_patches(b, g, st),
                        "patches_state": guard_patches(b, g, st, True),
                    }
                    if best is None or (c["상태"], len(c["guards"])) < (
                        best["상태"],
                        len(best["guards"]),
                    ):
                        best = c
                    break
        rows.append(best or {"off": off, "상태": "죽음", "lea": e["lea"][0], "root": None})
    return rows


LEDGER = (
    common.GAME_DIR / "battle_ctx_ledger.json"
)  # {"블록:오프셋": {"전략": …, "kill": …, "결과": "예"|"아니오"}} — 재현이 된 길을 남겨 다음 촬영이 바로 쓴다
STRATEGIES = {
    "B": ["전부", "상태", "전부+결선", "상태+결선"],
    "A": ["상태", "전부", "자연", "상태@쓰러짐", "전부@쓰러짐"],
    "T": ["전부", "상태"],
}


def run_patch(n: int, c: dict, b: bytes, strategy: str = "전부") -> list[tuple[int, bytes]]:
    """램에 쓸 (블록 안 오프셋, 바이트) — 길 위 분기 고정(`strategy`: 전부 · 상태 · 자연=고정 없음) + (B 의 훅 슬롯 1~3·미참조 T) 몬스터 행동 슬롯 0 을 그 루틴으로.
    전략 이름 = 분기 고정(전부·상태·자연) [+결선].
    엔진은 `(몬스터 종류 & 7) − 4` 로 자료 B 의 줄(워드 4개)을 고르고(`0x29EA6`) 사건 번호로 칸을 고른다 — 슬롯 0 은 매 턴 행동이라 줄마다 슬롯 0 을 걸면 어느 종류든 그 루틴을 돈다.
    자료 B 슬롯 0 이 이미 그 루틴이면 건드리지 않는다. 자료 A 훅(`A`)은 슬롯에 안 옮긴다 — 사건이 나야 불리므로 `kill` 로 돌린다
    (공격력 999 · 몬스터 HP 고정 끔 — 블록 10·20 에서 훅 2a0·4bc 발화 확인, 기본 전투에선 0회).
    ⚠ 사건 훅 칸(자료 A + 오프셋)에 B 루틴을 걸어 억지로 부르는 길은 시험했으나(10:0x4b1 ×6 오프셋) 안 열렸다 — 사건이 나야 한다."""
    if strategy == "자연":
        return []
    strategy, _, ev = strategy.partition("@")
    guards, _, bind = strategy.partition("+")
    ps = list(c["patches_state"] if guards == "상태" else c["patches"])
    t = battle.sections(b)
    # 결선 — 슬롯 0 이 일부 줄(몬스터 종류)에만 있거나 없으면 모든 줄의 슬롯 0 을 그 루틴으로(그 종류가 안 나와도 불리게)
    if ev:  # 사건 이동 — 자연 전투에서 안 나는 훅(0xa·0xc·0xe·0x12)을 **쓰러짐 훅(자료 A + 0x14)** 에 걸어 몬스터가 쓰러질 때 부르게 한다(`kill` 필요)
        ps.append((t[1] + 0x14, struct.pack(">H", c["root"])))
    if c["상태"] != "A" and (bind or not any(i % 4 == 0 for i in c["slots"])):
        ps += [(t[2] + 8 * r, struct.pack(">H", c["root"])) for r in range((t[3] - t[2]) // 8)]
    return ps


def run_contexts(specs: list[str], bl, bo) -> None:
    """문맥을 차례로 재현한다 — 문맥마다 전략을 장부 순서로 시도해 문안이 찍히면 장부에 남기고 다음으로. 부팅은 일반·kill 코어 각각 한 번."""
    import json

    import battle_sweep as BS
    import headless

    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "battle-ctx"
    out.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    idl = BS.ids()
    cores: dict[bool, tuple] = {}

    def core(kill: bool):
        if kill not in cores:
            BS.KILL = kill
            c = headless.Core(str(BS.ROM))
            cores[kill] = (c, BS.boot(c))
        return cores[kill]

    for spec in specs:
        n, off = spec.split(":")
        n, off = int(n), int(off, 0)
        key = f"{n}:{off:#x}"
        row = next(r for r in contexts(n, bl, bo) if r["off"] == off)
        if row["상태"] not in ("B", "A", "T"):
            print(key, f"상태 {row['상태']}: 재현할 문맥이 없다")
            continue
        b = bl[n][1]
        refs = dict(BS.block_streams(None, bl, n))
        kill = row["상태"] == "A"
        known = ledger.get(key, {}).get("전략")
        tried = ledger.get(key, {}).get("시도", [])
        order = [known] if known else [x for x in STRATEGIES[row["상태"]] if x not in tried]
        got = "아니오"
        for strat in order:
            c, armed = core(kill)
            BS.KILL = kill
            keys, shots = set(), []
            ps = run_patch(n, row, b, strat)
            BS.run_block(
                c,
                armed,
                n,
                idl[n],
                out,
                900,
                0,
                keys,
                shots,
                0,
                1,
                None,
                None,
                (b, ps) if ps else None,
            )
            got = "예" if refs.get(off) in keys else "아니오"
            for j, pth in enumerate(shots):
                pth.rename(pth.with_name(f"c{off:04x}_{strat}_{j + 1:02d}.png"))
            print(key, row["상태"], strat, len(shots), got, flush=True)
            tried.append(strat)
            if got == "예":
                ledger[key] = {"전략": strat, "kill": kill, "결과": "예"}
                break
        else:
            ledger[key] = {"전략": None, "kill": kill, "결과": "아니오", "시도": tried}
        LEDGER.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )


EDGE_OK = 291  # 전투 창 한 줄 23.0슬롯의 글자 오른끝 x — 실측 sweep-1031 b02/07 이 288~290(창 안쪽 끝은 306)


def window_edge(png: Path) -> int | None:
    """전투 창(y 180~219 · x 5~306 안쪽)의 글자 픽셀 오른끝 x — 글자가 없으면 None. 창 테두리·바깥은 안 센다."""
    import numpy as np
    from PIL import Image

    reg = np.array(Image.open(png).convert("RGB")).astype(int)[180:220, 5:307, :].max(axis=2)
    xs = np.where((reg > 150).any(axis=0))[0]
    return int(xs.max()) + 5 if len(xs) else None


def edges(out: Path) -> None:
    """재현에 성공한 문맥의 화면 전부에서 글자 오른끝을 재 EDGE_OK 를 넘는 것을 센다(합성 줄 넘침 — 이름 뒤에 이어 붙는 조각은 정적으로 못 잰다) → work/battle_ctx_edges.tsv."""
    import json

    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    rows = ["블록:오프셋\t전략\t화면 수\t오른끝 최대\t판정"]
    for key, v in sorted(
        ledger.items(), key=lambda kv: (int(kv[0].split(":")[0]), int(kv[0].split(":")[1], 0))
    ):
        if v.get("결과") != "예":
            continue
        n, off = key.split(":")
        shots = sorted((out / f"b{int(n):02d}").glob(f"c{int(off, 0):04x}_{v['전략']}_*.png"))
        es = [e for e in (window_edge(p) for p in shots) if e is not None]
        mx = max(es) if es else None
        rows.append(
            f"{key}\t{v['전략']}\t{len(shots)}\t{mx}\t{'넓음' if mx and mx > EDGE_OK else 'ok'}"
        )
    dst = common.WORK / "battle_ctx_edges.tsv"
    dst.write_text("\n".join(rows) + "\n", encoding="utf-8")
    from collections import Counter

    print(Counter(r.split("\t")[-1] for r in rows[1:]), "→", dst)


PROBE = 0xFF1B90  # 진입 표지 — 루틴마다 한 바이트


def probe_patches(b: bytes, t4: int) -> tuple[list[tuple[int, bytes]], list[int]]:
    """훅·진입 루틴의 첫머리를 `move.b #1,$FF1B90+i.l; rts`(10B)로 바꾼다 — 불렸는지만 본다(루틴은 거기서 돌아온다). 10B 보다 짧은 루틴(`rts` 훅)은 뺀다."""
    bw, aw, _tab = entries(b, t4)
    ps, roots = [], []
    for a in sorted(set(bw) | set(aw)):
        if b[a : a + 2] == b"\x4e\x75":
            continue
        ps.append((a, b"\x13\xfc\x00\x01" + struct.pack(">I", PROBE + len(roots)) + b"\x4e\x75"))
        roots.append(a)
    return ps, roots


def probe(sel: list[int], bl, bo) -> None:
    """블록마다 자연 전투를 돌려(순열 난수 + 난수표 상수 몇 번) 어느 진입 루틴이 불렸는지 표로 남긴다 — 안 불린 루틴은 `미사용` 후보."""
    import battle_sweep as BS
    import headless

    out = headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "battle-ctx"
    c = headless.Core(str(BS.ROM))
    armed = BS.boot(c)
    idl = BS.ids()
    for n in sel:
        b = bl[n][1]
        ps, roots = probe_patches(b, table_start(b, bo[n][1]))
        hit = [False] * len(roots)
        for attempt in range(3):
            c.load_state(armed)
            c.poke(PROBE, bytes(len(roots)))
            BS.run_block(
                c,
                armed,
                n,
                idl[n],
                out,
                900,
                0x40 * attempt & 255,
                set(),
                [],
                0,
                1 if attempt == 0 else 0,
                None if attempt == 0 else BS.CONSTS[attempt],
                None,
                (b, ps),
            )
            flags = c.ram(PROBE, len(roots))
            hit = [h or bool(f) for h, f in zip(hit, flags, strict=True)]
        print(
            n,
            " ".join(f"{a:x}:{'Y' if h else '-'}" for a, h in zip(roots, hit, strict=True)),
            flush=True,
        )


def main() -> None:
    args = sys.argv[1:]
    bl = list(battle.blocks(built_rom()))
    bo = list(battle.blocks(common.rom()))
    if (
        "--kill" in args
    ):  # (--probe 용) 공격력을 올리고 몬스터 HP 고정을 끈다 — 쓰러짐·승리 사건 훅 시험
        args.remove("--kill")
        import battle_sweep as BS

        BS.KILL = True
    if args and args[0] == "--run":
        run_contexts(args[1:], bl, bo)
        return
    if args and args[0] == "--edges":
        import headless

        edges(headless._common_dir() / ".local" / "work" / "inbox" / "md-ed2" / "battle-ctx")
        return
    if args and args[0] == "--probe":
        probe([int(a) for a in args[1:]], bl, bo)
        return
    sel = [int(a) for a in args] or range(len(bl))
    rows = ["블록\t오프셋\t상태\t루틴\t슬롯(자료 B)\t훅(자료 A)\tlea\t길 위 분기(주소 니모닉 종류)"]
    for n in sel:
        for r in contexts(n, bl, bo):
            gs = " ; ".join(f"{a:x} {m} {k}" for a, m, _o, k in r.get("guards", []))
            rows.append(
                f"{n}\t{r['off']:#x}\t{r['상태']}\t{r['root'] and hex(r['root'])}\t{','.join(map(str, r.get('slots', [])))}\t{','.join(hex(x) for x in r.get('hookA', []))}\t{r['lea'] and hex(r['lea'])}\t{gs}"
            )
    dst = common.WORK / "battle_ctx.tsv"
    dst.write_text("\n".join(rows) + "\n", encoding="utf-8")
    from collections import Counter

    print(Counter(r.split("\t")[2] for r in rows[1:]), "→", dst)


if __name__ == "__main__":
    main()
