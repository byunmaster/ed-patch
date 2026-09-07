"""시나리오를 진입점부터 따라간다 — **재삽입 단위가 설 수 있나**를 재는 자.

🔴 **시나리오 한 장은 「스크립트 파일」이 아니라 「8086 코드 + 이벤트 스크립트」다.**
머리 세 바이트가 `e9 xx xx`(JMP rel16)이고, 이벤트 스크립트는 그 코드가 **가리켜서**
들어간다. 그래서 스크립트 옵코드만 따라가면 **0.8% 밖에 안 닿는다**(2026-08-30 실측).

이 스크립트가 하는 일:

    1. `0xe000` · `0xe003` 에서 **x86 을 디스어셈블**하며 흐름을 따라간다
    2. `0xe008` 은 코드일 수도 **진입점 표**일 수도 있다 — 그 자리 값으로 가른다
    3. 코드 안의 **범위 안 즉치값**을 이벤트 진입점 후보로 걷는다
    4. 그 후보들에서 **이벤트 옵코드**를 따라가며 텍스트에 얼마나 닿는지 잰다

고치지 않는다. **얼마나 닿나**만 잰다 — 안 닿는 만큼이 코드 훅으로 메울 몫이다.
층을 셋으로 갈라 재는 이유는 **재삽입 전략이 여기서 갈리기** 때문이다:

| 층                    | 무엇을 더하나                                   | 실측  |
| --------------------- | ----------------------------------------------- | ----- |
| 진입점                | x86 흐름을 따라가며 만난 즉치값                 | 33.5% |
| + 포인터 훑기         | 데이터 어디든 **범위 안 워드**면 진입점으로 본다 | 83.5% |
| + 이어짐              | 닿은 종료코드 **바로 다음**이 텍스트면 잇는다   | 90.4% |

⇒ **포인터를 전부 찾아 고치는 전략이 성립한다**(9할). 남은 1할이 선행 패치의 per-scenario
코드 훅에 해당하는 몫이다. ⚠ 훑기는 **과대추정**이다 — 우연히 범위 안 값인 바이트쌍이
진입점으로 잡힐 수 있다. 재삽입에 쓰려면 후보마다 **검증**이 붙어야 한다.
"""

import sys
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_16, Cs
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import scn

BASE = 0xE000
ASM_ENTRIES = (0xE000, 0xE003)
THIRD_ENTRY = 0xE008

# 이벤트 스크립트 옵코드 — 길이는 옵코드 자신을 포함한다.
CODE_LEN = {
    0x00: 1,
    0x01: 1,
    0x02: 1,
    0x03: 1,
    0x04: 1,
    0x05: 1,
    0x06: 1,
    0x07: 1,
    0x08: 1,
    0x09: 2,
    0x0A: 1,
    0x0B: 1,
    0x0C: 3,
    0x0D: 1,
    0x0E: 1,
    0x0F: 3,
    0x10: 3,
    0x11: 3,
    0x12: 3,
    0x13: 3,
    0x14: 3,
    0x15: 3,
    0x16: 11,
    0x1A: 1,
    0x1C: 1,
    0x1E: 1,
    0x1F: 1,
}
TERMINATORS = {0x00, 0x06, 0x07, 0x0A, 0x0D}
BRANCHES = {0x0F, 0x10, 0x11, 0x12, 0x13, 0x14}
ASM_CALL, ASM_STOP = 0x15, 0xE887

_STOP_MNEMONIC = {"ret", "retf", "iret", "jmp", "hlt"}
_md = Cs(CS_ARCH_X86, CS_MODE_16)
_md.detail = True


def _in_range(addr: int, size: int) -> bool:
    return BASE <= addr < BASE + size


