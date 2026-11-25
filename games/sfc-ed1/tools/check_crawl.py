"""오프닝·엔딩 크롤 회귀 검사 — 크롤은 다른 엔진이라 조판기도 하네스도 안 본다(마스터 10-28 「크롤이 깨진다」).

  ① 줄 폭 — 크롤 조각의 손으로 맞춘 줄은 화면(256px) 왼쪽 여백 32px 를 뺀 224px 안이어야 한다(넘으면 화면 오른쪽 밖으로 나가 왼쪽 끝으로 말려 든다).
  ② 흘러내림 — 크롤 엔진은 `$E0` 다음 바이트를 **그대로 이어 읽는다**(`$F9` 절대 호출·`$FE` 를 모른다). 구운 롬에서 이웃 크롤 조각 시작 바로 앞 바이트가 `$E0` 이 아니면
     (= `jump_after` 가 `F9 목표 · FE` 를 심었으면) 크롤이 그 주소 바이트를 글자로 찍는다(10-20 부터 있던 결함, 줄머리에 「셀▮.」).
  ③ 미배정 글리프 — 글자마다 인코더가 코드를 주는가(`encode.KR_TABLE` 또는 동적 글리프). 못 주면 인코더가 이미 실패하므로 여기선 안 센다.

    python3 tools/check_crawl.py     # 실패면 종료 코드 1
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import msg_addr
import typeset

SCREEN_PX = 256
LEFT_MARGIN = 32
LIMIT = SCREEN_PX - LEFT_MARGIN


def main() -> int:
    typeset.VWF = True
    seg = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    lo, hi = typeset.CRAWL
    units = sorted((int(v["addr"], 16), v["kr"]) for v in seg.values() if lo <= int(v["addr"], 16) <= hi)
    bad = []
    for a, kr in units:
        for ln in re.sub(r"<[^>]*>|\{[^}]*\}", "", kr).split("\n"):
            w = sum(typeset.pxw(c) for c in ln)
            if w > LIMIT:
                bad.append(f"줄 폭 {w}px > {LIMIT}px — {a:06X} 「{ln[:20]}…」")
    d = common.BUILD_DIR / common.BUILD_TAG
    rom_p = next(iter(sorted(d.glob("*(KR).sfc"))), None)
    if rom_p is None:
        print("⚠ 구운 제품 롬이 없어 ② 는 안 쟀다")
    else:
        rom = rom_p.read_bytes()
        for (a0, _), (a1, _) in zip(units, units[1:]):
            n1 = common.snes2off(msg_addr.kr_snes_addr(a1, debug=False))
            if rom[n1 - 1] != 0xE0:
                bad.append(f"흘러내림 끊김 — {a0:06X} 다음 {a1:06X} 앞 바이트 {rom[n1 - 1]:02X}(≠E0, 점프 조각이 낀다)")
    for b in bad:
        print("🔴", b)
    print(f"{'🔴' if bad else '✅'} 크롤 {len(units)}조각 · 줄 폭 ≤ {LIMIT}px · 흘러내림 이음")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
