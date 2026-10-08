#!/usr/bin/env python3
"""`TITLE.BIN` 의 오프닝·엔딩·스태프롤 자막을 제자리 교체한다.

구조는 [`dump_title.py`](dump_title.py) 가 정본이다 — 레코드 42B + 구분 2B, 스트라이드 44.
**고정 길이 제자리 교체**라 블록 재배치도 포인터 갱신도 없다. 새턴에서 가장 싼 재삽입이다.

🔴 **중앙정렬을 우리가 채운다.** PS1 은 엔진이 필드 폭에 맞춰 중앙정렬했는데 여기는
데이터가 전각 공백 `　` 으로 좌우를 채워 놨다. 그래서 문안을 넣을 때 **폭에 맞춰 우리가
패딩을 만들어야** 한다. 남는 칸이 홀수면 **왼쪽을 한 칸 적게** 준다(원본 관용 — 실측).

⚠ **폭을 넘기면 실패시킨다.** 잘라 내면 화면에서만 티가 나고 빌드는 통과한다.

**항등 검증**(`--check`)이 이 도구의 안전판이다 — 원문을 그대로 다시 인코딩해 원본
바이트와 맞댄다. 통과하면 「레코드 경계·패딩 규칙·인코딩」이 맞다는 뜻이고, 그 위에서만
문안을 갈아 끼운다. 통과 못 하면 넣는 순간 조용히 깨진다.

  python3 games/ss-ed1+2/tools/patch_title.py --check     # 항등 (원본 불변 확인)
  python3 games/ss-ed1+2/tools/patch_title.py --apply     # work/build 에 적용
"""

import json
import os
import shutil
import sys

import common
import font
from dump_title import LABELS, PREFIX, _load, runs
from font import byte_len, to_bytes  # noqa: F401  🔴 인코딩 규칙 정본

TITLE = "/TITLE.BIN"
BUILD = common.BUILD_DIR  # ⚠ 꼬리표별로 갈린다 — `common.BUILD_TAG`


def pad(text, width, left):
    """문안을 전각 `width` 칸으로 채운다 — 왼쪽 `left` 칸.

    🔴 **정렬은 유도할 수 없다 — 원본이 손으로 짜여 있다**(2026-08-21 실측).
    중앙정렬이 대세지만 아닌 자리가 30건이다: 대사 인용(`「…」`)은 **왼쪽 고정**이고
    `Ｃｏ．，Ｌｔｄ．` 같은 꼬리표는 오른쪽으로 밀려 있다. 가운데로 계산해 넣으면
    그 자리들의 **연출이 바뀐다** — 그래서 원본의 왼쪽 패딩을 읽어서 쓴다.
    """
    text = widen(text)
    n = len(text)  # widen 뒤엔 전부 전각이라 글자 수 = 칸 수
    if n > width:
        raise SystemExit(f"폭 초과 {n}>{width}칸: {text!r}")
    left = max(0, min(left, width - n))
    return "　" * left + text + "　" * (width - n - left)


def align_of(orig, width):
    """원본 한 줄의 정렬 → `("center", None)` 또는 `("left", 왼쪽칸수)`.

    남는 칸이 좌우로 **한 칸 차이 안**이면 중앙정렬로 본다. 그 밖은 손으로 짠 자리라
    왼쪽 칸수를 그대로 물려준다.
    """
    body = orig.strip("　")
    left = len(orig) - len(orig.lstrip("　"))
    if not body:
        return ("center", None)
    right = width - left - len(body)
    return (
        ("center", None)
        if abs(left - right) <= 1 and left == (width - len(body)) // 2
        else ("left", left)
    )


# ── 한글 슬롯 배정 (2026-08-21) ───────────────────────────────────────────────
# 한글은 cp932 로 인코딩이 안 되므로 **안 쓰는 글리프 슬롯을 덮어쓰고 그 슬롯의 SJIS 코드로**
# 적는다(PS1 과 같은 수법). 슬롯 정본은 `hangul_map.json` 이고 **커밋한다** —
# 빌드가 결정적이어야 하기 때문이다(루트 CLAUDE.md 제1 원칙). 계획이 바뀌면 폰트와 문안이
# 함께 바뀌어야 하므로 둘을 **한 도구**가 만든다.
#
# ⚠ 전각 로마자·전각 공백은 **원본 폰트에 이미 있다** — 슬롯을 쓰지 않고 그대로 둔다.
HMAP = os.path.join(common.GAME_DIR, "hangul_map.json")
FONT16 = "/KANJI.FON"
GLYPH16 = 32  # 16행 × 2B
NEODGM = os.path.join(common.ROOT, "shared", "fonts", "neodgm.ttf")


