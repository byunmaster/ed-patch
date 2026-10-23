"""전 씬 대사 캡처 하네스 — 맵마다 이동하고 그 맵 스크립트의 대사 시퀀스를 하나씩 주입해 **게임이 그리는 대사창**을 한 장씩 모은다.

  sh scripts/heavy.sh .venv/bin/python games/ps1-ed3/tools/dialog_harness.py --maps FT0000,FT1000 --out <폴더> [--cue <cue>] [--max-seq N]

원리(`status.md` 「디버그 빌드」 (나)): 엔진이 읽는 주 스크립트 포인터 `0x800DD6F8` 을 우리 버퍼로 바꾸면 엔진이 제 문맥에서 돌려 준다.
맵 이동 = `14 <방향> 06 <이름 6자>`(다른 챕터면 먼저 `14 02 FF <챕터>` 로 그 챕터 시작 맵), 대사 = 맵 스크립트 블록(`*0x800DD730`)에서 찾은
`[12 n] 0F 90 <u16> (01 90 <u16>)* 00`. 쓰고 **2프레임 뒤 원래 포인터로 복구**한다(안 하면 매 프레임 다시 돌아 줄이 겹쳐 쌓인다).
산출: `<out>/<맵>/NNN.png`(창 띠만 잘라 낸 그림) + `index.tsv`(맵·번호·시퀀스 바이트) + 맵별 접촉 시트. 원본·세이브는 안 건드린다(새 게임 시작).
"""

import argparse
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

import debugpatch
import headless_ps1 as H
import warp_table

PTR = 0x800DD6F8
BASE = 0x800DD730
BUF = 0x801F4000  # 빈 RAM(코드 영역에 쓰면 코어가 죽는다)
SEQ = re.compile(rb"\x0f\x90(..)((?:\x01\x90..)*)\x00", re.S)
DEFAULT_CUE = "work/build/ps1-ed3/Eiyuu Densetsu III (KR) (TEST).cue"


def boot(emu, state_path=None):
    """새 게임 → FT0000 필드. 상태 파일이 있으면 그걸 쓴다."""
    if state_path and os.path.exists(state_path):
        emu.run(5)
        emu.load(state_path)
        emu.run(30)
        return
    emu.run(3200)
    emu.press("start", 10, 2000)
    emu.press("start", 10, 1500)
    emu.press("circle", 10, 400)
    emu.press("circle", 10, 400)
    emu.run(300)
    settle(emu, 160)  # 새 게임 첫 이벤트(오르골)가 길다 — 60번으로는 모자랐다(실측)
    if state_path:
        emu.save(state_path)


def settle(emu, presses=60):
    """진행 중인 입장 이벤트의 대사를 ○ 로 넘겨 조용한 상태로 만든다. ⚠ 화면이 멈췄다고 일찍 끝내지 않는다 — 입력 대기 창도 멈춰 보인다(실측)."""
    for _ in range(presses):
        emu.press("circle", 6, 25)
    for _ in range(4):  # 조용한 필드에서 ○ 는 명령 메뉴를 연다 — ✕ 로 닫는다
        emu.press("cross", 6, 25)


def inject(emu, script):
    """스크립트를 한 번만 돌린다: 포인터 꽂기 → 2프레임 → 복구."""
    old = emu.u32(PTR)
    emu.poke(BUF, script + b"\x00\x00")
    emu.poke(PTR, BUF.to_bytes(4, "little"))
    emu.run(2)
    emu.poke(PTR, old.to_bytes(4, "little"))


def jump(emu, name, chapter, cur_chapter):
    """맵 이동. 챕터가 다르면 그 챕터 시작 맵을 먼저 거친다. 반환 = 새 현재 챕터."""
    if chapter != cur_chapter:
        inject_jump(emu, bytes([0x14, 0x02, 0xFF, chapter]) + bytes(4))
        wait_map(emu)
    inject_jump(emu, bytes([0x14, 0x02, 0x06]) + name.encode("ascii") + bytes(4))
    wait_map(emu)
    return chapter


def inject_jump(emu, script):
    emu.poke(BUF, script + b"\x00\x00")
    emu.poke(PTR, BUF.to_bytes(4, "little"))
    emu.run(2)


