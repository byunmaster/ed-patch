"""촬영 롬 = 지금 소스 — 빌드가 롬 옆에 **소스 지문**(`<롬>.src`)을 남기고, 촬영 도구가 지금 소스 지문과 맞는지 본다(마스터 10-19 「촬영 롬 = 지금 HEAD 빌드를 자동으로」).
지문 = `tools/`·`data/` 아래 소스 파일(테스트·캐시 제외)의 상대 경로 + 내용 sha1. 소스를 고치고 다시 안 구우면 촬영이 거절된다(`--allow-stale` 로만 넘긴다).
"""

import hashlib
import subprocess
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
HARNESS = {"pceview.py", "pcehl.py", "sweep_view.py", "sweep_sheets.py", "battleview.py", "battle_sweep.py", "romtag.py", "dis6280.py", "itemuse.py", "spelluse.py", "spellbook.py", "battle_cmd.py", "pairs.py"}  # 롬을 안 바꾸는 촬영·분석 도구


def fingerprint() -> str:
    h = hashlib.sha1()
    for sub in ("tools", "data"):
        for p in sorted((GAME / sub).rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or "tests" in p.parts or p.suffix in (".pyc", ".bak") or p.name in HARNESS:
                continue
            h.update(str(p.relative_to(GAME)).encode())
            h.update(hashlib.sha1(p.read_bytes()).digest())
    return h.hexdigest()


def stamp(iso: str) -> None:
    Path(iso + ".src").write_text(fingerprint() + "\n")


def head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=GAME, capture_output=True, text=True).stdout.strip()
    except Exception:
        return "?"


def check(iso: str, allow_stale: bool = False) -> str:
    """촬영 전에 부른다 — 롬의 소스 지문이 지금 소스와 다르면 종료(코드 4). 같으면 한 줄 설명(`롬 sha1 · HEAD · 지문`)을 돌려준다."""
    src = Path(iso + ".src")
    cur = fingerprint()
    got = src.read_text().strip() if src.exists() else "(없음)"
    sha = hashlib.sha1(Path(iso).read_bytes()).hexdigest()
    desc = f"롬 {sha} · HEAD {head()} · 소스 지문 {cur[:12]}"
    if got != cur and not allow_stale:
        print(f"⚠ 촬영 롬이 지금 소스와 다르다(롬 지문 {got[:12]} ≠ 소스 {cur[:12]}) — 다시 굽고 찍는다. {desc}", file=sys.stderr)
        sys.exit(4)
    return desc
