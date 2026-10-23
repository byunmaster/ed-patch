"""구조 대조 — 원본과 빌드 결과의 모든 대사 구간에서 글자를 빼고 **엔진이 실제로 밟는 제어 코드 열**을 뽑아 구간마다 대조한다(마스터 10-22).

왜: 재배치(꼬리 옮김·쪽 넘김·채움)로 구간 끝의 제어 코드가 어긋나면 **다음 블록 호출이 막혀** 대사가 통째로 빠진다(ss-ed3 10-21: 채움 바이트 `FF FF` 가
다음 호출을 막아 새 게임 첫 장면에서 대사 1,046블록이 빠졌다). 한 블록씩 띄우는 하네스·qa 로는 안 보이고 연속 재생에서만 드러난다.

무엇을 본다 (엔진 규칙 근거는 `ALLOWED` 에 주소와 함께):
  ① 구간마다 빌드 롬에서 엔진이 읽는 길을 그대로 따라간다 — 제자리 / 트램펄린(`17 lo hi bank` → 꼬리 → `17 ret`) / 같은 뱅크 점프(`0F`, 3바이트 구간) /
     포인터 이전(`$A6~$A8` 즉치 → 새 자리). 따라간 끝이 **원문 구간 끝(b)** 에 정확히 닿아야 하고(다음 토큰·호출이 그대로 이어진다), 토큰 경계가 맞아야 한다.
  ② 따라간 토큰 열에서 글자(`$20~$E1` 등)·`$16`(빈 토큰)·줄바꿈 `$01` 을 빼고 남는 제어 코드 열이 원문 구간의 것과 같아야 한다.
     허용되는 차이는 `$05`(쪽 넘김) 추가뿐이다(조판기가 넘침에서 넣는다).
  ③ 구간 밖 구조 토큰(조건 `$11~$14` · 점프 `$0F` · 호출 `$10` · 끝 `$00` …)은 원본과 한 바이트도 안 달라야 하고, 점프·호출 목적지는 다시 쓴 구간의 한가운데가 아니어야 한다.

출력: 대조 구간 수 / 전체 구간 수 · 어긋남 · 허용 항목 종류별 수. `--table 경로` 로 구간별 표를 남긴다.

    python3 games/sfc-ed2/tools/check_structure.py [--table 경로] [--rom 빌드롬]
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import script

TRAMP = 0x17  # 트램펄린 제어코드(patches.TRAMP_CODE)
NOOP = 0x16  # 빈 토큰(build.NOOP)
JUMP = 0x0F
NEWLINE = 0x01
PAGE = 0x05
CTRL_IN_TEXT = {0x02, 0x04, 0x05, 0x08} | set(range(0x18, 0x20))  # 글자 구간 안에 올 수 있는 제어 코드(segs.TEXTLEVEL 의 비글자 몫)
MAXTOK = 5000

# 허용 목록 — 종류 · 무엇을 · 왜 · 엔진이 어떻게 처리하나(근거 주소). 이 꼴만 통과한다. 장부(`relocations.tsv`)의 종류·근거와 같은 출처다.
ALLOWED = {
    "채움": (
        "구간 끝을 `$16` 으로 채운다",
        "번역이 원문 바이트 수보다 짧아 남는 자리",
        "대사 출력기 `$C0:A870` 이 `$20` 미만 코드를 `$C0:AB28` 로 보내 점프표(`$C0:AB43`)로 핸들러에 넘기고, `$16` 핸들러는 `$C0:AEA3` 의 `rts` 뿐이라 다음 토큰을 그대로 읽는다",
    ),
    "쪽 넘김": (
        "조판기가 쪽 3줄이 넘치는 자리에 `$05` 를 넣는다",
        "한 쪽에 3줄까지만 들어간다(대사창 규격)",
        "`$05` 핸들러 `$C0:AC95`(키 대기 + 쪽 지움) — 원문도 같은 코드를 쓴다",
    ),
    "옮김": (
        "구간 머리 4바이트를 `17 lo hi bank` 로 덮고 번역문을 확장 뱅크로 옮긴다(끝에 `17 ret`)",
        "번역문이 원문 구간보다 길다",
        "`$17` 핸들러를 `$C0:FB10` 스텁으로 바꿨다(patches.STUB): `[$A6]` 의 3바이트를 읽어 `$A6~$A8` 를 새 자리로 돌린다 — `$0F`(`$C0:AD89`)와 같은 규약",
    ),
    "스텁": (
        "3바이트 구간을 같은 뱅크 점프 `0F lo hi` 로 덮고 번역문을 뱅크 안 빈 자리에 둔다(끝에 `0F ret`)",
        "번역문이 원문 3바이트보다 길고 트램펄린(4바이트)이 안 들어간다",
        "`$0F` 핸들러 `$C0:AD89` — `[$A6]` 의 16비트 주소로 같은 뱅크 점프",
    ),
    "포인터": (
        "구간을 가리키는 `$A6~$A8` 즉치(`A9 lo 8D A6 00 …`)를 새 자리로 돌린다",
        "4바이트 미만이라 트램펄린이 안 들어간다",
        "`$C0:A6E8` 대사 출력기가 `[$A6]` 24비트 포인터로 읽는다 — 호출 직전 코드가 즉치로 넣는다(relocate.a6_sites)",
    ),
}


def _tok_len(rom: bytes, i: int) -> int | None:
    return script.token_len(rom, i)


def follow(rom: bytes, src: bytes, a: int, b: int, sites=None) -> dict:
    """구간 (a, b)(원본 오프셋) 를 빌드 롬 `rom` 에서 엔진이 읽는 길로 따라간다 → {kind, toks:[(off,len)], end_ok, why}."""
    res = {"kind": None, "toks": [], "ok": False, "why": ""}
    snes_b = common.off2snes(b)

    def walk(start: int, stop) -> bool:
        i, n = start, 0
        while n < MAXTOK:
            if i >= len(rom):
                res["why"] = "롬 끝을 넘음"
                return False
            ln = _tok_len(rom, i)
            if ln is None:
                res["why"] = f"문법 밖 바이트 {rom[i]:02X} @{common.fmt(common.off2snes(i))}"
                return False
            if stop(i, ln):
                return True
            res["toks"].append((i, ln))
            i += ln
            n += 1
        res["why"] = "끝을 못 찾음"
        return False

    sites = [t for t in (sites or []) if t[0] < t[1] < t[2] <= t[0] + 16]  # `A9 lo 8D A6 00 · A9 hi 8D A7 00 · A9 bank 8D A8 00` 꼴이 아닌 우연한 일치는 뺀다
    if sites and bytes(rom[a:b]) == bytes(src[a:b]):  # 4바이트 미만 구간 — 원문 자리는 그대로(죽은 자리)이고 즉치 포인터가 새 자리로 갔다
        ptrs = {rom[lo] | rom[hi] << 8 | rom[bk] << 16 for lo, hi, bk in sites}
        if len(ptrs) != 1:
            res["why"] = "즉치 포인터 사이트들이 서로 다른 곳을 가리킨다"
            return res
        p = ptrs.pop()
        if p == (common.off2snes(a) & 0xFFFFFF):  # 안 옮김 — 제자리
            sites = None
        else:
            res["kind"] = "포인터"
            endtok = src[b]

            def stop(i, ln):
                return False

            i = common.snes2off(p)
            n = 0
            while n < MAXTOK:
                ln = _tok_len(rom, i)
                if ln is None:
                    res["why"] = "문법 밖(포인터 이전)"
                    return res
                res["toks"].append((i, ln))
                i += ln
                n += 1
                if rom[i - ln] == endtok:
                    break
            res["toks"].pop()  # 끝 토큰은 구간 밖 구조 — 원문의 끝 토큰과 같은지만 본다
            res["ok"] = rom[i - 1 - (ln - 1)] == endtok
            res["why"] = "" if res["ok"] else "끝 토큰이 원문과 다르다"
            return res

    if rom[a] == TRAMP and b - a >= 4:
        res["kind"] = "옮김"
        tgt = rom[a + 1] | rom[a + 2] << 8 | rom[a + 3] << 16
        if not walk(common.snes2off(tgt), lambda i, ln: rom[i] == TRAMP):
            return res
        end = res["toks"][-1][0] + res["toks"][-1][1] if res["toks"] else common.snes2off(tgt)
        ret = rom[end + 1] | rom[end + 2] << 8 | rom[end + 3] << 16
        if ret != snes_b:
            res["why"] = f"복귀 주소 {common.fmt(ret)} ≠ 원문 구간 끝 {common.fmt(snes_b)}"
            return res
        if any(x != NOOP for x in rom[a + 4 : b]):
            res["why"] = "트램펄린 뒤 남는 자리가 `$16` 이 아니다"
            return res
        res["ok"] = True
        return res
    if b - a == 3 and rom[a] == JUMP:
        res["kind"] = "스텁"
        bank = (common.off2snes(a) >> 16) & 0xFF
        tgt = (bank << 16) | rom[a + 1] | rom[a + 2] << 8
        if not walk(common.snes2off(tgt), lambda i, ln: rom[i] == JUMP):
            return res
        end = res["toks"][-1][0] + res["toks"][-1][1] if res["toks"] else common.snes2off(tgt)
        ret = rom[end + 1] | rom[end + 2] << 8
        if ret != snes_b & 0xFFFF:
            res["why"] = f"복귀 주소 ${ret:04X} ≠ 원문 구간 끝 ${snes_b & 0xFFFF:04X}"
            return res
        res["ok"] = True
        return res
    # 제자리 — 구간 끝에 정확히 닿아야 한다
    res["kind"] = "제자리"
    i = a
    while i < b:
        ln = _tok_len(rom, i)
        if ln is None:
            res["why"] = f"문법 밖 바이트 {rom[i]:02X} @{common.fmt(common.off2snes(i))}"
            return res
        res["toks"].append((i, ln))
        i += ln
    if i != b:
        res["why"] = f"토큰이 구간 끝({common.fmt(snes_b)})을 넘는다"
        return res
    res["ok"] = True
    return res


def ctrl_seq(d: bytes, toks) -> list[int]:
    """글자·빈 토큰·줄바꿈을 뺀 제어 코드 열(코드와 인자 바이트 포함 — 같은 코드라도 인자가 다르면 다르다)."""
    out = []
    for o, ln in toks:
        b = d[o]
        if b == NEWLINE or b == NOOP:
            continue
        if 0x20 <= b < 0xE0 or 0xE2 <= b < 0xF0 or b in (0xE0, 0xE1):
            continue
        out.append(int.from_bytes(d[o : o + ln], "big"))
    return out


def diff_seq(orig: list[int], built: list[int]) -> tuple[bool, int]:
    """원문 열이 빌드 열의 부분열이고 남는 것이 전부 `$05` 면 (True, 추가된 `$05` 수)."""
    j = 0
    extra = 0
    for x in built:
        if j < len(orig) and x == orig[j]:
            j += 1
        elif x == PAGE:
            extra += 1
        else:
            return False, 0
    return j == len(orig), extra


# 번역이 원문에 없던 화자 머리 `<1e>이름<04>` 를 붙인 구간(check_rules.CTL_EXEMPT 와 같은 목록) — `$1E`·`$04` 는 색 코드(`$18~$1F` 점프표 핸들러)라 글자 앞뒤에 놓여도 흐름을 안 바꾼다
HEADER_ADDED = {"$C5521A", "$CB74B3"}
ALLOWED["화자 머리 추가"] = (
    "원문에 없는 `<1e>이름<04>`(색 코드 쌍)를 구간 앞에 붙인다",
    "말하는 사람이 원문 구간에서 안 드러나 번역에서 밝힌다",
    "`$1E`·`$04` 는 색 코드(대사 출력기 `$C0:A870` → 점프표 `$C0:AB43`)라 출력 색만 바꾸고 흐름·끝 토큰을 건드리지 않는다 — 원문도 같은 쌍을 화자 머리에 쓴다",
)


def check_segment(src: bytes, rom: bytes, a: int, b: int, sites=None, key: str = "", translated: bool = True) -> dict:
    if not translated:  # 원문 유지(번역 안 한 구간) — 바이트가 그대로여야 한다
        ok = bytes(rom[a:b]) == bytes(src[a:b])
        return {"a": a, "b": b, "kind": "원문 유지", "ok": ok, "why": "" if ok else "번역 안 한 구간인데 바이트가 바뀌었다", "added05": 0, "pad": 0, "header": 0}
    f = follow(rom, src, a, b, sites)
    row = {"a": a, "b": b, "kind": f["kind"], "ok": False, "why": f["why"], "added05": 0, "pad": 0, "header": 0}
    if not f["ok"]:
        return row
    so = script.tokens(src, a, b)
    orig = ctrl_seq(src, [(o, ln) for o, ln in so if o < b])
    built = ctrl_seq(rom, f["toks"])
    ok, extra = diff_seq(orig, built)
    if not ok and key in HEADER_ADDED:
        built2 = [x for x in built if x not in (0x1E, 0x04)] if key == "$C5521A" else [x for x in built if x != 0x1E]
        ok, extra = diff_seq(orig, built2)
        row["header"] = 1 if ok else 0
    row["added05"] = extra
    if not ok:
        row["why"] = "제어 코드 열이 원문과 다르다: 원문 " + " ".join(f"{x:X}" for x in orig) + " ≠ 빌드 " + " ".join(f"{x:X}" for x in built)
        return row
    row["pad"] = sum(1 for o, _ in f["toks"] if rom[o] == NOOP) + (b - a - 4 if f["kind"] == "옮김" else 0)
    if f["kind"] == "제자리":
        row["pad"] = sum(1 for o, _ in f["toks"] if rom[o] == NOOP)
    row["ok"] = True
    return row


# 구조 대조에서 제외하는 가짜 토큰 — 코드 바이트가 글자·점프로 읽힌 단위(근거 없이 늘리지 않는다)
FALSE_TOKENS = {
    0x73FFA: "`$C7:3FF0~` 은 코드(`a9 0b 8d 0f 04 80 11` = `LDA #$0B / STA $040F` …)라 `8d 0f 04` 가 글자+점프 토큰으로 읽힌 것 — 이 자리를 메시지로 읽는 흐름이 없다(`$A6` 즉치도 코드 오검출)",
}
ALLOWED["가짜 토큰(코드 바이트)"] = ("코드 영역이 대사 단위로 잘못 읽힌 점프 토큰을 구조 대조에서 뺀다", "스캐너가 코드 바이트를 글자 구간으로 읽었다", "해당 주소 앞뒤가 코드(디스어셈블 확인)이고 번역 구간이 아니다")


def check_outside(src: bytes, rom: bytes, units, spans) -> tuple[int, list]:
    """구간 밖 구조 토큰이 원본과 같은가 + 점프·호출 목적지가 다시 쓴 구간의 한가운데가 아닌가."""
    import bisect

    starts = [a for a, _ in spans]
    bad, n = [], 0

    def inside(o: int):
        k = bisect.bisect_right(starts, o) - 1
        return spans[k] if k >= 0 and spans[k][0] <= o < spans[k][1] else None

    for s, e in units:
        bank = (common.off2snes(s) >> 16) & 0xFF
        for o, ln in script.tokens(src, s, e):
            if ln == 0:
                break
            sp = inside(o)
            if sp is not None:
                continue
            n += 1
            if rom[o : o + ln] != src[o : o + ln]:
                bad.append((o, "구조 토큰이 원본과 다르다"))
                continue
            if src[o] in (JUMP, 0x10) and o + 2 < len(src):
                t = common.snes2off((bank << 16) | src[o + 1] | src[o + 2] << 8)
                sp2 = inside(t)
                if sp2 is not None and sp2[0] != t and o not in FALSE_TOKENS:
                    bad.append((o, f"점프·호출 목적지 {common.fmt(common.off2snes(t))} 가 다시 쓴 구간 {common.fmt(common.off2snes(sp2[0]))} 의 한가운데"))
                elif sp2 is None and t < len(src) and rom[t] != src[t] and o not in FALSE_TOKENS:
                    # 구간 밖이라도 목표 바이트(예: 다른 메시지의 종료 바이트)가 스텁·채움에 덮였으면, 그 점프가 스텁 주소를 글자로 읽는다
                    bad.append((o, f"점프·호출 목적지 {common.fmt(common.off2snes(t))} 의 바이트가 원본과 다르다(종료 바이트 덮임)"))
    return n, bad


def load_ledger(path: Path) -> list[dict]:
    """`relocations.tsv`(빌드가 뽑은 장부) → 행 목록. 좌표는 SNES 24비트 정수."""
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines()[1:]:
        c = ln.split("\t")
        if len(c) < 8:
            continue
        a = lambda t: int(t.replace("$", "").replace(":", ""), 16)  # noqa: E731
        rows.append({"key": c[0], "kind": c[1], "orig": a(c[2]), "new": a(c[2]) if c[3] == "제자리" else a(c[3]), "n_new": int(c[4])})
    return rows


def derived_kinds(rows: list) -> dict[str, set]:
    """롬에서 따라가 얻은 구간별 재배치 종류 — 장부와 맞대 보는 쪽(빌드와 독립)."""
    import segs

    out: dict[str, set] = {}
    for r in rows:
        if not r["ok"] or r["kind"] in ("원문 유지", "D7(범위 밖)") or (r["kind"] == "제자리" and not (r["pad"] or r["added05"])):
            continue
        k = segs.seg_id(r["a"])
        st = out.setdefault(k, set())
        if r["kind"] in ("옮김", "스텁", "포인터"):
            st.add(r["kind"])
        if r["pad"]:
            st.add("채움")
        if r["added05"]:
            st.add("쪽 넘김")
    return out


def check_ledger(rows: list, ledger: list[dict]) -> list[str]:
    """장부(빌드가 적은 것) ↔ 롬에서 따라간 것. 장부에 없는 재배치가 롬에 있거나 장부에만 있으면 어긋남."""
    led: dict[str, set] = {}
    for r in ledger:
        k = r["key"].split(":")[0]
        if not k.startswith("$") or k.startswith("$D7"):  # `$D7` 오프닝·엔딩은 포인터 표 항목을 돌리는 별도 길 — 아래 `check_d7` 가 본다
            continue
        led.setdefault(k, set()).add(r["kind"])
    der = derived_kinds(rows)
    bad = []
    for k in sorted(set(led) | set(der)):
        if led.get(k, set()) != der.get(k, set()):
            bad.append(f"{k}: 장부 {sorted(led.get(k, set()))} ≠ 롬 {sorted(der.get(k, set()))}")
    return bad


def check_extension(rom: bytes, ledger: list[dict]) -> list[str]:
    """확장 영역·뱅크 빈 자리에 쓰인 바이트가 전부 장부의 새 좌표 범위 안인가(장부 밖 쓰기 = 어긋남). 글꼴·조사 표는 고정 영역."""
    import build
    import patches

    cover = []
    for r in ledger:
        if r["new"] != r["orig"] or r["kind"] in ("스텁",):
            cover.append((common.snes2off(r["new"]), common.snes2off(r["new"]) + r["n_new"]))
    # 고정 영역 — 글꼴 표(`$D8:0000~9FFF`)·조사 표(`$D8:F000~F83F`): 대사 재배치가 아니라 글리프·조사 훅 자료다(구조와 무관)
    fixed = [(patches.FONT_OUT, patches.FONT_OUT + 0xA000), (common.snes2off(patches.JOSA_TABLE), common.snes2off(patches.JOSA_PAIRS) + 0x40)]
    regions = [(common.ROM_SIZE, len(rom))] + [(((bank - 0xC0) << 16) + a, ((bank - 0xC0) << 16) + b + 1) for bank, rs in build.LOCAL_FREE.items() for a, b in rs]
    bad = []
    for lo, hi in regions:
        i = lo
        while i < hi:
            if rom[i] == 0xFF:
                i += 1
                continue
            j = i
            while j < hi and rom[j] != 0xFF:
                j += 1
            if not any(x <= i and j <= y for x, y in cover + fixed):
                # 일부만 걸쳐도 통과 — 런이 인접 항목 둘에 걸칠 수 있다(경계가 맞닿음)
                if not all(any(x <= k < y for x, y in cover + fixed) for k in range(i, j)):
                    bad.append(f"{common.fmt(common.off2snes(i))}~{common.fmt(common.off2snes(j))}: 장부에 없는 쓰기")
            i = j
    return bad


def run(rom: bytes, src: bytes | None = None, table: Path | None = None) -> dict:
    import relocate
    import script as _s
    import segs

    import build

    src = src if src is not None else common.rom_bytes()
    spans = sorted(segs.segments(src))
    seg_map, _, _ = build.collect_texts(src)
    a6 = {}
    for a, b in spans:
        if b - a < 4 and segs.seg_id(a) in seg_map:
            s = relocate.a6_sites(src, common.off2snes(a))
            if s:
                a6[a] = s
    rows = []
    for a, b in spans:
        key = segs.seg_id(a)
        if (common.off2snes(a) >> 16) == 0xD7:  # 오프닝·엔딩 문자열 — 포인터 표 항목을 돌리는 별도 길(장부 「포인터」)이라 여기선 제외
            rows.append({"a": a, "b": b, "kind": "D7(범위 밖)", "ok": True, "why": "", "added05": 0, "pad": 0, "header": 0})
            continue
        rows.append(check_segment(src, rom, a, b, a6.get(a), key, key in seg_map))
    rewritten = [(a, b) for a, b in spans if segs.seg_id(a) in seg_map]
    units = [(u0, u1) for u0, u1 in _s.all_units(src) if not segs.excluded(u0) and (common.off2snes(u0) >> 16) not in (0xC0, 0xC1, 0xD7)]
    n_out, bad_out = check_outside(src, rom, units, rewritten)
    kinds = Counter()
    for r in rows:
        if r["ok"] and r["kind"] != "제자리":
            kinds[r["kind"]] += 1
        if r["ok"] and r["pad"]:
            kinds["채움"] += 1
        if r["ok"] and r["added05"]:
            kinds["쪽 넘김"] += 1
        if r["ok"] and r.get("header"):
            kinds["화자 머리 추가"] += 1
        if r["ok"] and r["kind"] == "원문 유지":
            kinds["원문 유지"] += 1
    fails = [r for r in rows if not r["ok"]]
    ledger_path = common.GAME_DIR / "relocations.tsv"
    ledger = load_ledger(ledger_path) if ledger_path.exists() else []
    led_bad = check_ledger(rows, ledger) if ledger else ["장부(relocations.tsv)가 없다 — build.py 가 뽑는다"]
    ext_bad = check_extension(rom, ledger) if ledger else []
    out = {"ledger_n": len(ledger), "ledger_bad": led_bad, "ext_bad": ext_bad, "rows": rows, "total": len(spans), "compared": len(rows), "fails": fails, "outside_n": n_out, "outside_bad": bad_out, "kinds": kinds, "added05": sum(r["added05"] for r in rows)}
    if table:
        with open(table, "w", encoding="utf-8") as f:
            f.write("구간\t방식\t결과\t추가 쪽 넘김\t채움\t사유\n")
            for r in rows:
                f.write(f"{common.fmt(common.off2snes(r['a']))[1:].replace(':', '')}\t{r['kind']}\t{'통과' if r['ok'] else '어긋남'}\t{r['added05']}\t{r['pad']}\t{r['why']}\n")
    return out


def main() -> int:
    args = sys.argv[1:]
    table = Path(args[args.index("--table") + 1]) if "--table" in args else None
    if "--rom" in args:
        rom = Path(args[args.index("--rom") + 1]).read_bytes()
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        rom = (common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc").read_bytes()
    r = run(rom, table=table)
    nf, nb = len(r["fails"]), len(r["outside_bad"]) + len(r["ledger_bad"]) + len(r["ext_bad"])
    print(f"구조 대조: 대사 구간 {r['compared']:,}/{r['total']:,} 대조 · 구간 밖 구조 토큰 {r['outside_n']:,} 대조 · 어긋남 {nf + nb} (구간 {nf} · 구조·장부 {nb}) · 장부 {r['ledger_n']:,}행")
    print("  허용 항목(종류별 구간 수): " + " · ".join(f"{k} {r['kinds'].get(k, 0)}" for k in ALLOWED) + f" · 원문 유지 {r['kinds'].get('원문 유지', 0)} · 추가된 쪽 넘김 {r['added05']}개")
    for x in r["fails"][:12]:
        print(f"    ✗ {common.fmt(common.off2snes(x['a']))} [{x['kind']}] {x['why']}")
    for o, why in r["outside_bad"][:12]:
        print(f"    ✗ {common.fmt(common.off2snes(o))} {why}")
    for w in r["ledger_bad"][:12] + r["ext_bad"][:12]:
        print(f"    ✗ {w}")
    return 0 if nf + nb == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
