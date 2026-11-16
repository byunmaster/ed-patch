"""표 문자열의 제어 토큰(`FE xx`) 열 대조 — 원판과 구운 롬에서 같은 표 문자열의 토큰 열이 같은가.

    python3 tools/table_tokens.py [롬.bin]     # 빌드 게이트(check.sh 5e6) — 달라지면 실패

배경(11-07): 파티 이름 표 0번(아트라스)은 첫 `FE0C` 가 표 시작 앞에 따로 있는데 빌더가 템플릿대로 `FE0C` 를 한 번 더 써 시작 토큰이 둘이 됐다 —
화면은 멀쩡했지만(색 지정 중복) 빌더 결함이다. 같은 빌더를 쓰는 모든 표(`tables.records`)를 한 번에 대조한다.
토큰은 `FE` + 인자 1B 로 읽고, 한글·가나 글자(리드 0x81~0x9F·0xE0~0xFC)는 2B 로 건너뛴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import tables


def tokens(raw: bytes) -> list[int]:
    """`FE xx` 토큰의 인자 열."""
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if b == 0xFE and i + 1 < len(raw):
            out.append(raw[i + 1])
            i += 2
        elif 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            i += 2
        else:
            i += 1
    return out


def check(orig: bytes, kr: bytes) -> list[tuple[str, int, list[int], list[int]]]:
    bad = []
    for name, rs in tables.records(orig).items():
        for pos, raw in rs:
            a = tokens(raw)
            if not a:
                continue
            b = tokens(kr[pos : pos + len(raw)])
            if a != b:
                bad.append((name, pos, a, b))
    return bad


def selftest() -> bool:
    return (
        tokens(bytes.fromhex("fe0c8a4cfe10")) == [0x0C, 0x10]
        and tokens(bytes.fromhex("8afe20")) == []
    )


def main() -> int:
    if not selftest():
        print("❌ 표 토큰 대조 자체 시험 실패")
        return 1
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    )
    bad = check(common.rom(), path.read_bytes())
    n = sum(1 for rs in tables.records(common.rom()).values() for _, r in rs if tokens(r))
    print(
        f"표 토큰 대조 [md-ed2] — 토큰 든 표 문자열 {n} · 원판과 다른 것 {len(bad)} · 자체 시험 통과"
    )
    for name, pos, a, b in bad[:20]:
        print(f"  ✗ {name} {pos:#x} 원판 {[hex(x) for x in a]} → 롬 {[hex(x) for x in b]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
