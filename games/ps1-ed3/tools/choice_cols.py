"""이벤트 선택지 창 열 수 — 스크립트 연산 `3B a b c` 가 창을 연다(해석기 `0x800736B0`, 점프표 항목 0x3B).

`a` = 결과 변수 번호, **`b` = 열 × 2**(코드: `열 = b >> 1`), `c` = 줄 수. 창은 `0x800174A0(x, 15, 열, 줄)` 로 열리고 **x = 148 − 6×열**이라
열이 바뀌어도 가운데(148)가 유지된다. 뒤에 선택지가 `줄` 개 `[번호] 90 <포인터 u16>` 로 이어진다(첫 항목은 `00 90`).
원판은 일본어 최대 글자 수로 열을 박아 뒀다 — 한글 폭과 안 맞으면 잘리거나(넓힘) 커서 상자가 글자보다 훨씬 넓다(줄임, 마스터 11-06 「가장 긴 항목에 맞춰서
가로길이 조절」). 맞춤 열 = 올림((가장 긴 항목 px + 6) / 12) — 엔진이 열 N 창에 12N−6px 까지만 그린다(ps1-ed4 실측 11-06, ED3 확인 화면은 칸이 비면).
스크립트 크기는 안 변한다 — 바이트 하나만 바뀐다.
"""


OP = 0x3B
ENGINE_CLIP_PX = 6
CELL_PX = 12
MIN_COLS = 2
MAX_COLS = 24  # x = 148 − 6×열 ≥ 4


def item_px(text):
    """선택지 항목의 화면 폭 — 🔴 선택지 목록은 **글자마다 12px 칸**이다(공백·숫자·부호도 한 칸 — 대사창의 반각 0.5슬롯이 안 먹는다. 11-06 새 롬 촬영:
    「코인을 사고 싶다」·「…수상한 2인조」 의 공백이 온칸으로 그려져 마지막 글자가 잘렸다)."""
    return CELL_PX * len(text)


def need_cols(px):
    return min(MAX_COLS, max(MIN_COLS, -(-(px + ENGINE_CLIP_PX) // CELL_PX)))


def scan(mem, info):
    """[(연산 위치 p, 현재 열, 줄, [조각 번호…])] — 첫 항목이 `00 90` 이고 항목 포인터가 전부 조각 시작인 `3B` 만."""
    base = info["base"]
    starts = {s: i for i, (s, _c) in enumerate(info["segments"])}
    tgt = {at: t for at, t, _f in info["targets"]}
    out = []
    for p in range(1, base - 5):
        if mem[p] != OP or not 1 <= mem[p + 3] <= 8 or mem[p + 4] != 0 or mem[p + 5] != 0x90:
            continue
        r = mem[p + 3]
        sites = [at for at in sorted(tgt) if p + 4 <= at <= p + 4 + 4 * r + 2][:r]
        if len(sites) < r:
            continue
        ids = [starts.get(tgt[a]) for a in sites]
        if None in ids:
            continue
        out.append((p, mem[p + 2] >> 1, r, ids))
    return out


def patch(mem, info, kr_of, disc="ed3"):
    """`mem`(재구축 뒤 멤버)의 선택지 열 바이트를 맞춘다. `kr_of(조각 번호)` = 구운 글(없으면 None → 그 창은 건드리지 않는다).
    반환: (새 bytes, [(위치, 옛 열, 새 열)])."""
    out, log = bytearray(mem), []
    for p, cols, _r, ids in scan(mem, info):
        texts = [kr_of(i) for i in ids]
        if any(t is None for t in texts):
            continue
        px = max(item_px(t) for t in texts)
        need = need_cols(px)
        if need != cols:
            out[p + 2] = need * 2
            log.append((p, cols, need))
    return bytes(out), log
