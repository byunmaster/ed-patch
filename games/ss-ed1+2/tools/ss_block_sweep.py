#!/usr/bin/env python3
"""**씬 대사 블록 직접 그리기(ED1)** — 번호가 안 달린 대사(이벤트 코드가 직접 부르는 블록)까지 실제 그리기 길로 한 장씩 찍는다
(헤드리스 새턴 하네스 `ss_headless.py`, 롬·이미지는 안 고친다 — RAM 쓰기뿐).

    python3 tools/ss_block_sweep.py --scenes 6 --out <폴더>                 # 씬 6 의 블록 전부
    python3 tools/ss_block_sweep.py --scenes 6 --offsets 0x4b0,0x4e0 --out <폴더>
    python3 tools/ss_block_sweep.py --scenes 8 --verify 10 --out <폴더>    # 번호 길과 픽셀 대조(도구 검증)

## 왜 이렇게 하나
`ss_scene_sweep` 은 「번호 → 스크립트」 함수가 내놓는 대사만 찍는다. 이벤트 코드가 번호 없이 직접 부르는 블록(ED1 5,258 중 1,841 ·
ED2 7,330 중 4,310 이 화면 없음, 2026-11-06 항목 단위 계수)은 안 닿는다. 그런데 번호 함수의 한 가지 **단순 분기**(`mov.l 블록주소,r5 ·
bra 꼬리 · mov #6,r1`)는 블록 포인터를 리터럴 하나로 받는다 — 그 리터럴(RAM)만 임의 블록 주소로 바꾸고 그 번호를 부르면 **같은
조립·조사 훅·줄바꿈·창 그리기 길**로 블록이 찍힌다(번호 길과 같은 코드를 지난다). 롬은 안 고친다.
- 단순 분기 찾기: 모듈 함수 앞부분의 `mov.w 상한 · add #-1,r4 · cmp/hi r1,r4 · mova 표 · mov.w @(r0,r1),r1` 점프 표를 읽어,
  분기 첫 명령이 `d5xx(mov.l pc,r5) · axxx(bra) · e106(mov #6,r1)` 인 번호를 고른다.
- 블록에 런타임 인자(`%s`·`%d`)가 들면 꼬리가 인자를 안 채우므로 **표시**(`args`)를 달아 둔다(대표 값은 별도 단계).
"""

import argparse
import json
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import ss_battle_sweep as B
import ss_headless as H
import ss_scene_sweep as S


STUB_AT = 0x060F6400  # 우리 「번호→스크립트」 함수(진짜 분기 대신) — 훅 스텁(0x060F6000)과 겹치지 않는다
MBX = 0x260F7100  # 우편함(캐시 우회 미러 — 호스트가 쓴 값을 CPU 가 바로 본다): [서식 포인터, 인자 0~4]
NAME_AT = 0x060F7500  # `%s` 대표 값(이름 문자열, 게임 글자코드 + NUL)
REP_NAME = "세리오스"
REP_NUM = 100
SCR = 0x060F7400  # sprintf 임시 칸 (0x400)
SPRINTF = {"ed1": 0x06095BCC, "ed2": 0x0607B180}
STRCPY = {"ed1": 0x06095C28, "ed2": 0x0607B1DC}


