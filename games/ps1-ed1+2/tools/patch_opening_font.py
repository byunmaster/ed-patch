"""ED1 오프닝(OPEN1.EXE) 한글화 — 임베드 한글폰트 + 정발판 내레이션 50줄. (완료)

오프닝은 PS1 BIOS 일본어 폰트(0xBFC66000, 16×15/30B)를 렌더함수 0x8001BE24로
그린다(글리프=base+index×30). BIOS는 수정불가라 임베드 폰트로 대체:

  1) Galmuri9 네이티브 15행(30B) 글리프를 행-마스크 압축해 파일 0x15CE0에 임베드.
  2) PC0 후킹 디코더 스텁(0x80025414, 저작권문자열 자리)이 자유RAM FONT_RUNTIME
     (0x80080000)에 전개 후 원PC0(0x80021D50) 점프. (게임 힙클리어보다 먼저 대피)
  3) 폰트베이스 획득부(0x8001BE84) → lui/addiu s0 = FONT_RUNTIME 리다이렉트.
     렌더는 원본 그대로. 모든 문자(한글·부호·숫자·공백)를 2바이트 한자슬롯으로 통일
     (렌더가 2바이트 전용이라 1바이트 \\x20은 줄을 어긋냄).
  4) 내레이션 50줄을 저주소 텍스트 영역(0x974~0xEEE, 1402B) 내 재packing + 포인터 갱신.
     ⚠ 스크립트(0x145A0)가 주소 범위로 text(0x8001xxxx)/command(0x80026Dxx)를 구분
     → 고주소 재배치 금지(검은화면). 각 줄 끝 0x0A 필수(필드클리어 — 없으면 잔상).
  5) 전각 advance 4→3 패치(0x13370/0x13750). 공백·부호는 반각 2유닛 — 필드 64유닛.

텍스트는 정발판(originals/kr/dos-ed1/OPENING.EXE) 원문 우선, JP 전용부만 정발 어투 신규 번역.
상세 여정: docs/devlog.md, 핸드오프: docs/ed1-status.md.
전제: build.py(베이스) 후 이 스크립트 적용 → work/Eiyuu Densetsu (KR).bin (제자리 갱신).
"""

import hashlib
import json
import os
import shutil
import string
import struct
import sys

import hangul_font
import hangul_map as H
import numpy as np
from common import BUILD_DIR, extract, write_cue, write_user_data
from derive_text import off_pairs
from font_map import JIS_KANJI1_INDEX

OP_LBA, OP_SIZE = 69, 96256
TADDR = 0x80010000
SRC = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
DST = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"  # 제자리 갱신
DST_CUE = f"{BUILD_DIR}/Eiyuu Densetsu (KR).cue"

# 안전 위치: 에뮬 RAM 덤프로 오프닝 런타임 내내 0인 영역 확인(0x800254D4~0x8002634C,
# 3704B). 그 앞 0x8002546A~는 OPEN1이 런타임 작업버퍼로 씀 → 폰트 놓으면 셋업 깨짐.
# 폰트는 파일에 실려 로드시 FONT_LOAD로 온다(로더는 BSS 없음 b_size=0 → 클리어 안 함).
# 하지만 OPEN1 게임코드가 그 tail(힙/작업구조체)을 재사용/클리어 → 폰트 소실.
# 그래서 PC0(진입점) 첫 코드로 폰트를 자유 RAM(FONT_RUNTIME)으로 복사해 살린다.
# 폰트 소스: setjmp/초기 오염 영역(0x800254A4~0x800254DC, 0x80025410)을 피해 0x800254E0에.
# 압축 폰트 소스: 안전 0영역(참조 0건, 어제 폰트 위치)에 행-마스크 압축본을 둔다.
# 스텁이 이걸 자유 RAM에 네이티브 30B로 푼다. (원본 30B raw는 5730B로 안전영역 초과)
COMP_FONT_FILE_OFF = 0x15CE0  # RAM 0x800254E0 (안전 0영역·OPEN1 미참조)
COMP_FONT_LOAD = TADDR + (COMP_FONT_FILE_OFF - 0x800)  # 0x800254E0
COMP_FONT_MAX = 0x16CC0 - COMP_FONT_FILE_OFF  # 안전영역 상한(뒤쪽 참조영역 전)
FONT_RUNTIME = 0x80080000  # 자유 RAM(오프닝 내내 0, PC0 클리어 0x80026F30~ 밖) — 디코더 출력
# 내레이션은 저주소 텍스트 영역(0x80010174~0x800106ED, 1402B) 내 재packing으로 해결(고주소 재배치 불필요).
# 영역 앞(0x938~ 포인터배열)·뒤(0xEF0~ TIM명, 참조 중)는 확장 불가 — 예산 고정. ⚠ 스크립트(0x145A0)가
# text_ptr(0x8001xxxx)와 command_ptr(0x80026Dxx)를 주소 범위로 구분하므로, 줄을 고주소
# (0x80082000)로 옮기면 command로 오인돼 검은화면(과거 RELOCATE_OVERFLOW 실패의 진짜 원인).
GLYPH = 30  # 16×15 네이티브(BIOS 한자와 동일 셀). 원본 렌더 그대로 → 크기·행수·shadow 패치 불필요
DRAW_ROWS = 15
# ⚠ 오프닝·엔딩만 **Neo둥근모 16px** 이다 — 인게임 대사는 그대로 Galmuri11(11×11 셀).
# 원작도 이 자리는 PS1 BIOS 한자폰트(16×15)를 썼으니 **원작 크기로 돌아가는 것**이다.
# 셀(16×15)에 잉크 13행이 여유 있게 들어가고, 예산은 행 사전 코덱이 열어 줬다
# (옛 행-그대로 코덱으로는 5,472B 로 탈락했다 — `compress_font_dict` 주석).
NEODGM_TTF = os.path.join(hangul_font.REPO_ROOT, "shared", "fonts", "neodgm.ttf")
GALMURI_BDF = hangul_font.GALMURI11_BDF.replace("Galmuri11", "Galmuri9")  # 압축 비교용으로만 남긴다
# Galmuri9 dy=1 → 잉크 3~11행(위3/아래3 여백, 무잘림). 압축 3584B로 안전영역에 여유.
GALMURI_DY = 1
# 폰트는 Galmuri9 전용 BDF. neodgm(둥근모꼴 계열 16px)은 **공간이 안 나와서 기각**이다.
# ⚠ 예전 주석이 「도트가 거칠어 기각」이라고만 적어 둬서 2026-08-21 에 「advance 를 원본
# 16px 로 되돌리고 네이티브로 쓰면 되지 않나」로 한 번 헛돌았다 — **1순위 사유는 크기다.**
# 214자 실측(압축 후, 안전영역 COMP_FONT_MAX = 4064B):
#     Galmuri9      3498B ✅      neodgm 12px  4320B ❌
#     neodgm 15px   5142B ❌      neodgm 16px  5472B ❌ (35% 초과)
# 셀(16×15)에 **수납은 된다**(neodgm 16px 잉크 13행). 안 되는 건 압축 블롭이다 — 16px 도트는
# 잉크가 많아 행-마스크 압축이 안 먹는다. 영역은 못 넓힌다(앞 포인터배열·뒤 참조 중 TIM명).
# 도트가 거친 건 그 다음 문제다: 12px 로 줄이면 16px 설계의 그리드가 깨져 받침이 뭉갠다.
# 결론만 남기고 코드는 지웠다 — YAGNI.
STUB_FILE_OFF = 0x15C14  # 저작권 문자열 자리(게임 미사용, 어제 스텁 검증). RAM 0x80025414 = 디코더.
STUB_RAM = TADDR + (STUB_FILE_OFF - 0x800)  # 0x80025414
ORIG_PC0 = 0x80021D50

