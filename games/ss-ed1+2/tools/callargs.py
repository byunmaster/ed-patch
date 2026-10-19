"""씬 오버레이(SH-2)에서 대사 블록 호출처의 가변 인자(`%c` 제어값)를 뽑는다.

`%c` 하나 = sprintf 인자 한 바이트(제어코드)다(`docs/reference/our-findings.md`). 제어값이 줄 모양을 정한다 —
2·3·1 색 켜기/끄기 · 8 쪽 넘김(키 대기+지움) · 9 키 대기 + **폭 2.0 의 빈 칸**(이어 쓰기) · 10 개행(대기 없음) ·
6·7·12 끝맺음. 값은 호출 코드의 `mov #imm,rN` + 스택 밀어 넣기에 즉치로 박혀 있다 — 그걸 읽는다.

⚠ 이름 포인터(`%s`)는 레지스터 값이라 못 읽는다(`'?'`). 호출처를 못 찾은 블록은 결과에 없다.
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

_MD = None
MARK = re.compile(r"%[csd]")


def _pool(d, base, p, w):
    ea = ((p + 4) & ~3) + (w & 0xFF) * 4
    if ea - base < 0 or ea - base + 4 > len(d):
        return None
    return struct.unpack(">I", d[ea - base : ea - base + 4])[0]


def extract(d, base, blocks):
    """`{entry_index: [인자…]}` — `blocks` 는 `{절대주소: entry_index}`."""
    words = [struct.unpack(">H", d[i : i + 2])[0] for i in range(0, len(d) - 1, 2)]
    res = {}
    for i, w in enumerate(words):
        p = base + i * 2
        if w >> 12 != 0xD or ((w >> 8) & 0xF) != 5:  # mov.l pool,r5 — 문자열 포인터
            continue
        v = _pool(d, base, p, w)
        if v is None or v not in blocks:
            continue
        regs, stack, ok = {}, [], False
        for j in range(i + 1, min(len(words), i + 80)):
            x, hi = words[j], words[j] >> 12
            if hi == 0xE:  # mov #imm,rn
                imm = x & 0xFF
                regs[(x >> 8) & 0xF] = imm - 256 if imm & 0x80 else imm
            elif hi == 0xD:
                regs[(x >> 8) & 0xF] = ("P", _pool(d, base, base + j * 2, x))
            elif hi == 6 and (x & 0xF) == 3:  # mov rm,rn
                regs[(x >> 8) & 0xF] = regs.get((x >> 4) & 0xF, "?")
            elif hi == 2 and (x & 0xF) == 6 and ((x >> 8) & 0xF) == 15:  # mov.l rm,@-r15
                stack.append(regs.get((x >> 4) & 0xF, "?"))
            elif x & 0xF0FF == 0x400B:  # jsr @rn
                ok = True
                break
        if ok:
            res.setdefault(blocks[v], []).append([regs.get(6, "?"), regs.get(7, "?")] + stack[::-1])
    return res


_CACHE = {}


def for_file(path):
    """`{JP 원문: 인자 목록}` — 같은 원문이 서로 다른 인자로 불리면 그 원문은 뺀다(애매하다)."""
    if path in _CACHE:
        return _CACHE[path]
    import patch_scn as S

    out = {}
    got = S.load(path)
    f, mm = common.open_image()
    try:
        ent = {a: (l, s) for a, l, s in common.iso_files(mm)}
        if got and path in ent:
            d = bytes(common.read_extent(mm, *ent[path]))
            ents = got[1]
            la = None
            for e in ents:
                if e.get("ptr_at"):
                    pa = int(e["ptr_at"][0], 16)
                    la = struct.unpack(">I", d[pa : pa + 4])[0] - int(e["file_offset"], 16)
                    break
            if la is not None:
                blocks = {la + int(e["file_offset"], 16): i for i, e in enumerate(ents) if e.get("kind") == "block"}
                res = extract(d, la, blocks)
                seen = {}
                for i, calls in res.items():
                    jp = ents[i].get("text", "")
                    n = len(MARK.findall(jp))
                    for args in calls:
                        if len(args) >= n:
                            seen.setdefault(jp, []).append(tuple(args[:n]))
                out = {jp: list(v[0]) for jp, v in seen.items() if len(set(v)) == 1}
    finally:
        mm.close()
        f.close()
    _CACHE[path] = out
    return out
