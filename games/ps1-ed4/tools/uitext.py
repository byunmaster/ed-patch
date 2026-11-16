"""실행파일 UI 문안 정본 — 메뉴·시스템 메시지·실행파일 속 글(ps1-ed3 `uitext` 의 ED4 몫, 처음부터 얇게).

대사(`script/`)와 자리가 다르다 — UI 는 아카이브 멤버가 아니라 **실행파일 안**에 산다. 키는 그 문자열의 **실행파일 오프셋**(헤더 포함 파일 오프셋)이다.

```
ui_ed4.json   {"disc": "ed4", "strings": {"0x06D472": {"jp": "<원문 지문>", "kr": "처음부터 시작"}}}
```

🔴 **원문은 안 담고 지문(코드열 sha1 앞 10자)만 담는다**(루트 「저작권」 — UI 에 문장급이 섞여 있다). 지문이 다르면 번역이 남의 자리에 붙은 것이라 게이트가 운다.
🔴 **길이 규칙(지금)**: 표를 못 찾은 자리는 **고정**이다 — 한국어 코드 수 ≤ 원문 코드 수. 짧으면 종결 코드 뒤를 0 으로 채운다(아무도 안 가리킨다고 가정 —
   🔴 **가정이다**: 이 자리를 가리키는 표가 있으면 길이를 바꿔도 되는지는 따로 본다. 표 자리의 칸 예산은 아직 안 열었다 — 길이가 모자라면 `limit` 칸이 알려 준다).
종결 코드(0x8000·0x8002·0)는 원본 값을 그대로 쓴다 — 뜻(대기·줄 끝 등)은 모르고 **바꾸지 않는다**.

    python3 tools/uitext.py review      # 검토표(원문+칸) → work/review/ui_ed4.json  ⚠ 커밋 금지
    python3 tools/uitext.py put 0x06DF72 '처음부터 시작'   # 정본에 한 줄(지문은 원본에서 계산)
    python3 tools/uitext.py check       # 지문·길이 (게이트)
"""

import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump
import exetab
import font
import halfwidth
import hangul
import textenc

KINDS = ("menu", "text")  # UI 문안 + 실행파일 속 글 — 우리가 쓴다(`ui_ed4.json`)
NOUN_KINDS = (
    "monster",
    "spell",
    "item",
    "person",
    "place",
    "rank",
)  # 고유명사 — **정본**(`shared/canon/nouns/ed4.json`)에서 읽는다(게임 폴더에 표를 안 둔다, 규칙 3-3)
ALL_KINDS = KINDS + NOUN_KINDS
CANON = os.path.join(common.ROOT, "ui_ed4.json")


def raw_string(exe, off, limit=200):
    """(코드열, 종결값) — **코드표를 안 본다.**"""
    codes = []
    for k in range(limit):
        p = off + 2 * k
        if p + 2 > len(exe):
            return None, None
        w = struct.unpack_from("<H", exe, p)[0]
        if dump.is_term(w):
            return codes, w
        codes.append(w)
    return None, None


def stamp(codes):
    return hashlib.sha1(struct.pack(f"<{len(codes)}H", *codes)).hexdigest()[:10]


def sites(exe):
    """{오프셋: {"jp", "codes", "term", "kind", "table": (표 주소, base, N)|None, "budget": 칸 바이트}} — 구역 라벨이 KINDS 인 낱말들.

    🔴 **표가 가리키는 건 목록의 머리**일 수 있다(`exetab.units`) — 머리와 그 뒤 조각이 한 단위라 단위 전체가 칸 안에서 길이·자리를 바꿀 수 있다(`table` 있음).
       표 단위에 안 드는 문자열은 순차 스캔·절대 주소(닻)로 읽힐 수 있어 **제자리·고정 길이**다(`table=None`).
    """
    cm = textenc.charmap()
    tabs = exetab.scan_tables(exe, cm)
    regs = dump.survey(exe)
    kind_at = {o: r["kind"] for r in regs for o in r["offs"]}
    glued = dict(exetab.glued_entries(exe, tabs))
    out = {}
    own = [
        (t["table"], t["table"] + 2 * t["n"]) for t in tabs
    ]  # 표 자신은 글이 아니다(코드로 읽으면 한자처럼 보인다)
    for t in tabs:
        key = (t["table"], t["base"], t["n"])
        for lo, hi, us in exetab.unit_chunks(exe, t["table"], t["base"], t["n"]):
            for u in us:
                kind = next((kind_at[o] for o, _c, _t in u["pieces"] if o in kind_at), None)
                if kind is None:
                    kind = exetab.kind_of(glued.get(u["start"], []), kind_at)
                if kind not in ALL_KINDS:
                    continue
                for off, codes, term in u["pieces"]:
                    if (
                        codes
                        and all(c in cm for c in codes)
                        and not any(a <= off < b for a, b in own)
                    ):
                        out[off] = {
                            "jp": "".join(cm[c] for c in codes),
                            "codes": codes,
                            "term": term,
                            "kind": kind,
                            "table": key,
                            "budget": hi - lo,
                        }
    for r in regs:  # 표 밖(닻) — 제자리 고정
        if r["kind"] not in ALL_KINDS:
            continue
        for off, jp in zip(r["offs"], r["items"], strict=True):
            if off in out or any(a <= off < b for a, b in own):
                continue
            codes, term = raw_string(exe, off)
            if codes:
                out[off] = {
                    "jp": jp,
                    "codes": codes,
                    "term": term,
                    "kind": r["kind"],
                    "table": None,
                    "budget": 0,
                }
    return out