def _needs_slot(ch):
    """이 글자가 슬롯을 먹어야 하나.

    🔴 **반각(1바이트) 글자를 섞으면 안 된다.** 레코드는 42B 고정인데 반각은 1B 라
    한 자만 섞여도 길이가 어긋나고, 원본은 **전부 전각**이라 렌더러가 반각을 어떻게
    다루는지도 미검증이다(2026-08-21 실측: 「아주 먼 옛날, …」 이 36B 로 나와 걸렸다).
    그래서 한글뿐 아니라 **로마자·숫자·부호도 슬롯에 배정**하고 16×16 셀 가운데에 그린다 —
    보기엔 반각인데 바이트는 전각이다.

    ⚠ 공백만 예외다 — 전각 공백 `　` 로 바꾼다(원본 폰트에 이미 있고 잉크가 없다).
    """
    if ch == " ":
        return False
    if len(ch.encode("utf-8")) == 1 or ord(ch) < 0x80:
        return True  # ASCII — 반각이라 슬롯으로 뺀다
    try:
        ch.encode("cp932")
    except UnicodeEncodeError:
        return True
    return False


def widen(s):
    """반각 공백을 전각으로 — 나머지 반각은 슬롯이 받는다."""
    return s.replace(" ", "　")


# 부호는 셀 왼쪽에 붙여 굽는다(`bake_font`) — 그래서 **오른쪽 8~12px 가 이미 비어 있다.**
HUG_LEFT = ".,!?"

# 원본의 **손배치를 무시하고 가운데**로 놓을 줄. `(구간, 화면순서 인덱스)`.
# ⚠ 기본은 물려받는 것이다(`align_of`) — 원본이 일부러 비켜 놓은 자리를 지우지 않으려고.
#   여기 오는 건 **PS1 과 그림이 갈리는** 자리뿐이다. PS1 렌더러는 모든 줄을 가운데로
#   놓으므로, 손배치를 물려받으면 그 줄만 두 판이 달라진다(유저 확정 2026-08-22 —
#   「새턴만 다르게 하고 싶지 않다」). 문안이 하나면 그림도 하나여야 한다.
FORCE_CENTER = {
    ("ED2 오프닝", 23),  # 원본 `だが…` 가 왼쪽 8칸 손배치 — 우리 문안은 길어 오른쪽에 붙었다
}


def tighten(s):
    """부호 **뒤** 공백 한 칸을 없앤다 — 그 여백은 부호 셀이 이미 만들고 있다.

    ⚠ 이건 문안 교정이 아니라 **조판**이다. 정본(`script/title.json`)은 맞춤법대로
    「하지만, 그곳에」로 두고, 화면에 나갈 때만 칸을 줄인다. 정본에서 공백을 빼면
    다음 사람이 오탈자로 보고 되돌린다.

    안 하면 「하지만 ,  그곳에」처럼 **두 칸**이 벌어진다 — 부호 셀의 여백 + 공백 셀.
    """
    out = []
    for ch in s:
        if ch == " " and out and out[-1] in HUG_LEFT:
            continue
        out.append(ch)
    return "".join(out)


def slot_plan(lines_by_region, refresh=False):
    """`{글자: (SJIS 2B, 슬롯 인덱스)}` — 정본이 있으면 그대로 쓴다.

    ⚠ **정본을 자동으로 갱신하지 않는다.** 문안이 늘어 새 글자가 생기면 실패시키고
    `--refresh` 를 요구한다 — 조용히 재배정하면 낡은 이미지의 폰트와 어긋난다.
    """
    need = sorted(
        {c for v in lines_by_region.values() for t in v for c in widen(t) if _needs_slot(c)}
    )
    old = {}
    if os.path.exists(HMAP):
        with open(HMAP, encoding="utf-8") as f:
            old = json.load(f)["syllables"]
    if refresh or not old:
        free = font.free_slots("kanji")
        assert len(need) <= len(free), f"슬롯 부족 {len(need)}>{len(free)}"
        # 🔴 **덧붙이기만 한다**(2026-09-06). 예전엔 `enumerate(need)` 로 **통째 재배정**해
        #    한 글자만 늘어도 배정이 전부 밀렸다 — pce-ed1 이 그 꼴로 세이브를 깨뜨렸다.
        #    여기는 `TITLE.BIN` 자막 전용이라 세이브에 안 들어가지만, **같은 함정이라 같은
        #    규칙으로 닫는다**(4-D — 같은 지식이 두 곳에 있으면 갈린다).
        taken = set(old.values())
        pool = [i for i in free if i not in taken]
        for c in need:
            if c not in old:
                old[c] = pool.pop(0)
        with open(HMAP, "w", encoding="utf-8") as f:
            json.dump(
                {"_doc": "한글 → KANJI.FON 슬롯 인덱스 (커밋 정본)", "syllables": old},
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"  슬롯 정본 갱신: {len(old)}자 → {HMAP}")
    missing = [c for c in need if c not in old]
    assert not missing, (
        f"정본에 없는 글자 {len(missing)}자 — `--refresh` 로 갱신할 것: {missing[:8]}"
    )
    return {c: (font.sjis_of_index(i), i) for c, i in old.items()}


