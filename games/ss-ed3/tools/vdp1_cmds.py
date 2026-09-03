"""VDP1 **명령 표**를 읽는다 — emucap 으로 뜬 VRAM 덤프(헥스)를 넣는다.

    # 에뮬에서: read_memory(vdp1vram, 0, 512) … 를 이어 붙여 파일로 저장한 뒤
    python3 games/ss-ed3/tools/vdp1_cmds.py work/review/vdp1.hex

🔴 **순차로 읽으면 안 된다 — 사슬이다.** 명령마다 `JP`(점프 방식)가 있고, `jump assign`
   이면 `CMDLINK`(주소÷8)가 다음 명령을 가리킨다. 안 쓰는 칸은 표에 그대로 남아 있어
   순차로 훑으면 **지난 프레임의 쓰레기를 살아 있는 명령으로 읽는다**(2026-09-04 실제로
   그렇게 헤맸다 — `0x8000`(END)로 시작하는 칸이 수십 개 이어져 보였다).

⚠ 좌표는 `local coordinate`(보통 160,120) 기준이다 — 화면 좌표는 그만큼 더한다.
"""

import sys

NAMES = {
    0: "normal", 1: "scaled", 2: "distorted", 4: "polygon",
    5: "polyline", 6: "line", 8: "userclip", 9: "sysclip", 10: "local",
}


def s16(v):
    return v - 0x10000 if v >= 0x8000 else v


def walk(data, limit=256):
    """`[(색인, 정보)]` — 사슬을 따라가며 살아 있는 명령만."""
    out, i, seen = [], 0, set()
    while len(out) < limit:
        off = i * 32
        if off + 32 > len(data) or i in seen:
            out.append((i, None))  # 표 밖이거나 순환 — 더 읽어야 한다
            break
        seen.add(i)
        w = [int.from_bytes(data[off + k * 2 : off + k * 2 + 2], "big") for k in range(16)]
        ctrl, link, pmod, colr, srca, size = w[0], w[1], w[2], w[3], w[4], w[5]
        info = {
            "comm": NAMES.get(ctrl & 0xF, f"?{ctrl & 0xF}"),
            "w": ((size >> 8) & 0x3F) * 8, "h": size & 0xFF,
            "src": srca * 8, "colr": colr, "pmod": pmod,
            "x": s16(w[6]), "y": s16(w[7]), "end": bool(ctrl >> 15),
        }
        out.append((i, info))
        if info["end"]:
            break
        i = link if ((ctrl >> 12) & 7) == 1 else i + 1
    return out


def main():
    with open(sys.argv[1]) as f:
        data = bytes.fromhex("".join(f.read().split()))
    for i, c in walk(data):
        if c is None:
            print(f"  … 명령 {i}(오프셋 {i * 32:#x})부터 덤프 밖 — 더 읽는다")
            break
        print(
            f"  [{i:3d}] {c['comm']:9s} {c['w']:3d}x{c['h']:<3d} src={c['src']:#07x} "
            f"colr={c['colr']:#06x} pmod={c['pmod']:#06x} xy=({c['x']},{c['y']})"
            + (" END" if c["end"] else "")
        )


if __name__ == "__main__":
    main()
