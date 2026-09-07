#!/usr/bin/env python3
"""아직 안 옮긴 문안이 **화면에서 깨지는지** 센다.

🔴 이 게임의 한글은 원본 한자 구를 **빼앗아** 앉는다(JIS ku 0x40~0x58).
   그래서 안 옮긴 문안은 「일본어로 남는」 게 아니라 **그 구에 든 한자가 엉뚱한 한글로
   바뀌어** 나온다. 실측(2026-09-06): 세이브 슬롯 이름이 `L 1 ▨▨▨` 로 떴다 —
   원판으로 만든 세이브의 `第１章…` 이 우리 표를 타고 깨진 것이다.

   ⇒ 「화면에 일본어가 남았나」가 아니라 **「화면에 깨진 글자가 남았나」**가 축이다.
   흔한 한자의 절반쯤이 이 구에 있다(`了 第 旅 立 物 戦 闘 魔 法 道 力` …).

## 게이트가 아니라 계측이다

전량을 옮기기 전에는 0 이 될 수 없으므로 **실패로 치지 않는다**(루트 CLAUDE.md
「늘 빨간불이면 아무도 안 본다」). 대신 수를 찍어 상태 문서와 대조한다.
`--max N` 을 주면 그 수를 넘을 때 실패한다 — 회귀를 막고 싶을 때 쓴다.

## 못 보는 범위

🔴 **이 축은 「화면에 무엇이 나오나」지 「게임이 도나」가 아니다.** 2026-09-07 프리즈가
   그 자리다 — 전투 청크에 심은 `0F` 점프로 게임이 멈췄는데, 이 검사기도 되읽기도
   **둘 다 초록이었다.** 되읽기는 「디스크에 쓴 게 정본과 같나」를 보지 **「그 바이트를
   해석기가 어떻게 읽나」를 못 본다.** 그 축은 `patch_scn.plan()` 의 사전조건
   (전투 청크에 `0F` 금지)과 **인게임 한 판**이 본다.

- **원판으로 만든 세이브**는 우리가 못 고친다(슬롯 이름이 깨진다). 배포 안내 몫이다.
- **그림에 구워진 글자**(타이틀 로고 등)는 바이트가 아니라 그림이라 여기 안 잡힌다.
- 런 안으로 점프가 들어와 「밖으로」 뺀 자리의 **꼬리**는 원본이 남는다 —
  블록 단위로 세므로 그 자리는 「옮겼다」로 계산된다(과소평가).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import patch_font_hook
import patch_sys
import translate

LO, HI = patch_font_hook.KU_LO, patch_font_hook.KU_HI


def ku_of(b0: int, b1: int) -> int:
    """SJIS 2바이트 → JIS 상위(구)."""
    c = b0 - (0x81 if b0 <= 0x9F else 0xC1)
    return c * 2 + (1 if b1 < 0x9F else 2) + 0x20


def hijacked(text: str) -> list[str]:
    """뺏은 구에 든 글자만 골라 낸다."""
    out = []
    for ch in text:
        try:
            b = ch.encode("shift_jis")
        except UnicodeEncodeError:
            continue
        if len(b) == 2 and LO <= ku_of(b[0], b[1]) <= HI:
            out.append(ch)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, help="이 수를 넘으면 실패한다(회귀 방지)")
    ap.add_argument("--list", type=int, default=0, help="깨지는 블록을 N개 보여준다")
    a = ap.parse_args()

    canon = translate.load_script()
    sys_canon = patch_sys.load()

    bad_blocks = 0
    bad_chars = 0
    seen = set()
    samples = []
    for k, b in translate.keyed(translate.blocks()):
        if k in canon or k in seen or not translate.looks_text(b["t"]):
            continue
        seen.add(k)
        hits = hijacked(b["t"])
        if hits:
            bad_blocks += 1
            bad_chars += len(hits)
            if len(samples) < a.list:
                samples.append((k, "".join(dict.fromkeys(hits))[:12], b["t"][:44]))

    sys_bad = sys_chars = 0
    for disk in patch_sys.DISKS:
        for o, v in patch_sys.sites(disk).items():
            if f"{disk}:{o:#x}" in sys_canon:
                continue
            hits = hijacked(v.get("t", ""))
            if hits:
                sys_bad += 1
                sys_chars += len(hits)

    print(f"뺏은 구 {LO:#04x}~{HI:#04x} — **안 옮기면 화면에서 깨지는** 자리")
    print(f"  시나리오·전투 블록 {bad_blocks:,} · 글자 {bad_chars:,}")
    print(f"  시스템 자리      {sys_bad:,} · 글자 {sys_chars:,}")
    for k, chars, t in samples:
        print(f"    [{k[:8]}] {chars} ← {t!r}")
    total = bad_blocks + sys_bad
    if a.max is not None and total > a.max:
        print(f"🔴 {total} > --max {a.max} — 늘었다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
