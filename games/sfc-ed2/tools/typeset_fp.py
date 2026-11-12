"""sfc-ed2 조판 지문 — `scripts/check/typeset_fingerprint.py` 가 부르는 게임별 구현.

롬에 굽는 문안 전량(`$C2~$CB` 대사 구간)을 **빌드와 같은 조판기**(`build.typeset_seg` — 앞 구간 줄 상태·호출 폭까지 센다)에 태워
구역별(뱅크·하위 4KB 쪽) sha1 을 낸다. 공용 `krwrap` 이 바뀌면 이 게임 줄바꿈이 조용히 바뀌므로 그걸 잡는다.
문안·조판 규칙을 의도적으로 바꿨을 때만 `--game sfc-ed2 --freeze`.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout


def fingerprint() -> dict[str, str]:
    res = check_layout.typeset_all()
    hs: dict[str, hashlib._Hash] = {}
    for key in sorted(res):
        # 구간 키 = SNES 주소(`$C2xxxx`) — 뱅크와 그 안 4KB 쪽으로 가른다
        snes = int(key.lstrip("$"), 16)
        zone = f"{snes >> 16:02X}:{(snes >> 12) & 0xF:X}"
        hs.setdefault(zone, hashlib.sha1()).update(f"{key}\x00{res[key]}\x02".encode())
    return {k: h.hexdigest()[:12] for k, h in sorted(hs.items())}


if __name__ == "__main__":
    print(fingerprint())
