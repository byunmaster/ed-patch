#!/usr/bin/env python3
"""이름 검사 진입점 — 게임 어댑터가 내놓은 「원문 줄 · 우리 줄」을 사전으로 잰다.

    python3 scripts/check/check_names.py --game sfc-ed1          # 요약(분모 포함)
    python3 scripts/check/check_names.py --game sfc-ed1 --list   # 어긋난 자리 전부

잣대는 `shared/canon/names.py`(공용 하나), 게임 몫은 둘뿐이다:

- **어댑터** `games/<게임>/tools/names_corpus.py` — `TITLE`(작품 사전, 기본 `eiyuu` · ED3 는 `ed3`) 과 `pairs()`. `pairs()` 가 `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 — 갈래는 "dialog"(메시지 창에 나가는 **문장** — 대사·전투 로그·시스템 메시지·자막) · "slot"(고정 폭 **칸** — HUD·워프·입장 배너·이름 칸·메뉴·표) —
  **문안 전체**에 대해 낸다. 미번역 줄도 None 으로 낸다(분모가 거짓말을 안 하게).
  🔴 어댑터는 이름을 **들지 않는다** — 원문과 문안을 읽어 넘길 뿐이다(독자 데이터 금지, 마스터 10-07).
- **예외** `games/<게임>/names_exceptions.json` — `{"<자리>|<사전 원문>": {"why": …, "approved": "마스터 YYYY-MM-DD"}}`.
  `approved` 가 없으면 예외로 안 친다 — 세션 판단이 정본이 되는 길을 막는다.

종료 코드: 0 = 어긋남 없음(번역 트랙이 아니면 해당 없음) · 1 = 승인 안 된 어긋남 · 2 = 어댑터 없음(이 게임은 **안 쟀다** — 실패).
"""

import argparse
import importlib.util
import json
import os
import pickle
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from canon.names import audit