# ── 게임별 설정 — 동영상 EXE 넷은 **같은 프로그램의 다른 빌드**다 (2026-08-16) ──────
# 넷이 내레이션 164줄을 통째로 한 벌씩 들고 각자 **자기 몫만** 화면에 낸다(읽기 BP 실측:
# OPEN1 이 도는 동안 ED2 오프닝 자리 읽기 0건 / 대조군 ED1 자리 179건). 그래서 파일마다
# **자기 슬라이스만** 손댄다 — 죽은 사본까지 쓰면 재packing 예산과 포인터 위험만 는다.
#
# ⚠ **주소를 손으로 적지 않는다.** 여섯 앵커는 `check_movie_anchors.derive` 가 시그니처로
# 뽑고, 그 도출기는 OPEN1 하드코딩 값을 재현하는 것으로 스스로를 검증한다. 여기 적는 건
# **도출로 안 나오는 것**뿐이다 — 어느 textmap 을 쓰는지, 보조 풀이 어디인지.
#
# 보조 풀 = CD 오류 문자열 자리. 읽기 실패 경로에서만 참조되고 그 시점엔 게임이 이미
# 죽으므로 본문 공간으로 돌린다. ⚠ 선두 4B 는 0으로 남겨 빈 문자열이 되게 한다.
# OPEN1 과 OPEN2 는 배치가 **정확히 +4 시프트**다(0x864/0x8CC/0x938 → 0x868/0x8D0/0x93C).
# ⚠ **보조 풀 자리도 도출한다** — 손으로 적으면 파일이 늘 때마다 틀린다. CD 오류 문자열
# 둘을 원문으로 찾고 포인터 테이블 시작을 그 뒤 0런 끝으로 잡는다. 도출기는 OPEN1
# 하드코딩 값(0x864/0x8CC/0x938)을 재현하는 것으로 스스로를 검증한다(`game_cfg`).
#
# `delta` = 텍스트 배치 델타(OPEN1 기준). textmap 의 오프셋 키는 OPEN1 배치라 이만큼
# 더해야 그 파일의 자리가 된다 — 문자열 일치로 실측했다(56/59).
# `font_ram` = 스텁이 폰트를 푸는 자유 RAM. ⚠ **파일마다 다시 재야 한다.**
# 오프닝(0x80080000)은 BIOS 가 **로드 시점에만** 쓰지만, 엔딩은 그 자리를 실제로 쓴다 —
# END1 을 0x80080000 로 구웠더니 화면 글자가 통째로 **네모 덩어리**가 됐다(RAM 이 0x6A 로
# 차 있었다, 2026-08-16 실측). 엔딩은 0x80100000 을 쓴다(쓰기 BP 0건 · 대조군 4,096건).
GAMES = {
    "OPEN1": {"lba": 69, "cls": "opening", "delta": 0, "font_ram": 0x80080000},
    "OPEN2": {"lba": 116, "cls": "opening_ed2", "delta": 0, "font_ram": 0x80080000},
    "END1": {
        "lba": 163,
        "cls": "ending_ed1",
        "delta": 8,
        "font_ram": 0x80100000,
        "blocks": ((0x1260, 0x1520), (0x17644, 0x1766C)),
        "spare": (0x1B84, 0x1E84),
    },
    "END2": {
        "lba": 210,
        "cls": "ending_ed2",
        "delta": 4,
        "font_ram": 0x80100000,
        "blocks": ((0x1B80, 0x1E80), (0x1752C, 0x17554)),
        "spare": (0x125C, 0x1508),
    },
}
POOL_KEYS = ("CD-ROMからのファイルサーチ", "CD-ROMからのファイル読み込み")


def _derive_pools(buf):
    """(err, err2, ptab) — CD 오류 문자열 둘과 포인터 테이블 시작."""
    e1 = buf.find(POOL_KEYS[0].encode("cp932"))
    e2 = buf.find(POOL_KEYS[1].encode("cp932"))
    assert e1 > 0 and e2 > e1, "CD 오류 문자열을 못 찾았다 — 보조 풀 도출 실패"
    k = buf.find(b"\x00", e2)
    while k < len(buf) and buf[k] == 0:
        k += 1
    return e1, e2, k


SIZE = 96256
# 스텁·폰트는 안전 0런 기준의 **상대 위치**로 잡는다(OPEN1 실측값에서 유도).
STUB_REL = 0x15C14 - 0x15C69  # 저작권 문자열 자리 — 0런보다 앞이다
FONT_REL = 0x15CE0 - 0x15C69


def _tm_path(cls):
    return os.path.join(os.path.dirname(__file__), "..", "textmap", f"{cls}.json")


def game_cfg(name):
    """게임 설정 + 도출 앵커. OPEN1 은 하드코딩 값과 대조해 도출기를 검증한다."""
    import check_movie_anchors as A

    g = dict(GAMES[name])
    buf = bytes(extract(g["lba"], SIZE))
    g["err"], g["err2"], g["ptab"] = _derive_pools(buf)
    if name == "OPEN1":
        assert (g["err"], g["err2"], g["ptab"]) == (0x864, 0x8CC, 0x938), "보조 풀 도출 실패"
    a = A.derive(buf)
    if name == "OPEN1":
        for k, v in A.KNOWN.items():
            if k in a:  # `stub`·`font` 는 도출값이 아니라 0런 상대 위치로 잡는다(아래)
                assert a[k] == v, f"앵커 도출 실패 {k}: {a[k]:X} != {v:X}"
    run_off, run_len = a["zero_run"]
    g.update(a)
    g["stub_off"] = run_off + STUB_REL
    g["font_off"] = run_off + FONT_REL
    # 꼬리 여유 16B. ⚠ 0런은 **실측**이고(넷 다 4,203B) 폰트 크기는 assert 로 막히므로
    # 이 값은 안전 마진일 뿐이다. END1 은 내레이션이 59줄이라 음절이 가장 많아 예산이
    # 빠듯하다 — 32B 로는 스태프롤 로마자 한 글자(G)가 안 들어갔다(2026-08-16 실측).
    g["font_max"] = (run_off + run_len) - g["font_off"] - 0x10
    return g


def _ellipsis_bits(ft):
    """말줄임표를 **셀 폭에 고르게** 다시 그린다.

    폰트의 `…` 는 점 셋이 가운데 몰려 있어 한 글자처럼 뭉쳐 보인다 — 유저는 온점 셋(`...`)
    쪽이 읽힌다고 했다(2026-08-22). 그런데 `...` 로 통일하면 **새턴이 깨진다**(16px 고정
    격자라 점마다 한 칸을 먹어 16px 씩 벌어진다). 그래서 **표기는 `…` 하나로 두고 그림만**
    온점 셋처럼 벌린다 — 두 판이 같은 문안을 쓰면서 둘 다 읽힌다.

    ⚠ 점의 **모양·높이는 폰트의 온점에서 가져온다**. 손으로 찍으면 본문 온점과 굵기·기준선이
    어긋나 그 줄만 다른 폰트처럼 보인다.
    """
    from PIL import Image, ImageDraw

    dot = Image.new("L", (16, DRAW_ROWS), 0)
    ImageDraw.Draw(dot).text((0, 0), ".", fill=255, font=ft)
    d = (np.array(dot) >= 128).astype(np.uint8)
    ys, xs = np.nonzero(d)
    assert len(xs), "온점 글리프가 비었다"
    w = xs.max() - xs.min() + 1
    stamp = d[:, xs.min() : xs.max() + 1]
    out = np.zeros((DRAW_ROWS, 16), np.uint8)
    # 셀 좌우에 1px 만 남기고 점 셋을 고르게 — `.` 하나 폭이 2px 이면 1 / 7 / 13 이 된다.
    span = 16 - 2 - w
    for k in range(3):
        x = 1 + round(span * k / 2)
        out[:, x : x + w] |= stamp
    return out


def gen_glyphs(chars):
    """렌더 단위 → GLYPH바이트(16×DRAW_ROWS) 글리프 (**Neo둥근모 16px 네이티브**).

    단위는 1글자(한글·부호)이거나 **로마자 2글자**다 — 로마자가 8px 라 둘이 한 셀에 맞는다.

    ⚠ **축소하지 않는다.** 16px 설계를 줄이면 정수배가 아니라 획이 서로 먹어 받침이
    뭉갠다(`오`·`스` 는 멀쩡한데 `영`·`웅`·`많`·`읽` 이 무너진다). 16px 그대로 찍으면
    잉크가 13행이라 셀(16×15)에 그냥 들어간다. 기준은 `shared/fonts/README.md`.
    ⚠ 레이아웃 엔진을 BASIC 으로 못 박는다 — Raqm 유무로 배치가 달라져 빌드가 환경을 탄다.
    """
    from PIL import Image, ImageDraw, ImageFont

    ft = ImageFont.truetype(NEODGM_TTF, 16, layout_engine=hangul_font.BASIC_LAYOUT)
    out = {}
    for ch in chars:
        im = Image.new("L", (16, DRAW_ROWS), 0)
        # ⚠ 짝을 못 찾은 로마자 한 글자(8px)는 **셀 가운데**로 민다 — 왼쪽에 붙이면 뒤에만
        #   8px 가 비어 「고작 6 살.」 처럼 한쪽으로 벌어진다.
        dx = 4 if len(ch) == 1 and ch in PAIRABLE else 0
        ImageDraw.Draw(im).text((dx, 0), ch, fill=255, font=ft)
        bits = (np.array(im) >= 128).astype(np.uint8)
        if ch == "…":
            bits = _ellipsis_bits(ft)
        if not bits.any() and not ch.isspace():
            print(f"경고: {ch!r} 글리프 없음")
        assert ft.getlength(ch) <= 16, f"{ch!r} 이 셀(16px)을 넘는다 — {ft.getlength(ch)}px"
        out[ch] = np.packbits(bits, axis=1).tobytes()  # DRAW_ROWS*2 = GLYPH
    return out


HALF_BIT = 1 << 15  # 마스크 최상위 = 반각 글리프(행마다 1B만 저장)


def compress_font(glyph_list):
    """행-마스크 압축: 글리프당 [2B 마스크(LE) + 비영 행들].
    마스크 비트 r(LSB=행0, r<15)=행 r이 비지 않음. 빈 행(0x0000)은 저장 생략 → 디코더가 0으로 채움.

    **비트 15 = 반각**(2026-08-16). 글리프의 오른쪽 바이트가 모든 행에서 0이면 왼쪽 1B만
    저장한다 — 폭 8px 이하 글자(로마자·부호, 그리고 Galmuri9 에선 한글도 상당수)가 여기
    해당해 **687B 가 빠진다**(END1 실측: 221자 중 84자). 행 카운터는 15라 비트 15는 절대
    소비되지 않으므로 플래그로 쓸 수 있다.
    ⚠ 저장은 **왼쪽 바이트 그대로**다 — 디코더가 `lbu`+`sh` 로 되돌리면 리틀엔디언이
    [왼쪽, 0] 으로 놓아 준다(시프트 금지)."""
    out = bytearray()
    for gb in glyph_list:
        rows = [gb[r * 2 : r * 2 + 2] for r in range(15)]
        half = all(row[1] == 0 for row in rows)
        mask = HALF_BIT if half else 0
        for r in range(15):
            if rows[r] != b"\x00\x00":
                mask |= 1 << r
        out += struct.pack("<H", mask)
        for r in range(15):
            if rows[r] != b"\x00\x00":
                out += rows[r][:1] if half else rows[r]
        # ⚠ **2바이트 정렬을 지킨다.** 다음 글리프의 마스크는 `lhu` 로 읽는데 MIPS 의
        # `lhu` 는 홀수 주소에서 **주소 예외**로 죽는다 — 반각 글리프의 저장 행이 홀수면
        # 여기서 한 바이트를 채워야 한다(2026-08-16 실측: 안 채웠더니 검은 화면 + 예외).
        if len(out) & 1:
            out += b"\x00"
    return bytes(out)


