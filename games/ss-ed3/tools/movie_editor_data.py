"""영상 자막 편집기 자료 — `script/movie.json` 의 자막을 한 장의 JSON 으로 뽑는다.

    python3 games/ss-ed3/tools/movie_editor_data.py          # → .local/work/inbox/ss-ed3/movie-editor/data.json
    python3 games/ss-ed3/tools/movie_editor_data.py --check  # 쓰지 않고 요약만

항목마다 `scene`(M01…)·`idx`(그 편 안 번호, 1부터)·`kr`(지금 자막)·`jp`(받아쓰기 초벌 — 시작 시각이 가장 가까운 줄, 없으면 빈 문자열)·
`t_start`·`t_end`·`fixed`(마스터가 시각을 확정한 칸 — `movie.json._fixed`)·`video`.

🔴 **산출물에 일본어 받아쓰기가 든다** — 커밋하지 않는다(`.local` 은 git 밖). 원문은 코드에 갖지 않고 `work/review/movie/Mxx.json`(받아쓰기 초벌)에서 붙인다.
영상은 같은 폴더 `video/Mxx.mp4`(자막 없는 원본 영상 — 원본 화면이라 커밋 금지).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")
DRAFT = os.path.join(C.REVIEW_DIR, "movie")
MATCH_WINDOW = 2.5  # 초 — 받아쓰기 시각과 이만큼 안이면 같은 줄로 본다


def out_dir():
    """메인 트리 `.local/work/inbox/ss-ed3/movie-editor/` — 워크트리 안에 `.local` 을 만들지 않는다."""
    common = os.popen(f"git -C {C.GAME_DIR} rev-parse --path-format=absolute --git-common-dir").read().strip()
    return os.path.join(os.path.dirname(common), ".local", "work", "inbox", "ss-ed3", "movie-editor")


def draft(scene):
    p = os.path.join(DRAFT, f"{scene}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("segments", [])


def rows():
    with open(SCRIPT, encoding="utf-8") as f:
        sc = json.load(f)
    fixed = sc.get("_fixed", {})
    out = []
    for scene in sorted(k for k in sc if k.startswith("M") and sc[k]):
        seg = draft(scene)
        fx = {round(float(x), 2) for x in fixed.get(scene, [])}
        for i, (a, b, kr) in enumerate(sc[scene], 1):
            near = min(seg, key=lambda s: abs(s["start"] - a), default=None)
            jp = near["jp"] if near and abs(near["start"] - a) <= MATCH_WINDOW else ""
            out.append(
                {
                    "scene": scene,
                    "idx": i,
                    "jp": jp,
                    "kr": kr,
                    "t_start": a,
                    "t_end": b,
                    "fixed": round(float(a), 2) in fx,
                    "video": f"{scene}.mp4",
                }
            )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    rs = rows()
    scenes = sorted({r["scene"] for r in rs})
    print(f"편 {len(scenes)} · 자막 {len(rs)}줄 · 원문 연결 {sum(1 for r in rs if r['jp'])} · 시각 확정 {sum(r['fixed'] for r in rs)}")
    if a.check:
        return 0
    d = out_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
        json.dump(rs, f, ensure_ascii=False)
    print("→", os.path.join(d, "data.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
