"""sfc-ed1 렌더러 훅 — 대사 엔진이 대본 바이트를 읽는 **한 자리**를 가로채 한글을 그린다.

설계 근거는 `docs/status.md` 13.5(실기 특정). 요지:
  · `$02:DE0B  JSR $E784` 가 「대본에서 다음 바이트를 읽어 A 로」다 — 40군데 중 **여기 하나만** 바꾼다
  · 우리가 돌려준 바이트를 엔진이 칸 배열 `$0305,X` 에 넣고 `JSL $02B07B` 로 타일로 바꾼다.
    한 자 = 타일 `t` + `t+$10` 이고 **우리 글리프 규약이 정확히 그것**이라 그리기 루프는 안 고친다
  · 한글은 2바이트(`[선두][색인]`)다. 훅이 색인을 **슬롯 코드 한 바이트**로 바꿔 준다 —
    슬롯 = 「타일을 덮어써도 되는 글자 코드」(`tools/tiles.py`), 글리프는 NMI 에서 그 타일에 올린다

세 조각이다:
  1. `$02:FE52` 트램펄린 — `JSL` 로 확장 뱅크의 훅을 부르고 `RTS`(원본 `JSR` 과 크기가 같다)
  2. 확장 뱅크 `$3F:8000` — 훅 본체 + 표(선두·슬롯·조사·받침) + NMI 큐 비우기
  3. `$00:FF20` — NMI 의 `JSR $ACA9` 를 감싸 큐 비우기를 덧붙인다(빈 자리 160B)

글리프는 `$3D:8000` 에 **2bpp 32B/자**(위 타일 16B + 아래 16B, 평면1 = $FF — 원본 적재 규약)로
색인 순서대로 눕는다. VRAM 워드 = `$1000 + 8×타일`($00:91F5 실측).

⚠ VRAM 쓰기는 NMI 안에서만 한다(그 시점엔 강제 블랭크가 켜져 있다 — `$00:A9EC`).
⚠ 큐가 넘치면 **가장 오래된 것을 덮는다** — 한 프레임에 16자를 넘겨 그리는 경로는 없다.

**오프닝(D1)은 네 번째 문이다**(`docs/status.md` 13절, 2026-09-15/16 실기 특정) — 대사 엔진과
**완전히 다른 경로**(`$1E:DF44`, 인라인 `LDA [$23],y`)라 트램펄린 없이 `JSL open_fetch` 로
직접 간다. 같은 코드→타일 표(`$03:F3EC`)·같은 `JSL $02:B07B` 변환을 쓰지만 **패턴 메모리가
워드 `$3000`**(인게임은 `$1000`)이라 완전히 딴 자리다 — 그래서 슬롯 코드는 **공유**하되 큐
항목마다 컨텍스트 한 바이트(`Q_CTX`)를 더 실어 `upload()` 가 베이스를 가른다. NMI 큐 비우기도
같은 것 하나를 그대로 쓴다(오프닝·인게임은 동시에 안 돌아 충돌하지 않는다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common
import encode
import tiles
from asm65816 import Asm

HOOK_BANK = 0x3F  # 훅 코드 + 표
GLYPH_BANK = 0x3D  # 글리프 2bpp 32B/자
DICT_BANK = 0x3E  # 사전·전투 UI 문자열(`tools/dicts.py`·`battle_ui.py`)
GLYPH_BASE = (GLYPH_BANK << 16) | 0x8000
GLYPH_MAX = 1024  # 한 뱅크 = 32,768B ÷ 32B. 넘으면 뱅크를 갈라야 한다(그때 훅도 고친다)
HOOK_ORG = 0x8000
TRAMPOLINE = 0x02FE52  # 뱅크 $02 빈 자리 430B
CALL_SITE = 0x02DE0B  # JSR $E784 → JSR $FE52
# 🔴 **글자가 들어오는 문은 둘이다**(2026-09-07 실측). `$02:DDEE` 가 사전 버퍼가 켜져 있으면
# 대본 대신 **버퍼**에서 한 바이트를 집어 같은 `$173A` 로 보낸다:
#     $DDF9  LDA $174C,X / CMP #$FF / BNE $DE0E     ← 두 번째 문
#     $DE0B  JSR $E784   / STA $173A                ← 첫 번째 문(위)
# 대본만 훅하면 **사전 문자열(이름·아이템·시스템 문장)의 한글이 통째로 안 풀린다** — 색인 바이트가
# 그대로 제어코드로 읽혀 인트로가 멈췄다. 크기가 같아 `JSR` 로 갈아 끼울 수 있다.
BUF_TRAMPOLINE = 0x02FE57
BUF_CALL_SITE = 0x02DDF9  # LDA $174C,X → JSR $FE57 (셋 다 3바이트)
BUF_CURSOR = 0x176B  # 사전 버퍼 읽기 커서($02:DDF3 이 올린다)
BUF_BASE = 0x174C  # 사전 문자열 버퍼 — `$176A` 가 켜져 있는 동안만 읽는다
# 🔴 **넷째 문 — 메뉴는 사전을 아예 안 거친다**(2026-09-07 실측: 사전 뱅크에 읽기 BP 를 걸고
# 도구 목록을 열었는데 **한 번도 안 걸렸다**). 아이템·장비 이름을 그리는 세 창은 아이템 표
# `$03:EF73` 을 **직접 long,X 로 읽어** 문자열을 **칸 배열 `$0305,Y` 에 그대로 복사한다** —
# `$173A` 를 안 거치므로 앞의 두 훅이 닿지 않는다. 셋 다 **똑같은 33바이트 덩이**다:
#     LDA $03EF73,X → $06 / LDA $03EF74,X → $07 / LDA #$03 → $08
#     LDY #$00 : LDA [$06],Y : CMP #$FF : BEQ 끝 : STA $0305,Y : INY : BRA
# ⚠ 끝나면 **Y 가 채운 칸 수**여야 한다 — 뒤에 오는 `CPY #$09/$0A/$0F` 패딩 루프가 그걸 쓴다.
# ⇒ 덩이를 통째로 우리 루틴 호출로 갈아 끼운다(`JSR` + `JMP 패딩`). 한글은 두 바이트를 한 칸으로 접는다.
NAME_TRAMPOLINE = 0x02FE5C
NAME_SITES = [  # (덩이 시작, 패딩 루프 = 끝난 뒤 갈 자리)
    (0x02B10F, 0x02B132),
    (0x02B18C, 0x02B1AD),
    (0x02B387, 0x02B3A8),
]
NAME_BLOCK = 33  # 세 자리 모두 같은 길이
# 🔴 **다섯째 문 — `MVN`.** 전투 커맨드·파티 이름 여덟(13칸 고정)은 바이트를 훑는 자리가 아예
# 없다. `$02:A2DB` 가 `LDX $0006 / LDY #$0305 / LDA #$000C / MVN $02,$00` 로 **13바이트를 칸
# 배열에 통째로 옮긴다** — 한 바이트 = 한 칸이 전제라 두 바이트 한글이 못 산다.
# ⇒ 전송 자체를 우리 루프로 갈아 끼운다. ⚠ 끝나고 **DB = $00**(원본 MVN 이 남기는 값)이어야 한다.
# 자리가 **둘**이다(2026-09-07 실측) — 파티 이름 여덟(13칸)과 **타이틀 메뉴 세 줄(12칸)**.
# 둘 다 `LDX $0006 / LDY #$0305 / LDA #길이−1 / MVN $02,$00` 로 똑같이 생겼다.
# ⇒ **`MVN` 세 바이트만** `JSR` 로 갈아 끼운다(크기가 같다). 칸 수는 **호출자가 이미 A 에 넣어 준다**
#   (`LDA #$000C` / `#$000B`) — 그래서 자리마다 상수를 안 든다.
MVN_SITES = [
    (0x02A2E4, 0x02A2DE),  # 전투 커맨드·파티 이름 (13칸)
    (0x02A620, 0x02A61A),  # 타이틀 메뉴 세 줄 (12칸)
    (0x02A3A8, 0x02A3A2),  # 메시지 속도 창 サクサク/ドキドキ (4칸) — 2026-09-08
    (0x02A400, 0x02A3FA),  # 확인 창 はい/いいえ (3칸) — 2026-09-08
    (0x02ADFA, 0x02ADF4),  # A4 전투 설정 창 라벨 (6줄×10칸) — 2026-09-15, 라이브 BP 로 확인
    (0x02AF3C, 0x02AF36),  # A3 시스템 설정 창 값 (8옵션, 스트라이드 ASM ×4 확장과 함께) — 2026-09-15
]  # (MVN, 앞의 `LDY #$0305`)
MVN_LEN = 3
NAME13_TRAMPOLINE = 0x02FE61
CELL_BASE = 0x000305  # `LDY #$0305` — 패치할 때 자리마다 확인한다
CELLS = 0x000305  # 칸 배열(WRAM 미러) — long 으로 써서 DB 에 안 기댄다
NMI_CALL = 0x00AA00  # NMI 의 JSR $ACA9 → JSR (우리 스텁)
NMI_STUB = 0x00FF20  # 뱅크 $00 빈 자리 160B
NMI_ORIG = 0xACA9
QN = 16  # 글리프 큐 칸 수(2의 거듭제곱)
DRAIN_MAX = 8  # 한 프레임에 올릴 글리프 수 — 32B×2 씩이라 여유 있다
REALLOC_MARGIN = 20  # 캐시 히트인데 남은 수명이 이만큼 미만이면 새 슬롯으로 옮긴다(`alloc` 주석)

# 🔴 **여섯째 문 — 오프닝(D1)은 인게임과 완전히 다른 경로다**(2026-09-15 실기 확정, status 13절).
# `$1E:DF44 LDA [$23],y / INY / STY $1B44`(6B, 인라인 — JSR 을 거치지 않는다)가 대본에서 다음
# 바이트를 읽는 자리다. 검사 셋(`$CF`/`$E0`/`$FF`)만 알아서 우리 2바이트 선두를 모른다.
# ⇒ 6바이트를 통째로 `JSL open_fetch` + `NOP`×2 로 갈아 끼운다(트램펄린이 필요 없다 — 원래도
# `JSR` 이 아니라 인라인 코드였다). `$1E:DF41`(패치 전 줄)이 이미 `LDY $1B44` 를 해 뒀으므로
# 진입 시 Y 는 그대로 커서다.
# 글리프·슬롯 코드는 **인게임과 공유한다** — 같은 `$03:F3EC` 표를 오프닝도 그대로 쓰고(같은
# `$02:B07B` 변환 호출, 실측), 오프닝의 타일 패턴 메모리는 **워드 `$3000`**(인게임은 `$1000`)로
# 완전히 별도 자리라 겹치지 않는다(status 13절: `$1E:E6CC`·`$1E:F175` 가 시트를 그리로 따로
# 올린다). 그래서 큐 항목마다 **컨텍스트 한 바이트**(`Q_CTX`)만 더 들고 다니면 `upload()` 가
# 그 값으로 `$1000` 표/`$3000` 표를 갈라 쓸 수 있다 — 새 글리프 뱅크·새 NMI 훅이 필요 없다.
OPEN_CALL_SITE = 0x1EDF44  # LDA [$23],y / INY / STY $1B44 (6B) → JSL open_fetch + NOP×2
OPEN_PATCH_LEN = 6
OPEN_CURSOR = 0x001B44  # 오프닝 읽기 커서(뱅크 $00 고정 — `long` 으로 쓴다, DB 가 훅뱅크라서)
# 🔴 **오프닝은 타자기다 — 한 칸 그릴 때마다 줄 시작 커서를 「칸 수」만큼 올린다**(2026-09-20 실기,
# `$1B44` 를 훅 호출마다 찍어서 잡았다: 2번째 호출 Y=1→커서 3, 3번째 호출 Y=**2**). 한 줄은
# `$1B81`(줄 시작) → `$1B44`(읽기 커서)로 시작하고, 칸을 다 채우면 `$1E:E0BB` 가 `$1B81 += $1B83`
# (칸 수 — 크롤 1 · 인물 카드 $32) 한다. **바이트가 아니라 칸이다.** 한글은 한 칸이 2바이트라
# 다음 칸이 색인 바이트에서 시작해 「정상 글리프 + 쓰레기 한 칸」이 음절마다 붙었다(4배 화면의
# 「아。주요 먼민」이 정확히 그 모양). `$1B44` 는 그 사이 `$1E:DF97` 이 DMA 카운터로 덮어쓰므로
# 못 믿는다 — 훅이 **실제 소비한 바이트 커서**를 따로 남기고(`V_OCUR`), `$1E:E0BB` 의 증가
# 루프(11B)를 `JSL open_advance` 로 갈아 끼워 `$1B81 = V_OCUR` 로 세운다.
OPEN_LINE = 0x001B81  # 줄 시작 커서(워드) — `$1E:DF34 LDY $1B81 / STY $1B44`
# 🔴 **컨텍스트(글리프가 올라갈 VRAM 베이스)는 「어느 훅이 불렸나」가 아니라 「지금 화면 배치가
# 무엇이냐」다**(2026-09-20 실기). 인물 소개 카드는 오프닝 화면(BG3 베이스 워드 `$3000`) 위에서
# **인게임 메시지 엔진**(`$02:DCE0` 가 칸 배열을 채운다 — 쓰기 BP 로 잡았다)이 글자를 그린다.
# 인게임 훅이 진입마다 `V_CTX=0` 으로 되돌리니 글리프가 워드 `$1000` 에 올라가고 화면은 `$3000`
# 의 원본 가나를 보여 줬다(카드 글자가 가나 모양으로 깨진 정체 — 서명 검사: 슬롯 타일의 평면1 이
# `$FF` 가 아니었다). 롬에 PPU 베이스 그림자 변수가 없어(`STA $210C` 가 세 자리뿐, 전부 즉치)
# **그 세 자리를 가로채** `V_CTX` 를 세운다 — BG3 베이스가 `$3000`(`$210C=$03`)이면 1, 아니면 0.
PPU_CTX_SITES = [  # (`LDA #imm / STA $210C` 5B 자리, 즉치, 컨텍스트) → `JSL ctx_*` + NOP
    (0x008082, 0x22, 0),
    (0x00826C, 0x22, 0),
    (0x008294, 0x03, 1),
]
PPU_BG34NBA = 0x00210C
OPEN_ADVANCE_SITE = 0x1EE0BB  # LDX $1B83 / DEX / BMI +5 / INC $1B81 / BRA -8 (11B) → JSL open_advance + NOP×7
OPEN_ADVANCE_LEN = 11
OPEN_VRAM_DELTA = 0x2000  # 오프닝 패턴 베이스 워드 $3000 — **확정됨**(09-17(6), 화면을
# 확정 번역과 줄 단위 대조해 구조가 완전히 일치함을 확인했다). 09-16(2)·09-17(5)의 "베이스가
# 틀렸다"는 전제는 오진이었다 — 다시 건드리지 않는다. 진짜 범인은 아래 `FONT_*`(09-17(6)(7)).

# 🔴 **일곱째 문 — 폰트 벌크카피가 오프닝 진입 시 우리 글리프를 도로 덮는다**(09-17(6)(7)
# 실기+정적 확정). `$1E:E6B3`(호출 자리 셋 — `$1E:D2CB`·`D508`·`EBCA`)가 WRAM `$7F:A028`
# 스테이징을 거쳐 **정확히 워드 `$3000`, 타일 0~0x17F(384장)**를 원본 가나로 채운다 —
# 우리 동적 슬롯의 타일 상한(`tiles.py` 의 `UPLOADED=0x180`)과 **완전히 겹친다**(옮겨 갈
# 자리가 없다, devlog 09-17(7)). 세 자리 모두 `JSR $E6B3`(3B, 뱅크 안 호출) 이라 트램펄린이
# 하나 더 필요하다 — 원본 호출을 그대로 하고 **직후 오너 표를 비우는** 트램펄린을
# `$1E:FAF4`(빈 자리, `$FF` 런 1,292B 확인)에 둔다.
FONT_CALL_SITES = [0x1ED2CB, 0x1ED508, 0x1EEBCA]  # `JSR $E6B3` 세 자리 — 전부 같은 패치
FONT_TRAMPOLINE = 0x1EFAF4  # `JSR $E6B3` + `JSL font_reset` + `RTS`(뱅크 안이라 JSR 로 부른다)

# ── WRAM 변수 ($7E:4625, 741B 무손상 확인 — status 13.8) ────────────────────────────────
VAR = 0x7E4625
V_MAGIC, V_HEAD, V_TAIL, V_NEXT = VAR + 0, VAR + 1, VAR + 2, VAR + 3
V_IDX = VAR + 4  # 워드: 글리프 색인 조립 + 돌려줄 바이트
V_PEND_N, V_PEND = VAR + 6, VAR + 7  # 조사가 두 글자일 때 남은 것(3칸)
V_LAST = VAR + 10  # 워드: 마지막 글리프 색인(조사 받침 판정)
# 🔴 **본체 임시와 NMI 임시를 가른다** — 훅(alloc·josa)은 아무 때나 NMI 에 끊긴다.
#    한 칸을 같이 쓰면 글자를 그리는 도중 슬롯 번호가 바뀌어 **가끔** 엉뚱한 글자가 나온다
#    (재현이 안 되는 종류의 사고라 처음부터 가른다).
V_T0 = VAR + 12  # 워드: 본체 임시(조사 — 마지막 글리프 사본)
V_T1 = VAR + 14  # 본체 임시(슬롯 번호 · 조사 k)
V_RES, V_TMP = VAR + 15, VAR + 16
V_CNT = VAR + 17  # NMI: 이번 프레임에 남은 장수
V_N13 = VAR + 24  # 워드: 고정 칸 문자열의 칸 수(호출자가 A 에 넣어 준다)
# 🔴 선두 표를 조회하면 **A 가 표 값으로 덮인다** — 선두가 아닌 글자는 원본 바이트를 되찾아야 한다.
#    안 그러면 공백·숫자 자리에 표의 `$FF` 가 들어가 **칸이 깨진다**(2026-09-07 타이틀 메뉴에서 드러났다).
V_RAW = VAR + 26  # 방금 읽은 원본 바이트
V_OVERFLOW = VAR + 23  # 슬롯 풀이 한 바퀴 다 돌아 재사용됐다(= 그 사이 화면에 남은 글자가 덮일 수 있다)
V_CTX = VAR + 27  # 다음 alloc() 큐잉의 컨텍스트(0=인게임 워드 $1000 · 1=오프닝 워드 $3000)
V_UCTX = VAR + 28  # NMI: upload 중 큐 항목의 컨텍스트 사본
V_OCUR = VAR + 30  # 워드: 오프닝 — 훅이 실제로 소비한 바이트 커서(`$1B44` 사본, `open_advance` 가 읽는다)
V_U0 = VAR + 18  # 워드: NMI 임시(글리프 색인)
V_U1 = VAR + 20  # NMI 임시(슬롯 번호)
V_UV = VAR + 21  # 워드: NMI 임시(VRAM 워드 주소)
Q_SLOT, Q_LO, Q_HI, Q_CTX = VAR + 32, VAR + 48, VAR + 64, VAR + 80
OWNER_BASE = VAR + 96  # 슬롯별 「지금 이 슬롯이 담은 글리프」 — nslot 만큼(build_payload 가 정한다)
MAGIC = 0x5A


def josa_rows() -> list[tuple[int, str]]:
    """색인 `k*2 + b`(b=0 받침 있음 · 1 없음) → (길이, 표기). 길이 0 = **아무것도 안 낸다**."""
    rows = []
    for pair in encode.JOSA_PAIRS:
        for tail in ("각", "가"):  # 받침 있음/없음 표본
            rows.append(encode.pick_josa(tail, pair))
    return [(len(s), s) for s in rows]


def josa_chars() -> str:
    return "".join(s for _n, s in josa_rows())


def glyph_bytes(rep: list[str | None]) -> bytes:
    """색인 순 2bpp 32B/자 — 위 타일 8행 + 아래 8행, 평면1 = $FF.
    ⚠ 비워 둔 자리(`None`, `encode.bad_index`)도 **32B 를 차지한다** — 색인이 곧 자리여야 한다."""
    import hangul_font

    if hangul_font.CELL_W != 8:
        raise SystemExit("훅은 반각 글리프(D1=B)만 다룬다")
    font = hangul_font.load_font()
    out = bytearray()
    for ch in rep:
        rows = [0] * 16 if ch is None else hangul_font.render(ch, font)
        for half in (0, 8):
            for r in range(8):
                out += bytes([rows[half + r], 0xFF])
    return bytes(out)


def batchim_bits(rep: list[str | None]) -> bytes:
    """글리프 색인 → 받침 있음 1비트. 조사 훅이 읽는다."""
    sys.path.insert(0, str(common.ROOT))
    from shared.text import josa as josa_mod

    n = (len(rep) + 7) // 8
    bits = bytearray(n)
    for i, ch in enumerate(rep):
        if ch is not None and josa_mod.batchim(ch):
            bits[i >> 3] |= 1 << (i & 7)
    return bytes(bits)


def build_payload(
    rep: list[str | None], slots: list[int], vram: list[int], item_table: int = 0x3E8000
) -> tuple[bytes, dict]:
    """훅 뱅크 하나를 통째로 만든다 — 코드가 앞, 표가 뒤. **원본을 안 읽는다**(테스트가 돌 수 있게)."""
    rep_index = encode.index_map(rep)
    nslot = len(slots)
    owner_lo, owner_hi = OWNER_BASE, OWNER_BASE + nslot  # 슬롯마다 word 하나 — 캐시 표
    var_end = OWNER_BASE + 2 * nslot
    if var_end - VAR >= 741:
        raise SystemExit(f"WRAM 무손상 구간(741B)을 넘는다: {var_end - VAR}B (슬롯 {nslot}개)")
    assert len(vram) == nslot
    josa_ord = encode.LEADS.index(encode.JOSA_LEAD)
    a = Asm(HOOK_ORG, bank=HOOK_BANK)

    # ── 훅 본체 ($02:FE52 에서 JSL) ────────────────────────────────────────────────
    a.label("hook")
    a.php()
    a.phb()
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.phx()
    a.phy()
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.op("lda", addr=V_PEND_N, mode="long")
    a.beq(label="h_fetch")
    a.op("lda", addr=V_PEND + 0, mode="long")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr=V_PEND + 1, mode="long")
    a.op("sta", addr=V_PEND + 0, mode="long")
    a.op("lda", addr=V_PEND + 2, mode="long")
    a.op("sta", addr=V_PEND + 1, mode="long")
    a.op("lda", addr=V_PEND_N, mode="long")
    a.dec()
    a.op("sta", addr=V_PEND_N, mode="long")
    a.bra(label="h_done")

    a.label("h_fetch")
    a.jsr(addr="fetch", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="lead_tab", mode="absx")
    a.cmp(imm=0xFF)
    a.beq(label="h_done")
    a.op("sta", addr=V_IDX + 1, mode="long")  # 선두 서수
    a.jsr(addr="fetch", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")  # 색인 하위
    a.op("lda", addr=V_IDX + 1, mode="long")
    a.cmp(imm=josa_ord)
    a.bne(label="h_glyph")
    a.op("lda", addr=V_IDX, mode="long")
    a.cmp(imm=encode.JOSA_BASE)
    a.bcc(label="h_glyph")
    a.op("and", imm=0x0F)
    a.jsr(addr="josa", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr=V_TMP, mode="long")
    a.beq(label="h_again")
    a.bra(label="h_done")
    a.label("h_again")
    a.jmp(addr="h_fetch", mode="abs")

    a.label("h_glyph")
    a.rep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.op("sta", addr=V_LAST, mode="long")
    a.sep(imm=0x20)
    a.jsr(addr="alloc", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")

    a.label("h_done")
    a.sep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.ply()
    a.plx()
    a.plb()
    a.plp()
    a.rtl()

    # ── 사전 버퍼에서 한 바이트 ($02:DDF9 에서 JSL) ─────────────────────────────────
    a.label("hookbuf")
    a.php()
    a.phb()
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.phx()
    a.phy()
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.op("lda", addr=BUF_CURSOR, mode="abs")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr=BUF_BASE, mode="absx")
    a.op("sta", addr=V_IDX, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="lead_tab", mode="absx")
    a.cmp(imm=0xFF)
    a.beq(label="hb_done")
    a.op("sta", addr=V_IDX + 1, mode="long")
    a.op("lda", addr=BUF_CURSOR, mode="abs")  # 둘째 바이트 — 커서를 우리가 올린다
    a.inc()
    a.op("sta", addr=BUF_CURSOR, mode="abs")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr=BUF_BASE, mode="absx")
    a.op("sta", addr=V_IDX, mode="long")
    a.rep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.op("sta", addr=V_LAST, mode="long")
    a.sep(imm=0x20)
    a.jsr(addr="alloc", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")
    a.label("hb_done")
    a.sep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.ply()
    a.plx()
    a.plb()
    a.plp()
    a.rtl()

    # ── 메뉴 이름 한 줄을 칸 배열에 채운다 (아이템 표 → $0305) ──────────────────────
    # 들어올 때: A/X/Y 8비트 · X = 표 색인(×2). 나갈 때: **Y = 채운 칸 수**(패딩 루프가 쓴다).
    a.label("namecopy")
    a.php()
    a.phb()
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.op("lda", addr=item_table, mode="longx")
    a.op("sta", addr=0x000006, mode="long")
    a.op("lda", addr=item_table + 1, mode="longx")
    a.op("sta", addr=0x000007, mode="long")
    a.lda(imm=item_table >> 16)
    a.op("sta", addr=0x000008, mode="long")
    a.ldy(imm=0x0000, m16=True)
    a.ldx(imm=0x0000, m16=True)
    a.label("nc_loop")
    a.op(
        "lda", dp=0x06, mode="indlongy"
    )  # ⚠ `[dp],Y` 다 — `[dp]`($A7) 로 쓰면 첫 글자만 읽는다  # LDA [$06],Y — ⚠ 뱅크는 $08 이 정한다
    a.cmp(imm=0xFF)
    a.beq(label="nc_end")
    a.phx()
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="lead_tab", mode="longx")
    a.plx()
    a.cmp(imm=0xFF)
    a.bne(label="nc_lead")
    a.op("lda", addr=V_RAW, mode="long")  # 🔴 선두가 아니다 — **원본 바이트**를 되찾는다
    a.bra(label="nc_plain")
    a.label("nc_lead")
    a.op("sta", addr=V_IDX + 1, mode="long")  # 선두 서수
    a.iny()
    a.op("lda", dp=0x06, mode="indlongy")  # ⚠ `[dp],Y` 다 — `[dp]`($A7) 로 쓰면 첫 글자만 읽는다
    a.op("sta", addr=V_IDX, mode="long")  # 색인 하위
    a.phx()
    a.phy()
    a.jsr(addr="alloc", mode="abs")
    a.ply()
    a.plx()
    a.label("nc_plain")
    a.op("sta", addr=CELLS, mode="longx")
    a.inx()
    a.iny()
    a.bra(label="nc_loop")
    a.label("nc_end")
    a.txy()  # Y = 채운 칸 수
    a.plb()
    a.plp()
    a.rtl()

    # ── 13칸 고정 문자열 한 줄 (전투 커맨드·파티 이름) ─────────────────────────────
    a.label("name13")
    a.php()
    a.rep(imm=0x30)
    a.inc()  # A = 길이−1 → **칸 수**
    a.op("sta", addr=V_N13, mode="long")
    a.sep(imm=0x20)
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.lda(imm=DICT_BANK)
    a.op("sta", addr=0x000008, mode="long")  # [$06] 의 뱅크 — 문자열은 우리 뱅크에 있다
    a.ldy(imm=0x0000, m16=True)  # 소스 커서
    a.ldx(imm=0x0000, m16=True)  # 칸 커서
    a.label("n13_loop")
    a.rep(imm=0x20)
    a.txa()
    a.op("cmp", addr=V_N13, mode="long")
    a.sep(imm=0x20)
    a.bcs(label="n13_end")
    a.op("lda", dp=0x06, mode="indlongy")
    a.cmp(imm=0xFF)
    a.beq(label="n13_pad")
    a.op("sta", addr=V_RAW, mode="long")  # 표 조회가 A 를 덮으므로 미리 보관한다
    a.phx()
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="lead_tab", mode="longx")
    a.plx()
    a.cmp(imm=0xFF)
    a.bne(label="n13_lead")
    a.op("lda", addr=V_RAW, mode="long")  # 🔴 선두가 아니다 — **원본 바이트**를 되찾는다
    a.bra(label="n13_put")
    a.label("n13_lead")
    a.op("sta", addr=V_IDX + 1, mode="long")
    a.iny()
    a.op("lda", dp=0x06, mode="indlongy")
    a.op("sta", addr=V_IDX, mode="long")
    a.phx()
    a.phy()
    a.jsr(addr="alloc", mode="abs")
    a.ply()
    a.plx()
    a.label("n13_put")
    a.op("sta", addr=CELL_BASE, mode="longx")
    a.inx()
    a.iny()
    a.bra(label="n13_loop")
    a.label("n13_pad")
    a.lda(imm=0x10)  # 남은 칸은 공백으로
    a.label("n13_padloop")
    a.op("sta", addr=CELL_BASE, mode="longx")
    a.inx()
    a.rep(imm=0x20)
    a.txa()
    a.op("cmp", addr=V_N13, mode="long")
    a.sep(imm=0x20)
    a.bcc(label="n13_padloop")
    a.label("n13_end")
    a.lda(imm=0x00)
    a.pha()
    a.plb()  # ⚠ 원본 MVN 처럼 DB = $00 으로 남긴다
    a.plp()
    a.rtl()

    # ── 오프닝(D1) 대본 다음 바이트 ($1E:DF44 에서 JSL, 인라인 코드를 통째로 갈아 끼운다) ──
    # `h_fetch`(위 `hook`)와 뼈대가 같다 — 다른 건 **fetch 방식뿐**이다. 인게임은 `$3F/$40`
    # 포인터 + `JSR $E784` 지만, 오프닝은 `[$23],y`(Y 는 `$1B44`, 호출 직전 `$1E:DF41` 이 이미
    # 채워 뒀다) — 그래서 `fetch` 를 호출하는 대신 이 자리에서 직접 읽는다. 조사·2음절 대기
    # (`V_PEND*`)까지 인게임과 **같은 전역**을 그대로 쓴다(오프닝·인게임은 동시에 안 돈다).
    a.label("open_fetch")
    a.php()
    a.phb()  # 🔴 원래 DBR 을 먼저 실어 둔다 — 안 그러면 끝의 plb() 가 엉뚱한 바이트를 집어 탈선한다
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.phx()
    a.phy()
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.lda(imm=0x01)
    a.op("sta", addr=V_CTX, mode="long")  # 오프닝 컨텍스트 — 글리프는 워드 $3000 에 올라간다
    a.op("lda", addr=V_PEND_N, mode="long")
    a.beq(label="o_fetch")
    a.op("lda", addr=V_PEND + 0, mode="long")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr=V_PEND + 1, mode="long")
    a.op("sta", addr=V_PEND + 0, mode="long")
    a.op("lda", addr=V_PEND + 2, mode="long")
    a.op("sta", addr=V_PEND + 1, mode="long")
    a.op("lda", addr=V_PEND_N, mode="long")
    a.dec()
    a.op("sta", addr=V_PEND_N, mode="long")
    a.jmp(addr="o_done", mode="abs")  # 커서 사본(`V_OCUR`)이 붙어 `bra` 로는 안 닿는다

    a.label("o_fetch")
    a.op("lda", dp=0x23, mode="indlongy")
    a.pha()  # STY 엔 long 이 없다(65816 명세) — 커서는 A 로 옮겨 stz long 대신 sta long 으로 쓴다
    a.iny()
    a.rep(imm=0x20)
    a.tya()
    a.op("sta", addr=OPEN_CURSOR, mode="long")
    a.op("sta", addr=V_OCUR, mode="long")  # 줄 끝에 `open_advance` 가 `$1B81` 로 되돌려 준다
    a.sep(imm=0x20)
    a.pla()
    a.op("sta", addr=V_IDX, mode="long")
    # 🔴 **페이지 경계(`$FF`)·메시지 끝(`$E0`/`$E4`)에서 캐시를 비운다**(관리자 제안,
    # 2026-09-17 — 박스 클리어 자리를 찾는 대신, 이미 가로채는 바이트 흐름 안의 페이지
    # 제어 코드를 그대로 쓴다). 화면이 어차피 지워지는 자리라 지금 보이는 글자를 갈아칠
    # 위험이 없다 — 한 페이지 고유 음절 최대 64 < 슬롯 80 이니 **페이지마다 비우면 몇
    # 바퀴를 돌아도 풀이 안 터진다**(무한 반복되는 오프닝 실측 — devlog 09-17).
    a.cmp(imm=0xFF)
    a.beq(label="o_pagebreak")
    a.cmp(imm=0xE0)
    a.beq(label="o_pagebreak")
    a.cmp(imm=0xE4)
    a.bne(label="o_notpage")
    a.label("o_pagebreak")
    a.jsr(addr="cache_reset", mode="abs")
    a.label("o_notpage")
    a.op("lda", addr=V_IDX, mode="long")  # cache_reset 이 A/X 를 비운다 — 원본 바이트를 되찾는다
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="lead_tab", mode="absx")
    a.cmp(imm=0xFF)
    a.beq(label="o_done")
    a.op("sta", addr=V_IDX + 1, mode="long")  # 선두 서수
    a.op("lda", dp=0x23, mode="indlongy")
    a.pha()
    a.iny()
    a.rep(imm=0x20)
    a.tya()
    a.op("sta", addr=OPEN_CURSOR, mode="long")
    a.op("sta", addr=V_OCUR, mode="long")
    a.sep(imm=0x20)
    a.pla()
    a.op("sta", addr=V_IDX, mode="long")  # 색인 하위
    a.op("lda", addr=V_IDX + 1, mode="long")
    a.cmp(imm=josa_ord)
    a.bne(label="o_glyph")
    a.op("lda", addr=V_IDX, mode="long")
    a.cmp(imm=encode.JOSA_BASE)
    a.bcc(label="o_glyph")
    a.op("and", imm=0x0F)
    a.jsr(addr="josa", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr=V_TMP, mode="long")
    a.beq(label="o_fetch")
    a.bra(label="o_done")

    a.label("o_glyph")
    a.rep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.op("sta", addr=V_LAST, mode="long")
    a.sep(imm=0x20)
    a.jsr(addr="alloc", mode="abs")
    a.op("sta", addr=V_IDX, mode="long")

    a.label("o_done")
    a.sep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")
    a.ply()
    a.plx()
    a.plb()
    a.plp()
    a.rtl()

    # ── 오너 표를 비운다(페이지 경계) — A/X 를 자유롭게 쓴다, 호출부가 원본 바이트를 되찾는다 ──
    a.label("cache_reset")
    a.sep(imm=0x20)
    a.lda(imm=0xFF)  # 캐시 표 — 실제 글리프 색인(최대 $08FF)은 절대 안 되는 값으로 비운다
    a.ldx(imm=0x0000, m16=True)
    a.label("cr_loop")
    a.op("sta", addr=owner_lo, mode="longx")
    a.op("sta", addr=owner_hi, mode="longx")
    a.inx()
    a.cpx(imm=nslot, m16=True)
    a.bne(label="cr_loop")
    a.lda(imm=0x00)
    a.op("sta", addr=V_NEXT, mode="long")
    a.rts()

    # ── 폰트 벌크카피 트램펄린의 착지점 — `JSL` 로 불려 `cache_reset`(근접 호출 규약)을
    #    감싼다. 원 호출부(`$1E:D2CB` 등)의 A/X/Y 폭을 모르므로 여기서 강제로 맞춘다 ──
    a.label("font_reset")
    a.php()
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.jsr(addr="cache_reset", mode="abs")
    a.plp()
    a.rtl()

    # ── 오프닝 줄 끝(`$1E:E0BB`) — 줄 시작 커서를 「칸 수」가 아니라 **소비한 바이트**로 올린다.
    #    호출부의 A 폭이 경로마다 다르다(8/16) — php/plp 로 감싸 16비트로 고정하고 A 만 쓴다.
    #    ⚠ `$1B81` 은 DBR 에 기대지 않고 long 으로 쓴다(뱅크 $00 WRAM 미러).
    a.label("open_advance")
    a.php()
    a.rep(imm=0x20)
    a.op("lda", addr=V_OCUR, mode="long", m16=True)
    a.op("sta", addr=OPEN_LINE, mode="long", m16=True)
    a.plp()
    a.rtl()

    # ── PPU 배치 자리(`$00:8082` 류) — 원본의 `LDA #imm / STA $210C` 를 대신하고 컨텍스트를 세운다.
    #    호출부는 A 8비트(직전이 `LDA #$0C / STA $210A`). 뱅크 $00 코드지만 DBR 에 안 기댄다.
    for name, imm, ctx in (("ctx_game", 0x22, 0), ("ctx_open", 0x03, 1)):
        a.label(name)
        a.lda(imm=imm)
        a.op("sta", addr=PPU_BG34NBA, mode="long")
        a.lda(imm=ctx)
        a.op("sta", addr=V_CTX, mode="long")
        a.rtl()

    # ── 대본 다음 바이트 (원본 $02:E784 과 같은 동작) ────────────────────────────────
    a.label("fetch")
    a.op("lda", addr=0x003F, mode="abs")
    a.clc()
    a.adc(imm=0x01)
    a.op("sta", addr=0x003F, mode="abs")
    a.op("lda", addr=0x0040, mode="abs")
    a.adc(imm=0x00)
    a.op("sta", addr=0x0040, mode="abs")
    a.op("lda", dp=0x3F, mode="indlong")
    a.rts()

    # ── 슬롯 하나를 잡고 글리프를 큐에 넣는다 (색인 = V_IDX) ─────────────────────────
    # 🔴 **먼저 캐시를 본다**(status 13.5 원 설계 — 구현에서 빠져 있던 검사). 이미 어느
    # 슬롯이 이 글리프를 담고 있으면 **그 슬롯을 그대로 돌려준다** — 새로 안 뺏는다. 캐시가
    # 없으면 같은 화면 안에서 슬롯 수(nslot)보다 글자 **인스턴스**가 많을 때(반복 포함) 라운드
    # 로빈이 이미 그려진 앞 글자의 타일을 뒤 글자가 덮어쓴다(오프닝 첫 페이지 실기로 확인,
    # 2026-09-16 — 대사창은 68 < 80 이라 우연히 안 터졌을 뿐이다).
    a.label("alloc")
    a.sep(imm=0x20)
    a.ldx(imm=0x0000, m16=True)
    a.label("ac_scan")
    a.op("lda", addr=owner_lo, mode="longx")
    a.op("cmp", addr=V_IDX, mode="long")
    a.bne(label="ac_next")
    a.op("lda", addr=owner_hi, mode="longx")
    a.op("cmp", addr=V_IDX + 1, mode="long")
    a.beq(label="ac_hit")
    a.label("ac_next")
    a.inx()
    a.cpx(imm=nslot, m16=True)
    a.bne(label="ac_scan")
    a.bra(label="al_miss")
    # 🔴 **늙은 히트는 다시 올린다**(2026-09-20 실기 — 소니아 카드의 「다루는」이 「다성는」으로).
    #    라운드로빈은 히트해도 나이를 안 되돌리므로, 60여 할당 전에 올린 글리프(로우 카드의 「크루스」)를
    #    지금 화면이 다시 쓰면 그 슬롯이 몇 글자 뒤 「성」에게 밀려 **화면에 남은 글자가 바뀐다.**
    #    남은 수명이 `REALLOC_AGE` 미만이면 오너 표를 비우고 새 슬롯으로 옮긴다(재업로드 한 번이 비용).
    a.label("ac_hit")
    a.txa()
    a.op("sta", addr=V_T1, mode="long")
    a.op("eor", imm=0xFF)  # -slot-1
    a.clc()
    a.op("adc", addr=V_NEXT, mode="long")  # 나이 = V_NEXT - slot - 1 (음수면 한 바퀴 보정)
    a.bpl(label="ac_age")
    a.clc()
    a.adc(imm=nslot)
    a.label("ac_age")
    a.cmp(imm=nslot - REALLOC_MARGIN)
    a.bcc(label="ac_fresh")
    a.lda(imm=0xFF)
    a.op("sta", addr=owner_lo, mode="longx")
    a.op("sta", addr=owner_hi, mode="longx")
    a.bra(label="al_miss")
    a.label("ac_fresh")
    a.op("lda", addr="slot_code", mode="absx")
    a.jmp(addr="al_ret", mode="abs")  # `bra` 로는 안 닿을 수 있다 — 아래 al_miss 본문이 길다

    a.label("al_miss")
    a.op("lda", addr=V_NEXT, mode="long")
    a.cmp(imm=nslot)
    a.bcc(label="al0")
    a.lda(imm=0x00)  # 표 밖으로 새지 않게 가둔다
    a.label("al0")
    a.op("sta", addr=V_T1, mode="long")
    a.inc()
    a.cmp(imm=nslot)
    a.bcc(label="al1")
    a.lda(imm=0x01)  # 한 바퀴 다 돌았다 — 화면에 남은 글자가 덮일 수 있다(계측, 조용히 안 넘긴다)
    a.op("sta", addr=V_OVERFLOW, mode="long")
    a.lda(imm=0x00)
    a.label("al1")
    a.op("sta", addr=V_NEXT, mode="long")
    a.op("lda", addr=V_HEAD, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr=V_T1, mode="long")
    a.op("sta", addr=Q_SLOT, mode="longx")
    a.op("lda", addr=V_IDX, mode="long")
    a.op("sta", addr=Q_LO, mode="longx")
    a.op("lda", addr=V_IDX + 1, mode="long")
    a.op("sta", addr=Q_HI, mode="longx")
    a.op("lda", addr=V_CTX, mode="long")  # 이 큐 항목이 인게임/오프닝 어느 쪽인지 같이 싣는다
    a.op("sta", addr=Q_CTX, mode="longx")
    a.op("lda", addr=V_HEAD, mode="long")
    a.inc()
    a.op("and", imm=QN - 1)
    a.op("sta", addr=V_HEAD, mode="long")
    a.op("lda", addr=V_T1, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr=V_IDX, mode="long")  # 캐시 갱신 — 이 슬롯이 이제 이 글리프를 담는다
    a.op("sta", addr=owner_lo, mode="longx")
    a.op("lda", addr=V_IDX + 1, mode="long")
    a.op("sta", addr=owner_hi, mode="longx")
    a.op("lda", addr="slot_code", mode="absx")
    a.label("al_ret")
    a.rts()

    # ── 런타임 조사 (A = k) ─────────────────────────────────────────────────────────
    a.label("josa")
    a.op("sta", addr=V_T1, mode="long")
    a.rep(imm=0x30)
    a.op("lda", addr=V_LAST, mode="long")
    a.op("sta", addr=V_T0, mode="long")
    a.lsr()
    a.lsr()
    a.lsr()
    a.tax()
    a.op("lda", addr=V_T0, mode="long")
    a.op("and", imm=0x0007, m16=True)
    a.tay()
    a.sep(imm=0x20)
    a.op("lda", addr="batchim", mode="absx")
    a.op("and", addr="bitmask", mode="absy")
    a.beq(label="j_no")
    a.lda(imm=0x00)
    a.bra(label="j_e")
    a.label("j_no")
    a.lda(imm=0x01)
    a.label("j_e")
    a.op("sta", addr=V_TMP, mode="long")
    a.op("lda", addr=V_T1, mode="long")
    a.asl()
    a.clc()
    a.op("adc", addr=V_TMP, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="josa_len", mode="absx")
    a.op("sta", addr=V_TMP, mode="long")
    a.beq(label="j_done")
    a.op("lda", addr="josa_i0lo", mode="absx")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr="josa_i0hi", mode="absx")
    a.op("sta", addr=V_IDX + 1, mode="long")
    a.phx()
    a.jsr(addr="alloc", mode="abs")
    a.plx()
    a.op("sta", addr=V_RES, mode="long")
    a.op("lda", addr=V_TMP, mode="long")
    a.cmp(imm=0x02)
    a.bcc(label="j_done")
    a.op("lda", addr="josa_i1lo", mode="absx")
    a.op("sta", addr=V_IDX, mode="long")
    a.op("lda", addr="josa_i1hi", mode="absx")
    a.op("sta", addr=V_IDX + 1, mode="long")
    a.jsr(addr="alloc", mode="abs")
    a.op("sta", addr=V_PEND + 0, mode="long")
    a.lda(imm=0x01)
    a.op("sta", addr=V_PEND_N, mode="long")
    a.label("j_done")
    a.op("lda", addr=V_RES, mode="long")
    a.rts()

    # ── NMI 에서 큐를 비운다 ($00:FF20 에서 JSL) ─────────────────────────────────────
    a.label("drain")
    a.php()
    a.phb()
    a.sep(imm=0x20)
    a.rep(imm=0x10)
    a.phx()
    a.phy()
    a.lda(imm=HOOK_BANK)
    a.pha()
    a.plb()
    a.op("lda", addr=V_MAGIC, mode="long")
    a.cmp(imm=MAGIC)
    a.beq(label="d_go")
    a.lda(imm=0x00)
    for v in (V_HEAD, V_TAIL, V_NEXT, V_PEND_N, V_OVERFLOW):
        a.op("sta", addr=v, mode="long")
    a.lda(imm=0xFF)  # 캐시 표 — 실제 글리프 색인(최대 $08FF)은 절대 안 되는 값으로 비운다
    a.ldx(imm=0x0000, m16=True)
    a.label("d_ownerclr")
    a.op("sta", addr=owner_lo, mode="longx")
    a.op("sta", addr=owner_hi, mode="longx")
    a.inx()
    a.cpx(imm=nslot, m16=True)
    a.bne(label="d_ownerclr")
    a.lda(imm=MAGIC)
    a.op("sta", addr=V_MAGIC, mode="long")
    a.bra(label="d_end")
    a.label("d_go")
    a.lda(imm=0x80)
    a.op("sta", addr=0x2115, mode="abs")  # VMAIN — $2119 뒤 +1 워드
    a.lda(imm=DRAIN_MAX)
    a.op("sta", addr=V_CNT, mode="long")
    a.label("d_loop")
    a.op("lda", addr=V_TAIL, mode="long")
    a.op("cmp", addr=V_HEAD, mode="long")
    a.beq(label="d_end")
    a.op("and", imm=QN - 1)
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.jsr(addr="upload", mode="abs")
    a.op("lda", addr=V_TAIL, mode="long")
    a.inc()
    a.op("and", imm=QN - 1)
    a.op("sta", addr=V_TAIL, mode="long")
    a.op("lda", addr=V_CNT, mode="long")
    a.dec()
    a.op("sta", addr=V_CNT, mode="long")
    a.bne(label="d_loop")
    a.label("d_end")
    a.ply()
    a.plx()
    a.plb()
    a.plp()
    a.rtl()  # ⚠ NMI 스텁이 **JSL** 로 부른다 — RTS 로 닫으면 프레임마다 스택이 2바이트씩 어긋난다

    # ── 글리프 한 자를 VRAM 으로 (X = 큐 칸) ────────────────────────────────────────
    a.label("upload")
    a.sep(imm=0x20)
    a.op("lda", addr=Q_CTX, mode="longx")  # X 가 아직 **큐 칸**일 때 먼저 챙긴다(곧 슬롯 번호로 바뀐다)
    a.op("sta", addr=V_UCTX, mode="long")
    a.op("lda", addr=Q_SLOT, mode="longx")
    a.op("sta", addr=V_U1, mode="long")
    a.op("lda", addr=Q_LO, mode="longx")
    a.op("sta", addr=V_U0, mode="long")
    a.op("lda", addr=Q_HI, mode="longx")
    a.op("sta", addr=V_U0 + 1, mode="long")
    a.rep(imm=0x30)
    a.op("lda", addr=V_U1, mode="long")
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr=V_UCTX, mode="long")
    a.beq(label="u_ig")
    a.op("lda", addr="slot_ovlo", mode="absx")  # 오프닝 — 패턴 베이스 워드 $3000
    a.op("sta", addr=V_UV, mode="long")
    a.op("lda", addr="slot_ovhi", mode="absx")
    a.op("sta", addr=V_UV + 1, mode="long")
    a.bra(label="u_vd")
    a.label("u_ig")
    a.op("lda", addr="slot_vlo", mode="absx")  # 인게임 — 패턴 베이스 워드 $1000
    a.op("sta", addr=V_UV, mode="long")
    a.op("lda", addr="slot_vhi", mode="absx")
    a.op("sta", addr=V_UV + 1, mode="long")
    a.label("u_vd")
    a.rep(imm=0x30)
    a.op("lda", addr=V_U0, mode="long")
    for _ in range(5):
        a.asl()
    a.tax()
    a.op("lda", addr=V_UV, mode="long")
    a.op("sta", addr=0x2116, mode="abs")
    # 🔴 **배경 투명(마스터 지시 2026-09-20)** — `glyph_bytes()`는 평면1을 늘 `$FF`로 굽는다
    #    (인게임 대사창은 그게 맞다 — 칸이 불투명한 박스로 보여야 읽힌다). 하지만 **오프닝
    #    크롤은 별이 비치는 배경 위에 글자만 떠야 한다** — 원본도 그렇게 그린다(실기 확인,
    #    원본 가나 시트는 평면0=평면1 중복이라 꺼진 픽셀이 색인 0=투명이다). 그래서 여기,
    #    VRAM 에 실제로 쓰는 시점에 **컨텍스트별로 평면1을 다시 만든다** — 오프닝(V_UCTX=1)
    #    이면 평면1 을 평면0 으로 덮어써 꺼진 픽셀이 색인 0(투명)이 되게 하고, 인게임(=0)
    #    이면 원본 그대로(평면1=`$FF`, 불투명 박스)를 둔다. 소스 뱅크(`$3D`)는 그대로 —
    #    "서명"(평면1=`$FF`)은 여기 오프닝 분기를 타지 않는 인게임 타일에서는 계속 유효하다.
    a.sep(imm=0x20)
    a.op("lda", addr=V_UCTX, mode="long")
    a.rep(imm=0x30)
    a.beq(label="u1_ig")
    a.ldy(imm=0x0008, m16=True)
    a.label("u1")
    a.op("lda", addr=GLYPH_BASE, mode="longx")
    a.op("and", imm=0x00FF, m16=True)  # 평면1 을 비우고
    a.op("sta", addr=V_U0, mode="long")
    a.xba()  # 평면0 을 상위 바이트로 옮겨
    a.op("ora", addr=V_U0, mode="long")  # 평면1 자리에 평면0 을 복제 — 꺼진 칸 = 색인 0(투명)
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u1")
    a.bra(label="u1_done")
    a.label("u1_ig")
    a.ldy(imm=0x0008, m16=True)
    a.label("u1i")
    a.op("lda", addr=GLYPH_BASE, mode="longx")  # 인게임 — 원본 그대로(평면1=`$FF`, 불투명)
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u1i")
    a.label("u1_done")
    a.op("lda", addr=V_UV, mode="long")
    a.clc()
    a.adc(imm=0x0080, m16=True)
    a.op("sta", addr=0x2116, mode="abs")
    a.sep(imm=0x20)
    a.op("lda", addr=V_UCTX, mode="long")
    a.rep(imm=0x30)
    a.beq(label="u2_ig")
    a.ldy(imm=0x0008, m16=True)
    a.label("u2")
    a.op("lda", addr=GLYPH_BASE, mode="longx")
    a.op("and", imm=0x00FF, m16=True)
    a.op("sta", addr=V_U0, mode="long")
    a.xba()
    a.op("ora", addr=V_U0, mode="long")
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u2")
    a.bra(label="u2_done")
    a.label("u2_ig")
    a.ldy(imm=0x0008, m16=True)
    a.label("u2i")
    a.op("lda", addr=GLYPH_BASE, mode="longx")
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u2i")
    a.label("u2_done")
    a.sep(imm=0x20)
    a.rts()

    code_end = a.pos
    # ── 표 ────────────────────────────────────────────────────────────────────────
    lead = bytearray(b"\xff" * 256)
    for i, c in enumerate(encode.LEADS):
        lead[c] = i
    a.label("lead_tab")
    a.raw(bytes(lead))
    a.label("slot_code")
    a.raw(bytes(slots))
    a.label("slot_vlo")
    a.raw(bytes(v & 0xFF for v in vram))
    a.label("slot_vhi")
    a.raw(bytes(v >> 8 for v in vram))
    ovram = [v + OPEN_VRAM_DELTA for v in vram]  # 같은 슬롯 코드, 오프닝 패턴 베이스(워드 $3000)
    a.label("slot_ovlo")
    a.raw(bytes(v & 0xFF for v in ovram))
    a.label("slot_ovhi")
    a.raw(bytes(v >> 8 for v in ovram))
    rows = josa_rows()
    a.label("josa_len")
    a.raw(bytes(n for n, _s in rows))
    for k in (0, 1):
        idx = [rep_index[s[k]] if len(s) > k else 0 for _n, s in rows]
        a.label(f"josa_i{k}lo")
        a.raw(bytes(i & 0xFF for i in idx))
        a.label(f"josa_i{k}hi")
        a.raw(bytes(i >> 8 for i in idx))
    a.label("bitmask")
    a.raw(bytes(1 << i for i in range(8)))
    a.label("batchim")
    a.raw(batchim_bits(rep))
    blob = a.assemble()
    if len(blob) > 0x8000:
        raise SystemExit(f"훅 뱅크가 넘친다: {len(blob):,}B")
    info = {
        "code_bytes": code_end - HOOK_ORG,
        "table_bytes": len(blob) - (code_end - HOOK_ORG),
        "slots": nslot,
        "glyphs": len(rep),
        "hook": common.fmt((HOOK_BANK << 16) | a.labels["hook"]),
        "drain": common.fmt((HOOK_BANK << 16) | a.labels["drain"]),
        "open_fetch": common.fmt((HOOK_BANK << 16) | a.labels["open_fetch"]),
        "open_advance": common.fmt((HOOK_BANK << 16) | a.labels["open_advance"]),
        "var_end": var_end,
    }
    return blob, info | {"labels": a.labels}


def apply(
    out: bytearray,
    rom: bytes,
    rep: list[str | None],
    slots: list[int],
    item_table: int = 0x3E8000,
) -> dict:
    """훅 뱅크·글리프 뱅크를 놓고 **글자가 들어오는 문 셋**을 갈아 끼운다(대본 · 사전 버퍼 · 메뉴 이름)."""
    if len(rep) > GLYPH_MAX:
        raise SystemExit(
            f"글리프 {len(rep)} > 한 뱅크 {GLYPH_MAX} — 훅의 소스 주소 계산을 넓혀야 한다"
        )
    if not slots:
        raise SystemExit("동적 슬롯이 하나도 없다")
    tile = tiles.code_tile(rom)
    blob, info = build_payload(rep, slots, [tiles.vram_word(tile[c]) for c in slots], item_table)
    o = common.snes2off((HOOK_BANK << 16) | HOOK_ORG)
    out[o : o + len(blob)] = blob
    g = glyph_bytes(rep)
    go = common.snes2off(GLYPH_BASE)
    out[go : go + len(g)] = g
    hook_addr = (HOOK_BANK << 16) | info["labels"]["hook"]
    buf_addr = (HOOK_BANK << 16) | info["labels"]["hookbuf"]
    drain_addr = (HOOK_BANK << 16) | info["labels"]["drain"]

    # 1. 트램펄린: JSL 훅 + RTS (원본 JSR 과 자리를 맞춘다)
    t = common.snes2off(TRAMPOLINE)
    out[t : t + 5] = bytes([0x22, hook_addr & 0xFF, (hook_addr >> 8) & 0xFF, HOOK_BANK, 0x60])
    # 2. 소비 지점: JSR $E784 → JSR $FE52
    c = common.snes2off(CALL_SITE)
    if bytes(rom[c : c + 3]) != bytes([0x20, 0x84, 0xE7]):
        raise SystemExit(f"소비 지점이 예상과 다르다: {rom[c : c + 3].hex()}")
    out[c : c + 3] = bytes([0x20, TRAMPOLINE & 0xFF, (TRAMPOLINE >> 8) & 0xFF])
    # 2b. 사전 버퍼 소비 지점: LDA $174C,X → JSR $FE57
    t2 = common.snes2off(BUF_TRAMPOLINE)
    out[t2 : t2 + 5] = bytes([0x22, buf_addr & 0xFF, (buf_addr >> 8) & 0xFF, HOOK_BANK, 0x60])
    cb = common.snes2off(BUF_CALL_SITE)
    if bytes(rom[cb : cb + 3]) != bytes([0xBD, BUF_BASE & 0xFF, BUF_BASE >> 8]):
        raise SystemExit(f"사전 버퍼 소비 지점이 예상과 다르다: {rom[cb : cb + 3].hex()}")
    out[cb : cb + 3] = bytes([0x20, BUF_TRAMPOLINE & 0xFF, (BUF_TRAMPOLINE >> 8) & 0xFF])
    # 3. NMI: JSR $ACA9 → JSR 스텁(원래 것을 부르고 큐를 비운다)
    n = common.snes2off(NMI_CALL)
    if bytes(rom[n : n + 3]) != bytes([0x20, NMI_ORIG & 0xFF, NMI_ORIG >> 8]):
        raise SystemExit(f"NMI 자리가 예상과 다르다: {rom[n : n + 3].hex()}")
    out[n : n + 3] = bytes([0x20, NMI_STUB & 0xFF, NMI_STUB >> 8])
    s = common.snes2off(NMI_STUB)
    out[s : s + 8] = bytes(
        [
            0x20,
            NMI_ORIG & 0xFF,
            NMI_ORIG >> 8,
            0x22,
            drain_addr & 0xFF,
            (drain_addr >> 8) & 0xFF,
            HOOK_BANK,
            0x60,
        ]
    )
    # 3. 메뉴 이름 세 자리: 33바이트 덩이 → `JSR 우리것` + `JMP 패딩`
    name_addr = (HOOK_BANK << 16) | info["labels"]["namecopy"]
    t3 = common.snes2off(NAME_TRAMPOLINE)
    out[t3 : t3 + 5] = bytes([0x22, name_addr & 0xFF, (name_addr >> 8) & 0xFF, HOOK_BANK, 0x60])
    for site, join in NAME_SITES:
        so = common.snes2off(site)
        if bytes(rom[so : so + 4]) != bytes([0xBF, 0x73, 0xEF, 0x03]):
            raise SystemExit(
                f"메뉴 이름 자리가 예상과 다르다 {common.fmt(site)}: {rom[so : so + 4].hex()}"
            )
        if rom[so + NAME_BLOCK - 2 : so + NAME_BLOCK] != bytes([0x80, 0xF4]):
            raise SystemExit(f"메뉴 이름 덩이 끝이 BRA 가 아니다 {common.fmt(site)}")
        blk = bytearray([0xEA]) * NAME_BLOCK  # 안 닿는 자리는 NOP 로 둔다(디스어셈블이 안 튄다)
        blk[0:3] = bytes([0x20, NAME_TRAMPOLINE & 0xFF, (NAME_TRAMPOLINE >> 8) & 0xFF])
        blk[3:6] = bytes([0x4C, join & 0xFF, (join >> 8) & 0xFF])
        out[so : so + NAME_BLOCK] = bytes(blk)
    # 4. 고정 칸 문자열(파티 이름 · 타이틀 메뉴): **`MVN` 세 바이트만** JSR 로
    n13 = (HOOK_BANK << 16) | info["labels"]["name13"]
    t4 = common.snes2off(NAME13_TRAMPOLINE)
    out[t4 : t4 + 5] = bytes([0x22, n13 & 0xFF, (n13 >> 8) & 0xFF, HOOK_BANK, 0x60])
    for mvn, ldy in MVN_SITES:
        mo, lo = common.snes2off(mvn), common.snes2off(ldy)
        if rom[mo] != 0x54:
            raise SystemExit(f"MVN 자리가 아니다 {common.fmt(mvn)}: {rom[mo : mo + 3].hex()}")
        # ⚠ 우리 루틴은 목적지를 `$0305` 로 **고정**한다 — 자리마다 그게 맞는지 확인한다
        want = bytes([0xA0, CELL_BASE & 0xFF, (CELL_BASE >> 8) & 0xFF])
        if bytes(rom[lo : lo + 3]) != want:
            raise SystemExit(
                f"목적지가 $0305 가 아니다 {common.fmt(ldy)}: {rom[lo : lo + 3].hex()}"
            )
        out[mo : mo + MVN_LEN] = bytes(
            [0x20, NAME13_TRAMPOLINE & 0xFF, (NAME13_TRAMPOLINE >> 8) & 0xFF]
        )
    # 5. 오프닝(D1) 소비 지점: 인라인 6바이트 → `JSL open_fetch` + NOP×2(트램펄린이 필요 없다 —
    #    원래도 JSR 이 아니었다). `apply()` 밖(=$1E:DF41)이 이미 Y 를 채워 두므로 손 안 댄다.
    open_addr = (HOOK_BANK << 16) | info["labels"]["open_fetch"]
    oc = common.snes2off(OPEN_CALL_SITE)
    want_open = bytes([0xB7, 0x23, 0xC8, 0x8C, 0x44, 0x1B])
    if bytes(rom[oc : oc + OPEN_PATCH_LEN]) != want_open:
        raise SystemExit(f"오프닝 소비 지점이 예상과 다르다: {rom[oc : oc + OPEN_PATCH_LEN].hex()}")
    out[oc : oc + OPEN_PATCH_LEN] = bytes(
        [0x22, open_addr & 0xFF, (open_addr >> 8) & 0xFF, HOOK_BANK, 0xEA, 0xEA]
    )
    # 5b. 오프닝 줄 끝: `$1B81 += $1B83`(칸 수) 루프 11B → `JSL open_advance`($1B81 = 소비한 바이트)
    #     + NOP×7. 뒤이은 `$1E:E0C6`(스택 복원·RTS)로 그대로 떨어진다.
    adv_addr = (HOOK_BANK << 16) | info["labels"]["open_advance"]
    oa = common.snes2off(OPEN_ADVANCE_SITE)
    want_adv = bytes([0xAE, 0x83, 0x1B, 0xCA, 0x30, 0x05, 0xEE, 0x81, 0x1B, 0x80, 0xF8])
    if bytes(rom[oa : oa + OPEN_ADVANCE_LEN]) != want_adv:
        raise SystemExit(f"오프닝 줄 끝 자리가 예상과 다르다: {rom[oa : oa + OPEN_ADVANCE_LEN].hex()}")
    out[oa : oa + OPEN_ADVANCE_LEN] = bytes(
        [0x22, adv_addr & 0xFF, (adv_addr >> 8) & 0xFF, HOOK_BANK] + [0xEA] * 7
    )
    # 5c. PPU 배치 세 자리: `LDA #imm / STA $210C`(5B) → `JSL ctx_*` + NOP. 컨텍스트의 정본.
    for site, imm, ctx in PPU_CTX_SITES:
        so = common.snes2off(site)
        if bytes(rom[so : so + 5]) != bytes([0xA9, imm, 0x8D, 0x0C, 0x21]):
            raise SystemExit(f"PPU 배치 자리가 예상과 다르다 {common.fmt(site)}: {rom[so : so + 5].hex()}")
        ctx_addr = (HOOK_BANK << 16) | info["labels"]["ctx_open" if ctx else "ctx_game"]
        out[so : so + 5] = bytes([0x22, ctx_addr & 0xFF, (ctx_addr >> 8) & 0xFF, HOOK_BANK, 0xEA])
    # 6. 폰트 벌크카피 세 자리: `JSR $E6B3` → `JSR <뱅크 $1E 트램펄린>`(같은 3바이트).
    #    트램펄린은 원 호출을 그대로 하고 `JSL font_reset` 으로 오너 표를 비운 뒤 돌아온다.
    reset_addr = (HOOK_BANK << 16) | info["labels"]["font_reset"]
    ft = common.snes2off(FONT_TRAMPOLINE)
    if rom[ft : ft + 8] != b"\xff" * 8:
        raise SystemExit(f"폰트 트램펄린 자리가 비어 있지 않다: {rom[ft : ft + 8].hex()}")
    out[ft : ft + 8] = bytes(
        [
            0x20,
            0xB3,
            0xE6,  # JSR $E6B3 (원본 그대로)
            0x22,
            reset_addr & 0xFF,
            (reset_addr >> 8) & 0xFF,
            HOOK_BANK,  # JSL font_reset
            0x60,  # RTS
        ]
    )
    for site in FONT_CALL_SITES:
        so = common.snes2off(site)
        if bytes(rom[so : so + 3]) != bytes([0x20, 0xB3, 0xE6]):
            raise SystemExit(f"폰트 벌크카피 호출 자리가 예상과 다르다 {common.fmt(site)}: {rom[so : so + 3].hex()}")
        out[so : so + 3] = bytes([0x20, FONT_TRAMPOLINE & 0xFF, (FONT_TRAMPOLINE >> 8) & 0xFF])
    info.pop("labels")
    info["glyph_bytes"] = len(g)
    info["hook_bytes"] = len(blob)
    return info


def patch_ranges() -> list[tuple[int, int]]:
    """원본 1MB 안에서 우리가 바꾸는 자리(무변경 구간 검사용)."""
    return [
        (common.snes2off(CALL_SITE), common.snes2off(CALL_SITE) + 3),
        (common.snes2off(TRAMPOLINE), common.snes2off(TRAMPOLINE) + 5),
        (common.snes2off(BUF_CALL_SITE), common.snes2off(BUF_CALL_SITE) + 3),
        (common.snes2off(BUF_TRAMPOLINE), common.snes2off(BUF_TRAMPOLINE) + 5),
        (common.snes2off(NAME_TRAMPOLINE), common.snes2off(NAME_TRAMPOLINE) + 5),
        (common.snes2off(NAME13_TRAMPOLINE), common.snes2off(NAME13_TRAMPOLINE) + 5),
        *[(common.snes2off(m), common.snes2off(m) + MVN_LEN) for m, _l in MVN_SITES],
        *[(common.snes2off(s_), common.snes2off(s_) + NAME_BLOCK) for s_, _j in NAME_SITES],
        (common.snes2off(NMI_CALL), common.snes2off(NMI_CALL) + 3),
        (common.snes2off(NMI_STUB), common.snes2off(NMI_STUB) + 8),
        (common.snes2off(OPEN_CALL_SITE), common.snes2off(OPEN_CALL_SITE) + OPEN_PATCH_LEN),
        (common.snes2off(OPEN_ADVANCE_SITE), common.snes2off(OPEN_ADVANCE_SITE) + OPEN_ADVANCE_LEN),
        *[(common.snes2off(s_), common.snes2off(s_) + 5) for s_, _i, _c in PPU_CTX_SITES],
        *[(common.snes2off(s_), common.snes2off(s_) + 3) for s_ in FONT_CALL_SITES],
        (common.snes2off(FONT_TRAMPOLINE), common.snes2off(FONT_TRAMPOLINE) + 8),
    ]
