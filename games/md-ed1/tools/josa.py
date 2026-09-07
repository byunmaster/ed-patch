"""조사(종성) 훅 — 이름 뒤 조사를 **런타임에** 고른다. 병기 `을(를)` 을 없앤다.

    python3 tools/josa.py --check    # 후킹 자리·죽은 코드·기계어 검산
    python3 tools/josa.py --asm      # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 왜 이렇게 푸는가

PS1 은 조립 버퍼를 1패스로 훑어 병기를 줄이는 방식이었다. **MD 는 조립 버퍼가 없다** — 렌더러
(`$978C`)가 스트림에서 글자를 바로 그린다. 대신 이름 삽입 코드(`02` 배우 · `0E` 아이템)가
**렌더러를 재귀 호출**한다는 게 실마리다(`$A94A`: 이름 포인터를 a1 에 넣고 `bsr $978C`).
⇒ 「마지막에 그린 글자」를 RAM 에 적어 두는 대신, **이름이 어디 있는지 우리가 다시 찾아** 끝 글자를
본다. 새 RAM 을 한 칸도 안 쓴다.

## 제어코드

원본 문안이 **한 번도 안 쓰는** 코드 둘을 가져온다 — `EB`·`EC` 는 핸들러가 `rts` 하나뿐인 빈 코드다
(실측 2026-09-06: 대본·전투·시스템·자막 전량에서 0회, 핸들러 `$A4D0` = rts).

    EB p   배우 이름 기준 조사 — 이름은 `($FF3470)` 의 첫 바이트(배우 번호) → `$FF1DBC + n*0x40 + 0x30`
    EC p   아이템 이름 기준 조사 — 이름 버퍼 `$FF2028`
    p = 0 은/는 · 1 이/가 · 2 을/를

정본에선 `<02>을(를)` 대신 `<02><eb02>` 로 쓴다.

## 어디에 무엇을 쓰나

    0x9FE2 + i    코드별 피연산자 길이(디스패처 `$9FA0` 가 읽고 핸들러 뒤에 a1 을 그만큼 민다)
    0xA018 + i*2  코드별 핸들러 **워드 오프셋**(0xA018 기준) — ⚠ 부호 있는 16비트라 ±32KB 안이어야 한다
    0xA4D2~       코드 `EE` 의 죽은 핸들러 자리 — 여기에 `jmp <꼬리>.l` 트램펄린 둘을 둔다
    꼬리          진짜 핸들러 + 종성 비트표(한글·반각) + 조사 코드 쌍

종성 판정은 **비트표**다 — 한글 코드는 `hangul_codes.json` 의 등록 순서라 규칙이 없다(빌드가 표를
만든다). 반각은 숫자·라틴 글자를 한국어로 읽을 때의 받침(1=일 · 3=삼 · L=엘 …)을 담는다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ARGLEN_TBL = 0x9FE2  # 코드별 피연산자 길이
HANDLER_TBL = 0xA018  # 코드별 핸들러 워드 오프셋(이 자리 기준)
DEAD_HANDLER = 0xA4D2  # 코드 EE 의 핸들러 몸통(30B) — 원본 문안이 EE 를 안 쓴다
CODE_ACTOR, CODE_ITEM = 0xEB, 0xEC
IDX_ACTOR, IDX_ITEM = CODE_ACTOR - 0xCB, CODE_ITEM - 0xCB  # 표 색인(디스패처가 0xCB 를 뺀다)
RENDER = 0x978C  # 렌더러 — a1 = 문안, d0 = 재귀 표식
MAGIC = 0xFEDCBA98  # 이름 삽입 핸들러가 쓰는 값 그대로
ACTOR_PTR = 0xFF3470  # 배우 레코드 포인터
PARTY_REC = 0xFF1DBC  # 레코드 배열(0x40 간격, 이름은 +0x30)
ITEM_BUF = 0xFF2028  # 아이템 이름 버퍼

# p → (받침 없음, 받침 있음)
PAIRS = [("는", "은"), ("가", "이"), ("를", "을")]
# 반각을 한국어로 읽었을 때 받침이 있는 글자(1=일 · 3=삼 · 6=육 · 7=칠 · 8=팔 · 0=영 · L/M/N/R)
ASCII_FINAL = set("013678") | set("LMNR") | set("lmnr")


def bitmap(bits: list[bool]) -> bytes:
    """LSB 우선 비트맵 — 핸들러가 `btst d0,d1` 로 읽는다(비트 0 이 LSB)."""
    out = bytearray((len(bits) + 7) // 8)
    for i, v in enumerate(bits):
        if v:
            out[i >> 3] |= 1 << (i & 7)
    return bytes(out)


def has_final(ch: str) -> bool:
    """한글 음절에 종성이 있나 — (코드 − 0xAC00) % 28 ≠ 0."""
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def tables(cs) -> tuple[bytes, int]:
    """(한글 비트표 + 반각 비트표 + 조사 쌍, 한글 표 항목 수)."""
    codes = cs.hangul  # {글자: 코드}
    base = min(codes.values())
    n = max(codes.values()) - base + 1
    by_code = {v: k for k, v in codes.items()}
    hangul = bitmap([has_final(by_code.get(base + i, "")) for i in range(n)])
    ascii_ = bitmap([chr(0x20 + i) in ASCII_FINAL for i in range(0x60)])
    pairs = b"".join(
        struct.pack(">HH", codes[a], codes[b]) for a, b in PAIRS
    )  # (받침 없음, 있음)
    return hangul + ascii_ + pairs, n


def code(at: int, cs) -> tuple[bytes, bytes]:
    """(핸들러 기계어, 표) — `at` = 꼬리에 놓을 자리(짝수)."""
    tbl, n = tables(cs)
    base = min(cs.hangul.values())
    # 표는 코드 **뒤에** 붙는데 코드 안에 표 주소가 박힌다 — 길이를 먼저 재고(1패스) 자리를 넣어 다시 짠다.
    body = _asm(at, None, base, n)
    tbl_at = at + len(body)
    body = _asm(at, tbl_at, base, n)
    assert tbl_at == at + len(body), "코드 길이가 2패스에서 갈렸다"
    return body, tbl


def _asm(at: int, tbl_at: int | None, base: int, n: int) -> bytes:
    """손인코딩 — 표 자리를 모르는 1패스에선 0 으로 채워 길이만 잰다."""
    t = tbl_at if tbl_at is not None else 0
    hangul_tbl = t
    ascii_tbl = t + (n + 7) // 8
    pairs_tbl = ascii_tbl + 0x0C
    b = bytearray()

    def w(*vals):
        for v in vals:
            b.extend(struct.pack(">H", v))

    def l(v):
        b.extend(struct.pack(">I", v))

    # ── EB: 배우 이름 ─────────────────────────────────────────────
    w(0x48E7, 0xE0C0)  # movem.l d0-d2/a0-a1,-(a7)
    w(0x2079)
    l(ACTOR_PTR)  # movea.l ACTOR_PTR.l,a0
    w(0x7000)  # moveq #0,d0
    w(0x1010)  # move.b (a0),d0
    w(0xED88)  # lsl.l #6,d0
    w(0x41F9)
    l(PARTY_REC)  # lea PARTY_REC.l,a0
    w(0xD1C0)  # adda.l d0,a0
    w(0x41E8, 0x0030)  # lea $30(a0),a0
    common_from_actor = len(b)
    w(0x6000, 0)  # bra.w common (변위는 아래에서)
    # ── EC: 아이템 이름 ───────────────────────────────────────────
    item_entry = len(b)
    w(0x48E7, 0xE0C0)  # movem.l d0-d2/a0-a1,-(a7)
    w(0x41F9)
    l(ITEM_BUF)  # lea ITEM_BUF.l,a0
    # ── 공통: 이름의 마지막 글자를 찾는다 ─────────────────────────
    common = len(b)
    struct.pack_into(">h", b, common_from_actor + 2, common - (common_from_actor + 2))
    w(0x7200)  # moveq #0,d1        마지막 글자
    scan = len(b)
    w(0x7400)  # moveq #0,d2
    w(0x1418)  # move.b (a0)+,d2
    w(0x0C02, 0x0006)  # cmpi.b #6,d2
    done_br1 = len(b)
    w(0x6700, 0)  # beq.w done
    w(0x4A02)  # tst.b d2
    done_br2 = len(b)
    w(0x6700, 0)  # beq.w done
    w(0x0C02, 0x0081)  # cmpi.b #$81,d2
    half_br1 = len(b)
    w(0x6500, 0)  # bcs.w half        < 0x81 = 반각
    w(0x0C02, 0x00A0)  # cmpi.b #$a0,d2
    wide_br = len(b)
    w(0x6500, 0)  # bcs.w wide        0x81~0x9F = 전각
    w(0x0C02, 0x00E0)  # cmpi.b #$e0,d2
    half_br2 = len(b)
    w(0x6500, 0)  # bcs.w half        0xA0~0xDF = 반각 가나
    wide = len(b)
    struct.pack_into(">h", b, wide_br + 2, wide - (wide_br + 2))
    w(0xE14A)  # lsl.w #8,d2
    w(0x1418)  # move.b (a0)+,d2
    half = len(b)
    struct.pack_into(">h", b, half_br1 + 2, half - (half_br1 + 2))
    struct.pack_into(">h", b, half_br2 + 2, half - (half_br2 + 2))
    w(0x3202)  # move.w d2,d1
    w(0x6000, 0)
    struct.pack_into(">h", b, len(b) - 2, scan - (len(b) - 2))  # bra.w scan
    # ── 종성 판정 ─────────────────────────────────────────────────
    done = len(b)
    struct.pack_into(">h", b, done_br1 + 2, done - (done_br1 + 2))
    struct.pack_into(">h", b, done_br2 + 2, done - (done_br2 + 2))
    w(0x7400)  # moveq #0,d2        종성 플래그
    w(0x0C41, 0x0080)  # cmpi.w #$80,d1
    wide2_br = len(b)
    w(0x6400, 0)  # bcc.w wide2
    w(0x0441, 0x0020)  # subi.w #$20,d1
    pick_br1 = len(b)
    w(0x6500, 0)  # bcs.w pick
    w(0x0C41, 0x0060)  # cmpi.w #$60,d1
    pick_br2 = len(b)
    w(0x6400, 0)  # bcc.w pick
    w(0x41F9)
    l(ascii_tbl)  # lea ascii_tbl.l,a0
    bit_br = len(b)
    w(0x6000, 0)  # bra.w bit
    wide2 = len(b)
    struct.pack_into(">h", b, wide2_br + 2, wide2 - (wide2_br + 2))
    w(0x0441, base & 0xFFFF)  # subi.w #base,d1
    pick_br3 = len(b)
    w(0x6500, 0)  # bcs.w pick
    w(0x0C41, n & 0xFFFF)  # cmpi.w #n,d1
    pick_br4 = len(b)
    w(0x6400, 0)  # bcc.w pick
    w(0x41F9)
    l(hangul_tbl)  # lea hangul_tbl.l,a0
    bit = len(b)
    struct.pack_into(">h", b, bit_br + 2, bit - (bit_br + 2))
    w(0x3001)  # move.w d1,d0
    w(0xE649)  # lsr.w #3,d1
    w(0xD0C1)  # adda.w d1,a0
    w(0x0240, 0x0007)  # andi.w #7,d0
    w(0x1210)  # move.b (a0),d1
    w(0x0101)  # btst d0,d1
    pick_br5 = len(b)
    w(0x6700, 0)  # beq.w pick        비트 0 = 받침 없음
    w(0x7401)  # moveq #1,d2
    # ── 조사를 골라 그린다 ────────────────────────────────────────
    pick = len(b)
    for br in (pick_br1, pick_br2, pick_br3, pick_br4, pick_br5):
        struct.pack_into(">h", b, br + 2, pick - (br + 2))
    w(0x7000)  # moveq #0,d0
    w(0x1011)  # move.b (a1),d0     p (피연산자 — a1 은 디스패처가 민다)
    w(0x0240, 0x0003)  # andi.w #3,d0
    w(0xE548)  # lsl.w #2,d0        p*4
    w(0xD442)  # add.w d2,d2        종성*2
    w(0xD042)  # add.w d2,d0
    w(0x41F9)
    l(pairs_tbl)  # lea pairs_tbl.l,a0
    w(0x3430, 0x0000)  # move.w (a0,d0.w),d2
    w(0x4842)  # swap d2
    w(0x343C, 0x0600)  # move.w #$0600,d2   → d2 = [코드][06][00]
    w(0x2F02)  # move.l d2,-(a7)
    w(0x224F)  # movea.l a7,a1
    w(0x203C)
    l(MAGIC)  # move.l #MAGIC,d0
    w(0x4EB9)
    l(RENDER)  # jsr RENDER.l
    w(0x588F)  # addq.l #4,a7
    w(0x4CDF, 0x0307)  # movem.l (a7)+,d0-d2/a0-a1
    w(0x4E75)  # rts
    _asm.item_entry = item_entry
    return bytes(b)


def plan(rom: bytes, cs, at: int) -> list[tuple[str, int, bytes]]:
    """(라벨, 자리, 바이트) — 꼬리 `at` 에 핸들러+표, 표 둘과 트램펄린을 고친다."""
    body, tbl = code(at, cs)
    item_entry = at + _asm.item_entry
    out = [("josa-code", at, body + tbl)]
    tramp = b"\x4e\xf9" + struct.pack(">I", at) + b"\x4e\xf9" + struct.pack(">I", item_entry)
    out.append(("josa-tramp", DEAD_HANDLER, tramp))
    for i, off in ((IDX_ACTOR, DEAD_HANDLER), (IDX_ITEM, DEAD_HANDLER + 6)):
        disp = off - HANDLER_TBL
        assert -0x8000 <= disp < 0x8000, "핸들러 표는 부호 있는 워드다 — ±32KB 안이어야 한다"
        out.append((f"josa-tbl:{i:02x}", HANDLER_TBL + i * 2, struct.pack(">h", disp)))
        out.append((f"josa-arg:{i:02x}", ARGLEN_TBL + i, b"\x01"))
    return out


def size(cs) -> int:
    body, tbl = code(0x1F0000, cs)  # 길이만 — 자리에 안 의존한다
    return len(body) + len(tbl)


def verify(body: bytes, at: int) -> list[str]:
    """디스어셈블로 되읽는다(루트 규율: 손인코딩은 검산한다)."""
    from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs

    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    out, p = [], 0
    for ins in md.disasm(body, at):
        out.append(f"{ins.address:06x}  {ins.mnemonic:9s} {ins.op_str}")
        p = ins.address + ins.size - at
    if p != len(body):
        out.append(f"⚠ {len(body) - p}B 가 디코드 안 됐다 (@{at + p:#x})")
    return out


def check(d: bytes) -> None:
    import font  # noqa: F401  (import 확인용)
    import hangul

    for c, idx in ((CODE_ACTOR, IDX_ACTOR), (CODE_ITEM, IDX_ITEM)):
        h = HANDLER_TBL + int.from_bytes(d[HANDLER_TBL + idx * 2 : HANDLER_TBL + idx * 2 + 2], "big")
        if d[h] != 0x4E or d[h + 1] != 0x75:
            raise SystemExit(f"코드 {c:02x} 의 원본 핸들러가 rts 가 아니다 @{h:#x}")
        if d[ARGLEN_TBL + idx] != 0:
            raise SystemExit(f"코드 {c:02x} 의 원본 피연산자 길이가 0 이 아니다")
    cs = hangul.Charset(d, set("는은가이를을"))
    body, tbl = code(0x1F0000, cs)
    print(f"  조사 훅 — 코드 {CODE_ACTOR:02x}/{CODE_ITEM:02x} · 기계어 {len(body)}B · 표 {len(tbl)}B")


if __name__ == "__main__":
    d = common.rom()
    if "--asm" in sys.argv:
        import hangul

        cs = hangul.Charset(d, set("는은가이를을"))
        body, _tbl = code(0x1F0000, cs)
        print("\n".join(verify(body, 0x1F0000)))
    else:
        check(d)