# 내레이션 50줄 — 정발판(originals/kr/dos-ed1/OPENING.EXE) 원문 우선.
# JP(PS1)에만 있고 정발에 없는 부분(다섯 나라 11~13행·몬스터 습격 확장 26~40행)은
# 정발 어투로 새로 번역.
# 표기 규칙(유저 확정): 쉼표 뒤 공백 없음(쉼표도 전각 슬롯이라 공백까지 두면 여백 과대),
# 문장 끝 마침표 일관 추가. 줄 폭은 필드 64유닛(전각 3·반각 2) — units() 로 잰다.
# 바이트 예산이 영역(0x974~0xEEE, 1402B)에 거의 꽉 참(빌드 출력의 '여유' 확인) — 늘릴 땐 다른 줄을 줄여야 함.
# [(슬롯 오프셋, KR 내레이션)] 50줄 — textmap/opening.json 파생(행별 편차 사유는 note 필드).
LINES = off_pairs("opening")
FIELD = 64  # 표시 필드 폭(유닛). 폭측정·표시 루프가 같은 단위로 센다
# ⚠ 전각 4 = 16px = **원작 그대로**다. Galmuri9 를 쓰던 동안만 3(12px)으로 좁혔었는데
#   (잉크폭 9px라 셀 여백이 넓어 성겨 보였다), Neo둥근모 16px 는 잉크가 16px 라 되돌린다.
#   좁힌 채로 두면 글자끼리 4px 겹친다.
ADV_WIDE, ADV_NARROW = 4, 2  # 전각 / 반각 advance(유닛)
# 반각으로 낼 글자 — 렌더러에 **이미 있는 advance 2 경로**를 빌린다. 원본은 전각공백과
# 좁은 라틴(ｆｉｊｌ) 다섯 코드를 하드코딩 비교해 2유닛만 진행하는데, 그 상수를 우리
# 글자의 슬롯 SJIS 로 바꿔치면 코드 추가 없이 반각이 된다(트램폴린 불필요).
# ⚠ 다섯 자리뿐이다. 늘리려면 비교 체인을 새로 짜야 한다.
# ⚠ **다섯 칸뿐이다.** 원본이 「좁은 글자 5종」 비교(`ori` 상수 다섯)를 이미 갖고 있어
#   그 자리를 우리 글자로 바꿔 쓰는 것이라, 코드를 한 줄도 안 늘리는 대신 **정확히 5개**다.
#   앞에서부터 「그 EXE 문안에 실제로 있는 것」 5개가 뽑힌다(`narrow[:5]`).
#   `()` 는 스태프롤 이름 뒤 괄호용이다 — 넷 다 재 보니 `!?` 는 한 번도 안 나와서 두 칸이
#   비어 있었다(2026-08-21 실측). ⚠ 늘리려면 등가비교 다섯을 **범위 비교**로 바꿔야 하는데
#   폭측정·표시 루프를 EXE 넷에서 각각 고쳐야 한다 — 로마자 34종 74회(대부분 스태프롤)에
#   견주면 값이 안 맞아 안 한다.
NARROW = " .,()!?"


# ── 스크립트 제어문자 · 들여쓰기 빈칸 (2026-08-16 원본 대조) ───────────────────────
# 원문에 섞인 이 글자들은 **글자가 아니다.** 원본을 나란히 돌려 확인했다:
#   `*` 색 전환(라벨이 노란색으로 뜨고 별표는 안 보인다) · `~`·`<`·`!` 스크립트 표식
#   `＿` 들여쓰기(원본 스태프롤의 `＿＿＿Corporation` 에 밑줄이 **하나도 안 보인다**)
# 슬롯 글리프로 넣으면 화면에 별표·느낌표·밑줄이 그대로 찍힌다(우리 첫 엔딩 빌드가 그랬다).
# ⚠ 원문도 `*`·`!` 를 **1바이트**로 담고 있으므로 원바이트로 내보내야 원본과 배치가 같다
#   (폭측정 루프는 1바이트를 폭 0으로 건너뛴다 — 원본 정렬이 그걸 전제로 짜여 있다).
CTRL_RAW = "!*~<"
BLANK_CH = "＿"


def norm(s):
    """폰트에 담아야 할 글자만 남긴다 — 제어문자는 빼고 `＿` 는 공백으로."""
    return "".join(" " if c == BLANK_CH else c for c in s if c not in CTRL_RAW)


# ── 로마자 두 글자를 한 글리프에 (2026-08-21) ─────────────────────────────────
# **왜.** 한 글자가 전각 셀 하나를 먹어 `S A L  L a b o r a t o r y` 처럼 늘어졌다.
# 진짜 반각을 얻으려면 원본의 「좁은 글자 5종」 비교를 **범위 비교로** 바꿔야 하는데,
# 폭측정·표시 루프를 EXE 넷에서 각각 고치는 일이라 값이 안 맞았다(유저와 검토 2026-08-21).
#
# 대신 **두 글자를 한 셀에 굽는다.** Neo둥근모는 로마자가 정확히 8px 이고 한글이 16px 라
# (실측 `getlength('Co') == 16.0`) `Co` 를 그대로 16×15 셀에 그리면 **딱 맞는다.**
# 🔴 **코드를 한 줄도 안 고친다** — 게임은 그냥 전각 글리프 하나로 본다.
#
# 곁가지 이득 둘: 폭이 절반이라 **줄 예산이 남고**, 두 글자가 슬롯 하나라 **바이트도 준다.**
# 대가는 **조합마다 슬롯 하나**를 먹는 것 — 실측치는 빌드 출력에 찍는다.
#
# ⚠ 제어문자(`!*~<`)와 이미 반각인 것(`NARROW`)은 절대 안 묶는다. 앞의 것은 화면에 찍히고,
#   뒤의 것은 이미 8px 이라 묶으면 오히려 넓어진다.
PAIRABLE = frozenset(string.ascii_letters + string.digits + "-&'")
# 홀수로 남은 로마자가 끌어올 수 있는 **반각** — 공백과 문장부호. 셀 하나에 같이 담긴다.
# ⚠ 제어문자(`!*~<` 중 제어로 쓰이는 것)는 여기 넣지 않는다 — 화면에 안 찍히는 것들이다.
PULLABLE = frozenset(" .,)")
# 잇달으면 한 셀에 같이 굽는 부호. ⚠ 공백은 넣지 않는다 — 공백끼리 묶으면 줄머리 들여쓰기가
# 셀 단위로 뭉쳐 원본 배치가 어긋난다.
PUNCT_PAIR = frozenset(".,")


def render_units(s):
    """문자열 → **렌더 단위** 목록. 로마자 연속열은 두 글자씩 묶인다.

    묶음 규칙 — 묶음은 로마자로 **시작하고 끝난다**. 가운데 공백은 함께 묶어 낱말 사이가
    벌어지지 않게 하고, 홀수로 남으면 **뒤따르는 공백 하나를 끌어와** 짝을 맞춘다
    (`Corporation` 11자 → `Co rp or at io n_`). 못 맞추면 마지막 한 글자는 그냥 한 셀이다.

    >>> render_units("(주) Co.,Ltd.")
    ['(', '주', ')', ' ', 'Co', '.', ',', 'Lt', 'd', '.']
    """
    out, i, n = [], 0, len(s)
    while i < n:
        # 부호가 잇달으면 **둘을 한 셀에** 굽는다 — `Co.,` 의 `.,` 가 그렇다(유저 QA
        # 2026-08-22). 폭은 어차피 같지만(반각 2유닛 × 2 = 전각 1셀), 한 글리프로 구우면
        # 두 부호 사이 간격을 우리가 정할 수 있다.
        if s[i] in PUNCT_PAIR and i + 1 < n and s[i + 1] in PUNCT_PAIR:
            out.append(s[i : i + 2])
            i += 2
            continue
        if s[i] not in PAIRABLE:
            out.append(s[i])
            i += 1
            continue
        j = i  # 로마자로 끝나는 최장 구간 (가운데 공백 허용)
        k, last = i, i
        while k < n and (s[k] in PAIRABLE or s[k] == " "):
            if s[k] in PAIRABLE:
                last = k
            k += 1
        j = last + 1
        run = s[i:j]
        # 홀수면 **뒤에 오는 반각 하나를 끌어와** 짝을 맞춘다 — 공백이든 부호든.
        # ⚠ 부호까지 끌어오는 이유: `Ltd.` 가 `Lt` + `d`(홀수라 셀 가운데) + `.` 로 갈려
        #   「Lt d.」 처럼 벌어졌다(유저 QA 2026-08-22, `GMF` 와 같은 증상).
        #   `d.` 를 한 셀에 담으면 잉크 16px 가 셀 16px 를 꽉 채워 폭 계산도 그림도 맞는다.
        if len(run) % 2 and j < n and s[j] in PULLABLE:
            run, j = s[i : j + 1], j + 1
        for t in range(0, len(run) - 1, 2):
            out.append(run[t : t + 2])
        if len(run) % 2:
            # ⚠ 홀수로 남은 한 글자는 셀 **가운데**로 밀리는데(`gen_glyphs`), 뒤에 아무것도
            #   없으면 그게 곧 앞 글자와 벌어져 보인다 — `GMF` 가 「GM F」 로 나왔다
            #   (유저 QA 2026-08-22). 끝이거나 개행 앞이면 **공백과 묶어** 왼쪽에 붙인다.
            #   ⚠ 뒤에 글자가 오는 자리(`6명`)까지 붙이면 반대로 뒤가 벌어진다 — 거기는 그대로.
            tail = run[-1]
            out.append(tail + " " if j >= n or s[j] == "\n" else tail)
        i = j
    return out


