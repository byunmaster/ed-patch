"""구조 대조 정적 검사 — 원판과 구운 롬을 **같은 길로 나란히 걸어** 제어 코드 열이 같은지 본다(마스터 10-22).

왜: 재배치(블록 옮김·중계 조각·포인터 재기입·채움)를 한 롬은 「한 블록씩 띄워 보는」 하네스·qa 로는 안 보이는 사고를 낸다.
ss-ed3 에서 재조판이 대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아 첫 장면 대사가 통째로 빠졌다(1,046블록, 10-21).
이 검사는 글자 바이트를 빼고 **제어 코드 열**(색·창 지움·조건·화자·쪽 넘김·종결·호출/분기/점프와 그 목표)만 원판 ↔ 구운 롬에서 대조한다.

걷는 법(lockstep) — 시작점은 메시지 포인터 표 항목(원판 표의 목표 ↔ 구운 롬 표의 목표) 3,358 + 못 닿은 조각 시작(2차 보충):
  · 원판은 `script.py` 항목 열(되쓰기 왕복이 증명된 파서)로, 구운 롬은 **바이트를 직접** 읽는다(한글 2B 글자 · 사전 2B · 제어 + 인자).
  · 글 덩이는 길이가 달라도 된다(번역). 글 덩이가 끝나는 자리에서 양쪽이 **같은 제어 코드·같은 인자**여야 한다.
  · `FA`(무조건 점프)는 말없이 따라간다 — FD 중계의 `FA 건너뛰기`·슬롯 `FA 목표` 가 여기 해당한다(허용 목록 = 장부 스텁 행).
  · `FC` 목표가 `FC 03 00 F9 abs24 FE`(중계 조각)이면 abs 목표로 푼다. `F9`/`FC`/`FD` 목표는 (원문 목표, 구운 목표) 짝으로 이어 걷는다.
  · 종결(`E0`/`E4`/`FE`)에서 멈춘다. `E0` 다음 바이트가 `E4` 인가도 같아야 한다(`verify_terminators` 와 같은 눈금).
    흘러내림 짝(`E0` 이 끝이고 다음 조각이 무참조)은 다음 조각까지 이어 걷는다 — 채움·이웃 어긋남이 여기서 잡힌다.
  · 개행(`CF`)은 글 덩이 안이라 세지 않는다 — 조판(`typeset.py`)의 몫이고 줄 수·위치가 번역마다 다르다(허용: 근거 typeset.py).
허용되는 달라짐은 **장부(`relocations.tsv`)에 있는 것뿐**이다 — 옮겨진 조각 시작 · FC 중계 조각 · FD 중계 · 표 포인터. 장부에 없는 재배치가
롬에 있으면 실패, 장부가 이번 빌드의 후보와 다르면 실패(`--freeze` 로 갱신 — 손으로 안 쓴다).
원판에 없던 채움·패딩은 **걸어서 닿는 길에 있으면** 제어 열이 달라져 잡힌다. 닿지 않는 채움(본체를 FF 로 비운 자리)은 「도달 0」을 센다.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (shared/text 와 이름이 겹친다 — common 보다 먼저)
import common
import script

GAME = common.GAME_DIR
# 종료 꼴 검사와 같은 면제 — 머리가 네이티브 코드와 섞이거나 포인터 전용 별도 메시지라 선형·분기 걷기가 원판과 같은 길이 아니다
# (근거는 build.TERMINATOR_EXEMPT 의 사유 그대로: 02A7 `pointer_tail` · 04FD·0B40 미니게임 `text.MINIGAME_RUNS`)
EXEMPT = {("main", 0x02A7), ("main", 0x04FD), ("main", 0x0B40)}
LEDGER = GAME / "relocations.tsv"
KNOWN = GAME / "ctrl_flow_known.tsv"  # 알려진 어긋남(미판정·허용) — 원문 좌표 · 종류 · 상태 · 설명
STUB_FC = bytes([0xFC, 3, 0, 0xF9])  # FC 중계 조각: FC +3 · F9 abs24 · FE
MAX_STEPS = 5_000_000
REGION_ENDS = frozenset(common.snes2off(b) for _a, b in text.EXTRA_REGIONS)  # 스크립트 덩이 끝 바로 뒤 — 엔진이 코드로 들어간다(걷기 종료)
BLANK = frozenset({0x0A, 0x0D, 0x10, 0xCF})  # 공백·개행 글자 코드


@dataclass
class Result:
    errors: list = field(default_factory=list)
    keys: list = field(default_factory=list)  # 오류마다 (원문 SNES 좌표, 종류) — 알려진 목록 대조용
    pairs: int = 0  # 걸은 (원문, 구운) 짝
    items: int = 0  # 대조한 원문 항목
    ctrl: int = 0  # 그중 제어 항목
    covered: set = field(default_factory=set)  # 글 덩이 속 원문 항목(시작점이 아닌 것) — 커버리지용
    moved: dict = field(default_factory=dict)  # 원문 항목 오프셋 → 구운 오프셋(걸어서 확인한 것)
    fc_stubs: set = field(default_factory=set)  # (원문 목표, 구운 중계 조각 위치)
    fd_relays: set = field(default_factory=set)  # (원문 FD 오프셋, 구운 FD 위치)
    built_visited: set = field(default_factory=set)
    unparsed: int = 0  # 원문 항목 열 밖(네이티브 코드 등)으로 간 짝 — 같은 자리여야 한다


def _adv(o: int, n: int) -> int:
    """원문 쪽 선형 진행 — 뱅크 경계를 넘으면 -1(엔진은 16비트만 올려 `$xx:FFFF` 다음이 램이라 이어서 못 읽는다. build.segment_slices 주석)."""
    n2 = o + n
    return n2 if (common.off2snes(n2) >> 16) == (common.off2snes(o) >> 16) else -1


def _rel16_built(img: bytes, b: int) -> int:
    return script._rel16(b, img[b + 1] | (img[b + 2] << 8))


def _is_lead(c: int, leads: frozenset) -> bool:
    return c in leads


def built_text_len(img: bytes, b: int, leads: frozenset) -> int:
    """구운 롬의 글 덩이 한 낱자 길이(0 이면 제어 코드)."""
    c = img[b]
    if c < 0xD0:
        return 2 if c in leads else 1
    if c in text.DICT_TABLES:
        return 2
    if c < 0xE0:
        return 1
    return 0


def lockstep(
    orig: bytes,
    items: list,
    built: bytes,
    starts: list,
    fall: frozenset = frozenset(),
    leads: frozenset = frozenset(),
    res: Result | None = None,
    seen: set | None = None,
) -> Result:
    """`starts` = [(원문 오프셋, 구운 오프셋, 이름)]. `fall` = 흘러내림 짝(E0 이 끝이고 다음이 무참조)의 **E0 원문 오프셋**."""
    res = res or Result()
    seen = seen if seen is not None else set()
    by_off = {it.off: i for i, it in enumerate(items)}
    stack = [(o, b, n) for o, b, n in starts]
    steps = 0

    def err(msg: str, o: int, b: int, name: str, kind: str = "") -> None:
        res.keys.append((common.fmt(common.off2snes(o)), kind or msg.split()[0]))
        res.errors.append(f"{name}: 원문 {common.fmt(common.off2snes(o))} ↔ 구운 {common.fmt(common.off2snes(b))} — {msg}")

    def is_relay_fd(b: int, it) -> bool:
        """구운 FD 가 중계 꼴인가 — `FD s0..s4 · FA 건너뛰기 · FA 목표 × 살아 있는 슬롯 수`(`script.emit`)이고 슬롯이 각자 자기 `FA` 를 가리킨다."""
        if len(it.args) != 5 or built[b + 6] != 0xFA:
            return False
        live = [j for j in range(5) if j not in it.dead]
        if _rel16_built(built, b + 6) != b + 9 + 3 * len(live):
            return False
        return all(built[b + 1 + j] == 9 + 3 * n and built[b + 9 + 3 * n] == 0xFA for n, j in enumerate(live))

    while stack:
        o, b, name = stack.pop()
        while True:
            steps += 1
            if steps > MAX_STEPS:
                err("걸음 한도 — 순환?", o, b, name)
                break
            if o < 0:
                break
            key = (o, b)
            if key in seen:
                break
            seen.add(key)
            res.pairs += 1
            i = by_off.get(o)
            if i is None:  # 원문 항목 열 밖 — 네이티브 코드·표 등. 같은 자리여야 한다
                res.unparsed += 1
                if o != b and o not in REGION_ENDS:
                    err("원문 항목 열 밖인데 구운 자리가 다르다", o, b, name, "열 밖")
                break
            it = items[i]
            if it.off in res.moved and res.moved[it.off] != b:
                err(f"같은 원문 항목이 두 자리로 간다({common.fmt(common.off2snes(res.moved[it.off]))})", o, b, name)
                break
            res.moved[it.off] = b
            res.built_visited.add(b)
            res.items += 1
            if b >= len(built):
                err("구운 롬 밖", o, b, name)
                break
            if it.kind != "ctrl":  # 글 덩이 — 길이는 달라도 된다
                oo, bb, has_o = o, b, False
                while True:
                    j = by_off.get(oo)
                    if j is None or items[j].kind == "ctrl":
                        break
                    if not (items[j].kind == "char" and items[j].code in BLANK):
                        has_o = True  # 공백·개행뿐인 글 덩이는 글로 세지 않는다(조판의 몫)
                    res.covered.add(items[j].off)
                    oo += items[j].size
                bb = b
                has_b = False
                while bb < len(built) and built_text_len(built, bb, leads):
                    if not (built[bb] in BLANK):
                        has_b = True
                    bb += built_text_len(built, bb, leads)
                if has_o != has_b:
                    err("글 덩이가 한쪽에만 있다", o, b, name, "글 덩이")
                    break
                o, b = _adv(o, oo - o), bb
                continue
            res.ctrl += 1
            c = it.code
            if built[b] != c:
                err(f"제어 코드가 다르다 원문 {c:02X} 구운 {built[b]:02X}", o, b, name, "제어 코드")
                break
            k = len(it.args)
            if c in (0xE0, 0xE4):
                on = orig[o + 1] if o + 1 < len(orig) else None
                bn = built[b + 1] if b + 1 < len(built) else None
                if (on == 0xE4) != (bn == 0xE4):
                    err(f"{c:02X} 다음 바이트의 E4 여부가 다르다(원문 {on}, 구운 {bn})", o, b, name)
                    break
                if c == 0xE0 and o in fall and on != 0xE4:  # 흘러내림 — 다음 조각까지 이어 걷는다
                    o, b = _adv(o, 1), b + 1
                    continue
                break
            if c == 0xFE:
                break
            if c == 0xFF:
                o, b = _adv(o, 1), b + 1
                continue
            if c == 0xFA:
                to = it.targets[0]
                tb = _rel16_built(built, b)
                o, b = to, tb
                continue
            if c == 0xF9:
                if it.targets[0] < 0:  # 롬 밖(표를 문안으로 읽은 자리) — 인자 그대로여야 한다
                    if bytes(built[b + 1 : b + 4]) != it.args:
                        err("F9 롬 밖 인자가 다르다", o, b, name)
                        break
                else:
                    ab = built[b + 1] | (built[b + 2] << 8) | (built[b + 3] << 16)
                    if not ab & 0x8000:
                        err(f"F9 목표가 롬 주소가 아니다 {ab:06X}", o, b, name)
                        break
                    stack.append((it.targets[0], common.snes2off(ab), name))
                o, b = _adv(o, 4), b + 4
                continue
            if c == 0xFC:
                ot = it.targets[0]
                dst = _rel16_built(built, b)
                if dst + 8 <= len(built) and bytes(built[dst : dst + 4]) == STUB_FC and built[dst + 7] == 0xFE:
                    ab = built[dst + 4] | (built[dst + 5] << 8) | (built[dst + 6] << 16)
                    res.fc_stubs.add((ot, dst))
                    res.built_visited.add(dst)
                    dst = common.snes2off(ab)
                stack.append((ot, dst, name))
                o, b = _adv(o, 3), b + 3
                continue
            if c in (0xFB, 0xFD):
                ok = True
                relay = c == 0xFD and is_relay_fd(b, it)
                if relay:
                    res.fd_relays.add((it.off, b))
                for j in range(k):
                    if j in it.dead:
                        if built[b + 1 + j] != it.args[j]:
                            err(f"{c:02X} 죽은 슬롯 {j} 값이 다르다", o, b, name)
                            ok = False
                        continue
                    bt = b + built[b + 1 + j]
                    if relay:
                        res.built_visited.add(bt)
                        bt = _rel16_built(built, bt)
                    stack.append((it.targets[j], bt, name))
                if not ok or c == 0xFB:
                    break
                if relay:
                    o, b = _adv(o, 1 + k), _rel16_built(built, b + 6)
                else:
                    o, b = _adv(o, 1 + k), b + 1 + k
                continue
            # 나머지 제어 — 인자가 그대로여야 한다(색·창 지움·효과음·조건 · 화자 · 네이티브 호출)
            if bytes(built[b + 1 : b + 1 + k]) != it.args:
                err(f"{c:02X} 인자가 다르다 원문 {it.args.hex()} 구운 {bytes(built[b + 1 : b + 1 + k]).hex()}", o, b, name)
                break
            if 0xF0 <= c <= 0xF7:
                # 조건 — 거짓이면 **다음 항목 하나**를 건너뛴다(text.py). 다음이 제어(FA 등)면 건너뛴 쪽 길도 걷는다
                ni = by_off.get(o + 1 + k)
                if ni is not None and items[ni].kind == "ctrl":
                    nx, b2 = items[ni], b + 1 + k
                    if nx.code in (0xFB, 0xFD):
                        sz = 1 + len(nx.args)
                        if nx.code == 0xFD and is_relay_fd(b2, nx):
                            sz += 3 + 3 * sum(1 for j in range(5) if j not in nx.dead)
                    else:
                        sz = 1 + text.ARGLEN.get(built[b2], 0)
                    alt = _adv(o + 1 + k, nx.size)
                    if alt >= 0:
                        stack.append((alt, b2 + sz, name))
            o, b = _adv(o, 1 + k), b + 1 + k
    return res


def target_bytes(orig: bytes, items: list, built: bytes, moved: dict, pm: dict, tables: list, leads: frozenset) -> tuple[list, dict]:
    """**남이 들어오는 바이트를 우리가 바꿨나** — 원판의 점프(F9 · FA · FC · FB · FD)·표 포인터 목표를 전부 모아, 구운 쪽 대응 자리의 첫 바이트가
    원문 항목과 같은 종류인지 본다(제어면 같은 코드, 글이면 글). pce-ed1 10-22: 메시지 A 의 점프 스텁이 제자리 끝의 종료 바이트까지 덮었는데 B 의
    끝 점프가 그 바이트로 들어와 B 가 스텁 주소를 글자로 읽었다. 걷기(`lockstep`)는 걸은 짝만 보므로, 목표 쪽에서 한 번 더 모은다.
    대응 자리는 걸은 짝(`moved`) → 조각 시작 장부(`pm`) 순으로 찾는다. 둘 다 없으면 「대응 없음」(원판도 못 닿는 꼬리일 수 있다)으로 센다.
    `tables` = 표 포인터 목표(원문 오프셋)들. 반환 = (어긋남 목록, 집계)."""
    by_off = {it.off: it for it in items}
    tg: dict[int, str] = {}
    for it in items:
        if it.kind == "ctrl":
            for t in it.targets:
                if t >= 0:
                    tg.setdefault(t, f"{it.code:02X}@{common.fmt(common.off2snes(it.off))}")
    for t in tables:
        tg.setdefault(t, "표")
    bad, st = [], {"목표": len(tg), "대응 없음": 0, "맞음": 0}
    for t, why in sorted(tg.items()):
        it = by_off.get(t)
        b = moved.get(t, pm.get(t))
        if it is None:
            continue  # 항목 열 밖(네이티브·표) — 걷기가 따로 본다
        if b is None or b >= len(built):
            st["대응 없음"] += 1
            continue
        if it.kind == "ctrl":
            b2 = b
            while b2 < len(built) and built[b2] == 0xCF:  # 구운 쪽 앞 개행은 조판의 몫(알려진 목록 — 앞 CF)
                b2 += 1
            ok = built[b2] == it.code
        else:
            # 글·치환이 목표인 자리 — 첫 바이트가 종료·점프·호출이면 남의 바이트가 덮은 것이다(조판이 앞에 이름 창 E3 을 두는 건 정상)
            oo = t
            while (j := by_off.get(oo)) is not None and j.kind == "char" and j.code in BLANK:
                oo += j.size  # 원판 앞 개행·공백 — 구운 쪽은 조판이 떼므로 그 뒤 항목과 견준다
            nx = by_off.get(oo)
            if nx is not None and nx.kind == "ctrl" and oo != t:
                b2 = b
                while b2 < len(built) and built[b2] == 0xCF:
                    b2 += 1
                ok = built[b2] == nx.code
            else:
                ok = built[b] not in (0xE0, 0xE4, 0xFA, 0xF9, 0xFC, 0xFD, 0xFB, 0xFE, 0xFF)
        if ok:
            st["맞음"] += 1
        else:
            bad.append(f"목표 바이트가 바뀌었다 — {why} → 원문 {common.fmt(common.off2snes(t))}({'제어 %02X' % it.code if it.kind == 'ctrl' else '글'}) ↔ 구운 {common.fmt(common.off2snes(b))} = {built[b]:02X}")
    return bad, st


# ---------------------------------------------------------------- 롬 짝 걷기
def table_entries(img: bytes, name: str) -> list[int | None]:
    """표 항목의 파일 오프셋(포인터가 아니면 None — alt3 끝의 `$FFFFFF` 등)."""
    addr, n = text.MSG_TABLES[name]
    base = common.snes2off(addr)
    out = []
    for i in range(n):
        lo, hi, bk = img[base + 3 * i : base + 3 * i + 3]
        if hi < 0x80 or not (0x04 <= bk <= 0x3F):
            out.append(None)
        else:
            out.append(common.snes2off((bk << 16) | (hi << 8) | lo))
    return out


def walk_roms(rom: bytes, out: bytes, use_place_map: bool = True) -> dict:
    import build
    import encode

    items = build.body_items(rom)
    slices = build.segment_slices(items)
    fall_si = build.fallthrough_pairs(items, slices, rom)
    fall = frozenset(items[slices[si][2] - 1].off for si in fall_si)
    leads = frozenset(encode.LEADS)
    starts = []
    ptr_rows = []  # (표, 번호, 원래 포인터 SNES, 새 포인터 SNES)
    skipped = 0
    for name in text.MSG_TABLES:
        eo, eb = table_entries(rom, name), table_entries(out, name)
        base = common.snes2off(text.MSG_TABLES[name][0])
        for i, (a, b) in enumerate(zip(eo, eb, strict=True)):
            if a is None and b is None:
                skipped += 1
                continue
            if a is None or b is None:
                starts.append(None)  # 한쪽만 포인터 — 아래에서 실패로 센다
                ptr_rows.append((name, i, a, b))
                continue
            if a != b or True:
                if a != b:
                    ptr_rows.append((name, i, a, b))
            if a < common.snes2off(text.TEXT_START) and name != "alt3":
                skipped += 1  # 표 구간을 가리키는 항목(alt1[0] 등) — 문안이 아니다
                continue
            if (name, i) in EXEMPT:
                skipped += 1
                continue
            starts.append((a, b, f"{name}[{i:#06x}]"))
    res = Result()
    for s, pr in zip([s for s in starts if s is None], [p for p in ptr_rows if p[2] is None or p[3] is None], strict=False):
        res.errors.append(f"{pr[0]}[{pr[1]:#06x}] 한쪽만 포인터다")
    starts = [s for s in starts if s is not None]
    seen: set = set()
    lockstep(rom, items, out, starts, fall, leads, res, seen)
    n_phase1 = len(res.moved)
    # 2차 — 표로 못 닿은 조각 시작(네이티브 코드·다른 조각이 부르는 것). 장부 좌표(place_map)로 시작점을 보충한다
    pm = {}
    if use_place_map:
        import json

        p = common.OUT_DIR / "place_map.json"
        if p.exists():
            pm = {int(k, 16): int(v, 16) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    seg_first = {items[a].off: (sid, a, e) for sid, a, e in slices}
    extra = [(o, pm[o], "2차") for o in seg_first if o not in res.moved and o not in res.covered and o in pm]
    if extra:
        lockstep(rom, items, out, extra, fall, leads, res, seen)
    # 포인터가 장부 밖인 표 항목도 수집
    cover_any = cover_full = 0
    uncovered = []
    for sid, a, e in slices:
        vis = [(items[j].off in res.moved or items[j].off in res.covered) for j in range(a, e)]
        cover_any += any(vis)
        cover_full += all(vis)
        if not all(vis):
            uncovered.append((sid, items[a].off, sum(vis), e - a))
    return {
        "res": res,
        "items": items,
        "slices": slices,
        "ptr_rows": [r for r in ptr_rows if r[2] is not None and r[3] is not None],
        "skipped": skipped,
        "n_phase1": n_phase1,
        "cover_any": cover_any,
        "cover_full": cover_full,
        "uncovered": uncovered,
        "n_starts": len(starts),
        "n_extra": len(extra),
    }


# ---------------------------------------------------------------- 장부 대조
def load_ledger(path: Path) -> list[list[str]]:
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln or ln.startswith("#") or ln.startswith("블록 키"):
            continue
        rows.append(ln.split("\t"))
    return rows


def ledger_gaps(w: dict, out: bytes, ledger: list[list[str]]) -> list[str]:
    """걸어서 확인한 재배치 중 장부에 없는 것."""
    import build

    res: Result = w["res"]
    items, slices = w["items"], w["slices"]
    L = {(r[1], r[2], r[3]) for r in ledger}  # (종류, 원래, 새)
    key_of = {r[0]: r for r in ledger}
    gaps = []

    def s(o: int) -> str:
        return common.fmt(common.off2snes(o))

    for sid, a, e in slices:
        o0 = items[a].off
        if o0 in res.moved and res.moved[o0] != o0 and ("옮김", s(o0), s(res.moved[o0])) not in L:
            gaps.append(f"옮김 {sid} {s(o0)}→{s(res.moved[o0])}")
    for ot, dst in sorted(res.fc_stubs):
        if ("스텁", s(ot), s(dst)) not in L:
            gaps.append(f"FC 중계 {s(ot)}→{s(dst)}")
    for fo, fb in sorted(res.fd_relays):
        if ("스텁", s(fo), s(fb)) not in L:
            gaps.append(f"FD 중계 {s(fo)}→{s(fb)}")
    for name, i, a, b in w["ptr_rows"]:
        if ("포인터", common.fmt(common.off2snes(a)), common.fmt(common.off2snes(b))) not in L:
            gaps.append(f"포인터 {name}[{i:#06x}] {s(a)}→{s(b)}")
    lo, hi = common.snes2off(build.BODY[0]), common.snes2off(build.BODY[1])
    pinned = [(common.snes2off(a), common.snes2off(b)) for a, b in build.PINNED]
    for b in sorted(res.built_visited):
        if lo <= b < hi and not any(p0 <= b < p1 for p0, p1 in pinned):
            gaps.append(f"비운 본체 안으로 걸어 들어간다(도달 0 이어야 한다) {s(b)}")
            break
    _ = key_of
    return gaps


def summarize(w: dict, ledger: list[list[str]], gaps: list[str]) -> str:
    res: Result = w["res"]
    kinds: dict[str, int] = {}
    for r in ledger:
        kinds[r[1]] = kinds.get(r[1], 0) + 1
    total = len(w["slices"])
    return (
        f"구조 대조: 시작점 {w['n_starts']}(표) + {w['n_extra']}(2차) · 걸은 짝 {res.pairs:,} · 대조 항목 {res.items:,}(제어 {res.ctrl:,}) · "
        f"조각 커버 {w['cover_any']}/{total}(전부 걸음 {w['cover_full']}) · 어긋남 {len(res.errors)} · 장부 밖 재배치 {len(gaps)} · "
        f"장부 {len(ledger)}행(" + " ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + ")"
    )


def write_table(path: Path, w: dict, gaps: list[str]) -> None:
    res: Result = w["res"]
    lines = ["종류\t내용"]
    lines += [f"어긋남\t{e}" for e in res.errors]
    lines += [f"장부 밖\t{g}" for g in gaps]
    lines += [f"못 걸음\t{sid} {common.fmt(common.off2snes(o))} {n}/{t}항목" for sid, o, n, t in w["uncovered"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_known() -> dict:
    """알려진 어긋남 — {(원문 좌표, 종류): (상태, 설명)}. 상태 `미판정` 은 보고 대기, `허용` 은 사유·엔진 근거를 적은 것."""
    out = {}
    if KNOWN.exists():
        for ln in KNOWN.read_text(encoding="utf-8").splitlines():
            if not ln or ln.startswith("#"):
                continue
            a = ln.split("\t")
            out[(a[0], a[1])] = (a[2], a[3] if len(a) > 3 else "")
    return out


def product_paths() -> tuple[Path, Path]:
    d = common.BUILD_DIR / common.BUILD_TAG
    rom = next(iter(sorted(d.glob("*(KR).sfc"))), None)
    if rom is None:
        raise SystemExit(f"제품 롬이 없다 — 먼저 `build.py --kr`: {d}")
    return rom, d / "relocations.tsv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rom", type=Path, help="구운 롬(기본: 이 브랜치의 제품 롬)")
    ap.add_argument("--freeze", action="store_true", help="장부 후보를 커밋 장부(relocations.tsv)로 갱신한다")
    ap.add_argument("--table", type=Path, help="어긋남·장부 밖·못 걸은 조각 표를 이 경로에 쓴다")
    a = ap.parse_args()
    rom_p, cand = product_paths()
    rom_p = a.rom or rom_p
    if not cand.exists():
        raise SystemExit(f"장부 후보가 없다 — 제품 롬을 다시 구워라(`build.py --kr`): {cand}")
    if a.freeze:
        LEDGER.write_bytes(cand.read_bytes())
        print(f"장부 갱신 → {LEDGER}")
    if not LEDGER.exists():
        raise SystemExit(f"커밋 장부가 없다 — `check_ctrl_flow.py --freeze`: {LEDGER}")
    if LEDGER.read_bytes() != cand.read_bytes():
        raise SystemExit(
            "장부가 이번 빌드의 재배치와 다르다(재배치가 바뀌었다) — 의도한 변경이면 `python3 games/sfc-ed1/tools/check_ctrl_flow.py --freeze` 로 "
            f"갱신하고 diff 를 읽어라: {LEDGER}"
        )
    rom = common.rom_bytes()
    out = rom_p.read_bytes()
    w = walk_roms(rom, out)
    ledger = load_ledger(LEDGER)
    gaps = ledger_gaps(w, out, ledger)
    import encode

    tbl = [a for n in text.MSG_TABLES for a in table_entries(rom, n) if a is not None and a >= common.snes2off(text.TEXT_START)]
    pm_p = common.OUT_DIR / "place_map.json"
    pm = {int(k, 16): int(v, 16) for k, v in json.loads(pm_p.read_text(encoding="utf-8")).items()} if pm_p.exists() else {}
    tbad, tst = target_bytes(rom, w["items"], out, w["res"].moved, pm, tbl, frozenset(encode.LEADS))
    print(f"목표 바이트 대조: 원판 점프·호출·포인터 목표 {tst['목표']} · 맞음 {tst['맞음']} · 대응 없음 {tst['대응 없음']} · 바뀜 {len(tbad)}")
    gaps = gaps + tbad
    print(summarize(w, ledger, gaps))
    if a.table:
        write_table(a.table, w, gaps)
    res: Result = w["res"]
    known = load_known()
    hit = set(res.keys)
    new_err = [e for e, k in zip(res.errors, res.keys, strict=True) if k not in known]
    stale = sorted(k for k in known if k not in hit)
    by_state: dict[str, int] = {}
    for k in hit & set(known):
        by_state[known[k][0]] = by_state.get(known[k][0], 0) + 1
    print("알려진 어긋남: " + (" · ".join(f"{k} {v}" for k, v in sorted(by_state.items())) or "0"))
    if new_err or gaps or stale:
        for e in (new_err + gaps)[:20]:
            print("  ✗", e)
        for k in stale:
            print(f"  ✗ 알려진 목록에 있는데 이제 안 나온다(지워라): {k}")
        raise SystemExit("구조 대조 실패 — 제어 코드 열이 원판과 다르거나 장부에 없는 재배치가 있다")
    print("구조 대조 OK")


if __name__ == "__main__":
    main()
