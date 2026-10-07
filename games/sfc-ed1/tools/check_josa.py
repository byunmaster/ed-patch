#!/usr/bin/env python3
"""조사 일치 상주 검사 — 우리 문안 전량에서 받침과 안 맞는 조사를 잡는다(PS1 `check_josa_agreement` 에 해당).

두 축, 둘 다 **0건 유지**가 목표다.

① 받침 불일치 — 사전 토큰을 한국어로 푼 뒤 `…를/을` 이 앞 음절 받침과 안 맞는 자리.
   ⚠ 을/를 한 축만 본다: 은/는·이/가·과/와 는 관형사형 어미(`먹는`)·단일 형태소(`사과`)와 어휘만으로
   못 갈라 오탐이 쏟아진다(PS1 실측 645건 전부 오탐). 을/를 은 관형사형이 늘 받침 뒤라 규칙과 안 부딪힌다.
② 변수 뒤 고정 조사 — 런타임 치환(`{D6}` 같은 한 바이트 토큰, 받침을 빌드 때 모른다) 바로 뒤에
   `은/는/이/가/을/를/과/와/으로` 가 한 꼴로 박힌 자리. 받침마다 다르니 `{은/는}` 자리표시자로 써야 훅이 푼다.

  python3 tools/check_josa.py        # 어긋나면 종료코드 1
  python3 tools/check_josa.py -v     # 자리마다 문맥
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import names_corpus  # noqa: E402
from shared.text import josa as josa_mod  # noqa: E402

# 을/를 을 품은 단일 형태소 — 조사가 아니라 낱말의 일부
STOP = ("마을", "가을", "겨을", "서울", "나을", "이을", "그을", "졸을", "잘을")
RX_EULREUL = re.compile(r"([가-힣])(을|를)(?=[\s,.!?」』…”\"'()~～]|<|\{|$)")
RX_RUNTIME = re.compile(r"\{[0-9A-F]{2}\}(은|는|이|가|을|를|과|와|으로)(?![가-힣])")


def scan(kr: str) -> list[tuple[str, str]]:
    out = []
    for m in RX_EULREUL.finditer(kr):
        prev, j = m.group(1), m.group(2)
        if kr[m.start() : m.end()] in STOP:
            continue
        want = "을" if josa_mod.batchim(prev) else "를"
        if j != want:
            out.append(("①", kr[max(0, m.start() - 6) : m.end() + 4]))
    for m in RX_RUNTIME.finditer(kr):
        out.append(("②", kr[max(0, m.start() - 6) : m.end() + 4]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()
    n = bad = 0
    for where, _jp, kr, _kind in names_corpus.pairs():
        if not kr:
            continue
        n += 1
        for axis, ctx in scan(kr):
            bad += 1
            print(f"  {axis} {where}: {ctx!r}")
    print(f"조사 일치: 문안 {n:,}자리 · 위반 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
