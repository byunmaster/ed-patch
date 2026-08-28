"""`/SYSTEM/BATTLE.BIN` 의 **프리렌더 이름판**을 한글로 다시 그린다.

🔴 HP 창의 `ジュリオ` 는 문자열이 아니라 **그림**이다 — `status.spr` 항목에 든
128×128 4bpp 아틀라스에 **40×8 이름판 14 개**가 미리 그려져 있다(2026-08-29).
게임은 파티원 것을 떼어 VDP1 `0x1A980` 으로 펴고 `40x8` 스프라이트로 찍는다.

**이름판 규격**(실측, 14 판 전부 같다):

```
아틀라스 (40 + 8·n, 0..7)         ← n 번째 판, 40×8
판        값 9(밝은 회색)가 글자를 감싸고, **획은 1~5(어두움)** 로 파여 있다
꼬리      글자 뒤로 이어지는 막대 — 열마다 rows 4..7 이 [7,2,5,9]
꼬리 끝   마지막 세 열이 고정 마개다 (아래 TAIL_CAP)
```

⚠ **항목 크기를 바꾸지 않는다.** 뱅크는 `[크기][이름][스트림]` 연쇄라 크기를 줄이면
뒤 항목이 전부 밀린다. 다시 압축한 스트림을 넣고 **남는 자리는 0 으로 채운다**
(해제기는 선언된 길이만큼만 읽으니 뒤는 안 본다).

    python3 tools/reinsert_battle.py          # 들어가나 보기만
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common as C
import lzss

from shared import fonts

PATH = "/SYSTEM/BATTLE.BIN"
ENTRY = "status.spr"
AW = AH = 128  # 아틀라스
STRIDE = AW // 2  # 4bpp
PX0, PW, PH = 40, 40, 8  # 이름판 왼쪽 끝 · 폭 · 높이
#   🔴 **밝은 판에 어두운 글자다**(유저 지적 2026-08-29). 처음엔 뒤집어 그렸다 —
#     원본을 값으로 보면 배경이 9(밝은 회색)고 획이 1~5(어두움)다. 획 안쪽이 2 로 가장 흔하다.
PLATE = 9  # 판 바탕 (밝은 회색)
INK = 2  # 글자 획 (어두움)
BAR_TOP = 4  # 이 행부터 아래는 **바처럼 꽉 채운다** (원본도 rows 4~7 이 꽉 찼다)
PAD = 1  # 글자를 왼쪽에서 한 칸 띄운다 — 원문도 판 왼쪽에 한 칸이 있다(유저 지적)
TAIL = (0, 0, 0, 0, 7, 2, 5, 9)  # 꼬리 몸통 한 열
TAIL_CAP = (  # 마지막 네 열 (36~39)
    (0, 0, 0, 0, 7, 2, 4, 9),
    (0, 0, 0, 0, 0, 5, 2, 5),
    (0, 0, 0, 0, 0, 7, 4, 2),
    (0, 0, 0, 0, 0, 0, 7, 7),
)

#   🔴 **눈으로 읽어 확신이 서는 것만 넣는다.** 판 7~13 은 아직 못 읽었다 —
#     엉뚱한 이름을 넣느니 원문을 두는 게 낫다(유저 확인 대기).
#   ⓘ 표기는 `glossary_manual.json` 정본을 따른다.
NAMES = {
    0: "쥬리오",
    1: "크리스",
    2: "샤라",
    3: "구스",
    4: "로디",
    5: "휘리",
    6: "알프",
}


def _get(buf, x, y):
    b = buf[y * STRIDE + x // 2]
    return (b >> 4) if x % 2 == 0 else (b & 0xF)


def _set(buf, x, y, v):
    i = y * STRIDE + x // 2
    if x % 2 == 0:
        buf[i] = (v << 4) | (buf[i] & 0x0F)
    else:
        buf[i] = (buf[i] & 0xF0) | v


def draw_plate(atlas, n, word, bdf):
    """판 `n` 을 `word` 로 다시 그린다 — 글자 + 꼬리. 글자 폭(px)을 돌려준다."""
    y0 = n * PH
    for c in range(PW):  # 판을 비운다
        for y in range(PH):
            _set(atlas, PX0 + c, y0 + y, 0)
    #   ① 획을 먼저 모은다
    ink = [[False] * PW for _ in range(PH)]
    x = PAD
    for ch in word:
        #   ⚠ `dy=-1 · rows=8` 이 자리다 — 잉크가 최대(20)로 온전히 담기면서
        #     **획이 1~7 행에 앉아 원문과 같은 줄**이 된다(원문도 1~7 행, 유저 지적).
        #     `dy=-2` 면 0~6 행이라 한 줄 떠 보이고, `dy=-3` 은 잉크가 깎인다(20→15).
        bits = bdf.bits(ch, dy=-1, rows=PH, width=8)
        for yy in range(PH):
            for xx in range(8):
                if bits[yy][xx] and x + xx < PW:
                    ink[yy][x + xx] = True
        x += 8
    #   ② 바탕을 만든다 — 원본을 따라 셋을 지킨다(유저 지적 2026-08-29):
    #     ⓐ 위쪽은 **글자 모양을 따라 감싼다**(네모로 꽉 채우지 않는다)
    #     ⓑ 아래 `BAR_TOP` 행부터는 **바처럼 꽉 채워 오른쪽 꼬리와 잇는다**
    #     ⓒ 글자 안쪽 구멍(ㄷ·ㅁ·ㅇ 속)은 **메운다** — 원본엔 뚫린 데가 없다
    plate = [[False] * PW for _ in range(PH)]
    for yy in range(PH):
        for xx in range(x):
            if yy >= BAR_TOP:
                plate[yy][xx] = True
            elif not ink[yy][xx]:
                plate[yy][xx] = any(
                    ink[yy + dy][xx + dx]
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                    if 0 <= yy + dy < PH and 0 <= xx + dx < PW
                )
    #   ⓒ 바깥에서 물을 부어 **닿지 않는 빈칸 = 구멍**을 찾아 메운다.
    solid = [[plate[y][c] or ink[y][c] for c in range(PW)] for y in range(PH)]
    seen = [[False] * PW for _ in range(PH)]
    stack = [(y, c) for y in range(PH) for c in (0, x - 1) if x and not solid[y][c]]
    stack += [(y, c) for y in (0, PH - 1) for c in range(x) if not solid[y][c]]
    while stack:
        yy, xx = stack.pop()
        if not (0 <= yy < PH and 0 <= xx < x) or seen[yy][xx] or solid[yy][xx]:
            continue
        seen[yy][xx] = True
        stack += [(yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1)]
    for yy in range(PH):
        for xx in range(x):
            if not solid[yy][xx] and not seen[yy][xx]:
                plate[yy][xx] = True
    #   ③ 바탕 → 획 순으로 얹는다
    for yy in range(PH):
        for xx in range(PW):
            if plate[yy][xx]:
                _set(atlas, PX0 + xx, y0 + yy, PLATE)
    for yy in range(PH):
        for xx in range(PW):
            if ink[yy][xx]:
                _set(atlas, PX0 + xx, y0 + yy, INK)
    #   꼬리 — **바로 이어 붙인다**(사이를 띄우면 바가 끊겨 보인다)
    start = min(x, PW - len(TAIL_CAP))
    for c in range(start, PW - len(TAIL_CAP)):
        for y in range(PH):
            _set(atlas, PX0 + c, y0 + y, TAIL[y])
    for k, col in enumerate(TAIL_CAP):
        for y in range(PH):
            _set(atlas, PX0 + PW - len(TAIL_CAP) + k, y0 + y, col[y])
    return x


def patch(bank):
    """`(새 bank, 다시 그린 판 수, [사유])` — **길이 불변**."""
    ents = {n: (o, s, st) for n, o, s, st in lzss.entries(bank)}
    if ENTRY not in ents:
        return bank, 0, [f"{ENTRY} 항목이 없다"]
    off, size, stream = ents[ENTRY]
    atlas, _end = lzss.decode(bank, stream)
    atlas = bytearray(atlas)
    bdf = fonts.galmuri("Galmuri7")
    n = 0
    for idx, word in sorted(NAMES.items()):
        draw_plate(atlas, idx, word, bdf)
        n += 1
    room = size - (stream - off)
    enc = lzss.encode(bytes(atlas))
    if len(enc) > room:
        return bank, 0, [f"{ENTRY}: 칸 {room}B 에 {len(enc)}B"]
    out = bytearray(bank)
    out[stream : stream + room] = enc + b"\x00" * (room - len(enc))
    assert len(out) == len(bank), (len(out), len(bank))
    return bytes(out), n, []


def main():
    with C.open_disc(1) as d:
        fs = {n: (l, s) for n, l, s in d.files()}
        lba, size = fs[PATH]
        bank = d.read_extent(lba, size)
    new, n, bad = patch(bank)
    ents = {e[0]: e for e in lzss.entries(bank)}
    _, off, sz, st = ents[ENTRY]
    room = sz - (st - off)
    print(f"{ENTRY} 칸 {room}B · 이름판 {n} 개를 다시 그렸다 · 실패 {len(bad)}")
    for why in bad:
        print(f"  ❌ {why}")
    #   되읽어 확인 — 압축·해제가 왕복하나
    if not bad:
        back, _ = lzss.decode(new, st)
        want, _ = lzss.decode(bank, st)
        print(
            f"  왕복 {len(back)}B (원본 {len(want)}B) — 크기 {'일치' if len(back) == len(want) else '🔴 다름'}"
        )
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