def _adapter(game):
    path = os.path.join(ROOT, "games", game, "tools", "names_corpus.py")
    if not os.path.exists(path):
        return None
    sys.path.insert(0, os.path.dirname(path))  # 어댑터가 자기 게임 도구를 임포트한다
    spec = importlib.util.spec_from_file_location(f"names_corpus_{game}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return cached(mod, game)


class _CachedPairs:
    """게이트 한 번 안에서 어댑터 `pairs()` 를 **한 번만** 돌린다(11-26 전체 점검 — 공용 검사 다섯이 같은
    말뭉치를 프로세스마다 다시 만들어 PS1 III 는 이름·정본 검사만 각 9분이 들었다). 칸은 `scripts/check.sh` 가
    `CHECK_PAIRS_CACHE` 로 만들어 끝나면 지운다 — 칸이 없으면(검사기를 혼자 돌릴 때) 원래대로 매번 만든다."""

    def __init__(self, mod, game, cache_dir):
        self._mod, self._path = mod, os.path.join(cache_dir, f"{game}.pairs.pkl")

    def __getattr__(self, name):
        return getattr(self._mod, name)

    def pairs(self):
        if os.path.exists(self._path):
            with open(self._path, "rb") as f:
                return pickle.load(f)
        rows = list(self._mod.pairs())
        try:  # 어댑터 고유 클래스처럼 피클이 안 되는 값이면 그냥 넘긴다(캐시는 빠르게 하는 것일 뿐)
            tmp = self._path + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump(rows, f)
            os.replace(tmp, self._path)
        except (pickle.PicklingError, TypeError, AttributeError, OSError) as e:
            print(f"  (말뭉치 캐시 생략: {type(e).__name__})", file=sys.stderr)
        return rows


def cached(mod, game):
    d = os.environ.get("CHECK_PAIRS_CACHE")
    return _CachedPairs(mod, game, d) if (mod is not None and d and os.path.isdir(d)) else mod


def _is_kr(game):
    """번역(kr) 트랙인가 — 게임 CLAUDE.md 머리의 「트랙」 줄로 가른다(fix 트랙은 우리 이름 문안이 없다)."""
    path = os.path.join(ROOT, "games", game, "CLAUDE.md")
    if not os.path.exists(path):
        return True
    with open(path, encoding="utf-8") as f:
        head = f.read(2000)
    return "kr" in head.split("트랙", 1)[-1][:40] if "트랙" in head else True


def _exceptions(game):
    path = os.path.join(ROOT, "games", game, "names_exceptions.json")
    if not os.path.exists(path):
        return {}, []
    with open(path, encoding="utf-8") as f:
        raw = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    ok = {k for k, v in raw.items() if isinstance(v, dict) and v.get("approved")}
    return ok, sorted(set(raw) - ok)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--list", action="store_true", help="어긋난 자리를 전부 찍는다")
    a = ap.parse_args(argv)

    mod = _adapter(a.game)
    if mod is None and not _is_kr(a.game):
        print(f"이름 검사 [{a.game}] — 해당 없음(번역 트랙이 아니다)")
        return 0
    if mod is None:
        print(
            f"⚠ 이름 검사 어댑터 없음 — {a.game} 은 **안 쟀다** (games/{a.game}/tools/names_corpus.py)"
        )
        return 2

    title = getattr(mod, "TITLE", "eiyuu")  # 작품 사전 — ED3 는 "ed3"
    r = audit(mod.pairs(), title=title)
    if not r.units:
        # 줄 0 = 어댑터가 문안을 못 읽었다(파생물 없는 트리 등) — 「어긋남 0」으로 찍히면 거짓 초록이다(11-08 실측)
        print(
            f"⚠ 이름 검사 [{a.game}] — 어댑터가 낸 줄이 0 이다 · **안 쟀다**(파생물·원본 링크 확인)"
        )
        return 2
    approved, unsigned = _exceptions(a.game)
    left = [h for h in r.mismatches if f"{h.where}|{h.jp}" not in approved]
    excused = len(r.mismatches) - len(left)

    print(
        f"이름 검사 [{a.game} · 사전 {title}] — 줄 {r.translated}/{r.units}(번역/전체) · 사전 이름 출현 {len(r.hits)}"
        f" · 어긋남 {len(left)}"
        + (f" (승인 예외 {excused})" if excused else "")
        + f" · 확인 대기 이름 {len(r.pending)} · 안 잰 열쇠 {r.skipped_keys}"
        + (f" · ⚠ 대사/비대사 미구분 줄 {r.unlabeled}" if r.unlabeled else "")
    )
    if unsigned:
        print(f"  ⚠ 승인 없는 예외 {len(unsigned)} — 예외로 안 쳤다: {', '.join(unsigned[:5])}")
    for h in left if a.list else left[:10]:
        print(f"  ✗ {h.where}  {h.jp} → 사전 「{h.canon}」 이 우리 줄에 없다")
    if not a.list and len(left) > 10:
        print(f"  … 외 {len(left) - 10} (--list)")
    print(
        f"  대사 속 이름 띄어쓰기 — 잰 이름 {r.spacing_checked} · 어긋남 {len(r.spacing)}"
        + (" (알림 — 실패 아님)" if r.spacing else "")
        + (" ⚠ 0 개를 쟀다 — 어댑터가 대사 갈래를 안 내는가" if not r.spacing_checked else "")
    )
    if r.spacing:
        for h in r.spacing if a.list else r.spacing[:5]:
            print(f"    ␣ {h.where}  {h.jp} → 정본 「{h.canon}」 을 띄어 썼다")
    # 알림 둘(11-08 「대도둑·대도적」 — 정본이 있는데 남아 있었다): 실패로 치지 않고 늘 센다
    print(
        f"  긴 낱말 속 이름 {len(r.glued)} · 같은 칸 원문인데 표기 갈림 {len(r.slot_split)}"
        + (" (알림 — 하나씩 보고 고칠 것은 고친다)" if r.glued or r.slot_split else "")
    )
    for h in r.glued if a.list else r.glued[:5]:
        print(f"    ⊂ {h.where}  {h.jp} → 정본 「{h.canon}」 이 더 긴 낱말 속에만 있다")
    for jp, krs in r.slot_split if a.list else r.slot_split[:5]:
        print(f"    ≠ {jp} → {' / '.join(krs)}")
    for h in r.pending[:5]:
        print(f"  ⏳ {h.where}  {h.jp} — 사전 확인 대기(_pending) 이름이 화면에 쓰인다")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