def load():
    if not os.path.exists(CANON):
        return {}
    with open(CANON, encoding="utf-8") as f:
        doc = json.load(f)
    return {int(k, 16): v for k, v in doc["strings"].items()}


def save(rows):
    rows = {f"0x{o:06X}": v for o, v in sorted(rows.items()) if v.get("kr")}
    with open(CANON, "w", encoding="utf-8") as f:
        json.dump({"disc": "ed4", "strings": rows}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def noun_rows(ss):
    """{오프셋: 한국어} — 고유명사 구역 자리 중 **정본에 원문이 그대로 있는** 것(`canon.lookup`). 없는 것은 `missing_nouns` 가 센다."""
    from shared import canon

    out = {}
    for off, s in ss.items():
        if s["kind"] in NOUN_KINDS:
            kr = canon.lookup(s["jp"], s["kind"], "ed4")
            if kr:
                out[off] = kr
    return out


def missing_nouns(ss):
    from shared import canon

    return {
        s["jp"]
        for s in ss.values()
        if s["kind"] in NOUN_KINDS and not canon.lookup(s["jp"], s["kind"], "ed4")
    }


def rows_for(ss):
    """{오프셋: {"kr":…, "from": "ui"|"canon"}} — `ui_ed4.json`(우리가 쓴 것)이 정본(고유명사)을 이긴다."""
    out = {o: {"kr": kr, "from": "canon"} for o, kr in noun_rows(ss).items()}
    for o, row in load().items():
        out[o] = {"kr": row["kr"], "from": "ui", "jp": row["jp"]}
    return out


def kr_codes(kr, table=None):
    import josa_build

    return hangul.encode(josa_build.flex([kr])[0], table)


def plan(exe, table=None):
    """(표별 새 문안, 제자리 새 문안, [사유]) — 정본을 자리별로 가른다. 길이 초과(고정 자리)·지문 불일치는 사유로."""
    ss = sites(exe)
    bad, by_table, fixed = [], {}, {}
    for off, row in sorted(rows_for(ss).items()):
        s = ss.get(off)
        if s is None:
            bad.append(f"0x{off:06X}: 구역 라벨 {ALL_KINDS} 밖이거나 원본에 없는 자리")
            continue
        if row["from"] == "ui" and stamp(s["codes"]) != row["jp"]:
            bad.append(f"0x{off:06X}: 원문 지문이 다르다 — 번역이 남의 자리에 붙었다")
            continue
        try:
            codes = kr_codes(row["kr"], table)
        except KeyError as e:
            bad.append(f"0x{off:06X}: 글리프 자리 정본에 없는 글자 {e} — `slots.py assign`")
            continue
        if s["table"] is None:
            if len(codes) > len(s["codes"]):
                bad.append(
                    f"0x{off:06X}: 길이 초과 {len(codes)} > {len(s['codes'])}(제자리·고정 자리)"
                )
            else:
                fixed[off] = (codes, s)
        else:
            by_table.setdefault(s["table"], {})[off] = codes
    return by_table, fixed, bad


def _pad(table):
    return (table or hangul.load())[" "]


ITEM_TBL = 0x000A38  # 🔴 아이템 메뉴 구조체 — 스택에 복사해 읽는 자료라 제자리·arena 로 못 옮긴다 → 둘째 동굴로 통째로(`halfwidth.patch_hx`, 사용처 패치)
ITEM_BLOB = bytearray()  # 새 구조체 바이트(표 u16 N개 + 단위들) — 둘째 동굴 `ITEM_STRUCT` 에 쓴다
RELOC = {}  # {원래 표 주소: 새 표 주소(파일 오프셋)} — 마지막 `apply` 에서 arena 로 옮긴 표들(되읽기가 쓴다)


def apply(exe, table=None):
    """실행파일 버퍼(`bytearray`)에 정본 문안을 쓴다 — 표 항목은 칸 안에서 다시 싸고, 칸이 모자라면 **그 표를 글리프 arena 로 옮기고**, 나머지는 제자리. 쓴 자리 수를 돌려준다.

    🔴 칸 예산을 넘는다고 번역을 줄이지 않는다(규칙 3-6, 관리자 10-24) — 모자란 표는 `exetab.relocate_units`(표 기준 상수 `lui+addiu` 를 고쳐 arena 로)로 옮긴다.
    `ED_FORCE_RELOC=0x06DB80,…`(표 주소) 를 주면 그 표를 칸이 넉넉해도 옮긴다 — 옮기기 길을 실게임으로 시험하는 용도(`test-` 빌드에서만).
    """
    import slots

    table = table or hangul.load()
    slots.assert_arena_free(table)
    nfr = apply_frags(exe, table)  # 🔴 표 재구축 전에 — 표 안 단위에 낀 조각이라 재구축·옮기기가 새 바이트를 그대로 싣는다
    by_table, fixed, bad = plan(bytes(exe), table)
    if bad:
        raise SystemExit("🔴 UI 문안 정본이 안 맞는다:\n  " + "\n  ".join(bad[:8]))
    pad = _pad(table)
    forced = {int(x, 16) for x in os.environ.get("ED_FORCE_RELOC", "").split(",") if x}
    # 옮길 자리(조각) — 첫째 = 글리프 arena(1653~1872, 원본 문안이 안 쓰는 한자 칸), 둘째 = 한글에서 뺀 연속 29칸(코드 72~100). 표 하나(옮긴 단위들)는 한 조각 안에 통째로 앉는다.
    g = font.GLYPH_BYTES
    a_lo, _a_hi = slots.arena_range()
    base0 = a_lo - slots.ARENA[0] * g  # 글리프 배열 시작(파일 오프셋)
    segs = [
        [a_lo, a_lo + (slots.ARENA_SAFE_END - slots.ARENA[0]) * g],
        [base0 + slots.ARENA2[0] * g, base0 + slots.ARENA2[1] * g],
    ]
    cursors = [seg[0] + (seg[0] & 1) for seg in segs]
    dead_segs = []  # [처음, 끝, 커서] — 옮겨진 표의 옛 u16 배열(죽은 자료)
    RELOC.clear()
    n = 0
    ITEM_BLOB.clear()
    for (tbl, base, cnt), m in sorted(by_table.items(), key=lambda kv: (-kv[0][2], kv[0][0])):
        if tbl == ITEM_TBL and not any(os.environ.get(k) == "1" for k in ("ED_NO_HX", "ED_NO_HOOK", "ED_HOOK_TRAP", "ED_NO_ITEM")):
            import halfwidth

            dest = halfwidth._off(halfwidth.ITEM_STRUCT)
            out, end, _moved = exetab.relocate_units(
                bytes(exe), tbl, base, cnt, m, dest, pad_code=pad, force_all=True, patch_refs=False
            )
            if end - dest > halfwidth.ITEM_STRUCT_MAX:
                raise SystemExit(f"🔴 아이템 메뉴 구조체 {end - dest}B 가 둘째 동굴 자리({halfwidth.ITEM_STRUCT_MAX}B)보다 크다")
            ITEM_BLOB[:] = out[dest:end]
            RELOC[tbl] = dest
            n += len(m)
            continue
        try:
            if tbl in forced:
                raise exetab.ExeTextError("강제 옮기기 시험")
            out, _slack = exetab.rebuild_units(bytes(exe), tbl, base, cnt, m, pad_code=pad)
        except exetab.ExeTextError as e:
            why = str(e)
            placed = None
            last = None
            dead_done = False
            for dk, dead in enumerate(dead_segs):  # 🔴 먼저 옮긴 표의 죽은 u16 배열이 있으면 뺀 단위들은 거기에(새 표만 첫 자리) — 첫 자리를 아낀다
                try:
                    out, end, _moved = exetab.relocate_units(
                        bytes(exe), tbl, base, cnt, m, cursors[0], pad_code=pad, units_off=dead[2]
                    )
                except exetab.ExeTextError as e2:
                    last = e2
                    continue
                if end <= dead[1] and cursors[0] + 2 * cnt <= segs[0][1]:
                    RELOC[tbl] = cursors[0]
                    cursors[0] += 2 * cnt
                    cursors[0] += cursors[0] & 1
                    dead[2] = end + (end & 1)
                    dead_segs.append([tbl, tbl + 2 * cnt, tbl + (tbl & 1)])
                    dead_done = True
                    break
            if dead_done:
                exe[:] = out
                n += len(m)
                continue
            for k in (1, 0):  # 작은 둘째 자리를 먼저 — 들어가는 표는 거기로 보내 첫째(큰) 자리를 아낀다
                seg = segs[k]
                try:
                    out, end, _moved = exetab.relocate_units(
                        bytes(exe), tbl, base, cnt, m, cursors[k], pad_code=pad
                    )
                except exetab.ExeTextError as e2:
                    last = e2
                    continue
                if end <= seg[1]:
                    placed = (k, end)
                    break
                last = f"자리 {k} 에 안 든다({end - seg[0]}B > {seg[1] - seg[0]}B)"
            if placed is None:
                raise SystemExit(f"🔴 UI 표 0x{tbl:06X}: 칸 재구축 실패({why}) · 옮기기도 실패({last})")
            k, end = placed
            RELOC[tbl] = cursors[k]
            cursors[k] = end + (end & 1)
            dead_segs.append([tbl, tbl + 2 * cnt, tbl + (tbl & 1)])  # 옛 표 = 죽은 배열 — 뒤 표의 뺀 단위가 쓴다
        exe[:] = out
        n += len(m)
    for off, (codes, s) in fixed.items():
        # 🔴 남는 칸은 종결 **앞**을 안 보이는 채움 글자로 — 종결 뒤를 0 으로 채우면 순차 스캔 목록이 구조가 달라져 끊긴다(ED3 실측)
        words = [*codes, *([pad] * (len(s["codes"]) - len(codes))), s["term"]]
        exe[off : off + 2 * len(words)] = struct.pack(f"<{len(words)}H", *words)
        n += 1
    return n + nfr


def check(exe=None):
    """(옮긴 줄, 전체 자리, [사유]) — 표 칸 예산은 **실제로 재구축해 보고** 넘치면 사유로."""
    exe = bytes(exe or common.read_file(common.EXE_PATH))
    ss = sites(exe)
    table = hangul.load()
    *_, bad = plan(exe, table)
    if not bad:
        try:
            apply(bytearray(exe), table)
        except SystemExit as e:
            bad.append(str(e))
    return len(load()), len(ss), bad


def put(off, kr):
    """정본에 한 줄을 넣는다(지문은 원본에서 계산). 길이 초과·없는 자리는 `SystemExit`."""
    exe = bytes(common.read_file(common.EXE_PATH))
    s = sites(exe).get(off)
    if s is None:
        raise SystemExit(f"0x{off:06X} 는 UI 자리가 아니다")
    if s["table"] is None and len(kr) > len(
        s["codes"]
    ):  # 고정 자리 — 글자 하나 = 코드 하나(정확한 검사는 `check` — 자리 배정 뒤)
        raise SystemExit(f"0x{off:06X}: 길이 초과 {len(kr)} > {len(s['codes'])}")
    rows = load()
    rows[off] = {"jp": stamp(s["codes"]), "kr": kr}
    save(rows)


def moved(orig, new, key):
    """{원래 조각 오프셋: 새 오프셋} — 표 하나에서 단위(목록)가 어디로 갔나(표 항목 순서로 짝지어 조각 순서로 대응)."""
    tbl, base, cnt = key
    ntbl = RELOC.get(tbl, tbl)  # 옮긴 표는 새 표 시작이 곧 새 기준이다
    o_ents = struct.unpack_from(f"<{cnt}H", orig, tbl)
    n_ents = struct.unpack_from(f"<{cnt}H", new, ntbl)
    n_starts = {ntbl + x for x in n_ents}
    out = {}
    for u in exetab.units(orig, tbl, base, cnt):
        i = next(i for i, x in enumerate(o_ents) if base + x == u["start"])
        pieces = exetab.unit_at(new, ntbl + n_ents[i], n_starts)
        if len(pieces) != len(u["pieces"]):
            raise SystemExit(
                f"🔴 표 0x{tbl:06X}: 단위 0x{u['start']:06X} 의 조각 수가 달라졌다 {len(u['pieces'])}→{len(pieces)}"
            )
        for (o, _c, _t), (nw, _c2, _t2) in zip(u["pieces"], pieces, strict=True):
            out[o] = nw
    return out


def readback(orig, new, table=None):
    """[사유] — 구운 실행파일(`new`)에서 정본 문안을 **다시 읽어** 원본(`orig`) 자리에 대응하는 자리에 코드로 앉았나(표 단위는 새 표가 가리키는 자리)."""
    table = table or hangul.load()
    ss = sites(orig)
    bad, maps = [], {}
    for off, row in rows_for(ss).items():
        s = ss[off]
        want = kr_codes(row["kr"], table)
        at = off
        if s["table"] is not None:
            if s["table"] not in maps:
                maps[s["table"]] = moved(orig, new, s["table"])
            at = maps[s["table"]][off]
        got, _ = raw_string(new, at)
        # 칸을 채운 안 보이는 글자(공백)는 끝에 붙을 수 있다
        trimmed = list(got or [])
        while trimmed and len(trimmed) > len(want) and trimmed[-1] == _pad(table):
            trimmed.pop()
        if trimmed != want:
            bad.append(f"0x{off:06X}(→0x{at:06X}): 되읽은 것이 정본과 다르다")
    return bad


def put_many(mapping):
    """{오프셋: 한국어} 를 한 번에 넣는다(지문은 원본에서 계산). 이미 있는 줄은 덮어쓴다 — 그 오프셋이 원본에 없거나 고정 자리 길이를 넘으면 `SystemExit`."""
    exe = bytes(common.read_file(common.EXE_PATH))
    ss = sites(exe)
    rows = load()
    for off, kr in mapping.items():
        s = ss.get(off)
        if s is None:
            raise SystemExit(f"0x{off:06X} 는 UI 자리가 아니다")
        if s["table"] is None and len(kr) > len(s["codes"]):
            raise SystemExit(
                f"0x{off:06X}: 길이 초과 {len(kr)} > {len(s['codes'])}(고정 자리) — 「{kr}」"
            )
        rows[off] = {"jp": stamp(s["codes"]), "kr": kr}
    save(rows)
    return len(mapping)


FRAG_PATH = os.path.join(common.ROOT, "ui_frag_ed4.json")


def frags():
    """{오프셋: {"jp"(지문), "n"(칸 수), "kr"}} — 표에 안 잡히는 조각(`ui_frag_ed4.json`)."""
    with open(FRAG_PATH, encoding="utf-8") as f:
        return {int(k, 16): v for k, v in json.load(f)["rows"].items()}


def apply_frags(exe, table=None):
    """표에 안 잡히는 조각을 **제자리에 같은 칸 수로** 쓴다 — 원문 지문이 안 맞으면 실패. 남는 칸은 안 보이는 채움 글자."""
    table = table or hangul.load()
    pad = _pad(table)
    n = 0
    for off, row in frags().items():
        got = list(struct.unpack_from(f"<{row['n']}H", exe, off))
        if stamp(got) != row["jp"]:
            raise SystemExit(f"🔴 조각 0x{off:06X} 가 원판이 아니다")
        new = kr_codes(row["kr"], table)
        if len(new) > row["n"]:
            raise SystemExit(f"🔴 조각 0x{off:06X}: 칸 {row['n']} 보다 길다({len(new)})")
        fill = [pad] * (row["n"] - len(new))
        new = fill + new if row.get("align") == "right" else new + fill
        struct.pack_into(f"<{row['n']}H", exe, off, *new)
        n += 1
    return n


def used_chars():
    exe = bytes(common.read_file(common.EXE_PATH))
    return "".join(row["kr"] for row in rows_for(sites(exe)).values()) + "".join(r["kr"] for r in frags().values())


def review():
    exe = bytes(common.read_file(common.EXE_PATH))
    ss = sites(exe)
    have = load()
    out = {
        f"0x{o:06X}": {
            "jp": s["jp"],
            "kr": have.get(o, {}).get("kr", ""),
            "limit": f"{len(s['codes'])}자" if s["table"] is None else f"칸 {s['budget']}B",
            "kind": s["kind"],
        }
        for o, s in sorted(ss.items())
    }
    p = os.path.join(common.REVIEW_DIR, "ui_ed4.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"disc": "ed4", "strings": out}, f, ensure_ascii=False, indent=1)
    return len(out), p


def main(argv):
    common.verify_source()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "review":
        n, p = review()
        print(f"검토표 {n} 자리 → {p}  (⚠ 원문 포함 — 커밋 금지)")
        return 0
    if cmd == "put" and len(argv) >= 4:
        put(int(argv[2], 16), argv[3])
        return 0
    if cmd == "check":
        n, tot, bad = check()
        print(f"UI 문안 — 옮긴 {n} / 자리 {tot}")
        for b in bad:
            print("  🔴", b)
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
