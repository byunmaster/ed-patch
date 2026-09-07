"""역번역 대조 — **ss-ed3 어댑터**. 엔진은 `shared/text/backtrans.py` 다.

    python3 games/ss-ed3/tools/backtrans.py            # 옮긴 것 전량 (열쇠 필요)
    python3 games/ss-ed3/tools/backtrans.py MAP001     # 그 맵만
    python3 games/ss-ed3/tools/backtrans.py --report   # 캐시만으로 다시 본다
    python3 games/ss-ed3/tools/backtrans.py --report --worst 40

여기서 하는 일은 둘뿐이다 — **어디서 블록을 긁는가**와 **무엇을 보여 주는가**.
되돌리기·캐시·점수는 공용 엔진이 한다(`spellcheck.py` 와 같은 경계).

⚠ 나가는 것은 우리 문안뿐이다 — 원문은 보내지 않고 대조는 이쪽에서 한다.
⚠ 점수는 순위로 읽는다 — 사투리·조사 회피·길이 줄이기도 점수를 깎는다.
⚠ 게이트에는 안 물린다: 망이 드는 검사를 `check.sh` 에 넣으면 끊긴 자리에서 늘 빨간불이다.
"""

EPILOG = """열쇠는 `.local/secrets.env` 하나에 모은다(환경변수가 이긴다):

  DEEPL_API_KEY=...    # https://www.deepl.com/pro-api 의 DeepL API Free — 월 50만 자

⚠ 워크트리엔 `.local/` 이 안 따라온다 — 메인 트리에 한 번만 두면 거슬러 올라가 찾는다.
자세한 것은 `.local/README.md`."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import common as C
import mapfile as M
import reinsert as R
import typeset as T

from shared.text import backtrans as B

CACHE = os.path.join(C.REVIEW_DIR, "backtrans_cache.json")
MIN_JP, MIN_KO = 6, 4  # 이름표·짧은 맞장구는 볼 것이 없다


def collect(stems):
    """`[(키, 원문, 우리 문안)]` — 옮긴 블록 전부. 키는 `MAP012:37`."""
    out = []
    maps = {}
    for disc in (1, 2):
        with C.open_disc(disc) as d:
            for n, lba, size in sorted(d.files()):
                if not (n.startswith("/MAP/") and n.endswith(".BIN")):
                    continue
                stem = os.path.basename(n)[:-4]
                if stem not in maps:
                    maps[stem] = M.blocks(d.read_extent(lba, size))
    for stem in sorted(maps):
        if stems and stem not in stems:
            continue
        kr, _ = R.load_script(stem)
        bl = maps[stem]
        for k, v in sorted(kr.items(), key=lambda x: int(x[0])):
            i = int(k)
            if not 0 <= i < len(bl):
                continue
            jp = B.flatten(T.visible(M.text_of(bl[i]["body"])))
            ko = B.flatten(T.visible(v))
            if len(jp) >= MIN_JP and len(ko) >= MIN_KO:
                out.append((f"{stem}:{k}", jp, ko))
    return out


def main():
    ap = argparse.ArgumentParser(
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--report", action="store_true", help="되돌리지 않고 캐시만으로 본다")
    ap.add_argument("--worst", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0, help="이만큼만 되돌린다(시험용)")
    ap.add_argument("--short", action="store_true", help="짧아서 점수를 못 믿는 것만 본다")
    ap.add_argument(
        "--min", type=int, default=0, help="원문이 이 글자 이상인 것만 (긴 문장에 오역이 숨는다)"
    )
    a = ap.parse_args()

    pairs = collect(a.stems)
    cache = B.load_cache(CACHE)
    todo = [p for p in pairs if p[2] not in cache]
    if a.limit:
        todo = todo[: a.limit]

    if todo and not a.report:
        key = C.need_secret(
            "DEEPL_API_KEY", "https://www.deepl.com/pro-api 의 **DeepL API Free** — 월 50만 자"
        )
        chars = sum(len(p[2]) for p in todo)
        print(f"되돌릴 것 {len(todo)} 블록 · {chars:,}자 (캐시 {len(cache)})")

        def tick(done, total):
            B.save_cache(CACHE, cache)
            print(f"  {done}/{total}")

        B.fetch(todo, cache, key, "KO", "JA", on_save=tick)
        B.save_cache(CACHE, cache)

    # 🔴 짧은 문장은 표기 하나에 점수가 흔들린다(`乾杯～` = 0.00) — 갈라서 본다.
    scored = B.rank(pairs, cache, drop_short=not a.short)
    if a.short:
        scored = [x for x in scored if B.is_short(x[2], x[4])]
    if a.min:
        scored = [x for x in scored if len(x[2]) >= a.min]
    if not scored:
        print("대조할 것이 없다 — `--report` 를 빼고 한 번 돌린다")
        return
    print(f"\n대조 {len(scored)} 블록 · 어긋난 순 {min(a.worst, len(scored))} 개")
    print("⚠ 점수는 순위로 읽는다 — 낮다고 오역은 아니다(사투리·조사 회피·길이 줄이기도 깎인다)\n")
    for sim, k, jp, ko, back in scored[: a.worst]:
        print(f"  [{sim:.2f}] {k}")
        print(f"    원문   {jp[:58]}")
        print(f"    우리   {ko[:58]}")
        print(f"    되돌림 {back[:58]}")
    lo = sum(1 for x in scored if x[0] < 0.35)
    print(f"\n0.35 미만 {lo} · 중앙값 {scored[len(scored) // 2][0]:.2f}")
    if not a.short:
        n_short = sum(1 for k, jp, ko in pairs if ko in cache and B.is_short(jp, cache[ko]))
        print(f"⚠ 짧아서 뺀 것 {n_short} — 보려면 `--short`")


if __name__ == "__main__":
    main()
