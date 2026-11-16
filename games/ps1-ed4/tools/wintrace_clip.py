"""덫 로그에서 「그린 글자열 px > 창 열×12−6」 인 그리기를 자동으로 뽑는다(시험 전용). 사용: wintrace_clip.py(로그 경로는 내부 목록 — 필요하면 고쳐 쓴다). ⚠ 작은 메뉴(열×12 에 꼭 맞는 3~4글자)는 −6 기준이 거짓 양성을 낸다 → 열×12 초과만 진짜 넘침으로 본다."""

import collections
import glob
import json
import struct
import sys

sys.path.insert(0, "/tmp/claude-0/ovw")
sys.path.insert(0, "tools")
sys.path.insert(0, "../..")
import lw

files = (
    ["/tmp/claude-0/ovw/wt_ex.json"]
    + glob.glob("/tmp/claude-0/ovw/wt_shops2.*.json")
    + ["/tmp/claude-0/ovw/wt_battle.json", "/tmp/claude-0/ovw/wt_btl_flat.json"]
)
flag = collections.defaultdict(lambda: [0, 0, ""])
for f in files:
    opens = []
    with open(f) as fh:
        events = json.load(fh)
    for ev in events:
        tag, a0, a1, a2, a3, ra, x, y, c, r, codes, *raw = ev
        if tag == 1:
            opens.append((ra - 8, (a0, a1, a2, a3)))
            continue
        if tag not in (2, 3):
            continue
        if tag == 3 and raw and raw[0]:
            w = struct.unpack("<24H", bytes.fromhex(raw[0]))[1:]
            nm = []
            for v in w:
                if v in (0xFFFF, 0, 0x8000, 0x8002) or v >= 0x4000:
                    break
                nm.append(v)
            codes = nm
        if not codes:
            continue
        site = None
        for s, (oa0, oa1, oa2, _oa3) in reversed(opens):
            if (
                ((oa0 - 160) & 0xFFFF) == (x & 0xFFFF)
                and ((oa1 - 120) & 0xFFFF) == (y & 0xFFFF)
                and (oa2 & 0xFF) == c
            ):
                site = s
                break
        px = lw.px(codes)
        lim = c * 12 - 6
        k = (hex(site) if site else "?", c)
        flag[k][0] += 1
        if px > lim and c <= 20:
            flag[k][1] += 1
            if px > len(flag[k][2]):
                pass
            flag[k][2] = max(
                flag[k][2],
                f"{px}px {lw.txt(codes)}",
                key=lambda s: int(s.split("px")[0]) if s else 0,
            )
for k, v in sorted(flag.items()):
    if v[1]:
        print(k, "그림", v[0], "한도 초과", v[1], "최장", v[2])
print("총 창(열)별", len(flag))
