"""타이틀 화면(「모험을 이어서 한다」)의 BIOS 한자폰트 리다이렉트 — [ed3] 전용.

이 화면은 `ED3.EXE`(대본 코드)가 아니라 **부팅 실행파일(`SLPS_012.01`)이 BIOS 한자 ROM을
그대로 불러 그린다** — `font.py`(대본 코드 → 임베드 18B 폰트)와는 **완전히 다른 파이프라인**.
문자열은 SJIS 이고 M01.DAT!MD05.BIN 안에 산다.

## 구조 (2026-09-27 라이브 검증 완료 — `write_memory` 로 실기 확인 · devlog 참조)

```
print_string(0x80012B60, a1=SJIS 포인터)
  → 0x80012EA8 (글자별 처리)
    → 0x80024DC4 (코드 → 글리프 주소, 구역별 BIOS 조회)
      → 0x800254D4 (원시 BIOS Krom2RawAdd, 미등록 코드만)
```

**리다이렉트**: `0x80024DC4` 머리를 STUB 로 분기시킨다. STUB 는 우리가 재배정한 코드
(`0x889F`~)면 임베드 30B/1bpp 글리프 주소를 돌려주고, 아니면 원래 두 명령
(`addiu sp,-0x20`·`sw s1,0x14(sp)`)을 실행하고 원 흐름으로 돌아간다.

## 왜 코드를 새로 판다(0x889F~) — 원본 가나·기호 코드 재사용 금지

라이브 검증 1차 시도는 원본 코드(メ=0x8381 등)를 그대로 재배정 트리거로 썼다. **위험하다** —
이 코드표는 이 화면 전역에서 쓰인다. 다른 글자가 우연히 같은 코드를 쓰면 **엉뚱한 데서도
한글이 튄다.** 그래서 **아무도 안 쓰는 사구역**(0x889F~, JIS 1수준 한자 시작대 — 유효 검사 범위 안)을
새로 배정해, 우리가 문자열 바이트도 같이 쓰는 자리에서만 튄다.

## 임베드 데이터는 어디서 오나 — PC0 훅 (ED1 `patch_opening_font.py` 와 같은 수법)

`0x801F0000`(안전 RAM, 라이브로 전 구간 쓰기 0건 확인)은 **디스크가 안 채운다** —
SLPS_012.01 의 `t_size` 는 `0x8005B800` 에서 끝난다(PS-EXE 헤더 실측). 그 위는 BIOS 가
로드하지 않는 생 RAM 이라, 화면에 쓰기 전에 **누군가 거기 데이터를 옮겨 둬야 한다.**

`pc0`(0x80011C70, 게임의 첫 명령)를 훅해 **부팅 즉시 1회** 임베드 페이로드(글리프 스텁 +
폰트 데이터)를 자유 RAM 으로 복사한다. 원본 pc0 의 처음 두 명령은
`lui v0,0x8005 / addiu v0,v0,0x0770`(BSS 클리어 시작 주소 계산) — **복사 스텁 꼬리에서
그대로 재현한 뒤** pc0+8 로 돌아간다.

임베드 페이로드의 **소스**는 `0x80050800`(파일 오프셋 0x41000) — SLPS_012.01 자신의 꼬리
0런 구역이다. 이 구역은 **런타임엔 스크래치 힙으로 쓰이지만(라이브 실측, 쓰기 46,000+건),
pc0 가 첫 명령이라 우리 복사가 끝날 때까지 아무도 못 건드린다.** 복사가 끝난 뒤 그 자리가
스크래치로 재사용돼도 상관없다 — 우리 데이터는 이미 목적지(0x801F0000)에 있다.

## 검증 (2026-09-27)

- `write_memory` 로 실기 라이브 검증: 페이지 목록에서 커서를 움직일 때마다 다시 그려지는
  「データがありません」을 재배정 8자로 「데이터가없습니다」로 렌더 — **exec 브레이크로
  print_string 재호출 확인, 화면 캡처로 렌더 확인.**
- 이 모듈은 그 검증을 **재빌드 스텁**으로 옮긴 것 — 아직 실물 디스크로 안 구웠다.
  ⚠ **부팅 경로 패치라 신중하게**: `write_memory`+`disassemble` 로 실기 역어셈블 검산 완료
  (`patch_opening_font.verify_asm` 과 같은 규율 — 오프라인 단위테스트는 조립 결과의 길이·
  정렬만 본다, `tools/tests/test_patch_title_font.py`).

## 아직 안 붙인 것 (다음 회차)

- **はい／いいえ** — MD05.BIN 에 없다. 다른 자리(공용 예/아니오 리소스?)로 추정, 미확인.
- **슬롯 지명(「ラグピック村」)** — 세이브 데이터 조회로 보인다(고정 문자열 아님). 세이브
  슬롯 이름이 그려지는 순간에 실행 브레이크를 걸어 조회 경로를 역추적해야 한다.
- **メモリーカードのチェック中** — 화면 재현 경로를 못 찾았다(체크 단계에서 한 번만 그려지고
  프레임버퍼에 남는다). 문자열 자리·예산은 이미 확정했으니 **재빌드로 구운 뒤 정식 부팅으로
  확인**하면 된다(라이브 write_memory 반복 재현보다 이쪽이 빠르다).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common

from shared.fonts import galmuri

# ✅ 2026-10-05 — 정식 빌드에 켠다(마스터 실기 확인: 이어서 하기 · 페이지 목록 · 지명 · 예／아니오 · 로드까지 정상).
# 🔴 09-28 에 껐던 것은 실기에서 「이어서 하기」 선택이 안 먹고 방향키까지 먹통이던 회귀였다. 원인은 둘이었다 —
#    ① 부팅 복사 루프의 R3000 로드 지연 위반 ② 글리프 스텁이 4B 경계에 안 놓여 `j` 가 하위 2비트를 버린 것.
#    둘 다 고쳤고(테스트가 지킨다) 글꼴도 memset 에 안 지워지는 멤버 꼬리로 옮겼다. 자세한 건 devlog 2026-10-05.
ENABLED = True
# 분해 시험용 — 환경변수 `ED_TITLE_FONT=base` 면 훅 + 글꼴 데이터만(문자열은 원문 그대로)이다.
#   멈춤이 다시 나면 어느 조각에서 나는지 가르려는 것이다(2026-10-05). `full`(= 기본)과 `off` 는 같은 뜻.
import os as _os

MODE = _os.environ.get("ED_TITLE_FONT", "off")

EXE_PATH = "/SLPS_012.01"
T_ADDR = 0x80010000
T_HEADER = 0x800  # PS-EXE 헤더 길이 — file_off = T_HEADER + (ram - T_ADDR)

HOOK_ADDR = 0x80024DC4  # 글리프 조회 래퍼 머리
RESUME_ADDR = 0x80024DCC  # 원 명령 둘(addiu sp / sw s1) 다음
# 🔴 2026-10-05 — 글꼴·스텁은 **타이틀 오버레이(MD05.BIN) 꼬리의 섹터 여유**에 둔다. 처음엔 부팅 때(pc0)
#    0x801F0000 으로 복사했는데, main 이 곧바로 그 구간(0x801F0000~+0xDC43, main 의 지역 변수)을
#    memset 으로 0 으로 민다 — 먹통은 풀렸어도 글꼴이 지워져 한글이 **빈칸**으로 나왔다. 오버레이 안이면
#    디스크가 직접 채우니 복사 코드(= 로드 지연 사고를 낸 루프)도 필요 없다.
MD05_NAME = "MD05.BIN"
OVERLAY_RAM = 0x80088000  # MD05.BIN 이 올라오는 자리(devlog 실측)
MD05_SIZE = 27409  # TOC 가 적은 크기 — 그 뒤 섹터 여유(다음 멤버 시작까지)가 우리 자리다
MD05_SLOT = 28672  # 다음 멤버(TIM\\GMF_S.TIM)까지 — 14 섹터. apply 가 TOC 로 다시 검산한다
FONT_DEST = OVERLAY_RAM + ((MD05_SIZE + 3) & ~3)  # 워드 정렬(스텁 시작이 4B 경계여야 한다)

CELL = 16  # BIOS 한자 셀 폭(px) — 실제 글리프는 더 좁아 DX 로 가운데 둔다
DX = 0  # Galmuri14 는 열 1~14 를 쓴다 — 16칸 셀 가운데(마스터 2026-10-05: 9px 는 작다)
DY = -3  # Galmuri14 는 행 4~17 — 15행 셀(0~14)에 1~14 로 앉힌다

# 재배정 코드 0x889F~ (JIS 1수준 한자 시작대 — 이 화면 문구엔 안 나온다) → 우리 글리프.
# 🔴 사구역(0xF040~)이 **아니다**(2026-10-05): 글자 출력 루프가 글자마다 유효 검사(0x80012DE0 —
#    `(code+0x7EC0)&0xFFFF < 0x1731` = 0x8140~0x9870)를 하고 범위 밖은 **전부 공백(0x8140)으로 바꾼다.**
#    사구역으로 짠 문자열이 빈칸으로 나온 원인이다(첫 라이브 시험은 이 검사를 안 거치는 줄이라 통과했다).
GLYPHS = [
    "메",
    "모",
    "리",
    "카",
    "드",
    "체",
    "크",
    "중",  # 메모리카드 체크중
    "로",
    "합",
    "니",
    "다",  # 로드합니다 (드·니는 위·아래서 재사용)
    "괜",
    "찮",
    "까",  # 괜찮습니까(습·니 는 아래·위에서 재사용) — 정본 「괜찮습니까?」(ED1·ED2 와 맞춤, 마스터 10-08)
    "페",
    "이",
    "지",  # 페이지
    "기",
    "록",
    "없",
    "습",  # 기록이 없습니다. (이·니·다 는 위에서 재사용)
]
CODE_BASE = 0x889F
CODE = {ch: CODE_BASE + i for i, ch in enumerate(GLYPHS)}
SP = 0x8140  # 기존 전각 공백 — 원본도 이미 이 코드로 공백을 찍는다, 재배정 불필요


def _c(ch):
    """문자 하나 → SJIS 코드 2바이트(재배정 코드거나 기존 공백)."""
    return struct.pack(">H", CODE.get(ch, SP))


def _fullwidth(u):
    """숫자·물음표는 **전각 SJIS**(0x824F+n · 0x8148)로 쓴다 — 출력 루프는 글자마다 2바이트를 읽어
    (0x80012C68) 반각 `0x31 0x00` 은 유효 검사에서 떨어져 공백이 된다(2026-10-05, 숫자가 사라졌다)."""
    if u == "?":
        return struct.pack(">H", 0x8148)
    if u == ".":
        return struct.pack(">H", 0x8144)  # ． 전각 마침표(원문은 。 0x8142 — 한국식 모양)
    return struct.pack(">H", 0x824F + int(u))


def encode_string(units):
    """[문자 또는 리터럴바이트, ...] → NUL 종결 바이트열. 전부 2바이트(재배정 코드 · 전각 숫자/물음표 · 공백)."""
    out = bytearray()
    for u in units:
        out += _fullwidth(u) if len(u) == 1 and u in "0123456789?." else _c(u)
    out += b"\x00\x00"
    return bytes(out)


# M01.DAT 절대 오프셋(devlog 실측, 원문 예산 안) — RAM 0x80088000 + 멤버오프셋
STRINGS = {
    0x8F0D5: (13, encode_string(["메", "모", "리", "카", "드", " ", "체", "크", "중"])),
    0x8F09B: (7, encode_string(["로", "드", "합", "니", "다", "."])),
    0x8F0AB: (8, encode_string(["괜", "찮", "습", "니", "까", "?"])),
}
# " " 는 기존 전각 공백 코드로 처리 — encode_string 은 ' ' 를 CODE 에서 못 찾으면 SP 로 폴백한다
PAGE_BASE = 0x8EF8B
PAGE_STRIDE = 14
for _n in range(1, 9):
    STRINGS[PAGE_BASE + (_n - 1) * PAGE_STRIDE] = (
        6,
        encode_string(["페", "이", "지", " ", str(_n)]),
    )
for _off, (_budget, _data) in STRINGS.items():
    assert len(_data) <= _budget * 2 + 2, f"0x{_off:X}: 예산 초과 {len(_data)} > {_budget * 2 + 2}"


# SLPS_012.01 안 문자열(RAM 주소) — 「データがありません」 한 줄(@6 색 + 전각 공백 + 9칸 + @%x).
# 원문 9칸과 같은 9칸으로 쓴다(길이 고정): 「기록이 없습니다.」 — ED3.EXE 쪽 문안과 같다.
SLPS_DATA_STR = 0x80010BE8
SLPS_DATA_ORIG = b"@6\x81\x40" + "データがありません".encode("cp932") + b"@%x\x00"


def slps_data_string():
    text = b"".join(_c(ch) if ch != "." else _fullwidth(".") for ch in "기록이 없습니다.")
    assert len(text) == 18
    return b"@6\x81\x40" + text + b"@%x\x00"


REG = {
    "zero": 0,
    "at": 1,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "t5": 13,
    "t6": 14,
    "t7": 15,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
    "s4": 20,
    "s5": 21,
    "s6": 22,
    "s7": 23,
    "t8": 24,
    "t9": 25,
    "k0": 26,
    "k1": 27,
    "gp": 28,
    "sp": 29,
    "fp": 30,
    "ra": 31,
}


def _i(op, rs, rt, imm):
    return struct.pack("<I", (op << 26) | (REG[rs] << 21) | (REG[rt] << 16) | (imm & 0xFFFF))


def _addiu(rt, rs, imm):
    return _i(0x09, rs, rt, imm)


def _ori(rt, rs, imm):
    return _i(0x0D, rs, rt, imm & 0xFFFF)


def _andi(rt, rs, imm):
    return _i(0x0C, rs, rt, imm & 0xFFFF)


def _bne(rs, rt, off_words):
    return _i(0x05, rs, rt, off_words)


def _sltiu(rt, rs, imm):
    return _i(0x0B, rs, rt, imm)


def _beq(rs, rt, off_words):
    return _i(0x04, rs, rt, off_words)


def _r(rs, rt, rd, shamt, funct):
    return struct.pack(
        "<I", (REG[rs] << 21) | (REG[rt] << 16) | (REG[rd] << 11) | (shamt << 6) | funct
    )


def _sll(rd, rt, sh):
    return _r("zero", rt, rd, sh, 0x00)


def _addu(rd, rs, rt):
    return _r(rs, rt, rd, 0, 0x21)


def _subu(rd, rs, rt):
    return _r(rs, rt, rd, 0, 0x23)


def _sw(rt, off, rs):
    return _i(0x2B, rs, rt, off)


def _lw(rt, off, rs):
    return _i(0x23, rs, rt, off)


def _lb(rt, off, rs):
    return _i(0x20, rs, rt, off)


def _lbu(rt, off, rs):
    return _i(0x24, rs, rt, off)


def _sb(rt, off, rs):
    return _i(0x28, rs, rt, off)


def _lui(rt, imm):
    return _i(0x0F, "zero", rt, imm)


def _jimm(target):
    return struct.pack("<I", (0x02 << 26) | ((target >> 2) & 0x03FFFFFF))


def _jr(rs):
    return struct.pack("<I", (REG[rs] << 21) | 0x08)


def _nop():
    return struct.pack("<I", 0)


def _pack_bios_cell(ch):
    """Galmuri14 → 16×15 1bpp, 30B. 9px 는 작아 보인다는 마스터 피드백(2026-10-05)으로 14px 로 키웠다."""
    f = galmuri("Galmuri14")
    bits = f.bits(ch, dx=DX, dy=DY, rows=15, width=16)
    out = bytearray()
    for row in bits:
        v = 0
        for i, b in enumerate(row):
            if b:
                v |= 0x8000 >> i
        out += struct.pack(">H", v)
    assert len(out) == 30
    return bytes(out)


def _rows(ch):
    """글리프 하나 → 15행의 16비트 행 값(큰 끝) — `_pack_bios_cell` 과 같은 그림."""
    cell = _pack_bios_cell(ch)
    return [cell[i : i + 2] for i in range(0, 30, 2)]


# 🔴 글꼴은 **행 사전 + 색인**으로 싣는다(2026-10-05). 30B 셀로는 지명 86개의 음절(156자)이
#    자리에 안 들어간다(필요 4.7KB · 자리 3.7KB). 갈무리14 의 한글 156자는 **서로 다른 행이 132개**뿐이라
#    「행 하나 = 1바이트 색인」 이면 글자당 15B + 사전 264B 로 줄어든다(≈2.6KB).
#    조회 때 스텁이 그 글자를 30B 셀로 펼쳐 그 주소를 돌려준다.
#    🔴 **글자마다 제 칸**(`CELL_CACHE + idx*30`)에 펼친다. 처음엔 셀 버퍼 하나를 돌려 썼는데 화면에
#       「지지지 1」「을을을 을을」처럼 **한 줄이 전부 마지막 글자**로 나왔다 — 호출자는 한 줄의 셀 주소를
#       먼저 다 모으고 나서 그린다(2026-10-05 스테이트 주입 실측). 칸이 따로면 몇 번을 불러도 안 겹친다.
#
# 자리는 셋이다 — 모두 **디스크가 섹터째 읽어 오는 멤버 꼬리**(0 패딩)이고, 타이틀 동안 같은 주소에
# 머문다(스테이트 넷 · 새 부팅 표지 실측 — devlog 2026-10-05 밤 3):
#   A  MD05.BIN 꼬리   RAM FONT_DEST~         스텁 + 셀 버퍼 + 행 사전 + 앞쪽 글자들
#   B  YUKI8.TIM 꼬리  RAM 0x80199194~ 1384B
#   C  DATA5.BIN 꼬리  RAM 0x80193C20~ 1044B
# 🔴 B·C 는 힙에 올라온 멤버라 주소가 **할당 순서에 달렸다** — 네 상태(오프닝을 본 것·건너뛴 것)에서
#    같았지만 실기 확인 전까지는 가설이다. 어긋나면 그 자리 글자만 깨지고(빈칸·엉뚱한 모양) 멈추진 않는다.
TAILS = (
    # (멤버, TOC 크기, 다음 멤버까지, 멤버가 올라오는 RAM)
    ("TIM\\YUKI8.TIM", 664, 2048, 0x80198EFC),
    ("DATA5.BIN", 261100, 262144, 0x80154034),
)
GLYPH_BYTES = 15
STUB_WORDS = 49
# 펼친 셀이 사는 곳 — 쓰기만 하는 RAM(디스크에서 안 채운다). 타이틀 동안 0 인 구간
# 0x8006D000~0x80080000(76KB) 안이다: 스테이트 넷에서 0 이고, SLPS·MD05 코드가 이 구간을 가리키는
# 정적 참조가 없다(lui/addiu 쌍 전수, devlog 2026-10-05 밤 3). ⚠ 그래도 가설이다 — 실기 확인 대기.
CELL_CACHE = 0x8007D000


def build_payload(glyphs):
    """({"a": MD05 꼬리, 멤버이름: 그 꼬리 바이트 …}, 스텁 시작 주소) — 스텁은 A 맨 앞."""
    dict_rows = sorted({r for ch in glyphs for r in _rows(ch)})
    assert len(dict_rows) <= 256, f"행 사전이 1바이트 색인을 넘는다 ({len(dict_rows)})"
    ridx = {r: i for i, r in enumerate(dict_rows)}
    enc = [bytes(ridx[r] for r in _rows(ch)) for ch in glyphs]

    dict_at = FONT_DEST + STUB_WORDS * 4
    assert CELL_CACHE + 30 * len(glyphs) <= 0x80080000, "셀 칸이 빈 구간을 넘는다"
    glyph_a = dict_at + 2 * len(dict_rows)
    segs = [(glyph_a, (OVERLAY_RAM + MD05_SLOT - glyph_a) // GLYPH_BYTES)]
    for _nm, size, slot, ram in TAILS:
        segs.append((ram + size, (slot - size) // GLYPH_BYTES))
    counts, left = [], len(glyphs)
    for _base, cap in segs:
        counts.append(min(cap, left))
        left -= counts[-1]
    assert left == 0, f"글자 자리 부족 ({len(glyphs)}자, {left}자 남음)"

    def li(r, v):
        return _lui(r, v >> 16) + _ori(r, r, v & 0xFFFF)

    st = bytearray()
    st += _andi("t0", "a0", 0xFFFF)
    # addiu 즉치는 부호 16비트라 -0x889F 가 안 들어간다(0x7761 = +30561 로 읽혔다) — 둘로 나눈다.
    st += _addiu("t0", "t0", -0x4000)
    st += _addiu("t0", "t0", -(CODE_BASE - 0x4000))
    st += _sltiu("v1", "t0", len(glyphs))
    beq_at = len(st)
    st += _beq("v1", "zero", 0)  # → fallback (아래서 채운다)
    st += _sll("t5", "t0", 5)  # 지연 슬롯: t5 = idx*32
    st += _sll("t2", "t0", 1)
    st += _subu("t5", "t5", "t2")  # idx*30
    # 자리 고르기: idx < n 이면 그 자리, 아니면 n 을 빼고 다음 자리
    bnes = []
    for k, (base, _cap) in enumerate(segs):
        st += li("t1", base)
        if k == len(segs) - 1:
            break
        st += _sltiu("v1", "t0", counts[k])
        bnes.append(len(st))
        st += _bne("v1", "zero", 0)  # → L1
        st += _nop()
        st += _addiu("t0", "t0", -counts[k])
    l1 = len(st)
    for at in bnes:
        st[at : at + 4] = _bne("v1", "zero", (l1 - (at + 4)) // 4)
    # L1: t1 += idx*15
    st += _sll("t2", "t0", 4)
    st += _subu("t2", "t2", "t0")
    st += _addu("t1", "t1", "t2")
    st += li("t3", dict_at)
    st += li("v0", CELL_CACHE)
    st += _addu("v0", "v0", "t5")  # 이 글자의 셀 칸
    st += _addiu("t4", "zero", 15)
    st += _addu("t5", "v0", "zero")
    # loop: 행 색인 → 사전의 2바이트(큰 끝)를 그대로 셀에 옮긴다
    loop_at = len(st)
    st += _lbu("t2", 0, "t1")
    st += _addiu("t1", "t1", 1)
    st += _sll("t2", "t2", 1)
    st += _addu("t2", "t2", "t3")
    st += _lbu("t6", 0, "t2")
    st += _lbu("t7", 1, "t2")
    st += _sb("t6", 0, "t5")
    st += _sb("t7", 1, "t5")
    st += _addiu("t4", "t4", -1)
    st += _bne("t4", "zero", (loop_at - (len(st) + 4)) // 4)
    st += _addiu("t5", "t5", 2)  # 지연 슬롯
    st += _jr("ra")
    st += _nop()
    fb_at = len(st)
    st[beq_at : beq_at + 4] = _beq("v1", "zero", (fb_at - (beq_at + 4)) // 4)
    st += _addiu("sp", "sp", -0x20 & 0xFFFF)
    st += _sw("s1", 0x14, "sp")
    st += _jimm(RESUME_ADDR)
    st += _nop()
    assert len(st) == STUB_WORDS * 4, len(st) // 4

    parts = {}
    i = counts[0]
    parts["a"] = bytes(st) + b"".join(dict_rows) + b"".join(enc[:i])
    for (nm, *_r), n in zip(TAILS, counts[1:], strict=True):
        parts[nm] = b"".join(enc[i : i + n])
        i += n
    return parts, FONT_DEST


def build_hook_patch():
    return _jimm(FONT_DEST) + _nop()


# ── 슬롯 지명 표 — SLPS 안 86칸 × 16B(전각 6자 + NUL 4). 세이브엔 맵 번호만 있고 이름은 여기서 뽑는다.
PLACE_TABLE = 0x80010624
PLACE_COUNT = 86
PLACE_STRIDE = 16
PLACE_CELLS = 6  # 원문이 쓰는 칸(`%-12s` 가 이만큼 채운다)
# 🔴 칸은 16B 라 7자(14B) + 종결도 들어가지만 **줄이 잘린다** — 「수정호 오솔길 00:02:28 1」 처럼
#    끝의 「LV」 가 사라졌다(2026-10-05 스테이트 주입 실측, 줄 버퍼 길이가 고정이다). 그래서 6자에서 끊고
#    넘는 이름은 띄어쓰기를 뺀다(지금은 「수정호오솔길」 하나뿐이다 — 대사·본체 표엔 안 나오는 이름).
PLACE_MAX = 6
# 열쇠 목록(glossary_keys_ed3.json 의 place)에 없는 둘 — 실행파일 지명 표엔 없고 이 타이틀 표에만 있다.
# 마스터 확정(10-05): 표기는 둘 다 맞다. 지명은 띄어쓰기를 살린다 — DOS 정발판 HUD 의 「독늪지대」는
# 정발이 칸 예산으로 붙인 것이고 우리 정본 규칙(띄어쓰기 + 칸이 모자랄 때만 붙임)과 다르다.
# 슬롯 지명 중 낱말 표 열쇠(`glossary_keys_ed3.json`)에 없는 둘 — 표기는 사전에서 읽는다(열쇠만 둔다).
PLACE_EXTRA = ("冬至の路", "毒沼地帯")


def _place_kr(jp):
    import glossary

    kr = glossary.load("ed3")["categories"]["place"].get(jp)
    if kr is None and jp in PLACE_EXTRA:
        kr = glossary.lookup_shared("ed3", jp, "place")
    if kr is None or not all("가" <= c <= "힣" or c == " " for c in kr):
        return None  # 「Ｆａｌｃｏｍ」 같은 칸은 원문 그대로 둔다
    if len(kr) > PLACE_MAX:
        kr = kr.replace(" ", "")  # 칸 예산 — 띄어쓰기부터 뺀다(실행파일 낱말 표와 같은 규칙)
    assert len(kr) <= PLACE_MAX, f"{jp} → {kr}: {PLACE_MAX}칸 초과"
    return kr


def place_entries(exe):
    """[(RAM 주소, 원문, 우리 표기|None)] — 표를 원본에서 읽는다(원문은 커밋하지 않는다)."""
    out = []
    for i in range(PLACE_COUNT):
        ram = PLACE_TABLE + i * PLACE_STRIDE
        off = T_HEADER + (ram - T_ADDR)
        raw = bytes(exe[off : off + PLACE_STRIDE])
        assert raw[12:] == bytes(4), f"0x{ram:08X}: 지명 칸 규격이 다르다"
        jp = raw[:12].decode("cp932").replace("\u3000", "")
        out.append((ram, jp, _place_kr(jp)))
    return out


def all_glyphs(entries):
    extra = sorted({c for _, _, kr in entries if kr for c in kr if c != " "} - set(GLYPHS))
    return GLYPHS + extra


def encode_place(kr, code):
    """가운데 맞춤(원문과 같은 규칙: 왼쪽 여백 = 남는 칸 // 2) · 전각 공백으로 6칸을 채운다."""
    pad = max(0, PLACE_CELLS - len(kr))
    cells = [" "] * (pad // 2) + list(kr) + [" "] * (pad - pad // 2)
    out = b"".join(struct.pack(">H", code.get(c, SP)) for c in cells)
    return out.ljust(PLACE_STRIDE, b"\x00")  # 칸 전체(16B) — 7자면 종결 2B 만 남는다


def apply(disc, base_arcs=None):
    """(패치한 문자열 수, {파일경로: 새 바이트열}) — SLPS_012.01 + M01.DAT.

    `base_arcs` — 이미 다른 패치(그림 등)가 손댄 아카이브 바이트가 있으면 그 위에 문자열을
    얹는다. 🔴 **`arcs.setdefault` 로 병합하면 안 된다** — M01.DAT 는 그림 자리표
    (`graphics_ed3.json`)도 같은 파일을 쓸 수 있어, 먼저 온 쪽만 남고 나머지가 조용히
    사라진다(`build.py` 가 이 함수를 그림 병합 **뒤에** 부르고 그 결과를 넘긴다).
    """
    if disc != "ed3" or not (ENABLED or MODE in ("base", "full")):
        return 0, {}

    base_arcs = base_arcs or {}
    fs = common.iso_files(disc)
    if EXE_PATH in base_arcs:
        exe = bytearray(base_arcs[EXE_PATH])
    else:
        exe_lba, exe_size = fs[EXE_PATH]
        exe = bytearray(common.read_lba(disc, exe_lba, exe_size))

    def poke(ram_addr, data):
        off = T_HEADER + (ram_addr - T_ADDR)
        assert 0 <= off < len(exe), f"0x{ram_addr:08X}: SLPS_012.01 범위 밖"
        exe[off : off + len(data)] = data

    places = place_entries(exe) if MODE != "base" else []
    glyphs = all_glyphs(places)
    code = {ch: CODE_BASE + i for i, ch in enumerate(glyphs)}
    parts, _entry = build_payload(glyphs)

    poke(HOOK_ADDR, build_hook_patch())
    # 「データがありません」 → 「기록이 없습니다.」 (길이 고정 — 원문과 검산)
    off = T_HEADER + (SLPS_DATA_STR - T_ADDR)
    assert bytes(exe[off : off + len(SLPS_DATA_ORIG)]) == SLPS_DATA_ORIG, "SLPS 문자열이 달라졌다"
    if MODE != "base":
        poke(SLPS_DATA_STR, slps_data_string())
    for ram, _jp, kr in places:
        if kr is not None:
            poke(ram, encode_place(kr, code))

    m01_path = next(p for p in fs if p.endswith("/M01.DAT"))
    if m01_path in base_arcs:
        m01 = bytearray(base_arcs[m01_path])
    else:
        m_lba, m_size = fs[m01_path]
        m01 = bytearray(common.read_lba(disc, m_lba, m_size))
    # 두 자리 다 멤버 경계 안(다음 멤버를 안 침범)이고 0 패딩인지 TOC 로 검산한다.
    members = {nm: (o, sz) for nm, o, sz in common.arc_parse(bytes(m01))[1]}

    def put_tail(name, size, slot, ram_base, member_ram, data):
        mo, msz = members[name]
        nxt = min(o for o, _ in members.values() if o > mo)
        assert msz == size and nxt - mo == slot, f"{name} 규격이 달라졌다"
        at = mo + (ram_base - member_ram)
        assert at + len(data) <= nxt, f"{name} 꼬리 여유 부족 {at + len(data) - nxt}B"
        assert not any(m01[at : at + len(data)]), f"{name} 꼬리가 0 이 아니다 — 남의 자료다"
        m01[at : at + len(data)] = data

    put_tail(MD05_NAME, MD05_SIZE, MD05_SLOT, FONT_DEST, OVERLAY_RAM, parts["a"])
    for nm, size, slot, ram in TAILS:
        if parts[nm]:
            put_tail(nm, size, slot, ram + size, ram, parts[nm])
    n = 0
    for off, (_budget, data) in sorted(STRINGS.items()):
        if MODE == "base":
            break
        m01[off : off + len(data)] = data
        n += 1

    return n, {EXE_PATH: bytes(exe), m01_path: bytes(m01)}