NARROW_SET = frozenset(NARROW)


def units(s):
    """줄의 표시 폭(유닛). 반각 글자는 2, 그 밖은 4. 제어문자는 안 센다(폭 0).

    ⚠ **세는 단위는 글자가 아니라 렌더 단위**다 — 로마자 두 글자가 한 셀이므로
    `render_units` 를 거치지 않으면 측정폭 > 표시폭이 되어 중앙정렬이 밀린다.
    ⚠ `u in NARROW` 은 **부분문자열 검사**라 두 글자 단위가 걸릴 수 있다 — 집합으로 본다.
    """
    return sum(ADV_NARROW if u in NARROW_SET else ADV_WIDE for u in render_units(norm(s)))


# ⚠ **여기 있던 `kuten_to_sjis` 를 `hangul_map` 것으로 합쳤다**(2026-08-18).
# 쓰는 범위(`ku ≤ 62`, 아래 단언 `0x889F~0x9872`)에서는 두 구현이 **한 자리도 안 달랐다**
# (실측 62×94 전수). 다른 건 안 쓰는 `ku ≥ 63` 가지뿐이었고 **그쪽이 틀려 있었다** —
# 표준 SJIS 는 `s1` 이 0xA0 을 넘으면 0x40 을 더해 반각 구간을 건너뛰는데 그 처리가 없었다
# (표준 대비 정확도 4,899 vs `hangul_map` 6,879). 안 쓰이는 코드가 조용히 틀려 있으면
# 언젠가 누가 그걸 근거로 쓴다.


def index_to_sjis(idx):
    """JIS 선형 인덱스 → SJIS (연속 인덱스용 역변환)."""
    ku, ten = idx // 94 + 1, idx % 94 + 1
    return H.kuten_to_sjis(ku, ten)


def build_slots(syllables):
    """음절 → 연속 한자슬롯 매핑. 인덱스 1410부터 순차 배정 → 폰트 컴팩트."""
    slot = {}
    for i, ch in enumerate(sorted(syllables)):
        idx = JIS_KANJI1_INDEX + i  # 1410, 1411, ...
        sjis = index_to_sjis(idx)
        assert 0x889F <= sjis <= 0x9872, f"슬롯 초과 idx={idx} sjis=0x{sjis:04X}"
        slot[ch] = (sjis, idx)
    return slot


def enc(s, slot):
    """내레이션 인코딩 — 모든 문자(한글·부호·숫자·공백)를 폰트 슬롯 SJIS로 통일.
    렌더 폭측정 루프(0x800132D4)는 2바이트(0x81~0x9F)만 폭에 세고 1바이트(\\x20 등)는
    폭 0으로 건너뛴다 → \\x20 공백/\\x81xx 부호를 쓰면 측정폭≠표시폭이라 중앙정렬이
    밀려 단어가 화면 밖으로 누락된다(+부호는 폰트 리다이렉트로 한글 깨짐). JP 원문처럼
    전부 2바이트 슬롯 글리프로 통일하면 폭측정=표시가 일치해 문장이 온전히 나온다.
    공백은 빈(잉크 없는) 글리프 슬롯.

    끝에 개행 0x0A를 붙인다(JP 원문 각 줄이 …0A 00으로 끝나는 것과 동일). 표시 함수의
    0x0A 핸들러(0x8001366C)가 X좌표가 필드 우변(960)에 닿을 때까지 빈 글리프16으로 채워
    줄 뒤 필드를 클리어한다. 이게 없으면 짧은 줄이 이전(더 긴) 줄의 잔여 픽셀을 못 덮어
    오른쪽에 유령 글자가 남는다("파렌, 온리크,"→뒤에 "는"). DuckStation/mednafen 실측 확인."""
    out = bytearray()
    for u in render_units(s):
        if u in CTRL_RAW and len(u) == 1:
            out += u.encode("ascii")  # 제어코드 — 글리프로 바꾸면 화면에 찍힌다
        else:
            out += struct.pack(">H", slot[" " if u == BLANK_CH else u][0])
    return bytes(out) + b"\x0a"


def verify_asm(words, base):
    """손인코딩 기계어를 **디스어셈블해 검산**한다.

    이 스텁은 손으로 워드를 적는다(어셈블러를 안 쓴다). 과거 그 오타 둘을 잡느라 반나절을
    썼다(devlog "디코더 손인코딩 함정"). capstone 이 이미 있으니 최소한 이건 자동으로 본다:

      ① 모든 워드가 유효 명령으로 **끊김 없이** 디코드되는가(중간에 데이터가 끼면 실패)
      ② 분기·점프의 **지연 슬롯이 비지 않는가**(delay slot 에 분기가 또 오면 정의되지 않음)
      ③ **로드 지연 슬롯** — MIPS I(R3000)은 `lw/lhu/lbu` **바로 다음 명령**에서 그 목적
         레지스터를 못 읽는다(옛 값이 온다). 이걸 어겨 반나절을 태웠다(2026-08-16):
         `andi t6, t3, 0x8000` 을 `lhu t3` 직후에 넣었더니 **옛 t3** 로 판정해 반각 분기가
         통째로 죽고 화면이 검게 나갔다. 디스어셈블은 멀쩡해 보이는 게 이 함정의 핵심이다.

    ⚠ 재조립 대조까지는 못 한다(capstone 은 디스어셈블러다). 의미가 맞는지는 사람이 본다."""
    from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

    blob = b"".join(struct.pack("<I", w) for w in words)
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    ins = list(md.disasm(blob, base))
    if len(ins) != len(words):
        bad = base + len(ins) * 4
        raise SystemExit(
            f"스텁 디코드 실패 @0x{bad:08X} ({len(ins)}/{len(words)}명령) — 손인코딩 확인"
        )
    BR = ("b", "beq", "bne", "beqz", "bnez", "bgtz", "blez", "j", "jr", "jal", "jalr")
    LOAD = ("lb", "lbu", "lh", "lhu", "lw", "lwl", "lwr")
    for a, b in zip(ins, ins[1:], strict=False):
        if a.mnemonic in BR and b.mnemonic in BR:
            raise SystemExit(f"지연 슬롯에 분기 @0x{b.address:08X} {b.mnemonic} — 정의되지 않음")
        if a.mnemonic in LOAD:
            dst = a.op_str.split(",")[0].strip()  # "$t3, ($t1)" → "$t3"
            if dst and dst in b.op_str:
                raise SystemExit(
                    f"로드 지연 슬롯 위반 @0x{b.address:08X}: {a.mnemonic} {dst} 직후 "
                    f"{b.mnemonic} {b.op_str} — MIPS I 은 옛 값을 읽는다"
                )
    print(f"  스텁 검산 OK — {len(ins)}명령 연속 디코드 · 분기/로드 지연 슬롯 정상")


def _jp_original():
    """소장 JP 원본 디스크 — "원본이 어땠는가"를 묻는 읽기는 전부 여기서."""
    import glob

    c = glob.glob(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "originals", "jp", "ps1-ed1+2", "*.bin"
        )
    )
    if not c:
        raise SystemExit("JP 원본 없음 — originals/jp/ps1-ed1+2 확인")
    return c[0]


def w32(op, off, val):
    op[off : off + 4] = struct.pack("<I", val)


STAFF = os.path.join(os.path.dirname(__file__), "..", "script", "END_STAFF.json")


