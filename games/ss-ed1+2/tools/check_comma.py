"""쉼표는 한국식으로 — 번역 규칙 2-13 「뺀다」 부류를 굽는 문안에서 센다.

    python3 tools/check_comma.py            # 표 + 기준선 대조 (실패 부류가 늘면 종료코드 1)
    python3 tools/check_comma.py --show 8   # 부류마다 표본

규칙 행 전문을 따른다 — **남긴다**: 부르는 말 뒤 · 감탄·응답 뒤 · 나열 · 앞 절이 길어 쉼이 꼭 필요한 곳 · 경계 사례 ①~⑧.
**뺀다**: 주어·주제 뒤 · 부사어 뒤 · 짧은 연결 어미 뒤 · 줄 끝이라 줄바꿈이 이미 쉼을 주는 곳 · ⑨ `~는데,` `~지만,` `~만,` 앞 절 11음절 이하.

## 실패(0 이어야 하는 것 — 규칙 예시와 꼴이 똑같다)

    ⑨ 쉼표 규칙이 더 뺄 것   `patch_scn.comma_rule` 을 굽는 문안에 다시 걸면 바뀐다 (빌드가 이미 건다 — 어긋나면 어느 경로가 샜다)
    주제 뒤 쉼표             두 음절 이상 낱말 + 은/는 + `,`  (`파렌 왕국은,`)
    부사어 뒤 쉼표           문장 맨 앞 `~에는,` `~에서는,` `~로는,` `실은,`  (`처음에는,`)

## 보고 전용(애매 — 부류와 수만 둔다, 마스터 판정 몫)

    접속 「그럼,」           접속(그러면)인지 응답인지 용법이 갈린다
    연결 어미 줄끝           줄 끝에 놓인 `~고,` `~서,` `~는데,`… — 줄바꿈이 쉼을 주는 자리지만 ⑨ 의 「긴 앞 절은 남김」과 겹친다
    연결 어미(고·며·서)      짧은 앞 절 뒤 `~고,` `~며,` `~서,` — 「짧은」의 기준(11음절?)이 규칙에 없다
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn
from check_oneline import built_blocks

BASELINE = os.path.join(common.GAME_DIR, "comma_baseline.json")
FAIL = ("⑨ 쉼표 규칙이 더 뺄 것", "주제 뒤 쉼표", "부사어 뒤 쉼표")
REPORT = ("접속 그럼", "연결 어미 줄끝", "연결 어미(고·며·서)")
_TOPIC = re.compile(r"(?<![가-힣])[가-힣]{2,}[은는],(?=[\s%]|$)")
_ADV = re.compile(
    r"(?:^|(?<=[\n%])|(?<=[.!?…] ))(?:[가-힣]+(?:에서는|에는|으로는|로는|에게는|한테는)|실은|사실은),(?=[ \n%])"
)
_THEN = re.compile(r"(?:^|(?<=[\s\n%]))그럼,")
_ENDLINE = re.compile(
    r"[가-힣](?:고|며|[아어여해라러]서|으니|는데|인데|[은ㄴ]데|지만|면서|다가|거나|려고|도록|[가-힣]면|[가-힣]만),\n"
)
_SHORT = re.compile(r"[가-힣](?:(?<!아이)(?<!뭐라)(?<!뭔)(?<!말)고|며|[아어여해라러]서),(?=[ \n%])")  # 감탄 「아이고,」 · 되묻는 「뭐라고,」 는 남기는 부류


def corpus():
    """`[(꼬리표, 굽는 문안)]` — 씬 대사 · 메시지 · 자막. 쪽 구분(`\\x08`)은 `%c` 로 눕힌다."""
    out = [(t, b.replace("\x08", "%c")) for t, b in built_blocks()]
    out += [(f"메시지 {k[:6]}", v) for k, v in common.sys_lines().items()]
    with open(os.path.join(common.GAME_DIR, "script", "title.json"), encoding="utf-8") as f:
        out += [(f"자막 {k}:{i}", ln) for k, v in json.load(f).items() for i, ln in enumerate(v)]
    return out


def _is_parallel(flat, comma_at):
    """`flat[comma_at]` 의 쉼표가 대구(`치안도 좋고, 세금도 싸고`)인가 — `patch_scn._parallel` 과 같은 판별."""
    cut = 0
    for b in patch_scn._BOUNDARY.finditer(flat, 0, comma_at):
        cut = b.end()
    return patch_scn._parallel(flat[cut:comma_at], flat[comma_at + 1 :])


def classify(tag, text):
    """한 문안 → `{부류: [표본]}`."""
    out = collections.defaultdict(list)
    flat = text.replace("\n", " ")
    if patch_scn.comma_rule(flat) != flat:
        out["⑨ 쉼표 규칙이 더 뺄 것"].append(flat[:40])
    for m in _TOPIC.finditer(text):
        out["주제 뒤 쉼표"].append(text[max(0, m.start() - 6) : m.end() + 6].replace("\n", "⏎"))
    for m in _ADV.finditer(text):
        out["부사어 뒤 쉼표"].append(text[max(0, m.start() - 6) : m.end() + 8].replace("\n", "⏎"))
    for m in _THEN.finditer(text):
        out["접속 그럼"].append(text[max(0, m.start() - 6) : m.end() + 10].replace("\n", "⏎"))
    for m in _ENDLINE.finditer(text):
        if _is_parallel(flat, m.end() - 2):  # 대구(규칙 2-13 ⑪ — 마스터 11-05·11-06)는 남기는 쉼표라 센다 안 센다
            continue
        out["연결 어미 줄끝"].append(text[max(0, m.start() - 6) : m.end() + 6].replace("\n", "⏎"))
    for m in _SHORT.finditer(flat):
        cut = 0
        for b in patch_scn._BOUNDARY.finditer(flat, 0, m.start()):
            cut = b.end()
        if patch_scn.read_syllables(flat[cut : m.end() - 1]) <= 11 and not patch_scn._parallel(flat[cut : m.end() - 1], flat[m.end() :]):
            out["연결 어미(고·며·서)"].append(flat[max(0, m.start() - 8) : m.end() + 6])
    return out


def scan():
    docs = corpus()
    hits = collections.defaultdict(list)
    for tag, text in docs:
        for k, v in classify(tag, text).items():
            hits[k] += [(tag, x) for x in v]
    return len(docs), hits


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    n, hits = scan()
    cur = {k: len(hits.get(k, ())) for k in FAIL + REPORT}
    print(
        f"  쉼표 2-13 [문안 {n:,}] — "
        + " · ".join(f"{k} {cur[k]}" for k in FAIL)
        + "  (보고: "
        + " · ".join(f"{k} {cur[k]}" for k in REPORT)
        + ")"
    )
    for k in FAIL + REPORT:
        for tag, x in hits.get(k, ())[:show]:
            print(f"      [{k}] {tag}: {x!r}")
    if "--freeze" in sys.argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"  ✍ 기준선 갱신 {cur}")
        return 0
    try:
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    except OSError:
        print("  ⚠ 기준선 없음 — `--freeze` 로 만든다 (안 쟀다는 통과가 아니다)")
        return 1
    bad = [k for k in FAIL if cur[k] > 0]
    worse = {k: (base.get(k, 0), cur[k]) for k in REPORT if cur[k] > base.get(k, 0)}
    if bad:
        print("  🔴 뺄 쉼표가 남았다 — " + " · ".join(f"{k} {cur[k]}" for k in bad))
        return 1
    if worse:
        print("  🔴 보고 부류가 기준선보다 늘었다 — " + " · ".join(f"{k} {a}→{b}" for k, (a, b) in worse.items()))
        return 1
    print("  ✅ 쉼표 — 뺄 부류 0 · 보고 부류는 기준선 이하")
    return 0


if __name__ == "__main__":
    sys.exit(main())