def build_formatter(game):
    """`f(r4=번호, r5=출력)` — 우편함의 서식 블록을 `sprintf(임시, 서식, 인자 0~7)` 한 뒤 `strcpy(출력, 임시)`. 모든 분기의 꼬리가 하는 일과 같다
    (ED1SCN08 0x060D1346: `sprintf(local, 블록, 2, 1, 6) · strcpy(r11, local)`). 씬마다 분기 꼴이 달라도 이 둘은 본체 함수라 같다.
    우편함 = `[서식, 인자 0..7]` — 인자 0·1 은 r6·r7, 나머지 여섯은 스택(뒤부터 밀어 인자 2 가 맨 위)."""
    W = []  # (워드, 풀 이름 | None)
    W += [(0x2F86, None), (0x4F22, None), (0x6853, None), (0xD100, "MBX")]  # push r8 · pr · r8=출력 · r1=우편함
    for k in range(7, 1, -1):  # 인자 7..2 → push
        W += [(0x5210 | (k + 1), None), (0x2F26, None)]  # mov.l @(k+1,r1),r2 · mov.l r2,@-r15
    W += [(0x5510, None), (0x5611, None), (0x5712, None)]  # r5=서식 · r6=인자0 · r7=인자1
    W += [(0xD400, "SCR"), (0xD000, "SPF"), (0x400B, None), (0x0009, None), (0x7F18, None)]  # sprintf · add #24,r15
    W += [(0xD000, "CPY"), (0x6483, None), (0xD500, "SCR"), (0x400B, None), (0x0009, None)]  # strcpy(출력, 임시)
    W += [(0x4F26, None), (0x000B, None), (0x68F6, None)]  # pop pr · rts · pop r8(지연 슬롯)
    body = len(W) * 2
    if body % 4:
        W.append((0x0009, None))
        body += 2
    pool = {"MBX": MBX, "SCR": SCR, "SPF": SPRINTF[game], "CPY": STRCPY[game]}
    at = {n: body + 4 * i for i, n in enumerate(pool)}
    words = []
    for i, (w, nm) in enumerate(W):
        if nm:
            disp = (at[nm] - (((i * 2) + 4) & ~3)) // 4
            assert 0 <= disp < 256
            w = (w & 0xFF00) | disp
        words.append(w)
    out = b"".join(struct.pack(">H", w) for w in words) + b"".join(struct.pack(">I", v) for v in pool.values())
    return out, body


def fmt_args(raw):
    """블록 원 바이트 → `(sprintf 인자 5개, 대표 값이 필요한가)`. `%c` = 제어 바이트(실측 — 번호 길 스크립트):
    이름 쌍 `%c이름%c`(사이에 개행 없음) — 줄 앞 + 뒤에 개행이 오면 화자 머리 `02 … 01`, 아니면 본문 속 색 `03 … 01`;
    쌍이 아닌 `%c` 는 창 끝 `08`, 블록의 마지막 것은 끝 `06`. `%s`=대표 이름 포인터 · `%d`=100."""
    toks = []  # (시작, 종류)
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0x25 and raw[i + 1] in b"csd":
            toks.append((i, chr(raw[i + 1])))
            i += 2
        else:
            i += 2 if raw[i] >= 0x80 else 1
    vals = {}
    k = 0
    while k < len(toks):
        st, kind = toks[k]
        if kind == "c":
            # 쌍 찾기: 다음 `%c` 까지 사이에 개행이 없고 짧으면 이름 쌍
            j = k + 1
            while j < len(toks) and toks[j][1] != "c":
                j += 1
            if j < len(toks) and 0x0A not in raw[st + 2 : toks[j][0]] and toks[j][0] - st <= 26 and toks[j][0] > st + 2 and len(raw) - (toks[j][0] + 2) >= 2:
                after = raw[toks[j][0] + 2 : toks[j][0] + 3]
                head = after == b"\x0a"
                vals[k], vals[j] = (2, 1) if head else (3, 1)
                k = j + 1
                continue
        k += 1
    cs = [n for n, (_, c) in enumerate(toks) if c == "c" and n not in vals]
    for n, idx in enumerate(cs):
        vals[idx] = 6 if n == len(cs) - 1 else 8
    args = []
    rep = False
    for n, (_, c) in enumerate(toks):
        if c == "c":
            args.append(vals[n])
        else:
            args.append(NAME_AT if c == "s" else REP_NUM)
            rep = True
    return (args + [0] * 8)[:8], rep


