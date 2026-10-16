"""md-ed2 공용 — 원본 지문 · 롬 헤더 · 경로 상수. md-ed1 의 common.py 와 같은 꼴.

⚠ **읽기 전용이다.** 쓰기 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다.

🔴 **소장본은 `.zip` 안의 plain BIN 이다**(ED1 은 압축 없는 `.bin`). 0x100 에 `SEGA MEGA DRIVE` 가
그대로 있고 SMD 인터리브가 아니다. 좌표는 전부 **롬 파일 오프셋 = 68000 주소**(매퍼 없음, 2MB).
"""

import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from build_tag import build_tag

GAME = "md-ed2"
ROOT = Path(__file__).resolve().parents[3]
GAME_DIR = ROOT / "games" / GAME
ORIG_DIR = ROOT / "originals" / "jp" / GAME

WORK = GAME_DIR / "work"
OUT_DIR = WORK / "derived"
REVIEW_DIR = WORK / "review"
BUILD_TAG = build_tag()
BUILD_DIR = WORK / "build"
DIST_DIR = WORK / "dist"
EMU_DIR = WORK / "emu"

ORIG_ZIP = ORIG_DIR / "SMD - Dragon Slayer - Eiyuu Densetsu 2 (J).zip"
ORIG_MEMBER = "Dragon Slayer - Eiyuu Densetsu 2 (J).BIN"
ORIG_SHA1 = "79b6201301acb5d9e9c56dcf65a9bcf9d9a931ab"
ROM_SIZE = 2_097_152

# 헤더 실측 (0x100~). 체크섬은 0x200~ 의 16비트 BE 합 & 0xFFFF — 롬을 고치면 다시 맞춰야 한다.
HDR_SERIAL = b"GM G-5544   00"
HDR_CHECKSUM = 0x368F
SRAM_RANGE = (0x200001, 0x203FFF)  # 2MB 바로 뒤라 4MB 확장은 불가(ED1 과 같다)
# ED1 과 달리 꼬리 빈 공간이 거의 없다 — 아카이브 끝 0x1FF71E 뒤 FF 2,272B(마지막 2B 제외)
FREE_TAIL = (0x1FF720, 0x1FFFFE)


def sha1_of_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


_rom_cache: bytes | None = None


def rom() -> bytes:
    """원본 롬 바이트(zip 에서 읽는다). 지문이 어긋나면 죽는다 — 패치된 사본을 원본으로 오해하지 않기 위해."""
    global _rom_cache
    if _rom_cache is not None:
        return _rom_cache
    if not ORIG_ZIP.exists():
        raise SystemExit(f"원본 없음: {ORIG_ZIP}")
    with zipfile.ZipFile(io.BytesIO(ORIG_ZIP.read_bytes())) as z:
        data = z.read(ORIG_MEMBER)
    if len(data) != ROM_SIZE:
        raise SystemExit(f"크기 불일치: {len(data)} != {ROM_SIZE}")
    got = sha1_of_bytes(data)
    if got != ORIG_SHA1:
        raise SystemExit(f"지문 불일치: {ORIG_ZIP.name}\n  기대 {ORIG_SHA1}\n  실제 {got}")
    _rom_cache = data
    return data


def header_checksum(data: bytes) -> int:
    n = (len(data) - 0x200) // 2
    return sum(struct.unpack(f">{n}H", data[0x200 : 0x200 + n * 2])) & 0xFFFF


def check() -> None:
    d = rom()
    assert d[0x100:0x110] == b"SEGA MEGA DRIVE ", "헤더 시그니처"
    assert d[0x180:0x18E] == HDR_SERIAL, f"시리얼 {d[0x180:0x18E]!r}"
    cs = struct.unpack(">H", d[0x18E:0x190])[0]
    assert cs == HDR_CHECKSUM == header_checksum(d), (
        f"체크섬 헤더 {cs:#x} 실계산 {header_checksum(d):#x}"
    )
    tail = d[FREE_TAIL[0] : FREE_TAIL[1]]
    assert tail == b"\xff" * len(tail), "꼬리 빈 공간이 비어 있지 않다"
    print(f"  원본 OK — sha1 {ORIG_SHA1[:8]}… · 체크섬 {cs:#06x} · 꼬리 빈 공간 {len(tail):,}B")


if __name__ == "__main__":
    check()
