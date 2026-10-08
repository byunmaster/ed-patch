"""나레이션 자막 ↔ 음성 박자 표 — 음성 토막마다 「음성 길이」와 「이어진 자막 시간」을 나란히 놓는다(정적).

ON 경로는 `JSR $5815 + 인라인 4B(오프셋·섹터 수)` 로 음성을 틀고 `LDX/LDY · JSR $5BD7` 로 그 프레임 수만큼
기다린다. 우리 상주부는 같은 타이머에서 읽은 시간만 빼고 기다리므로 자막이 뜨는 시간은 타이머 합이다.
음성이 그보다 `SYNC_TOL`(1.5초) 넘게 길면 `narration_gates.retime` 이 마지막 자막 타이머를 음성 끝까지 늘린다(마스터 10-08 (가)).
이 표는 늘리기 **전/후**의 어긋남을 센다. 음성 1섹터 = 0.256초, PCE 프레임은 59.826Hz.

    python3 games/pce-ed1/tools/voice_sync.py          # → work/review/voice_sync.md
    python3 games/pce-ed1/tools/voice_sync.py --check  # 게이트: 늘린 뒤 모든 토막이 ±1.5초 안이어야(OPEN_RUNS 는 미해결로 따로 센다)
"""

import glob
import sys
from pathlib import Path

import common
import narration_gates as G


def blocks():
    for sid in sorted(G.SITES):
        for f in sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin"))):
            yield sid, Path(f).read_bytes()
            break  # 컨테이너마다 같은 사본이면 하나만


def measure():
    """[(씬, 토막 dict, 전 합초, 후 합초, 음성초, 상태)] — 상태: ok | open | bad."""
    out = []
    for sid, b in blocks():
        add = G.retime(b, sid)
        for r in G.voice_runs(b, sid):
            voice = r["voice"] / G.FPS
            before = sum(v for _, v, _ in r["timers"]) / G.FPS
            after = before + sum(add.get(p, 0) for p, _, _ in r["timers"]) / G.FPS
            if r["open"]:
                state = "open"
            elif abs(voice - after) <= G.SYNC_TOL:
                state = "ok"
            else:
                state = "bad"
            out.append((sid, r, before, after, voice, state))
    return out


def main():
    rows = measure()
    lines = [
        "| 씬 | 게이트 | 음성(초) | 자막 합 전(초) | 후(초) | 음성−후(초) | 판정 |",
        "|---|---|---|---|---|---|---|",
    ]
    mark = {"ok": "✅", "open": "🔴 미해결", "bad": "❌ 어긋남"}
    for sid, r, before, after, voice, state in rows:
        extra = f" — {G.OPEN_RUNS[sid]}" if state == "open" and sid in G.OPEN_RUNS else ""
        lines.append(
            f"| {sid} | g{r['gate']} | {voice:.1f} | {before:.1f} | {after:.1f} | {voice - after:+.1f} | {mark[state]}{extra} |"
        )
    n = {k: sum(1 for x in rows if x[5] == k) for k in mark}
    summary = f"토막 {len(rows)} — ✅ {n['ok']} · 🔴 미해결 {n['open']} · ❌ {n['bad']}"
    lines += ["", summary]
    out = common.REVIEW_DIR / "voice_sync.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if "--check" in sys.argv:
        print(f"나레이션 싱크 [pce-ed1] — {summary}")
        for sid, r, _b, a, v, state in rows:
            if state == "bad":
                print(
                    f"  ❌ scn{sid:03d} g{r['gate']}: 음성 {v:.1f}초 ↔ 자막 {a:.1f}초",
                    file=sys.stderr,
                )
        for sid, r, *_ in rows:
            if _[-1] == "open" and sid not in G.OPEN_RUNS:
                print(
                    f"  ❌ scn{sid:03d} g{r['gate']}: 열린 토막인데 OPEN_RUNS 에 사유가 없다",
                    file=sys.stderr,
                )
                n["bad"] += 1
        sys.exit(1 if n["bad"] else 0)
    print("\n".join(lines))
    print("→", out, file=sys.stderr)


if __name__ == "__main__":
    main()
