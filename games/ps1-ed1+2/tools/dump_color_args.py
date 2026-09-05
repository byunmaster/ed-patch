#!/usr/bin/env python3
"""원판이 **어느 창을 무슨 색으로 칠하는가** — 콜사이트 인자를 전수로 뽑는다.

**왜(2026-09-03).** 색은 문안에 없다. 문안에는 `%c` 자리만 있고 **값은 스크립트
콜사이트가 인자로 넘긴다.** 그래서 지금까지 색 판정이 전부 「유저가 인게임에서 보고
알려 준 것」에 묶여 있었고, 그 공백을 내 추론으로 메우다 두 번 틀렸다 —
「같은 획득 안내면 같은 색」(파에토 랄프는 원판이 통째로 초록) · 「구간마다 아이템만
주황」(원판은 콜사이트로 가른다). 유저 QA 2026-09-01·09-02.

문체는 원문이 **문안 안에** 있어서 세어 보니 규칙이 있었다(`check_log_register`).
색도 같은 방식으로 판단하려면 **먼저 읽을 수 있어야 한다.** 이 도구가 그 자리다.

## 어떻게 읽나

메시지 조립은 `sprintf(0x800CC740)` 한 곳으로 모인다. 콜사이트는 늘 같은 꼴이다:

    addiu a0, sp, 0x20            ; 조립 버퍼
    lui   a1, hi / addiu a1, lo   ; **서식 문자열 = 대사 블록 주소**
    addiu a2, zero, 2             ; 인자1
    addiu a3, zero, 1             ; 인자2
    addiu v0, zero, 8  / sw v0, 0x10(sp)   ; 인자3
    addiu v0, zero, 3  / sw v0, 0x14(sp)   ; 인자4  ← 이 값이 색이다
    ...
    jal   0x800CC740

⇒ 인자열은 `a2, a3, sp+0x10, sp+0x14, …` 순이고, 서식의 변환(`%c`/`%s`/`%d`)에
**나온 순서대로** 대응한다. eid 280 주석의 실측 `(2,1,8,3,1,0xC)` 와 일치한다.

색코드 실측(`reinsert_kr_pilot.NAME_PLATE` 주석): **1=흰색 · 2=주황 · 3=초록**.
그 밖의 값(6·8·0xC …)은 색이 아니라 **종단·제어**다(`%c` 인자가 색 전용이 아니다).

## 한계 — 알고 쓴다

- **정적 분석이라 못 읽는 자리가 있다.** 인자가 레지스터·메모리에서 오거나(`move a2,s1`),
  서식 주소를 `move a1,s0` 로 넘기거나, 분기 너머에서 값을 세우면 못 뽑는다. 그런 블록은
  `?` 로 남기고 **수를 보고한다** — 「전수」라고 말하려면 못 본 몫을 같이 말해야 한다.
- **한 블록에 콜사이트가 여럿일 수 있다**(리더별 대사). 색이 갈리면 그대로 보고한다.
- 여기서 나오는 건 **원판의 색**이다. 우리가 무엇을 칠했는지가 아니다.

  python3 tools/dump_color_args.py                # 씬별 요약 + 못 읽은 몫
  python3 tools/dump_color_args.py --census       # 부류별 색 분포 (판단용)
  python3 tools/dump_color_args.py ED1SCN6 --list # 블록별 인자열
  python3 tools/dump_color_args.py --json <path>  # 표를 파일로
"""

import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict

os.environ.setdefault("LOCK_BYPASS", "1")

import common
from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs
from reinsert_kr_pilot import OVERLAY_BASE, SCN_FILES

# ⚠ **트랙마다 주소가 다르다.** ED1 은 0x800CC740, ED2 는 다른 실행 파일이라 라이브러리가
# 딴 자리에 있다(실측 ED2SCN1: 그 주소로는 콜사이트 0건). 손으로 박으면 ED2 가 조용히 0 이
# 되므로 **각 오버레이에서 찾아낸다** — `find_sprintf`.
SPRINTF = 0x800CC740  # ED1 실측(테스트 정답지)
COLOR = {1: "흰색", 2: "주황", 3: "초록"}
# 인자열을 되짚는 창 — eid 280 실측이 9명령, 여유를 둔다. 기본블록 경계에서 먼저 멈춘다.
BACK = 24
_BRANCH = ("j", "jal", "jr", "jalr", "b", "beq", "bne", "blez", "bgtz", "bltz", "bgez")

