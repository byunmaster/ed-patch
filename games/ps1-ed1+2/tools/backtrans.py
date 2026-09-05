#!/usr/bin/env python3
"""역번역 대조 — **ps1-ed1+2 어댑터**. 엔진은 `shared/text/backtrans.py` 다.

    python3 games/ps1-ed1+2/tools/backtrans.py                # 옮긴 것 전량 (열쇠 필요)
    python3 games/ps1-ed1+2/tools/backtrans.py ED1SCN3        # 그 씬만
    python3 games/ps1-ed1+2/tools/backtrans.py --limit 300    # 300블록만 되돌린다(시험)
    python3 games/ps1-ed1+2/tools/backtrans.py --report       # 캐시만으로 다시 본다
    python3 games/ps1-ed1+2/tools/backtrans.py --report --worst 40 --min 20

여기서 하는 일은 둘뿐이다 — **어디서 블록을 긁는가**와 **무엇을 보여 주는가**.
되돌리기·캐시·점수는 공용 엔진이 한다(`spellcheck_ours.py` 와 같은 경계).

⚠ **나가는 것은 우리 문안뿐이다** — 원문(팔콤 일문)은 보내지 않고 대조는 이쪽에서 한다.
⚠ **게이트에 안 물린다** — 망이 드는 검사를 `check.sh` 에 넣으면 끊긴 자리에서 늘 빨간불이다.
⚠ 점수는 **순위로 읽는다.** 우리가 일부러 바꾼 자리도 깎인다 — 이 게임에선 특히
  사투리(`-구먼유`·`-뎁쇼`)·조사 병기(`을(를)`)·이름 주입(`%s`)·이스터에그가 그렇다.

🔴 **이 게임의 문안엔 화면 제어물이 섞여 있다** — 그대로 보내면 번역기가 헛것을 본다.
  `{n}`·`{p}`(줄바꿈·창 넘김) · `\\x1a`(이름 주입) · `\\x17`(아이템 주입) · `\\x1b`(수치) ·
  `\\ue000`(하드 개행). 보내기 전에 지운다(`strip_ctrl`).
"""

EPILOG = """열쇠는 `.local/secrets.env` 하나에 모은다(환경변수가 이긴다):

  DEEPL_API_KEY=...    # https://www.deepl.com/pro-api 의 DeepL API Free — 월 50만 자

⚠ 워크트리엔 `.local/` 이 안 따라온다 — 메인 트리에 한 번만 두면 거슬러 올라가 찾는다.
⚠ 전량은 44만 자쯤이라 무료 한도(월 50만)를 거의 다 쓴다. `--limit` 로 나눠 도는 게 낫다.
자세한 것은 `.local/README.md`."""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import common as C

from shared.text import backtrans as B

CACHE = os.path.join(C.REVIEW_DIR, "backtrans_cache.json")
MIN_JP, MIN_KO = 8, 5  # 이름표·짧은 맞장구는 볼 것이 없다

# 화면 제어물 — 번역기에 보내기 전에 지운다. 조사 병기 `을(를)` 은 **앞을 남긴다**
# (`을(를)` → `을`): 괄호째 보내면 번역기가 괄호를 뜻으로 읽는다.
_CTRL = re.compile(r"\{[np]\}|[\x17\x1a\x1b-]")
_BYEONGGI = re.compile(r"(은|는|이|가|을|를|와|과|으로|로)\((?:은|는|이|가|을|를|와|과|으로|로)\)")


def strip_ctrl(s):
    s = _BYEONGGI.sub(r"\1", s)
    return B.flatten(_CTRL.sub(" ", s))


