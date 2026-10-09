"""대사 VM 의 opcode 표 — **디스패치 트리를 걸어서** 뽑는다.

지금 파서(`scriptmap`)는 스크립트 구간에서 `0x90`(ED3) · `0x0F`(ED4) 바이트를 **스캔**한다.
바이트 스트림을 스캔하면 **인자에 우연히 그 값이 있는 자리**에 속는다 — 그래서 못 푼 자리가
남았다(ED3 452 중 152). opcode 마다 인자가 몇 바이트인지 알면 IP 를 정확히 밀 수 있고,
그러면 스캔이 필요 없다.

## 디스패치는 점프 테이블이 아니다

컴파일러가 `switch` 를 **비교 트리**로 폈다(0x8003850C~). 그래서 표가 메모리에 없고,
**코드를 걸어야** 나온다:

```
lbu   v0, 0x24(fp)        ; opcode
addiu v1, zero, K
beq   v0, v1, HANDLER     ; opcode == K  →  HANDLER
slti  v1, v0, K2
beqz  v1, ELSE            ; opcode >= K2 →  ELSE (다른 가지)
...
j     DEFAULT
```

⚠ **정적으로 읽는다**(capstone). 에뮬로 재현하면 회차마다 달라질 수 있고, 무엇보다
   이 표는 **커밋되는 정본**이 되어야 한다(제1 원칙: 빌드는 결정적이어야 한다).

## 결과 — 표가 작다 (ED3, 실측 2026-09-03)

```
0x00~0x0C   제어 (개행·문장끝·대기·색 …) — **인자 0바이트**. 핸들러 어디도 IP 를 안 민다
0x90        문자열 — 다음 짝수 자리의 u16 이 `TEXT_BASE + (V & ~1)`
그 밖       기본 가지: `byte - 0x10` 을 0x2c(fp) 에 넣는다 (글자 쪽)
```

⇒ **IP 를 걸어도 0x90 스캔과 결과가 똑같다**(33,861/34,265, 완전 일치). 스캔이 문제가 아니었다.

## 그러면 안 풀리는 404 는 무엇인가

전부 **스크립트 구간 안의 데이터**다. 눈으로 확인했다 — `0f 08 90 2b 0f 0f 0f 0f` 같은 구조체
한복판의 `0x90` 이 opcode 로 읽힌다. 근거 셋:

- 목표가 **멤버 밖**(242) 이거나 **조각 한복판**(162) 이다. 진짜 포인터는 조각 시작을 가리킨다.
- 멤버 123·103 개에 **하나둘씩 흩어져** 있다(뭉쳐 있으면 그 멤버에서 어긋난 것이다).
- 스크립트 구간 안 상대 위치가 **앞쪽**(중앙 0.41)이다 — 꼬리 패딩이 아니다.

🔴 즉 남은 미지는 **메시지 VM 이 아니라 그 데이터를 가진 이벤트 VM** 이다. 그걸 읽어야
   「같은 길이로만」인 152 멤버와 `*B.BIN` 143 개가 닫힌다. **여기까지가 이 도구의 범위다.**

⚠ ED4 는 구조가 다르다 — 스크립트 커서가 스택이 아니라 **전역 `0x800C65E8`** 이고
  (`0x80046094` 에서 `lbu` 로 읽어 `0x0F` 와 비교), 디스패치 모양도 ED3 과 다르다. 미착수.

## 이벤트 VM — 자리는 찾았고 해독은 안 했다 (ED3, 정찰 2026-09-03)

| 무엇 | 어디 |
| --- | --- |
| 메시지 VM 함수 | `0x80038340` — `a1` 로 **스트림 포인터**를 받는다 |
| 그걸 부르는 곳 | `0x8003A1E8` **하나뿐**. `a1` 은 전역에서 오고 반환값을 도로 넣는다 |
| 전역 스크립트 커서 | **`0x800DD734`** |
| 그 전역을 건드리는 자리 | **291곳**, `0x80063xxx`~`0x80080xxx` 에 퍼져 있다 |
| 디스패치 모양 | **점프 테이블**(`sltiu` 경계검사 + `sll ...,2` + `lw` + `jr`), 예: `0x80063968`, 표 `0x800105B8` 16칸 |

⇒ 이벤트 VM 은 **메시지 VM 보다 훨씬 크다.** 커서에서 바이트를 읽어 곧장 테이블로 가는
   자리는 안 보였다(구조체 필드를 거친다). 핸들러마다 커서를 얼마나 미는지 세면
   「어디가 코드고 어디가 데이터인가」가 정해지고, 그래야 152 멤버와 `*B.BIN` 이 닫힌다.
   **여기부터가 다음 덩어리다.**
"""

import argparse
import os
import re
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