def simple_case(d, fn):
    """모듈 함수 `fn` 의 점프 표에서 단순 분기를 찾는다 → `(번호, 리터럴 파일 오프셋)` 또는 `None`.
    머리 꼴: `mov.w|mov #상한,r1 · add #-N,r4 · cmp/hi r1,r4 · … · mova 표,r0` — 번호 = 표 색인 + N."""
    base = fn - S.SCN_BASE
    bound = tbl = None
    add = 0
    for o in range(base, base + 0x70, 2):
        w = struct.unpack(">H", d[o : o + 2])[0]
        if tbl is None and w == 0x3416:  # cmp/hi r1,r4 — 앞에서 r1 에 상한을, r4 에 −N 을 넣는다
            for q in range(o - 2, max(base, o - 12), -2):
                v = struct.unpack(">H", d[q : q + 2])[0]
                if bound is None and (v & 0xFF00) == 0xE100:
                    bound = v & 0xFF
                elif bound is None and (v & 0xFF00) == 0x9100:
                    t = q + 4 + (v & 0xFF) * 2
                    bound = struct.unpack(">H", d[t : t + 2])[0]
                if (v & 0xFF00) == 0x7400:
                    add = struct.unpack(">b", bytes([v & 0xFF]))[0]
        if tbl is None and (w & 0xFF00) == 0xC700:  # mova @(pc),r0
            tbl = ((o + 4) & ~3) + (w & 0xFF) * 4
    if bound is None or tbl is None:
        return None
    for k in range(bound + 1):
        ent = struct.unpack(">h", d[tbl + 2 * k : tbl + 2 * k + 2])[0]
        c = tbl + ent
        w0, w1, w2 = struct.unpack(">3H", d[c : c + 6])
        if (w0 & 0xFF00) == 0xD500 and (w1 & 0xF000) == 0xA000 and (w2 & 0xFF00) == 0xE100:
            lit = ((c + 4) & ~3) + (w0 & 0xFF) * 4
            return k - add, lit
    return None


def rep_bytes():
    import check_name_tables as N

    fwd = {c: sj for sj, c in N._inv_map().items()}
    return b"".join(fwd[c] for c in REP_NAME) + b"\x00"


REP_BYTES = None


