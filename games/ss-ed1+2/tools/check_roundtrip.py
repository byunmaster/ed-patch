#!/usr/bin/env python3
"""**덤프 라운드트립** — 덤프에서 원본을 되짚으면 원본과 같은가.

    python3 tools/check_roundtrip.py

## 되읽기와 다른 것을 묻는다 (2026-09-06 점검에서 이 층이 없다는 게 드러났다)

    되읽기      내가 **쓴 것**이 이미지에 그대로 있나   → 쓰기가 빗나감·포인터 미갱신을 잡는다
    라운드트립  **덤프 → 재조립**이 원본과 같나        → **덤퍼가 잃는 것**을 잡는다

🔴 **둘째가 없으면 「덤퍼가 안 본 바이트」를 영영 못 본다.** 되읽기는 내가 쓴 자리만 보므로,
   덤퍼가 애초에 못 읽은 자리는 검사 대상에 들지도 않는다.

## 무엇을 대조하나 — 덤프의 두 층

덤프의 항목은 `raw_hex`(원본 바이트)와 `text`(디코드 결과)를 **둘 다** 들고 있다. 그래서
두 방향을 잰다:

1. **바이트 ↔ 원본** — `raw_hex` 가 `file_offset` 의 원본 바이트와 같은가.
   ⇒ 덤퍼가 **자리를 잘못 잡았나**를 잡는다.
2. **텍스트 ↔ 바이트** — `text` 를 우리 인코더로 되돌리면 `raw_hex` 가 되는가.
   ⇒ 덤퍼가 **디코드에서 잃은 것**을 잡는다(제어문자·이스케이프·인코딩).

⚠ 2번이 핵심이다 — 여기서 어긋나면 우리는 **원문을 잘못 읽은 채** 번역·조판·재삽입을
  하게 되고, 되읽기는 그걸 **전부 통과시킨다**(내가 쓴 대로 있으니까).
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common


def _reencode(text):
    """`text` → 바이트. 덤퍼의 디코드를 되돌린다(cp932 + 덤퍼가 편 이스케이프)."""
    try:
        return text.encode("cp932")
    except UnicodeEncodeError:
        return None


def check_one(path, entries, data):
    """`(자리 어긋남, 디코드 손실, 잰 항목)`."""
    off_bad, dec_bad, n = [], [], 0
    for e in entries:
        raw = e.get("raw_hex")
        if raw is None:
            continue
        raw = bytes.fromhex(raw)
        at = int(e["file_offset"], 16)
        n += 1
        if data[at : at + len(raw)] != raw:
            off_bad.append((at, e.get("text", "")[:20]))
            continue
        t = e.get("text")
        if t is None:
            continue
        back = _reencode(t)
        if back is not None and back != raw:
            dec_bad.append((at, t[:20], raw[:12].hex(), back[:12].hex()))
    return off_bad, dec_bad, n


def main():
    common.verify_source()
    _f, mm = common.open_image()
    try:
        files = {n: (l, s) for n, l, s in common.iso_files(mm)}
        tot = off_n = dec_n = 0
        shown = 0
        for p in sorted(glob.glob(os.path.join(common.OUT_DIR, "scn_jp", "*.json"))):
            name = os.path.basename(p).replace(".json", ".BIN")
            hit = next((k for k in files if os.path.basename(k) == name), None)
            if hit is None:
                continue
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            data = common.read_extent(mm, *files[hit])
            off_bad, dec_bad, n = check_one(hit, d["entries"], data)
            tot += n
            off_n += len(off_bad)
            dec_n += len(dec_bad)
            for at, t in off_bad[:2]:
                if shown < 8:
                    print(f"        🔴 {hit} 0x{at:X} 자리 어긋남 — {t!r}")
                    shown += 1
            for at, t, a, b in dec_bad[:2]:
                if shown < 8:
                    print(f"        🔴 {hit} 0x{at:X} 디코드 손실 — {t!r} {a} → {b}")
                    shown += 1
    finally:
        mm.close()
        _f.close()
    mark = "✅" if not (off_n or dec_n) else "❌"
    print(f"     {mark} 라운드트립 {tot - off_n - dec_n:,}/{tot:,} — 자리 {off_n} · 디코드 {dec_n}")
    if off_n or dec_n:
        raise SystemExit("덤프가 원본과 어긋난다 — 덤퍼가 잃는 것이 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
