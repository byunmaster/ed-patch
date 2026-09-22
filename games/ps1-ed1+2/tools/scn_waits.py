#!/usr/bin/env python3
"""**키 입력 뒤 같은 줄에 이어 쓰는 블록**을 SCN 코드에서 뽑는다.

**왜.** 대사 한 창은 코드가 블록 여럿을 `sprintf` 로 찍어 `strcat` 으로 이어 붙여 만든다.
블록 끝 `%c` 는 창 구분자가 아니라 **인자를 받는 제어 escape** 이고, 그 인자를 코드가
준다. ED2 실측(2026-09-24, ED2SCN8 jp188·189·191·192·193 디스어셈블):

- `8` — 키 입력 뒤 창을 지운다(다음 블록은 새 창)
- `9` — 키 입력 뒤 **커서 자리에서 이어 쓴다**(창도 줄도 그대로)
- `0x0C` — 대화 끝

원작은 `9` 뒤를 새 줄에서 열고 싶을 때 블록 끝에 `{n}` 을 직접 넣어 뒀다(84곳 중 70곳).
나머지 14곳은 `{n}` 없이 **같은 줄에서** 잇는다(그중 1곳은 뒷 블록이 `{n}` 으로 열어 빠진다 → 13곳) — 일본어는 띄어쓰기가 없고 짧아서 괜찮지만
한국어는 ① 두 블록이 공백 없이 붙고(`그렇습니까…그럼`) ② 조판이 블록마다 따로 돌아 앞 줄
길이를 모르니 이은 줄이 창 폭을 넘어 엔진이 멋대로 꺾는다 — 꺾인 자리에 공백이 남으면
**첫칸공백**, 29열을 딱 채우면 우리 개행과 겹쳐 **빈 줄**(마스터 QA 2026-09-24, 셋 다 발각).

⇒ 재삽입기가 이 블록들 끝(`%c` 바로 앞)에 **개행**을 넣는다(마스터 선택: 공백보다 개행).
뒷 블록은 늘 새 줄 0열에서 시작하므로 앞 줄 길이와 무관하게 조판이 맞는다.

⚠ **`%c` 경계는 전부 창 종료라는 옛 가정**(`check_block_join` 의 `raw.endswith("%c")`
건너뛰기)이 이 부류를 통째로 가렸다 — 게이트가 「블록 경계 이상 없음」을 찍는 동안 화면에선
붙고 있었다.

⚠ 인자를 정적으로 못 푸는 호출(런타임 레지스터 값)이 ED2 에 160여 곳 남는다. 그중 `9` 가
섞여 있다면 여기서 못 잡는다 — 지금까지 드러난 이어 쓰기는 전부 상수 `9` 였다.
⚠ ED1 은 대사 블록이 이 호출 꼴(`%c` 종단 + sprintf 인자)을 안 쓴다 — 빈 집합을 낸다.

  python3 tools/scn_waits.py            # 전 씬 목록
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
from patch_sys_ui import SCN_FILES

OVERLAY_BASE = {"ED1": 0x8016A000, "ED2": 0x80165000}  # reinsert_kr_pilot.OVERLAY_BASE 와 같다
SPRINTF = {"ED2": 0x800A8134}  # ED2.EXE sprintf — 씬 대사 조립 호출 390/390
CONTINUE_SAME_LINE = 9
_SPEC = re.compile(rb"%[csd]")
_TMP = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 31)


def _blocks(scn):
    with open(os.path.join(common.OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
        doc = json.load(f)
    return {int(str(e["file_offset"]), 0): e for e in doc["entries"]}


def _calls(scn, base, blocks, data):
    """[(대상, fmt 블록 오프셋, 인자들)] — 상수 레지스터·스택 추적만 하는 얕은 해석."""
    words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
    regs, stack, out = {}, {}, []

    def step(w):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0x0F:  # lui
            regs[rt] = imm << 16
        elif op == 0x09:  # addiu
            if rs == 0:
                regs[rt] = simm
            elif rs in regs:
                regs[rt] = (regs[rs] + simm) & 0xFFFFFFFF
            else:
                regs.pop(rt, None)
        elif op == 0x0D:  # ori
            if rs == 0:
                regs[rt] = imm
            elif rs in regs:
                regs[rt] = regs[rs] | imm
            else:
                regs.pop(rt, None)
        elif op == 0x2B and rs == 29:  # sw → 스택 인자
            stack[simm] = regs.get(rt)
        elif op == 0 and (w & 0x3F) == 0x21:  # addu = move
            rd = (w >> 11) & 31
            src = rs if rt == 0 else rt if rs == 0 else None
            if src is not None and src in regs:
                regs[rd] = regs[src]
            else:
                regs.pop(rd, None)
        elif op in (0x20, 0x21, 0x23, 0x24, 0x25):  # 로드 — 값을 모른다
            regs.pop(rt, None)

    def record(tgt):
        a1 = regs.get(5)
        if a1 is not None and (a1 - base) in blocks:
            out.append(
                (
                    tgt,
                    a1 - base,
                    [regs.get(6), regs.get(7)] + [stack.get(o) for o in (0x10, 0x14, 0x18)],
                )
            )

    i = 0
    while i < len(words):
        w = words[i]
        op = w >> 26
        if op == 3:  # jal — 지연 슬롯을 먼저 먹인다
            if i + 1 < len(words):
                step(words[i + 1])
            record(((w & 0x3FFFFFF) << 2) | 0x80000000)
            for r in _TMP:
                regs.pop(r, None)
            i += 2
            continue
        if op == 2 or (op == 0 and (w & 0x3F) in (8, 9)):  # j · jr · jalr
            if i + 1 < len(words):
                step(words[i + 1])
            a1 = regs.get(5)
            if op == 2 and a1 is not None and (a1 - base) in blocks:
                # 꼬리 호출 — 인자만 채우고 공용 sprintf 자리로 뛴다. 첫 jal 까지 따라간다.
                saved = (dict(regs), dict(stack))
                k = ((((w & 0x3FFFFFF) << 2) | 0x80000000) - base) // 4
                for _ in range(12):
                    if not 0 <= k < len(words):
                        break
                    ww = words[k]
                    if ww >> 26 == 3:
                        if k + 1 < len(words):
                            step(words[k + 1])
                        record(((ww & 0x3FFFFFF) << 2) | 0x80000000)
                        break
                    if ww >> 26 == 2 or (ww >> 26 == 0 and (ww & 0x3F) in (8, 9)):
                        break
                    step(ww)
                    k += 1
                regs, stack = saved
            if op == 0 and (w & 0x3F) == 8:  # jr — 함수 끝
                regs, stack = {}, {}
            else:
                regs = {r: v for r, v in regs.items() if 16 <= r <= 23}
            i += 2
            continue
        step(w)
        i += 1
    return out


def same_line_waits(scn):
    """{jp_eid} — 끝 `%c` 인자가 `9` 인데 원문이 개행 없이 끝나는 블록(뒤가 같은 줄에 붙는다)."""
    game = "ED2" if scn.startswith("ED2") else "ED1"
    if game not in SPRINTF:
        return set()
    lba, size = next((lba, size) for name, lba, size in SCN_FILES if name == scn)
    data = bytes(common.extract(lba, size))  # 원본 — 코드는 우리가 안 건드린다
    blocks = _blocks(scn)
    by_id = {e["entry_id"]: e for e in blocks.values()}
    hits = set()
    for tgt, off, args in _calls(scn, OVERLAY_BASE[game], blocks, data):
        if tgt != SPRINTF[game]:
            continue
        e = blocks[off]
        raw = bytes.fromhex(e["raw_hex"]).rstrip(b"\x00")
        n = len(_SPEC.findall(raw))
        if not raw.endswith(b"%c") or not 1 <= n <= len(args):
            continue
        if args[n - 1] != CONTINUE_SAME_LINE or e["text"].endswith("{n}{c}"):
            continue
        nxt = by_id.get(e["entry_id"] + 1)
        if nxt and nxt["text"].startswith("{n}"):  # 뒷 블록이 스스로 새 줄을 연다
            continue
        hits.add(e["entry_id"])
    return hits


if __name__ == "__main__":
    total = 0
    for name, _lba, _size in SCN_FILES:
        s = sorted(same_line_waits(name))
        if s:
            print(f"  {name}: {len(s)} — " + " ".join(f"jp{e}" for e in s))
            total += len(s)
    print(f"같은 줄 이어 쓰기 경계 {total}곳 — 재삽입기가 앞 블록 끝에 개행을 넣는다")
