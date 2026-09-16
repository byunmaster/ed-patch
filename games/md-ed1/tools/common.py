"""md-ed1 공용 — 원본 지문 · 롬 헤더 · 경로 상수.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 쓰기 사전조건이 없는 쓰기 경로를 만들지 않는다).

🔴 **원본은 물리적으로 SMD 인터리브가 아니라 plain BIN 이다.** 0x100 에 `SEGA MEGA DRIVE`
가 그대로 있고 벡터 테이블이 0 에 있다. `docs/ports-survey.md` 가 「SMD 인터리브 · 커스텀 문자
테이블」로 적은 건 옛 `.zip` 안의 `.SMD` 를 디인터리브해 읽은 결과였다(그래서 SJIS 가 0 으로
나왔다). 실제 대본은 **SJIS 평문**이다(`docs/status.md`). 좌표는 전부 **롬 파일 오프셋 = 68000
주소**(매퍼 없음, 2MB). 2026-09-15 부터 소장본이 압축 없는 `.bin` 으로 옮겨져(HDD 컬렉션),
읽기 경로도 그에 맞춰 zip 해제를 걷어냈다 — 바이트는 옛 zip 안의 `.SMD` 와 sha1 까지 동일하다.
"""

import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "md-ed1"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"
# 에뮬 실행용 사본 자리 — `ed1.bin` 으로 둔다(원본 그 자체엔 안 쓴다, 빌드가 실수로 원본을 덮지
# 않게 사본을 따로 둔다).
EMU_DIR = WORK / "emu"

# 소장본은 압축 없는 plain BIN 하나(2,097,152B).
ORIG_ROM = ORIG_DIR / "Dragon Slayer - Eiyuu Densetsu (J).bin"
ORIG_SHA1 = "f67c9139bbc93f171e274a5cd3fba66480cd8244"
ROM_SIZE = 2_097_152

# 헤더 실측 (0x100~). 체크섬은 0x200~ 의 16비트 BE 합 & 0xFFFF — 롬을 고치면 다시 맞춰야 한다.
HDR_SERIAL = b"GM G-5542   00"
HDR_CHECKSUM = 0x5D33
HDR_DOMESTIC = "ﾄﾞﾗｺﾞﾝｽﾚｲﾔｰ 英雄伝説"
SRAM_RANGE = (0x200001, 0x203FFF)  # RA F8 20 — 홀수 바이트 8KB 백업 SRAM
FREE_TAIL = (
    0x1EC35C,
    0x1FFFFE,
)  # FF 로 찬 빈 공간 81,058B(마지막 2B 는 00 00). 헤더 ROM end 는 0x1FFFFF


def sha1_of_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


_rom_cache: bytes | None = None


def rom() -> bytes:
    """원본 롬 바이트. 지문이 어긋나면 그 자리에서 죽는다 — 패치된 사본을 원본으로 오해하지 않기 위해."""
    global _rom_cache
    if _rom_cache is not None:
        return _rom_cache
    if not ORIG_ROM.exists():
        raise SystemExit(f"원본 없음: {ORIG_ROM}")
    data = ORIG_ROM.read_bytes()
    if len(data) != ROM_SIZE:
        raise SystemExit(f"크기 불일치: {len(data)} != {ROM_SIZE}")
    got = sha1_of_bytes(data)
    if got != ORIG_SHA1:
        raise SystemExit(f"지문 불일치: {ORIG_ROM.name}\n  기대 {ORIG_SHA1}\n  실제 {got}")
    _rom_cache = data
    return data


def header_checksum(data: bytes) -> int:
    n = (len(data) - 0x200) // 2
    return sum(struct.unpack(f">{n}H", data[0x200 : 0x200 + n * 2])) & 0xFFFF


def verify_header(data: bytes) -> None:
    if data[0x100:0x110] != b"SEGA MEGA DRIVE ":
        raise SystemExit("헤더 없음 — plain BIN 이 아니다(인터리브 SMD?)")
    if data[0x180:0x18E] != HDR_SERIAL:
        raise SystemExit(f"시리얼 불일치: {data[0x180:0x18E]!r}")
    hdr = struct.unpack(">H", data[0x18E:0x190])[0]
    calc = header_checksum(data)
    if hdr != HDR_CHECKSUM or calc != hdr:
        raise SystemExit(f"체크섬 불일치: 헤더 {hdr:04x} 계산 {calc:04x}")
    a, b = FREE_TAIL
    if data[a:b] != b"\xff" * (b - a):
        raise SystemExit("꼬리 빈 공간이 FF 가 아니다")


if __name__ == "__main__":
    data = rom()
    verify_header(data)
    print(f"{GAME}: {ORIG_ROM.name} sha1={ORIG_SHA1} size={ROM_SIZE}")
    print(
        f"  serial {HDR_SERIAL.decode()} checksum {HDR_CHECKSUM:04x} 확인 · 꼬리 빈 공간 {FREE_TAIL[1] - FREE_TAIL[0]}B"
    )
