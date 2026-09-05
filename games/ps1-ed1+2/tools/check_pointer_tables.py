#!/usr/bin/env python3
"""**포인터 표에 문안을 넣지 않았는가** — 넣으면 표가 통째로 지워진다.

**왜.** `ED2SCN2:300` 은 **327바이트짜리 포인터 표**(4바이트 워드 81개 중 80개가
`0x8017xxxx` RAM 주소)인데, 어느 배치가 여기에 워프 목록 문안을 채워 넣었다. 재삽입기는
그걸 정상 블록으로 보고 **264바이트 한글을 덮어썼다.** 화면에 나가는 워프 목록은 사실
`patch_ed2_sys` 의 EXE 표에서 오므로, 이 블록은 애초에 번역 대상이 아니었다.

🔴 **어느 게이트도 이걸 못 봤다.** 무변경 구간(`build.IMMUTABLE`)은 **선언한 자리만** 보고,
구조 계약(`%c`·`%s` 개수)은 원본에 제어부호가 없으니 지킬 게 없으며, 재삽입 예행은
「탈락 0」으로 초록이었다. 증상은 오타가 아니라 **엉뚱한 곳으로 점프**다.

⚠ 이건 `check_jp_leak.untranslated()` 의 **거울상**이다 — 저쪽은 「문안이 없어서 원문이
나간다」, 이쪽은 「문안이 있어서 표가 깨진다」. 둘 다 「원문에 텍스트가 있는가」를 안 물어서
생긴 구멍이라 같은 날 같이 막았다(2026-08-20).

판정은 **바이트로** 한다(디코드 결과로 하면 안 된다 — 포인터 바이트가 한자로 디코드돼
「일본어가 있다」로 읽힌다. 실제로 첫 스캔이 그렇게 이 블록을 놓쳤다):

- 정렬 0~3 중 가장 잘 맞는 자리에서 4바이트 워드를 읽어
- **절반 이상이 PS1 RAM 대역(`0x80010000`~`0x801FFFFF`)** 이고
- 🔴 **꼬리에 텍스트가 없어야** 한다

⚠ 마지막 조건이 핵심이다. **표 접두 + 대사 꼬리**(anchor_tail)는 아주 흔하고
재삽입기가 꼬리만 다시 쓰므로 **정상**이다 — 비율만 보면 그것들까지 66건이 걸린다(실측).
표만 있고 꼬리가 빈 블록은 194개이고, 그중 문안이 있던 건 `ED2SCN2:300` 하나였다.

  python3 tools/check_pointer_tables.py       # 전 씬
  python3 tools/check_pointer_tables.py -v    # 표로 판정한 블록 전량
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAM_LO, RAM_HI = 0x80010000, 0x80200000
MIN_BYTES = 24  # 이보다 짧으면 우연히 맞을 수 있다
RATIO = 0.5


def pointer_ratio(raw):
    """정렬 0~3 중 **가장 잘 맞는 자리**의 RAM 포인터 비율. 표가 워드 경계에서 시작하지 않는다."""
    best = 0.0
    for off in range(4):
        words = [int.from_bytes(raw[i : i + 4], "little") for i in range(off, len(raw) - 3, 4)]
        if not words:
            continue
        hit = sum(1 for w in words if RAM_LO <= w < RAM_HI)
        best = max(best, hit / len(words))
    return best


def tail_text(text):
    """포인터 표 접두를 지난 **실제 텍스트**. 비어 있으면 순수 표다."""
    i = text.rfind("\\x80")
    return (text[i + 4 :] if i >= 0 else text).strip()


def scan(verbose=False):
    bad, tables = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "work", "derived", "scn_jp", "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        try:
            with open(os.path.join(ROOT, "script", f"{scn}.json"), encoding="utf-8") as f:
                kr = json.load(f)
        except FileNotFoundError:
            continue
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["entries"]
        for e in entries:
            raw_hex = e.get("raw_hex")
            if not raw_hex:
                continue
            raw = bytes.fromhex(raw_hex)
            if len(raw) < MIN_BYTES:
                continue
            r = pointer_ratio(raw)
            if r < RATIO:
                continue
            if tail_text(e.get("text") or ""):
                continue  # 표 접두 + 대사 꼬리 — 재삽입기가 꼬리만 다시 쓴다(정상)
            tables += 1
            v = kr.get(str(e["entry_id"]))
            t = (v or {}).get("t") if isinstance(v, dict) else None
            if t and t.strip():
                bad.append((scn, e["entry_id"], len(raw), r, " ".join(t.split())[:48]))
            elif verbose:
                print(f"    ✅ {scn} jp{e['entry_id']}  {len(raw)}B · 포인터 {r:.0%} · 문안 없음")
    for scn, eid, n, r, t in bad:
        print(f"    ❌ {scn} jp{eid}  {n}B 중 포인터 {r:.0%} 인데 문안이 있다  {t!r}")
    print(
        f"  {'✅' if not bad else '❌'} 포인터 표에 문안 없음: 표 {tables} · 덮어쓴 곳 {len(bad)}"
        + ("" if not bad else "  ← 재삽입이 표를 지운다(엉뚱한 곳으로 점프)")
    )
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