# 디스패치가 시작하는 자리 — 디스어셈블로 찾았다(둘 다 `lbu v0, 0x24(fp)` 로 연다).
DISPATCH = {"ed3": 0x8003850C, "ed4": None}
EXE = {"ed3": "/ED3.EXE", "ed4": "/SLPS_015.40"}
T_ADDR, HDR = 0x80010000, 0x800


def _md():
    return capstone.Cs(
        capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN
    )


def load(disc):
    lba, size = common.iso_files(disc)[EXE[disc]]
    return common.read_lba(disc, lba, size)


def code(data, ram, n):
    off = ram - T_ADDR + HDR
    return bytes(data[off : off + n * 4])


def walk(data, start, limit=64):
    """({opcode: 핸들러}, 기본 가지) — 비교 트리를 **범위를 들고** 걷는다.

    🔴 범위가 핵심이다. 트리는 `slti` 로 구간을 반씩 가르고, **마지막 한 값만 남으면
       비교 없이 `j` 로 간다.** 범위를 안 들면 그 `j` 를 「기본 가지」로 오해해 가지가
       통째로 사라진다(실측: 그렇게 해서 opcode 를 9개밖에 못 찾았다).

    ⚠ 「남은 한 값」은 **범위 − 이미 배정된 값**이다. `beq` 로 가운데 값을 하나 빼는 건
      범위로 표현이 안 되므로(구멍이 생긴다) 배정 집합을 같이 본다.
    """
    md = _md()
    out, seen, default, nodes = {}, set(), None, []
    stack = [(start, 0, 0xFF)]
    while stack:
        pc, lo, hi = stack.pop()
        if (pc, lo, hi) in seen or lo > hi:
            continue
        seen.add((pc, lo, hi))
        nodes.append((pc, lo, hi))
        ins = list(md.disasm(code(data, pc, limit), pc))
        k = 0
        while k < len(ins):
            i = ins[k]
            nxt = ins[k + 1] if k + 1 < len(ins) else None
            nn = ins[k + 2] if k + 2 < len(ins) else None
            # opcode == K
            if i.mnemonic == "addiu" and i.op_str.startswith("$v1, $zero,"):
                val = int(i.op_str.split(",")[-1].strip(), 0)
                br = nxt if (nxt and nxt.mnemonic in ("beq", "bne")) else None
                if br is not None and br.op_str.startswith("$v0, $v1,"):
                    tgt = int(br.op_str.split(",")[-1].strip(), 0)
                    if br.mnemonic == "beq":
                        if lo <= val <= hi:
                            out.setdefault(val, tgt)
                    else:  # bne — 같지 않으면 뛴다
                        stack.append((tgt, lo, hi))
                        lo = hi = val
                    k += 3 if nn is not None and nn.mnemonic == "nop" else 2
                    continue
            # opcode == 0
            if i.mnemonic == "beqz" and i.op_str.startswith("$v0,"):
                tgt = int(i.op_str.split(",")[-1].strip(), 0)
                if lo == 0:
                    out.setdefault(0, tgt)
                    lo = 1
                k += 2 if nxt is not None and nxt.mnemonic == "nop" else 1
                continue
            # opcode < K 로 구간을 가른다
            if i.mnemonic in ("slti", "sltiu") and i.op_str.startswith("$v1, $v0,"):
                cut = int(i.op_str.split(",")[-1].strip(), 0)
                br = nxt if (nxt and nxt.mnemonic in ("beqz", "bnez")) else None
                if br is not None and br.op_str.startswith("$v1,"):
                    tgt = int(br.op_str.split(",")[-1].strip(), 0)
                    if br.mnemonic == "beqz":  # v0 >= cut
                        stack.append((tgt, max(lo, cut), hi))
                        hi = min(hi, cut - 1)
                    else:  # v0 < cut
                        stack.append((tgt, lo, min(hi, cut - 1)))
                        lo = max(lo, cut)
                    k += 3 if nn is not None and nn.mnemonic == "nop" else 2
                    continue
            if i.mnemonic == "j":
                tgt = int(i.op_str, 0)
                rest = [v for v in range(lo, hi + 1) if v not in out]
                if len(rest) == 1:
                    out[rest[0]] = tgt  # 남은 한 값 — 비교 없이 간다
                else:
                    default = tgt if default is None else default
                break
            if i.mnemonic in ("jr", "jal"):
                break
            k += 1
    # ⚠ **가지가 값 하나로 좁혀졌으면 그 자리가 곧 핸들러다** — 컴파일러는 더 비교하지 않고
    #   바로 뛴다. 걷는 도중엔 아직 다른 값이 안 배정돼 못 알아보므로 **끝나고 한 번 더 본다.**
    for _ in range(4):
        for pc, lo, hi in nodes:
            rest = [v for v in range(lo, hi + 1) if v not in out]
            if len(rest) == 1 and pc != start:
                out.setdefault(rest[0], pc)
    return out, default


