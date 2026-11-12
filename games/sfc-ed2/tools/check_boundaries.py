"""롬 짝 표(romdump) 기준 경계 점검 — 원판과 맞댄 세 부류(마스터 10-30 「보물상자처럼 띄어쓰기·개행이 안 된 곳」, pce-ed1 결함 셋과 같은 부류).

  ① 엔진이 끼워 넣는 칸(이름·아이템 등 `{…}` 토큰, 조사 훅·조건·제어 코드 제외) 바로 앞이 한글인데 공백이 없다
  ② 원판 메시지의 쪽 넘김(⏎)이 우리 문안에서 줄었다 — 두 문장이 한 쪽에 붙는다
  ③ 원판 메시지가 개행(↵ · ⏎)으로 끝나는데 우리 문안은 안 끝난다 — 다음 메시지가 같은 줄에 붙는다
가나가 남은 행(원문 바이트 그대로 · 표 데이터를 글리프 표로 읽은 행)은 화면 대사가 아니라 뺀다.

    python3 games/sfc-ed2/tools/check_boundaries.py [롬]      # 기본 = 지금 꼬리표의 빌드
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KANA = re.compile(r"[ぁ-ヿ]")
SKIP_MARK = {"원문 바이트 그대로", "그래픽·표 데이터"}
# 토큰이 아닌 것: 조사 훅 · 조건 · 16진 제어(단 $0A $0B $0D $0E 는 이름·아이템을 끼워 넣는 코드라 센다) · 점프
NOT_INSERT = re.compile(
    r"\{(?:[가-힣]/[가-힣]|으?로/?로?|조건\d+|(?![0-9A-Fa-f]*(?:0[abdeABDE])\})[0-9A-Fa-f?]{2,3}|\?[^}]*)\}"
)
TOKEN = re.compile(r"\{[^}]*\}")


def scan(lines: list[str]) -> tuple[list[int], list[str]]:
    """짝 표 줄들 → (분모 넷, 위반 목록). 테스트가 양성 대조로 부른다."""
    n = [0, 0, 0, 0]
    bad: list[str] = []
    for ln in lines:
        f = ln.split("\t")
        if len(f) < 3:
            continue
        jp, kr = f[1], f[2]
        if (f[3:4] and f[3] in SKIP_MARK) or not jp.strip() or not kr.strip() or KANA.search(kr):
            continue
        n[0] += 1
        for m in TOKEN.finditer(kr):
            if NOT_INSERT.fullmatch(m.group(0)):
                continue
            n[1] += 1
            p = kr[m.start() - 1] if m.start() else ""
            if "가" <= p <= "힣":
                bad.append(
                    f"① {f[0]} 끼워 넣는 칸 앞 공백 없음 {kr[max(0, m.start() - 8) : m.end() + 4]!r}"
                )
        if jp.count("⏎") > 0:
            n[2] += 1
            if kr.count("⏎") < jp.count("⏎"):
                bad.append(f"② {f[0]} 쪽 넘김 줄었다 원판 {jp.count('⏎')} → 한글 {kr.count('⏎')}")
        if jp.rstrip().endswith(("↵", "⏎")):
            n[3] += 1
            if not kr.rstrip().endswith(("↵", "⏎")):
                bad.append(f"③ {f[0]} 끝 개행 없음 {kr[-12:]!r}")
    return n, bad


def main() -> None:
    rom = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    )
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent / "romdump.py"),
                td,
                "--kr",
                str(rom),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        lines = (Path(td) / "pairs.tsv").read_text(encoding="utf-8").split("\n")[1:]
    n, bad = scan(lines)
    for b in bad[:30]:
        print("  " + b)
    print(
        f"경계 점검 — 대사 행 {n[0]} · ① 끼워 넣는 칸 {n[1]} · ② 쪽 넘김 있는 행 {n[2]} · ③ 개행으로 끝나는 행 {n[3]} · 위반 {len(bad)}"
    )
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
