"""전투 시스템 문구 단독 호출(시험 전용, 제품 롬 불변 — RAM 스텁) — 글 그리기 함수 입구(`0x80017334`)에 스텁을 꽂아, 다음 호출 때 한 번
**창을 열고(`0x80015B20`) 지정한 문자열 포인터를 그린다**. 전투 중(적 유닛 칸이 있는 상태)에서 문구 종류마다 한 줄 창으로 쌓아 한 장에 찍는다 —
같은 호출을 원판 이미지에도 먹여(문자열 자리는 같다) 나란히 견준다.

   sh scripts/capture.sh python3 tools/battle_msg_call.py <cue> <card.mcr> <슬롯 내림> <출력 폴더> [표시 이름]
스트링 목록은 `STRS`(RAM 주소 = 0x80010000 + EXE 오프셋 − 0x800). 창 구조체 = `0x801EF9C8 + 42 × 창 번호`.
"""

import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialog_harness  # noqa: F401,I001  (🔴 맨 먼저 — drc 를 끈다, 안 끄면 RAM 스텁이 안 걸린다)
import battle_msg_probe as B
import replay
from mipsasm import asm

FN_DRAW, FN_OPEN = 0x80017334, 0x80015B20
STUB = 0x801B2800
CTL = 0x801B2F00  # +0 플래그 · +4 x · +8 y · +12 열 · +16 행 · +20 문자열 포인터

STRS = [  # (이름, 한글 문안, 원판 RAM 주소 — 한글판은 문안 길이가 달라 시작 자리가 앞으로 밀려 있어 이미지에서 찾는다)
    ("레벨이 올랐습니다.", "레벨이 올랐습니다.", 0x8007D45C),
    ("을(를) 소환한다.", "을(를) 소환한다.", 0x8007DC8E),
    ("피스카를 얻었다.", " 피스카를 얻었다.", 0x8007DEE4),
    ("마법을 사용합니다.", "마법을 사용합니다.", 0x8007DF18),
    ("아이템을 사용합니다.", "아이템을 사용합니다.", 0x8007DF2C),
    ("전투에서 퇴각합니다.", "전투에서 퇴각합니다.", 0x8007DF44),
    ("괜찮습니까?", "괜찮습니까?", 0x8007DF06),
    ("상태 확인", "상태 확인", 0x8007DE62),
    ("자동전투 선택", "자동전투 선택", 0x8007DE72),
    ("독", "독", 0x8007DF7A),
    ("혼", "혼", 0x8007DF7E),
    ("묵", "묵", 0x8007DF82),
    ("속", "속", 0x8007DF86),
    ("잠", "잠", 0x8007DF8A),
    ("이동력", "이동력", 0x8007DED8),
    ("불덩이를 만들어 적에게 던진다.", "불덩이를 만들어 적에게 던진다.", 0x8007DB50),
]


def kr_ptrs(cue):
    """한글판 이미지의 실행파일에서 각 한글 문안의 코드열 자리를 찾는다(RAM 주소) — `ps1-ed3` 의 같은 이름 모듈이 경로에 먼저 서므로 별도 프로세스로 부른다."""
    import subprocess

    code = (
        "import sys,struct,json;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);import common,uitext;"
        "exe=common.read_file(common.EXE_PATH,image=sys.argv[3]);o=[]\n"
        "for kr in json.loads(sys.argv[4]):\n"
        " i=exe.find(b''.join(struct.pack('<H',c) for c in uitext.kr_codes(kr)));o.append(0x80010000+i-0x800 if i>=0 else None)\n"
        "print(json.dumps(o))"
    )
    r = subprocess.run(
        [sys.executable, "-I", "-c", code, HERE, os.path.join(HERE, "..", "..", ".."), cue.replace(".cue", ".bin"), json.dumps([k for _n, k, _a in STRS], ensure_ascii=False)],
        capture_output=True, text=True, check=True,
    )
    ptrs = json.loads(r.stdout.strip().splitlines()[-1])
    # 한두 글자 문안은 이미지 안 우연한 일치가 나온다 — 원판 자리(제자리에 쓴다)를 쓴다
    return [p if len(k.strip()) > 2 and p is not None else a for (_n, k, a), p in zip(STRS, ptrs, strict=True)]


