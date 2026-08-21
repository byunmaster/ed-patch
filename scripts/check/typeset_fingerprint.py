#!/usr/bin/env python3
"""조판 지문 — **`shared/` 를 고치면 다른 게임이 스스로 운다**.

## 왜 필요한가

락(`locked_lines`)도 관측 대장(`observed_lines`)도 **조판을 안 본다** — 화자 + 창 본문만
해시한다. 그래서 줄바꿈 규칙을 건드리면 **이미지는 바뀌는데 아무 알림도 안 뜬다**
(게임 `CLAUDE.md` 가 적어 둔 함정이다).

플랫폼을 병행하면 이 구멍이 사고가 된다 — 새턴 작업하다 `shared/text/krwrap.py` 를
한 줄 고치면 **PS1 이미지의 조판이 조용히 바뀐다.** 게임 트리는 안 겹쳐도 `shared/` 는 겹친다.

## 무엇을 재나

그 게임의 **화면에 나갈 문안 전량을 조판기에 통과시킨 결과**를 해시한다. 문안이 바뀌어도
값이 바뀌므로, **문안 작업 중에는 갱신하며 간다**(`--freeze`). 값이 말하는 것은
「내가 안 건드린 게임의 조판이 그대로인가」다 — 그래서 **공용 변경 전후로 비교**한다.

  python3 scripts/check/typeset_fingerprint.py            # 지금 지문 (정본과 대조)
  python3 scripts/check/typeset_fingerprint.py --freeze   # 정본 갱신 (문안을 의도적으로 바꿨을 때)

⚠ **자동 갱신하지 않는다.** 자동이면 알림이 무의미해진다(락·관측과 같은 규율).

⚠ 정본 값은 **게임 아래**(`games/<게임>/typeset_fingerprint.json`)라 `main` 의 작업 트리엔
없다 — 그런데 공용을 고치는 자리가 바로 `main` 이다. 그래서 파일이 없으면 **게임 브랜치
`game/<게임>` 에서 읽어 온다**(`load_canon`). 장치가 도는 곳과 사고가 나는 곳이 어긋나면
장치가 아니다.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

# scripts/check/ 아래라 세 번 올라가야 레포 루트다
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ⚠ **값은 게임 것**이다 — 루트에 두면 게임 브랜치가 갱신할 때마다 공용 파일을 건드리게
#   된다(공용은 main 에서만 고친다는 규칙과 부딪힌다). 도구는 공용, 값은 게임 아래.
def canon_path(game):
    return os.path.join(REPO, "games", game, "typeset_fingerprint.json")


# 🔴 그런데 **공용은 `main` 에서 고친다** — 값이 게임 브랜치에 있으니 정작 위험한 자리에서
#    파일이 없어 검사가 건너뛴다(실측: main 에서 `⏭ 정본 없음` 만 떴다). 장치가 도는 곳과
#    사고가 나는 곳이 어긋나면 장치가 아니다. 없으면 **게임 브랜치에서 읽어 온다.**
def load_canon(game):
    path = canon_path(game)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8")), "작업 트리"
    ref = f"game/{game}:games/{game}/typeset_fingerprint.json"
    r = subprocess.run(["git", "show", ref], cwd=REPO, capture_output=True, text=True, check=False)
    if r.returncode == 0 and r.stdout.strip():
        return json.loads(r.stdout), f"브랜치 game/{game}"
    return {}, None


# 게임마다 「문안을 조판기에 통과시키는 법」이 다르다 — 그 게임 도구가 안다.
GAMES = {
    "ps1-ed1+2": ("games/ps1-ed1+2/tools", "reinsert_kr_pilot"),
}


def fingerprint(game):
    """{씬: 조판 결과 sha1} — 그 게임의 화면 문안 전량을 조판기에 태운다."""
    rel, mod = GAMES[game]
    sys.path.insert(0, os.path.join(REPO, rel))
    os.environ.setdefault("LOCK_BYPASS", "1")
    R = __import__(mod)
    out = {}
    for scn, _lba, _size in R.SCN_FILES:
        h = hashlib.sha1()
        with redirect_stdout(io.StringIO()):
            ren = R.rendered(scn)
        for eid in sorted(ren):
            # 조판기를 그대로 태운다 — 줄바꿈이 값에 들어가야 조판 변화를 잡는다
            pages = R.wrap_page(ren[eid])
            h.update(f"{eid}\x00".encode())
            for pg in pages:
                h.update(("\x01".join(pg) + "\x02").encode())
        out[scn] = h.hexdigest()[:12]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--game", default="ps1-ed1+2")
    a = ap.parse_args()
    now = fingerprint(a.game)
    CANON = canon_path(a.game)
    canon, src = load_canon(a.game)
    old = canon.get(a.game, {})
    if a.freeze:
        # ⚠ 갱신은 **작업 트리에만** 쓴다 — 남의 브랜치 값을 여기로 베끼면 안 된다
        if src and src != "작업 트리":
            canon = {}
            old = {}
        canon[a.game] = now
        canon.setdefault(
            "_doc",
            [
                "조판 지문 — `shared/` 변경이 다른 게임의 줄바꿈을 조용히 바꾸는 것을 잡는다.",
                "락·관측 대장은 조판을 안 본다(화자 + 창 본문만 해시). 이 파일이 그 구멍을 메운다.",
                "⚠ 문안을 의도적으로 바꿨을 때만 `--freeze`. 자동 갱신하면 알림이 무의미해진다.",
            ],
        )
        json.dump(canon, open(CANON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  조판 지문 갱신 ({a.game}) — {len(now)}씬")
        return 0
    if not old:
        print(f"  ⏭ {a.game} 정본 없음 — `--freeze` 로 세운다")
        return 0
    diff = [s for s in now if old.get(s) != now[s]]
    where = f"{a.game}, 정본 {src}" if src and src != "작업 트리" else a.game
    print(f"  {'✅ 조판 그대로' if not diff else f'⚠ 조판이 바뀐 씬 {len(diff)}'} ({where})")
    for s in diff[:8]:
        print(f"      {s}: {old.get(s)} → {now[s]}")
    if diff:
        print("      문안을 바꿨으면 `--freeze`. **안 바꿨는데 떴으면 `shared/` 를 의심한다.**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
