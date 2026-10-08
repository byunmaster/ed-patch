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
import glossary_src as GS
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
#   ⚠ **값이 클수록 어둡다**(CRAM 실측) — 1=밝기224 · 2=200 · 4=144 · 5=117 · 9=89.
#     즉 원문은 **어두운 판에 밝은 글자**다. 미리보기를 `값×17` 로 그리면 명암이 뒤집혀
#     보이니, 확인은 반드시 **CRAM 팔레트를 씌워** 한다(2026-08-29 이걸로 한참 헤맸다).
INK = 2  # 글자 획 (밝다)
BAR_TOP = 4  # 이 행부터 아래는 **바처럼 꽉 채운다** (원본도 rows 4~7 이 꽉 찼다)
PAD = 1  # 글자를 왼쪽에서 한 칸 띄운다 — 원문도 판 왼쪽에 한 칸이 있다(유저 지적)
GAP = 1  # 글자 사이 (잉크 폭에 붙여 준다 — 고정 간격을 쓰면 좁은 글자 뒤가 벌쭉해진다)
#   🔴 **바탕은 Galmuri7 을 쓰고, 안 읽히는 글자만 손으로 덮는다**(유저 확정 2026-08-29).
#     칸이 7×7 뿐이라 기성 글꼴이 힘든데, 그렇다고 전부 손으로 그릴 일도 아니다 —
#     대부분은 Galmuri7 이 잘 나오고 **몇 자만 획이 뭉갠다.**
#     ⚠ Galmuri9 는 안 된다 — 잉크가 1~9 행이라 8 행 칸에서 **글자마다 2~9px 이 잘린다**
#       (`오`·`로`·`알`·`프` 는 9px). 「잉크가 는다」만 보고 고르면 이 함정에 빠진다.
FONT, FONT_DY, CELLW = "Galmuri7", -1, 8

#   ⚠ **글자를 손으로 덮는 길을 냈다가 걷었다**(유저 확정 2026-08-29). `로`·`휘`·`알` 이
#     안 읽힌다고 보고 7×7 로 직접 그렸는데, 견줘 보니 **Galmuri7 이 대체로 낫다** —
#     `로`·`알` 의 ㄹ 은 `루`·`르`·`젤` 과 **같은 꼴**이라 손으로 그리면 그 자리만 튄다.
#     「폰트가 그렇게 세팅된 이유가 있다」는 판단이다. 장치는 남겨 두되 **비워 둔다** —
#     정말 못 쓸 글자가 나오면 여기 한 줄이면 된다.
#     ⓘ 표는 `{글자: (GH 줄, 각 줄 같은 폭)}` 이고 `#` 이 획이다. `GY` 행부터 그린다.
GH, GY = 7, 1
GLYPHS = {}
for _ch, _g in GLYPHS.items():
    assert len(_g) == GH and len({len(r) for r in _g}) == 1, _ch

TAIL = (0, 0, 0, 0, 7, 2, 5, 9)  # 꼬리 몸통 한 열
TAIL_CAP = (  # 마지막 네 열 (36~39)
    (0, 0, 0, 0, 7, 2, 4, 9),
    (0, 0, 0, 0, 0, 5, 2, 5),
    (0, 0, 0, 0, 0, 7, 4, 2),
    (0, 0, 0, 0, 0, 0, 7, 7),
)

#   이름판 열넷 = 파티원. 판독은 **대사 빈도로 검산**했다(그 이름이 실제로 쓰이는가) —
#   눈으로만 읽으면 틀린다(`ジョアンナ` 를 `ジョアッキーノ`, `バダット` 를 `バラッド` 로 봤다).
#   ⓘ 표기는 공용 사전(`shared/glossary/ed3.json`)을 따른다.
#   번호 → JP 원문. KR 은 **공용 사전**(person)에서 읽는다(2026-10-08 — 종전엔 KR 을 여기 직접 적었다).
_PARTY_JP = (
    "ジュリオ",  # 0
    "クリス",
    "シャーラ",
    "グース",
    "ローディ",
    "フィリー",  # 5
    "アルフ",
    "モリスン",
    "ジョアンナ",
    "ステラ",
    "バダット",  # 10
    "バンバン",
    "デュルゼル",
    "ルーレ",
)
NAMES = dict(enumerate(GS.party(*_PARTY_JP)))


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
        if ch in GLYPHS:  # 손으로 덮은 글자
            g = GLYPHS[ch]
            gw = len(g[0])
            cols = [c for c in range(gw) if any(g[y][c] == "#" for y in range(GH))]
            for yy in range(GH):
                for xx in range(gw):
                    if g[yy][xx] == "#" and x + xx < PW:
                        ink[GY + yy][x + xx] = True
        else:  # 나머지는 글꼴에서
            b = bdf.bits(ch, dy=FONT_DY, rows=PH, width=CELLW)
            cols = [c for c in range(CELLW) if any(b[y][c] for y in range(PH))]
            for yy in range(PH):
                for xx in range(CELLW):
                    if b[yy][xx] and x + xx < PW:
                        ink[yy][x + xx] = True
        #   🔴 **글자마다 폭이 달라 고정 간격을 쓰면 사이가 벌쭉해진다**(유저 지적) —
        #     잉크 폭 + 1 로 붙여 **사이를 늘 1px** 로 만든다.
        x += (max(cols) + 1 if cols else 3) + GAP
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
                #   🔴 **십자(4 이웃)로 부풀린다** — 네모(8 이웃)로 부풀리면 모서리가
                #     각져 판이 투박해 보인다(유저 지적 2026-08-29).
                plate[yy][xx] = any(
                    ink[yy + dy][xx + dx]
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
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
    #   🔴 **바가 시작하는 행의 왼쪽 끝 한 칸을 깎는다**(유저 지적) — 안 깎으면 판이
    #     거기서 직각으로 튀어나와 투박하다. 위쪽에 잉크가 없을 때만 깎는다.
    if _get(atlas, PX0, y0 + BAR_TOP) == PLATE and _get(atlas, PX0, y0 + BAR_TOP - 1) == 0:
        _set(atlas, PX0, y0 + BAR_TOP, 0)
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
    bdf = fonts.galmuri(FONT)
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
