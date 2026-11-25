"""줄·쪽 나눔 지표 — 공통 번역 규칙 2-16 을 **조판 결과**(`typeset.pages`)의 전량 계수로 본다(사람·에이전트 눈이 아니라 기계 지표, 마스터 10-26).

    python3 tools/linebreak_metrics.py [--list]     # 지표 a/b/c/d (+e) 를 센다. --list 는 열쇠를 찍는다
    python3 tools/linebreak_metrics.py --check      # 기준선(`linebreak_baseline.json`)보다 늘면 실패 · 줄면 알린다(래칫)
    python3 tools/linebreak_metrics.py --freeze     # 기준선을 지금 값으로 내린다(줄었을 때만)

지표(단위 = 번역 단위 하나, 센 것은 쪽 · 줄 · 낱말 하나 단위가 아니라 **단위 수**):
  a  쪽 끝 한 어절 고아 쪽 — 둘 이상의 쪽으로 나뉜 조각의 **마지막 쪽이 한 줄·한 어절**이고 앞 쪽이 문장 끝으로 안 끝난다(문장 꼬리 낱말 하나가 쪽을 차지한다. 혼자 선 한 어절 문장 쪽은 아니다)
  b  문장 중간 한 낱말로 끝나는 쪽 — 쪽의 **끝 줄이 한 어절**인데 문장이 다음 쪽에서 이어진다
  c  문장 중간 손 개행 — 정본 문안의 `\\n` 이 문장 한가운데에 있고 조판기가 공백으로 못 읽었다(장 끝 카드·이름 머리 줄은 제외 · 읽기 전 값은 devlog)
  d  절째 내리면 들어가는데 쪼갠 줄 — 줄이 넘쳐 한 절(문장 끝 > 쉼표 > 연결어미 경계)이 둘 줄에 걸렸는데
     그 절이 다음 줄에 통째로 들어간다(경계 앞에 `typeset.MIN_LEFT_PX` 이상 남을 때)
  f  퇴행 — 규칙이 새로 만든 나쁜 끊김(보조용언·의존명사·관형사 고아 등 `krwrap.split_reason` 에 걸리는 새 줄 끝, 전에 한 줄이던 문장이 갈림). 래칫 0
  h  창 분배 — 마지막 창이 문장 꼬리 한 어절(a 의 마지막 조각판) · h2 같은 문장이 이어지는 창끼리 줄 수 차 ≥ 2
  g  넘침 — 계획한 줄이 런타임 줄넘김 모델(`typeset_check.wrap`)이 실제로 나눌 줄과 다른 쪽(13칸에 닿은 줄 끝 어절이 다음 줄 첫 어절과 붙어 어절째 내려감) 래칫 0
  i  쪽 경계가 문장 끝·절 경계가 아님 — 쪽이 문장 중간에서 끝나는데 그 경계(끝 어절｜다음 쪽 첫 어절)가 쉼표·연결어미가 아니거나 이음이 갈린다(꾸밈말·목적어·주어 뒤 — 규칙 2-16 「쪽 경계는 문장 끝·절 경계만」, 마스터 10-26·10-28 시녀 창).
     개수는 경계(쪽 사이) 수다. 한 낱말로 끝나는 쪽(b)과 겹쳐 센다.
  e  띄어 쓴 고유명사(정본 이름)와 [명사+명사] 굳은 구(같은 이음이 대사 전량에 2회 이상 · 앞 어절이 조사·어미·관형형·부사가 아님)가 줄·쪽 사이에서 갈린 자리 수(규칙 2-16 ④)

쪽 끝 판정의 「문장이 이어진다」는 끝 줄이 문장 끝 부호(`. ! ? … ~ 」 』`)로 안 끝남을 뜻한다.
강제 쪽(`\\f`) 앞뒤는 번역자가 정한 쪽이라 a·b 에서 따로 센다(`forced`) — 조판기가 못 고친다.
"""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset

BASELINE = common.GAME_DIR / "linebreak_baseline.json"
KEYS = ("a", "b", "c", "d", "e", "f", "g", "h", "h2", "i")


def _is_fixed_layout(t: str) -> bool:
    """손으로 줄을 짠 창(장 끝 카드 · 화자/줄 계획) — 지표 c 에서 뺀다(조판기가 줄을 그대로 둔다)."""
    return any(not x or x[0] in " 　" for x in t.split("\n"))


def units():
    """(씬 파일명, 열쇠, 정본 문안 t) — 입장 배너(raw)와 빈 문안은 뺀다."""
    for p in sorted((common.GAME_DIR / "script").glob("scn*.json")):
        for k, v in M.load_translations(int(p.stem[3:])).items():
            t = v.get("t", "")
            if t and not v.get("raw"):
                yield p.stem, k, t