def bake_font(plan):
    """계획대로 `KANJI.FON` 글리프를 굽는다 — Neo둥근모 16px 네이티브(16×16 셀)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    ft = ImageFont.truetype(NEODGM, 16, layout_engine=ImageFont.Layout.BASIC)
    out = {}
    for ch, (_sjis, idx) in plan.items():
        im = Image.new("L", (16, 16), 0)
        # 반각 글자(로마자·숫자)는 8px 라 **셀 가운데**로 민다 — 왼쪽에 붙이면 뒤에만
        # 8px 가 비어 한쪽으로 벌어진다.
        # 🔴 **부호만은 예외로 왼쪽에 붙인다**(유저 QA 2026-08-21 — 「나라였다 .」).
        #   이 렌더러는 **16px 고정 격자**라 반각이 없다(`TITLE.BIN` 은 `KANJI.FON` 하나만
        #   부른다 — 반각짝 `/ASCII.FON` 은 본편 전용). 부호를 가운데 두면 앞뒤로 4px 씩
        #   떠서 **공백이 하나 더 있는 것처럼 보인다.** 칸은 못 줄여도 **칸 안 위치는
        #   우리 것**이라, 왼쪽에 붙이면 앞 글자에 달라붙고 남는 오른쪽이 곧 뒤 공백이 된다.
        dx = 0 if (ch in HUG_LEFT or ft.getlength(ch) > 8) else 4
        ImageDraw.Draw(im).text((dx, 0), ch, fill=255, font=ft)
        bits = (np.array(im) >= 128).astype(np.uint8)
        assert bits.any(), f"글리프 없음 {ch!r}"
        out[idx] = np.packbits(bits, axis=1).tobytes()
        assert len(out[idx]) == GLYPH16

    # 말줄임표를 **셀 폭에 고르게** 다시 그린다(PS1 과 같은 처리).
    # 폰트의 `…` 는 점 셋이 가운데 몰려 한 글자처럼 뭉친다 — 유저는 온점 셋(`...`) 쪽이
    # 읽힌다고 했다. 그런데 `...` 로 통일하면 **여기서 깨진다**: 16px 고정 격자라 점마다
    # 한 칸을 먹어 16px 씩 벌어진다. 그래서 **표기는 `…` 하나로 두고 그림만** 벌린다.
    # ⚠ `…`(구 1·점 36)은 **원본 폰트가 쓰던 글리프**라 슬롯을 새로 안 먹는다. 그 자리를
    #   우리 것으로 덮는다 — 원본 어딘가에 `…` 가 남아 있어도 **여전히 말줄임표**라 안전하다.
    # ⚠ 점의 모양·기준선은 폰트의 온점에서 가져온다. 손으로 찍으면 본문 온점과 어긋난다.
    dot = Image.new("L", (16, 16), 0)
    ImageDraw.Draw(dot).text((0, 0), ".", fill=255, font=ft)
    d = (np.array(dot) >= 128).astype(np.uint8)
    _ys, xs = np.nonzero(d)
    assert len(xs), "온점 글리프가 비었다"
    w = xs.max() - xs.min() + 1
    stamp = d[:, xs.min() : xs.max() + 1]
    ell = np.zeros((16, 16), np.uint8)
    span = 16 - 2 - w
    for k in range(3):
        x = 1 + round(span * k / 2)
        ell[:, x : x + w] |= stamp
    out[font.jis_index("…")] = np.packbits(ell, axis=1).tobytes()
    return out


# ── 반각 진행 — 합성 타일 (마스터 2026-10-08 「오프닝·엔딩 공백·부호 반각」) ────────────────────────
# 🔴 지난 시도(08-21)가 막힌 곳: 레코드가 **글자당 2B 고정**이고 엔진이 글자마다 **16px 전진**한다 — 반각 코드를
#    쓸 길이 없다. 엔진을 안 고치고 넘는 길 = **줄을 비례 폭으로 한 장에 그린 뒤 16px 로 잘라, 조각마다 글리프 슬롯**
#    (PS1 ED3 안 B 와 같은 수). 한 칸에 반각 둘이 들어가고, 레코드 길이·정렬 규칙은 그대로다.
#    진행 폭: 공백·`. , ! ?` 8px · 한글·`…`·`～`·「」·전각 로마자 16px.
# ⚠ 조각이 원본 글리프와 **바이트까지 같으면**(맨 앞 글자들 — 위상 0) 새 슬롯을 안 먹고 그 코드를 쓴다 — 전각 로마자·
#    「」 처럼 원본 폰트가 가진 글자는 **원본 글리프 그대로**(모양이 화면마다 갈리지 않게), 합성 조각 속에서도 원본 글리프를 쓴다.
# ⚠ `…` 는 **전각 한 글자**, 점 셋은 **한국식 바닥**(글자 아랫줄) — 가운데 점은 안 된다(마스터, 전 기종 규칙).
TMAP = os.path.join(common.GAME_DIR, "hangul_tiles.json")
HALF = " .,!?"
BLANK_CODE = "　".encode("cp932")


def _bits_of(raw32):
    import numpy as np

    return np.unpackbits(np.frombuffer(raw32, np.uint8).reshape(16, 2), axis=1)


def _pack(bits):
    import numpy as np

    return np.packbits(bits.astype(np.uint8), axis=1).tobytes()


def _neo_bits(ch, ft, w):
    """Neo둥근모로 `ch` 를 그린 16×`w` 이진 배열. 잉크가 `w` 밖으로 나가면 실패한다."""
    import numpy as np
    from PIL import Image, ImageDraw

    im = Image.new("L", (16, 16), 0)
    ImageDraw.Draw(im).text((0, 0), ch, fill=255, font=ft)
    b = (np.array(im) >= 128).astype(np.uint8)
    assert not b[:, w:].any(), f"{ch!r}: 잉크가 {w}px 밖이다"
    return b[:, :w]


def ellipsis_bits(ft):
    """`…` — 점 셋을 셀 폭에 고르게, 높이는 폰트의 온점(= 글자 아랫줄, 한국식 바닥)."""
    import numpy as np
    from PIL import Image, ImageDraw

    dot = Image.new("L", (16, 16), 0)
    ImageDraw.Draw(dot).text((0, 0), ".", fill=255, font=ft)
    d = (np.array(dot) >= 128).astype(np.uint8)
    _ys, xs = np.nonzero(d)
    assert len(xs), "온점 글리프가 비었다"
    w = xs.max() - xs.min() + 1
    stamp = d[:, xs.min() : xs.max() + 1]
    ell = np.zeros((16, 16), np.uint8)
    span = 16 - 2 - w
    for k in range(3):
        x = 1 + round(span * k / 2)
        ell[:, x : x + w] |= stamp
    return ell


def sjis_index(code):
    """SJIS 2B → 글리프 인덱스(`font.sjis_of_index` 의 역). ⚠ EUC 경로(`font.jis_index`)는 `－`(전각 하이픈)처럼
    cp932 에만 있는 글자를 못 얻는다."""
    c1, c2 = code
    ku1 = (c1 - 0x81) * 2 + 1 if c1 <= 0x9F else (c1 - 0xC1) * 2 + 63
    if c2 >= 0x9F:
        ku, ten = ku1 + 1, c2 - 0x9E
    else:
        ku, ten = ku1, c2 - 0x3F - (1 if c2 >= 0x80 else 0)
    return (ku - 1) * 94 + (ten - 1)


class Composer:
    """줄 → 16px 조각들. 원본 `KANJI.FON` 글리프(전각 로마자·「」 …)는 원본 그대로 쓴다."""

    def __init__(self):
        from PIL import ImageFont

        self.ft = ImageFont.truetype(NEODGM, 16, layout_engine=ImageFont.Layout.BASIC)
        self.orig = bytes(common.extract("/OPENEND" + FONT16))
        self.ell = ellipsis_bits(self.ft)
        self.cache = {}

    def unit(self, ch):
        """`(진행 px, 16×진행 이진 배열)`"""
        import numpy as np

        if ch in self.cache:
            return self.cache[ch]
        if ch == " ":
            u = (8, np.zeros((16, 8), np.uint8))
        elif ch == "…":
            u = (16, self.ell)
        elif ch == "　":
            u = (16, np.zeros((16, 16), np.uint8))
        elif ord(ch) < 0x80:
            u = (8, _neo_bits(ch, self.ft, 8))
        else:
            try:
                idx = sjis_index(ch.encode("cp932"))
                assert font.sjis_of_index(idx) == ch.encode("cp932"), ch
                u = (16, _bits_of(self.orig[idx * GLYPH16 : (idx + 1) * GLYPH16]))
            except UnicodeEncodeError:
                u = (16, _neo_bits(ch, self.ft, 16))
        self.cache[ch] = u
        return u

    def tiles(self, text, width, left):
        """`[바이트 32 | None(공백)]` × `width` — `left` 가 None 이면 가운데, 아니면 그 칸 수만큼 왼쪽."""
        import numpy as np

        units = [self.unit(c) for c in text]
        total = sum(w for w, _ in units)
        cap = width * 16
        assert total <= cap, f"폭 초과 {total}>{cap}px: {text!r}"
        x = (cap - total) // 2 if left is None else min(left * 16, cap - total)
        canvas = np.zeros((16, cap), np.uint8)
        for w, b in units:
            canvas[:, x : x + w] |= b
            x += w
        out = []
        for k in range(width):
            t = canvas[:, k * 16 : k * 16 + 16]
            out.append(_pack(t) if t.any() else None)
        return out


def known_codes(smap, comp, lines):
    """`{조각 바이트: 2B 코드}` — 이미 코드가 있는 조각(굽힌 글자 · 원본 글리프 · 전각 공백)."""
    known = {}
    for idx, g in bake_font(smap).items():
        known.setdefault(g, font.sjis_of_index(idx))
    for t in lines:
        for ch in t:
            if ord(ch) >= 0x80 and ch != "…":
                try:
                    code = ch.encode("cp932")
                except UnicodeEncodeError:
                    continue
                idx = sjis_index(code)
                known.setdefault(comp.orig[idx * GLYPH16 : (idx + 1) * GLYPH16], code)
    return known


def tile_plan(needed, known, refresh=False, persist=True):
    """`{조각 hex: 슬롯}` — 정본이 있으면 그대로, 새 조각은 **덧붙이기만**(정렬 순서로 빈 슬롯에).

    ⚠ 조용히 안 늘린다 — 새 조각이 생기면 `--refresh` 를 요구한다(문안이 바뀌었다는 뜻이다).
    """
    old = {}
    if os.path.exists(TMAP):
        with open(TMAP, encoding="utf-8") as f:
            old = json.load(f)["syllables"]
    want = sorted({g.hex() for g in needed if g not in known})
    new = [h for h in want if h not in old]
    if new:
        assert refresh or not old, f"정본에 없는 조각 {len(new)}개 — `--refresh` 로 갱신할 것"
        with open(HMAP, encoding="utf-8") as f:
            char_slots = set(json.load(f)["syllables"].values())
        taken = set(old.values()) | char_slots
        pool = [i for i in font.free_slots("kanji") if i not in taken]
        assert len(new) <= len(pool), f"슬롯 부족 {len(new)}>{len(pool)}"
        for h in new:
            old[h] = pool.pop(0)
        if not persist:  # 🔬 `--as` 검증 치환 — 정본에 안 쓴다(슬롯 계획이 치환 문안에만 맞게 좁아지는 사고 방지)
            print(f"  🔬 검증용 임시 조각 슬롯 {len(new)}개(정본 불변)")
            return old
        with open(TMAP, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "_doc": "합성 타일(16×16 조각 32B hex) → KANJI.FON 슬롯 — 덧붙이기만 (커밋 정본, patch_title.py)",
                    "syllables": old,
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"  조각 슬롯 정본 갱신: {len(old)}개 (새 {len(new)}) → {TMAP}")
    return old


def encode_tiles(codes, nbytes):
    """조각 코드(각 2B) → 레코드 바이트 — 접두가 있으면 앞 2B 가 제어다."""
    body = b"".join(codes)
    out = (PREFIX + body) if nbytes == len(body) + 2 else body
    assert len(out) == nbytes, f"레코드 {len(out)}B ≠ {nbytes}B"
    return out


def encode(text, width, nbytes, left, plan=None):
    """레코드 바이트 `nbytes` — 접두가 있으면 앞 2B 가 제어(`\\x00\\x09` 등)다."""
    padded = pad(text, width, left)
    if plan is None:
        body = padded.encode("cp932")
    else:
        body = to_bytes(padded, plan)
    out = (PREFIX + body) if nbytes == len(body) + 2 else body
    assert len(out) == nbytes, f"레코드 {len(out)}B ≠ {nbytes}B: {text!r}"
    return out


def plan(raw):
    """`[(구간명, 인덱스, 파일오프셋, 원문, 폭, 접두여부)]` — 화면 순서가 아니라 저장 순서."""
    out = []
    for off, recs in runs(raw):
        name = LABELS[off]
        # 🔴 **폭은 레코드마다 다르다** — 같은 구간에 20칸·21칸이 섞여 있다(실측).
        #   구간 최댓값을 쓰면 20칸 자리에 21칸을 넣어 레코드 길이가 어긋난다.
        for i, (t, p, n) in enumerate(recs):
            out.append((name, i, p, t, len(t), n))
    return out


def check(raw):
    """항등 — 원문을 **원본의 정렬 그대로** 다시 인코딩해 바이트로 맞댄다.

    통과하면 레코드 경계·패딩·인코딩이 맞다는 뜻이다. 정렬은 유도하지 않고 읽어서 쓰므로
    이 검사는 「우리가 원본을 정확히 재현할 수 있는가」를 본다 — 그 위에서만 문안을 바꾼다.
    """
    rows = plan(raw)
    bad, kinds = [], {"center": 0, "left": 0}
    for name, i, p, t, width, nb in rows:
        mode, left = align_of(t, width)
        kinds[mode] += 1
        if mode == "center":
            body = t.strip("　")
            left = (width - len(body)) // 2
        if encode(t.strip("　"), width, nb, left) != raw[p : p + nb]:
            bad.append((name, i, p, t))
    print(
        f"  {'✅' if not bad else '❌'} 항등: 레코드 {len(rows)} · 어긋남 {len(bad)}"
        f"  (정렬 — 가운데 {kinds['center']} · 손으로 짠 자리 {kinds['left']})"
        + ("" if not bad else "  ← 패딩 규칙이나 인코딩이 틀렸다")
    )
    for name, i, p, t in bad[:8]:
        print(f"      {name} #{i} @0x{p:05X}  {t!r}")
    return len(bad)


def verify_tiles(dst, patch, glyphs):
    """🔴 쓴 것을 되읽는다 — 레코드 바이트와 글리프(두 사본)가 쓴 그대로인가. 되읽기는 쓴 직후 한 곳에서."""
    _f, mm = common.open_image(dst)
    bad = 0
    files = {p_: (l, s_) for p_, l, s_ in common.iso_files(mm)}
    raw2 = _load(mm)
    for p, rec in patch.items():
        if raw2[p : p + len(rec)] != rec:
            if bad < 6:
                print(f"      ❌ 레코드 0x{p:05X} 가 쓴 것과 다르다")
            bad += 1
    for path_in in (FONT16, "/OPENEND" + FONT16):
        lba, size = files[path_in]
        blob = bytes(common.read_extent(mm, lba, size))
        for idx, g in glyphs.items():
            if blob[idx * GLYPH16 : (idx + 1) * GLYPH16] != g:
                if bad < 6:
                    print(f"      ❌ {path_in} 글리프 {idx} 가 쓴 것과 다르다")
                bad += 1
    print(
        f"  {'✅' if not bad else '❌'} 되읽기: 레코드 {len(patch)} · 글리프 {len(glyphs)}×2 · 어긋남 {bad}"
    )
    return bad


def verify(dst, kr, smap):
    """🔴 **쓴 것을 되읽어 정본과 맞댄다** — 이 도구의 마지막 안전판.

    ⚠ 항등(`--check`)은 「원본을 재현할 수 있는가」를 보고, 이건 「우리 문안이 **제자리에**
    들어갔는가」를 본다. 둘은 다른 것을 지킨다 — 2026-08-21 에 줄 하나가 중간에 끼면서
    그 뒤가 통째로 한 칸씩 밀렸는데, 항등은 통과했고 **화면 캡처도 멀쩡해 보였다**
    (밀린 줄도 전부 제대로 된 한국어라 눈으로는 안 걸린다). 되읽기만이 잡는다.
    """
    rev = {sj.decode("cp932", "replace"): c for c, (sj, _i) in smap.items()}
    _f, mm = common.open_image(dst)
    raw2 = _load(mm)
    bad = 0
    for name, i, _p, t, _w, _nb in plan(raw2):
        # ⚠ 양쪽을 **전각으로 통일해** 맞댄다 — 정본엔 반각 공백과 전각 공백이 섞여 있고
        #   쓸 때 `widen` 을 거치므로, 그대로 비교하면 스태프롤 이름이 전부 오탐이 된다.
        got = "".join(rev.get(c, c) for c in t).strip("　")
        want = widen(kr[name][len(kr[name]) - 1 - i])
        if got != want:
            if bad < 6:
                print(f"      ❌ {name} #{i}\n         쓴것 |{got}|\n         정본 |{want}|")
            bad += 1
    print(
        f"  {'✅' if not bad else '❌'} 되읽기가 정본과 같다: 레코드 {len(plan(raw2))} · 어긋남 {bad}"
        + ("" if not bad else "  ← 색인이 밀렸다(저장은 역순이다)")
    )
    return bad


def main():
    common.verify_source()
    _f, mm = common.open_image()
    raw = _load(mm)
    if "--apply" not in sys.argv:
        sys.exit(1 if check(raw) else 0)

    if check(raw):
        raise SystemExit("항등이 깨졌다 — 문안을 넣기 전에 이걸 먼저 고친다")
    canon = os.path.join(common.GAME_DIR, "script", "title.json")
    with open(canon, encoding="utf-8") as f:
        kr = json.load(f)
    # ⚠ **여기 한 자리에서만** 조판을 적용한다 — 아래 `--as` 치환도 `verify` 되읽기도
    #   같은 문안을 보게 된다. 두 곳에서 각각 하면 되읽기 검사가 자기 자신을 통과시킨다.
    # 🔴 예전엔 여기서 `tighten`(부호 뒤 공백 제거)을 걸었다 — 전각 격자에선 부호 셀이 뒤 여백을 이미 만들었기 때문이다.
    #    반각 진행(합성 타일)에선 공백이 8px 로 제대로 그려지므로 **걸면 안 된다**(걸어서 「아니,어쩌면」이 붙었다, 2026-10-08).

    os.makedirs(BUILD, exist_ok=True)
    dst = os.path.join(BUILD, os.path.basename(common.ORIG_BIN))
    # 🔴 **늘 새로 뜬다 — 「없을 때만」이 아니다**(2026-08-27). 사본이 회차 사이에 남으면
    #    **낡은 도구 버전이 쓴 바이트가 그대로 산다.** 실측: 같은 소스로 지은 이미지가
    #    이어 지으면 `f361990d`, 새로 지으면 `b54e5533` 로 갈렸다 — 오늘 세션 동안 조판기를
    #    고쳐 가며 얹은 옛 문안이 남아 있었다. 제1원칙(빌드는 결정적)이 여기서 샌다.
    #    ⚠ 사본은 2초면 뜬다(484MB, 실측) — 체인 2분에 견주면 값이 안 나간다.
    print(f"  원본 복사 → {dst}")
    shutil.copy2(common.ORIG_BIN, dst)
    shutil.copy2(common.ORIG_CUE, os.path.join(BUILD, os.path.basename(common.ORIG_CUE)))

    _f2, mm2 = common.open_image(dst)
    files = {p_: (l, s_) for p_, l, s_ in common.iso_files(mm2)}
    mm2.close()
    _f2.close()
    lba, size = files[TITLE]

    # 저장 순서로 모아 **한 번에** 쓴다 — 섹터를 여러 번 여닫으면 EDC/ECC 를 그만큼 다시 짠다.
    # ⚠ **검증 전용 치환** — ED2 오프닝·엔딩은 게임을 끝까지 가야 보인다. 그래서 다른 구간의
    #   문안을 **ED1 오프닝 자리에 얹어** 눈으로 본다(PS1 의 `ED_OPENING_TEXT_AS` 와 같은 수법).
    #   🔴 배포 빌드에 켜지 않는다.
    as_arg = next((a[5:] for a in sys.argv if a.startswith("--as=")), None)
    if as_arg:
        # 🔴 치환본으로 **정본을 갱신하면 안 된다** — 슬롯 계획이 그 치환 문안에만 맞게
        #   좁아져(실측 346→280) 정상 빌드에서 글자가 사라진다. 2026-08-21 에 실제로 그랬다.
        assert "--refresh" not in sys.argv, "`--as` 와 `--refresh` 를 같이 쓰지 않는다"
        # `+` 로 여러 덩어리를 화면 순서대로 이어 붙인다 (ED2 오프닝은 두 덩어리다)
        parts, src, picked = as_arg.split("+"), [], []
        for q in parts:
            match = [k for k in kr if q in k]
            assert len(match) == 1, f"구간을 못 고르겠다 {q!r} → {match}"
            picked.append(match[0])
            src += kr[match[0]]
        match = [" + ".join(picked)]
        # 어느 구간 자리에 얹을지 고를 수 있다 — **도달 가능성**이 다르다.
        #   ED1 오프닝: 부팅하면 바로. ED2 오프닝: 타이틀에서 `right`→`a` (자기 그림을 쓴다).
        host = next((a_[7:] for a_ in sys.argv if a_.startswith("--host=")), "ED1 오프닝")
        host = next(k for k in kr if host in k)
        n = min(len(kr[host]), len(src))
        # ⚠ 폭이 다른 구간을 옮기면 넘칠 수 있다(21칸 → 20칸 자리). 검증용이니 **버린다.**
        w = min(len(t) for t, _o, _n in next(r[1] for r in runs(raw) if LABELS[r[0]] == host))
        drop = [t for t in src[:n] if len(widen(t)) > w]
        src = [t if len(widen(t)) <= w else "" for t in src[:n]]
        kr = dict(kr)
        kr[host] = src + [""] * (len(kr[host]) - n)
        if drop:
            print(f"     ⚠ 폭 넘어 버린 줄 {len(drop)} (치환 부작용): {drop[0][:24]}…")
        print(f"  🔬 검증 치환: {host} 자리에 {match[0]} {n}줄")

    smap = slot_plan(kr, refresh="--refresh" in sys.argv)
    print(f"  한글 슬롯 {len(smap)}자")

    comp = Composer()
    jobs = []  # (오프셋, 조각들, 레코드 길이, 구간, 화면 줄)
    for name, i, p, t, width, nb in plan(raw):
        # 🔴 **저장은 역순, 정본은 화면 순서**다(`dump_title` 이 뒤집어 내보낸다).
        #   그대로 색인하면 화면에 **결말부터** 나온다 — 2026-08-21 에 실제로 그렇게 나왔다.
        #   ⚠ 증상이 「깨짐」이 아니라 「순서가 이상함」이라 캡처를 대충 보면 넘어간다.
        line = kr[name][len(kr[name]) - 1 - i]
        mode, left = align_of(t, width)
        if mode == "center" or (name, len(kr[name]) - 1 - i) in FORCE_CENTER:
            left = None  # 줄마다 **비례 폭으로 다시 재서** 가운데(마스터 10-08)
        jobs.append((p, comp.tiles(line, width, left), nb, name, line))
    known = known_codes(smap, comp, [j[4] for j in jobs])
    needed = [g for _p, tl, _n, _a, _l in jobs for g in tl if g is not None]
    tmap = tile_plan(
        needed, known, refresh="--refresh" in sys.argv or bool(as_arg), persist=not as_arg
    )
    code_of = {bytes.fromhex(h): font.sjis_of_index(slot) for h, slot in tmap.items()}
    patch, expect_tiles = {}, set()
    for p, tl, nb, _name, _line in jobs:
        codes = []
        for g in tl:
            if g is None:
                codes.append(BLANK_CODE)
            else:
                codes.append(known[g] if g in known else code_of[g])
                if g not in known:
                    expect_tiles.add(g)
        patch[p] = encode_tiles(codes, nb)
    print(f"  합성 조각: 줄 {len(jobs)} · 새 슬롯 조각 {len(expect_tiles)}종 · 기존 글리프 재사용")

    lo, hi = min(patch), max(p + len(r) for p, r in patch.items())
    buf = bytearray(raw[lo:hi])
    for p, rec in patch.items():
        buf[p - lo : p - lo + len(rec)] = rec
    with open(dst, "r+b") as f:
        n = common.write_at(f, lba, size, lo, bytes(buf), label="TITLE.BIN 자막")
    # ⚠ **검증 전용** — 그림 파일명을 바꿔 다른 시퀀스의 배경을 띄운다. 길이가 같아 제자리다.
    dg2 = next((a_[6:] for a_ in sys.argv if a_.startswith("--dg2=")), None)
    if dg2:
        # `옛이름>새이름` 을 쉼표로. ⚠ **이름을 짝지어** 바꾼다 — 접두만 갈면 없는 파일을
        #   부른다(디스크의 `E1_ED*` 는 01·02·03·04·06·07… 로 번호가 비어 있다).
        n_sw = 0
        for pair in dg2.split(","):
            old, new = pair.split(">")
            assert len(old) == len(new), f"이름 길이가 다르다 {old}→{new}"
            i = bytes(buf).find(old.encode())
            assert i >= 0, f"{old} 을 못 찾았다"
            buf[i : i + len(new)] = new.encode()
            n_sw += 1
        print(f"     🔬 그림 파일명 {n_sw}개 교체")

    print(f"  자막 {len(patch)}줄 교체 · 0x{lo:05X}~0x{hi:05X} ({hi - lo:,}B, 섹터 {n})")

    # 폰트 — 계획대로 글리프를 굽는다. ⚠ `KANJI.FON` 은 두 자리에 있고 **둘 다** 고쳐야 한다
    #   (`/KANJI.FON` 타이틀 · `/OPENEND/KANJI.FON` 오프닝·엔딩 모듈). 한쪽만 고치면
    #   그 모듈에서만 글자가 깨지는데, 다른 쪽이 멀쩡해서 눈치채기 어렵다.
    glyphs = bake_font(smap)
    for h, slot in tmap.items():
        g = bytes.fromhex(h)
        if g in expect_tiles:
            glyphs[slot] = g
    with open(dst, "r+b") as f:
        for path_in in (FONT16, "/OPENEND" + FONT16):
            flba, fsize = files[path_in]
            for idx, g in glyphs.items():
                common.write_at(f, flba, fsize, idx * GLYPH16, g, label=f"{path_in} 글리프 {idx}")
            print(f"  폰트 {path_in}: 글리프 {len(glyphs)}자 구움")
    if verify_tiles(dst, patch, glyphs):
        raise SystemExit("되읽기가 쓴 것과 다르다 — 이 이미지를 쓰지 않는다")
    print(f"  → {dst}")


if __name__ == "__main__":
    # ⚠ **실패하면 산출물을 무효화한다**(레포 빌드 규율 — ps1 `build.py` 와 같은 장치).
    #   오늘 두 번 물렸다(2026-08-21): ① 글리프 정본에 없는 글자로 죽으면서 **원본 사본**을
    #   그대로 남겼고(=한글이 하나도 없는 이미지) ② numpy 없는 파이썬으로 죽으면서
    #   **자막만 쓰이고 폰트는 안 구운** 절반짜리를 남겼다. 둘 다 **파일은 멀쩡해 보인다** —
    #   에뮬에 올려 보고서야 이상한데, 그때는 원인이 빌드 실패였다는 걸 이미 잊는다.
    try:
        main()
    except BaseException:
        if "--apply" in sys.argv:
            for _n in (os.path.basename(common.ORIG_BIN), os.path.basename(common.ORIG_CUE)):
                _p = os.path.join(BUILD, _n)
                if os.path.exists(_p):
                    os.rename(_p, _p + ".failed")
            print(f"\n⚠ 실패 — 산출물을 *.failed 로 무효화했다 ({BUILD})")
        raise
