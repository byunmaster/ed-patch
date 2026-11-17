"""전수 촬영 결과에서 **한글에만 나온 「빈 줄」**(본문 뒤 이어지는 이름 줄 앞 빈 줄 부류)을 잡는 게이트 — 같은 꼴이 다시 생기지 못하게 한다.

   python3 tools/check_sweep_blank.py [촬영 폴더…]      # 기본: 메인 트리 `.local/work/inbox/ps1-ed4/sweep-*` 중 가장 늦은 것

촬영(`sweep_shots.py shoot`)이 스트림마다 낸 `index*.jsonl` 의 이상 중 「빈 줄」을 읽고, 원판에서도 나온 스트림(`blank_row_baseline.json`)이 아니면 실패한다.
정적으로는 못 가린다 — 이름·다음 출력이 **어디서 이어 그려지는지**가 스크립트 흐름(해석기)에 있어, 조각 합침 뒤 빈 꼬리 조각이 결함인지는 화면에서만 드러난다.
촬영 폴더가 없으면 「안 쟀다」로 알리고 통과한다(`check_names` 와 같은 처리). 전수 촬영을 돌릴 때마다 이 게이트도 돌린다.
"""

import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(HERE)


def main(argv):
    with open(os.path.join(G, "blank_row_baseline.json"), encoding="utf-8") as f:
        base = json.load(f)
    ok = {tuple(x) for x in base["원판과 같은 스트림"]}
    dirs = argv[1:]
    if not dirs:
        try:
            top = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=G, capture_output=True, text=True, check=True).stdout.strip()
            root = os.path.abspath(os.path.join(G, top, ".."))
        except Exception:  # noqa: BLE001
            root = ""
        found = sorted(glob.glob(os.path.join(root, ".local/work/inbox/ps1-ed4/sweep-*")))
        dirs = [d for d in found if glob.glob(os.path.join(d, "index*.jsonl"))][-1:]
    if not dirs:
        print("  ⚠ 전수 촬영 결과가 없다 — 한글 전용 「빈 줄」을 안 쟀다(촬영 뒤 다시 돌린다)")
        return 0
    n = bad = 0
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "index*.jsonl"))):
            with open(p, encoding="utf-8") as f:
                lines = f.readlines()
            for ln in lines:
                x = json.loads(ln)
                n += 1
                if any("빈 줄" in a for a in x["anom"]):
                    k = (x["member"].split("\\")[-1], x["si"])
                    if k not in ok:
                        bad += 1
                        print(f"   🔴 {k[0]} 스트림 {k[1]}: 한글에만 있는 빈 줄 — {x['anom'][:2]}")
    print(f"  촬영 {n}스트림 ({', '.join(os.path.basename(d) for d in dirs)}) · 한글 전용 「빈 줄」 {bad} (원판과 같은 {len(ok)}곳은 기준선)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