def operand_bytes(data, handler, limit=120):
    """(인자 바이트 수, [읽은 폭…]) — 그 핸들러가 IP(`0x54(fp)`)를 얼마나 미는가.

    🔴 「`lw` 다음이 `addiu` 다음이 `sw`」로 못 잡는다 — 사이에 인자를 읽는 명령이 낀다.
       **IP 를 담은 레지스터를 따라간다**: `lw rD,0x54(fp)` → rD 는 IP.
       `addiu rD,rS,N`(rS 가 IP+k) → rD 는 IP+k+N. `sw rS,0x54(fp)` → 그만큼 밀었다.
       중간의 `lbu/lhu (rS)` 는 **그 자리에서 인자를 읽었다**는 뜻이다.

    ⚠ 분기마다 다르면 None 이다 — 「대개 N」으로 뭉개면 그 자리에서 조용히 어긋난다.
    """
    md = _md()
    ip = {}  # 레지스터 → IP 로부터의 거리
    adds, reads = [], []
    for i in md.disasm(code(data, handler, limit), handler):
        m = i.mnemonic
        ops = [x.strip() for x in i.op_str.split(",")]
        if m == "lw" and i.op_str.endswith("0x54($fp)"):
            ip[ops[0]] = 0
            continue
        if m == "sw" and i.op_str.endswith("0x54($fp)"):
            if ops[0] in ip:
                adds.append(ip[ops[0]])
            continue
        if m == "addiu" and len(ops) == 3 and ops[1] in ip:
            ip[ops[0]] = ip[ops[1]] + int(ops[2], 0)
            continue
        if m in ("lbu", "lb", "lhu", "lh", "lw") and len(ops) == 2:
            mm = re.match(r"(-?0x[0-9a-f]+|-?\d+)?\((\$\w+)\)$", ops[1])
            if mm and mm.group(2) in ip:
                reads.append({"lbu": 1, "lb": 1, "lhu": 2, "lh": 2, "lw": 4}[m])
                continue
        if m in ("j", "jr", "jal"):
            break
        if m in ("move",) and len(ops) == 2 and ops[1] in ip:
            ip[ops[0]] = ip[ops[1]]
            continue
        if ops and ops[0] in ip and m not in ("nop",):
            ip.pop(ops[0], None)  # 다른 값으로 덮였다 — 더는 IP 가 아니다
    if not adds:
        return 0, reads
    return (adds[0] if len(set(adds)) == 1 else None), reads


def table(disc):
    """[(opcode, 핸들러, 인자 바이트 수)] — 못 정한 건 None."""
    if DISPATCH.get(disc) is None:
        raise SystemExit(f"{disc}: 디스패치 자리를 아직 안 찾았다")
    data = load(disc)
    ops, default = walk(data, DISPATCH[disc])
    return [(op, h, *operand_bytes(data, h)) for op, h in sorted(ops.items())], default


CANON = os.path.join(common.ROOT, "opcodes_ed3.json")


def main():
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--freeze", action="store_true", help="정본에 박는다")
    ap.add_argument("--check", action="store_true", help="정본과 같은가 (게이트)")
    a = ap.parse_args()
    common.verify_source(a.disc)
    rows, default = table(a.disc)
    known = sum(1 for _, _, n, _ in rows if n is not None)
    print(
        f"{a.disc}: opcode {len(rows)} · 인자 크기를 정한 것 {known} · 기본 가지 0x{default or 0:08X}"
    )
    for op, h, n, reads in rows:
        r = "".join(f" r{x}" for x in reads[:6])
        print(f"  0x{op:02X} → 0x{h:08X}  인자 {n if n is not None else '?'}B{r}")
    if a.disc != "ed3":
        return 0
    doc = {
        "_doc": "대사 VM opcode 표 — 디스패치 트리에서 뽑았다. 자세한 건 tools/opcodes.py",
        "disc": "ed3",
        "dispatch": f"0x{DISPATCH['ed3']:08X}",
        "default": f"0x{default:08X}" if default else None,
        "opcodes": {f"0x{op:02X}": {"handler": f"0x{h:08X}", "operand": n} for op, h, n, _ in rows},
    }
    if a.freeze:
        with open(CANON, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"→ {CANON}")
        return 0
    if a.check:
        if not os.path.exists(CANON):
            print("⏭ opcode 정본이 아직 없다")
            return 0
        with open(CANON, encoding="utf-8") as f:
            old = json.load(f)
        same = old["opcodes"] == doc["opcodes"] and old["default"] == doc["default"]
        print(
            f"ed3: opcode 표 — {'✅ 정본과 같다' if same else '🔴 달라졌다 — 원본이나 트리 해독이 바뀌었다'}"
        )
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
