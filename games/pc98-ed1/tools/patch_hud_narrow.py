#!/usr/bin/env python3
"""필드 HUD·LOAD 슬롯 지명 — **좁은 출력기(8px)** 전용 글리프 + 가운데 정렬.

## 왜 따로인가

필드/LOAD 는 `0x7d3c`(좁은 출력기)로 그린다 — 대사창의 `0x7d06`(16px, `font.py`+
`patch_font_hook` 이 이미 훅한 경로)과 **완전히 다른 코드**다. 좁은 경로는 CGROM 을
직접 읽어 8px 로 압축(`0x7e49`)하므로, 우리가 뺏은 한글 구(`0x40~0x58`)를 읽으면
**한글 표가 아니라 원본 한자를 압축한 잡음**이 나온다(devlog 09-27 서른두 번째).
⇒ **좁은 경로만의 훅**이 따로 필요하다.

## 좁은 경로의 실측 두 가지 (2026-09-27, 8px 자리 조사 중 발견)

1. **그래픽 평면에 바이트 단위로 직접 쓴다** — 대사창의 매달기 마무리(`0x7f07`)와 같은
   블리터를 쓴다. 다만 글자마다 정확히 +1(8px)만 전진해 **격자에 못박혀 있다.**
2. 🔴 **ASCII/반각(0x20~0x7F, 공백 포함)은 그리지도 전진하지도 않는다**
   (`0x7d45~0x7d60`: `dec si`로 절반만 되돌리고 재시도) — 이 경로가 실제로 쓰인 적이
   없어(원문은 순수 일본어 지명이라 반각이 안 낀다) **아무도 몰랐던 동작**이다.
   ⇒ **이름 안 낱말 사이 공백은 좁은 화면에선 사라진다**(자리도 안 차지한다) — 알려진
   한계로 남긴다. 정렬 계산(아래)은 이 사라짐을 **그대로 반영**한다(실제로 그려질
   글리프 수만 센다).

## 자리(칸) — 하드 캡, 폰트와 무관 (devlog 서른아홉 번째 정정)

이름 칸은 `0x946b`(전 지역 공용 피커)가 **항상 정확히 12B(=6 글리프)** 를 복사하고
terminator 를 찍는다(`mov cx,6/rep movsw` — 손댈 수 없는 하드 값). 접미사
(`program:0x4ee6`)도 **항상 정확히 4B(=2 글리프)** 다(`movsw`×2, 근처/입구 중 하나).
🔴 이전 조사의 "80px/96px" 예산은 상자 그래픽 폭을 잰 것이라 틀렸다 — 실제 글자 자리는
**6+2** 로 하드 고정이고, 어떤 폰트를 걸어도 글자 수 한도는 안 변한다.

## 이름 칸은 **마을 안(16px)과 표를 같이 쓴다** — 인코딩은 못 바꾸고 정렬은 코드로

`0x946b`는 town(`0x76e2`,16px)·field(`0x94a6`)·LOAD(`0x662a` 등) **셋 다** 부른다 —
같은 `program:0x497c` 바이트를 나눠 읽는다. ⇒ 이름 글자는 **대사창과 같은 전역 음절
인코딩**(`patch_scn.encode`, 구 0x40~0x58)을 그대로 두고, 우리 8px 훅은 **스파스 표**
(전역 색인 2,350칸 → 우리 글리프 칸, 없으면 빈칸)로 찾는다. **접미사만** 전용 구
(`SUFFIX_KU`)를 쓴다 — 접미사는 좁은 경로 말고 아무도 안 읽는다(호출자 전수 확인:
`0x662a`·`0x6648`·`0x664e`·`0x7713`·`0x7719` 뿐이라 겹칠 상대가 없다).

## 🔴 09-27 실측 — 부트섹터 꼬리는 **영구 발판 자리로 못 쓴다**

첫 판은 근처 발판을 부트섹터 꼬리(`0x3f0`, 폰트 훅 로더가 다 안 쓴 빈 자리)에 뒀다가
**인게임 LOAD 화면 이후 입력이 멎었다.** `patch_josa_hook`·`patch_font_hook` 이 쓰는
발판(`0x5a5b`)은 **본 프로그램 코드 안의 죽은 블록**이라 게임 내내 살아 있다고
**실제로 확인된** 자리인 반면, 부트섹터 꼬리는 「로더는 부팅 때만 돈다」— 그 메모리가
**부팅 이후에도 그대로 남는다는 보장은 어디에도 없었다**(추정이었지 실측이 아니었다).
LOAD 화면(부팅 한참 뒤) 시점엔 그 자리가 다른 것으로 덮였을 공산이 크고, 그러면 우리
발판을 호출하는 순간 **임의 바이트를 코드로 실행**하게 된다 — 관측(같은 모양 반복
→ 멎음)과 정확히 들어맞는다.

⇒ **발판을 아예 없앤다.** `0x7d56` 의 원래 콜 둘(`call 0x7e49`·`call 0x7f07`, 합쳐
6바이트)을 **하나의 far 콜**로 바꾸고, 그리기(0x7f07 이 하던 그래픽 평면 블릿)까지
**우리 far 몸통 안에서 그대로 재현**한다 — 프로그램 코드로 다시 넘어오는 자리가
아예 없으므로 "그 메모리가 나중에도 살아 있나"를 걱정할 자리 자체가 없어진다.
(가운데 정렬(`field_shift`)은 **여전히 발판이 필요**해 이번 회차엔 뺐다 — 남는 다음
과제는 아래 `TODO` 참조.)
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import font
import patch_font_hook as H
import patch_sys
from text import sjis

FONT_BDF = common.ROOT / "shared" / "fonts" / "Galmuri11-Condensed.bdf"
BUFFER = H.SITES["program"]["buffer"]  # 0x4076 — 0x7e49 이 쓰던 그 버퍼(재사용)
NAME_SLOTS = 6

# ── 접미사 전용 구 — 좁은 경로 말고 아무도 안 읽으므로 자유롭게 고른다 ──────
SUFFIX_KU = H.KU_HI + 1  # 0x59 — 대사창 전역 표(0x40~0x58) 바로 다음, 안 겹친다
SUFFIX_CHARS = "근처입구"  # 순서가 곧 칸 번호(0..3)


def encode_suffix(text: str) -> bytes:
    out = bytearray()
    for ch in text:
        if ch not in SUFFIX_CHARS:
            raise SystemExit(f"🔴 접미사 표에 없는 글자 {ch!r} — SUFFIX_CHARS 를 넓힌다")
        idx = (SUFFIX_KU - 0x21) * 94 + SUFFIX_CHARS.index(ch)
        out += sjis.sjis_of_index(idx)
    return bytes(out)


# ── 이름 칸 — 전역 음절 인덱스(대사창과 같은 것)를 그대로 쓴다 ─────────────
def _name_chars() -> list[str]:
    items = [x.strip() for x in patch_sys.load()["program:0x497c"]["items"]]
    return sorted(set("".join(items).replace(" ", "")))


def name_glyph_map() -> dict[str, int]:
    """글자 → 우리 8px 표에서의 칸 번호(0..N-1)."""
    return {c: i for i, c in enumerate(_name_chars())}


# ── 8px 글리프 래스터화 — Galmuri11-Condensed(7×11, 8px 전진, 이미 8px 격자용 서체) ──
def _parse_bdf():
    txt = FONT_BDF.read_text(encoding="latin1")
    out = {}
    pat = re.compile(
        r"STARTCHAR \S+\nENCODING (-?\d+)\n(?:SWIDTH[^\n]*\n)?DWIDTH (\d+) 0\n"
        r"BBX (\d+) (\d+) (-?\d+) (-?\d+)\nBITMAP\n((?:[0-9A-Fa-f]+\n)*)ENDCHAR"
    )
    for m in pat.finditer(txt):
        code, _dw, w, h, xo, yo, bmp = m.groups()
        out[int(code)] = (int(w), int(h), int(xo), int(yo), bmp.split())
    return out


_BDF = None


def glyph_bits(ch: str) -> bytes:
    """한 글자 → 16B(행마다 1B, 상위비트가 왼쪽). 필요 글자 전수(조사 완료, `r5-hud-mixed.md`
    ⑥절) 중 칸 밖으로 나가는 화소는 없다."""
    global _BDF
    if _BDF is None:
        _BDF = _parse_bdf()
    w, _h, xo, yo, rows = _BDF.get(ord(ch), (0, 0, 0, 0, []))
    baseline = 16 - 3  # 아래에서 3px — 목업(r5-hud-4font-mockup.png)과 같은 기준선
    out = bytearray(16)
    for r, hx in enumerate(rows):
        bits = bin(int(hx, 16))[2:].zfill(len(hx) * 4)
        y = baseline - (len(rows) - 1 - r) - yo
        if not (0 <= y < 16):
            continue
        byte = 0
        for ci, b in enumerate(bits[:w]):
            xx = xo + ci
            if b == "1" and 0 <= xx < 8:
                byte |= 0x80 >> xx
        out[y] = byte
    return bytes(out)


def name_glyph_table() -> bytes:
    chars = [c for c, _ in sorted(name_glyph_map().items(), key=lambda kv: kv[1])]
    return b"".join(glyph_bits(c) for c in chars)


def suffix_glyph_table() -> bytes:
    return b"".join(glyph_bits(c) for c in SUFFIX_CHARS)


def name_sparse_index() -> bytes:
    """전역 음절 색인(0..2349, `H.KU_LO`~`H.KU_HI`) → 우리 이름 칸 번호. 없으면 0xFF(빈칸)."""
    syl, _ = font.build()
    gm = name_glyph_map()
    out = bytearray([0xFF]) * (H.KU_COUNT * 94)
    for c, slot in gm.items():
        out[syl.index(c)] = slot
    return bytes(out)


# ── 자리 — program 디스크 ────────────────────────────────────────────────
# 원래 콜 둘(`call 0x7e49` · `call 0x7f07`, 합쳐 6B)을 **하나의 far 콜**로 바꾼다.
# 발판이 필요 없다 — 그리기(그래픽 평면 블릿)까지 far 몸통 안에서 재현한다(위 docstring).
NARROW_AT = 0x7D56
NARROW_EXPECT = bytes.fromhex("e8f000e8ab01")  # `call 0x7e49` · `call 0x7f07`

# TODO(다음 회차) — 가운데 정렬은 발판이 있어야 한다(`mov di,0x68a4` 자리 3B 뿐이라
# far 콜 하나로 못 묶는다). 프로그램 코드 안의 **죽은 블록**(부팅 뒤에도 사는 게 확인된
# 자리, `0x5a5b` 류)을 새로 찾기 전엔 손 안 댄다 — 부트섹터 꼬리를 다시 쓰지 않는다.


def _nasm(src: str, d: Path, name: str, labels: tuple[str, ...] = ()) -> tuple[bytes, dict]:
    out = {}
    for tag, text in (("", src), ("l", src + "\n    dw " + ", ".join(labels) + "\n")):
        if tag and not labels:
            continue
        p = d / f"{name}{tag}.asm"
        p.write_text(text, encoding="utf-8")
        r = subprocess.run(
            ["nasm", "-f", "bin", str(p), "-o", str(p.with_suffix(".bin"))],
            capture_output=True,
            check=False,
            cwd=d,
        )
        if r.returncode:
            raise SystemExit("🔴 nasm 실패:\n" + r.stderr.decode())
        out[tag] = p.with_suffix(".bin").read_bytes()
    lab = {}
    if labels:
        import struct

        lab = dict(
            zip(
                labels, struct.unpack(f"<{len(labels)}H", out["l"][-2 * len(labels) :]), strict=True
            )
        )
    return out[""], lab


FAR_LABELS = ("narrow8",)


def far_asm() -> str:
    return f"""
