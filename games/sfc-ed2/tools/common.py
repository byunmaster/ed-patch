"""sfc-ed2 공용 — 원본 지문 · HiROM 주소 변환 · 경로 상수.

⚠ **sfc-ed1 과 다른 게임이다** — ED1 은 LoROM 1MB, ED2 는 **HiROM 2MB(Fast, map $31)**. ED1 의
`snes2off`·`ROM_SIZE`·`HEADER_TITLE` 을 그대로 가져오면 조용히 틀린다.
⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다(patcher-checklist 2).

🔴 주소는 `$뱅크:오프셋` 으로 적는다. HiROM 은 뱅크 $C0~$FF 가 롬 64KB 통째로 사상된다(미러 $40~$7D,
$00~$3F 의 $8000~ 도 같은 자리):
    file_offset = (bank & 0x3F) * 0x10000 + (addr & 0xFFFF)
파일 오프셋과 섞어 적지 않는다.
"""

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "sfc-ed2"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"

ROM_NAME = "Dragon Slayer - Eiyuu Densetsu 2 (J).sfc"
ORIG_ROM = ORIG_DIR / ROM_NAME
ROM_SHA1 = "680539d0a7699adcf06eb0b1ba541603d3aa02e9"
ROM_SIZE = 1_572_864  # 12Mbit — 내부 헤더는 2MB($0B) 로 선언 (뒤 0.5MB 는 비어 있다)
ROM_CRC32 = 0xF409C139

# 내부 헤더($00:FFC0 = 파일 0xFFC0) — HiROM Fast(map $31) · ROM+SRAM(type $02) · SRAM 8KB(ram $03)
HEADER_OFF = 0xFFC0
HEADER_TITLE = b"DRAGON SLAYER LEGEND2"
# 벡터는 $00:FFB2.. 의 트램펄린(CLC XCE JML $C0:0000 등)을 가리킨다
RESET_VECTOR = 0xFFB2


def snes2off(addr: int) -> int:
    """`$bb:aaaa` 24비트 HiROM 주소 → 파일 오프셋. $00~$3F 뱅크는 $8000 이상만 롬이다."""
    bank = (addr >> 16) & 0xFF
    a = addr & 0xFFFF
    if bank < 0x40 or 0x80 <= bank < 0xC0:
        if a < 0x8000:
            raise ValueError(f"HiROM $00~$3F 뱅크는 $8000 이상만 롬이다: ${addr:06X}")
    return (bank & 0x3F) * 0x10000 + a


def off2snes(off: int) -> int:
    """파일 오프셋 → 정본 표기 `$C0+` 주소."""
    return (0xC0 + (off >> 16)) << 16 | (off & 0xFFFF)


def fmt(addr: int) -> str:
    return f"${(addr >> 16) & 0xFF:02X}:{addr & 0xFFFF:04X}"


def sha1_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


_rom_cache: bytes | None = None


def rom_bytes() -> bytes:
    """원본 롬 1.5MB 를 한 번만 읽는다. 지문이 어긋나면 그 자리에서 죽는다."""
    global _rom_cache
    if _rom_cache is None:
        if not ORIG_ROM.exists():
            raise SystemExit(f"원본 없음: {ORIG_ROM}")
        data = ORIG_ROM.read_bytes()
        if len(data) % 1024 != 0:
            raise SystemExit(
                f"복사기 헤더가 붙은 것으로 보인다: {ORIG_ROM}\n"
                f"  크기 {len(data):,}B 가 1024 로 안 나눠떨어진다(나머지 {len(data) % 1024}) — 앞 512B 를 잘라낸다."
            )
        if len(data) != ROM_SIZE:
            raise SystemExit(f"롬 크기가 다르다: {len(data):,}B (기대 {ROM_SIZE:,}B)")
        got = sha1_of(data)
        if got != ROM_SHA1:
            raise SystemExit(f"지문 불일치: {ROM_NAME}\n  기대 {ROM_SHA1}\n  실제 {got}")
        _rom_cache = data
    return _rom_cache


def header() -> dict:
    d = rom_bytes()
    h = d[HEADER_OFF : HEADER_OFF + 0x40]
    chk = int.from_bytes(h[0x1E:0x20], "little")
    cmpl = int.from_bytes(h[0x1C:0x1E], "little")
    return {
        "title": h[:21],
        "map": h[0x15],
        "type": h[0x16],
        "rom_kb": 1 << h[0x17],
        "ram_kb": (1 << h[0x18]) if h[0x18] else 0,
        "checksum": chk,
        "complement": cmpl,
        "complement_ok": (chk ^ cmpl) == 0xFFFF,
        "reset": int.from_bytes(d[0xFFFC:0xFFFE], "little"),
    }


def verify_originals() -> None:
    rom_bytes()
    h = header()
    assert h["title"] == HEADER_TITLE, h["title"]
    assert h["map"] == 0x31 and h["rom_kb"] == 2048, h
    assert h["complement_ok"], "내부 체크섬 보수가 안 맞는다"
    # 헤더 체크섬은 2MB 로 선언된 롬 기준(1.5MB 는 0.5MB 를 반복해 채운 합) — 합 대조는 정본 롬에서 확인
    assert h["checksum"] == 0xD4E6 and h["complement"] == 0x2B19, h
    d = rom_bytes()
    # 선언 2MB 중 뒤 0.5MB 는 마지막 0.5MB(0x100000~) 의 반복으로 합을 낸다(실측 일치)
    assert (sum(d) + sum(d[0x100000:])) & 0xFFFF == h["checksum"], "체크섬 합이 안 맞는다 — 손댄 롬이다"


if __name__ == "__main__":
    verify_originals()
    h = header()
    print(f"{GAME} 원본 OK  {ORIG_ROM.name}  {ROM_SIZE:,}B  sha1={ROM_SHA1[:12]}")
    print(f"  title={h['title'].decode()} map=${h['map']:02X} type=${h['type']:02X} rom={h['rom_kb']}KB ram={h['ram_kb']}KB")
    print(f"  checksum=${h['checksum']:04X} complement=${h['complement']:04X}  reset→${h['reset']:04X}")
