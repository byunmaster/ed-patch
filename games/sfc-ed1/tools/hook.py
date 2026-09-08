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
V_U0 = VAR + 18  # 워드: NMI 임시(글리프 색인)
V_U1 = VAR + 20  # NMI 임시(슬롯 번호)
V_UV = VAR + 21  # 워드: NMI 임시(VRAM 워드 주소)
Q_SLOT, Q_LO, Q_HI = VAR + 32, VAR + 48, VAR + 64
VAR_END = VAR + 80
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
    a.label("alloc")
    a.sep(imm=0x20)
    a.op("lda", addr=V_NEXT, mode="long")
    a.cmp(imm=nslot)
    a.bcc(label="al0")
    a.lda(imm=0x00)  # 표 밖으로 새지 않게 가둔다
    a.label("al0")
    a.op("sta", addr=V_T1, mode="long")
    a.inc()
    a.cmp(imm=nslot)
    a.bcc(label="al1")
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
    a.op("lda", addr=V_HEAD, mode="long")
    a.inc()
    a.op("and", imm=QN - 1)
    a.op("sta", addr=V_HEAD, mode="long")
    a.op("lda", addr=V_T1, mode="long")
    a.rep(imm=0x20)
    a.op("and", imm=0x00FF, m16=True)
    a.tax()
    a.sep(imm=0x20)
    a.op("lda", addr="slot_code", mode="absx")
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
    for v in (V_HEAD, V_TAIL, V_NEXT, V_PEND_N):
        a.op("sta", addr=v, mode="long")
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
    a.op("lda", addr="slot_vlo", mode="absx")
    a.op("sta", addr=V_UV, mode="long")
    a.op("lda", addr="slot_vhi", mode="absx")
    a.op("sta", addr=V_UV + 1, mode="long")
    a.rep(imm=0x30)
    a.op("lda", addr=V_U0, mode="long")
    for _ in range(5):
        a.asl()
    a.tax()
    a.op("lda", addr=V_UV, mode="long")
    a.op("sta", addr=0x2116, mode="abs")
    a.ldy(imm=0x0008, m16=True)
    a.label("u1")
    a.op("lda", addr=GLYPH_BASE, mode="longx")
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u1")
    a.op("lda", addr=V_UV, mode="long")
    a.clc()
    a.adc(imm=0x0080, m16=True)
    a.op("sta", addr=0x2116, mode="abs")
    a.ldy(imm=0x0008, m16=True)
    a.label("u2")
    a.op("lda", addr=GLYPH_BASE, mode="longx")
    a.op("sta", addr=0x2118, mode="abs")
    a.inx()
    a.inx()
    a.dey()
    a.bne(label="u2")
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
    ]
