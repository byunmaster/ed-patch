#!/usr/bin/env python3
"""바뀐 바이트 감사 게이트(밤샘 11, 마스터 11-08) — 원판과 방금 구운 롬을 섹터 단위로 대조해 **어느 구역이 얼마나 바뀌었나**를 구역별로 세고,
커밋된 기준선(`changed_bytes_baseline.json`)에 **없던 구역**이 새로 바뀌거나 구역의 바뀐 섹터 수가 기준선을 **넘으면 실패**한다(래칫).

구역 = 유저 데이터 상대 섹터(rel)를 이름 붙인 것: IPL · 본 프로그램(rel 34~129, 뱅크 0x68+ 단위 8KB) · 씬 컨테이너(rel 별 · `containers.scan`) ·
전투 컨테이너 · 그 밖(rel 범위 버킷). 빌드는 허용 섹터 밖이 같음을 이미 보장하지만(무변경 대조 — 허용 627섹터) **허용 안에서 어디가 얼마나 늘었나**는 안 봤다 —
조용히 새 구역을 건드리거나(예: 다른 컨테이너 배치 변경) 어떤 구역의 변경이 갑자기 불어나는 걸 여기서 잡는다.

    python3 tools/check_changed_bytes.py            # 게이트
    python3 tools/check_changed_bytes.py --freeze   # 기준선 갱신(의도한 변경일 때만)
    python3 tools/check_changed_bytes.py --report   # work/review/changed_bytes.md 에 구역표
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
import containers

BASELINE = HERE.parent / "changed_bytes_baseline.json"
SLACK = 1.10  # 구역 바뀐 섹터 수가 기준선의 10% 안에서 흔들리는 건 문안 변경이라 허용(작은 구역은 +2섹터)


def region_of(rel: int, cont_starts: list[tuple[int, int, str]]) -> str:
    if rel < 34:
        return "IPL·시스템 카드 앞"
    if rel < 130:
        return f"본 프로그램 뱅크 0x{0x68 + (rel - 34) // 4:02X}"
    for a, b, name in cont_starts:
        if a <= rel < b:
            return name
    return f"그 밖 rel {rel // 512 * 512}~"


def main() -> int:
    built = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not built.exists():
        print(f"✘ {built} 가 없다 — 빌드가 먼저 돌아야 한다")
        return 1
    import numpy as np

    o = np.frombuffer(common.ORIG_ISO.read_bytes(), np.uint8)
    n = np.frombuffer(built.read_bytes(), np.uint8)
    if len(o) != len(n):
        print(f"✘ 이미지 크기가 다르다 — 원판 {len(o)} · 롬 {len(n)}")
        return 1
    raw = common.RAW
    diff = o != n
    secs = np.nonzero(diff.reshape(-1, raw).any(axis=1))[0] if len(o) % raw == 0 else np.array([], int)
    cont = [(c["rel"], c["rel"] + 16, f"씬 컨테이너 rel {c['rel']}") for c in containers.scan()]
    cont += [(a, a + 16, f"씬 컨테이너(이사) rel {a}") for a in range(9700, 10000, 16)]
    per_sec = diff.reshape(-1, raw).sum(axis=1)
    reg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in secs:
        rel = int(s) - common.T2_SECTOR
        name = region_of(rel, cont)
        reg[name][0] += 1
        reg[name][1] += int(per_sec[s])
    out = {k: {"sectors": v[0], "bytes": v[1]} for k, v in sorted(reg.items())}
    total = {"sectors": sum(v[0] for v in reg.values()), "bytes": sum(v[1] for v in reg.values())}
    if "--freeze" in sys.argv:
        BASELINE.write_text(json.dumps({"total": total, "regions": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  바뀐 바이트 기준선 갱신: 구역 {len(out)} · 섹터 {total['sectors']} · 바이트 {total['bytes']}")
        return 0
    if "--report" in sys.argv:
        for k, v in out.items():
            print(f"{k}\t{v['sectors']}\t{v['bytes']}")
        return 0
    if not BASELINE.exists():
        print("✘ changed_bytes_baseline.json 이 없다 — --freeze 로 만든다")
        return 1
    base = json.loads(BASELINE.read_text("utf-8"))["regions"]
    bad = []
    for k, v in out.items():
        b = base.get(k)
        if b is None:
            bad.append(f"새 구역이 바뀜: {k} — 섹터 {v['sectors']} · 바이트 {v['bytes']}")
        elif v["sectors"] > max(b["sectors"] * SLACK, b["sectors"] + 2):
            bad.append(f"구역 변경이 불어남: {k} — 섹터 {b['sectors']} → {v['sectors']}")
    print(f"바뀐 바이트 감사 — 구역 {len(out)} · 섹터 {total['sectors']} · 바이트 {total['bytes']:,} (원판 대비)")
    if bad:
        print("✘ 의도한 변경이면 `check_changed_bytes.py --freeze` 로 기준선을 갱신하고 사유를 devlog 에 남긴다:")
        for m in bad:
            print("   ", m)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