# 🔴 **원문의 화자 이름표를 떼고 넣는다.** `{c}ライアス{c}` 가 붙은 채로 대조하면 우리 문안엔
# 없는 이름이 원문에만 남아 **점수가 통째로 깎인다** — 이름창은 우리 쪽에서 `s` 로 빠져 있다.
_JP_HEAD = re.compile(r"^\{c\}[^{]{0,12}\{c\}")
# ⚠ 파생 원문은 `!`·`?` 를 **`\x21`·`\x3F` 라는 여섯 글자 그대로** 들고 있다. 안 풀면 짧은
#   대사가 길어 보여 `--min`·`is_short` 을 통과하고, 글자 대조 점수도 통째로 흔들린다
#   (`こけっ～ \x21\x3F` 가 0.00 으로 최악 목록을 채웠다 — 실측 2026-08-26).
_JP_ESC = re.compile(r"\\x([0-9A-Fa-f]{2})")


def _strip_jp(s):
    s = _JP_ESC.sub(lambda m: chr(int(m.group(1), 16)), s)
    return re.sub(r"\{[cnp]\}", " ", _JP_HEAD.sub("", s))


# 🔴 **원문이 텍스트가 아닌 블록이 섞여 있다.** 추출기가 포인터 표를 대사로 잡은 자리로,
# `¬æôæ4ç|çÈç…` 처럼 일본어가 아니다(전 씬 84블록 실측 2026-08-27). 그대로 두면 최악
# 목록을 통째로 점령한다 — 우리 문안은 멀쩡한데 대조 상대가 쓰레기라 점수가 0 이 된다.
_JP_CH = re.compile(r"[ぁ-んァ-ヶ一-龠ー、。！？]")


def looks_japanese(s, floor=0.5):
    return s and sum(1 for c in s if _JP_CH.match(c)) / len(s) >= floor


def collect(scenes):
    """`[(키, 원문, 우리 문안)]` — 번역 정본이 있는 블록 전부. 키는 `ED1SCN3:152`."""
    out = []
    for f in sorted(glob.glob(os.path.join(C.ROOT, "script", "ED*SCN*.json"))):
        scn = os.path.basename(f)[:-5]
        if scenes and scn not in scenes:
            continue
        jf = os.path.join(C.OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jf):
            continue
        with open(jf, encoding="utf-8") as h:
            jp = {e["entry_id"]: (e.get("text") or "") for e in json.load(h)["entries"]}
        with open(f, encoding="utf-8") as h:
            d = json.load(h)
        for k, v in sorted(d.items(), key=lambda x: int(x[0])):
            if not isinstance(v, dict) or not v.get("t"):
                continue
            src = strip_ctrl(_strip_jp(jp.get(int(k), "")))
            ko = strip_ctrl(v["t"])
            if len(src) >= MIN_JP and len(ko) >= MIN_KO and looks_japanese(src):
                out.append((f"{scn}:{k}", src, ko))
    return out


def semantic(scored, batch=256):
    """`[(뜻점수, 글자점수, 키, 원문, 우리, 되돌림)]` — **뜻이 어긋난 순**.

    🔴 **글자 유사도만으로는 이 코퍼스에서 못 쓴다.** 되돌린 일본어는 기계번역이라
    **표준 정중체**로 나오는데 원문은 팔콤의 구어·사투리다 — 뜻이 같아도 낱말이 안 겹쳐
    점수가 0.1 아래로 깔린다(실측 2026-08-27: 최악 22개가 **전부 정확한 번역**이었다.
    `酒ぐせが悪く` ↔ 되돌림 `酒癖がひどい` 가 0.09).

    되돌림과 원문은 **둘 다 일본어**다 — 그러니 같은 언어끼리 **뜻으로** 재면 그 잡음이
    걷힌다. 모델은 로컬 LaBSE 라 망도 한도도 안 든다.

    ⚠ 글자 점수는 버리지 않고 둘째 축으로 남긴다 — **뜻은 같은데 표현이 멀다**와
    **둘 다 멀다**는 층이 다르다.
    """
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/LaBSE", device="cpu")
    uniq = {}
    for _sim, _k, jp, _ko, back in scored:
        for t in (jp, back):
            uniq.setdefault(t, len(uniq))
    texts = [t for t, _ in sorted(uniq.items(), key=lambda x: x[1])]
    emb = model.encode(texts, batch_size=batch, convert_to_tensor=True, normalize_embeddings=True)
    out = []
    for sim, k, jp, ko, back in scored:
        sem = float(emb[uniq[jp]] @ emb[uniq[back]])
        out.append((sem, sim, k, jp, ko, back))
    out.sort(key=lambda x: x[0])
    del torch
    return out