def _repack_block(op, orig, lo, hi, table, slot, find_ptr, alloc):
    """스태프롤처럼 **본 내레이션 밖의 연속 문자열 블록**을 통째로 다시 깐다.

    ⚠ 한자 슬롯을 한글로 덮었으므로 스태프롤을 **그대로 두면 깨진다**(END2 34줄).
    그런데 한글 음차는 한자보다 길어 제자리엔 안 들어간다(총 728B / 슬롯 616B).
    블록이 연속이고 **줄마다 포인터가 따로** 있으므로 통째로 재packing하면 든다(블록 768B).

    표에 없는 줄은 원문 그대로 다시 깐다 — 자리만 옮기고 내용은 안 건드린다.

    ⚠ **재packing만으로는 여전히 모자란다**(실측: 786B/684B · 874B/768B). 부푸는 건 전부
    인명 줄이라 — 한자 두 자가 한글 넉 자가 된다 — 블록 안에서는 답이 안 나온다. 줄마다
    포인터가 따로 있으므로 **긴 줄부터 내레이션 풀로 흘린다**(`far_lines` 와 같은 수법).
    """
    items = []
    i = lo
    while i < hi:
        if orig[i] == 0:
            i += 1
            continue
        e = orig.find(b"\x00", i)
        if e < 0 or e > hi:
            break
        try:
            jp = bytes(orig[i:e]).decode("cp932")
        except UnicodeDecodeError:
            jp = None
        items.append((i, jp, e))
        i = e + 1
    ptrs = {off: find_ptr(TADDR + (off - 0x800)) for off, _, _ in items}
    rows = []
    for off, jp, e in items:
        # ⚠ 원문은 `\n` 으로 끝난다 — 조회는 벗긴 것으로 하고 쓸 때 되붙인다.
        core = jp.rstrip("\n") if jp else None
        kr = table.get(hashlib.sha1(core.encode()).hexdigest()[:10]) if core else None
        # (`enc` 가 개행을 스스로 붙인다 — 여기서 더하면 슬롯에 없는 글자가 된다)
        b = (enc(kr, slot) if kr else bytes(orig[off:e])) + b"\x00"
        rows.append([off, kr, b + b"\x00" * (-len(b) % 2)])

    # 큰 줄부터 흘려 보내 블록이 들어갈 때까지 — 순서가 결정적이라 재현된다.
    spill, order = [], sorted(range(len(rows)), key=lambda k: (-len(rows[k][2]), rows[k][0]))
    need = sum(len(r[2]) for r in rows)
    for k in order:
        if need <= hi - lo:
            break
        # 포인터를 못 찾은 줄은 못 옮긴다(제자리에서만 유효한 참조가 남는다).
        if ptrs[rows[k][0]] is None:
            continue
        spill.append(k)
        need -= len(rows[k][2])
    assert need <= hi - lo, f"스태프롤 예산 초과 0x{lo:X}: {need}B > {hi - lo}B"

    for k in range(lo, hi):
        op[k] = 0
    cur, n = lo, 0
    for k, (off, kr, b) in enumerate(rows):
        n += kr is not None
        if k in spill:
            npos = alloc(b)
            if npos is None:
                raise SystemExit(f"스태프롤 이설 공간 부족 0x{lo:X}: {kr!r}")
            op[npos : npos + len(b)] = b
            w32(op, ptrs[off], TADDR + (npos - 0x800))
            continue
        op[cur : cur + len(b)] = b
        if ptrs[off] is not None:
            w32(op, ptrs[off], TADDR + (cur - 0x800))
        cur += len(b)
    return len(items), n, (hi - cur, len(spill)), [p for p in ptrs.values() if p is not None]


