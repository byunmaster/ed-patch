"""QA 디버그 메뉴 시험(헤드리스 — RAM 에 훅을 꽂는다, 롬 불변).

python3 tools/qa_debug_probe.py <state> <출력폴더>    # state = 필드 세이브스테이트(없으면 카드로 만든다)
"""

import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness as D  # noqa: F401  (🔴 맨 먼저 — drc 를 끈다)
import headless_ps1 as H
import qa_debug as Q

BASE = 0x801B4000


def kr_code_lists(texts):
    code = "import sys,json;sys.path.insert(0,sys.argv[1]);import uitext;print(json.dumps([uitext.kr_codes(t) for t in json.loads(sys.argv[2])]))"
    r = subprocess.run(
        [sys.executable, "-I", "-c", code, HERE, json.dumps(texts, ensure_ascii=False)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(r.stdout.strip().splitlines()[-1])


def exp_action(label):
    return f"""
    lui $t1, {Q.hi(Q.EXP1):#x}
    ori $t1, $t1, {Q.lo(Q.EXP1):#x}
    lhu $t2, 0($t1)
    nop
    addiu $t2, $t2, 200
    slti $t3, $t2, 1000
    bne $t3, $zero, {label}
    nop
    addiu $t2, $zero, 999
{label}:
    sh $t2, 0($t1)
    sh $t2, 4($t1)
"""


def money_action(label):
    return f"""
    lui $t1, {Q.hi(Q.MONEY):#x}
    ori $t1, $t1, {Q.lo(Q.MONEY):#x}
    lw $t2, 0($t1)
    nop
    addiu $t2, $t2, 1000
    sw $t2, 0($t1)
"""


def main():
    st, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    cue = os.path.abspath(
        os.path.join(HERE, "..", "work", "build", "ps1-ed4", "Eiyuu Densetsu IV (KR).cue")
    )
    rows = ["경험치 추가", "돈 추가", "조우 끄기", "닫기"]
    codes = dict(zip(rows, kr_code_lists(rows), strict=True))
    blob, entry, ctl, _lab = Q.build(
        BASE, rows, [(0, exp_action("EXPOK")), (1, money_action("MNY"))], lambda t: codes[t]
    )
    print("blob", len(blob), "B ctl", hex(ctl))
    e = H.Emu(cue, card="/tmp/claude-0/ov/qa/card.mcr")
    e.run(5)
    e.load(st)
    e.run(3)
    e.poke(BASE, blob)
    e.poke(Q.PAD_SITE, struct.pack("<I", Q.site_word(entry)))
    e.run(10)
    e.shot(f"{out}/00_closed.png")
    e.press("select+l2+r2", 6, 20)
    e.run(20)
    e.shot(f"{out}/01_open.png")
    print("state", e.u32(ctl), "win", hex(e.u32(ctl + 8)))
    e.press("down", 4, 20)
    e.shot(f"{out}/02_down.png")
    e.press("up", 4, 20)
    e.press("circle", 4, 20)
    e.shot(f"{out}/03_exp.png")
    print("exp", struct.unpack("<HHHH", e.peek(Q.EXP1, 8)))
    e.press("down", 4, 20)
    e.press("circle", 4, 20)
    print("money", e.u32(Q.MONEY))
    e.press("cross", 4, 20)
    e.run(30)
    e.shot(f"{out}/04_closed.png")
    print("state after close", e.u32(ctl))


if __name__ == "__main__":
    main()