BITS 16
org 0
narrow8:                    ; ax = JIS 코드(ah=구·al=점). 원래 0x7e49+0x7f07 을 대신해
                             ; 그래픽 평면까지 여기서 직접 그리고 retf(발판 없음, 위 docstring).
    push ax                  ; 🔴 원본 0x7e49 는 ax·bx·cx·dx·si·di 를 전부 보존한다(실측)
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    cmp ah, 0x{SUFFIX_KU:x}
    jne short .name
    mov bl, al
    sub bl, 0x21
    cmp bl, {len(SUFFIX_CHARS)}
    jae short .blank
    xor bh, bh
    shl bx, 1
    shl bx, 1
    shl bx, 1
    shl bx, 1
    add bx, suffix_glyphs
    mov bp, bx
    jmp short .blit
.name:
    cmp ah, 0x{H.KU_LO:x}
    jb  short .blank
    cmp ah, 0x{H.KU_HI:x}
    ja  short .blank
    push ax                 ; 원본 ax(ah=구·al=점) 를 잠깐 더 보존(아래서 al 로 다시 쓴다)
    sub ah, 0x{H.KU_LO:x}
    mov al, ah
    mov ah, 0
    mov bl, 94
    mul bl                  ; ax = 구 오프셋 × 94
    pop bx                  ; bx = 원본(bh=구·bl=점)
    sub bl, 0x21
    xor bh, bh
    add ax, bx              ; ax = 전역 음절 색인(0..2349)
    mov bx, ax
    mov al, [cs:bx+name_index]
    cmp al, 0xff
    je  short .blank
    xor ah, ah
    mov bx, ax
    shl bx, 1
    shl bx, 1
    shl bx, 1
    shl bx, 1
    add bx, name_glyphs
    mov bp, bx
    jmp short .blit
