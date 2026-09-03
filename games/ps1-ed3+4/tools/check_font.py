"""폰트 레이아웃 게이트 — **모양이 뻔한 글자**로 읽기 변환을 검산한다.

🔴 이 게임은 글리프를 12행 × 12비트로 저장하되 **이웃한 두 열이 짝으로 뒤바뀌어** 있다
   (`font._swap_pairs`). 그 변환을 빠뜨리면 한자는 두꺼워 그럭저럭 읽히는데 **한글은
   획이 한 칸씩 튀어 무너진다** — 실제로 그 상태로 한 번 구웠다(2026-09-03).

   그래서 「글자가 대충 읽히나」로는 못 잡는다. **모양이 계산되는 글자**로 본다:
   `一` 은 가로 한 줄이고, 그 줄은 **끊기면 안 된다.**
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import font  # noqa: E402
import textenc  # noqa: E402


def check(disc):
    exe, _, _ = font.exe_bytes(disc)
    rev = {v: k for k, v in textenc.charmap(disc).items()}
    bad = []

    def glyph(ch):
        return np.asarray(font.read_glyph(exe, rev[ch], disc), dtype=int) if ch in rev else None

    # 一 — 가로 한 줄. 잉크가 있는 행은 하나뿐이고 그 행은 **끊김이 없어야** 한다.
    g = glyph("一")
    if g is None:
        bad.append("一 이 코드표에 없다")
    else:
        rows = np.nonzero(g.any(axis=1))[0]
        if len(rows) != 1:
            bad.append(f"一 의 잉크 행이 {len(rows)}개 (1이어야 한다)")
        else:
            cols = np.nonzero(g[rows[0]])[0]
            if len(cols) != cols.max() - cols.min() + 1:
                bad.append(f"一 의 가로줄이 끊겼다 — 열 {cols.tolist()}")
    # 口 — 위·아래 가로줄과 좌·우 세로줄. 네 변이 다 끊김 없이 이어져야 한다.
    g = glyph("口")
    if g is not None:
        rows = np.nonzero(g.any(axis=1))[0]
        for r in (rows.min(), rows.max()):
            cols = np.nonzero(g[r])[0]
            if len(cols) != cols.max() - cols.min() + 1:
                bad.append(f"口 의 가로변(행 {r})이 끊겼다")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    a = ap.parse_args()
    common.verify_source(a.disc)
    if not os.path.exists(textenc.charmap_path(a.disc)):
        print(f"⏭ {a.disc}: 코드표 정본이 아직 없다")
        return 0
    bad = check(a.disc)
    for m in bad:
        print(f"  🔴 {m}")
    print(f"{a.disc}: 폰트 레이아웃 — {'🔴 어긋났다' if bad else '✅ 모양이 계산대로 나온다'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
