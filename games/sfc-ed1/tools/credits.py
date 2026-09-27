"""엔딩 스태프롤 — 한글 줄(`textmap/credits.json`)을 인코딩해 사전 뱅크에 굽고 크롤 포인터를 옮긴다.

원문은 `$06:FB55`(메시지 표 밖, 850B = 10칸 × 85줄)이고 `$1E:F23D` 가 긴 포인터 `$23~$25` 에 직접
세팅해 오프닝과 같은 크롤 엔진(`$00:E5A6` → 우리 `open_fetch`)으로 읽는다(devlog 09-20(20)).
원문 가나를 그대로 두면 그 바이트가 한글 선두 코드(`encode.LEADS`)로 읽혀 **한글·가나가 섞여**
나온다(마스터 폰 캡처 2026-09-26) — 가나와 한글 글리프가 같은 타일 자리를 쓰니 섞어 쓸 수도 없다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001  (common 보다 먼저)
import common
import dicts
import encode

ROW_CELLS = 10
N_ROWS = 85
ORIG = 0x06FB55
SITE = 0x1EF23D  # LDX #$FB55 / STX $0023 / LDA #$06 / STA $0025
SITE_ORIG = bytes([0xA2, 0x55, 0xFB, 0x8E, 0x23, 0x00, 0xA9, 0x06, 0x8D, 0x25, 0x00])
END = 0xFF  # 원문도 850B 뒤가 `$FF`
# 🔴 끝 판정 — `$1E:F327 LDX $1B81 / CPX #$0352 / BPL 끝`. 스태프롤은 **읽은 바이트가 850 에 닿으면** 끝난다
# (원문 = 10칸 × 85줄 × 1바이트). 우리 크롤 훅은 줄 위치를 바이트로 세므로(한글 2바이트) 비교값을 한글판
# 길이로 바꾸지 않으면 850B(13쪽 감수)에서 잘려 디렉터~제작 네 쪽이 빠진다(2026-09-26 실측).
LEN_SITE = 0x1EF32A  # CPX #imm16
LEN_ORIG = bytes([0xE0, 0x52, 0x03])


def rows() -> list[str]:
    d = json.loads((common.GAME_DIR / "textmap" / "credits.json").read_text(encoding="utf-8"))
    r = d["rows"]
    if len(r) != N_ROWS:
        raise SystemExit(f"크레딧 줄 수 {len(r)} ≠ {N_ROWS}(원문 페이지 구조와 같아야 한다)")
    return r


def texts() -> list[str]:
    return rows()


def encode_rows(rep_index: dict[str, int]) -> bytes:
    out = bytearray()
    for i, row in enumerate(rows()):
        if len(row) > ROW_CELLS:
            raise SystemExit(f"크레딧 {i}줄 {row!r} 이 {ROW_CELLS}칸을 넘는다")
        for ch in row:
            if encode.is_glyph(ch) or ch in encode.CREDIT_GLYPHS:
                out += encode.glyph_code(rep_index[ch])
            elif ch in encode.KR_TABLE:
                out.append(encode.KR_TABLE[ch])
            else:
                raise SystemExit(f"크레딧에 못 넣는 글자: {ch!r} ({i}줄)")
        out += bytes([encode.KR_TABLE[" "]]) * (ROW_CELLS - len(row))
    out.append(END)
    return bytes(out)


def bake(out: bytearray, rom: bytes, rep_index: dict[str, int], org: int) -> dict:
    so = common.snes2off(SITE)
    if bytes(rom[so : so + len(SITE_ORIG)]) != SITE_ORIG:
        raise SystemExit(
            f"크레딧 포인터 자리가 예상과 다르다: {rom[so : so + len(SITE_ORIG)].hex()}"
        )
    b = encode_rows(rep_index)
    if org + len(b) > 0x10000:
        raise SystemExit(f"사전 뱅크가 넘친다: 크레딧 {org:#x}+{len(b)}")
    do = common.snes2off((dicts.BANK << 16) | org)
    out[do : do + len(b)] = b
    out[so + 1] = org & 0xFF
    out[so + 2] = org >> 8
    out[so + 7] = dicts.BANK
    lo = common.snes2off(LEN_SITE)
    if bytes(rom[lo : lo + 3]) != LEN_ORIG:
        raise SystemExit(f"크레딧 끝 판정 자리가 예상과 다르다: {rom[lo : lo + 3].hex()}")
    n = len(b) - 1  # 끝 코드 앞까지
    out[lo + 1] = n & 0xFF
    out[lo + 2] = n >> 8
    return {"자리": common.fmt((dicts.BANK << 16) | org), "바이트": len(b), "next": org + len(b)}