.blank:
    mov bp, blank_glyph
.blit:                       ; bp = 우리 16B 글리프(cs 기준). 0x7f07 을 그대로 흉내 낸다.
    mov dl, [0x404f]
    mov dh, dl
    shr dh, 1
    shr dh, 1
    shr dh, 1
    shr dh, 1
    mov bx, 0x409e
    cmp byte [0x85a], 0
    je  short .plane1
    mov bx, 0x40a4
.plane1:
    mov ax, 0xa800
    call blit_plane
    mov ax, 0xb000
    call blit_plane
    mov ax, 0xb800
    call blit_plane
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    retf

blit_plane:                  ; ax=평면 세그먼트 · bx=마스크 포인터(호출마다 +2) · dh/dl 은
                              ; 호출 사이에 안 리셋(0x7f07 과 같은 회전 규약). di 는 보존.
    ror dh, 1
    jb  short .skip
    push es
    push si
    push cx
    mov es, ax
    mov si, bp
    mov cx, 16
    ror dl, 1
    jae short .andmode
.ormode:
    mov al, [cs:si]
    or  al, [bx]
    mov [es:di], al
    add di, 0x50
    inc si
    loop .ormode
    jmp short .after
.andmode:
    mov al, [cs:si]
    not al
    and al, [bx]
    mov [es:di], al
    add di, 0x50
    inc si
    loop .andmode
