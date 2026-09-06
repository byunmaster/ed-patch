"""sfc-ed1 공용 — 원본 지문 · LoROM 주소 변환 · 경로 상수.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 쓰기 사전조건이 없는 쓰기 경로를 만들지 않는다).

🔴 **주소는 `$뱅크:오프셋`(LoROM, 64KB 뱅크에 $8000~$FFFF 만 롬)** 로 적는다.
    file_offset = bank * 0x8000 + (addr & 0x7FFF)
파일 오프셋으로만 적힌 상수는 뱅크 경계에서 조용히 틀린다 — 둘을 섞지 않는다.
"""

import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "sfc-ed1"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"

# 소장본은 zip 째다(mednafen 이 zip 을 직접 읽는다 — `scripts/emu.sh`). 도구는 zip 안의 .sfc 를
# 메모리로 편다. 헤더 없는 1MB 순수 롬(복사기 헤더 512B 없음 — 크기가 정확히 2^20).
ORIG_ZIP = ORIG_DIR / "SFC - Dragon Slayer - Eiyuu Densetsu (J).zip"
ROM_NAME = "Dragon Slayer - Eiyuu Densetsu (J).sfc"
ROM_SHA1 = "2fbc7d0b48f6017d4a2d65b3c37032ad708a6255"
ROM_SIZE = 1_048_576  # 8Mbit LoROM
ROM_CRC32 = 0x70BBA233

# 내부 헤더($00:FFC0 = 파일 0x7FC0) — LoROM(map $20) · ROM+SRAM(type $02) · SRAM 2KB(ram $01)
HEADER_OFF = 0x7FC0
HEADER_TITLE = b"DRAGON SLAYER LEGEND1"
RESET_VECTOR = 0x8209  # 에뮬 모드 RESET — $00:8209


def snes2off(addr: int) -> int:
    """`$bb:aaaa` 24비트 LoROM 주소 → 파일 오프셋. 뱅크 $80+ 는 미러(빠른 롬)라 같은 자리다."""
    bank = (addr >> 16) & 0x7F
    a = addr & 0xFFFF
    if a < 0x8000:
        raise ValueError(f"LoROM 은 $8000 이상만 롬이다: ${addr:06X}")
    return bank * 0x8000 + (a - 0x8000)


def off2snes(off: int) -> int:
    return ((off // 0x8000) << 16) | 0x8000 | (off % 0x8000)


def fmt(addr: int) -> str:
    return f"${(addr >> 16) & 0xFF:02X}:{addr & 0xFFFF:04X}"


def sha1_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


_rom_cache: bytes | None = None


def rom_bytes() -> bytes:
    """원본 롬 1MB 를 zip 에서 한 번만 편다. 지문이 어긋나면 그 자리에서 죽는다 —
    패치된 사본을 원본으로 오해하지 않기 위해."""
    global _rom_cache
    if _rom_cache is None:
        if not ORIG_ZIP.exists():
            raise SystemExit(f"원본 없음: {ORIG_ZIP}")
        with zipfile.ZipFile(ORIG_ZIP) as zf:
            data = zf.read(ROM_NAME)
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
        "checksum_ok": (chk ^ cmpl) == 0xFFFF and (sum(d) & 0xFFFF) == chk,
        "reset": int.from_bytes(d[0x7FFC:0x7FFE], "little"),
    }


def verify_originals() -> None:
    rom_bytes()
    h = header()
    assert h["title"] == HEADER_TITLE, h["title"]
    assert h["map"] == 0x20 and h["rom_kb"] == 1024, h
    assert h["checksum_ok"], "내부 체크섬이 안 맞는다 — 손댄 롬이다"
    assert h["reset"] == RESET_VECTOR, hex(h["reset"])


if __name__ == "__main__":
    verify_originals()
    h = header()
    print(
        f"원본 OK: {ROM_NAME} ({ROM_SIZE:,}B) LoROM · SRAM {h['ram_kb']}KB · "
        f"체크섬 {h['checksum']:04X} · RESET {fmt(h['reset'])}"
    )
