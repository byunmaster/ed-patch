"""sfc-ed2 문자열 이전 — 코드가 `$A6~$A8`(문자열 포인터)에 즉치로 넣는 문자열을 확장 영역으로 옮긴다.

`$C0:9395`(UI 출력기)와 `$C0:A691`(대사 출력기)은 둘 다 `[$A6]` 24비트 포인터로 문자열을 읽는다. 호출 직전 코드가
`A9 lo 8D A6 00 · A9 hi 8D A7 00 · A9 bank 8D A8 00` 으로 포인터를 넣으므로, 이 즉치 셋만 고치면 문자열을 **길이 제한 없이** 다른 뱅크로 옮길 수 있다.
(같은 문자열을 가리키는 자리가 여럿이면 전부 고친다 — 하나라도 빠지면 그 호출만 옛 자리를 본다.)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

_LO = re.compile(rb"\xa9(.)\x8d\xa6\x00", re.S)


def a6_sites(d: bytes, addr: int, window: int = 40) -> list[tuple[int, int, int]]:
    """주소 `addr`(`$bb:aaaa`) 를 `$A6~$A8` 에 즉치로 넣는 자리들 → [(lo 즉치 오프셋, hi 즉치 오프셋, bank 즉치 오프셋)] (파일 오프셋 — 즉치 바이트 위치)."""
    lo, hi, bk = addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16
    code = d[: common.ROM_SIZE]
    out = []
    for m in _LO.finditer(code):
        if m.group(1)[0] != lo:
            continue
        base = m.start()
        seg = code[base : base + window]
        mh = re.search(rb"\xa9" + bytes([hi]) + rb"\x8d\xa7\x00", seg)
        mb = re.search(rb"\xa9" + bytes([bk]) + rb"\x8d\xa8\x00", seg)
        if mh and mb:
            out.append((base + 1, base + mh.start() + 1, base + mb.start() + 1))
    return out


def refs24(d: bytes, addr: int, skip: tuple[int, int] | None = None) -> list[int]:
    """문자열 시작 주소 `addr` 를 **3바이트 리틀엔디언 포인터**(`lo hi bank`)로 담은 자리들(파일 오프셋). 문자열 자신(`skip` 구간) 안은 뺀다."""
    pat = bytes([addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16])
    out, i = [], -1
    while True:
        i = d.find(pat, i + 1, common.ROM_SIZE)
        if i < 0:
            return out
        if skip and skip[0] <= i < skip[1]:
            continue
        out.append(i)