.after:
    sub di, 0x500
    pop cx
    pop si
    pop es
.skip:
    add bx, 2
    ret

suffix_glyphs:
    incbin "suffix.bin"
blank_glyph:
    times 16 db 0
name_index:
    incbin "index.bin"
name_glyphs:
    incbin "names.bin"
"""


def FAR_SEG() -> int:
    import patch_josa_hook as J

    return J.FAR_SEG + -(-len(J.far_blob()) // 16)


def _no_near_jcc(blob: bytes, at: int) -> None:
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs

    for i in Cs(CS_ARCH_X86, CS_MODE_16).disasm(blob, at):
        if i.bytes[:1] == b"\x0f":
            raise SystemExit(f"🔴 {i.address:#07x} 386 전용 near Jcc — short 로 잡아라")


def _build():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "suffix.bin").write_bytes(suffix_glyph_table())
        Path(d, "index.bin").write_bytes(name_sparse_index())
        Path(d, "names.bin").write_bytes(name_glyph_table())
        far, lab = _nasm(far_asm(), Path(d), "far", FAR_LABELS)
    _no_near_jcc(far[: lab["narrow8"] + 200], 0)
    return far, lab


def far_blob() -> bytes:
    return _build()[0]


def build_patch() -> list[tuple[int, bytes, bytes]]:
    _far, lab = _build()
    seg = FAR_SEG()
    off = lab["narrow8"]
    call_far = bytes([0x9A]) + off.to_bytes(2, "little") + seg.to_bytes(2, "little")
    if len(call_far) > len(NARROW_EXPECT):
        raise SystemExit("🔴 far 콜이 자리를 넘는다")
    call_far += b"\x90" * (len(NARROW_EXPECT) - len(call_far))
    return [(NARROW_AT, NARROW_EXPECT, call_far)]


if __name__ == "__main__":
    gm = name_glyph_map()
    print(f"이름 글리프 {len(gm)}자 · 접미사 {len(SUFFIX_CHARS)}자(구 {SUFFIX_KU:#04x})")
    far = far_blob()
    print(f"far 몸통 {len(far)}B · FAR_SEG {FAR_SEG():#06x}")
    for off, exp, new in build_patch():
        print(f"  {off:#07x}  {len(new):3d}B  ← {exp.hex(' ') if exp else '(zero)'}")
