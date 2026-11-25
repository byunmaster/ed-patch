"""보스 직전 장면 → 전투 → 전투 뒤 이벤트 시험(마스터 10-24) — 디버그 마을(ETC. TEST)의 「보스」 NPC(ダリス · レイシア · カザズーム１·２ · ゴドウィン１·２)로 보스 직전 장면에 서서 I 로 진행시키며
화면 상태(전투 · 창 · 필드 · 검은 화면)와 프레임 해시 변화를 시간순으로 기록한다. 전투 뒤에도 장면이 이어지는지(멈춤 = 같은 화면이 오래 안 바뀜)를 본다. 촬영 없음 — 상태표와 끝 화면 몇 장만 남긴다.

    sh scripts/capture.sh python3 games/pce-ed2/tools/boss_event.py --iso <ed2.iso> --out <폴더> --state <etc_strong.state> [--boss 0,1,2,3,4,5] [--frames 14000]
`--state` 는 battle_run.py 가 남기는 etc_strong.state(레벨 96 으로 올린 디버그 마을 상태).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_run as br
import pcehl
from PIL import Image

BOSS = ["ダリス", "レイシア", "カザズーム１", "カザズーム２", "ゴドウィン１", "ゴドウィン２"]
NPC_STEPS = 21  # 보스 NPC 앞(왼쪽 길 NPC 열의 열째)까지 `up` 걸음 수(NPC k 번째 = 2k+1 걸음) — 닿기만 해도 메뉴가 열린다
EVENTS = [
    "エルアスタ オープニング",
    "ルディア城 出発",
    "ルディア城 1章始まり",
    "ルディア城 3章始まり",
    "ルディア城 終章始まり",
]  # 아홉째 NPC(19걸음) 세로 목록


def classify(img) -> str:
    bf = br.black_frac(img)
    if bf > 0.5:
        return "B" if br.window_open(img) else "K"  # B = 전투(검은 배경 + 창) · K = 검은 화면
    return "W" if br.window_open(img) else "F"  # W = 필드/장면 위 창(대사) · F = 창 없는 필드


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.e42dc6b34ced533663e83bcdb21e7a7d.sav")
    ap.add_argument("--boss", default="0,1,2,3,4,5")
    ap.add_argument(
        "--events", action="store_true", help="보스 NPC 대신 이벤트 점프 NPC(아홉째, 세로 목록 5개)"
    )
    ap.add_argument("--frames", type=int, default=14000)
    a = ap.parse_args()
    out = Path(a.out)
    pre = "event" if a.events else "boss"
    out.mkdir(parents=True, exist_ok=True)
    cue = str(Path(a.iso).with_suffix(".cue"))
    e = pcehl.Emu(cue, bram=a.bram)
    for b in [int(x) for x in a.boss.split(",")]:
        e.load(a.state)
        br.close_windows(e)
        for _ in range(19 if a.events else NPC_STEPS):
            br.step_up(e)
        e.press("left", 3, 30)
        if a.events:
            for _ in range(b):
                e.press("down", 4, 20)
        else:
            for _ in range(b // 2):
                e.press("down", 4, 20)
            if b % 2:
                e.press("right", 4, 20)
        Image.fromarray(e.frame_img).save(out / f"{pre}{b}_menu.png")
        e.press("i", 3, 10)
        line, hashes, used = [], [], 0
        while used < a.frames:
            e.press("i", 3, 37)
            used += 40
            if used % 120 == 0:
                line.append(classify(e.frame_img))
                hashes.append(e.frame_hash())
            if used % 2400 == 0:
                Image.fromarray(e.frame_img).save(out / f"{pre}{b}_{used:05d}.png")
        Image.fromarray(e.frame_img).save(out / f"{pre}{b}_end.png")
        tail = hashes[-20:]
        frozen = len(set(tail)) == 1
        tl = "".join(line)
        print(
            f"{b} {(EVENTS if a.events else BOSS)[b]} 타임라인(120f/칸) {tl} · 끝 20칸 화면 {'같음(멈춤 의심)' if frozen else '변함'}",
            flush=True,
        )
        (out / f"{pre}{b}.txt").write_text(tl + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
