"""이벤트 선택지 창 열 수 — 스크립트 연산 `3B <첫째 바이트> <열> <줄>` 이 창을 연다(해석기 `0x80046334`: `0x80015B20(4, …, 열, 줄)` 을 부른다).

연산 뒤에 선택지 문자열 `줄` 개가 `0F <색인 u16(짝수 자리)> <흐름>` 으로 이어진다. **열은 원문 문자열의 최대 글자 수로 박혀 있다**(전수 28곳이 그렇다) —
한국어가 한 글자라도 길면 오른쪽이 잘리고 커서 상자가 글자 끝에 붙는다(마스터 10-25 「고기 요(리)」·「장작 패기」·「역사책을 본다」).
그래서 번역 뒤 열을 **가장 긴 선택지의 실제 픽셀 폭**에 맞춘다 — 반각(6px)·전각(12px) 섞임을 재고 엔진이 자르는 6px 를 더해 올림한 칸 수(실측).
넓히기만 하던 것을 **줄이기도 한다**(마스터 11-06 「가장 긴 항목에 맞춰서 가로길이 조절」 — 원판 일본어 폭 그대로 남아 하늘색 커서 상자가 글자보다 훨씬 오른쪽까지 간다).
스크립트는 안 움직인다 — 바이트 하나만 바뀐다.
"""

import struct

OP = 0x3B
TEXT = 0x0F
ENGINE_CLIP_PX = 6  # 창 열 수 × 12px 에서 엔진이 글자를 자르는 폭 — 11-06 실측(열 4·5·6·7 로 직접 그림): 열 4(48px)는 「고기 요」(42px)까지만, 열 5(60px)는 「고기 요리」(54px)가 다 보인다. 메시지 창(18px)과 다르다
CELL_PX = 12
MIN_COLS = 2
MAX_COLS = 20


def need_cols_for_px(px):
    return min(MAX_COLS, max(MIN_COLS, -(-(px + ENGINE_CLIP_PX) // CELL_PX)))


def need_cols(codes, half=frozenset()):
    """선택지 한 줄(글리프 코드열)이 들어가는 최소 열 — 반각 코드(`half`)는 6px, 나머지 12px."""
    return need_cols_for_px(sum(6 if c in half else CELL_PX for c in codes))


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


MARGIN = 1  # 옛 규칙(`fit=False`): 글자 끝과 커서 상자 사이 여백(칸)


def fit_enabled():
    """맞춤 공식 스위치 — 기본 켬(마스터 미리보기 OK, 11-06). `ED_CHOICE_FIT=0` 이면 옛 규칙(코드 수+1칸 · 넓히기만)."""
    import os

    return os.environ.get("ED_CHOICE_FIT") != "0"


def patch_cols(mem, base, segs, half=frozenset(), fit=None):
    """멤버 바이트열 `mem`(스크립트 구간 `[0, base)`)의 선택지 창 열을 `segs`(새 조각 코드열) 기준으로 맞춘 사본과 [(위치, 옛, 새)].

    `fit` 거짓(기본)이면 옛 규칙 — 코드 수 + 1칸으로 **넓히기만** 한다. 참이면 실측 공식으로 줄이기도 한다.
    """
    fit = fit_enabled() if fit is None else fit
    out, log = bytearray(mem), []
    for p, cols, _rows, idxs in scan(mem, base, len(segs)):
        if fit:
            need = max(need_cols(segs[i], half) for i in idxs)
        else:
            need = min(MAX_COLS, max(len(segs[i]) for i in idxs) + MARGIN)
            if need <= cols:
                continue
        if need != cols:
            out[p + 2] = need
            log.append((p, cols, need))
    return bytes(out), log


def verify(mem, base, segs, half=frozenset()):
    """게이트 — 굽힌 멤버의 선택지 창 열이 「가장 긴 항목 + 엔진 자르기」와 **같아야** 한다. [(위치, 열, 맞출 열, 사유)] 결함 목록.

    좁으면 끝이 잘리고(🔴), 넓으면 커서 상자가 글자 끝보다 멀리 간다(마스터 11-06). 맞출 열이 `MAX_COLS` 를 넘는 창은 잘림으로 센다.
    """
    bad = []
    for p, cols, _rows, idxs in scan(mem, base, len(segs)):
        px = max(sum(6 if c in half else CELL_PX for c in segs[i]) for i in idxs)
        raw = -(-(px + ENGINE_CLIP_PX) // CELL_PX)
        need = need_cols_for_px(px)
        if raw > MAX_COLS:
            bad.append((p, cols, raw, "창이 최대 열을 넘는다(잘림)"))
        elif cols < need:
            bad.append((p, cols, need, "좁다(끝이 잘린다)"))
        elif cols > need:
            bad.append((p, cols, need, "넓다(커서 상자가 글자보다 멀리 간다)"))
    return bad
