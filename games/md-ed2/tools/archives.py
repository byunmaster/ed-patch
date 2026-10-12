"""md-ed2 아카이브 — 색인(BE32 오프셋 × n, 첫 값 = 4n) + LZ 블록들. ED1 과 같은 코덱·같은 색인 꼴.

    python3 tools/archives.py --check   # 아카이브 분모 + 대본 블록의 씬 분할(4분할 표) 확인

🔴 **ED1 과 다른 점 — 대본 블록 하나가 씬 모듈 넷이다.** 블록(LZ 출력) 안에 모듈 넷이 이어 붙어 있고
(`SCENE_SIZES` 0x19DC3C: 블록마다 BE16 × 4 = 모듈 크기, 합 = 블록 길이), 씬 로더(`0x1A41C`~)가
씬 번호 → 블록 = id>>2(모드 1 이면 >>3 …) 를 풀어 **필요한 모듈만 FF6650 으로 옮긴다**
(`0x1A490~`). 그래서 대본의 단위는 「블록」이 아니라 **모듈 356개**다. 엔진 코드는 ED1 과 같은 것이
다른 주소에 있다(LZ 디컴프레서 0xE04 = ED1 0xC9E, 렌더러 0xB738 = 0x978C, ARGS 표 0xBF9A = 0x9FE2).
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lz

# 이름 → (색인 주소, 기대 블록 수, 기대 총 출력 바이트). 실측 2026-10-12.
# ⚠ 이름은 ED1 과의 대응을 추정한 것이다(대본·전투는 화자 태그/SJIS 로 확정, 나머지는 미확정).
ARCHIVES = {
    "gfx_a": (0x88F4E, 21, 430_080),
    "gfx_b": (0xE1B2C, 6, 61_568),
    "gfx_c": (0x10D0A0, 7, 133_792),
    "gfx_d": (0x116184, 5, 69_056),
    "misc": (0x11CD62, 103, 936_448),  # SJIS 5,696자 · 화자 0 — 대본이 아니다(맵/그래픽 추정)
    "battle": (0x18BF76, 99, 139_282),  # 화자 9 · SJIS 5,910자 (전투 메시지·몬스터 이름 추정)
    "script": (
        0x19DF08,
        90,
        1_051_602,
    ),  # 화자 2,028 — 대본 본진. 블록 89 는 스트림이 아닌 꼬리(164B)
}
# 색인 0xD1598(53항목)은 체인 0xD166C~0xE130C(52블록)을 가리키는데 첫 항목이 체인 밖이라 blocks() 가
# 못 푼다 — 그래픽 계열이라 후순위(status.md).

SCENE_SIZES = 0x19DC3C  # 블록 × (BE16 × 4) — 모듈 크기
SCENE_BLOCKS = 89  # 블록 89 는 표 밖(꼬리 164B)

SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){4,}")
SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){1,8})\x04")


def table(d: bytes, base: int) -> list[int]:
    """색인 → 블록 시작 주소 목록. 첫 값이 4n 이 아니면 색인이 아니다."""
    first = struct.unpack(">I", d[base : base + 4])[0]
    if first < 4 or first % 4 or first > 4 * 4096:
        raise ValueError(f"{base:#x}: 색인이 아니다 (첫 값 {first:#x})")
    n = first // 4
    offs = struct.unpack(f">{n}I", d[base : base + 4 * n])
    return [base + o for o in offs]


def blocks(d: bytes, base: int) -> list[tuple[int, bytes, int]]:
    """(시작, 출력, 끝) — 끝은 헤더 길이로 잰 다음 블록 자리. 디코더가 헤더와 어긋나면 죽는다."""
    out = []
    for s in table(d, base):
        data, end = lz.decode(d, s)
        span = lz.block_span(d, s)
        if end not in (s + span, s + span - 1):
            raise SystemExit(f"{s:#x}: 디코더 끝({end:#x}) ≠ 헤더 길이({s + span:#x})")
        out.append((s, data, s + span))
    return out


def scene_sizes(d: bytes, i: int) -> tuple[int, int, int, int]:
    return struct.unpack(">4H", d[SCENE_SIZES + 8 * i : SCENE_SIZES + 8 * i + 8])


def modules(d: bytes) -> list[tuple[int, int, bytes]]:
    """대본 씬 모듈 목록 — (블록, 블록 안 순번, 바이트). 합이 블록 길이와 다르면 죽는다."""
    out = []
    for i, (_, b, _) in enumerate(blocks(d, ARCHIVES["script"][0])[:SCENE_BLOCKS]):
        sz = scene_sizes(d, i)
        if sum(sz) != len(b):
            raise SystemExit(f"대본 블록 {i}: 분할 표 합 {sum(sz)} ≠ 블록 길이 {len(b)}")
        o = 0
        for k, s in enumerate(sz):
            out.append((i, k, b[o : o + s]))
            o += s
    return out


def check(d: bytes) -> None:
    for name, (base, n_exp, tot_exp) in ARCHIVES.items():
        bl = blocks(d, base)
        tot = sum(len(b) for _, b, _ in bl)
        chars = sum(len(m.group()) // 2 for _, b, _ in bl for m in SJIS_RUN.finditer(b))
        spk = sum(len(SPEAKER.findall(b)) for _, b, _ in bl)
        print(
            f"  {name:7s} {base:#08x}: 블록 {len(bl):3d} · {bl[0][0]:#x}~{bl[-1][2]:#x} · "
            f"출력 {tot:,}B · SJIS 런 {chars:,}자 · 화자 {spk}"
        )
        if len(bl) != n_exp or tot != tot_exp:
            raise SystemExit(f"{name}: 분모가 갈렸다 (기대 {n_exp}블록 {tot_exp}B)")
    mods = modules(d)
    print(
        f"  대본 씬 모듈 {len(mods)} (블록 {SCENE_BLOCKS} × 4) · 최대 {max(len(m) for _, _, m in mods):,}B"
    )
    # 인코더 회귀 — 실물 블록을 다시 눌러 풀면 같아야 하고, 원본 이하여야 한다(꼬리 빈 공간이 2KB 뿐이라
    # 인코더가 원본보다 약하면 무변경 재압축만으로 넘친다 — 첫 조사 때 탐욕 인코더가 +8.7KB 였다)
    s0, b0, _ = blocks(d, ARCHIVES["script"][0])[35]
    packed = lz.encode(b0)
    if lz.decode(packed, 0)[0] != b0:
        raise SystemExit("인코더 왕복 실패 (script 35)")
    span = lz.block_span(d, s0)
    print(f"  인코더 왕복 OK — script 35: 원본 {span:,}B ↔ 재압축 {len(packed):,}B")
    if len(packed) > span:
        raise SystemExit("인코더가 원본 압축보다 약하다 (script 35)")


if __name__ == "__main__":
    check(common.rom())
