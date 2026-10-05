"""가운데 정렬 나레이션(검은 바탕 문구 화면)을 **실제 렌더 폭** 기준 화면 중앙에 놓는다.

원문은 줄마다 앞에 전각 공백을 채워 가운데를 잡는다. 번역 때 그 공백을 **그대로 옮겨서**
우리 줄 폭과 안 맞아 들쭉날쭉했다(마스터 폰 실측 09-26, MAP061 엔딩 나레이션).
폭 모형은 조판기와 같다 — 전각 1칸 · 반각(ASCII) 0.5칸. 화면 중심은 12.5칸
(원문 줄 중심들의 가운데이자 캡처 실측 중심).

    python3 games/ss-ed3/tools/center_narration.py          # 고쳐 쓴다
    python3 games/ss-ed3/tools/center_narration.py --check  # 게이트: 어긋난 줄이 있으면 실패

대상은 원문 블록의 첫 줄이 전각 공백으로 시작하고 들여쓰지 않은 줄이 하나 이하인 2줄 이상 블록과,
전각 공백 셋 이상으로 시작하는 한 줄 카드(장 제목·「며칠 뒤」)다
(편지 서명처럼 첫 줄이 붙어 있는 건 배치가 의도라 건드리지 않는다).

⚠ 앞 공백도 바이트다(길이 보존 예산). 예산을 넘는 블록은 **블록 전체를 반 칸씩 왼쪽으로**
옮겨 맞춘다 — 줄끼리의 가운데는 그대로라 들쭉날쭉하지 않다. 옮긴 블록은 출력에 적는다.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import typeset as T

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENTER = 12.5
FW = "　"


def targets():
    for f in sorted(glob.glob(os.path.join(GAME, "work/derived/map_jp/MAP*.json"))):
        name = os.path.basename(f)
        jp = json.load(open(f, encoding="utf-8"))["blocks"]
        for i, b in enumerate(jp):
            ls = [x for x in b["text"].split("\n") if x.strip(FW + " ")]
            #   화면 폭을 꽉 채운 줄은 원문도 앞 공백이 없다(MAP038 #70) — 한 줄까지는 봐준다
            multi = (
                len(ls) >= 2
                and ls[0].startswith(FW)
                and sum(x.startswith(FW) for x in ls) >= len(ls) - 1
            )
            card = len(ls) == 1 and ls[0].startswith(FW * 3)
            if multi or card:
                yield name, i, T.body_bytes(b["text"])


def lead_for(body, center=CENTER):
    half = int((center - T.cols(body) / 2) * 2 + 0.5)
    half = max(0, half)
    return FW * (half // 2) + (" " if half % 2 else "")


def recenter(text, center=CENTER):
    out = []
    for line in text.split("\n"):
        body = line.strip(FW + " ")
        out.append(lead_for(body, center) + body if body else line)
    return "\n".join(out)


def fitted(text, budget):
    """예산 안에서 가장 화면 중앙에 가까운 배치 → `(문안, 중심)`."""
    c = CENTER
    while c >= CENTER - 3:
        new = recenter(text, c)
        if T.body_bytes(new) <= budget:
            return new, c
        c -= 0.5
    return recenter(text, c + 0.5), None


def main():
    check = "--check" in sys.argv
    bad = changed = seen = 0
    by_map = {}
    for name, i, budget in targets():
        by_map.setdefault(name, []).append((i, budget))
    for name, ids in by_map.items():
        p = os.path.join(GAME, "script", name)
        doc = json.load(open(p, encoding="utf-8"))
        dirty = False
        for i, budget in ids:
            kr = doc.get(str(i))
            if not isinstance(kr, str):
                continue
            seen += 1
            new, c = fitted(kr, budget)
            if c is None:
                bad += 1
                print(f"  ✗ {name} #{i} 예산 {budget}B — 옮겨도 안 들어간다(문안을 줄여야 한다)")
            elif c != CENTER:
                print(f"  ⓘ {name} #{i} 예산이 빠듯해 블록째 {CENTER - c:g}칸 왼쪽")
            if new != kr:
                if check:
                    bad += 1
                    print(f"  ✗ {name} #{i} 가운데가 어긋난 줄이 있다")
                else:
                    doc[str(i)] = new
                    dirty = True
                    changed += 1
        if dirty:
            json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            open(p, "a", encoding="utf-8").write("\n")
    if check:
        print(f"  나레이션 가운데 정렬: {seen}블록 중 어긋남 {bad}")
        sys.exit(1 if bad else 0)
    print(f"나레이션 {seen}블록 중 {changed}블록 다시 가운데 맞춤 (중심 {CENTER}칸)")


if __name__ == "__main__":
    main()
