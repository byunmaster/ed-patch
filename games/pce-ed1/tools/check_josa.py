"""조사 일치 검사 — **P2 를 닫는 상주 게이트**(`docs/ed1-phases.md`).

이 게임의 조사는 두 갈래다:

    런타임 주입 뒤 → **동적 조사 토큰**(`은/는`·`이/가`…). 앞말이 실행 중에 정해지니
                     빌드가 못 고른다 — 폰트 후킹 루틴이 받침을 보고 고른다(status 12절).
    리터럴 뒤     → **고른 조사 한 글자**. 앞말이 빌드 시점에 확정되니 그냥 맞게 쓴다.

그래서 틀릴 수 있는 자리도 둘이다. 둘 다 **빌드도 통과하고 화면에서만 드러난다**:

    A. 주입 토큰(`{02}` 이름 · `{0E}` 아이템) **바로 뒤에 고정 조사**를 썼다
       → 앞말이 뭐가 오든 한 쪽으로 굳는다. 동적 토큰을 써야 한다.
🔴 **B(「리터럴 뒤 조사가 받침과 안 맞는다」)는 기계로 못 본다 — 시도했다가 접었다.**
   조사 글자는 낱말 안에도 들어간다(「라**이**아스」·「페**이**지」·「마**을**」·「독**가**스」·
   「효**과**」). 형태소 경계를 모르면 가를 수 없어서, 처음 판에서 **42건 중 39가 오탐**이었다.
   ⇒ 그 축은 사람이 본다. 기계는 **A 만** 본다 — 그건 경계가 토큰으로 분명하다.
   (자동 생성한 문안은 `shared/text/josa` 로 만들어 애초에 맞다.)

⚠ **동적 토큰을 리터럴 뒤에 쓴 것은 오류가 아니다** — 훅이 받침을 보고 옳게 고른다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common

from shared.text.josa import PAIRS

TOKEN = re.compile(r"\{([0-9A-Fa-f]{2,})\}")
# 글자를 **끼워 넣는** 토큰만 본다 — 앞말이 실행 중에 정해지는 자리다(status 3절·12절).
#   02 행위자 이름 · 0E 아이템 이름
# ⚠ 01(개행)·04(표시 모드 복원)·05·06·07 은 **글자를 안 넣는다** — 그 뒤 조사는 앞의 리터럴에
#   붙는 것이라 고정 조사가 맞다(실측: 「２０００{04}이 됐다」는 「이천이」라 정상).
INJECT = {"02", "0E"}
DISPLAY = {"01", "03", "04", "05", "06", "07", "0A", "1E", "1F", "20"}
JOSA_TOKEN = re.compile("|".join(re.escape(p) for p in PAIRS))
# 고정 조사 한 글자 — 앞이 한글 음절일 때만 본다
FIXED = {v: k for k, pair in PAIRS.items() for v in pair}
SCRIPT = common.GAME_DIR / "script"


def strings():
    """정본의 우리 문안 전부 — (파일, 열쇠, 글)."""

    def walk(o, path, name):
        if isinstance(o, str):
            yield name, path, o
        elif isinstance(o, dict):
            for k, v in o.items():
                if not k.startswith("_"):
                    yield from walk(v, f"{path}.{k}" if path else k, name)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, f"{path}[{i}]", name)

    for f in sorted(SCRIPT.rglob("*.json")):
        yield from walk(json.loads(f.read_text()), "", f.name)


def check_text(t: str) -> list[str]:
    """주입 토큰 뒤에 고정 조사를 쓴 자리를 잡는다(표시 전용 코드는 건너뛴다)."""
    out = []
    for m in TOKEN.finditer(t):
        if m.group(1).upper() not in INJECT:
            continue
        i = m.end()
        while (nxt := TOKEN.match(t, i)) and nxt.group(1).upper() in DISPLAY:
            i = nxt.end()  # 표시 전용 코드는 글자를 안 넣으니 건너뛴다
        if i < len(t) and t[i] in FIXED and not JOSA_TOKEN.match(t, i):
            out.append(
                f"주입 토큰 {m.group()} 뒤에 고정 조사 「{t[i]}」 —"
                f" 앞말이 실행 중에 정해지니 동적 토큰({FIXED[t[i]]})을 써라"
            )
    return out


def main() -> int:
    bad = 0
    for fname, key, t in strings():
        for msg in check_text(t):
            print(f"  🔴 {fname} {key}: {msg}")
            bad += 1
    n = sum(1 for _ in strings())
    print(f"조사 검사: 문안 {n}개 · 어긋남 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
