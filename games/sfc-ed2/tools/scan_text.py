"""sfc-ed2 대본 후보 스캐너 — 롬에서 2바이트 코드(`$80~$85` + 색인) 덩이를 찾아 뱅크별 분포를 낸다(조사용).

코드 규칙(`$C0:9395` 출력 루틴을 읽어 얻었다, 2026-10-12):
  $00        종료
  $01~$1F    제어(일부는 `$18` 를 빼 색 번호로 쓴다 — `$18+`)
  $20~$7F    반각 1바이트(8×16 글꼴, `font.HALF_BASE`)
  $80~$87    전각 2바이트: 코드 = 상위<<8|하위, 글리프 색인 = 코드 − $8000
  $88~$DF    1바이트 문자(`$C0:90E8` 경로는 $80 미만만 — 이 구간은 미확정)
  $F0~$FF    제어
⚠ 이 스캐너는 **후보**를 찾을 뿐 포인터 표·구조는 모른다 — 대본 정본은 포인터 표 해독 뒤에 선다.

    python3 games/sfc-ed2/tools/scan_text.py
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

MAX_INDEX = 1516  # 글리프 색인 상한(실측: 비어 있지 않은 마지막 색인 1515)


def find_runs(d: bytes, min_chars: int = 8) -> list[tuple[int, int, int]]:
    n = len(d)

    def run(i: int) -> tuple[int, int]:
        j, chars = i, 0
        while j < n - 1:
            b = d[j]
            if 0x80 <= b <= 0x85 and (b - 0x80) * 256 + d[j + 1] < MAX_INDEX:
                chars += 1
                j += 2
            elif b <= 0x20 or 0xF0 <= b < 0xFF:
                j += 1
            else:
                break
        return j, chars

    i, runs = 0, []
    while i < n - 1:
        if 0x80 <= d[i] <= 0x85:
            j, c = run(i)
            if c >= min_chars:
                runs.append((i, j, c))
                i = j
                continue
        i += 1
    return runs


if __name__ == "__main__":
    common.verify_originals()
    runs = find_runs(common.rom_bytes())
    tot, cnt = collections.Counter(), collections.Counter()
    for a, _b, c in runs:
        tot[a >> 16] += c
        cnt[a >> 16] += 1
    print(f"덩이 {len(runs)}개 · 글자 {sum(tot.values()):,}")
    for k in sorted(tot):
        print(f"  ${0xC0 + k:02X}  덩이 {cnt[k]:4d}  글자 {tot[k]:6,}")