def main():
    ap = argparse.ArgumentParser(
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("scenes", nargs="*", help="ED1SCN3 처럼 씬 이름")
    ap.add_argument("--report", action="store_true", help="되돌리지 않고 캐시만으로 본다")
    ap.add_argument("--worst", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0, help="이만큼만 되돌린다(한도를 아낀다)")
    ap.add_argument("--short", action="store_true", help="짧아서 점수를 못 믿는 것만 본다")
    ap.add_argument("--sem", action="store_true", help="뜻으로 잰다(로컬 LaBSE, 일↔일) — 권장")
    ap.add_argument(
        "--min", type=int, default=0, help="원문이 이 글자 이상인 것만 (긴 문장에 오역이 숨는다)"
    )
    a = ap.parse_args()

    pairs = collect(set(a.scenes))
    cache = B.load_cache(CACHE)
    todo = [p for p in pairs if p[2] not in cache]
    if a.limit:
        todo = todo[: a.limit]

    if todo and not a.report:
        key = C.need_secret(
            "DEEPL_API_KEY", "https://www.deepl.com/pro-api 의 **DeepL API Free** — 월 50만 자"
        )
        chars = sum(len(p[2]) for p in todo)
        print(f"되돌릴 것 {len(todo)} 블록 · {chars:,}자 (캐시 {len(cache)} · 전체 {len(pairs)})")

        def tick(done, total):
            B.save_cache(CACHE, cache)
            print(f"  {done}/{total}")

        B.fetch(todo, cache, key, "KO", "JA", on_save=tick)
        B.save_cache(CACHE, cache)

    # 🔴 짧은 문장은 표기 하나에 점수가 흔들린다 — 갈라서 본다.
    scored = B.rank(pairs, cache, drop_short=not a.short)
    if a.short:
        scored = [x for x in scored if B.is_short(x[2], x[4])]
    if a.min:
        scored = [x for x in scored if len(x[2]) >= a.min]
    if not scored:
        print("대조할 것이 없다 — `--report` 를 빼고 한 번 돌린다")
        return
    if a.sem:
        rows = semantic(scored)
        print(f"\n대조 {len(rows)} 블록 · **뜻이** 어긋난 순 {min(a.worst, len(rows))} 개")
        print("⚠ 글자 점수는 둘째 축이다 — 낮다고 오역이 아니라 표현이 다른 것이다\n")
        for sem, sim, k, jp, ko, back in rows[: a.worst]:
            print(f"  [뜻 {sem:.2f} · 글자 {sim:.2f}] {k}")
            print(f"    원문   {jp[:58]}")
            print(f"    우리   {ko[:58]}")
            print(f"    되돌림 {back[:58]}")
        lo = sum(1 for x in rows if x[0] < 0.70)
        print(f"\n뜻 0.70 미만 {lo} · 뜻 중앙값 {rows[len(rows) // 2][0]:.2f}")
    else:
        print(f"\n대조 {len(scored)} 블록 · 어긋난 순 {min(a.worst, len(scored))} 개")
        print("⚠ 글자 대조는 이 코퍼스에서 잡음이 크다 — `--sem` 을 쓴다\n")
        for sim, k, jp, ko, back in scored[: a.worst]:
            print(f"  [{sim:.2f}] {k}")
            print(f"    원문   {jp[:58]}")
            print(f"    우리   {ko[:58]}")
            print(f"    되돌림 {back[:58]}")
        lo = sum(1 for x in scored if x[0] < 0.35)
        print(f"\n0.35 미만 {lo} · 중앙값 {scored[len(scored) // 2][0]:.2f}")
    if not a.short:
        n_short = sum(1 for _k, jp, ko in pairs if ko in cache and B.is_short(jp, cache[ko]))
        print(f"⚠ 짧아서 뺀 것 {n_short} — 보려면 `--short`")


if __name__ == "__main__":
    main()
