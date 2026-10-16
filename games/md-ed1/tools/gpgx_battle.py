"""전투 110블록 일괄 시험 — genesis_plus_gx 헤드리스(`gpgx_run.Genesis`)로 emucap 호출 없이 돌린다.

디버그 롬(`ED_DEBUG=1` 빌드)을 새 게임으로 부팅해 침실 필드에서 상태를 저장하고, 블록마다 그 상태를 복원해
`$FF3606` = 블록 번호 · `$FF1852` = 0040 으로 강제 조우를 연다(`docs/status.md` 「전투를 강제로 띄우는 법」).
파티 HP 는 매 프레임 되돌리고, 명령창이 뜨면 「방어」로 턴을 넘기며, 난수표(`$FF3480`)를 턴마다 바꿔 분기를
돌린다. 메시지 창이 바뀔 때마다(안정된 뒤) 화면을 PNG 로 낸다.

사용: `python3 gpgx_battle.py --rom <디버그 롬> --out <폴더> [--blocks 0-109] [--turns 6]`
"""

import argparse
import ctypes
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpgx_run import Genesis

WIN = (176, 224)  # 메시지·명령 창이 있는 화면 아래쪽 띠(y 범위)
STATE_NAME = "field_L1.state"


def boot_to_field(g: Genesis, slot: int = 0):
    """이어하기 → 슬롯 → 필드(세이브는 `Genesis(srm=…)` 로 미리 넣는다). 확인 키 c, 목록은 down 으로 옮긴다."""
    g.run(1601)
    g.press("start", 20, 400)
    g.press("down", 20, 20)
    g.press("c", 15, 200)
    g.run(100)
    for _ in range(slot):
        g.press("down", 12, 12)
    g.press("c", 15, 300)
    g.run(300)