def patch_game(name):
    """동영상 EXE 하나를 한글화한다 — 폰트 임베드 + PC0 스텁 + 내레이션 재packing."""
    g = game_cfg(name)
    OP_LBA, OP_SIZE = g["lba"], SIZE
    LINES = [(o + g["delta"], kr) for o, kr in off_pairs(g["cls"])]
    # ⚠ **검증 전용 치환** — 엔딩·ED2 오프닝은 게임을 끝까지 가야 보인다. 그래서 문안만
    #   다른 클래스 것으로 갈아끼워 **오프닝 자리에 띄워** 눈으로 본다(유저 요청 2026-08-21).
    #   ⚠ 오프셋은 반드시 **이 EXE 것**을 쓴다 — 남의 클래스 오프셋을 쓰면 엉뚱한 주소에
    #   쓴다(엔딩 오프셋 0x1A6C 는 END1.EXE 의 것이지 OPEN1.EXE 의 것이 아니다).
    #   🔴 배포 빌드에 절대 켜지 않는다. 환경변수라 커밋물에 안 남는다.
    #      ED_OPENING_TEXT_AS="OPEN1=ending_ed1" python3 tools/build.py
    _as = dict(
        kv.split("=", 1) for kv in os.environ.get("ED_OPENING_TEXT_AS", "").split(",") if "=" in kv
    )
    if name in _as:
        # `클래스[:시작줄]` — ⚠ **잘리는 뒤를 볼 길이 있어야 한다.** ED1 엔딩은 59줄인데
        #   오프닝 슬롯이 50뿐이라 9줄이 조용히 안 보였다. 「검수했다」가 실은 「앞만 봤다」가
        #   되는 자리라, 두 번째 회차로 뒤를 띄운다:
        #      ED_OPENING_TEXT_AS="OPEN1=ending_ed1:50"
        spec = _as[name]
        cls_as, _, start = spec.partition(":")
        start = int(start or 0)
        src_txt = [kr for _, kr in off_pairs(cls_as)][start:]
        n_show = min(len(LINES), len(src_txt))
        rest = len(src_txt) - n_show
        print(
            f"  🔬 검증 치환: {name} 자리에 {cls_as} 문안 {n_show}줄"
            + (f" ({start}번부터)" if start else "")
            + (
                f"  ⚠ 뒤 {rest}줄은 슬롯이 모자라 안 보인다 — `{cls_as}:{start + n_show}` 로 이어 본다"
                if rest
                else ""
            )
        )
        LINES = [(o, src_txt[i]) for i, (o, _) in enumerate(LINES[:n_show])]
    # ⚠ **포인터 테이블이 가리키는데 본 구획 밖에 있는 줄**이 있다(OPEN2 `だが…` @0x17484,
    # RAM 0x80026C84). 재packing 범위(min~max 오프셋)에 넣으면 그 사이의 **코드·자료를 통째로
    # 지운다** — 그래서 따로 뺀다. 이런 줄은 원본 슬롯 안에서 **제자리 치환**한다.
    # 실측(2026-08-16): 이 줄이 표에 없어 화면 한복판에 깨진 `드` 한 글자가 떠 있었다.
    FAR = {
        int(e["k"], 16) + g["delta"]
        for e in json.load(open(_tm_path(g["cls"]), encoding="utf-8"))["entries"]
        if e.get("far")
    }
    far_lines = [(o, kr) for o, kr in LINES if o in FAR]
    LINES = [(o, kr) for o, kr in LINES if o not in FAR]
    # ⚠ **디코더는 저작권 문자열 자리에 두지 않는다**(2026-08-16 전환). 그 자리는 뒤가
    # 곧 **게임의 런타임 작업버퍼**(0x8002546A~)라 스텁이 길어지면 그걸 덮는다 — 반각
    # 분기를 넣어 23→32명령이 되자 화면이 검게 죽었다(대조군: 옛 스텁은 정상). 옛 가드는
    # setjmp 영역(0런+0x3B)만 봐서 못 잡았다.
    # 폰트 구획 **앞 128B 를 디코더 몫으로 떼어** 둔다 — 여기는 0런이고 폰트 소스가 이미
    # 무사히 읽히는 자리라 코드도 안전하다. 저작권 자리는 이제 아예 안 건드린다.
    DEC_RESERVE = 0x80
    DEC_FILE_OFF = g["font_off"]
    DEC_RAM = TADDR + (DEC_FILE_OFF - 0x800)
    COMP_FONT_FILE_OFF = g["font_off"] + DEC_RESERVE
    COMP_FONT_LOAD = TADDR + (COMP_FONT_FILE_OFF - 0x800)
    COMP_FONT_MAX = g["font_max"] - DEC_RESERVE
    ORIG_PC0 = g["pc0"]
    FONT_RUNTIME = g["font_ram"]

    if not os.path.exists(SRC):
        raise SystemExit(f"KR 이미지 없음 — build.py 먼저 실행\n  기대: {SRC}")
    op = bytearray(extract(OP_LBA, OP_SIZE, path=SRC))

    # 사용 문자 수집 — 한글뿐 아니라 부호·숫자·공백도 전부 슬롯화(렌더 폭측정 일치).
    staff = {}
    if g.get("blocks") and os.path.exists(STAFF):
        with open(STAFF, encoding="utf-8") as f:
            staff = json.load(f)
    syl = set()
    for _, kr in LINES + far_lines:  # ⚠ 구획 밖 줄의 글자도 폰트에 있어야 한다
        syl.update(render_units(norm(kr)))
    for kr in staff.values():  # 스태프롤 글자도 폰트에 있어야 한다
        syl.update(render_units(norm(kr)))
    slot = build_slots(syl)
    n = len(syl)
    print(f"고유 음절 {n}, 네이티브 폰트 {n * GLYPH}B(raw)")

    # 1) 폰트를 네이티브 30B로 생성 → 행-마스크 압축 → 안전 0영역에 임베드.
    #    (raw 5730B는 안전영역 초과 → 압축본 ~3986B만 파일에 둔다. 스텁이 자유 RAM에 푼다.)
    glyphs = gen_glyphs(sorted(syl))  # 30B/글리프(15행)
    raw = [glyphs[ch][:GLYPH] for ch in sorted(syl)]
    comp, NDICT = compress_font_dict(raw)
    assert len(comp) <= COMP_FONT_MAX, (
        f"압축폰트 {len(comp)}B > 안전 {COMP_FONT_MAX}B"
        f" (옛 행-그대로 코덱이면 {len(compress_font(raw))}B)"
    )
    op[COMP_FONT_FILE_OFF : COMP_FONT_FILE_OFF + len(comp)] = comp
    DICT_BYTES = NDICT * 2 + (NDICT * 2 & 1)
    print(
        f"압축 폰트 {len(comp)}B (행 사전 {NDICT}개 · 옛 코덱 {len(compress_font(raw))}B) "
        f"임베드 파일 0x{COMP_FONT_FILE_OFF:X} (로드 RAM 0x{COMP_FONT_LOAD:08X})"
    )

    # 1b) 내레이션 재삽입 — 저주소 텍스트 영역 내 재packing.
    #     원본은 각 줄이 고정 오프셋(포인터테이블 1:1)이라 초과줄이 제자리 예산을 넘쳤다. 하지만
    #     전체 KR < 영역이므로, 49줄을 영역 안에 통째로 다시 깔고 포인터를 갱신하면 다 들어간다.
    #     스크립트(0x145A0)가 주소 범위로 text/command를 가르므로 반드시 저주소(0x8001xxxx) 유지.
    #     원본 배치(표시순=내림차순 주소) 보존 위해 영역 상단부터 아래로 팩. 렌더 lhu 위해 2B 정렬.
    # ⚠ **원본에서 읽는다.** 아래 둘은 "원본 JP 가 어땠는가"를 묻는 질문이라, 제자리 갱신된
    #   이미지(SRC=DST)를 다시 읽으면 회차마다 답이 달라진다 — jp_len 은 우리 한국어 길이를
    #   재고, find_ptr 은 이미 갱신된 포인터를 못 찾는다(실측 2026-08-02).
    orig = bytes(extract(OP_LBA, OP_SIZE, path=_jp_original()))

    def jp_len(o):
        e = o
        while orig[e]:
            e += 1
        return e - o

    # ⚠ **포인터 스캔 범위를 도출한다.** 파일 넷이 서로의 포인터 테이블까지 사본으로
    # 들고 있어서(내레이션 164줄이 다 실려 있다) 범위를 넓게 잡고 첫 일치를 쓰면
    # **사문 테이블을 갱신하고 살아있는 쪽은 그대로 두는** 사고가 난다.
    # 그래서 이 게임의 줄들을 가리키는 포인터가 **가장 촘촘히 모인 구간**을 찾아 쓴다.
    # (END2 는 테이블이 0x14EF4~0x15184 라 옛 고정 범위 0x14000~0x15000 밖이었다.)
    _all_ptr = {}
    for i in range(0x13000, 0x16000, 4):
        _all_ptr.setdefault(struct.unpack("<I", orig[i : i + 4])[0], []).append(i)
    _wanted = {TADDR + (o - 0x800) for o, _ in LINES}
    _hits = sorted(i for ram, xs in _all_ptr.items() if ram in _wanted for i in xs)
    assert _hits, "이 게임의 줄을 가리키는 포인터를 하나도 못 찾았다"
    _best, _run = (0, 0), []
    for i in _hits:  # 400B 안에 몇 개나 모이나 — 가장 촘촘한 곳이 살아있는 표다
        _run = [x for x in _run if i - x <= 0x400] + [i]
        if len(_run) > _best[0]:
            _best = (len(_run), _run[0])
    _lo = _best[1] - 0x400
    _hi = _lo + 0x1000

    def find_ptr(ram):
        for i in range(max(0, _lo), _hi, 4):
            if struct.unpack("<I", orig[i : i + 4])[0] == ram:
                return i
        return None

    line_offs = [off for off, _ in LINES]
    region_lo = min(line_offs)
    region_hi = max(line_offs) + jp_len(max(line_offs)) + 1  # 마지막 null 종료자 포함
    # 보조 풀 — JP CD 오류문 2개 자리(0x864·0x8CC). CD 읽기 실패 경로(0x80012D08·0x80012DC0·
    # 0x80012DFC)에서만 참조되고 그 안을 가리키는 다른 참조는 없다(전 명령 lui/addiu 쌍 스캔
    # 으로 확인 — 대조군 cdrom:\ED.EXE·OPENEND 는 정상 검출됨). 그 시점엔 게임이 이미 죽으므로
    # 문안을 비우고 본문 공간으로 돌린다. 각 문자열 **선두 4B 는 0으로 남겨** 오류 경로가 빈
    # 문자열을 읽게 한다(안 그러면 내레이션이 오류창에 뜬다).
    # ⚠ 늘리지 말 것 — 0x938 부터는 포인터 테이블이다(0x80014xxx 를 가리킨다).
    POOLS = [(g["err"] + 4, g["err2"]), (g["err2"] + 4, g["ptab"])]
    ptr_pos = {}  # 갱신 전 원주소로 포인터 위치 선수집(신주소가 타 원주소와 충돌 시 오매칭 방지)
    for off in line_offs:
        pi = find_ptr(TADDR + (off - 0x800))
        if pi is None:
            raise SystemExit(f"포인터 못찾음 줄 0x{off:X}")
        ptr_pos[off] = pi
    # 본영역 + 보조 풀 클리어(구 JP 데이터 제거). ⚠ 두 범위를 **따로** 지운다 — 사이의
    # 0x938~0x973 은 포인터 테이블이라 통째로 지우면 오프닝이 죽는다(실측 2026-08-02).
    # 0x864~0x938 전체를 지워야 오류문 선두 4B 도 0이 되어 빈 문자열이 된다.
    # ⚠ **본영역에서 스태프롤 블록을 도려낸다.** 본영역은 `min~max` 스팬이라 사이에 낀
    # 블록까지 삼킨다 — END2 는 내레이션 줄 둘(`당신이 꿈을…`·`당신이 나를…`)이 블록
    # **뒤쪽**에 있어 스팬이 0x1B80~0x1E80 을 통째로 덮었다. 그러면 내레이션 packer 와
    # 블록 packer 가 **같은 바이트를 서로 덮어써서** 회사명 자리에 내레이션 조각이 뜬다
    # (2026-08-16 인게임 실측: `＊발매` 아래 「..」, `＊협력` 아래 내레이션 한 줄).
    body = [(region_lo, region_hi)]
    for blo, bhi in g.get("blocks", ()):
        nxt = []
        for lo, hi in body:
            if bhi <= lo or blo >= hi:
                nxt.append((lo, hi))
                continue
            if lo < blo:
                nxt.append((lo, blo))
            if bhi < hi:
                nxt.append((bhi, hi))
        body = nxt

    for lo, hi in (
        (g["err"], g["ptab"]),
        *body,
        *([g["spare"]] if g.get("spare") else []),
    ):
        for k in range(lo, hi):
            op[k] = 0
    # 본영역을 위에서 아래로 채우고, 모자라면 보조 풀로 넘어간다. 줄마다 포인터가 따로
    # 있으므로 배치 순서·연속성은 상관없다(스크립트는 값의 주소 대역만 본다 — 전부 0x8001xxxx).
    # ⚠ 풀을 순서대로 소진하면 전환할 때마다 자투리(최대 한 줄분)가 버려진다. 줄마다
    # 포인터가 따로라 배치 순서는 자유이므로 **first-fit** 으로 모든 풀을 계속 살려 둔다.
    # ⚠ **상대편 스태프롤 블록을 보조 풀로 돌린다.** END1·END2 는 서로의 스크립트까지
    # 사본으로 들고 있어서(내레이션과 같은 구조) 스태프롤 블록도 둘이다. 어느 쪽이
    # 살아있는지는 **포인터가 어느 표에 놓였는가**로 갈린다(실측 2026-08-16):
    #   END1 내레이션 표 0x14AB8~0x14D84 → 바로 뒤 0x14DEC~0x14EA8 이 블록 0x1260
    #   END2 내레이션 표 0x14EF4~0x15184 → 그 안에 섞인 0x14FE8~0x15108 이 블록 0x1B80
    # 남는 쪽은 그 파일에서 한 번도 안 읽힌다. 한글 음차가 한자보다 길어 블록 안에서는
    # 100B 남짓 모자라는데(786B/684B), 이 자리를 풀로 쓰면 넉넉히 든다.
    pools = [*body, *POOLS, *([g["spare"]] if g.get("spare") else [])]
    cur = [hi for _, hi in pools]  # 풀별 커서(위에서 아래로)
    for off, kr in LINES:  # 표시순(=원본 내림차순 주소) 유지
        u = units(kr)
        if u > FIELD:
            raise SystemExit(f"줄 폭 초과({u}>{FIELD}유닛): '{kr}'")
        b = enc(kr, slot)
        for pi, (lo, _) in enumerate(pools):
            npos = (cur[pi] - len(b) - 1) & ~1  # null 종료자 + 2바이트 정렬
            if npos >= lo:
                break
        else:
            raise SystemExit(f"재packing 공간 부족: '{kr}' (풀 {len(pools)}개 소진)")
        cur[pi] = npos
        op[npos : npos + len(b)] = b  # 뒤 null은 클리어로 이미 0
        w32(op, ptr_pos[off], TADDR + (npos - 0x800))
    free = sum(c - lo for c, (lo, _) in zip(cur, pools, strict=True))
    print(
        f"내레이션 {len(LINES)}줄 재packing — 풀 {len(pools)}개, "
        f"여유 {free}B (최대 연속 {max(c - lo for c, (lo, _) in zip(cur, pools, strict=True))}B)"
    )

    # 1c) 본 구획 밖 줄 — **풀로 옮기고 포인터를 갱신**한다.
    # 원 슬롯이 8B(`だが…\n`+널)뿐이라 제자리로는 한 글자도 못 늘린다. 줄마다 포인터가
    # 따로 있으므로 본 구획 풀에 넣고 포인터만 돌리면 된다.
    # ⚠ **저주소(0x8001xxxx)로 옮기는 건 안전하다** — 스크립트가 주소 대역으로 text/command
    # 를 가르는데(0x145A0) 우리 풀은 전부 텍스트 대역이다. 위험한 건 반대 방향(고주소)이다.
    def alloc(b):
        """풀에서 `b` 만큼 떼어 준다(first-fit, 2바이트 정렬). 없으면 None."""
        for pi, (lo, _) in enumerate(pools):
            npos = (cur[pi] - len(b)) & ~1
            if npos >= lo:
                cur[pi] = npos
                return npos
        return None

    for off, kr in far_lines:
        b = enc(kr, slot) + b"\x00"
        npos = alloc(b)
        if npos is None:
            raise SystemExit(f"구획 밖 줄 공간 부족: {kr!r}")
        op[npos : npos + len(b)] = b
        ptr = find_ptr(TADDR + (off - 0x800))
        if ptr is None:
            raise SystemExit(f"구획 밖 줄 포인터 못찾음 0x{off:X}")
        w32(op, ptr, TADDR + (npos - 0x800))
        e = off
        while orig[e]:
            e += 1
        op[off : e + 1] = b"\x00" * (e + 1 - off)  # 옛 자리는 비운다(일본어 잔존 제거)
        print(f"  구획 밖 줄 이설 0x{off:X} → 0x{npos:X} (ptr 0x{ptr:X}) {kr!r}")

    live_ptrs = list(ptr_pos.values())

    # 1d) 스태프롤 등 별도 블록 — 통째로 재packing(포인터 갱신 포함).
    for blo, bhi in g.get("blocks", ()):
        cnt, hit, (left, moved), bptrs = _repack_block(
            op, orig, blo, bhi, staff, slot, find_ptr, alloc
        )
        live_ptrs += bptrs
        print(
            f"  블록 0x{blo:X}~0x{bhi:X}: {cnt}줄 중 {hit}줄 한글화"
            f" (여유 {left}B · 풀로 이설 {moved}줄)"
        )

    # ⚠ **화면에 나가는 바이트를 게이트로 본다.** 렌더러는 **2바이트 코드를 전부 우리
    # 폰트로 돌린다** — 한자뿐 아니라 전각 로마자도 그렇다. 그래서 「로마자니까 안 깨진다」는
    # 틀렸다: `ＧＭＦ` 가 「일자인」으로, `ＣＲＥＤＩＴＳ` 가 일곱 글자 잡소리로 나갔다
    # (2026-08-16 인게임 실측). 빌드도 단위 테스트도 조용했다.
    #
    # 그래서 **살아있는 포인터 표를 되짚어** 우리 슬롯 밖의 2바이트 코드가 한 줄이라도
    # 남으면 죽인다. 표 구간은 손으로 안 적는다 — 이번 회차에 우리가 실제로 갱신한
    # 포인터 자리에서 유도한다(사문 표를 같이 훑으면 죽은 사본까지 걸려 못 쓴다).
    ok_codes = {sj for sj, _ in slot.values()}
    garbled = {}
    for i in range(min(live_ptrs), max(live_ptrs) + 4, 4):
        fo = struct.unpack("<I", op[i : i + 4])[0] - TADDR + 0x800
        if not (0x800 <= fo < SIZE):
            continue
        e = op.find(b"\x00", fo)
        if e < 0 or e - fo > 80:
            continue
        raw = bytes(op[fo:e])
        j = 0
        while j < len(raw) - 1:
            if raw[j] >= 0x81:
                if struct.unpack(">H", raw[j : j + 2])[0] not in ok_codes:
                    garbled[fo] = raw
                    break
                j += 2
            else:
                j += 1
    assert not garbled, (
        f"{name}: 우리 폰트 밖 2바이트 코드가 남은 줄 {len(garbled)}건"
        f" — 화면에 깨져 나간다 ({[hex(o) for o in sorted(garbled)]})"
    )

    # 2) PC0 진입점 훅: 저작권 문자열 자리에 디코더 스텁을 넣고 헤더 PC0를 스텁으로.
    #    (a) 압축 폰트(COMP_FONT_LOAD)를 자유RAM(FONT_RUNTIME)에 네이티브 30B로 전개(행-마스크).
    #    (b) 원PC0 점프. (로더 b_size=0라 소스는 PC0 시점 온전 → 게임 힙클리어 전에 대피)
    #    폰트 레지스터: t0=dst t1=src t2=글리프수 t3=마스크 t4=행 t5=행값.
    #    (줄은 저주소 영역 재packing이라 스텁 복사 불필요 — 폰트만 자유RAM으로 대피)
    # ⚠ 스텁은 `build_decoder_stub` 이 만든다 — **테스트가 부를 수 있어야** 하기 때문이다.
    #   인라인이던 시절엔 손인코딩을 검증할 방법이 디스어셈뿐이었고, 그건 분기 오프셋이
    #   어긋나도 통과시킨다(2026-08-21 실측: 셋이 전부 한 칸씩 틀렸는데 다 통과).
    #   지금은 `test_opening_decoder_stub_actually_decodes` 가 **실행해서** 대조한다.
    stub = build_decoder_stub(FONT_RUNTIME, COMP_FONT_LOAD, DICT_BYTES, n, ORIG_PC0)
    verify_asm(stub, DEC_RAM)
    stub_end = DEC_RAM + len(stub) * 4
    assert len(stub) * 4 <= DEC_RESERVE, (
        f"디코더 {len(stub) * 4}B > 예약 {DEC_RESERVE}B — 폰트 자리를 침범한다"
    )
    for k, ins in enumerate(stub):
        w32(op, DEC_FILE_OFF + k * 4, ins)
    w32(op, 0x10, DEC_RAM)  # 헤더 PC0 → 디코더
    print(
        f"PC0 훅: 디코더@0x{DEC_RAM:08X}~0x{stub_end:X} ({len(stub)}명령) → 폰트 0x{FONT_RUNTIME:08X}"
    )

    # 3) 폰트베이스 리다이렉트 (0x8001BE84 jal / BE88 nop / BE8C addu s0,v0 → lui/addiu s0 = base).
    #    렌더는 원본 그대로(글리프 base+index×30, 15행). 행수·stride·shadow 패치 불필요.
    #    한자 index = SJIS-table[k].base+offset(@0x80024E60), index(0x889F)=0 → base=FONT_RUNTIME.
    #    디코더가 글리프0을 dst+0에 직접 쓰므로 +4 밀림 없음(과거 memcpy 방식의 잔재였음).
    fbase = FONT_RUNTIME & 0xFFFFFFFF
    hi, lo = (fbase >> 16) & 0xFFFF, fbase & 0xFFFF
    if lo & 0x8000:
        hi = (hi + 1) & 0xFFFF
    base_be84 = 0x800 + (g["fontbase"] - TADDR)
    w32(op, base_be84 + 0, 0x3C100000 | hi)  # lui s0, hi
    w32(op, base_be84 + 4, 0x26100000 | lo)  # addiu s0, s0, lo
    w32(op, base_be84 + 8, 0x00000000)  # nop
    print(f"폰트베이스 리다이렉트 s0=0x{fbase:08X} (glyph=base+index×{GLYPH}, 네이티브 렌더)")

    # 4) 글자 간격 축소(가독성). 표시 루프는 전각 1글자마다 X누적 s3를 4유닛(=16px 셀)씩
    #    진행하는데 Galmuri9 잉크폭은 ~9px라 셀당 여백이 넓어 성기게 보인다. 폭측정 루프
    #    (0x13370)·표시 루프(0x13750)의 전각 advance를 4→3(12px)로 줄이면 촘촘해진다.
    #    둘 다 바꿔야 폭측정=표시가 일치해 중앙정렬이 맞는다. (2=8px는 넓은 받침 겹침 → 3 채택.
    #    에뮬 실측 확인). 글리프 타일은 16px지만 배경 투명 블릿이라 셀 겹침은 무해.
    def fo(ram):
        return 0x800 + (ram - TADDR)

    # 4b) 반각 처리 — 원본의 "좁은 글자 5종" 비교 상수를 우리 공백·부호 슬롯으로 바꾼다.
    #     원본: 0x8140(전각공백)·0x8286·0x8289·0x828A·0x828C(ｆｉｊｌ)를 만나면 advance 2.
    #     이 다섯 자리를 우리 글자로 채우면 **코드 한 줄 안 늘리고** 반각을 얻는다.
    #     ⚠ 폭측정·표시 **양쪽 다** 바꿔야 한다 — 한쪽만 바꾸면 측정≠표시라 중앙정렬이
    #     밀려 글자가 화면 밖으로 잘린다(advance 4→3 때 실측한 함정과 같은 것).
    narrow = [c for c in NARROW if c in slot][:5]
    codes = [slot[c][0] for c in narrow]
    codes += [codes[0]] * (5 - len(codes))  # 남는 자리는 첫 코드로 채워 무해하게
    for base in (g["narrow_w"], g["narrow_d"]):  # 폭측정 / 표시 — ori 5개
        step = 4 if base == g["narrow_w"] else 8  # 표시 쪽은 ori 사이에 beq 가 낀다
        for k, c in enumerate(codes):
            a = fo(base + k * step)
            ins = struct.unpack("<I", op[a : a + 4])[0]
            assert ins >> 26 == 0x0D, f"ori 아님 @0x{base + k * step:X}: {ins:08X}"
            w32(op, a, (ins & 0xFFFF0000) | c)
    print(f"반각 처리: {''.join(narrow)!r} → advance {ADV_NARROW}유닛 (전각 {ADV_WIDE})")

    # ⚠ 폭측정·표시 **양쪽 다** 같은 값이어야 한다 — 어긋나면 중앙정렬이 밀려 글자가
    #   화면 밖으로 잘린다. 그래서 `ADV_WIDE` 하나에서 끌어온다.
    w32(op, fo(g["adv_w"]), 0x24840000 | ADV_WIDE)  # addiu a0,a0,N  (폭측정 전각, 원 +4)
    w32(op, fo(g["adv_d"]), 0x26730000 | ADV_WIDE)  # addiu s3,s3,N  (표시 전각, 원 +4)
    print(f"글자 advance {ADV_WIDE}유닛 ({ADV_WIDE * 4}px)")

    if SRC != DST:
        shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        n_sec = write_user_data(f, OP_LBA, op, label=f"내레이션 폰트 ({name})")
        print(f"{name}.EXE: 섹터 {n_sec}개 수정")
    write_cue(DST_CUE, os.path.basename(DST))


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or ["OPEN1"]
    for name in want:
        patch_game(name)
    print(f"완료: {DST}")