def wait_map(emu, limit=1500):
    """주 포인터·스크립트 블록이 바뀌고 화면이 안정될 때까지."""
    before = emu.u32(BASE)
    for _ in range(limit // 10):
        emu.run(10)
        if emu.u32(BASE) != before and emu.u32(PTR) != BUF:
            break
    emu.run(120)
    settle(emu, 60)


def sequences(emu, size=0x4000):
    blk = emu.peek(emu.u32(BASE), size)
    out = []
    for m in SEQ.finditer(blk):
        a = m.start()
        pre = blk[a - 2 : a] if a >= 2 and blk[a - 2] == 0x12 else b""
        out.append((a, pre + m.group(0)))
    return out


def stable(emu, cap=900):
    """글자가 다 찍혀 화면이 멎을 때까지(30프레임 연속 같음 — 글자가 한 자씩 찍히는 틈을 넘긴다)."""
    same, last = 0, None
    for _ in range(cap):
        emu.run(1)
        cur = emu.frame.tobytes()
        same = same + 1 if cur == last else 0
        last = cur
        if same >= 30:
            return True
    return False


def band(base, frame, pad=2):
    """기준 화면과 달라진 행 중 **가장 긴 연속 띠** — 대사창 자리(배경 애니메이션 잡음은 짧아서 걸러진다). 없으면 None."""
    diff = (np.abs(base.astype(int) - frame.astype(int)).sum(axis=2) > 60).sum(axis=1) >= 20
    best, cur = (0, 0), None
    for y, on in enumerate(list(diff) + [False]):
        if on and cur is None:
            cur = y
        elif not on and cur is not None:
            if y - cur > best[1] - best[0]:
                best = (cur, y)
            cur = None
    if best[1] - best[0] < 8:
        return None
    return max(0, best[0] - pad), min(frame.shape[0], best[1] + pad)


def sheet(paths, out, cols=3, h=96):
    ims = [Image.open(p) for p in paths]
    w = ims[0].width
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (w * cols, h * rows))
    for i, im in enumerate(ims):
        s.paste(im.crop((0, 0, w, h)), ((i % cols) * w, (i // cols) * h))
    s.save(out)


CHAPTER_ENDS = ("MT70V0", "MR43V0", "AT09V0", "CT22V0", "OT12V0", "ST12V0", "GT42V0")  # 서장~제6장 끝(`status.md` 맵 표 ③)


def chapter_ends(a):
    """장 끝 연출 보기 — 그 맵으로 이동하면 엔진이 항해 연출(암전 → 두루마리 → 띠·지명 → 액자 창)을 자동으로 돌린다."""
    table = {n: ch for n, ch, _p, _a in warp_table.table("ed3")}
    os.makedirs(a.out, exist_ok=True)
    emu = H.Emu(a.cue)  # ⚠ 한 프로세스에서 코어를 두 번 띄우면 죽는다 — 하나로 돌리고 상태를 다시 불러온다
    state = a.state or os.path.join(a.out, "_boot.state")
    boot(emu, state)
    for name in CHAPTER_ENDS:
        emu.load(state)
        emu.run(30)
        if table[name][0]:
            inject_jump(emu, bytes([0x14, 0x02, 0xFF, table[name][0]]) + bytes(4))
            wait_map(emu)
        inject_jump(emu, bytes([0x14, 0x02, 0x06]) + name.encode("ascii") + bytes(4))
        paths = []
        for k in range(8):
            emu.run(150)
            p = os.path.join(a.out, f"{name}_{k}.png")
            emu.shot(p)
            paths.append(p)
        sheet(paths, os.path.join(a.out, f"{name}_sheet.png"), cols=4, h=240)
        print(name, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", help="맵 이름 쉼표 목록 (맵 표 443항목)")
    ap.add_argument("--chapter", type=int, help="그 챕터 폴더의 맵 전부(맵 표 순서)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cue", default=DEFAULT_CUE)
    ap.add_argument("--max-seq", type=int, default=0)
    ap.add_argument("--chapter-ends", action="store_true", help="장 끝 항해 연출 7편(`*V0` 맵)을 150프레임 간격 8장씩 캡처한다")
    ap.add_argument("--state", help="새 게임 시작 상태 파일(없으면 만든다)")
    a = ap.parse_args()
    table = {n: ch for n, ch, _p, _a in warp_table.table("ed3")}
    if a.chapter_ends:
        return chapter_ends(a)
    maps = a.maps.split(",") if a.maps else [n for n, ch, _p, _a in warp_table.table("ed3") if ch and ch[0] == a.chapter]
    assert maps, "--maps 또는 --chapter 가 필요하다"
    emu = H.Emu(a.cue)
    boot(emu, a.state)
    cur = 0
    os.makedirs(a.out, exist_ok=True)
    idx_path = os.path.join(a.out, "index.tsv")
    if not os.path.exists(idx_path):
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write("맵\t번호\t오프셋\t시퀀스\t비고1\t비고2\n")
    for name in maps:
        d = os.path.join(a.out, name)
        if os.path.exists(os.path.join(d, "done")):
            continue  # 이어 하기 — 코어가 죽어도 맵 단위로 이어 간다
        ch = table[name][0]
        cur = jump(emu, name, ch, cur)
        os.makedirs(d, exist_ok=True)
        index = []
        snap = os.path.join(d, "_start.state")
        emu.save(snap)
        seqs = sequences(emu)
        if a.max_seq:
            seqs = seqs[: a.max_seq]
        paths = []
        for k, (off, s) in enumerate(seqs):
            emu.load(snap)
            emu.run(2)
            base = emu.frame.copy()
            inject(emu, s)
            ok = stable(emu)
            b = band(base, emu.frame)
            p = os.path.join(d, f"{k:03d}.png")
            img = emu.frame if b is None else emu.frame[b[0] : b[1]]
            Image.fromarray(np.ascontiguousarray(img)).save(p)
            paths.append(p)
            index.append((name, k, off, s.hex(), "" if ok else "미정지", "" if b else "창없음"))
        if paths:
            sheet(paths[:12], os.path.join(d, "sheet.png"))
        os.remove(snap)
        with open(idx_path, "a", encoding="utf-8") as f:
            for r in index:
                f.write("\t".join(map(str, r)) + "\n")
        open(os.path.join(d, "done"), "w").close()
        print(name, ch, len(seqs), flush=True)


if __name__ == "__main__":
    main()
