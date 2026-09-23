"""VRAM 덤프 묶음 → 장면별 **안전 청크**(512B) 표 — 자막 스프라이트를 둘 자리를 고른다.

    python3 tools/vram_scenes.py <덤프폴더> <장면정의.json>      # 표를 stdout 으로

emucap `dump_memory` 가 떨군 폴더(vram0.bin · sat0.bin · ram.bin · state.json)를 시간순으로 읽는다.
각 덤프의 **카운터 프레임**(런타임 V_FRAME 과 같은 눈금 = IRQ1 통과 횟수)은 `$2249`(IRQ 가 매번
올리는 바이트)의 증분을 이어 붙여 구한다 — 그림을 갈 때 게임이 IRQ 를 막아 벽시계와 어긋나기 때문이다.

청크가 장면 k 에서 **안전**하려면 [switch−120, 다음 switch+180] 안의 어느 덤프에서도
  · BAT(전체 — 보이는 창만이 아니라) 가 타일로 참조하지 않고, BAT·SATB 자리도 아니고,
  · 게임 스프라이트(SAT)가 패턴으로 읽지 않고(워드주소 = 코드<<5),
  · 이웃 덤프 사이에 내용이 바뀌지 않아야 한다.
오프닝(opening_scenes.json)과 달리 **빌리지 않는다** — 엔딩은 장면마다 25개 넘게 남는다.
⚠ 덤프 간격(1~4초) 사이에 썼다가 되돌린 청크는 못 본다. 인게임 확인이 최종이다.
"""

import glob
import json
import struct
import sys

BAT = {
    0: (32, 32),
    1: (64, 32),
    2: (128, 32),
    3: (128, 32),
    4: (32, 64),
    5: (64, 64),
    6: (128, 64),
    7: (128, 64),
}


def load(dirs):
    out, counter, prev_irq = [], None, None
    for d in dirs:
        st = json.load(open(d + "/state.json"))
        ram = open(d + "/ram.bin", "rb").read()
        irq = ram[0x249]
        if counter is None:
            counter = 0
        else:
            counter += (irq - prev_irq) & 0xFF
        prev_irq = irq
        v = open(d + "/vram0.bin", "rb").read()
        w = struct.unpack("<32768H", v)
        bw, bh = BAT[(st["VDC.MWR"] >> 4) & 7]
        used = {i // 256 for i in range(bw * bh)} | {
            ((w[i] & 0x7FF) * 16) // 256 for i in range(bw * bh)
        }
        used.add(st["VDC.DVSSR"] // 256)
        s = struct.unpack("<256H", open(d + "/sat0.bin", "rb").read())
        for k in range(64):
            y, x, p, a = s[k * 4 : k * 4 + 4]
            if not (y or x or p or a):
                continue
            cw = 2 if a & 0x100 else 1
            ch = {0: 1, 1: 2, 2: 4, 3: 4}[(a >> 12) & 3]
            base = (p & 0x7FF) << 5
            for dy in range(ch):
                for dx in range(cw):
                    used.add((base + (dy * 2 + dx) * 64) // 256)
        width = ((st["VDC.HDR"] & 0x7F) + 1) * 8
        out.append(
            {"dir": d, "counter": counter, "vram": v, "used": used, "width": width, "h": ram[0xD54]}
        )
    return out


def join(series):
    """여러 덤프 묶음(각자 0 에서 센 카운터)을 **앞 묶음 끝과 겹치는 기준점**으로 잇는다.
    series = [(묶음, 이 묶음 첫 덤프의 카운터)]."""
    out = []
    for dumps, base in series:
        for x in dumps:
            out.append(dict(x, counter=x["counter"] + base))
    out.sort(key=lambda x: x["counter"])
    return out


def safe_table(dumps, switches, pre=120, post=180):
    res = []
    for k, sw in enumerate(switches):
        nxt = switches[k + 1] if k + 1 < len(switches) else 1 << 30
        lo, hi = sw - pre, nxt + post
        sel = [x for x in dumps if lo <= x["counter"] <= hi]
        bad = set()
        for x in sel:
            bad |= x["used"]
        for a, b in zip(sel, sel[1:]):
            bad |= {
                c
                for c in range(128)
                if a["vram"][c * 512 : (c + 1) * 512] != b["vram"][c * 512 : (c + 1) * 512]
            }
        widths = sorted(
            {x["width"] for x in sel if sw <= x["counter"] < nxt} or {x["width"] for x in sel}
        )
        res.append(
            {
                "switch": sw,
                "safe": [c for c in range(128) if c not in bad],
                "widths": widths,
                "n_dumps": len(sel),
            }
        )
    return res


if __name__ == "__main__":
    dumps = load(sorted(glob.glob(sys.argv[1] + "/*")))
    sw = json.load(open(sys.argv[2]))["switches"]
    print(json.dumps(safe_table(dumps, sw), ensure_ascii=False, indent=1))
