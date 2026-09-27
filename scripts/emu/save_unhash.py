"""mednafen 세이브를 **해시가 안 붙은 이름 한 벌**로 모은다 — 새턴 밖 기종용(md·pce·sfc·ps1).

    python3 scripts/emu/save_unhash.py --fit <세이브디렉터리> "<이미지>"

🔴 **왜.** mednafen 은 세이브 이름을 `<이미지이름>.<md5>.<확장자>` 로 짓는다(`%f.%M%x`).
롬을 새로 구울 때마다 md5 가 바뀌므로 **빌드를 갈면 세이브가 조용히 안 보인다** — 마스터가
md 에서 여러 번 겪었다(2026-09-27, 하루에 롬이 네 번 바뀌며 세이브가 못 따라왔다). 세션이
게시 때마다 새 md5 이름으로 사본을 떠 주는 방식은 한 번만 빠져도 샌다.
그런데 `%M` 의 규칙은 **먼저 해시 없는 이름을 찾아보고 있으면 그걸 쓴다**
(`general.cpp:MDFN_MakeFName`). 그래서 `<이미지이름>.<확장자>` 한 벌을 두면 **빌드를 아무리
갈아도 mednafen 이 늘 그 파일을 읽고 거기에 쓴다.** 새턴은 `ss_gameid.py --fit` 이 같은 일을
하고(백업 RAM 셋을 한 조로 옮겨야 해서 따로 있다), 여기는 나머지 기종의 일반판이다.

규칙은 `ss_gameid.fit` 과 **한 군데가 다르다** — 고르는 기준이 「든 것이 많은 것」이 아니라
**「비어 있지 않은 것 중 제일 새것」**이다.
  ⚠ 새턴 백업 RAM 은 빈 자리가 0 이라 비영 바이트 수가 곧 진행량이지만, 카트리지 SRAM 은
    아니다 — 실측(md, 2026-09-27): 09-17 세이브가 16384B 전부 비영이고 09-27 마스터 진행분이
    12250B 라, 「많은 것」으로 고르면 **열흘 전 세이브가 이긴다.** 그래서 새것을 고르되,
    못 읽은 회차가 남기는 **빈 세이브**(바이트가 전부 같은 값)만 후보에서 뺀다.
  · 해시별로 묶는다(PS1 메모리카드는 한 회차에 `0.mcr`·`1.mcr` 두 장이다).
  · 해시 없는 쪽이 이미 있고 그것이 **더 새것이면 손대지 않는다** — mednafen 이 이미 그걸
    쓰고 있다는 뜻이다. 세션이 그 뒤에 새 md5 이름으로 사본을 떠 두었으면 그게 이긴다.
  · 덮어쓸 때는 옛 해시 없는 파일을 `.bak` 으로 한 세대 남긴다. 옛 해시 이름은 **안 지운다.**
  · mednafen 이 켜져 있으면 아무것도 안 한다(종료할 때 덮어쓴다).
"""

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ss_gameid import _mednafen_running

HASHED = re.compile(r"^(?P<hash>[0-9a-f]{32})\.(?P<rest>.+)$")


def _blank(path):
    """못 읽은 회차가 남긴 빈 세이브인가 — 바이트가 전부 같은 값(0x00 이든 0xFF 든)."""
    try:
        with open(path, "rb") as f:
            return len(set(f.read())) <= 1
    except OSError:
        return True


def fit(save_dir, image):
    base = os.path.splitext(os.path.basename(image))[0]
    if _mednafen_running():
        print("⚠ mednafen 이 켜져 있어 세이브 이름을 안 건드린다 — 끄고 다시 띄운다")
        return base, 0, None
    if not os.path.isdir(save_dir):
        return base, 0, None

    # 해시별로 묶는다 — `ed1-kr.<md5>.sav` · PS1 은 `<이름>.<md5>.0.mcr`/`.1.mcr`
    groups = {}
    for f in os.listdir(save_dir):
        if not f.startswith(base + "."):
            continue
        m = HASHED.match(f[len(base) + 1 :])
        if m and not m["rest"].endswith((".bak", ".tmp")):
            groups.setdefault(m["hash"], []).append(m["rest"])
    if not groups:
        return base, 0, None

    def paths(h):
        return [os.path.join(save_dir, f"{base}.{h}.{r}") for r in groups[h]]

    live = [h for h in groups if any(not _blank(p) for p in paths(h))]
    if not live:
        return base, 0, None
    best = max(live, key=lambda h: max(os.path.getmtime(p) for p in paths(h)))
    b_time = max(os.path.getmtime(p) for p in paths(best))
    have = [
        p
        for p in (os.path.join(save_dir, f"{base}.{r}") for r in groups[best])
        if os.path.exists(p)
    ]
    if have and max(os.path.getmtime(p) for p in have) >= b_time:
        return base, 0, None
    n = 0
    for r in groups[best]:
        dst = os.path.join(save_dir, f"{base}.{r}")
        if os.path.exists(dst):
            shutil.copy2(dst, dst + ".bak")
        shutil.copy2(os.path.join(save_dir, f"{base}.{best}.{r}"), dst)
        n += 1
    return base, n, best


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "--fit":
        name, n, old = fit(a[1], a[2])
        if n:
            print(f"세이브를 해시 없는 이름으로 모았다: {old[:8]}… → {name}.* ({n} 개)")
    else:
        raise SystemExit("사용: save_unhash.py --fit <세이브디렉터리> <이미지>")