# ── 행 사전 코덱 (2026-08-21) ─────────────────────────────────────────────────
# **왜 갈아엎나.** 위 `compress_font` 는 비지 않은 행을 **그대로** 저장한다. 그래서 예산
# 4,064B 가 곧 「평균 잉크 8.5행」이 되고, **셀(16×15)에는 수납되는 폰트가 예산에서 떨어진다** —
# Galmuri11(10.2행) 4,782B · neodgm 16px(11.9행) 5,472B 가 그렇게 탈락했다.
#
# 그런데 한글 도트는 가로획 패턴이 심하게 겹친다. 실측(오프닝 214자):
#
#     Galmuri9   비지 않은 행 1,780 → **서로 다른 행 95**
#     neodgm16   비지 않은 행 2,540 → **서로 다른 행 173**
#
# 즉 행을 사전에 모으고 1바이트 색인만 늘어놓으면 된다. 같은 214자 기준:
#
#     Galmuri9  3498B → 2398B      Galmuri11 4782B → 2868B      neodgm16 5472B → 3314B
#
# **셋 다 예산 안에 들어온다.** 폰트를 키우는 길이 여기서 열린다.
#
# 형식:  [사전 D×2B][글리프 …]   글리프 = 2B 마스크 + (선 비트마다) 1B 색인 + 짝수 패딩
#   ⚠ 마스크는 디코더가 `lhu` 로 읽는다 — **2B 정렬**을 지켜야 한다(홀수 주소 `lhu` 는
#     MIPS 에서 주소 예외로 죽는다, 2026-08-16 실측).
#   ⚠ 색인이 1B 라 사전은 **256개까지**다. 넘으면 여기서 실패시킨다.
#   ⚠ 반각(비트15) 최적화는 **뺐다.** 사전이 이미 그 이득을 먹고(반각 행도 한 항목),
#     디코더 명령 예산(32명령)이 빠듯하다.

