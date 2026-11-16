#!/usr/bin/env python3
"""스크립트 `0F`(점프)가 **메시지 한가운데**로 들어가는 곳을 센다 — 래칫 게이트(11-06).

원판은 문장 꼬리를 여러 길이 공유한다(`…が、少しなくなっ` + `0F` → 다른 메시지의 `ている`). 번역은 그 메시지를 통째로 바꾸니 점프가
한국어 글자 한가운데로 떨어져 깨진 글·멈춤이 난다. 처리하는 길 둘 — ① 점프 바로 앞이 글이면 꼬리까지 이은 한 메시지
(`messages._merge_jump_tails`) ② 글 없는 메시지 + 3B 옵코드 뒤의 점프면 꼬리 자리에서 조각내(`messages._op_jump_targets`, 목적지 호스트를
`OP_JUMP_HOSTS` 에 올린 것만). 이 게이트는 **둘 다 못 잡은 점프**(파서 결과 기준)가 기준선(`script/jump_baseline.json`)보다
늘면 실패한다. 줄면 `--freeze` 로 내린다. 양성 대조: 처리 안 된 꼴(호스트 목록을 비운 파서)이 실제로 걸리는지 먼저 돈다.

    python3 games/pce-ed1/tools/check_script_jumps.py [--freeze]
    (구운 롬 쪽 되읽기는 `jump_readout.py` — check.sh 가 빌드 뒤에 돌린다)
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import messages as M

BASE_FILE = Path(__file__).resolve().parent.parent / "script" / "jump_baseline.json"


def scan(hosts_off: bool = False) -> list[str]:
    """처리 안 된 중간 진입 점프 — 「씬:점프위치→목적지(호스트 열쇠)」."""
    saved = M.OP_JUMP_HOSTS
    if hosts_off:
        M.OP_JUMP_HOSTS = frozenset()
    try:
        out = []
        for f in sorted(glob.glob(str(common.OUT_DIR / "text" / "*.bin"))):
            sid = int(re.search(r"_(\d+)\.bin$", f).group(1))
            b = Path(f).read_bytes()
            msgs = M.parse(b)
            for m in msgs:
                e = m.end
                if m.terminated or e + 5 >= len(b):
                    continue
                q = e if b[e] == M.JUMP else (e + 3 if b[e] in M.OP3 and b[e + 3] == M.JUMP else None)
                if q is None or any(isinstance(t, str) for t in m.tokens) != (q == e):
                    continue  # 글 + 바로 점프(①이 이은 것) / 글 없음 + 옵코드 + 점프(②)만 본다
                w = (b[q + 1] | b[q + 2] << 8) - M.BASE
                host = next((t for t in msgs if t.start < w < t.end), None)
                if host is not None:
                    out.append(f"scn{sid:03d}:{q}->{w}({host.key[:8]})")
        return sorted(set(out))
    finally:
        M.OP_JUMP_HOSTS = saved


def main() -> int:
    ctrl = scan(hosts_off=True)
    now = scan()
    if len(ctrl) <= len(now):
        print(f"❌ 양성 대조 실패 — 호스트 목록을 비워도 {len(ctrl)}곳(현재 {len(now)}곳): 검사가 처리 여부를 못 가린다")
        return 1
    base = json.loads(BASE_FILE.read_text()) if BASE_FILE.exists() else []
    if "--freeze" in sys.argv:
        BASE_FILE.write_text(json.dumps(now, ensure_ascii=False, indent=1) + "\n")
        print(f"기준선 갱신 — {len(now)}곳")
        return 0
    new = [x for x in now if x not in base]
    print(f"스크립트 점프 중간 진입 — 처리 안 된 {len(now)}곳 (기준선 {len(base)}) · 양성 대조 {len(ctrl)}곳(호스트 목록을 비웠을 때)")
    if new:
        print("❌ 기준선에 없는 새 중간 진입 점프:")
        for x in new:
            print("   ", x)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
