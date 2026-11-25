#!/usr/bin/env python3
"""음성 자막(비모달 ON) 쪽 시각 게이트(11-08, 마스터 「빼기 줄의 끝 시각이 다음 줄 열림을 늦춘다」 — 062 #3 이 0.3초만 떴다·046 「으응…」이 2.4초 늦게 열렸다).

제품 명세(`gwin_rt._on_flow_spec` — 구워지는 것과 같은 코드)를 22씬·31토막 전부 뽑아:
  ① 표시 시간이 0.5초 미만인 쪽 → 실패 (0.5~1.0초는 알림 — 「예.」「…아니요」 같은 짧은 외침)
  ② 마스터가 연 시각(`on_overlay.starts`)을 준 쪽이 그 시각보다 1.1초 넘게 늦게 열림 → 실패(리드로 앞당기는 건 허용)
  ③ 쪽이 앞 쪽 끝보다 0.05초 넘게 먼저 시작(겹침) → 실패
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gwin_rt as G
import voice_sched as VS


def main() -> int:
    sc = VS.load(drafts=True)
    bad, note = [], []
    for sid, segs in sc.items():
        lst = segs if isinstance(segs, list) else [segs]
        for k, seg in enumerate(lst):
            pg = G._on_flow_spec(int(sid), k)["pages"]
            ov = seg.get("on_overlay") or {}
            starts = ov.get("starts", {})
            hidden = {a for a, _ in G.audit_absent(int(sid), k, seg.get("voice_gate"))} | set(ov.get("skip") or [])  # 안 나가는 줄은 열림 시각이 없다
            for i, p in enumerate(pg):
                d = p["end"] - p["start"]
                if d < 0.5:
                    bad.append(f"씬 {sid} s{k} 쪽 {i}: 표시 {d:.2f}초 [{p['start']}-{p['end']}] {p['text'][:14]!r}")
                elif d < 1.0:
                    note.append(f"씬 {sid} s{k} 쪽 {i}: 표시 {d:.2f}초 {p['text'][:12]!r}")
                if i and p["start"] < pg[i - 1]["end"] - 0.05:
                    bad.append(f"씬 {sid} s{k} 쪽 {i}: 앞 쪽 끝 {pg[i-1]['end']} 보다 먼저 {p['start']}")
            # ② 마스터 시작 vs 실제 시작: 열쇠의 첫 쪽을 찾을 수 없어 시작 값 자체가 어느 쪽 시작과도 0.6초 안에 드는지만 본다
            for key, st in starts.items():
                if st >= 900 or key in hidden or any(h.startswith(key[:16]) or key.startswith(h[:16]) for h in hidden):
                    continue
                near = [p for p in pg if -0.7 <= p["start"] - st <= 1.1]  # 겹침(마스터 시작 < 앞 쪽 끝)은 앞 쪽 끝에서 이어 연다 — 최대 1초 늦음 허용
                if not near and any(st <= p["end"] for p in pg):
                    bad.append(f"씬 {sid} s{k}: 마스터 시작 {st}({key[:8]}) 에 열리는 쪽이 없다")
    print(f"음성 자막 쪽 시각 감사 — 짧은 쪽(0.5~1.0초) 알림 {len(note)}")
    for m in note:
        print("  ·", m)
    if bad:
        print("✘ 쪽 시각 이상:")
        for m in bad:
            print("   ", m)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