_md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)


def scenes():
    return [(n, lba, size) for n, lba, size in SCN_FILES]


def _imm(op_str):
    """`$v0, $zero, 0xc` → 12 (즉치 로드일 때만)."""
    m = re.fullmatch(r"\$(\w+), \$zero, (-?(?:0x)?[0-9a-f]+)", op_str)
    return (m.group(1), int(m.group(2), 0)) if m else None


def disasm(data, base, start):
    """`start` 부터 끝까지 — **중간에 못 읽는 워드가 있어도 건너뛰고 잇는다.**

    ⚠ 오버레이는 `[텍스트][코드]` 라 앞머리가 데이터다. `Cs.disasm` 은 첫 무효 워드에서
    **조용히 멈춘다** — 그대로 쓰면 명령 한 개만 얻고 콜사이트 0건이 나온다(실측).
    """
    ins, off = [], start
    while off < len(data):
        got = False
        for i in _md.disasm(data[off:], base + off):
            ins.append(i)
            off = i.address - base + 4
            got = True
        if not got:
            off += 4
    return ins


def find_sprintf(ins, base, text_end):
    """이 오버레이의 메시지 조립 루틴 주소 — **서식 인자가 텍스트를 가리키는 호출**로 판정한다.

    ⚠ 이름이나 고정 주소로 못 찾는다(심볼이 없고 트랙마다 다르다). 대신 성질로 찾는다:
    `sprintf(dst, fmt, …)` 의 `fmt`(=`a1`)는 **대사 블록 영역**을 가리킨다. 그런 호출이
    가장 많은 대상이 곧 그 루틴이다. ED1 에서 이 방법이 0x800CC740(정답)을 고르는지
    회귀 테스트로 묶어 둔다.
    """
    lo, hi = base, base + text_end
    score = Counter()
    for k, i in enumerate(ins):
        if i.mnemonic != "jal":
            continue
        st = _state_from(ins, _block_start(ins, k), k)
        if st["fmt"] is not None and lo <= st["fmt"] < hi:
            score[int(i.op_str, 0)] += 1
    return score.most_common(1)[0][0] if score else None


def _block_start(ins, idx):
    j, start = idx - 1, idx
    while j >= 0 and idx - j <= BACK:
        if ins[j].mnemonic in _BRANCH:
            break
        start = j
        j -= 1
    return start


def _state(ins, idx):
    """콜사이트가 속한 **기본블록**을 훑어 인자 상태를 모은다 — (블록 시작 주소, 상태).

    상태는 `{fmt, a2, a3, stack{off: val}}`. 지연 슬롯(`idx+1`)도 포함한다 —
    `jal` 이든 `j` 든 지연 슬롯은 **점프 전에 실행**되므로 인자 설정에 쓰인다(eid 280 실측).
    """
    start = _block_start(ins, idx)
    return ins[start].address, _state_from(ins, start, idx)


def _state_from(ins, start, idx):
    """`start` 부터 `idx`(+지연 슬롯)까지의 인자 상태."""
    st = {"fmt": None, "a2": None, "a3": None, "stack": {}}
    reg = {}
    lui = {}
    seq = ins[start:idx] + (ins[idx + 1 : idx + 2] if idx + 1 < len(ins) else [])
    for x in seq:
        if x.mnemonic == "lui":
            m = re.fullmatch(r"\$(\w+), (0x[0-9a-f]+)", x.op_str)
            if m:
                lui[m.group(1)] = int(m.group(2), 0) << 16
        elif x.mnemonic in ("addiu", "ori"):
            m = re.fullmatch(r"\$(\w+), \$(\w+), (-?(?:0x)?[0-9a-f]+)", x.op_str)
            if not m:
                continue
            rd, rs, v = m.group(1), m.group(2), int(m.group(3), 0)
            if rd == rs == "a1" and "a1" in lui:
                st["fmt"] = (lui["a1"] + v) & 0xFFFFFFFF if x.mnemonic == "addiu" else lui["a1"] | v
            elif rs == "zero":
                reg[rd] = v
                if rd in ("a2", "a3"):
                    st[rd] = v
            else:
                reg.pop(rd, None)
        elif x.mnemonic == "sw":
            m = re.fullmatch(r"\$(\w+), (0x[0-9a-f]+)\(\$sp\)", x.op_str)
            if m:
                st["stack"][int(m.group(2), 0)] = reg.get(m.group(1))
        elif x.mnemonic in ("move", "lw", "lwl", "addu", "or"):
            m = re.match(r"\$(\w+)", x.op_str)
            if m:
                reg.pop(m.group(1), None)
                if m.group(1) == "a1":
                    st["fmt"] = None
                if m.group(1) in ("a2", "a3"):
                    st[m.group(1)] = None
    return st


