"""sfc-ed1 공용 — 원본 지문 · LoROM 주소 변환 · 경로 상수.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 쓰기 사전조건이 없는 쓰기 경로를 만들지 않는다).

🔴 **주소는 `$뱅크:오프셋`(LoROM, 64KB 뱅크에 $8000~$FFFF 만 롬)** 로 적는다.
    file_offset = bank * 0x8000 + (addr & 0x7FFF)
파일 오프셋으로만 적힌 상수는 뱅크 경계에서 조용히 틀린다 — 둘을 섞지 않는다.
"""

import hashlib
import os
import sys
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
# 대사창 가변 폭(VWF, `hook_vwf.py`) — **정본 빌드에서 켠다**(마스터 판정 2026-10-08, D안 유지).
# 공백·`. , ? !` 가 4px 로 그려진다. 꺼진 경로(`ED_VWF=0`)는 시험·대조용으로 남기고 **다른 빌드 칸**(`<꼬리표>-novwf`)에 굽는다.
VWF = os.environ.get("ED_VWF") != "0"
# 🔴 시험 빌드 전용 디버그 진입(`debugpatch.py`) — `ED_DEBUG=1` 이면 꼬리표가 `test-debug` 로 **강제**된다(제품 칸을 못 덮는다).
DEBUG = os.environ.get("ED_DEBUG") == "1"
# 꼬리표는 `test-*`(시험) 또는 `debug`(마스터용 디버그 빌드)만 받는다 — 그 밖의 값·미지정은 `test-debug` 로 강제한다(제품 칸 `<브랜치>` 를 못 덮는다).
_DEBUG_TAGS_OK = lambda t: bool(t) and (t == "debug" or t.startswith("test-"))  # noqa: E731
_DEBUG_TAG = os.environ.get("ED_BUILD_TAG") if _DEBUG_TAGS_OK(os.environ.get("ED_BUILD_TAG")) else "test-debug"
BUILD_TAG = (_DEBUG_TAG if DEBUG else build_tag()) + ("" if VWF else "-novwf")
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"


def rom_input_fingerprint() -> str:
    """ROM 바이트를 만드는 입력의 지문 — 빌드 도구(`tools/*.py`) + 번역 정본(`textmap/*.json`) + 공용 조판(`shared/text/*.py`).

    빌드가 이 값을 `manifest.json` 에 적고, 촬영 도구(`headless.py`)가 지금 값과 같을 때만 시작한다 — 옛 롬으로 전수 촬영해 놓고
    최신처럼 보고하는 사고(2026-10-19: 신부 E0·엘리베이터 부호가 없는 롬으로 6천 장)를 막는다. 시험·Lua·문서는 롬에 안 닿아 뺀다.
    """
    h = hashlib.sha1()
    parts = [
        # 검사기(`check_*.py`)·촬영 실행기(`headless.py`)는 롬을 안 만든다 — 손봐도 롬이 낡았다고 하지 않는다
        *sorted(f for f in (GAME_DIR / "tools").glob("*.py") if f.name != "headless.py" and not f.name.startswith("check_")),
        *sorted((GAME_DIR / "textmap").glob("*.json")),
        *sorted((ROOT / "shared" / "text").glob("*.py")),
    ]
    for f in parts:
        h.update(f.relative_to(ROOT).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()

# 소장본은 압축 안 한 순정 .sfc 파일이다(mednafen 은 zip 도 읽지만 도구는 파일을 직접 연다 —
# `scripts/emu.sh` 는 그쪽대로 알아서 찾는다). 헤더 없는 1MB 순수 롬 — 복사기 헤더(512B) 가
# 붙으면 파일 크기가 1024 로 안 나눠떨어진다(1,049,088 % 1024 = 512) — `rom_bytes()` 가
# 그 자리에서 잡는다. 2026-09-15 zip 추출본으로 갈음(원본 zip 은 원본 폴더에 그대로 둔다).
ROM_NAME = "Dragon Slayer - Eiyuu Densetsu (J).sfc"
ORIG_ROM = ORIG_DIR / ROM_NAME
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
    """원본 롬 1MB 를 파일에서 한 번만 읽는다. 지문이 어긋나면 그 자리에서 죽는다 —
    패치된 사본을 원본으로 오해하지 않기 위해."""
    global _rom_cache
    if _rom_cache is None:
        if not ORIG_ROM.exists():
            raise SystemExit(f"원본 없음: {ORIG_ROM}")
        data = ORIG_ROM.read_bytes()
        # 복사기 헤더(512B) 방어 — 있으면 이후 모든 오프셋이 512 밀려 조용히 틀린다.
        if len(data) % 1024 != 0:
            raise SystemExit(
                f"복사기 헤더가 붙은 것으로 보인다: {ORIG_ROM}\n"
                f"  크기 {len(data):,}B 가 1024 로 안 나눠떨어진다(나머지 {len(data) % 1024}) — "
                "앞 512B 를 잘라내고 다시 시도한다."
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
