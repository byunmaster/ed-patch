"""이벤트 선택지 창 열 수 — 스크립트 연산 `3B <첫째 바이트> <열> <줄>` 이 창을 연다(해석기 `0x80046334`: `0x80015B20(4, …, 열, 줄)` 을 부른다).

연산 뒤에 선택지 문자열 `줄` 개가 `0F <색인 u16(짝수 자리)> <흐름>` 으로 이어진다. **열은 원문 문자열의 최대 글자 수로 박혀 있다**(전수 28곳이 그렇다) —
한국어가 한 글자라도 길면 오른쪽이 잘리고 커서 상자가 글자 끝에 붙는다(마스터 10-25 「고기 요(리)」·「장작 패기」·「역사책을 본다」).
그래서 번역 뒤 **가장 긴 선택지 + 1칸**으로 늘린다(줄이지는 않는다). 스크립트는 안 움직인다 — 바이트 하나만 바뀐다.
"""

import struct

OP = 0x3B
TEXT = 0x0F
MARGIN = 1  # 글자 끝과 커서 상자 사이 여백(칸)
MAX_COLS = 20


def scan(mem, base, nseg):
    """[(연산 위치 p, 열, 줄, [색인…])] — 스크립트 구간 `[0, base)` 에서 형식이 맞는 `3B` 연산(문자열 `줄` 개가 그대로 이어져야 한다)."""
    out = []
    for p in range(1, base - 5):
        if mem[p] != OP:
            continue
        cols, rows = mem[p + 2], mem[p + 3]
        if not (1 <= rows <= 8 and 1 <= cols <= 24):
            continue
        q, idxs = p + 5, []
        for _ in range(rows):
            if q + 4 > base or mem[q] != TEXT:
                break
            ip = (q + 2) // 2 * 2
            idx = struct.unpack_from("<H", mem, ip)[0]
            if idx >= nseg:
                break
            idxs.append(idx)
            q = ip + 3
        if len(idxs) == rows:
            out.append((p, cols, rows, idxs))
    return out


def patch_cols(mem, base, segs, orig_segs=None):
    """멤버 바이트열 `mem`(스크립트 구간 `[0, base)`)의 선택지 창 열을 `segs`(새 조각 코드열) 기준으로 넓힌 사본과 [(위치, 옛, 새)]."""
    out, log = bytearray(mem), []
    for p, cols, _rows, idxs in scan(mem, base, len(segs)):
        need = min(MAX_COLS, max(len(segs[i]) for i in idxs) + MARGIN)
        if need > cols:
            out[p + 2] = need
            log.append((p, cols, need))
    return bytes(out), log
