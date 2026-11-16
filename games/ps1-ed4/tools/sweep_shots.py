"""전 대사 대사창 전수 촬영 + 화면 자동 걸러내기 — 대사 주입 하네스(`dialog_harness`)로 모든 메시지 스트림을 게임이 그리게 해 **쪽마다 한 장** 찍고,
찍은 화면(픽셀)에서 이상을 가른다. 문안 바이트만 보고 「이상 없음」으로 치지 않는다(마스터 10-30).

    python3 tools/sweep_shots.py worklist <work.json>                        # 대상 목록(에뮬 없이) — 같은 화면 문안은 하나로 묶는다
    sh scripts/capture.sh nice -n 10 python3 tools/sweep_shots.py shoot <cue> <카드.mcr> <work.json> <출력 폴더> [샤드 i/n]

산출(`<출력>/`): `crops/<멤버>_s<스트림>_<쪽>.png`(창 둘레 잘라낸 그림) · `full/…`(이상 난 쪽만 전체 화면) · `index.jsonl`(스트림마다 한 줄 — 끊겼다 다시 돌려도 이어 한다).
화면에서 보는 것(창 글자 영역 = 줄 띠 셋 · 왼쪽 16px · 한 줄 24칸 288px):
  빈 쪽 · 빈 줄(위 줄이 빈데 아래 줄에 글) · 넘침(오른쪽 304px·왼쪽 16px 밖, 마지막 줄 아래) · 줄 수 불일치 · 줄 폭 불일치(기대 폭보다 넓다/끝 글자 소실) ·
  글자 칸 빔(기대 글자 칸에 잉크 0 — 빈·깨진 글리프) · 쪽 수 불일치 · 쪽 늘어남(기대 쪽 뒤에 스트림 밖 화면이 아닌 다른 쪽이 더 나온다).
이름·수가 끼는 쪽(`rigid`)은 끼움 폭을 모르니 줄 폭·글자 칸 검사를 건너뛴다(나머지 검사는 한다).
"""

import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

BANDS = (185, 198, 211)  # 줄 띠 시작 y(높이 11)
BAND_H = 13  # 글자 몸통 11행 + 쉼표·마침표·말줄임표가 닿는 바닥 2행
X0, XMAX = 16, 304