def measure_unit(t: str, scn: int | None = None) -> dict[str, int]:
    """한 단위의 지표(0/1 또는 개수) — 조판은 빌드와 같은 `typeset.pages`(화자 있음으로 짠다, 더 엄한 쪽)."""
    r = dict.fromkeys(KEYS, 0)
    src = font.expand_packed(t)
    for chunk in t.split("\f"):  # 조판기가 읽은 뒤에도 남은 문장 중간 손 개행(이름 머리 줄은 뺀다)
        if "\n" not in chunk or _is_fixed_layout(chunk):
            continue
        used, header = typeset.soften_chunk(chunk)
        ls = used.split("\n")[1 if header is not None else 0 :]
        r["c"] += sum(1 for ln in ls[:-1] if not typeset.ends_sentence(ln))
    bounds: list[int] = []
    typeset.set_scene(scn)
    pgs = typeset.pages(src, speaker="nl", _bounds=bounds)
    for ci, lo in enumerate(
        bounds
    ):  # 강제 쪽(`\\f`) 조각마다 — 조각 안의 쪽 끝만 본다(조각 사이는 번역자가 정한 쪽)
        hi = bounds[ci + 1] if ci + 1 < len(bounds) else len(pgs)
        ch = pgs[lo:hi]
        if len(ch) < 2:
            continue
        for i, pg in enumerate(ch):
            if not pg or isinstance(pg, typeset.Card):
                continue
            last = pg[-1]
            one_word = " " not in last
            if i == len(ch) - 1:
                if len(pg) == 1 and one_word and not typeset.ends_sentence(ch[i - 1][-1]):
                    r["a"] += 1
            elif one_word and not typeset.ends_sentence(last):
                r["b"] += 1
            if i < len(ch) - 1 and ch[i + 1] and not typeset.ends_sentence(last):
                if not typeset.page_edge_ok(last.rsplit(" ", 1)[-1], ch[i + 1][0].split(" ", 1)[0]):
                    r["i"] += 1
    # h·h2 — 창 분배(마스터 10-26): h 마지막 창이 문장 꼬리 한 어절(마지막 조각만) · h2 같은 문장이 이어지는 창끼리 줄 수 차가 2 이상(창 수를 안 늘려도 고를 수 있다)
    if bounds:
        ch = pgs[bounds[-1] :]
        if (
            len(ch) >= 2
            and len(ch[-1]) == 1
            and " " not in ch[-1][0]
            and not typeset.ends_sentence(ch[-2][-1])
        ):
            r["h"] += 1
    uneven = False
    for ci, lo in enumerate(bounds):
        hi = bounds[ci + 1] if ci + 1 < len(bounds) else len(pgs)
        ch = pgs[lo:hi]
        uneven |= any(
            not typeset.ends_sentence(x[-1]) and abs(len(x) - len(y)) >= 2
            for x, y in itertools.pairwise(ch)
            if x and y and not isinstance(x, typeset.Card)
        )
    r["h2"] += int(uneven)
    # g — 계획한 줄이 런타임 줄넘김 모델과 다른 쪽(넘침) — 단위 안 쪽 수
    r["g"] += sum(
        1 for pg in pgs if pg and not isinstance(pg, typeset.Card) and not typeset.runtime_ok(pg)
    )
    # f — 규칙이 새로 만든 나쁜 끊김·쪽 경계(전 = 규칙 끔)
    prev, typeset.RULE_2_16 = typeset.RULE_2_16, False
    try:
        before = [pg for pg in typeset.pages(src, speaker="nl") if not isinstance(pg, typeset.Card)]
    finally:
        typeset.RULE_2_16 = prev
    after = [pg for pg in pgs if not isinstance(pg, typeset.Card)]
    r["f"] += typeset.regressions(before, after)
    # 줄 쌍 — d, e
    flat = [ln for pg in pgs if not isinstance(pg, typeset.Card) for ln in pg]
    r["d"] += typeset.clause_splits(flat)
    r["e"] += typeset.glued_splits(flat)
    return r


def measure() -> tuple[dict[str, int], dict[str, list[str]]]:
    total = dict.fromkeys(KEYS, 0)
    where: dict[str, list[str]] = {k: [] for k in KEYS}
    for scn, key, t in units():
        m = measure_unit(t, int(scn[3:]))
        for k in KEYS:
            if m[k]:
                total[k] += m[k]
                where[k].append(f"{scn}:{key}")
    return total, where


def main(argv: list[str]) -> int:
    total, where = measure()
    print("  ".join(f"{k}={total[k]}" for k in KEYS))
    if "--list" in argv:
        for k in KEYS:
            print(k, " ".join(where[k]))
    base = json.loads(BASELINE.read_text("utf-8")) if BASELINE.exists() else None
    if "--freeze" in argv:
        if base and any(k in base and total[k] > base[k] for k in KEYS):  # 새 지표(기준선에 없는 키)는 처음 얼릴 때 통과
            print("기준선보다 늘었다 — 얼리지 않는다")
            return 1
        BASELINE.write_text(json.dumps(total, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("기준선 갱신:", total)
        return 0
    if "--check" in argv:
        if base is None:
            print("기준선이 없다 — --freeze 로 만든다")
            return 1
        worse = {k: (base.get(k, 0), total[k]) for k in KEYS if total[k] > base.get(k, 0)}
        if worse:
            print("❌ 줄·쪽 나눔 지표가 기준선보다 늘었다(2-16):", worse)
            return 1
        better = {k: (base[k], total[k]) for k in KEYS if k in base and total[k] < base[k]}
        if better:
            print("✅ 기준선보다 줄었다 — --freeze 로 내린다:", better)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