def _merge(caller, tail):
    """꼬리가 **나중에 실행**되므로 겹치는 자리는 꼬리가 이긴다."""
    out = {
        "fmt": tail["fmt"] if tail["fmt"] is not None else caller["fmt"],
        "a2": tail["a2"] if tail["a2"] is not None else caller["a2"],
        "a3": tail["a3"] if tail["a3"] is not None else caller["a3"],
        "stack": dict(caller["stack"]),
    }
    out["stack"].update(tail["stack"])
    return out


def _args(st):
    args = [st["a2"], st["a3"]]
    off = 0x10
    while off in st["stack"]:
        args.append(st["stack"][off])
        off += 4
    return args


def callsites(data, base, code_start, sprintf=None):
    """[(fmt_addr, [인자…], 콜사이트 주소)].

    ⚠ **콜사이트가 두 토막인 꼴이 다수다**(실측 ED1SCN1: 직접 512 · 꼬리 경유 다수).
    앞 블록이 서식 주소와 스택 인자 일부를 세우고 `j` 로 **공용 꼬리**에 뛰면, 꼬리가
    `a2`·`a3` 를 채우고 `jal` 한다. 앞 블록만 보면 인자가 반쪽이라 색을 못 읽는다.
    그래서 ①꼬리를 먼저 모으고 ②그 꼬리로 뛰는 블록을 합친다.
    """
    ins = disasm(data, base, code_start)
    if sprintf is None:
        sprintf = find_sprintf(ins, base, code_start) or SPRINTF
    out, entry = [], {}
    for k, i in enumerate(ins):
        if i.mnemonic != "jal" or int(i.op_str, 0) != sprintf:
            continue
        s0 = _block_start(ins, k)
        st = _state_from(ins, s0, k)
        if st["fmt"] is not None:
            out.append((st["fmt"], _args(st), i.address))
        # ⚠ 꼬리로 **뛰어드는 자리는 블록 중간**이다 — 진입 주소마다 잡아 둔다.
        for t in range(s0, k + 1):
            entry[ins[t].address] = (t, k)
    for k, i in enumerate(ins):
        if i.mnemonic != "j":
            continue
        hit = entry.get(int(i.op_str, 0))
        if not hit:
            continue
        tail = _state_from(ins, hit[0], hit[1])
        _s, caller = _state(ins, k)
        m = _merge(caller, tail)
        if m["fmt"] is not None:
            out.append((m["fmt"], _args(m), i.address))
    return out


def conversions(raw):
    """서식의 변환을 나온 순서대로 — [('c'|'s'|'d', 바이트 위치)]."""
    return [(m.group(1).decode(), m.start()) for m in re.finditer(rb"%([csd])", raw)]


