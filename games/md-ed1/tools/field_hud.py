"""필드 HUD 지명 뒷말(부근·입구) · 방위(동서남북) — 텍스트맵을 거치지 않는다.

    python3 tools/field_hud.py --check   # 여덟 자리가 원본과 같은 값인지 검산

## 왜 깨졌나 (마스터 지적 2026-09-27, 캡처 m39~m41)

필드에서 마을과 떨어져 있을 때 HUD 아래 칸에 뜨는 「엘아스타 부근」·「엘아스타 입구」와 동서남북은
`textmap/*.json` 을 안 거친다. 루틴(`$1EC20`)이 SJIS 코드를 **그대로** 레지스터에 찍거나(방위,
`move.w #$938C,d6` 류) ROM 리터럴 문자열을 복사한다(뒷말, `$1ED0C`=「付近」·`$1ED10`=「入口」).
`hangul.py` 가 번역이 안 쓰는 한자 칸을 한글로 갈아엎으면서, 이 여덟 코드가 우연히 가리키던 자리도
같이 갈렸다 — `0x8bdf`(近)는 「암」, `0x8cfb`(口)는 「할」이 됐다(부근/입구 첫 글자 자리 `0x9574`·
`0x93fc` 는 아직 아무도 안 써서 빈칸). 화면에 「엘아스타 암」·「엘아스타 할」로 뜬 게 그 결과다.

## 고치는 법

여덟 자리 전부 **2B 코드 하나를 다른 2B 코드로**(길이 불변) 바꾸는 것뿐이다 — 우리가 이미 쓰는
한글 코드(`textmap/hangul_codes.json`)로 갈아 끼운다. `부·근·입·구·동·서·남·북` 은 이미 다른
문안에서 쓰여 코드가 고정돼 있다(빌드가 없다고 실패시킨다 — `hangul.Charset`).

자리 여섯은 **즉값**(레지스터에 직접 찍는 명령의 피연산자)이고 둘은 **리터럴 문자열**(4B, 2글자)이다.
즉값 중 둘(`$1ECA4`·`$1ECC8`)은 **비교값**이다 — 위쪽에서 찍은 북/동 코드와 **똑같아야** 캐시
플래그(`$FF1FDE`, 다시 안 그려도 되는지 판정)가 안 흔들린다.

## 뒷말·방위 앞 공백 (마스터 지시 2026-09-27 밤 — 기종 공통 규칙)

이름과 뒷말·방위 사이에 원판엔 공백이 없다(「エルアスタ付近」 그대로 붙는다) — 마스터가 「입구·부근·
방위 앞은 띄운다」로 정해서 하나 넣는다. `movea.l a3,a2`(0x1EC6A, 2B) 로 출력 버퍼를 잡는 자리가
방위·뒷말 두 갈래 **모두의 공통 진입점**이라 여기 한 곳에서 반각 공백 하나(`$20`, 6px)를 써 넣으면
끝난다 — 이어지는 `lea.l $1ED10,a1`(6B)까지 합쳐 12B 가 필요한데 원래 자리는 8B 뿐이라, 통째로
`jmp <꼬리>`(6B, 남는 2B 는 죽은 자리로 둔다)로 옮기고 거기서 원래 두 명령 + 공백 쓰기를 한 뒤
0x1EC72(다음 원래 코드)로 되돌아간다. 코드 흐름 나머지는 안 건드린다.

## 박스 오른쪽 넘침 — 가운데 정렬을 왼쪽 정렬로 (마스터 지적 2026-09-27 밤, 캡처 m57)

「크루즈마을 부근」처럼 이름이 길면 뒷말이 박스 오른쪽을 뚫는다. 지명 표(`place_a`/`place_b`)는
12B 칸에 **가운데 정렬**로 굽는데($1ED14`, `$1EC20` 의 유일한 호출자 — 다른 곳에서 안 쓴다), 이 함수가
**런타임에 다시** 앞뒤 공백을 트림하고 원래 칸의 빈 칸 수(`총 공백 바이트 − 2) / 2`)만큼 **앞에** 공백을
채워 되돌린다. 원문(JP) 12B 기준으로 짠 공식이라 글자 수가 다른 한글 지명에서는 앞 여백이 이름마다
들쭉날쭉하고, 특히 **짧은 지명일수록 앞 여백이 커져 뒷말이 더 오른쪽에서 시작**한다.

**마스터 재판정(2026-09-27 밤 늦게)**: 왼쪽 정렬 대신 **가운데 정렬을 유지**한다(pc98·새턴 배너도 같은
방향). 왼쪽 정렬로 껐던 2026-09-27 밤 초판은 걷고, 공식의 **상수만** 고쳐 다시 가운데 정렬한다.

원래 식은 `d1`(그 12B 칸의 총 공백 바이트 수 — 이름이 짧을수록 크다) 하나로 `(d1−2)/2` 를 낸다.
`d1 = 12 − 이름폭(반칸 단위)` 이므로 이름만 12칸 상자에 넣고 중앙을 맞추는 식이다 — **뒷말은 아예
모르는 식**이라 뒷말을 붙이면 그만큼 오른쪽으로 밀려난다.

`$1EC20` 이 호출하는 순서(이름을 먼저 자리 잡고, 그 **뒤에** 방위·뒷말을 거리로 판정해 붙인다)를
바꾸지 않고도 고치는 법 — **뒷말·방위 중 가장 넓은 경우(뒷말 2글자 + 앞 공백, 반칸 5칸)를 상수에
미리 얹는다.** `(d1 − 2)/2` 를 `(d1 − 1)/2` 로: 상수 2 는 「12칸 상자에서 이름만 중앙」이고 상수 1 은
「이름 + 뒷말 최대 폭(5칸)을 합쳐 16칸 상자에서 중앙」과 같은 식이 된다(유도는 `d1=12−이름폭` 대입해
정리하면 나온다). 자리 표(place_a/b) **50개 전부**로 계산해 **밑돌지 않음을 확인**했다(가장 긴
5음절 지명 10곳 모두 `front_pad=0` — 왼쪽 정렬과 같은 안전한 값, 나머지는 0~3칸). 방위만 붙는(뒷말보다
좁은) 경우는 여백을 실제보다 넉넉히 잡아 **살짝 왼쪽 치우친 가운데** 가 된다 — 넘칠 위험은 없다.

`subq.b #2,d1`(0x1ED30, 원래 값)을 `subq.b #1,d1` 로 — 명령 모양은 원판과 완전히 같고 상수만
바꿨다(즉값 1바이트). 자리·크기 그대로라 트램펄린이 필요 없다. 박스 실제 폭(px)을 몰라 **반칸 5칸을
예비로 미리 까는 근사**다 — 정확한 폭을 알면 상수를 더 정밀하게 맞출 수 있다.

🔴 **정정(2026-09-28) — 위 `subq#1` 은 실제로는 아무 이름에도 영향이 없었다.** place_a/b 50개를
전부 시뮬레이션하면 `subq#2`(원본)과 `subq#1`(위 "고침")이 **완전히 같은 `front_pad`**를 낸다 —
한글은 전부 2바이트/음절이라 `d1`이 늘 짝수이고, 짝수 `d1`에서는 두 상수가 산술적으로 같아진다
(마스터가 실제로 "front_pad 는 이미 0, 더 당길 데가 없다"로 다시 잡은 자리와 같은 결론). 진짜
문제는 오프셋이 아니라 **폭**이었다 — 아래 절로 이어진다.

## 뒷말·방위를 콘덴스드로 압축 (마스터 확정 2026-09-28 — "입구 부근 동서남북도 콘덴스드로")

이름은 그대로 두고 **뒷말(부근/입구)·방위만** 갈무리 콘덴스드(`shared/fonts/Galmuri11-Condensed.bdf`,
한글 8px/자)로 다시 그려 **12px 코드 칸**으로 잘라 넣는다. 공백도 **별도 1바이트가 아니라 그림
안에 녹인다**(앞 공백 6px, 마스터 확정 — 처음 8px/꼬리0 은 우측 여유가 1px까지 줄어 근사 오차
안에 들어 반려, 7px 도 거쳐 최종 6px). 렌더러는 **글리프마다 폭 메타데이터가 없다**(표0 서술자가
리소스 전체에 [w,h] 하나 — `font.py` 확인) — 그래서 "글자를 좁게 그린다"는 통하지 않고, **칸
수 자체를 줄이는 것만** 통한다(09-28 낮에 이걸 몰라 "이름만 압축" 안이 한 번 엎어졌다).

- **부근/입구**: 「공백6px+두 글자(16px)」=22px 를 12px 칸 2개(24px)로 자른다 — 원래 공백(6px,
  1B)+두 글자(24px, 2코드)=30px 대비 **6px 절약**. 복사 루프(`$1ECE6`~`$1ECEC`, `move.b
  (a1)+,(a2)+` 4번 고정)는 **길이가 그대로**(4B=코드 2개)라 안 건드린다 — `$1ED0C`/`$1ED10`
  리터럴 **내용만** 새 코드 2개로 간다.
- **방위(동서남북)**: 「공백6px+한 글자(8px)」=14px — 칸(14px 폭 셀) 하나에 꼭 맞게 들어간다
  (칸을 넘는 2px는 다음 칸이 없어 버려져도 안전). 방위는 **리터럴 복사가 아니라 즉값**이다
  (`move.w #코드,d6/d3`) — 이미 코드 하나짜리 자리라 "칸을 나눈다"는 개념이 없고, 공백만
  흡수해 18px→12px(1코드)로 줄어든다.
- **가운데 정렬(K)**: 시뮬레이션(합성 데이터)으로는 `subq#1`(K=1)이 `subq#2`(K=2, 원본)와
  산술적으로 같아 보여 **한 번은 NOP**(K=0, 뺄셈 없음)까지 시도했다 — 그런데 **마스터 실기
  캡처(2026-09-28, `m-0928-cruise-iriguchi-overflow.png`)가 그 모델을 반증했다.** 박스
  내부를 픽셀 임계값으로 실측하니 **88px**(모델 가정 90px)·왼쪽 여백 **8px**(모델 예측
  6px)였고, K=0(front_pad=6px)에서는 **「구」가 박스 오른쪽에 그대로 닿아** 여유가 0px
  이었다(모델은 3px 남는다고 예측했었다). 보정한(88px·+2px 기준선) 모델로 K=0/K=1을
  50개×4경우 다시 돌리니 **K=0은 34/200 넘침**·**K=1은 0/200, 최소 여유 좌2·우5px**로
  갈렸다 — **결국 `subq.b #1,d1`(K=1, 09-27 밤에 처음 넣었던 그 상수)로 되돌아간다.**
  자리·크기는 그대로라 트램펄린 불필요. 🔴 **교훈**: 합성 글리프 폭·박스 경계는 실기 캡처
  없이 산술로만 믿으면 틀린다 — 여기서 두 번(이름 압축 폭 오해·K=0 오판) 물렸다.
- **트램펄린**: `space_tramp`(SPACE_SITE, 우리가 이미 둔 자리)의 `move.b #$20,(a2)+`(4B, 공백을
  별도로 쓰던 스텝)을 뺀다 — 공백이 이제 콘덴스드 그림 안에 있어서다. 18B→14B, `FIELD_HUD_RESERVE`
  (0x20=32B) 예산 안이라 build.py 쪽 구간 상수는 안 바꾼다.
- **코드 배정**: 합성 글리프 8개(부근용 2·입구용 2·방위용 4)는 진짜 문자가 아니라 **PUA(U+E000~)
  자리표시**를 키로 써서 `hangul.py`의 기존 파이프라인(코드 배정·표0 굽기)을 그대로 탄다 —
  `hangul.CUSTOM_GLYPHS`에 채움 행렬만 등록하면 `glyph_fill()`이 BDF 대신 그걸 돌려준다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hangul

SPACE_SITE = 0x1EC6A  # movea.l a3,a2 (2B) + lea.l $1ED10,a1 (6B) — 방위·뒷말 공통 진입점
SPACE_SITE_LEN = 8
SPACE_RESUME = 0x1EC72  # 원래 흐름으로 되돌아갈 자리(공백 삽입 다음 원래 명령)
SPACE_A1 = 0x1ED10  # lea 가 원래 가리키던 곳("입구") — 트램펄린에서 복제한다
SPACE_TRAMP_LEN = 14  # movea(2)+lea(6)+jmp(6) — 공백은 이제 콘덴스드 그림 안에 있어 별도 write 없음

ALIGN_SITE = 0x1ED30  # subq.b #2,d1(원본) — 가운데 정렬 앞 공백 계산의 상수. 즉값 1바이트만 바꾼다
ALIGN_PATCH = b"\x53\x01\xe2\x09"  # subq.b #1,d1(="K=1") + lsr.b #1,d1(원본 그대로)

# (자리, 글자) — 즉값 이동/비교 명령의 피연산자 2B. 전부 같은 함수(`$1EC20`) 안. `글자`는
# PUA 코드를 찾는 키(아래 DIR_PUA)일 뿐, 실제로 이 글자 하나짜리 코드를 굽지는 않는다.
DIRECTIONS = [
    (0x1EC3C, "서", "move.w #서,d6 — 서쪽 기본값"),
    (0x1EC46, "동", "move.w #동,d6 — 동쪽"),
    (0x1EC5A, "북", "move.w #북,d3 — 북쪽 기본값"),
    (0x1EC64, "남", "move.w #남,d3 — 남쪽"),
    (0x1ECA4, "북", "cmpi.w #북,d3 — 북/남 갈림(캐시 플래그), 위 북 값과 같아야 한다"),
    (0x1ECC8, "동", "cmpi.w #동,d6 — 동/서 갈림(캐시 플래그), 위 동 값과 같아야 한다"),
]
# (자리, 낱말) — 4B 리터럴(콘덴스드 슬라이스 코드 2개). 出典 위치는 표 0x1ED0C(付近)·0x1ED10(入口).
SUFFIX = [
    (0x1ED0C, "부근", "「부근」— 마을과 떨어졌을 때"),
    (0x1ED10, "입구", "「입구」— 마을 그 칸일 때"),
]

# ── 콘덴스드 합성 글리프 — PUA(U+E000~) 자리표시로 hangul.py 기존 파이프라인을 그대로 탄다 ──
CONDENSED_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11-Condensed.bdf"
CONDENSED_ADVANCE = 8  # 콘덴스드 한글 1자 전진폭(BDF DWIDTH 실측, 전부 8)
SPACE_PX = 6  # 압축분 앞 공백(마스터 확정 2026-09-28 — 8px/꼬리0 은 우측여유 1px라 반려, 최종 6px)
CELL = hangul.CELL  # 14
PITCH = 12

PUA_SUFFIX = {"부근": ["", ""], "입구": ["", ""]}
PUA_DIR = {"동": "", "서": "", "남": "", "북": ""}

_cbdf_cache: dict | None = None


def _load_condensed() -> dict:
    global _cbdf_cache
    if _cbdf_cache is not None:
        return _cbdf_cache
    raw = {}
    lines = CONDENSED_BDF.read_text(encoding="utf-8", errors="replace").split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("ENCODING "):
            code = int(lines[i].split()[1])
            j = i
            while not lines[j].startswith("BBX"):
                j += 1
            bw, bh, bx, by = map(int, lines[j].split()[1:5])
            while lines[j].strip() != "BITMAP":
                j += 1
            rows = []
            for r in lines[j + 1 : j + 1 + bh]:
                r = r.strip()
                v = int(r, 16) if r else 0
                nb = len(r) * 4
                rows.append([(v >> (nb - 1 - x)) & 1 for x in range(bw)])
            raw[chr(code)] = (bw, bh, bx, by, rows)
            i = j + bh
        i += 1
    _cbdf_cache = raw
    return raw


def _condensed_strip(text: str, space_px: int) -> list[list[int]]:
    """「공백 + text」를 이어 그린 연속 채움 비트맵(높이 CELL, 폭 = space_px + 8*len(text))."""
    bdf = _load_condensed()
    _bw, _bh, _bx, _by, _ = bdf.get("가", (0, 0, 0, 0, []))
    ref = _by + _bh
    width = space_px + CONDENSED_ADVANCE * len(text)
    grid = [[0] * width for _ in range(CELL)]
    top = 1
    for k, ch in enumerate(text):
        bw, bh, bx, by, rows = bdf[ch]
        y0 = top + (ref - (by + bh))
        x_off = space_px + k * CONDENSED_ADVANCE
        for y in range(bh):
            ry = y0 + y
            if not 0 <= ry < CELL:
                continue
            for x in range(bw):
                rx = x_off + x + bx
                if 0 <= rx < width:
                    grid[ry][rx] = grid[ry][rx] or rows[y][x]
    return grid


def _slice_multi(strip: list[list[int]]) -> list[list[list[int]]]:
    """12px 피치 · 14px 폭 창으로 자른다 — 뒷말(부근/입구)용, 코드 여러 개."""
    width = len(strip[0])
    n = -(-width // PITCH)
    out = []
    for k in range(n):
        x0 = k * PITCH
        g = [[0] * CELL for _ in range(CELL)]
        for y in range(CELL):
            for x in range(CELL):
                sx = x0 + x
                if 0 <= sx < width:
                    g[y][x] = strip[y][sx]
        out.append(g)
    return out


def _slice_single(strip: list[list[int]]) -> list[list[int]]:
    """칸 하나(0~13열)만 잘라낸다 — 방위용. 코드 하나짜리 즉값이라 여러 칸으로 못 나눈다
    (내용을 칸 폭(14px) 안에 들어오게 미리 맞춘다 — `SPACE_PX+8` = 14, 정확히 한 칸)."""
    g = [[0] * CELL for _ in range(CELL)]
    width = len(strip[0])
    for y in range(CELL):
        for x in range(CELL):
            if x < width:
                g[y][x] = strip[y][x]
    return g


_registered = False


def _ensure_custom_glyphs() -> None:
    """합성 글리프 8개를 `hangul.CUSTOM_GLYPHS`에 등록 — 코드 배정·표0 굽기는 기존 길을 탄다."""
    global _registered
    if _registered:
        return
    for word, puas in PUA_SUFFIX.items():
        slices = _slice_multi(_condensed_strip(word, SPACE_PX))
        if len(slices) != len(puas):
            raise SystemExit(f"뒷말 「{word}」 슬라이스 수가 예상과 다르다: {len(slices)} ≠ {len(puas)}")
        for pua, g in zip(puas, slices, strict=True):
            hangul.CUSTOM_GLYPHS[pua] = g
    for ch, pua in PUA_DIR.items():
        hangul.CUSTOM_GLYPHS[pua] = _slice_single(_condensed_strip(ch, SPACE_PX))
    _registered = True


def space_tramp(at: int) -> bytes:
    """트램펄린 본체 — 원래 명령 둘(공백 쓰기는 이제 없다), 그리고 원래 흐름으로 복귀."""
    b = bytearray()
    b += struct.pack(">H", 0x244B)  # movea.l a3,a2
    b += struct.pack(">H", 0x43F9) + struct.pack(">I", SPACE_A1)  # lea.l $1ED10.l,a1
    b += struct.pack(">H", 0x4EF9) + struct.pack(">I", SPACE_RESUME)  # jmp $1EC72.l
    assert len(b) == SPACE_TRAMP_LEN, len(b)
    return bytes(b)


def plan(cs, tramp_at: int) -> list[tuple[str, int, bytes]]:
    """`cs` 는 `hangul.Charset` — 순환 임포트를 피해 타입은 안 박는다."""
    _ensure_custom_glyphs()
    out = []
    for i, (addr, ch, _why) in enumerate(DIRECTIONS):
        out.append((f"field-hud-dir:{i}", addr, cs.encode_char(PUA_DIR[ch])))
    for i, (addr, word, _why) in enumerate(SUFFIX):
        body = b"".join(cs.encode_char(pua) for pua in PUA_SUFFIX[word])
        out.append((f"field-hud-suffix:{i}", addr, body))
    out.append(("field-hud-space-tramp", tramp_at, space_tramp(tramp_at)))
    out.append(
        (
            "field-hud-space-site",
            SPACE_SITE,
            struct.pack(">H", 0x4EF9) + struct.pack(">I", tramp_at),
        )
    )
    out.append(("field-hud-align", ALIGN_SITE, ALIGN_PATCH))
    return out


def chars() -> set[str]:
    """이 패치가 쓰는 글자 — `collect_chars()` 가 다른 문안과 상관없이 늘 구워 둔다.
    실제로 굽는 건 합성 글리프(PUA)뿐이다 — `_ensure_custom_glyphs()`가 비트맵을 채워야
    `needs_glyph()`가 코드를 배정할 게 있다."""
    _ensure_custom_glyphs()
    return {p for puas in PUA_SUFFIX.values() for p in puas} | set(PUA_DIR.values())


ORIG = {
    0x1EC3C: b"\x90\xbc",  # 西
    0x1EC46: b"\x93\x8c",  # 東
    0x1EC5A: b"\x96\x6b",  # 北
    0x1EC64: b"\x93\xec",  # 南
    0x1ECA4: b"\x96\x6b",  # 北
    0x1ECC8: b"\x93\x8c",  # 東
    0x1ED0C: b"\x95\x74\x8b\xdf",  # 付近
    0x1ED10: b"\x93\xfc\x8c\xfb",  # 入口
    SPACE_SITE: b"\x24\x4b\x43\xf9\x00\x01\xed\x10",  # movea.l a3,a2 + lea.l $1ed10,a1
    ALIGN_SITE: b"\x55\x01\xe2\x09",  # subq.b #2,d1 + lsr.b #1,d1
}


def check(d: bytes) -> None:
    for addr, orig in ORIG.items():
        got = d[addr : addr + len(orig)]
        if got != orig:
            raise SystemExit(f"필드 HUD 자리 {addr:#x} 가 예상과 다르다: {got.hex()} ≠ {orig.hex()}")
    print(f"  필드 HUD 뒷말·방위 — 여덟 자리 원본과 일치 ({len(ORIG)}곳)")


if __name__ == "__main__":
    check(common.rom())
