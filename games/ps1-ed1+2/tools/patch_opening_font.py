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
  5) 전각 advance 4→3 패치(0x13370/0x13750)로 간격 축소. 줄당 한계 21슬롯.

텍스트는 정발판(originals/kr/dos-ed1/OPENING.EXE) 원문 우선, JP 전용부만 정발 어투 신규 번역.
상세 여정: docs/opening-font-devlog.md, 핸드오프: docs/HANDOFF.md.
전제: build.py(베이스) 후 이 스크립트 적용 → work/Eiyuu Densetsu (KR).bin (제자리 갱신).
"""

import os
import shutil
import struct

import hangul_font
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
GALMURI_BDF = hangul_font.GALMURI11_BDF.replace("Galmuri11", "Galmuri9")  # 9px 전용 비트맵(또렷)
# Galmuri9 dy=1 → 잉크 3~11행(위3/아래3 여백, 무잘림). 압축 3584B로 안전영역에 여유.
GALMURI_DY = 1
# 폰트 선택: "galmuri"(전용 BDF, 도트 또렷) | "neodgm"(16px TTF 축소, 거침 — 비추천)
FONT_MODE = "galmuri"
NEODGM_TTF = os.path.join(os.path.dirname(__file__), "../../../shared/fonts/neodgm.ttf")
NEODGM_PX = 12  # 맞는 것 중 최대(3908B). 15행 셀 상단여백 2에서 잉크 2~12
NEODGM_TOP = 2
STUB_FILE_OFF = 0x15C14  # 저작권 문자열 자리(게임 미사용, 어제 스텁 검증). RAM 0x80025414 = 디코더.
STUB_RAM = TADDR + (STUB_FILE_OFF - 0x800)  # 0x80025414
ORIG_PC0 = 0x80021D50


def gen_glyphs_neodgm(chars):
    """음절 → GLYPH바이트. neodgm(16px TTF)을 NEODGM_PX로 렌더(잉크 상단정렬+여백)."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(NEODGM_TTF, NEODGM_PX)
    out = {}
    for ch in chars:
        img = Image.new("L", (16, 16), 0)
        ImageDraw.Draw(img).text((0, 0), ch, fill=255, font=font)
        a = np.array(img)
        ys, xs = np.where(a >= 128)
        bits = np.zeros((DRAW_ROWS, 16), dtype=np.uint8)
        if len(ys):
            y0 = ys.min()
            for y, x in zip(ys, xs, strict=True):
                yy = int(y) - int(y0) + NEODGM_TOP
                if 0 <= yy < DRAW_ROWS and 0 <= x < 16:
                    bits[yy, x] = 1
        out[ch] = np.packbits(bits, axis=1).tobytes()
    return out