def worklist(out_path):
    import build
    import reinsert
    import script_kr
    import typeset

    members = build.identity_gate({})
    rows_all = script_kr.load_all()
    work, seen = [], {}
    for key, rows in rows_all.items():
        mem = members[key]
        texts, _ = script_kr.page_plan(mem, rows)
        segs = reinsert.member_segments(mem)
        for si, msg in enumerate(typeset.windows(mem)):
            scr, flags, jp_total = [], [], 0
            for pg in msg:
                lines = []
                for i in pg:
                    t = texts.get(i, "")
                    for k in range(0, len(t), typeset.COLS):
                        ln = t[k : k + typeset.COLS].rstrip(" ")
                        if ln:
                            lines.append(ln)
                jp_rows = sum(typeset.rows_of(len(segs[i])) for i in pg)
                jp_total += -(-jp_rows // 3) if jp_rows else 0
                rig = bool(getattr(pg, "rigid", False))
                n = max(1, -(-len(lines) // 3)) if lines else 0
                for s in range(n):
                    scr.append(lines[s * 3 : s * 3 + 3])
                    flags.append(rig)
            if not scr:
                continue
            sig = json.dumps(scr, ensure_ascii=False) + json.dumps(flags) + str(jp_total)
            if sig in seen:
                seen[sig]["dups"].append([key[0], key[1], si])
                continue
            w = {"archive": key[0], "member": key[1], "si": si, "screens": scr, "flags": flags, "jp_total": jp_total, "dups": []}
            seen[sig] = w
            work.append(w)
    json.dump(work, open(out_path, "w"), ensure_ascii=False)
    print(f"고유 스트림 {len(work)} · 고유 화면 {sum(len(w['screens']) for w in work)}")


def ink_mask(frame):
    """글자 잉크 — 대사 글자 색(흰색 · 이름·색 연산 주황) 픽셀. 창 테두리(238,170,98)·배경은 안 센다."""
    import numpy as np

    a = frame.astype(np.int16)
    white = (a[..., 0] == 238) & (a[..., 1] == 234) & (a[..., 2] == 238)
    orange = (a[..., 0] == 255) & (a[..., 1] == 129) & (a[..., 2] == 0)
    return white | orange


def settle_mask(frame):
    """기다림 판정용 — 글자 잉크에 더해 **막 나타나는 어두운 회색 글자**(타자 페이드 중인 끝 글자)까지 본다. 창 배경은 갈색(r>g>b)이라 회색만 따로 골라진다."""
    import numpy as np

    a = frame.astype(np.int16)
    gray = (np.abs(a[..., 0] - a[..., 1]) < 20) & (np.abs(a[..., 1] - a[..., 2]) < 20) & (a[..., 0] >= 90)
    return ink_mask(frame) | gray


def analyze(frame, expect, rigid):
    """한 쪽 화면 → [이상 문자열…]. `expect` = 그 쪽에 있어야 할 줄 목록(없으면 None)."""
    import typeset

    m = ink_mask(frame)
    bad = []
    band = [m[y : y + BAND_H, 8:312] for y in BANDS]
    has = [bool(b.any()) for b in band]
    if not any(has):
        return ["빈 쪽"]
    if (not has[0] and (has[1] or has[2])) or (not has[1] and has[2]):
        bad.append("빈 줄")
    # 넘침 — 줄 띠 밖(글자 영역 오른쪽·왼쪽 바깥, 마지막 줄 아래)에 글 잉크
    if m[183:224, XMAX + 1 : 312].any() or m[183:224, 8:X0 - 1].any():
        bad.append("넘침(좌우)")
    if m[224:231, X0:XMAX].any():
        bad.append("넘침(아래)")
    if expect is not None:
        n = sum(has)
        if n != len(expect):
            bad.append(f"줄 수 불일치(기대 {len(expect)} · 화면 {n})")
        elif not rigid:
            for ln, y in zip(expect, BANDS, strict=False):
                row = m[y : y + BAND_H, X0:]
                cols = row.any(axis=0)
                xs = cols.nonzero()[0]
                exp_w = typeset.px_width(ln)
                if len(xs) and xs[-1] + 1 > exp_w + 2:
                    bad.append(f"줄 폭 넘음(기대 {exp_w}px · 화면 {xs[-1] + 1}px): {ln[-8:]!r}")
                elif len(xs) and xs[-1] + 1 < exp_w - 13:
                    bad.append(f"끝 글자 소실(기대 {exp_w}px · 화면 {xs[-1] + 1}px): {ln[-8:]!r}")
                # 글자 칸 빔
                x = 0
                for ch in ln:
                    w = typeset.WIDTHS.get(ch, typeset.CELL_PX)
                    if ch != " " and not row[:, x : x + w].any():
                        bad.append(f"글자 칸 빔 {ch!r}")
                        break
                    x += w
    return bad


def play(e, D, state_path, member, st, max_pages, out_prefix):
    """`dialog_harness.play_stream` 와 같은 길 — 다만 **글이 다 찍힐 때까지** 기다린다(고정 대기는 타자 중 화면을 찍어 가짜 잘림을 만든다):
    ○ 뒤 30프레임 + 20프레임씩 글 잉크가 안 변할 때까지(최대 ~900프레임, ▼ 구슬이 뜨고 글이 안 변할 때). 반환 = (찍은 파일들, 못 기다린 쪽 번호들)."""
    import struct

    import numpy as np
    from PIL import Image  # noqa: F401

    e.load(state_path)
    e.run(1)
    base = struct.unpack_from("<H", member, 0)[0]
    e.poke(D.BUF, member + b"\x00\x00")
    e.poke(D.TABLE, (D.BUF + base).to_bytes(4, "little"))
    e.poke(D.STACK_PTR, (D.BUF + D.stream_start(member, st)).to_bytes(4, "little"))
    shots, unsettled = [], []
    e.press("circle", 6, 6)
    for k in range(max_pages):
        e.run(30)
        prev, settled = None, False
        for _ in range(45):
            e.run(20)
            fr = np.asarray(e.frame)
            cur = settle_mask(fr)[183:224, 8:312]
            blue = (fr[205:225, 285:310, 2] > 180) & (fr[205:225, 285:310, 0] < 140)
            # 쪽이 다 그려져 ○ 를 기다리면 ▼(파란 구슬)이 뜬다 — 구슬이 있고 글이 안 변할 때만 끝난 쪽이다(줄 사이 쉼 연산에서 일찍 찍지 않는다)
            if prev is not None and (cur == prev).all() and cur.any() and blue.sum() > 0:
                settled = True
                break
            prev = cur
        if not D.window_open(e):
            break
        p = f"{out_prefix}_{k:02d}.png"
        e.shot(p)
        if shots and open(shots[-1], "rb").read() == open(p, "rb").read():
            os.remove(p)
            break
        if not settled:
            unsettled.append(k)
        shots.append(p)
        e.press("circle", 6, 6)
    return shots, unsettled


def shoot(cue, card, wfile, out, shard="0/1"):
    import numpy as np
    from PIL import Image

    import dialog_harness as D

    si_, sn = (int(v) for v in shard.split("/"))
    binp = cue.replace(".cue", ".bin")
    work = json.load(open(wfile))
    os.makedirs(os.path.join(out, "crops"), exist_ok=True)
    os.makedirs(os.path.join(out, "full"), exist_ok=True)
    idxp = os.path.join(out, f"index{si_}.jsonl")
    done = set()
    if os.path.exists(idxp):
        for ln in open(idxp):
            r = json.loads(ln)
            done.add((r["member"], r["si"]))
    state = "/tmp/claude-0/fx/dhstate_sweep" + str(si_) + ".st"
    e = D.make_state(cue, card, state)
    todo = [w for k, w in enumerate(work) if k % sn == si_ and (w["member"], w["si"]) not in done]
    print(f"샤드 {shard}: {len(todo)}개 남음", flush=True)
    f = open(idxp, "a")
    t0 = time.time()
    for n, w in enumerate(todo):
        name = w["member"].split("\\")[-1].replace(".BIN", "") + f"_s{w['si']:03d}"
        rec = {"archive": w["archive"], "member": w["member"], "si": w["si"], "nexp": len(w["screens"]), "anom": [], "files": []}
        try:
            mem = D.read_member(binp, w["archive"], w["member"])
            st = D.streams(mem)[w["si"]]
            tmp = os.path.join(out, "full", name)
            shots, unsettled = play(e, D, state, mem, st, len(w["screens"]) + 1, tmp)
            for k in [u for u in unsettled if u < len(w["screens"])]:
                rec["anom"].append(f"[{k}] 글이 안 멈춤(화면이 계속 바뀐다 — 애니메이션·연출 쪽이거나 하네스 한계)")
            rec["nshots"] = len(shots)
            if len(w["screens"]) > w["jp_total"] > 0:
                rec["anom"].append(f"원판보다 쪽 늘어남(원판 {w['jp_total']} · 우리 {len(w['screens'])})")
            if len(shots) < len(w["screens"]):
                rec["anom"].append(f"쪽 수 불일치(기대 {len(w['screens'])} · 화면 {len(shots)})")
            for k, p in enumerate(shots):
                if k >= len(w["screens"]):  # 스트림이 끝난 뒤 스크립트가 이어 그리는 화면(스트림 밖) — 분석하지 않는다
                    os.remove(p)
                    continue
                fr = np.asarray(Image.open(p).convert("RGB"))
                rigid = bool(w["flags"][k]) if k < len(w["flags"]) else False
                exp = w["screens"][k] if len(shots) == len(w["screens"]) and k < len(w["screens"]) and not os.environ.get("SWEEP_JP") else None  # 쪽 수가 어긋난 스트림은 쪽 짝이 밀려 기대 대조가 거짓이 된다 — 일반 검사만
                bad = analyze(fr, exp, rigid)
                cp = os.path.join(out, "crops", f"{name}_{k:02d}.png")
                Image.fromarray(fr[148:232]).save(cp)
                rec["files"].append(os.path.basename(cp))
                if bad:
                    rec["anom"] += [f"[{k}] {b}" for b in bad]
                else:
                    os.remove(p)
        except Exception as ex:  # noqa: BLE001
            rec["anom"].append(f"촬영 실패: {ex!r}")
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        if n % 20 == 0:
            print(f"{n}/{len(todo)} {name} {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "worklist":
        worklist(sys.argv[2])
    else:
        shoot(*sys.argv[2:])
