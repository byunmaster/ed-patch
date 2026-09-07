"""워크 RAM($2000~$3FFF) 사용 지도 — 후킹 루틴·글리프를 둘 빈 자리를 찾는다.

런타임 덤프(emucap `dump_memory` 의 ram.bin) 여러 장을 겹쳐 **어느 상태에서도 0 인** 구간을 낸다.
⚠ 「0 이면 빈 자리」는 계약이 아니다(체크리스트) — 후보는 **쓰기 BP 로 인게임 확인**한다(status.md 9절).
정적 스캔(모듈 코드의 절대주소 참조)은 해 봤지만 데이터·압축 영역의 쓰레기 참조에 묻혀 못 쓴다
(devlog 2026-09-05 (4)).
"""

import sys
from pathlib import Path


def main():
    dumps = [Path(p) for p in sys.argv[1:]]
    if not dumps:
        raise SystemExit("쓰기: ram_map.py <dump_dir>...   (emucap dump_memory 결과 폴더)")
    live = [0] * 0x2000
    for d in dumps:
        b = (d / "ram.bin").read_bytes()
        for i, v in enumerate(b):
            if v:
                live[i] += 1
    print(f"덤프 {len(dumps)}장 — 페이지별 비0 바이트 수")
    for pg in range(32):
        n = sum(1 for v in live[pg * 256 : (pg + 1) * 256] if v)
        print(f"${0x2000 + pg * 256:04X}  {n:4}{'  ← 후보' if n == 0 else ''}")
    runs, cur = [], None
    for i in range(0x2000):
        if live[i] == 0 and cur is None:
            cur = i
        if live[i] and cur is not None:
            runs.append((cur, i))
            cur = None
    if cur is not None:
        runs.append((cur, 0x2000))
    runs = [r for r in runs if r[1] - r[0] >= 64]
    print(
        "모든 덤프에서 0 인 64B+ 구간:",
        [f"${0x2000 + a:04X}-${0x2000 + b - 1:04X} ({b - a}B)" for a, b in runs],
    )


if __name__ == "__main__":
    main()
