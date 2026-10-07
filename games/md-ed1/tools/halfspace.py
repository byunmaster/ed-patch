"""「의␣」 — 보통 「의」를 그리고 **4px 더 전진**하는 합성 코드 하나(마스터 판정 2026-10-07 「반각 공백으로」).

    python3 tools/halfspace.py --check   # 후킹 자리가 원본 그대로인가
    python3 tools/halfspace.py --asm     # 손인코딩 기계어를 디스어셈블로 되읽어 출력

## 왜

아이템 칸은 14B(= 한글 7자)인데 「다이아의 지팡이」·「길모아의 무지개」는 반각 공백(1B)을 넣으면 15B 다.
칸을 넓히면 `$FF2028` 복사 버퍼 끝의 종결(0x06)을 덮어 `<0e>` 대사 삽입이 버퍼를 넘어 읽는다(devlog 10-07).
⇒ 공백을 **글자 안에 녹인다** — 「의」 글자 하나가 18px 를 차지한다. 글리프는 정상 「의」와 같은 비트맵이라
한 항목 안에서 글자 크기가 갈리지 않는다(마스터 기준).

⚠ **전진량은 4px 다(6px 가 아니다)** — 아이템 창 안쪽 폭이 88px 라 90px 가 되는 6px 는 끝 글자 오른쪽 2px(「이」의 ㅣ ·
「개」의 ㅣ)가 잘렸다(실측 10-07 캡처). 4px 면 88px 에 딱 들어가고, 글자 틈 최대 3px 보다 커 어절 틈으로 읽힌다.

## 렌더러 $978C — 넓은 글자 경로(0x9882~)

    0x9892  move.l #$80,d1
    0x9898  bsr.w $9b32          ← 글리프를 a2 에 그린다 (d0 = 코드)  ★ 여기를 후킹
    0x989e  d0 = $FF2014(피치 12) >> 1 = 6   → a2 += d0 · $FF2018 += d0   (바이트 = 2px)

그린 직후 d0 가 아직 코드다 — 이 코드면 a2 · $FF2018 을 2바이트(4px) 더 민다. 넘침 검사($A990)는 그리기 **전에**
12px 로 끝나므로 줄 끝에서도 안전하고, 어절 줄넘김(wordwrap)은 이 4px 빈 틈을 공백으로 읽는다(= 의도).

## 어디에 무엇을 쓰나

    0x9898            `bsr.w $9b32` → `bsr.w TRAMP`
    DEAD_HANDLER + 18 `jmp <본체>.l` (코드 EE 의 죽은 핸들러 30B 중 josa 12 · wrap 6 뒤)
    본체              wrap 꼬리 예약 안(wordwrap 본체 326B 뒤)
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hangul
import josa

PUA = ""  # 「의␣」 자리표시 — 문안엔 이 글자 하나로 적는다
BASE = "의"
SPACE = " "
EXTRA_BYTES = 2  # 4px = 4bpp 2바이트(위 ⚠)
SITE = 0x9898  # bsr.w $9b32
DRAW = 0x9B32
TRAMP = josa.DEAD_HANDLER + 18
CODE_OFF = 0x150  # wrap 꼬리 예약 안 오프셋(wordwrap 본체 326B = 0x146 뒤)
CODE_LEN = 28
EXTRA_PX = EXTRA_BYTES * 2


def plain(s: str) -> str:
    """검사·사전 대조용 — 합성 글자를 보통 글자 + 반각 공백으로 펼친다."""
    return s.replace(PUA, BASE + SPACE)


def ensure_glyph() -> None:
    hangul.CUSTOM_GLYPHS.setdefault(PUA, hangul.glyph_fill(BASE))


def chars() -> set[str]:
    ensure_glyph()
    return {PUA}


def code(cs) -> bytes:
    c = int.from_bytes(cs.encode_char(PUA), "big")
    b = bytearray()
    b += struct.pack(">HH", 0x0C40, c)  # cmpi.w #CODE,d0
    b += bytes([0x67, 0x06])  # beq.s +6
    b += struct.pack(">H", 0x4EF9) + struct.pack(">I", DRAW)  # jmp $9b32.l (보통 글자)
    b += struct.pack(">H", 0x4EB9) + struct.pack(">I", DRAW)  # jsr $9b32.l
    b += struct.pack(">H", 0x5088 | (EXTRA_BYTES << 9) | 2)  # addq.l #n,a2
    b += struct.pack(">H", 0x5039 | (EXTRA_BYTES << 9)) + struct.pack(">I", 0xFF2018)  # addq.b #n,$FF2018.l
    b += struct.pack(">H", 0x4E75)  # rts
    assert len(b) == CODE_LEN, len(b)
    return bytes(b)


def plan(cs, wrap_at: int) -> list[tuple[str, int, bytes]]:
    ensure_glyph()
    at = wrap_at + CODE_OFF
    disp = TRAMP - (SITE + 2)
    assert -0x8000 <= disp < 0x8000
    return [
        ("half-code", at, code(cs)),
        ("half-tramp", TRAMP, b"\x4e\xf9" + struct.pack(">I", at)),
        ("half-site", SITE, b"\x61\x00" + struct.pack(">h", disp)),
    ]


def check(d: bytes) -> None:
    disp = struct.unpack(">h", d[SITE + 2 : SITE + 4])[0]
    if d[SITE : SITE + 2] != b"\x61\x00" or SITE + 2 + disp != DRAW:
        raise SystemExit(f"후킹 자리 {SITE:#x} 가 `bsr.w $9B32` 가 아니다")
    print(f"  의␣ 반칸 전진 — 후킹 1 · 기계어 {CODE_LEN}B")


if __name__ == "__main__":
    if "--asm" in sys.argv:

        class _CS:
            hangul = {PUA: 0}

            def encode_char(self, _c):
                return b"\xaa\xbb"

        print("\n".join(josa.verify(code(_CS()), 0x1F0000)))
    else:
        check(common.rom())
