#!/usr/bin/env python3
"""변수 삽입 앞뒤 어절 경계 검사 — 엔진이 끼우는 칸(아이템 이름 `0x04` · 숫자 `0x05`~`0x07`) 바로 앞뒤의 공백.

    python3 tools/check_var_spacing.py

메시지 VM 은 조각 사이에 변수 opcode 를 끼워 **한 줄로 이어 붙인다**(`쥬리오는 ` + [아이템] + `을(를) 받았다.`).
일본어 원문은 띄어 쓰지 않으니 번역이 직접 공백을 줘야 한다. 못 주면 「그러면1000피아에」 처럼 붙어 나간다.
- 앞: 변수 앞 조각이 공백으로 안 끝났다 (`그러면` + [값] → `그러면 `).
- 뒤: 변수 뒤 조각이 조사·서술어미(`을(를)` `에` `입니다` `(이)야` …)가 아닌 **낱말**로 시작하는데 공백이 없다
  (`받을게.` → ` 받을게.`). 변수 뒤 붙는 조사는 붙는 게 맞다 — 어절 경계만 본다.
- 이름 뒤 서술격: `군.` 처럼 받침 유무를 모르는 자리에 병기 `(이)` 가 없다.

체인은 원판 멤버의 스크립트 바이트(`0F … 90 <u16> (op 90 <u16>)* 00`)에서 읽는다 — 원판 디스크가 있어야 잰다(없으면 「안 쟀다」로 실패).
쪽·줄 나눔(op 1·2)과 끝 개행은 번역이 못 바꾸는 스크립트 바이트라 `check_structure` 가 원판과 대조해 지킨다(여기선 셈만 알린다).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re

import common
import script as script_canon
import scriptmap

# 변수 바로 뒤에 붙어도 되는 첫머리 — 조사·서술격·연결어미·부호·병기
ATTACH = re.compile(
    r"^(은|는|이|가|을|를|과|와|으로|로|에|의|도|만|까지|부터|하고|라면|라고|인|입|예요|일|군|네|다니까|면|야|겠|\(|[,.?!…~ ])"
)


def _ops_back(mem, i):
    """0x90(i) 바로 앞에 붙은 opcode(1~7) 열과 그 앞 위치."""
    ops, k = [], i - 1
    while k > 0 and 1 <= mem[k] <= 7:
        ops.insert(0, mem[k])
        k -= 1
    return ops, k


def chains(disc="ed3"):
    """[(멤버, 앞 opcode 열, [(조각, 뒤 opcode 열)…], {조각: 우리 문안})] — 대사 창 체인.

    조각 사이는 opcode 1~7(줄·쪽·변수) 이 여럿 겹칠 수 있다(`01 06 90` = 줄을 바꾸고 숫자). 창 머리는 `0F [인자] [op…] 90`."""
    iso = common.iso_files(disc)
    canon, _ = script_canon.load_effective(disc)
    out = []
    for (path, nm), lines in sorted(canon.items()):
        lba, size = iso[path]
        data = common.read_lba(disc, lba, size)
        _, ents = common.arc_parse(data)
        off, sz = next((o, s) for n, o, s in ents if n == nm)
        mem = data[off : off + sz]
        info = scriptmap.parse(mem)
        base = info["base"]
        idx = {s: i for i, (s, _c) in enumerate(info["segments"])}
        sites = dict(info["pointers"])
        member = (
            os.path.basename(path).split(".")[0]
            + "_"
            + nm.replace("\\", "/").split("/")[-1].split(".")[0]
        )
        kr = {k: v["kr"] for k, v in lines.items()}

        def nxt(q, mem=mem, sites=sites):
            """q 의 뒤 opcode 열과 다음 조각 자리(없으면 None)."""
            ops, j = [], q + 2
            while j < len(mem) and 1 <= mem[j] <= 7:
                ops.append(mem[j])
                j += 1
            if ops and j < len(mem) and mem[j] == 0x90:
                q2 = j + 1 + ((j + 1) & 1)
                if q2 in sites:
                    return ops, q2
            return ops, None

        linked = {n for q in sites if (n := nxt(q)[1]) is not None}
        for q in sorted(sites):
            if q in linked:
                continue
            i = q - 1 if mem[q - 1] == 0x90 else q - 2
            if i < 3 or mem[i] != 0x90:
                continue
            head, k = _ops_back(mem, i)
            if not (mem[k] == 0x0F or mem[k - 1] == 0x0F):
                continue
            chain, cq = [], q
            while True:
                t = base + (sites[cq] & ~1)
                if t not in idx:
                    chain = None
                    break
                ops, q2 = nxt(cq)
                chain.append((idx[t], ops))
                if q2 is None:
                    break
                cq = q2
            if chain:
                out.append((member, head, chain, kr))
    return out


def main():
    try:
        cs = chains()
    except (OSError, SystemExit, KeyError) as e:
        print(f"변수 공백 검사 — 안 쟀다(원판 디스크를 못 읽음: {e})")
        return 1
    bad = []
    nvar = ncomma = npage = 0
    for member, head, chain, kr in cs:
        for _p, ops in chain:
            ncomma += ops.count(1)
            npage += ops.count(2)
            nvar += sum(1 for o in ops if 4 <= o <= 7)
        before = [head] + [ops for _p, ops in chain[:-1]]
        for (p, ops), pre in zip(chain, before, strict=True):
            a = kr.get(p)
            # 금액 연산 `06` 은 앞 조각 공백을 안 요구한다(마스터 11-07 「이건 고쳐야지」 — 판매 대사 「그럼 ⎵⎵⎵ 3 Pia」): 연산이 값을 고정 자리 칸으로 그려 앞자리 칸이 이미 공백으로 보인다
            if a and ops and 4 <= ops[0] <= 7 and ops[0] != 6 and not a.endswith((" ", "\n")):
                bad.append((member, p, "앞 공백 없음", a))
            b = kr.get(p)
            if b and pre and 4 <= pre[-1] <= 7:
                if not ATTACH.match(b):
                    bad.append((member, p, "뒤 공백 없음", b))
                elif pre[-1] == 4 and re.match(r"군[.요]?", b):
                    bad.append((member, p, "이름 뒤 서술격 병기 `(이)` 없음", b))
                elif pre[-1] >= 5 and re.match(r"[을은이과] ", b):
                    bad.append(
                        (
                            member,
                            p,
                            "숫자(Pia) 뒤 받침 조사 — 읽는 소리 `Pia` 는 무받침(를·는·가·와)",
                            b,
                        )
                    )
    print(
        f"변수 공백 검사 [ps1-ed3] — 창 {len(cs)} · 변수 칸 {nvar} · 줄 opcode {ncomma} · 쪽 opcode {npage} (구조는 check_structure) · 어긋남 {len(bad)}"
    )
    for m, p, why, t in bad[:40]:
        print(f"  ✗ {m}@{p}  {why}: {t!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