DICT_MAX = 256


def compress_font_dict(glyph_list):
    """행 사전 압축 → `(blob, 사전항목수)`. `blob` 은 사전+글리프를 이어 붙인 것."""
    order, seen = [], {}
    per = []
    for gb in glyph_list:
        idx = []
        for r in range(DRAW_ROWS):
            row = gb[r * 2 : r * 2 + 2]
            if row == b"\x00\x00":
                continue
            if row not in seen:
                seen[row] = len(order)
                order.append(row)
            idx.append((r, seen[row]))
        per.append(idx)
    if len(order) > DICT_MAX:
        raise SystemExit(f"행 사전 {len(order)}개 > {DICT_MAX} — 색인 1B 로 못 가리킨다")

    out = bytearray(b"".join(order))
    if len(out) & 1:  # 사전 뒤부터 글리프의 마스크가 시작한다 — 2B 정렬
        out += b"\x00"
    for idx in per:
        mask = 0
        for r, _ in idx:
            mask |= 1 << r
        out += struct.pack("<H", mask)
        out += bytes(i for _, i in idx)
        if len(out) & 1:
            out += b"\x00"
    return bytes(out), len(order)


def decode_font_dict(blob, ndict, nglyph):
    """디코더 스텁과 **같은 절차**로 되돌린다 — 왕복 대조용 기준 구현.

    ⚠ 스텁을 손으로 인코딩하므로 파이썬 기준이 없으면 「빌드는 되는데 화면만 검다」가 된다.
    """
    table = [blob[i * 2 : i * 2 + 2] for i in range(ndict)]
    p = ndict * 2 + (ndict * 2 & 1)
    out = []
    for _ in range(nglyph):
        mask = int.from_bytes(blob[p : p + 2], "little")
        p += 2
        rows = []
        for r in range(DRAW_ROWS):
            if mask & (1 << r):
                rows.append(table[blob[p]])
                p += 1
            else:
                rows.append(b"\x00\x00")
        if p & 1:
            p += 1
        out.append(b"".join(rows))
    return out


def build_decoder_stub(dst, src, dict_bytes, nglyph, pc0):
    """행 사전 blob → 네이티브 30B 글리프로 전개하는 PC0 스텁 (MIPS I 손인코딩).

    레지스터: t0=dst · t1=글리프 스트림 · t2=글리프수 · t3=마스크 · t4=행카운터 ·
    t5=행값 · t6=색인/주소 · t7=사전바닥 · t9=정렬 임시.

    ⚠ **MIPS I 로드 지연 슬롯** — 로드 바로 다음 명령에서 그 레지스터를 못 읽는다.
    옛 스텁이 여기서 죽었다(2026-08-16: `andi` 를 끼워 넣었다가 **옛 t3** 를 읽어 반각
    분기가 죽고 화면이 검게 나갔다). 아래 두 자리가 그 제약을 흡수한다:
      · `lbu t6`(11) → 쓰는 곳은 13  · `lhu t5`(15) → 쓰는 곳은 17
    `addiu t4,-1`(16)을 **분기 착지점으로 겸하게** 해서 nop 없이 간격을 만들었다 —
    비트가 0 이면 `andi` 결과 t5=0 이라 그대로 0 을 쓰면 된다.

    ⚠ 마스크는 `lhu` 다 — 글리프 경계가 **2B 정렬**이어야 한다(홀수 주소 `lhu` = 주소 예외).
    꼬리 셋(20~22)이 t1 을 짝수로 올린다. `andi t1,t1,0xFFFE` 로 줄이고 싶지만 **상위
    16비트가 날아가** 주소가 깨진다.
    """
    assert dst & 0xFFFF == 0, "dst 는 lui 하나로 만든다"
    assert src & 0xFFFF < 0x8000 and 0 < dict_bytes < 0x8000 and 0 < nglyph < 0x8000
    assert pc0 & 0xFFFF < 0x8000
    return [
        0x3C080000 | (dst >> 16),  # 0   lui   t0, dst_hi
        0x3C0F0000 | (src >> 16),  # 1   lui   t7, src_hi
        0x25EF0000 | (src & 0xFFFF),  # 2   addiu t7, t7, src_lo   (사전 바닥)
        0x25E90000 | dict_bytes,  # 3   addiu t1, t7, 사전크기 (글리프 스트림)
        0x240A0000 | nglyph,  # 4   addiu t2, r0, 글리프수
        0x952B0000,  # 5 G: lhu  t3, 0(t1)        마스크
        0x340C000F,  # 6    ori  t4, r0, 15       행 카운터
        0x25290002,  # 7    addiu t1, t1, 2       (t3 는 3명령 뒤에 쓴다)
        0x316D0001,  # 8 R: andi t5, t3, 1
        0x11A00006,  # 9    beq  t5, r0, DEC(+6 → 16)
        0x000B5842,  # 10   srl  t3, t3, 1   (delay)
        0x912E0000,  # 11   lbu  t6, 0(t1)        색인
        0x25290001,  # 12   addiu t1, t1, 1
        0x000E7040,  # 13   sll  t6, t6, 1        색인×2
        0x01CF7021,  # 14   addu t6, t6, t7       사전 + 오프셋
        0x95CD0000,  # 15   lhu  t5, 0(t6)        행값
        0x258CFFFF,  # 16 DEC: addiu t4, t4, -1   (겸 착지점)
        0xA50D0000,  # 17   sh   t5, 0(t0)
        0x1580FFF5,  # 18   bne  t4, r0, R(-11 → 8)
        0x25080002,  # 19   addiu t0, t0, 2  (delay)
        0x25290001,  # 20   addiu t1, t1, 1       ─┐ 2B 정렬로
        0x31390001,  # 21   andi t9, t1, 1         │ 올림
        0x01394823,  # 22   subu t1, t1, t9       ─┘
        0x254AFFFF,  # 23   addiu t2, t2, -1
        0x1540FFEC,  # 24   bne  t2, r0, G(-20 → 5)
        0x00000000,  # 25   nop  (delay)
        0x3C080000 | (pc0 >> 16),  # 26   lui  t0, pc0_hi
        0x25080000 | (pc0 & 0xFFFF),  # 27   addiu t0, t0, pc0_lo
        0x01000008,  # 28   jr   t0
        0x00000000,  # 29   nop
    ]


if __name__ == "__main__":
    main()
