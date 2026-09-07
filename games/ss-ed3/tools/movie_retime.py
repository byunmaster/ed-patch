"""자막 싱크 보정 — **앞 침묵만큼 시작을 되민다**.

    python3 games/ss-ed3/tools/movie_retime.py --segments M04   # 보정한 마디표 (번역용)
    python3 games/ss-ed3/tools/movie_retime.py --nudge M04      # script/movie.json 갱신
    python3 games/ss-ed3/tools/movie_retime.py --nudge --all

🔴 **Whisper 는 마디를 앞쪽 침묵으로 늘려 잡는다.** 그래서 **말이 끊겼다 다시 시작하는 자리**
   에서 자막이 눈에 띄게 일찍 뜬다. 붙어 있는 대사에서는 거의 안 틀린다.
   실측(M01, 유저가 잡아낸 5 곳) — **전부 뒤로 밀어야** 했고, 앞 침묵이 길수록 많이 밀렸다:

       앞침묵 1.14s → +0.80    4.44s → +1.04    4.10s → +1.62
              2.34s → +1.18    0.04s → +0.56

   ⇒ `min(1.2, 0.25×앞침묵 + 0.5)` 로 근사하면 **평균 오차 1.04s → 0.25s**.
     `앞침묵 < 0.8s` 면 손대지 않는다(붙은 대사는 원래 맞다) — M01 에서 47 줄 중 15 줄만 움직인다.

⚠ **이건 「대체로 맞게」 만드는 자다. 사람 확인을 없애지는 못한다.**
   ⓘ 이 앞에 다른 자 둘을 시도했다가 버렸다 — 기록해 두니 다시 하지 말 것:
     · **글자 수 비례 배분** — 원문·번역의 글자 밀도가 구간마다 달라 오차가 누적된다.
       M01 전 줄이 +50~80 초씩 밀렸다.
     · **에너지/음성대역 온셋으로 검증** — 이 영상은 BGM 이 안 끊겨 기준선이 없다.
       0.8 초 기준으로 41 줄 중 26 줄이 걸려 깃발이 무의미했다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

SCRIPT = os.path.join(C.GAME_DIR, "script", "movie.json")
WORDS_DIR = os.path.join(C.REVIEW_DIR, "movie")
GAP_MIN = 0.8  # 이보다 짧게 붙어 있으면 안 건드린다
MAX_SHIFT = 1.2


def shift_for(gap):
    return 0.0 if gap < GAP_MIN else min(MAX_SHIFT, 0.25 * gap + 0.5)


def segments(movie):
    """`[(시작, 끝, 원문, 되민 시작)]` — 어절 파일을 읽어 보정값까지 붙인다."""
    p = os.path.join(WORDS_DIR, f"{movie}.words.json")
    if not os.path.exists(p):
        return None
    w = json.load(open(p, encoding="utf-8"))["segments"]
    out, prev_end = [], 0.0
    for s in w:
        gap = s["start"] - prev_end
        out.append((s["start"], s["end"], s["jp"], round(s["start"] + shift_for(gap), 2)))
        prev_end = s["end"]
    return out


def nudge(lines, segs):
    """이미 있는 자막 줄의 시작을, **가장 가까운 마디**의 보정값으로 옮긴다."""
    out = []
    for a, b, t in lines:
        near = min(segs, key=lambda s: abs(s[0] - a))
        if abs(near[0] - a) <= 0.6:  # 그 마디에서 온 줄일 때만
            d = near[3] - near[0]
            a, b = round(a + d, 2), round(b + d, 2)
        out.append([a, b, t])
    return out


TAIL = 0.40  # 말이 끝나고 자막이 남는 여유 (유저 확정 2026-09-02 — 방송 규약 0.3~0.5 의 가운데)
MIN_DUR = 0.80  # 아무리 짧은 대사라도 이만큼은 읽을 시간을 준다 (유저 확정 2026-09-01)
PER_CH = 0.055  # 글자당 더 주는 시간
GAP_JOIN = 0.6  # 마디 사이가 이보다 벌어지면 딴 소리로 보고 끊는다


def fit_ends(lines, segs, fixed=()):
    """**끝 시각을 실제 음성 길이에 맞춘다** → `(새 줄, 고친 수)`.

    🔴 종전엔 끝을 **다음 줄 시작**으로 뒀다. 그래서 말이 끝나고 침묵이 이어지는 자리에서
       자막이 다음 대사까지 계속 남았다(유저 실측 2026-09-01, M11).
    ⇒ 그 줄이 덮는 받아쓰기 마디의 **끝**에 여유(`TAIL`)를 붙인다.

    ⚠ **이어진 마디만 문다.** 창 안에서 제일 늦게 끝나는 마디를 잡으면 사이의 딴 소리까지
      물어 버린다(M11 「방방!」이 중간의 한숨 `はぁ…` 때문에 13.2 초까지 남았다).
      마디 사이가 `GAP_JOIN` 보다 벌어지면 거기서 끊는다.
    ⚠ 너무 짧으면 못 읽으니 **글자 수에 비례한 최소 노출**을 보장하되, 다음 줄 시작은
      절대 안 넘는다(겹치면 두 줄이 같이 뜬다).
    ⚠ 받아쓰기엔 **끝이 시작보다 앞인 쓰레기 마디**가 섞여 있다(M11 세그 4) — 걸러 낸다.

    🔴 **사람이 정한 자리는 안 건드린다** — `movie.json` 의 `_fixed[편] = [시작시각…]` 에
       적힌 줄은 그대로 둔다. 음성이 근거가 아닌 자막(타이틀 카드)이나, 이어지는 대사라
       일부러 다음 줄까지 끌어 둔 자리가 있다. 안 잠그면 다음 `--fit` 이 도로 뭉갠다.
       ⓘ 색인이 아니라 **시작 시각**으로 짚는다 — 줄을 갈라도 안 어긋난다.
    """
    ok = sorted((s0, e) for s0, e, *_ in segs if e > s0)
    out, n = [], 0
    for i, (a, b, t) in enumerate(lines):
        nxt = lines[i + 1][0] if i + 1 < len(lines) else b + 5.0
        if any(abs(a - f) < 0.05 for f in fixed):
            #   🔴 **잠긴 줄도 「읽을 시간」은 준다** — 시작은 사람이 정한 그대로 두고
            #     끝만 최소 노출까지 늘린다(유저 물음 2026-09-01: 「짧은 대답은
            #     좌우로 늘리나 뒤만 늘리나」). **뒤만 늘린다** — 시작을 당기면 말보다
            #     자막이 먼저 떠서 눈에 바로 띄지만, 끝이 늦는 건 거의 안 거슬린다.
            #     방송 자막 규약(BBC·Netflix)도 최소 노출을 **아웃점**으로 맞춘다.
            floor = a + max(MIN_DUR, PER_CH * len(t.replace("\n", "")))
            out.append([a, round(min(nxt, max(b, floor)), 2), t])
            continue
        #   그 줄에서 시작하는 마디 — 앞 침묵만큼 시작이 당겨져 있어 여유를 준다
        cand = [(s0, e) for s0, e in ok if e > a + 0.05 and s0 < nxt - 0.05]
        end = b
        if cand:
            speech = cand[0][1]
            for s0, e in cand[1:]:
                if s0 - speech > GAP_JOIN:
                    break
                speech = max(speech, e)
            floor = a + max(MIN_DUR, PER_CH * len(t.replace("\n", "")))
            end = min(nxt, max(speech + TAIL, floor))
        end = round(max(end, a + 0.3), 2)
        if abs(end - b) > 0.05:
            n += 1
        out.append([a, end, t])
    return out, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--segments", action="store_true", help="보정한 마디표를 찍는다")
    ap.add_argument("--nudge", action="store_true", help="script/movie.json 을 갱신한다")
    ap.add_argument("--fit", action="store_true", help="끝 시각을 음성 길이에 맞춘다")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    sc = json.load(open(SCRIPT, encoding="utf-8"))
    names = a.names or ([k for k in sorted(sc) if not k.startswith("_") and sc[k]] if a.all else [])
    if not names:
        ap.error("편 이름을 주거나 --all")
    if not (a.segments or a.nudge or a.fit):
        ap.error("--segments · --nudge · --fit 중 하나를 고른다")

    for m in names:
        segs = segments(m)
        if segs is None:
            print(f"  {m} 건너뜀 — 어절 파일이 없다 (`transcribe.py --words {m}`)")
            continue
        if a.segments:
            print(f"── {m}")
            for s, e, jp, ns in segs:
                mark = f"→{ns:7.2f}" if abs(ns - s) > 0.01 else "        "
                print(f"  [{s:7.2f}~{e:7.2f}]{mark}  {jp}")
        if a.fit:
            before = [tuple(x) for x in sc.get(m, [])]
            sc[m], n = fit_ends(before, segs, sc.get("_fixed", {}).get(m, []))
            long = sum(1 for x, y in zip(before, sc[m], strict=True) if x[1] - y[1] > 0.5)
            print(f"  {m}  끝 시각 {n}/{len(before)} 줄 조정 (그중 {long} 줄은 0.5s 넘게 줄었다)")
        if a.nudge:
            before = [tuple(x) for x in sc.get(m, [])]
            sc[m] = nudge(before, segs)
            n = sum(1 for x, y in zip(before, sc[m]) if abs(x[0] - y[0]) > 0.01)
            print(f"  {m}  {n}/{len(before)} 줄 되밈")
    if a.nudge or a.fit:
        json.dump(sc, open(SCRIPT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(SCRIPT, "a", encoding="utf-8").write("\n")
        print(f"→ {SCRIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
