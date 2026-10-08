"""이름창 ≠ 본문 메아리 — 화자 이름창(`<1e>이름<04>`)에 쓴 이름이 본문 첫머리에 또 나오지 않는가. (기반 F4)

    python3 tools/check_name_echo.py          # 목록
    python3 tools/check_name_echo.py --check  # 게이트

이름창이 이미 화자를 보여 주므로 본문이 「남자: …」 · 「남자는 …」 로 같은 말을 되풀이하면 어색하다(PS1 `check_name_echo`).
번역된 대본 스트림 전량을 잰다(번역이 늘면 저절로 분모가 는다). 화자 칸 폭(이름창 글자 수) 자체는 빌드·정본(speaker)이 본다.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

HEAD = re.compile(r"<1e>([^<]*)<04>(?:<01>)?(.*)", re.S)


def echo(text: str) -> str | None:
    m = HEAD.match(text)
    if not m:
        return None
    name, body = m.group(1).strip(), re.sub(r"^(<[0-9a-f]+>)*", "", m.group(2)).lstrip()
    return name if name and body.startswith(name) else None


def scan() -> tuple[int, int, list[str]]:
    n = spk = 0
    errs = []
    for f in sorted(glob.glob(str(common.GAME_DIR / "script" / "*.json"))):
        for off, e in json.loads(Path(f).read_text(encoding="utf-8")).get("streams", {}).items():
            t = e.get("ours", "")
            if not t:
                continue
            n += 1
            if HEAD.match(t):
                spk += 1
            nm = echo(t)
            if nm:
                errs.append(f"script:{Path(f).stem}:{off} — 이름창 「{nm}」 이 본문 첫머리에 또 나온다")
    return n, spk, errs


def main() -> None:
    n, spk, errs = scan()
    print(f"  이름창 메아리 — 번역 스트림 {n} · 화자창 {spk} · 메아리 {len(errs)}")
    for e in errs:
        print(f"    ❌ {e}")
    if "--check" in sys.argv and errs:
        raise SystemExit("이름창 메아리 검사 실패 — 본문에서 화자 이름을 뺀다")


if __name__ == "__main__":
    main()
