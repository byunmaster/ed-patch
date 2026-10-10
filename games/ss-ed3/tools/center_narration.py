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


TAIL = ".,?!"  # 줄 끝 문장부호 — 반 칸이지만 잉크는 점 하나라 가운데를 재는 폭에 안 넣는다(마스터 10-06 「부호는 정렬에 영향을 안 준다」)


def ink_cols(body):
    """가운데 맞춤에 쓰는 폭(칸) — 줄 끝 부호는 뺀다."""
    return T.cols(body.rstrip(TAIL + " "))


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
    half = int((center - ink_cols(body) / 2) * 2 + 0.5)
    half = max(0, half)
    return FW * (half // 2) + (" " if half % 2 else "")


def recenter(text, center=CENTER):
    out = []
    for line in text.split("\n"):
        body = line.strip(FW + " ")
        out.append(lead_for(body, center) + body if body else line)
    return "\n".join(out)


def _mean_center(text):
    cs = []
    for ln in text.split("\n"):
        body = ln.strip(FW + " ")
        if body:
            cs.append((T.cols(ln) - T.cols(body)) + ink_cols(body) / 2)
    return sum(cs) / len(cs) if cs else CENTER


def balanced(text, budget):
    """**가장 긴 줄을 정확히 가운데에 두고**, 나머지 줄은 예산이 허락하는 만큼만 가운데로 당긴다 → `문안` 또는 `None`.

    🔴 앞 공백도 바이트다(반 칸 = 1B). 줄마다 가운데로 맞추면 **짧은 줄일수록 공백이 많이 든다** — 예산이 모자라면 종전엔 블록 전체를 왼쪽으로
    밀었다(가장 긴 줄도 가운데에서 빠졌다). 마스터 10-05 「원문도 정중앙이 아니면 최대한 정중앙에 — 가장 긴 문장을 가운데에 두고 그것을 기준으로」.
    ⇒ ① 가장 긴 줄의 앞 공백은 이상값(가운데) 그대로 ② 다른 줄은 그 줄과 **같은 시작점**(공백이 가장 적다)에서 출발해
    ③ 남는 바이트를 **가운데에서 가장 먼 줄부터** 한 칸(반 칸 = 1B)씩 나눠 준다(물채우기). 문안은 안 바꾼다.
    ⚠ ①만으로도 예산을 넘으면 `None` — 호출자가 옛 방식(블록째 왼쪽)으로 물러난다.
    """
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.strip(FW + " ")]
    if len(idx) < 3:
        return None
    body = {i: lines[i].strip(FW + " ") for i in idx}
    ideal = {i: max(0, int((CENTER - ink_cols(body[i]) / 2) * 2 + 0.5)) for i in idx}  # 반 칸 단위
    longest = max(idx, key=lambda i: (ink_cols(body[i]), -i))
    half = {i: ideal[longest] for i in idx}

    def build():
        out = list(lines)
        for i in idx:
            h = half[i]
            out[i] = FW * (h // 2) + (" " if h % 2 else "") + body[i]
        return "\n".join(out)

    spare = budget - T.body_bytes(build())
    if spare < 0:
        return None
    while spare > 0:
        i = max(idx, key=lambda i: (ideal[i] - half[i], -i))
        if ideal[i] - half[i] <= 0:
            break
        half[i] += 1
        spare -= 1
    return build()


def _devs(text):
    """줄마다 화면 중심에서 얼마나 벗어났나(칸) — 앞 공백 + 줄 폭/2 − 중심."""
    out = []
    for ln in text.split("\n"):
        body = ln.strip(FW + " ")
        if body:
            out.append((T.cols(ln) - T.cols(body)) + ink_cols(body) / 2 - CENTER)
    return out


def _score(text):
    """(줄 사이 들쭉날쭉 정도, 가장 큰 이탈) — 작을수록 좋다."""
    d = _devs(text)
    return (round(max(d) - min(d), 2), round(max(abs(x) for x in d), 2))


def fitted(text, budget):
    """예산 안에서 가장 보기 좋게 가운데 맞춘 배치 → `(문안, 중심)`.

    줄마다 가운데로 다 들어가면 그렇게 한다. 안 들어가면 **세 줄 이상**은 `balanced`(가장 긴 줄은 가운데 · 나머지는 예산껏)와
    **블록째 왼쪽**(줄끼리는 가운데 그대로) 중 **줄 사이 들쭉날쭉이 적은 쪽**(`balanced` 가 반 칸 이내면 그쪽)을 고른다 — 마스터 10-06 「블록들이 잘 안 맞는다」: `balanced` 는
    예산이 모자란 블록에서 가장 긴 줄만 가운데고 나머지가 1칸 가까이 왼쪽에 몰려 **한 블록 안에서 어긋나 보인다**. 한두 줄(제목 카드 등)은
    종전처럼 블록째 왼쪽이다(마스터: 한두 줄은 굳이 안 맞춰도 된다)."""
    new = recenter(text, CENTER)
    if T.body_bytes(new) <= budget:
        return new, CENTER
    shifted = None
    c = CENTER
    while c >= CENTER - 3:
        cand = recenter(text, c)
        if T.body_bytes(cand) <= budget:
            shifted = (cand, c)
            break
        c -= 0.5
    b = balanced(text, budget)
    if b is not None and (shifted is None or _score(b)[0] <= 0.5 or _score(b) < _score(shifted[0])):
        return b, round(_mean_center(b), 2)
    if shifted is not None:
        return shifted
    return recenter(text, c + 0.5), None


MANUAL = os.path.join(GAME, "narration_manual.json")


def apply_leads(text, leads):
    """줄마다 앞 공백(반 칸 단위)을 **손으로 준 값**으로 놓는다 — 빈 줄도 한 칸씩 센다(편집기의 줄 목록과 같다)."""
    k, pages = 0, []
    for pg in text.split("\f"):
        ls = pg.split("\n")
        tail = bool(ls) and ls[-1] == ""
        if tail:
            ls = ls[:-1]
        out = []
        for ln in ls:
            if k >= len(leads):
                raise ValueError(f"줄 수가 안 맞는다: 값 {len(leads)} 이 모자란다")
            h = leads[k]
            k += 1
            body = ln.strip(FW + " ")
            out.append(FW * (h // 2) + (" " if h % 2 else "") + body if body else ln)
        pages.append("\n".join(out) + ("\n" if tail else ""))
    if k != len(leads):
        raise ValueError(f"줄 수가 안 맞는다: 문안 {k} · 값 {len(leads)}")
    return "\f".join(pages)


def main():
    check = "--check" in sys.argv
    manual = json.load(open(MANUAL, encoding="utf-8")) if os.path.exists(MANUAL) else {}
    bad = changed = seen = 0
    known = {f"{n[:-5]}#{i}" for n, i, _ in targets()}
    for key in manual:
        if key not in known:
            bad += 1
            print(f"  ✗ {MANUAL} 의 {key} 는 가운데 정렬 대상 블록이 아니다")
    by_map = {}
    for name, i, budget in targets():
        by_map.setdefault(name, []).append((i, budget))
    for name, ids in by_map.items():
        p = os.path.join(GAME, "script", name)
        doc = json.load(open(p, encoding="utf-8"))
        dirty = False
        for i, budget in ids:
            #   🔴 `_wide` 블록은 **칸 안에 물리적으로 들어가는 대역**이 이 예산의 몫이다 — 진짜 문안(맵 꼬리)은 예산이 없다.
            holder = doc["_wide"] if str(i) in doc.get("_wide", {}) else doc
            kr = holder.get(str(i))
            if not isinstance(kr, str):
                continue
            seen += 1
            key = f"{name[:-5]}#{i}"
            if key in manual:  # 🔴 마스터가 편집기로 손수 맞춘 블록 — 자동 배치가 덮지 않는다(마스터 10-07)
                new, c = apply_leads(kr, manual[key]), CENTER
                if T.body_bytes(new) > budget:
                    bad += 1
                    print(f"  ✗ {name} #{i} 손 배치가 예산 {budget}B 를 넘는다({T.body_bytes(new)}B)")
            else:
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
                    holder[str(i)] = new
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