def scan(name, lba, size):
    base = OVERLAY_BASE[name[:3]]
    data = common.extract(lba, size)
    with open(os.path.join(common.OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    by_addr = {}
    for e in doc["entries"]:
        if e.get("raw_hex"):
            by_addr[base + int(e["file_offset"], 16)] = (e["entry_id"], bytes.fromhex(e["raw_hex"]))
    code_start = max(
        int(e["file_offset"], 16) + len(bytes.fromhex(e["raw_hex"]))
        for e in doc["entries"]
        if e.get("raw_hex")
    )
    code_start &= ~3
    got = defaultdict(list)
    for fmt, args, site in callsites(data, base, code_start):
        if fmt in by_addr:
            got[by_addr[fmt][0]].append((args, site))
    return by_addr, got


def block_colors(raw, args):
    """`%c` 변환에 인자를 짝지어 [(위치, 값)] — 인자가 모자라면 None."""
    out = []
    for k, (kind, pos) in enumerate(conversions(raw)):
        if kind == "c":
            out.append((pos, args[k] if k < len(args) else None))
    return out


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    want = set(argv) or None
    rows, unread, noargs = [], 0, 0
    for name, lba, size in scenes():
        if want and name not in want:
            continue
        by_addr, got = scan(name, lba, size)
        ids = {e for _a, (e, _r) in by_addr.items()}
        raws = {e: r for _a, (e, r) in by_addr.items()}
        for eid in sorted(ids):
            sites = got.get(eid, [])
            if not sites:
                unread += 1
                continue
            raw = raws[eid]
            for args, site in sites:
                cs = block_colors(raw, args)
                if any(v is None for _p, v in cs):
                    noargs += 1
                rows.append((name, eid, args, [v for _p, v in cs], site, raw))
    read = {(r[0], r[1]) for r in rows}
    ours, hit = 0, 0
    for name, _l, _s in scenes():
        f = pathlib.Path(f"games/ps1-ed1+2/script/{name}.json")
        if want and name not in want or not f.exists():
            continue
        ks = {
            int(k)
            for k, v in json.loads(f.read_text(encoding="utf-8")).items()
            if isinstance(v, dict)
        }
        ours += len(ks)
        hit += len({k for k in ks if (name, k) in read})
    # ⚠ **분모를 밝힌다** — 전 엔트리로 세면 표·제어 블록까지 들어가 「못 읽음」이 부풀고,
    #   우리 문안으로 세면 실제로 색을 알아야 하는 몫이 나온다(스킬 「완료 규칙」).
    print(
        f"콜사이트를 읽은 블록 {len(read)} (전 엔트리 중) · 우리 문안 기준 {hit}/{ours}"
        + (f" = {100 * hit // ours}%" if ours else "")
    )
    print(f"  (인자 일부가 레지스터에서 와 값이 빈 콜사이트 {noargs} — 그 자리는 `?` 로 남긴다)")
    if "--list" in flags:
        for name, eid, args, cs, site, _raw in rows:
            a = ",".join("?" if x is None else f"{x:#x}" for x in args)
            c = " ".join("?" if v is None else COLOR.get(v, f"[{v:#x}]") for v in cs)
            print(f"  {name}:{eid:<5} {site:08x}  인자({a})  %c→ {c}")
    if "--census" in flags:
        fam, used = Counter(), defaultdict(Counter)
        docs = {}
        for name, eid, _args, cs, _site, _raw in rows:
            f = pathlib.Path(f"games/ps1-ed1+2/script/{name}.json")
            if not f.exists():
                continue
            doc = docs.setdefault(name, json.loads(f.read_text(encoding="utf-8")))
            v = doc.get(str(eid))
            if not isinstance(v, dict):
                continue
            t = v.get("t") or ""
            if "\x1a" in t or "\x17" in t:
                kind = "로그(주입형)"
            elif (v.get("s") or "").strip():
                kind = "대사(화자 있음)"
            else:
                kind = "해설·나머지"
            fam[(kind, COLOR.get(next((x for x in cs if x in COLOR), 1), "?"))] += 1
            for x in cs:
                if x in COLOR:
                    used[kind][COLOR[x]] += 1
        print("\n① 블록이 **여는 색** — 부류별 (원판 인자)")
        for (k, c), n in sorted(fam.items(), key=lambda x: (x[0][0], -x[1])):
            print(f"   {n:>5}  {k} — {c}")
        print("\n② 블록 안에서 쓰인 색 전량")
        for k, cnt in used.items():
            tot = sum(cnt.values())
            print(
                f"   {k}: {tot}회 — "
                + " · ".join(f"{c} {n}({100 * n // tot}%)" for c, n in cnt.most_common())
            )
        print("\n⚠ 「해설·나머지」에는 **화자 칸이 빈 이어지는 대사 창**이 섞여 있다 —")
        print("   부류를 더 가르지 않으면 이 칸의 분포로 규칙을 말할 수 없다(다음 할 일).")
    for f in flags:
        if f.startswith("--json="):
            out = {
                f"{n}:{e}": {"args": a, "colors": c, "site": f"{st:#x}"}
                for n, e, a, c, st, _r in rows
            }
            pathlib.Path(f.split("=", 1)[1]).write_text(
                json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"  → {f.split('=', 1)[1]} ({len(out)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
