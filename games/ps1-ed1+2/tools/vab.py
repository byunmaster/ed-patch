#!/usr/bin/env python3
"""ED.EXE 안의 **VAB 사운드 뱅크** 구조 인식 — 「여기는 빈 공간이 아니다」를 코드로 안다.

**왜.** 자유 공간 판정을 **정적 3중 검증**(①파일이 0 ②참조 0건 ③런타임 덤프도 0)으로 했는데
전부 통과한 자리가 **VAB 뱅크 내부**였다(2026-07-29, 효과음 파괴). 뱅크는 CPU 가 주소로 읽는
게 아니라 **통째로 SPU RAM 에 전송**되므로 lui 참조가 0건이고, 게임이 거기 쓰지 않으니 런타임
덤프도 계속 0이다 — 기존 검증은 *"게임이 여기 쓰는가"* 만 봤고 *"게임이 여기를 읽어 가는가"* 는
못 봤다.

그래서 배치 기준이 바뀌었다: **자료구조 매직을 스캔해 알려진 블롭 내부가 아님을 먼저 확인.**
⚠ 그런데 그 규칙이 **주석에만** 있었다. 안전 한계(`JOSA_SAFE`·`DATA_SAFE`)는 손으로 한 번
계산해 박은 매직 넘버였고, 재검증 절차도 산문이었다. 여기서 **실행 가능하게** 만든다.

VAB(VH) 헤더 배치 — 파형(ADPCM)은 헤더 뒤에서 시작한다:

    0  "pBAV"   4  version   8  vab id   12 fsize
    18 ps(프로그램 수, u16)   20 ts(톤)   22 vs(VAG)
    32 프로그램 속성 128×16 = 2048
    +  톤 속성 512×ps
    +  VAG 오프셋 표 512
    →  파형 시작

⚠ **헤더의 0 패딩까지는 덮어도 소리에 영향이 없다** — 실제로 깨진 건 파형의 첫 ADPCM 블록을
덮었을 때다(첫 16B 가 무음이라 0런에 삼켜졌다). 그래서 한계는 **런 크기가 아니라 파형 시작**이다.
"""

import struct

MAGIC = b"pBAV"
HDR_FIXED = 32 + 128 * 16  # 헤더 + 프로그램 속성표
TONE_ATTR = 512  # 프로그램당 톤 속성
VAG_TABLE = 512  # VAG 오프셋 표


def banks(ed):
    """[(뱅크 오프셋, fsize, 프로그램 수, 파형 시작 오프셋)] — 파일 순서."""
    out, off = [], 0
    while (i := ed.find(MAGIC, off)) >= 0:
        fsize = struct.unpack_from("<I", ed, i + 12)[0]
        nprog = struct.unpack_from("<H", ed, i + 18)[0]
        out.append((i, fsize, nprog, i + HDR_FIXED + TONE_ATTR * nprog + VAG_TABLE))
        off = i + 4
    return out


def wave_start(ed, off):
    """`off` 가 속한 뱅크의 **파형 시작** 오프셋(뱅크 밖이면 None).

    반환값이 곧 「여기까지는 덮어도 된다」의 상한이다.
    """
    cur = None
    for b_off, fsize, _nprog, wav in banks(ed):
        if b_off <= off < b_off + fsize:
            cur = wav
    return cur


def hits_wave(ed, lo, hi):
    """[lo, hi) 가 어느 뱅크의 **파형**을 침범하는가 — 침범하면 (뱅크, 파형시작)."""
    for b_off, fsize, _nprog, wav in banks(ed):
        if lo < b_off + fsize and hi > wav:
            return b_off, wav
    return None


def safe_len(ed, off):
    """`off` 부터 파형 직전까지 몇 바이트 쓸 수 있는가(뱅크 밖이면 None)."""
    wav = wave_start(ed, off)
    return None if wav is None else wav - off
