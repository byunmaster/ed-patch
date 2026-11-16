"""가운데 맞춤 점검 — 번역 규칙 2-8 (마스터 10-13 「공백·문장부호는 0.5칸, 줄 끝 마침표·쉼표·…는 폭에서 빼기」, 11-03 정적 점검).

    python3 games/ss-ed3/tools/check_center.py          # 자리별 줄 수와 좌우 여백 차
    python3 games/ss-ed3/tools/check_center.py --check  # 양성 대조 · 고칠 수 있는 어긋남 · 한계 목록 증가 → rc 1

가운데 맞춤 자리를 **실제 픽셀 폭**으로 잰다(줄 끝 `. , ? ! …` 는 폭에서 뺀다). 좌우 여백 차 = |왼쪽 여백 − 오른쪽 여백| (px):
  · 해설·카드(`center_narration`) — 칸 12px · 반각 6px · 앞 공백 반 칸(6px) 단위라 **여백 차는 12px 단위**(글자 폭이 반 칸의 홀수배면 6px 이 하한)다.
    하한을 넘는 줄 = 어긋남. 예산(앞 공백도 바이트)이 모자라 블록째 왼쪽으로 민 블록 · 마스터 손 배치(`narration_manual.json`)는 고칠 수 없는 **한계 목록**으로 센다.
  · 영상 자막(`movie_hardsub`) — 그리는 쪽이 `(W − 폭)//2` 라 줄 끝 부호를 뺀 편(`CENTER_V2`)은 ≤1px. 부호를 뺀 계산판이 아닌 편에 줄 끝 부호 줄이 있으면 어긋남이다.
  · 음성 크레딧(`voice_credits`) — 앞 공백 4px 단위라 여백 차 4px 가 하한 안쪽. 4px 를 넘는 줄은 한계 목록이다 — 자동 배치는 줄끼리 가운데를 맞추는 게 우선
    (가장 긴 줄 기준 상대 반올림, 마스터 10-06 · 단위 테스트가 ≤2px 로 못 박는다)이고 손 배치 `pads` 는 마스터 값이다.
정렬이 아닌 자리는 안 센다 — 지명판(34장)은 원판처럼 양끝 맞춤, 서책 표지는 원판 짜임을 지키며 그림 한가운데에 앉히는 래스터라 따로 본다(devlog).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import center_narration as CN
import common as C
import typeset as T

PENDING = os.path.join(C.GAME_DIR, "script", "center_pending.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def narr_line_off(ln):
    """`None`(빈 줄) 또는 하한을 넘은 여백 차(px) — 하한은 글자 폭이 반 칸의 홀수배면 6, 아니면 0."""
    body = ln.strip(CN.FW + " ")
    if not body:
        return None
    lead_h = round((T.cols(ln) - T.cols(body)) * 2)
    ink_h = round(CN.ink_cols(body) * 2)
    d = abs(2 * lead_h + ink_h - 50) * 6  # 중심 12.5칸 = 25 반 칸
    return max(0, d - (ink_h % 2) * 6)


def narration():
    """`(어긋남 [(열쇠, 줄)], 한계 줄 수 {종류: n})`."""
    manual = _load(CN.MANUAL) if os.path.exists(CN.MANUAL) else {}
    bad, limit = [], {"예산 한계 블록째 왼쪽": 0, "마스터 손 배치": 0}
    for name, i, budget in CN.targets():
        doc = _load(os.path.join(C.GAME_DIR, "script", name))
        kr = doc.get(str(i)) or doc.get("_wide", {}).get(str(i))
        if not isinstance(kr, str):
            continue
        key = f"{name[:-5]}#{i}"
        offs = [(ln, narr_line_off(ln)) for ln in kr.replace("\f", "\n").split("\n")]
        offs = [(ln, o) for ln, o in offs if o]
        if not offs:
            continue
        if key in manual:
            limit["마스터 손 배치"] += len(offs)
            continue
        _new, c = CN.fitted(kr, budget)
        if c != CN.CENTER:
            limit["예산 한계 블록째 왼쪽"] += len(offs)
            continue
        bad += [(key, ln.strip()) for ln, _o in offs]
    return bad, limit


def movies(mv=None, v2=None):
    import movie_hardsub as MH

    mv = mv if mv is not None else _load(MH.SCRIPT)
    v2 = MH.CENTER_V2 if v2 is None else v2
    bad = []
    for k, v in mv.items():
        if k.startswith("M") and isinstance(v, list) and k not in v2:
            for j, x in enumerate(v):
                bad += [
                    (f"{k}#{j}", ln)
                    for ln in x[-1].split("\n")
                    if ln.rstrip()[-1:] in MH.TAIL_PUNCT and ln.strip()
                ]
    return bad


def credits():
    import voice_credits as VC

    d = _load(os.path.join(C.GAME_DIR, "script", "voice_credits.json"))
    bad, hand = [], 0
    for s in d["subs"]:
        ls = VC.wrap(s["lines"])
        man = s.get("pads")
        ps = man if man is not None else VC.pads(ls)
        for t, n in zip(ls, ps, strict=True):
            if abs(VC.BUF_W - 2 * n * VC.HALF - VC._ink_w(t)) > VC.HALF:
                #   손 배치는 마스터 값, 자동 배치는 「줄 사이 가운데를 가장 긴 줄 기준 상대 반올림」(마스터 10-06 — 줄끼리 어긋남 ≤2px 가 우선) — 둘 다 고칠 수 없는 한계
                hand += 1
    return bad, hand


def controls():
    return [
        (
            "해설: 오른쪽으로 쏠린 줄",
            (narr_line_off("　　　　　　　　　안녕하세요 여러분") or 0) > 0,
        ),
        (
            "해설: 가운데 줄은 안 걸림",
            narr_line_off(CN.lead_for("안녕하세요 여러분") + "안녕하세요 여러분") == 0,
        ),
        ("영상: 부호 안 뺀 편의 줄 끝 부호", bool(movies({"M99": [[0, 1, "안녕하세요."]]}, set()))),
        ("영상: 부호 뺀 편은 안 걸림", not movies({"M99": [[0, 1, "안녕하세요."]]}, {"M99"})),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    ctl = controls()
    for n, ok in ctl:
        print(f"  양성 대조 {'✅' if ok else '🔴'} {n}")
    nb, limit = narration()
    mb = movies()
    cb, hand = credits()
    print(f"  해설·카드: 고칠 수 있는 어긋남 {len(nb)} 줄 · 한계 {limit}")
    print(f"  영상 자막: 부호 뺀 계산판이 아닌 편의 줄 끝 부호 줄 {len(mb)}")
    print(f"  음성 크레딧: 어긋남 {len(cb)} 줄 · 줄 사이 정렬 우선·손 배치로 4px 초과 {hand}")
    cur = {**limit, "크레딧 손 배치": hand}
    if a.freeze:
        with open(PENDING, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "_why": "2-8 한계 목록(줄 수) — 예산 한계·마스터 손 배치는 고칠 수 없다. 늘면 실패, 줄었을 때만 --freeze.",
                    "counts": cur,
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
            f.write("\n")
        return 0
    rc = 0
    if a.check:
        base = _load(PENDING)["counts"] if os.path.exists(PENDING) else {}
        if [n for n, ok in ctl if not ok]:
            print("  🔴 양성 대조 실패")
            rc = 1
        for name, lst in (("해설", nb), ("영상 자막", mb), ("음성 크레딧", cb)):
            if lst:
                print(f"  🔴 {name} 어긋남:", lst[:5])
                rc = 1
        for k, v in cur.items():
            if v > base.get(k, 0):
                print(f"  🔴 한계 목록 {k} 증가 {base.get(k, 0)}→{v}")
                rc = 1
        if rc == 0:
            print("  ✅ 2-8 가운데 맞춤 — 고칠 수 있는 어긋남 0 · 한계 목록 기준선 이하")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