def walk_x86(data: bytes) -> tuple[set[int], set[int]]:
    """x86 흐름을 따라간다 → (닿은 코드 바이트, 범위 안 즉치값 = 이벤트 진입점 후보)"""
    size = len(data)
    seen: set[int] = set()
    candidates: set[int] = set()
    todo = list(ASM_ENTRIES)

    # 셋째 진입점 — 코드냐 표냐. 표면 워드마다 진입점이 줄줄이 들어 있다.
    off = THIRD_ENTRY - BASE
    word = int.from_bytes(data[off : off + 2], "little")
    if _in_range(word, size):
        a = off
        while True:
            w = int.from_bytes(data[a : a + 2], "little")
            if not _in_range(w, size):
                break
            candidates.add(w)
            todo.append(w)
            a += 2
    else:
        todo.append(THIRD_ENTRY)

    while todo:
        addr = todo.pop()
        if not _in_range(addr, size) or addr in seen:
            continue
        for insn in _md.disasm(data[addr - BASE :], addr):
            if insn.address in seen:
                break
            for k in range(insn.size):
                seen.add(insn.address + k)
            for op in insn.operands:
                if op.type == X86_OP_IMM and _in_range(op.imm, size):
                    candidates.add(op.imm)
                    todo.append(op.imm)
                elif op.type == X86_OP_MEM and _in_range(op.mem.disp, size):
                    candidates.add(op.mem.disp)
            if insn.mnemonic in _STOP_MNEMONIC:
                break
            if insn.mnemonic.startswith("j") or insn.mnemonic == "call":
                pass  # 위에서 즉치값으로 이미 걷었다
    return seen, candidates


def walk_events(data: bytes, entries: set[int]) -> set[int]:
    """이벤트 옵코드를 따라가며 닿은 바이트 오프셋을 모은다."""
    size = len(data)
    seen: set[int] = set()
    todo = [a for a in entries if _in_range(a, size)]
    started = set()
    while todo:
        addr = todo.pop()
        if addr in started or not _in_range(addr, size):
            continue
        started.add(addr)
        while _in_range(addr, size):
            off = addr - BASE
            if off in seen:
                break
            b = data[off]
            if b >= 0x20:
                seen.add(off)
                addr += 1
                continue
            n = CODE_LEN.get(b)
            if n is None:
                break
            for k in range(n):
                seen.add(off + k)
            if b in BRANCHES:
                todo.append(int.from_bytes(data[off + 1 : off + 3], "little"))
            if b == ASM_CALL and int.from_bytes(data[off + 1 : off + 3], "little") == ASM_STOP:
                break
            addr += n
            if b in TERMINATORS:
                break
    return seen


def pointer_sweep(data: bytes, body: int, seed: set[int]) -> set[int]:
    """데이터 어디든 **범위 안 워드**면 진입점 후보로 본다(과대추정, 천장 측정용)."""
    out = set(seed)
    size = len(data)
    for i in range(body - 1):
        w = int.from_bytes(data[i : i + 2], "little")
        if _in_range(w, size):
            out.add(w)
    return out


def continuation_pass(data: bytes, body: int, seen: set[int], rounds: int = 6) -> set[int]:
    """닿은 종료코드 **바로 다음**이 텍스트면 이어진 블록으로 본다."""
    for _ in range(rounds):
        extra = {
            off + 1 + BASE
            for off in seen
            if data[off] in TERMINATORS
            and off + 1 < body
            and data[off + 1] >= 0x20
            and (off + 1) not in seen
        }
        if not extra:
            break
        seen = seen | walk_events(data, extra)
    return seen


def main() -> int:
    common.check_originals()
    scenario, _ = scn.load()
    tot_text = 0
    tiers = {"진입점": 0, "+포인터훑기": 0, "+이어짐": 0}
    worst = []
    for key, info in scenario.items():
        data = info["data"]
        body = len(data) - info["tail_free"]
        code_seen, candidates = walk_x86(data)
        text_off = {i for i, b in enumerate(data[:body]) if b >= 0x20} - code_seen
        tot_text += len(text_off)

        a = text_off & walk_events(data, candidates)
        sweep = pointer_sweep(data, body, candidates)
        seen_sweep = walk_events(data, sweep)
        b = text_off & seen_sweep
        c = text_off & continuation_pass(data, body, seen_sweep)
        tiers["진입점"] += len(a)
        tiers["+포인터훑기"] += len(b)
        tiers["+이어짐"] += len(c)
        if text_off:
            worst.append((len(c) / len(text_off), scn.format_key(key), len(text_off)))
    worst.sort()
    print(f"시나리오 {len(scenario)}건 · 텍스트 {tot_text:,}B (x86 이 닿은 바이트는 뺐다)")
    for name, n in tiers.items():
        print(f"  {name:12s} {n:7,} = {n / tot_text:6.1%}")
    print("  이어짐까지 해도 못 닿은 시나리오:")
    for ratio, key, n in worst[:8]:
        print(f"    {key}  {ratio:6.1%}  (텍스트 {n:,}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