def gen_glyphs(chars):
    """음절 → GLYPH바이트(16×DRAW_ROWS) 글리프. FONT_MODE에 따라 Galmuri/neodgm."""
    if FONT_MODE == "neodgm":
        return gen_glyphs_neodgm(chars)
    glyphs, ascent = hangul_font.load_bdf(GALMURI_BDF)
    out = {}
    for ch in chars:
        g = glyphs.get(ord(ch))
        bits = np.zeros((DRAW_ROWS, 16), dtype=np.uint8)
        if not g:
            print(f"경고: {ch!r} 글리프 없음")
        else:
            w, h, xo, yo, rows = g
            top = ascent - (yo + h) + GALMURI_DY
            nb = ((w + 7) // 8) * 8
            for r, v in enumerate(rows):
                y = top + r
                if 0 <= y < DRAW_ROWS:
                    for x in range(w):
                        if v & (1 << (nb - 1 - x)):
                            px = x + xo
                            if 0 <= px < 16:
                                bits[y, px] = 1
        out[ch] = np.packbits(bits, axis=1).tobytes()  # DRAW_ROWS*2 = GLYPH
    return out


def compress_font(glyph_list):
    """행-마스크 압축: 글리프당 [2B 마스크(LE) + 비영 15행들(각 2B)].
    마스크 비트 r(LSB=행0)=행 r이 비지 않음. 빈 행(0x0000)은 저장 생략 → 디코더가 0으로 채움.
    네이티브 30B raw 5730B → ~3986B(안전영역 4084B에 수납). 디코더 스텁(0x80025414)이 역변환."""
    out = bytearray()
    for gb in glyph_list:
        rows = [gb[r * 2 : r * 2 + 2] for r in range(15)]
        mask = 0
        for r in range(15):
            if rows[r] != b"\x00\x00":
                mask |= 1 << r
        out += struct.pack("<H", mask)
        for r in range(15):
            if rows[r] != b"\x00\x00":
                out += rows[r]
    return bytes(out)


# 문장부호 → 게임 전각 심볼(SJIS) — BIOS 글리프 그대로 사용(별도 경로)
PUNC = {",": b"\x81\x43", ".": b"\x81\x44", "…": b"\x81\x63", "!": b"\x81\x49", "?": b"\x81\x48"}

# 내레이션 50줄 — 정발판(originals/kr/dos-ed1/OPENING.EXE) 원문 우선.
# JP(PS1)에만 있고 정발에 없는 부분(다섯 나라 11~13행·몬스터 습격 확장 26~40행)은
# 정발 어투로 새로 번역.
# 표기 규칙(유저 확정): 쉼표 뒤 공백 없음(쉼표도 전각 슬롯이라 공백까지 두면 여백 과대),
# 문장 끝 마침표 일관 추가. 각 줄 ≤MAX_SLOTS(21) — advance 3유닛 기준 필드(64유닛) 한계.
# 바이트 예산이 영역(0x974~0xEEE, 1402B)에 거의 꽉 참(빌드 출력의 '여유' 확인) — 늘릴 땐 다른 줄을 줄여야 함.
# [(슬롯 오프셋, KR 내레이션)] 50줄 — textmap/opening.json 파생(행별 편차 사유는 note 필드).
LINES = off_pairs("opening")
MAX_SLOTS = 21  # 필드 64유닛 ÷ advance 3 = 21전각 (초과 시 앞뒤 잘림)
FIELD = 64  # 표시 필드 폭(유닛). 폭측정·표시 루프가 같은 단위로 센다
ADV_WIDE, ADV_NARROW = 3, 2  # 전각 / 반각 advance(유닛)
# 반각으로 낼 글자 — 렌더러에 **이미 있는 advance 2 경로**를 빌린다. 원본은 전각공백과
# 좁은 라틴(ｆｉｊｌ) 다섯 코드를 하드코딩 비교해 2유닛만 진행하는데, 그 상수를 우리
# 글자의 슬롯 SJIS 로 바꿔치면 코드 추가 없이 반각이 된다(트램폴린 불필요).
# ⚠ 다섯 자리뿐이다. 늘리려면 비교 체인을 새로 짜야 한다.
NARROW = " .,!?"


def units(s):
    """줄의 표시 폭(유닛). 반각 글자는 2, 그 밖은 3."""
    return sum(ADV_NARROW if c in NARROW else ADV_WIDE for c in s)


def kuten_to_sjis(ku, ten):
    """1-based (구,점) → SJIS 2바이트."""
    if ku % 2:  # 홀수 구
        s2 = 0x3F + ten + (1 if ten >= 64 else 0)  # 0x7F 건너뜀
    else:
        s2 = 0x9E + ten
    s1 = 0x81 + (ku - 1) // 2 if ku <= 62 else 0xC1 + (ku - 63) // 2
    return (s1 << 8) | s2


def index_to_sjis(idx):
    """JIS 선형 인덱스 → SJIS (연속 인덱스용 역변환)."""
    ku, ten = idx // 94 + 1, idx % 94 + 1
    return kuten_to_sjis(ku, ten)


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
    return b"".join(struct.pack(">H", slot[ch][0]) for ch in s) + b"\x0a"


def w32(op, off, val):
    op[off : off + 4] = struct.pack("<I", val)


def main():

    if not os.path.exists(SRC):
        raise SystemExit(f"KR 이미지 없음 — build.py 먼저 실행\n  기대: {SRC}")
    op = bytearray(extract(OP_LBA, OP_SIZE, path=SRC))

    # 사용 문자 수집 — 한글뿐 아니라 부호·숫자·공백도 전부 슬롯화(렌더 폭측정 일치).
    syl = set()
    for _, kr in LINES:
        syl.update(kr)
    slot = build_slots(syl)
    n = len(syl)
    print(f"고유 음절 {n}, 네이티브 폰트 {n * GLYPH}B(raw)")

    # 1) 폰트를 네이티브 30B로 생성 → 행-마스크 압축 → 안전 0영역에 임베드.
    #    (raw 5730B는 안전영역 초과 → 압축본 ~3986B만 파일에 둔다. 스텁이 자유 RAM에 푼다.)
    glyphs = gen_glyphs(sorted(syl))  # 30B/글리프(15행)
    comp = compress_font([glyphs[ch][:GLYPH] for ch in sorted(syl)])
    assert len(comp) <= COMP_FONT_MAX, f"압축폰트 {len(comp)}B > 안전 {COMP_FONT_MAX}B"
    op[COMP_FONT_FILE_OFF : COMP_FONT_FILE_OFF + len(comp)] = comp
    print(
        f"압축 폰트 {len(comp)}B 임베드 파일 0x{COMP_FONT_FILE_OFF:X} (로드 RAM 0x{COMP_FONT_LOAD:08X})"
    )

    # 1b) 내레이션 재삽입 — 저주소 텍스트 영역 내 재packing.
    #     원본은 각 줄이 고정 오프셋(포인터테이블 1:1)이라 초과줄이 제자리 예산을 넘쳤다. 하지만
    #     전체 KR < 영역이므로, 49줄을 영역 안에 통째로 다시 깔고 포인터를 갱신하면 다 들어간다.
    #     스크립트(0x145A0)가 주소 범위로 text/command를 가르므로 반드시 저주소(0x8001xxxx) 유지.
    #     원본 배치(표시순=내림차순 주소) 보존 위해 영역 상단부터 아래로 팩. 렌더 lhu 위해 2B 정렬.
    def jp_len(o):
        e = o
        while op[e]:
            e += 1
        return e - o

    def find_ptr(ram):
        for i in range(0x14000, 0x15000, 4):
            if struct.unpack("<I", op[i : i + 4])[0] == ram:
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
    POOLS = [(0x868, 0x8CC), (0x8D0, 0x938)]  # 204B
    ptr_pos = {}  # 갱신 전 원주소로 포인터 위치 선수집(신주소가 타 원주소와 충돌 시 오매칭 방지)
    for off in line_offs:
        pi = find_ptr(TADDR + (off - 0x800))
        if pi is None:
            raise SystemExit(f"포인터 못찾음 줄 0x{off:X}")
        ptr_pos[off] = pi
    # 본영역 + 보조 풀 클리어(구 JP 데이터 제거). ⚠ 두 범위를 **따로** 지운다 — 사이의
    # 0x938~0x973 은 포인터 테이블이라 통째로 지우면 오프닝이 죽는다(실측 2026-08-02).
    # 0x864~0x938 전체를 지워야 오류문 선두 4B 도 0이 되어 빈 문자열이 된다.
    for lo, hi in ((0x864, 0x938), (region_lo, region_hi)):
        for k in range(lo, hi):
            op[k] = 0
    # 본영역을 위에서 아래로 채우고, 모자라면 보조 풀로 넘어간다. 줄마다 포인터가 따로
    # 있으므로 배치 순서·연속성은 상관없다(스크립트는 값의 주소 대역만 본다 — 전부 0x8001xxxx).
    # ⚠ 풀을 순서대로 소진하면 전환할 때마다 자투리(최대 한 줄분)가 버려진다. 줄마다
    # 포인터가 따로라 배치 순서는 자유이므로 **first-fit** 으로 모든 풀을 계속 살려 둔다.
    pools = [(region_lo, region_hi), *POOLS]
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

    # 2) PC0 진입점 훅: 저작권 문자열 자리에 디코더 스텁을 넣고 헤더 PC0를 스텁으로.
    #    (a) 압축 폰트(COMP_FONT_LOAD)를 자유RAM(FONT_RUNTIME)에 네이티브 30B로 전개(행-마스크).
    #    (b) 원PC0 점프. (로더 b_size=0라 소스는 PC0 시점 온전 → 게임 힙클리어 전에 대피)
    #    폰트 레지스터: t0=dst t1=src t2=글리프수 t3=마스크 t4=행 t5=행값.
    #    (줄은 저주소 영역 재packing이라 스텁 복사 불필요 — 폰트만 자유RAM으로 대피)
    assert n < 0x8000 and COMP_FONT_LOAD & 0xFFFF < 0x8000
    src_lo = COMP_FONT_LOAD & 0xFFFF
    pc0_hi, pc0_lo = (ORIG_PC0 >> 16) & 0xFFFF, ORIG_PC0 & 0xFFFF
    assert pc0_lo < 0x8000
    stub = [
        0x3C080000 | (FONT_RUNTIME >> 16),  # 0  lui  t0, dst_hi   (t0=FONT_RUNTIME, 하위0)
        0x3C090000 | (COMP_FONT_LOAD >> 16),  # 1  lui  t1, src_hi
        0x25290000 | src_lo,  # 2  addiu t1, t1, src_lo   (t1=COMP_FONT_LOAD)
        0x240A0000 | n,  # 3  addiu t2, r0, n         (글리프 수)
        0x952B0000,  # 4  G: lhu  t3, 0(t1)           마스크
        0x340C000F,  # 5     ori  t4, r0, 15          행 카운터
        0x25290002,  # 6     addiu t1, t1, 2          마스크 지나
        0x316D0001,  # 7  R: andi t5, t3, 1
        0x11A00003,  # 8     beq  t5, r0, WZ(+3)
        0x000B5842,  # 9     srl  t3, t3, 1  (delay)
        0x952D0000,  # 10    lhu  t5, 0(t1)
        0x25290002,  # 11    addiu t1, t1, 2
        0xA50D0000,  # 12 WZ: sh  t5, 0(t0)
        0x258CFFFF,  # 13    addiu t4, t4, -1
        0x1580FFF8,  # 14    bne  t4, r0, R(-8)
        0x25080002,  # 15    addiu t0, t0, 2 (delay)
        0x254AFFFF,  # 16    addiu t2, t2, -1
        0x1540FFF2,  # 17    bne  t2, r0, G(-14)
        0x00000000,  # 18    nop (delay)
    ]
    stub += [
        # (b) 원PC0 점프
        0x3C080000 | pc0_hi,  # lui  t0, pc0_hi
        0x25080000 | pc0_lo,  # addiu t0, t0, pc0_lo
        0x01000008,  # jr   t0
        0x00000000,  # nop
    ]
    stub_end = STUB_RAM + len(stub) * 4
    assert stub_end <= 0x800254A4, f"디코더가 setjmp 영역 침범 0x{stub_end:X}"
    for k, ins in enumerate(stub):
        w32(op, STUB_FILE_OFF + k * 4, ins)
    w32(op, 0x10, STUB_RAM)  # 헤더 PC0 → 디코더 스텁
    print(
        f"PC0 훅: 디코더@0x{STUB_RAM:08X}~0x{stub_end:X} ({len(stub)}명령) → 폰트 0x{FONT_RUNTIME:08X}"
    )

    # 3) 폰트베이스 리다이렉트 (0x8001BE84 jal / BE88 nop / BE8C addu s0,v0 → lui/addiu s0 = base).
    #    렌더는 원본 그대로(글리프 base+index×30, 15행). 행수·stride·shadow 패치 불필요.
    #    한자 index = SJIS-table[k].base+offset(@0x80024E60), index(0x889F)=0 → base=FONT_RUNTIME.
    #    디코더가 글리프0을 dst+0에 직접 쓰므로 +4 밀림 없음(과거 memcpy 방식의 잔재였음).
    fbase = FONT_RUNTIME & 0xFFFFFFFF
    hi, lo = (fbase >> 16) & 0xFFFF, fbase & 0xFFFF
    if lo & 0x8000:
        hi = (hi + 1) & 0xFFFF
    base_be84 = 0x800 + (0x1BE84 - 0x10000)
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
    for base in (0x800132E0, 0x80013704):  # 폭측정 / 표시 — ori 5개
        step = 4 if base == 0x800132E0 else 8  # 표시 쪽은 ori 사이에 beq 가 낀다
        for k, c in enumerate(codes):
            a = fo(base + k * step)
            ins = struct.unpack("<I", op[a : a + 4])[0]
            assert ins >> 26 == 0x0D, f"ori 아님 @0x{base + k * step:X}: {ins:08X}"
            w32(op, a, (ins & 0xFFFF0000) | c)
    print(f"반각 처리: {''.join(narrow)!r} → advance {ADV_NARROW}유닛 (전각 {ADV_WIDE})")

    w32(op, fo(0x80013370), 0x24840003)  # addiu a0,a0,3  (폭측정 전각, 원 +4)
    w32(op, fo(0x80013750), 0x26730003)  # addiu s3,s3,3  (표시 전각, 원 +4)
    print("글자 advance 4→3(16px→12px) — 간격 축소")

    if SRC != DST:
        shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        print(f"OPEN1.EXE: 섹터 {write_user_data(f, OP_LBA, op)}개 수정")
    write_cue(DST_CUE, os.path.basename(DST))
    print(f"완료: {DST}")


if __name__ == "__main__":
    main()