def make_meta(rom: bytes) -> list[dict]:
    """전투 110블록의 스트림 표 — [{block, names, streams:[{off,last,text}]}]. `off`/`last` 는 블록 안 오프셋(전투 블록은 RAM
    `0xFF20AE` 부터 올라온다). 문안은 롬의 한글 코드를 풀어 본 것(우리 말) — 보고서 표용이다."""
    import re

    import battle
    import common

    codes = json.loads(
        (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
    )
    rev = {v: k for k, v in codes.items()}

    def dec(raw: bytes) -> str:
        out, i = "", 0
        while i < len(raw):
            if i + 1 < len(raw) and ((raw[i] << 8) | raw[i + 1]) in rev:
                out += rev[(raw[i] << 8) | raw[i + 1]]
                i += 2
                continue
            if 0x81 <= raw[i] <= 0x9F or 0xE0 <= raw[i] <= 0xEF:
                try:
                    out += raw[i : i + 2].decode("cp932")
                    i += 2
                    continue
                except UnicodeDecodeError:
                    pass
            out += (
                raw[i : i + 1].decode("cp932", "replace") if raw[i] >= 0x20 else f"<{raw[i]:02x}>"
            )
            i += 1
        return out

    appear = re.compile(
        r"(나타났다|대결이다|공격해 왔다|습격해 왔다|무리다|함께다|같이 있다|이끌고 싸움을 걸어왔다)"
    )
    meta = []
    for n, (_s, b, _e) in enumerate(battle.blocks(rom)):
        names = [dec(r["name"]) for r in battle.records(b)]
        streams = []
        for tgt, ent in battle.refs(b).items():
            st = ent["stream"]
            txt = "".join(dec(t.raw) if t.kind == "text" else f"<{t.raw.hex()}>" for t in st.tokens)
            streams.append(
                {"off": tgt, "last": st.end - 1, "text": txt, "appear": bool(appear.search(txt))}
            )
        meta.append({"block": n, "names": names, "streams": streams})
    return meta


def map_table(rom: bytes) -> tuple[int, ...]:
    """맵 id 표(`0x134DDC`, 워드) — 씬 블록 번호 순번으로 그 씬의 맵 id."""
    import struct

    return struct.unpack(">110H", rom[0x134DDC : 0x134DDC + 220])


def _warp_once(g: Genesis, map_id: int, slot: int, gap: int):
    g.poke(0x1AC5, bytes([map_id >> 8, map_id & 0xFF]))

    def P(k, f, after):
        g.press(k, f, after + gap)

    P("b", 8, 20)
    P("up", 8, 8)
    P("c", 8, 40)
    P("c", 8, 40)
    for _ in range(slot):
        P("down", 8, 8)
    P("c", 8, 40)
    P("c", 8, 60)
    P("down", 8, 8)
    P("c", 8, 40)
    P("c", 8, 40)  # LOAD 목록은 방금 쓴 슬롯에 커서가 남아 있다
    P("c", 8, 60)
    g.run(500)


MODULE_HEAD = (
    0x6650,
    32,
)  # 씬 모듈이 풀리는 램($FF6650) 머리 — 워프가 실제로 모듈을 올렸는지 보는 자리


def warp(
    g: Genesis,
    map_id: int,
    slot: int = 1,
    expect: bytes | None = None,
    gaps: tuple[int, ...] = (0, 4, 8),
) -> bool:
    """디버그 워프 — 저장된 맵 id(`$FF1AC5/6`)를 바꿔 쓰고 메뉴로 SAVE → LOAD 한다(2번 슬롯 램만 덮는다).
    메뉴: b → 위(기타) → c → SAVE c → 슬롯(아래 slot번) c → 예 c → 아래(LOAD) c → 슬롯 c → 예 c.

    🔴 성공은 poke 한 맵 id 가 아니라 **모듈 머리($FF6650)** 로 판정한다 — 입력 간격이 짧으면 LOAD 가 반영되지 않거나
    (원판) LOAD 후 이벤트 적용이 $FF1ABC 를 덮어 폭주하는데(한글 scene 179), 맵 id 는 poke 값이 남아 성공처럼 보인다.
    `expect` = 그 씬 모듈의 앞 32바이트(없으면 워프 전과 달라졌는지만 본다). 실패하면 처음 상태로 돌려 입력 간격
    (`gaps` 프레임씩 더)을 바꿔 다시 한다. ⚠ 간격을 크게(+20 이상) 잡으면 메뉴 조작이 어긋나 상태 화면에 멈춘다(양 롬 실측) —
    간격은 작게만 바꾼다. 씬 모듈을 안 올리는 맵(씬 번호가 104 로 남는 18곳)은 간격과 무관하게 실패한다. 반환 = 성공 여부(마지막 시도 상태가 그대로 남는다)."""
    start = g.save_state()
    before = g.ram(*MODULE_HEAD)
    for gap in gaps:
        g.load_state(start)
        _warp_once(g, map_id, slot, gap)
        head = g.ram(*MODULE_HEAD)
        if (head == expect[: MODULE_HEAD[1]]) if expect is not None else (head != before):
            return True
    return False


def recipe(g: Genesis, level: int = 2):
    """강제 조우 준비 — 더미 객체(+5 = FF)·포인터·파티 레벨(무리형 등장문 조건)·HP."""
    g.poke(0xFF80, bytes.fromhex("0000000000FF00000000000000000000"))
    g.poke(0x3474, bytes.fromhex("00FFFF80"))
    g.poke(0x2076, bytes.fromhex("00FFFF80"))
    g.poke(0x1DBF, bytes([level]))
    g.poke(0x1DC0, bytes.fromhex("270F270F"))


def table(g: Genesis, v: int):
    g.poke(0x3480, bytes([v]) * 55)


def win_hash(g: Genesis) -> str:
    return hashlib.sha1(g.frame[WIN[0] : WIN[1]].tobytes()).hexdigest()[:12]


def is_menu(g: Genesis, tmpl: np.ndarray | None) -> bool:
    if tmpl is None:
        return False
    cur = g.frame[WIN[0] : WIN[1]]
    return float(np.mean(cur == tmpl)) > 0.93 and cur.shape == tmpl.shape


def ptr_hits(g: Genesis, rng: list[tuple[int, int, int]], blen: int) -> set[int]:
    """램 안의 32비트 값이 이 블록 스트림 범위에 드는 곳을 찾는다 — 그리는 중인 문안 포인터(스택·변수)가 잡힌다."""
    p, _ = g._mem(2)
    raw = np.frombuffer(ctypes.string_at(p, 0x10000), dtype=np.uint8)
    un = raw.reshape(-1, 2)[:, ::-1].reshape(-1)  # 바이트 스왑 풀기
    w = un.view(">u2").astype(np.uint32)
    vals = (w[:-1] << 16) | w[1:]
    vals[(np.arange(len(vals)) * 2 >= 0x20AE) & (np.arange(len(vals)) * 2 < 0x20AE + blen)] = 0
    out = set()
    for off, last, _tag in rng:
        a, b = 0xFF20AE + off, 0xFF20AE + last
        if np.any((vals >= a) & (vals <= b)):
            out.add(off)
    return out


def run_block(
    g,
    state,
    blk,
    out,
    turns,
    tmpl,
    vs,
    maxf,
    rng,
    blen,
    level=2,
    tag="r0",
    have=None,
    mode="defend",
):
    """한 번 돌린다. 새 스트림 포인터가 처음 보이면 45프레임 뒤(글이 다 그려진 뒤) 전체 화면을 PNG 로 낸다.
    반환 (턴 수, 프레임, {스트림 오프셋: 처음 본 프레임})."""
    g.load_state(state)
    recipe(g, level)
    g.poke(0x3606, bytes([blk]))
    g.poke(0x1852, bytes.fromhex("0040"))
    table(g, vs[0])
    have = have if have is not None else set()
    seen = {}
    pend = []
    cursor_set = False
    turn = 0
    last = ""
    stable = 0
    f = 0
    for f in range(maxf):
        g.poke(0x1DC0, bytes.fromhex("270F270F"))
        if (
            mode == "weak" and f >= 90 and f % 30 == 0
        ):  # 몬스터 HP 를 바닥으로 — HP 문턱 대사·마지막 일격 문구
            for rec in (0x1EC0, 0x1F00, 0x1F40, 0x1F80):
                g.poke(rec, bytes.fromhex("0003"))
        g.run(1)
        h = win_hash(g)
        if h == last:
            stable += 1
        else:
            stable = 0
            last = h
        if f % 2 == 0:
            for off in ptr_hits(g, rng, blen):
                if off not in seen:
                    seen[off] = f
                    if off not in have:
                        pend.append((f + 45, off))
        while pend and pend[0][0] <= f:
            _, off = pend.pop(0)
            g.shot(out / f"b{blk:03d}_{off:04x}_{tag}.png")
            have.add(off)
        if stable == 20 and tmpl is not None and is_menu(g, tmpl):
            if turn >= turns:
                break
            table(g, vs[turn % len(vs)])
            if mode == "attack":  # 공격 → 대상(첫째) 확정을 두 번
                g.press("c", 8, 20)
                g.press("c", 8, 20)
            elif mode == "flee":
                if not cursor_set:
                    g.press("down", 8, 6)
                    for _ in range(3):
                        g.press("right", 8, 6)
                    cursor_set = True
                g.press("c", 8, 4)
            else:  # defend · weak — 방어(오른쪽 둘)
                if not cursor_set:
                    g.press("right", 8, 6)
                    g.press("right", 8, 6)
                    cursor_set = True
                g.press("c", 8, 4)
            turn += 1
    for _, off in pend:
        g.shot(out / f"b{blk:03d}_{off:04x}_{tag}.png")
        have.add(off)
    return turn, f, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--blocks", default="0-109")
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--maxf", type=int, default=7000)
    ap.add_argument(
        "--meta", help="스트림 오프셋 표(JSON) — 없으면 롬에서 만들고 <out>/meta.json 으로 남긴다"
    )
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--mode", default="defend", choices=["defend", "attack", "flee", "weak"])
    ap.add_argument("--only-missing", help="앞선 log.json — 못 본 스트림이 있는 블록만")
    ap.add_argument("--state")
    ap.add_argument(
        "--party-name",
        help="리더(레코드 0) 이름을 바꾼다 — 조사 훅의 받침 있음/없음 두 판(예: 라울 / 세리오스)",
    )
    ap.add_argument("--save", default="/root/save/md-ed1/md-ed1-slots.sav")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    g = Genesis(a.rom, srm=Path(a.save).read_bytes())
    sp = Path(a.state) if a.state else out / STATE_NAME
    # 🔴 상태 파일은 롬을 바꿔도 옛 RAM 을 되살린다 — 만든 롬 sha1 을 옆에 적고 다르면 새로 만든다(ps1-ed3 10-20)
    rom_sha = hashlib.sha1(Path(a.rom).read_bytes()).hexdigest()
    shp = sp.with_name(sp.name + ".sha1")
    if sp.exists() and (not shp.exists() or shp.read_text().strip() != rom_sha):
        print(f"상태 파일을 만든 롬이 지금 롬과 다르다 — 새로 만든다 ({sp})", flush=True)
        sp.unlink()
    if sp.exists():
        state = sp.read_bytes()
    else:
        boot_to_field(g)
        if a.party_name:
            codes = json.loads(
                (
                    Path(__file__).resolve().parent.parent / "textmap" / "hangul_codes.json"
                ).read_text(encoding="utf-8")
            )
            nm = b"".join(
                struct.pack(">H", codes[c]) if c in codes else c.encode("ascii")
                for c in a.party_name
            )
            g.poke(0x1DBC + 0x30, nm + b"\x06")  # 파티 레코드 0 의 이름(+0x30, 끝 06)
        g.shot(out / "field.png")
        state = g.save_state()
        sp.write_bytes(state)
        shp.write_text(rom_sha)
    from PIL import Image

    tmpl = np.array(
        Image.open(Path(__file__).resolve().parent / "gpgx_menu_tmpl.png").convert("RGB")
    )
    blocks = []
    for part in a.blocks.split(","):
        if "-" in part:
            x, y = part.split("-")
            blocks += list(range(int(x), int(y) + 1))
        else:
            blocks.append(int(part))
    base = [0x10, 0x90, 0xF0, 0x50, 0xC0, 0x30, 0x70, 0xB0, 0x20, 0xD0]
    log = {}
    if a.meta:
        meta = json.loads(Path(a.meta).read_text())
    else:
        meta = make_meta(Path(a.rom).read_bytes())
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=0))
    for b in blocks:
        streams = [x for x in meta[b]["streams"] if x["off"] > 0x100 or x["last"] - x["off"] > 6]
        rng = [(x["off"], x["last"], 0) for x in streams]
        want = {x["off"] for x in streams}
        have: set[int] = set()
        if a.only_missing:
            prev = json.loads(Path(a.only_missing).read_text()).get(str(b))
            if prev is None or not prev["missing"]:
                continue
            have = {x["off"] for x in streams} - {int(m, 16) for m in prev["missing"]}
            want = {int(m, 16) for m in prev["missing"]} | have
        runs = 0
        for r in range(a.runs):
            vs = base[r % len(base) :] + base[: r % len(base)]
            lvl = 2 if r % 2 == 0 else 1
            turn, _f, _seen = run_block(
                g,
                state,
                b,
                out,
                a.turns,
                tmpl,
                vs,
                a.maxf,
                rng,
                0x600,
                lvl,
                f"{a.mode[0]}{r}",
                have,
                a.mode,
            )
            runs += 1
            print(
                f"  block {b} run {r} lvl{lvl} turns {turn} seen {len(have)}/{len(want)}",
                flush=True,
            )
            if have >= want:
                break
        log[b] = {
            "runs": runs,
            "seen": sorted(hex(x) for x in have),
            "missing": sorted(hex(x) for x in want - have),
        }
        print(b, log[b], flush=True)
    (out / f"log_{a.mode}.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
