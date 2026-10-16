"""시험 빌드 전용 디버그 스위치 — 새 게임 시작 맵·챕터 지정(맵 구경 모드). `ED_DEBUG=1` + 꼬리표 `test-*` 에서만 `build.py` 가 부른다.

🔴 **제품·일반 시험 빌드에는 들어가지 않는다.** 스위치 없이 구운 이미지의 sha1 이 이 모듈이 생기기 전과 같아야 한다(`status.md` 「디버그 빌드」).

원판 새 게임은 `ED3.EXE 0x8008636C~` 에서 맵 이름 리터럴 `FT0000`(`0x800B49EC`)을 찾아(`0x80012B70`) 챕터 폴더(`0x801D6468`, 직전에 0 으로 쓴다)의
팩에서 읽는다. 여기서 두 곳을 바꾼다:
  ① 이름 리터럴 6자 → `ED_DEBUG_MAP`(맵 표 `0x800A9C8C` 443항목 안의 이름이어야 한다)
  ② 챕터 0 쓰기(`0x8008639C sh zero,0x6468(at)`)를 `sh v0,…` 로 바꾸고, 그 앞 지연 슬롯 `nop`(`0x80086394`)에 `addiu v0,zero,<챕터>` 를 둔다
     (분기 `bne v0,v1` 은 이미 비교를 마친 뒤라 v0 를 덮어도 안전하고, 이어하기 갈래는 v0 를 바로 다시 쓴다).
⚠ 플레이어·파티는 안 나온다 — 맵 이벤트가 스폰을 정하는데 새 게임 상태 블록이 비어 있어서다(status 「디버그·개발 기능 분석」). 맵 그림·지형·이벤트 없는 장면을 보는 **맵 구경 모드**다.
"""

import os
import re
import struct

import common
import engine_patch as E

NAME_ADDR = 0x800B49EC  # 새 게임 시작 맵 이름 리터럴 `FT0000\0\0`(8B)
DIR_NOP = 0x80086394  # `bne v0,v1` 의 지연 슬롯 nop
DIR_STORE = 0x8008639C  # `sh zero, 0x6468($at)` — 챕터 폴더를 0 으로
MAP_TABLE = 0x800A9C8C  # 10B 항목(이름 6 · 팩 번호 · 영역 번호 · 값), 끝은 `ZZZZZZ`
NAME_ORIG = b"FT0000\x00\x00"
NOP = 0x00000000
SH_ZERO = 0xA4206468  # sh zero, 0x6468(at)


def map_names(exe):
    """맵 표의 이름 목록 — 원본 실행파일에서 읽는다."""
    names = []
    o = E._off(MAP_TABLE)
    while exe[o] != 0x5A:
        names.append(bytes(exe[o : o + 6]).decode("ascii"))
        o += 10
    return names


def chapter_of(disc, name):
    """맵 이름을 가진 장면 팩의 챕터 폴더(`SCE<n>`) — 팩 하나에만 있으면 그것, 여럿이면 `ED_DEBUG_DIR` 로 정한다."""
    found = set()
    for path, (lba, size) in common.iso_files(disc).items():
        m = re.fullmatch(r"/SCE(\d)/SC\d\d\d\.DAT", path)
        if not m:
            continue
        mem = common.arc_members(common.read_lba(disc, lba, size))
        if any(n == f"..\\DATA\\{name}.BIN" for n in mem):
            found.add(int(m.group(1)))
    forced = os.environ.get("ED_DEBUG_DIR")
    if forced is not None:
        return int(forced)
    if len(found) != 1:
        raise SystemExit(f"🔴 ED_DEBUG_MAP={name}: 챕터 폴더를 못 정했다({sorted(found) or '어느 팩에도 없다'}) — ED_DEBUG_DIR=<0~8> 로 준다")
    return found.pop()


def apply(exe, disc, name):
    """exe(bytearray) 를 제자리에서 고친다. 반환 = (이름, 챕터) 설명."""
    assert disc == "ed3", "디버그 스위치는 ED3 만 있다"
    if not re.fullmatch(r"[A-Za-z0-9]{6}", name or ""):
        raise SystemExit("🔴 ED_DEBUG_MAP=<맵 이름 6자> 가 필요하다 — 예: ED_DEBUG_MAP=FT1000 (목록은 status 「디버그 빌드」 · 맵 표 443항목)")
    if name not in map_names(exe):
        raise SystemExit(f"🔴 ED_DEBUG_MAP={name}: 맵 표(0x800A9C8C)에 없는 이름이다")
    d = chapter_of(disc, name)
    E._expect(exe, NAME_ADDR, struct.unpack("<2I", NAME_ORIG), "새 게임 시작 맵 이름")
    E._expect(exe, DIR_NOP, (NOP,), "챕터 쓰기 앞 지연 슬롯")
    E._expect(exe, DIR_STORE, (SH_ZERO,), "챕터 0 쓰기")
    new_name = name.encode("ascii") + b"\x00\x00"
    exe[E._off(NAME_ADDR) : E._off(NAME_ADDR) + 8] = new_name
    struct.pack_into("<I", exe, E._off(DIR_NOP), 0x24020000 | d)  # addiu v0, zero, d
    struct.pack_into("<I", exe, E._off(DIR_STORE), 0xA4226468)  # sh v0, 0x6468(at)
    words = [0x24020000 | d, 0xA4226468]
    E.verify([0x3C01801D] + words[1:], DIR_STORE - 4)  # 디코드·지연 슬롯 검산(앞 lui at 포함)
    return f"맵 {name} · 챕터 폴더 SCE{d}"