def kr_code_lists(texts):
    """한글 문안 → 코드열(별도 프로세스, `kr_ptrs` 와 같은 까닭)."""
    import subprocess

    code = "import sys,json;sys.path.insert(0,sys.argv[1]);import uitext;print(json.dumps([uitext.kr_codes(t) for t in json.loads(sys.argv[2])]))"
    r = subprocess.run([sys.executable, "-I", "-c", code, HERE, json.dumps(texts, ensure_ascii=False)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


_CODE = """
    lui $t0, 0x801b
    ori $t0, $t0, 0x2f00
    lw $t1, 0($t0)
    nop
    beq $t1, $zero, SKIP
    nop
    addiu $t1, $t1, -1
    sw $t1, 0($t0)
    lw $t4, 4($t0)
    nop
    addiu $t5, $t4, 1
    sw $t5, 4($t0)
    addiu $sp, $sp, -32
    sw $a0, 0($sp)
    sw $a1, 4($sp)
    sw $a2, 8($sp)
    sw $a3, 12($sp)
    sw $ra, 16($sp)
    sll $t4, $t4, 4
    addu $t4, $t4, $t0
    lw $t6, 32($t4)
    lw $a1, 36($t4)
    lw $t7, 40($t4)
    sw $t6, 20($t0)
    sw $t7, 24($t0)
    addiu $a0, $zero, 16
    addiu $a2, $zero, 24
    addiu $a3, $zero, 1
    jal 0x80015b20
    nop
    sll $v0, $v0, 16
    sra $v0, $v0, 16
    sll $t2, $v0, 4
    sll $t3, $v0, 2
    addu $t2, $t2, $t3
    addu $t2, $t2, $v0
    sll $t2, $t2, 1
    lui $a0, 0x801f
    addiu $a0, $a0, -0x638
    addu $a0, $a0, $t2
    lui $t0, 0x801b
    ori $t0, $t0, 0x2f00
    lw $a1, 20($t0)
    move $a2, $zero
    sw $a0, 28($sp)
    jal 0x80017334
    move $a3, $zero
    lui $t0, 0x801b
    ori $t0, $t0, 0x2f00
    lw $a1, 24($t0)
    nop
    beq $a1, $zero, DONE
    nop
    lw $a0, 28($sp)
    move $a2, $zero
    jal 0x80017334
    move $a3, $zero
DONE:
    lw $a0, 0($sp)
    lw $a1, 4($sp)
    lw $a2, 8($sp)
    lw $a3, 12($sp)
    lw $ra, 16($sp)
    addiu $sp, $sp, 32
SKIP:
"""


def install(e):
    o1, o2 = struct.unpack("<2I", e.peek(FN_DRAW, 8))
    words = list(asm(_CODE, STUB)[0]) + [o1, o2, 0x08000000 | (((FN_DRAW + 8) >> 2) & 0x3FFFFFF), 0]
    e.poke(STUB, b"".join(w.to_bytes(4, "little") for w in words))
    e.poke(CTL, bytes(32))
    e.poke(FN_DRAW, (0x08000000 | ((STUB >> 2) & 0x3FFFFFF)).to_bytes(4, "little") + b"\0\0\0\0")


def arm(e, items):
    """items = [(문자열 포인터, y)] — 이후 글 그리기 호출마다 하나씩 창을 열어 그린다(CTL+0 = 남은 수 · +4 = 다음 번호 · +32.. = (포인터, y) 쌍)."""
    e.poke(CTL + 4, bytes(4))
    for i, (ptr, y, ptr2) in enumerate(items):
        e.poke(CTL + 32 + 16 * i, struct.pack("<3I", ptr, y, ptr2))
    e.poke(CTL, struct.pack("<I", len(items)))


def main():
    cue, card, slot, out = sys.argv[1:5]
    tag = sys.argv[5] if len(sys.argv) > 5 else "kr"
    os.makedirs(out, exist_ok=True)
    shutil.copy(card, out + "/card.mcr")
    e = replay.boot(cue, out + "/card.mcr", int(slot))
    seq = ["right"] * 3 + ["down"] * 3 + ["right"] * 3 + ["up"] * 3
    for i in range(13):
        e.press(seq[i % 12], 45, 4)
    for _ in range(12):
        e.press("down", 100, 4)
        e.run(120)
        if B.units(e):
            break
    install(e)
    ptrs = [a for _n, _k, a in STRS] if tag == "jp" else kr_ptrs(cue)
    print("포인터", [hex(p) if p else None for p in ptrs], flush=True)
    for a, *_ in B.units(e):  # 적을 0 으로 — 승리 처리 중 글 그리기가 여러 번 불린다
        e.poke(a + 10, struct.pack("<H", 0))
    if os.environ.get("JOSA"):  # 이름(코드열을 RAM 에 놓는다) 뒤에 「을(를) 소환한다.」 를 이어 그려 조사 훅이 받침에 맞게 바꾸는지 본다
        names = ["불꽃", "바람", "정령", "대지", "물방울", "별빛", "구름", "나무"]
        sel = kr_code_lists(names)
        for k, codes in enumerate(sel):
            e.poke(0x801B3A00 + 0x40 * k, b"".join(struct.pack("<H", c) for c in codes) + b"\xff\xff\x00\x00")
        tail = ptrs[1] if tag == "kr" else STRS[1][2]
        arm(e, [(0x801B3A00 + 0x40 * k, 8 + 26 * k, tail) for k in range(len(names))])
        for _t in range(40):
            e.press("up", 6, 10)
            e.press("circle", 6, 10)
            e.run(40)
            if struct.unpack("<I", e.peek(CTL, 4))[0] == 0:
                break
        e.run(20)
        e.shot(f"{out}/{tag}_josa.png")
        print("josa", flush=True)
        return
    for part in range(int(os.environ.get("FROM", "0")), len(STRS), 8):  # FROM=8 이면 둘째 묶음부터(창 칸이 모자라 한 번에 8줄)  # 한 번에 8줄 — 이후 글 그리기 호출(승리 처리의 창)마다 하나씩 소비된다
        items = [(ptrs[part + k], 8 + 26 * k, 0) for k in range(len(STRS[part : part + 8]))]
        arm(e, items)
        for t in range(40):
            e.press("up", 6, 10)
            e.press("circle", 6, 10)
            e.run(40)
            if t < 3:
                print("dbg", struct.unpack("<6I", e.peek(CTL, 24)), [hex(x) for x in struct.unpack("<2I", e.peek(FN_DRAW, 8))], flush=True)
            if struct.unpack("<I", e.peek(CTL, 4))[0] == 0:
                break
        print("남은", struct.unpack("<I", e.peek(CTL, 4))[0], "호출", t, flush=True)
        e.run(20)
        e.shot(f"{out}/{tag}_{part // 8}.png")
    print("끝", [hex(x) for x in struct.unpack("<2I", e.peek(FN_DRAW, 8))], hex(struct.unpack("<I", e.peek(STUB, 4))[0]), flush=True)


if __name__ == "__main__":
    main()
