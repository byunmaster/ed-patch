#!/usr/bin/env python3
"""ED2.EXE 의 「번역 표에 없던」 가나 문자열 23건이 **빌드 이미지에서 어댑터가 말하는 값**인가.

`names_corpus` 가 `ED2전투:<오프셋>` 으로 내는 이름·메모리카드 문구는 다른 패처(`patch_ed2_sys` 의
정본 표 · `patch_sys_ui.MSGS`)가 옮긴다. 어댑터가 읽는 값과 **이미지에 실제로 박힌 바이트**가
같은지 여기서 대조한다 — 어댑터가 「번역됨」이라고 하는데 화면은 일본어인 어긋남을 잡는다.

- 시나리오 아이템 칸(`0xD4870~0xD4950`) → `enc(kr)` 가 그 자리에 있어야 한다.
  단 `FIXED_ITEM_REFS` 넷은 원래 칸을 그대로 두고 **참조(lui/addiu)만 REPACK 꼬리로 돌렸다** —
  참조가 가리키는 문자열이 `enc(kr)` 인지 본다.
- 메모리카드 문구 → `enc_msg(kr)` 가 그 자리에 있어야 한다.

  python3 tools/check_ed2_sys_corpus.py
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
)
os.environ.setdefault("LOCK_BYPASS", "1")

import patch_ed2_sys as S2
import patch_sys_ui as SU
from common import extract

KANA = re.compile(r"[぀-ヿ一-鿿]")


def main():
    if not os.path.exists(S2.IMG):
        print("⚠ 빌드 이미지가 없다 — 안 쟀다")
        return 1
    import patch_ed2_battle as B2

    buf = bytes(extract(S2.ED2_LBA, S2.ED2_SIZE, path=S2.IMG))
    canon = S2.apply_canon()
    msgs = dict(SU.MSGS)
    refs = S2.FIXED_ITEM_REFS
    items_lo, items_hi, _ = S2.FIXED_SLOTS[0]
    bad, n = [], 0
    _fit, _over, none = B2.plan()
    for off, jp in none:
        if not KANA.search(jp):
            continue  # 분모 밖(SDK 영문 · 서식 · 빈 문자열) — names_corpus 주석
        in_items = items_lo <= off < items_hi
        kr = canon.get(jp) if in_items else msgs.get(jp)
        loc = f"ED2전투:{off:#x}"
        if kr is None:
            bad.append((loc, "표에 없음"))
            continue
        want = S2._enc(kr) if in_items else SU.enc_msg(kr)
        n += 1
        if in_items and jp in refs:
            lui_fo, imm_fo, _wl, _wi = refs[jp]
            hi = struct.unpack_from("<I", buf, lui_fo)[0] & 0xFFFF
            lo = struct.unpack_from("<I", buf, imm_fo)[0] & 0xFFFF
            if lo & 0x8000:
                lo -= 0x10000
            fo = (hi << 16) + lo - 0x80010000 + 0x800
            got = buf[fo : fo + len(want)]
            where = f"참조→0x{fo:X}"
        else:
            got = buf[off : off + len(want)]
            where = f"0x{off:X}"
        if got != want:
            bad.append((loc, f"{where}: 이미지 {got.hex()} ≠ 기대 {want.hex()} ({kr!r})"))
    for loc, why in bad:
        print(f"  ❌ {loc} {why}")
    if bad:
        print(f"❌ ED2.EXE 가나 문자열 어댑터 값 ≠ 이미지: {len(bad)}/{n}")
        return 1
    print(f"✅ ED2.EXE 가나 문자열 {n}건: 어댑터 값 = 빌드 이미지 바이트")
    return 0


if __name__ == "__main__":
    sys.exit(main())