def main():
    global REP_BYTES, REP_NAME, REP_NUM
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=("ed1", "ed2"), default="ed1")
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--offsets", default=None, help="블록 파일 오프셋(쉼표) — 없으면 씬의 블록 전부")
    ap.add_argument("--kind", default="block", help="덤프 항목 종류(block|string|all)")
    ap.add_argument("--verify", type=int, default=0, help="번호 길로도 찍어 픽셀 대조할 블록 수(도구 검증)")
    ap.add_argument("--stub", action="store_true", help="씬의 분기 대신 우리 서식 함수로 찍는다(단순 분기가 없는 씬용). %s 는 대표 이름 「세리오스」, %d 는 100 으로 찍는다(표시 args)")
    ap.add_argument("--rep", choices=("party", "longest"), default="party", help="%s·%d 대표 값 — party=세리오스·100, longest=정본에서 가장 긴 이름(자이언트에이프)·최대 자릿수")
    ap.add_argument("--only-args", action="store_true", help="%s·%d 가 든 블록만")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=None)
    ap.add_argument("--bkr", default=S.B.DEFAULT_BKR)
    ap.add_argument("--state", default=None)
    ap.add_argument("--num", type=int, default=None, help="%d 대표 값을 직접 정한다(자릿수별 확인용 — --rep 보다 우선)")
    a = ap.parse_args()
    if a.rep == "longest":
        REP_NAME, REP_NUM = "자이언트에이프", 9999999
    if a.num is not None:
        REP_NUM = a.num
    REP_BYTES = rep_bytes()
    S.configure(a.game)
    G = a.game.upper()
    cue = a.cue or os.path.join(common.BUILD_DIR, "The_Legend_of_Heroes_I&II.cue")
    so = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(a.out, exist_ok=True)
    h = H.Harness(so, cue, a.out, bkr=a.bkr)
    nav = a.state or os.path.join(H.CACHE, "beetle-saturn", f"{a.game}_field_{B.image_key(cue)}.state")
    if not os.path.exists(nav):
        (S.boot_to_field_ed1 if a.game == "ed1" else B.boot_to_field)(h)
        h.save(nav)
    h.load(nav)
    h.run(5)
    code, body = S.build_stub()
    S.verify_stub(code, body)
    h.poke(S.HOOK, code)
    for k in range(0, 0x20, 4):
        S.p32(h, S.MB + k, 0)
    h.poke(S.TICK, S.hook_patch())
    h.run(30)
    assert S.g32(h, S.MB + 20) > 0, "스텁이 안 불렸다"
    base = S.snapshot(h)
    mm, fl = S.scene_files(common, cue)
    ed_targets = S.ed1_dispatch_targets(common.read_extent(mm, *fl["/ED.BIN"])) if a.game == "ed1" else None
    index_path = os.path.join(a.out, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else []
    for sc in S.parse_range(a.scenes):
        d = common.read_extent(mm, *fl[f"/BIN/{G}SCN{sc:02d}.BIN"])
        dump = json.load(open(os.path.join(common.OUT_DIR, "scn_jp", f"{G}SCN{sc:02d}.json")))
        want = None if not a.offsets else {int(x, 16) for x in a.offsets.split(",")}
        ents = [e for e in dump["entries"] if (a.kind == "all" or e["kind"] == a.kind)]
        if want is not None:
            ents = [e for e in ents if int(e["file_offset"], 16) in want]
        if a.only_args:
            ents = [e for e in ents if b"%s" in bytes.fromhex(e["raw_hex"]) or b"%d" in bytes.fromhex(e["raw_hex"])]
        if a.game == "ed1":
            fns = S.ed1_text_fns(d, ed_targets)
        else:
            fn0 = S.text_fn(d)
            fns = [fn0] if fn0 else []
        picked = None
        if a.stub:
            picked = (0, STUB_AT, 1, 0)
        else:
            for mi, fn in enumerate(fns):
                sc_case = simple_case(d, fn)
                if sc_case:
                    picked = (mi, fn, *sc_case)
                    break
        if not picked:
            print(f"{G}SCN{sc:02d}: 단순 분기를 못 찾았다 — 건너뜀", flush=True)
            continue
        mi, fn, nid, lit = picked
        S.restore(h, base)
        h.run(1)
        h.poke(S.SCN_BASE, d)
        if a.stub:
            h.poke(STUB_AT, build_formatter(a.game)[0])
        if a.game == "ed1":
            h.poke(S.DISPATCH, S.hook_patch_to(fn))
        else:
            S.p32(h, S.PTR_TEXT, fn)
        h.run(2)
        snap = S.snapshot(h)
        sdir = os.path.join(a.out, f"{G}SCN{sc:02d}")
        os.makedirs(sdir, exist_ok=True)
        index = [e for e in index if e["scene"] != sc]
        print(f"{G}SCN{sc:02d}: 모듈 {mi} 번호 {nid} 리터럴 0x{lit:X} · 블록 {len(ents)}", flush=True)
        nshots = 0
        for n, e in enumerate(ents):
            off = int(e["file_offset"], 16)
            raw = bytes.fromhex(e["raw_hex"])
            # 🔴 빌드에서 블록은 **이주**했을 수 있다 — 원본 오프셋이 아니라 빌드 이미지의 포인터 값을 따라간다
            cur = S.SCN_BASE + off
            for pa in e.get("ptr_at") or []:
                v = struct.unpack(">I", d[int(pa, 16) : int(pa, 16) + 4])[0]
                if S.SCN_BASE <= v < S.SCN_BASE + len(d):
                    cur = v
                    break
            if a.stub:
                args, rep = fmt_args(raw)
                S.POKES[:] = [(0x060F7100, struct.pack(">9I", cur, *args)), (NAME_AT, REP_BYTES)]
            else:
                S.POKES[:] = [(S.SCN_BASE + lit, struct.pack(">I", cur))]
            tag = f"b{off:05x}"
            shots, why = S.play_id(h, snap, nid, sdir, tag)
            ent = {"scene": sc, "offset": hex(off), "kind": e["kind"], "id_via": nid, "addr": hex(cur - S.SCN_BASE), "shots": [f"{G}SCN{sc:02d}/{s}" for s in shots], "status": why}
            if b"%s" in raw or b"%d" in raw:
                ent["args"] = True
            nshots += len(shots)
            index.append(ent)
            if n % 20 == 0:
                print(f"  {n}/{len(ents)} {tag} 창 {len(shots)} {why}", flush=True)
        S.POKES[:] = []
        print(f"{G}SCN{sc:02d}: 블록 {len(ents)} · 캡처 {nshots}장", flush=True)
        index.sort(key=lambda x: (x["scene"], int(x["offset"], 16)))
        with open(index_path, "w") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
