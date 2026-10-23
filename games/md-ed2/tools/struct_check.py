"""구조 대조 정적 검사 — 원판 대사 블록과 구운 롬을 「제어 코드 열」(글자 바이트를 뺀 흐름·종결·인자)로 블록마다 맞댄다.

    python3 tools/struct_check.py [롬.bin] [--list] [--battle 기본] [--update-ledger]

배경(ss-ed3 10-21): 재조판 때 대사 끝에 넣은 채움 바이트가 다음 블록 호출을 막아 첫 장면의 대사가 빠졌다 — 한 블록씩 띄우는 하네스는 못 본다.
`build.verify_reassembly` 는 **의도(정본 토큰)와** 맞댄다. 이 검사는 **원판과** 맞댄다 — 의도 자체가 흐름을 바꾼 것(정본이 goto 를 빼먹음)도 잡는다.

대조 단위 = 씬 모듈 356 안의 원판 스트림(참조 그래프에서 짝지은 것, `scene.pair_streams`).
 · 제어 열 = 글자·쪽/줄 배치 코드(01 줄 · 03 ▼ · 05 쪽 · 1E…04 화자)를 뺀 모든 제어 토큰(goto·call·조건·종결·인자 바이트). 참조는 **짝지은 목표**가 같은지로 맞댄다.
 · 새 쪽이 `0F` 스텁으로 옮겨 간 꼬리는 스텁을 따라가 이어 맞댄다.
 · 허용(ALLOW)은 사유와 엔진 근거 주소가 있는 꼴만 — 아래 표.
커버리지: 대조 스트림 수 / 원판 스트림 수 · 짝 못 지은 스트림 수를 출력한다.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene
import scene_sweep

LAYOUT = {0x01, 0x03, 0x04, 0x05, 0x1E}  # 줄·▼·화자 끝·쪽·화자 시작 — 번역이 쪽 나눔·화자 경계를 정한다
GOTO = 0x0F

# 허용 목록 — 꼴 · 사유 · 엔진 근거. 새 꼴은 근거 없이 넣지 않는다.
ALLOW = {
    "josa-hook": (
        "번역 문안에 조사 훅 EB/EC(+1B 인자)를 넣었다 — 원판엔 없던 코드",
        "ED2 메시지 렌더러 $B738~ 이 EB·EC 를 제어로 읽고 핸들러가 훅 트램폴린($FF1A5E~, tools/josa.py)으로 간다. 인자 1B 는 scene.ARGS[0xEB/0xEC]=1",
    ),
    "stub-tail": (
        "새 스트림이 0F 스텁으로 옮겨 간 꼬리(번역으로 길어진 본문을 모듈 꼬리로 옮김) — 스텁을 따라가 이어 맞댄다",
        "0F=goto: ED2 스트림 VM 의 goto 핸들러($A2xx, scene.parse_stream GOTO) 가 2B 상대 변위로 점프",
    ),
    "shop-head": (
        "상점 표 머리(`[포인터 워드 ×N] 4E71 …`) — 앞 워드가 자료라 파서가 제어로 읽는다. 별도 게이트가 워드·4E71 을 본다(대조에서 뺀다)",
        "build.verify_head_tables(상점 표 머리 검사, 머리 워드 자리 4E71 과 포인터 워드가 새 자리를 가리키는지) · build.repoint_shared_heads(lea 변위)",
    ),
    "table-head": (
        "표 머리 레코드·표 워드가 든 스트림 — 앞 바이트가 자료라 파서가 제어로 읽는다(이벤트 표·선택지 표). 별도 게이트가 본다(대조에서 뺀다)",
        "scene.verify_event_tables(이벤트 표 워드 대조) · scene.parse_module 의 entries/tables(표 읽는 lea 패턴 TABLE_PAT, ED2 씬 로더 $1A41C~)",
    ),
    "head16": (
        "포인터 워드 4개(`16xx`×4) 머리 + 글 — 파서가 인자 10B 로 글 앞 두 바이트까지 삼킨다. 워드 8B 와 끝 코드만 맞댄다",
        "scene.ARGS[0x16]=10(씬 VM 의 16 핸들러가 워드 표를 읽는다) — 087-0 계열 매입 표 머리, 워드는 build.verify_head_tables 가 새 자리를 본다",
    ),
    "toggle-byte": (
        "뿌리가 `lea d(pc),aN; move.b #imm,(aN)` 로 한 바이트만 덮는 자료 칸(파서가 글줄로 읽었다) — 글이 아니라 자료. 그 한 바이트가 새 롬에도 그대로인지만 본다",
        "031-2:0xAD8 lea 0xB1F(pc),a6 · 0xADC move.b #$2C,(a6) (원판 = 새 롬 같은 바이트) · 실제 글은 0x340 의 lea → 0xB20. 같은 칸을 ctl_toggle_scan.py(게이트 5d)가 본다",
    ),
    "battle-stub": (
        "전투 문안이 길어져 본문을 옮기고 원 자리에 둔 goto 스텁(체인은 같이 옮김)을 따라가 이어 맞댄다",
        "tools/battle.py plan_block(옮김·goto 스텁) · 전투 메시지 VM 도 scene 과 같은 0F goto 핸들러",
    ),
    "battle-mid-target": (
        "전투 call·goto 가 다른 글 한복판으로 간다(`<@>` 앵커 · 연쇄) — 번지는 새 자리로 다시 쟀으므로 도착한 곳의 제어 열이 같은지로 맞댄다",
        "tools/battle.py plan_block 의 mid 재측정(한복판 call 은 스트림 시작이 아니라 새 글에서 같은 지점으로 옮긴다) — 도착점 제어 열 대조가 안전망",
    ),
    "battle-boss-code-patch": (
        "블록 82 `では/ので` 4B 덮어쓰기 루틴을 자기 수정 lea 로 바꾸고 독립 문안 둘을 블록 끝에 놓았다(0x902·0x906·0xA13 자리는 새 코드가 쓴다)",
        "battle.patch_boss_block — BOSS_ROUTINE 의 원본 바이트가 다르면 SystemExit · 새 루틴은 자기 수정으로 문구 출력 lea 변위 워드를 쓴다(원본도 같은 방식, 0xAFFE 계열 `move.w d0,(a2)`)",
    ),
    "battle-goto-folded": (
        "글 한복판으로 이어 가던 goto 의 꼬리 글을 번역이 줄 안에 접어 넣었다(`…의 2회 공격!!`) — 접은 제어 열(앞 + 꼬리의 종결)이 같은 것만",
        "tools/battle.py drop_goto — 정본이 goto 를 빼고 꼬리 글까지 한 줄로 쓴다. 종결 코드(0A)가 원본 꼬리와 같아야 통과",
    ),
    "stub-pair": (
        "원판 스트림의 짝이 새 쪽 옛 자리의 goto 스텁(3B)이라 목적지(옮긴 본문)로 풀어 맞댄다 — 옮김·스텁은 재배치 장부(relocations.tsv)에 있어야 한다",
        "0F goto 핸들러($BF58 디스패처) · scene.reassemble 의 stub_at/tail_stub — 장부 행 `스텁`·`옮김` 과 같은 출처",
    ),
    "cond-tail-stub": (
        "조건 분기(11·12·F2·F6·F8) 꼬리에 더한 goto 스텁",
        "조건 코드는 다음 3B(0F goto)를 건너뛰거나 실행한다 — scene.COND, build 의 재조립이 같은 꼴을 낸다",
    ),
}


def cols(tokens, nm_resolve=None):
    """토큰 → 제어 열. 글자·배치 코드는 뺀다. 참조는 ('ref', code, target)."""
    out = []
    for t in tokens:
        if t.kind in ("text", "eof"):
            continue
        if t.kind == "end":
            out.append(("end", t.code))
            continue
        c = t.code
        if c in LAYOUT:
            continue
        if t.ref in (scene.GOTO, scene.CALL, scene.CODE, scene.CELL):
            out.append(("ref", c, t.target))
        else:
            out.append(("ctl", c, bytes(t.raw)))
    return out


def follow_stubs(nm: bytes, n: int, nmod, want_goto_end: bool, depth=8):
    """새 스트림 n 의 제어 열 — 꼬리가 goto 스텁이고 원판엔 그 goto 가 없으면 스텁을 따라 이어 붙인다."""
    st = nmod.streams.get(n)
    if st is None:
        st = scene.parse_stream(nm, n)
    seq = cols(st.tokens)
    stubs = 0
    while depth and seq and seq[-1][0] == "ref" and seq[-1][1] == GOTO and not want_goto_end:
        tgt = seq[-1][2]
        st2 = nmod.streams.get(tgt) or scene.parse_stream(nm, tgt)
        seq = seq[:-1] + cols(st2.tokens)
        stubs += 1
        depth -= 1
    return seq, stubs


def resolve(nm: bytes, nmod, n: int, depth=8) -> int:
    """goto 하나뿐인 스텁은 목적지로 푼다."""
    while depth:
        st = nmod.streams.get(n)
        if st is None:
            try:
                st = scene.parse_stream(nm, n)
            except (ValueError, IndexError):
                return n
        toks = [t for t in st.tokens if t.kind != "eof"]
        if len(toks) == 1 and toks[0].ref == scene.GOTO:
            n = toks[0].target
            depth -= 1
            continue
        return n
    return n


def compare_module(om: bytes, nm: bytes, tag: str):
    """→ (대조 수, 원판 스트림 수, 짝 못 지은 수, 어긋남 목록, 허용 계수)"""
    omod = scene.parse_module(om)
    nmod, pair = scene.pair_streams(omod, nm)
    bad = []
    allow = Counter()
    cmp_n = 0
    unpaired = 0
    toggled = {}  # lea 바로 뒤가 `move.b #imm,(aN)` 인 뿌리 — 글이 아니라 런타임이 한 바이트를 덮는 자료 칸
    for ins, s in omod.roots.items():
        w = int.from_bytes(om[ins + 4 : ins + 6], "big")
        if (w & 0xF1FF) == 0x10BC:
            toggled[s] = ins
    protected = bytearray(len(omod.data))  # 표 워드 · 머리 표 레코드 — 표 읽는 코드가 쓰는 자료(별도 게이트가 본다)
    for a in omod.tables:
        protected[a.word : a.word + 2] = b"\x01\x01"
    for e, ln in omod.entries.items():
        protected[e : e + ln] = b"\x01" * ln
    for s, st in sorted(omod.streams.items()):
        n = pair.get(s)
        if n is None:
            unpaired += 1
            continue
        o = cols(st.tokens)
        head = b"".join(x.raw for x in st.tokens)[:14]
        if b"\x4e\x71" in head[:14] and st.tokens[0].kind != "text":
            allow["shop-head"] += 1
            continue
        if s in toggled and not any(r != toggled[s] and omod.roots[r] == s for r in omod.roots):
            if nm[n : n + 1] != om[s : s + 1]:
                bad.append((tag, s, n, 0, [("toggle-byte", om[s : s + 1].hex())], [("toggle-byte", nm[n : n + 1].hex())]))
            allow["toggle-byte"] += 1
            cmp_n += 1
            continue
        if st.tokens[0].kind == "ctl" and st.tokens[0].code == 0x16 and len(st.tokens[0].raw) >= 8:
            # 포인터 워드 4개(`16xx`×4) 머리 + 글 — 파서가 인자 10B 로 글 앞 두 바이트까지 삼킨다. 워드 8B 와 끝 코드만 맞댄다
            nst = nmod.streams.get(n) or scene.parse_stream(nm, n)
            oe = [x.code for x in st.tokens if x.kind == "end"]
            ne = [x.code for x in nst.tokens if x.kind == "end"]
            if nst.tokens[0].raw[:8] != st.tokens[0].raw[:8] or oe[-1:] != ne[-1:]:
                bad.append((tag, s, n, 0, [("head16", st.tokens[0].raw[:8].hex())], [("head16", nst.tokens[0].raw[:8].hex())]))
            allow["head16"] += 1
            cmp_n += 1
            continue
        if any(protected[x.off] for x in st.tokens if x.kind != "eof"):
            allow["table-head"] += 1
            continue
        rawt = [x for x in st.tokens if x.kind != "eof"]
        lone = len(rawt) == 1 and rawt[0].ref == scene.GOTO
        if not lone:
            n2 = resolve(nm, nmod, n)  # 짝이 새 쪽의 빈틈 메우는 goto 스텁이면 목적지로
            if n2 != n:
                allow["stub-pair"] += 1
            n = n2
        want_goto_end = bool(o) and o[-1][0] == "ref" and o[-1][1] == GOTO
        g, stubs = follow_stubs(nm, n, nmod, want_goto_end)
        if stubs:
            allow["stub-tail"] += 1
        # 참조 목표를 짝으로 맞댄다
        def norm_o(seq):
            r = []
            for e in seq:
                if e[0] == "ref":
                    t = pair.get(e[2])
                    if t is not None:
                        r.append(("ref", e[1], resolve(nm, nmod, t)))
                    else:
                        r.append(("ref", e[1], e[2]))  # 짝 없는 목표(자료·코드 칸)는 제자리여야 한다
                else:
                    r.append(e)
            return r

        def norm_g(seq):
            return [
                ("ref", e[1], resolve(nm, nmod, e[2]) if e[1] in (0x0F, 0x10) else e[2])
                if e[0] == "ref"
                else e
                for e in seq
            ]

        a = norm_o(o)
        b = norm_g(g)
        # 번역이 넣은 조사 훅(EB/EC)은 허용 — 원판 열엔 없다
        removed = [e for e in b if e[0] == "ctl" and e[1] in (0xEB, 0xEC)]
        if removed:
            b = [e for e in b if not (e[0] == "ctl" and e[1] in (0xEB, 0xEC))]
            allow["josa-hook"] += 1
        # 조건 꼬리 스텁: 새 쪽 끝에 goto 하나가 더 붙은 꼴
        if len(b) == len(a) + 1 and b[-1][0] == "ref" and b[-1][1] == GOTO and a and a[-1][0] == "ref" and a[-1][1] == GOTO:
            b = b[:-1]
            allow["cond-tail-stub"] += 1
        if a != b:
            k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            bad.append((tag, s, n, k, a[k : k + 2], b[k : k + 2]))
        cmp_n += 1
    bad += inbound_check(om, nm, omod, nmod, pair, tag)
    return cmp_n, len(omod.streams), unpaired, bad, allow


def inbound_check(om: bytes, nm: bytes, omod, nmod, pair, tag: str):
    """남이 점프·호출·lea 로 들어오는 목표 스트림이 새 롬에서 그대로인가 — 글 없는 제어 스트림(끝 코드 하나 등)은 스텁을 따라가지 않고 그 자리의 열을 그대로 맞댄다.
    메시지 A 가 넘쳐 제자리 끝에 놓은 점프 스텁이 원본 종료 바이트를 덮었는데 메시지 B 의 끝 점프가 그 바이트로 들어오는 꼴(pce-ed1 10-22)을 잡는다."""
    targets = {t.target for st in omod.streams.values() for t in st.tokens if t.ref in (scene.GOTO, scene.CALL)}
    targets |= set(omod.roots.values())
    bad = []
    for t in sorted(targets):
        ost = omod.streams.get(t)
        if ost is None or any(x.kind == "text" for x in ost.tokens):
            continue
        oc = cols(ost.tokens)
        if not oc or any(e[0] == "ref" for e in oc):
            continue
        n = pair.get(t, t)
        try:
            nst = nmod.streams.get(n) or scene.parse_stream(nm, n)
        except (ValueError, IndexError):
            bad.append((tag, t, n, 0, oc, [("unparsable",)]))
            continue
        if any(x.kind == "text" for x in nst.tokens[:1]) or cols(nst.tokens) != oc:
            bad.append((tag, t, n, 0, oc, cols(nst.tokens)[:3]))
    return bad


def _follow_b(kb: bytes, n: int, want_goto_end: bool, depth=8):
    seq, stubs = [], 0
    st = scene.parse_stream(kb, n)
    seq = cols(st.tokens)
    while depth and seq and seq[-1][0] == "ref" and seq[-1][1] == GOTO and not want_goto_end:
        st2 = scene.parse_stream(kb, seq[-1][2])
        seq = seq[:-1] + cols(st2.tokens)
        stubs += 1
        depth -= 1
    return seq, stubs


def compare_battle(orig: bytes, kr: bytes):
    """전투 블록 — 원판 스트림마다 `pair_texts.pair_block` 의 한글 자리와 제어 열을 맞댄다. → (대조, 전체, 짝 없음, 어긋남, 허용)"""
    import battle
    import pair_texts

    ob, kb = list(battle.blocks(orig)), list(battle.blocks(kr))
    cmp_n = tot = unp = 0
    bad = []
    allow = Counter()
    for n, ((_s, jb, _e), (_s2, bb, _e2)) in enumerate(zip(ob, kb, strict=True)):
        items = pair_texts.pair_block(jb, bb, n)
        omap = {it["off"]: it["kr_off"] for it in items if it["kr_off"] is not None}
        for it in items:
            tot += 1
            if it["kr_off"] is None:
                unp += 1
                continue
            try:
                st = scene.parse_stream(jb, it["off"])
            except (ValueError, IndexError):
                unp += 1
                continue
            o = cols(st.tokens)
            wg = bool(o) and o[-1][0] == "ref" and o[-1][1] == GOTO
            try:
                g, stubs = _follow_b(bb, it["kr_off"], wg)
            except (ValueError, IndexError):
                bad.append((f"전투{n:03d}", it["off"], it["kr_off"], 0, [("parse", 0)], [("parse-fail", 0)]))
                continue
            if stubs:
                allow["battle-stub"] += 1

            def res(x, seq=None):
                return x

            def kinds(blk, off, tail):
                try:
                    sq, _ = _follow_b(blk, off, False) if tail else (cols(scene.parse_stream(blk, off).tokens), 0)
                except (ValueError, IndexError):
                    return ("unparsable", off)
                return tuple((e[0], e[1]) for e in sq)

            if any(e[0] == "ctl" and e[1] in (0xEB, 0xEC) for e in g):
                g = [e for e in g if not (e[0] == "ctl" and e[1] in (0xEB, 0xEC))]
                allow["josa-hook"] += 1
            if n == battle.BOSS_BLOCK and it["off"] in (*battle.BOSS_STREAMS, 0x902, 0x906):  # 0x902·0x906 = patch_boss_block 이 0 으로 지우는 `では`/`ので` 자료 8B
                allow["battle-boss-code-patch"] += 1  # 블록 82 의 4B 덮어쓰기 루틴을 통째로 바꿨다 — patch_boss_block 이 원본 바이트를 확인한 뒤 덮는다
                cmp_n += 1
                continue
            a, b = [], []
            gi = iter(g)
            for e in o:
                x = next(gi, None)
                if e[0] == "ref" and e[2] not in omap:  # 글 한복판으로 가는 call·goto — 번지 대신 도착한 곳의 제어 열을 맞댄다
                    a.append(("ref", e[1], ("mid", kinds(jb, e[2], False))))
                    if x is not None and x[0] == "ref":
                        b.append(("ref", x[1], ("mid", kinds(bb, x[2], True))))
                        allow["battle-mid-target"] += 1
                    elif x is not None:
                        b.append(x)
                    continue
                a.append(("ref", e[1], omap[e[2]]) if e[0] == "ref" else e)
                if x is not None:
                    b.append(x)
            b += list(gi)
            if any(e[0] == "ctl" and e[1] in (0xEB, 0xEC) for e in b):
                b = [e for e in b if not (e[0] == "ctl" and e[1] in (0xEB, 0xEC))]
                allow["josa-hook"] += 1
            if a != b and o and o[-1][0] == "ref" and o[-1][1] == GOTO and o[-1][2] not in omap:
                # 뒤를 다른 글 한복판으로 잇던 goto — 번역이 그 꼬리 글을 줄 안에 접어 넣었다. 접은 열(앞 + 꼬리 제어)이 같으면 허용
                tail = [(e[0], e[1]) if e[0] != "ref" else e for e in cols(scene.parse_stream(jb, o[-1][2]).tokens)]
                folded = [e if e[0] != "ref" else ("ref", e[1], omap.get(e[2], ("mid", e[2]))) for e in o[:-1] + tail]
                if folded == b:
                    allow["battle-goto-folded"] += 1
                    a = b
            if a != b:
                k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                bad.append((f"전투{n:03d}", it["off"], it["kr_off"], k, a[k : k + 2], b[k : k + 2]))
            cmp_n += 1
    return cmp_n, tot, unp, bad, allow


def page_rows(kr: bytes):
    """쪽 넘김 행 — 원판 스트림과 짝 스트림의 05(쪽 넘김) 수가 다른 곳(번역이 쪽 나눔을 정했다). 좌표만."""
    import reloc_ledger as RL

    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    rows = []
    for blk, k, om in archives.modules(orig):
        nm = km[(blk, k)]
        omod = scene.parse_module(om)
        nmod, pair = scene.pair_streams(omod, nm)
        for s, st in sorted(omod.streams.items()):
            n = pair.get(s)
            if n is None:
                continue
            n = resolve(nm, nmod, n)
            nst = nmod.streams.get(n) or scene.parse_stream(nm, n)
            toks = list(nst.tokens)
            for _ in range(8):  # 꼬리 스텁을 따라간다
                last = [x for x in toks if x.kind != "eof"][-1:]
                if last and last[0].ref == scene.GOTO and not (st.tokens[-1].ref == scene.GOTO):
                    nxt = nmod.streams.get(last[0].target) or scene.parse_stream(nm, last[0].target)
                    toks = toks[:-1] + list(nxt.tokens)
                else:
                    break
            co = sum(1 for x in st.tokens if x.kind == "ctl" and x.code == 5)
            cn = sum(1 for x in toks if x.kind == "ctl" and x.code == 5)
            if co != cn:
                rows.append(
                    (
                        f"{blk:03d}-{k}",
                        "쪽 넘김",
                        f"{s:#06x}",
                        f"{n:#06x}",
                        f"번역이 쪽 나눔을 정했다 — 쪽 표지(05) 원판 {co} → 한글 {cn}",
                        RL.EVID_PAGE,
                        RL.UNDO_PAGE,
                    )
                )
    return rows


def ledger(kr: bytes, build_dir: Path):
    import reloc_ledger as RL

    b = build_dir / "relocations.build.tsv"
    if not b.exists():
        raise SystemExit(f"❌ 재배치 장부 원재료가 없다({b}) — 빌드가 장부를 못 썼다")
    return sorted(set(RL.read_tsv(b)) | set(page_rows(kr)))


LEDGER_PATH = common.GAME_DIR / "relocations.tsv"
LEDGER_KEYS: set[str] = set()  # 장부에 스텁·옮김·채움 행이 있는 블록 키 — 구조 대조가 본 스텁이 장부에 있어야 한다


def run(kr: bytes, show=False):
    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    tot = [0, 0, 0]
    bad_all = []
    allow = Counter()
    for blk, k, om in archives.modules(orig):
        c, t, u, bad, al = compare_module(om, km[(blk, k)], f"{blk:03d}-{k}")
        if (al["stub-pair"] or al["stub-tail"]) and f"{blk:03d}-{k}" not in LEDGER_KEYS:
            bad.append((f"{blk:03d}-{k}", 0, 0, 0, [("ledger", "스텁·옮김 행 없음")], [("stub", al["stub-pair"] + al["stub-tail"])]))
        tot[0] += c
        tot[1] += t
        tot[2] += u
        bad_all += bad
        allow.update(al)
    return tot, bad_all, allow


def selftest(orig: bytes, kr: bytes) -> bool:
    """검사기 자신의 시험 — 구운 모듈 하나의 종결 코드 한 바이트를 일부러 바꾼 사본에서 검사가 실제로 우는가."""
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    for blk, k, om in archives.modules(orig):
        nm = km[(blk, k)]
        omod = scene.parse_module(om)
        nmod, pair = scene.pair_streams(omod, nm)
        for s, st in sorted(omod.streams.items()):
            n = pair.get(s)
            nst = nmod.streams.get(n) if n is not None else None
            ends = [x for x in (nst.tokens if nst else []) if x.kind == "end" and x.code in (6, 7)]
            if not ends or s in omod.pinned or any(x.kind != "text" and x.code == 0x0F for x in st.tokens):
                continue
            bad_nm = bytearray(nm)
            bad_nm[ends[-1].off] = 0x07 if ends[-1].code == 6 else 0x06
            _c, _t, _u, bad, _a = compare_module(om, bytes(bad_nm), f"{blk:03d}-{k}")
            return len(bad) >= 1
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    kr = path.read_bytes()
    import reloc_ledger as RL

    rows = ledger(kr, path.parent)
    if "--update-ledger" in sys.argv:
        RL.write_tsv(LEDGER_PATH, rows)
        print(f"재배치 장부 갱신 — {len(rows)}행 → {LEDGER_PATH}")
    ledger_bad = False
    LEDGER_KEYS.update(r[0] for r in rows if r[1] in ("스텁", "옮김", "채움"))
    kinds = Counter(r[1] for r in rows)
    if not LEDGER_PATH.exists():
        print("❌ 재배치 장부(games/md-ed2/relocations.tsv)가 없다 — `struct_check.py --update-ledger`")
        ledger_bad = True
    else:
        have = set(RL.read_tsv(LEDGER_PATH))
        new = sorted(set(rows) - have)
        gone = sorted(have - set(rows))
        if new or gone:
            ledger_bad = True
            print(f"❌ 재배치 장부가 빌드와 다르다 — 장부에 없는 재배치 {len(new)}건 · 빌드에 없는 장부 행 {len(gone)}건")
            for r in new[:10]:
                print("   + ", r[:5])
            for r in gone[:5]:
                print("   - ", r[:5])
            print("   (의도한 재배치면 `struct_check.py --update-ledger` 로 장부를 갱신하고 사유를 확인한다)")
    print("재배치 장부 — " + " · ".join(f"{k} {n}" for k, n in sorted(kinds.items())) + f" (총 {len(rows)}행)")
    tot, bad, allow = run(kr)
    if not selftest(common.rom(), kr):
        print("❌ 검사기 자체 시험 실패 — 종결 코드를 바꾼 사본을 못 잡았다")
        sys.exit(1)
    if "--no-battle" not in sys.argv:
        bc, bt, bu, bbad, bal = compare_battle(common.rom(), kr)
        print(f"  전투 블록 대조 {bc}/{bt} (짝 없음 {bu}) · 어긋남 {len(bbad)}")
        allow.update(bal)
        bad += bbad
    print(f"구조 대조 [md-ed2] — 대조 스트림 {tot[0]}/{tot[1]} (짝 못 지음 {tot[2]}) · 어긋남 {len(bad)} · 자체 시험(종결 코드 한 바이트) 통과")
    for kind, n in sorted(allow.items()):
        why, evid = ALLOW[kind]
        print(f"  허용 {kind} {n}건 — {why}")
        if "--list" in sys.argv:
            print(f"      근거: {evid}")
    for tag, s, n, k, a, b in bad[:40 if "--list" not in sys.argv else None]:
        print(f"  ✗ {tag} 원판@{s:#x} 새@{n:#x} 제어 {k}: 원판 {a} / 새 {b}")
    sys.exit(1 if (bad or ledger_bad) else 0)


if __name__ == "__main__":
    main()
