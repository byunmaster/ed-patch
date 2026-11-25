"""구운 롬 조판 전수 점검 — 롬 짝 표(romdump)의 한글 칸 전량(대사·전투·시스템·상점)을 줄·쪽으로 쪼개 세는 게이트(마스터 10-31 「첫칸공백, 고아부호, 빈줄개행, 여러창일때 균등한 문장 분배」).

  A 첫 칸 공백(2-5)   줄 머리가 공백(행 맨 앞·쪽 맨 앞의 이어 쓰기 자리는 제외)
  B 고아 부호(2-3)    줄이 `. , ! ? ) 」 ~ :` 등으로 시작하거나 부호만 있다
  C 빈 줄 개행(2-4)   행 안에서 내용이 없는 줄(↵↵ · 쪽 머리의 ↵)
  D 부호 뒤 공백(2-1) `, . ! ?` 바로 뒤에 글자(소수점·`?!`·닫는 부호 제외)
  E 낱말 속 접힘(2-6) 줄 머리가 조사 한 글자(은·는·이·가…)뿐인 어절 — 낱말 가운데서 끊었다
  F 넘침              한 줄 폭이 50 단위를 넘는다(런타임 변수 `{…}` 가 든 줄은 폭을 모르니 제외)
  G 쪽 분배(2-16 ③)   같은 화자 묶음에서 쪽이 둘 이상인데 ① 마지막 쪽이 한 어절뿐이고 앞 쪽이 문장 끝이 아니다 ② 쪽 끝 줄이 한 어절이고 문장 끝이 아니다
                      (창 줄 수 치우침은 쪽 경계가 문장 끝이면 정상이라 이 게이트가 안 세고 `check_layout.py` 의 balance 가 센다)
원판과 같은 꼴(같은 행 JP 칸에도 같은 횟수 이상 있다)은 「원판 동일」로 빼고 센다. A~G 는 0 이어야 한다. G 의 한도(`typeset_rom_baseline.json`, 늘면 실패)는 마스터 판정 10-31 로 둔 3곳 — 규칙 2-17(칸이 모자라면 문안을 줄이지 않고 줄·쪽 나뉨 허용, 쪽 끝 한 문장은 괜찮음):
  G1 1 = `C8A6A2`(+`C8A6B0` 같은 문장 — 머리 줄+본문 3줄이 창 3줄에 안 들어가 「싸우게.」가 새 쪽) · G2 2 = `C24E1C`(쉼표로 끝나는 쪽 끝 한 어절) · `CA951E`(원판이 손으로 가른 자리, 한글이 한 줄 길다).

    python3 check_typeset_rom.py [롬] [--list 축] [--freeze]
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import typeset as T

KANA = re.compile(r"[ぁ-ヿ]")
SKIP_MARK = {"원문 바이트 그대로", "그래픽·표 데이터"}
BASE = Path(__file__).resolve().parents[1] / "typeset_rom_baseline.json"
KEYS = ["A", "B", "C", "D", "E", "F", "G1", "G2"]
HARD = ["A", "B", "C", "D", "E", "F"]  # G 는 한도(baseline) 안이면 통과
END = ".!?…~」』"
JOSA1 = set("은는을를에도와과로만")
HDR = re.compile(r"^〔[^〕]*〕$")
TOK = re.compile(r"\{[^}]*\}")


def pages_of(cell: str) -> list[list[str]]:
    """칸 → 쪽 → 줄(화자 머리 줄 제외). 쪽 구분 ⏎ · 줄 구분 ↵."""
    out = []
    for p in cell.split("⏎"):
        out.append([ln for ln in p.split("↵") if not HDR.match(ln)])
    return out


def _plain(s: str) -> str:
    return TOK.sub("", s)


def _line_width(ln: str) -> int:
    return sum(T.width(c) for c in ln.replace(" ", " "))


def measure_cell(cell: str, wide: bool = True) -> dict[str, list[str]]:
    r: dict[str, list[str]] = {k: [] for k in KEYS}
    pg = pages_of(cell)
    for pi, p in enumerate(pg):
        for li, ln in enumerate(p):
            first = pi == 0 and li == 0
            body = _plain(ln)
            if ln.startswith(" ") and not first and body.strip():
                r["A"].append(ln)
            s = body.strip()
            if (
                s
                and not first
                and not ln.startswith("{")
                and (
                    re.fullmatch(r"[.,、。]+", s)
                    or re.match(r"^[.,!?)」』~:;]", s)
                    and not re.fullmatch(r"[?!]+", s)
                )
            ):
                r["B"].append(ln)
            if not ln.strip() and (li > 0 or pi > 0) and (li < len(p) - 1 or pi < len(pg) - 1):
                r["C"].append(ln)
            dbody = TOK.sub(
                "\x01", ln
            )  # 토큰 자리는 글자가 아니다(「다.{0a}용」 은 토큰 앞뒤라 센다)
            for m in re.finditer(r"[,.!?]([가-힣A-Za-z])", dbody):
                if (
                    not (
                        dbody[m.start() - 1 : m.start()].isdigit() and dbody[m.end() - 1].isdigit()
                    )
                    and "최초?의" not in dbody
                ):
                    r["D"].append(ln)
                    break
            if li and "{" not in ln:
                w = ln.split(" ")[0]
                if (
                    len(w) == 1
                    and w in JOSA1
                    and p[li - 1].strip()
                    and "가" <= p[li - 1].strip()[-1] <= "힣"
                ):
                    r["E"].append(ln)
            if wide and "{" not in ln and "<" not in ln and _line_width(ln) > T.LINE_UNITS:
                r["F"].append(ln)
    # 화자 묶음(머리 〔…〕·{09}·{F9}·{조건…}로 시작하는 쪽부터 새 묶음) 안에서만 쪽을 본다 — 다른 화자의 짧은 말은 앞 쪽의 고아가 아니다
    runs: list[list[list[str]]] = []
    for pr in cell.split("⏎"):
        allraw = [l for l in pr.split("↵") if l.strip()]
        body = [l for l in allraw if not HDR.match(l)]
        if not body:
            continue
        head = allraw[0].startswith(("〔", "{09}", "{F9}", "{조건")) or len(allraw) != len(body)
        if head or not runs:
            runs.append([])
        runs[-1].append(body)
    for ps in runs:
        for i, p in enumerate(ps):
            last = re.sub(r"(\{[^}]*\}|<[^>]*>)+$", "", p[-1].strip())
            one = " " not in last and bool(last)
            prev = re.sub(r"(\{[^}]*\}|<[^>]*>)+$", "", ps[i - 1][-1].strip()) if i else ""
            if i == len(ps) - 1 and i > 0 and len(p) == 1 and one and prev[-1:] not in END:
                r["G1"].append(last)
            elif i < len(ps) - 1 and one and last[-1:] not in END:
                r["G2"].append(last)
    return r


def scan(lines: list[str]) -> tuple[int, dict[str, list[str]]]:
    """짝 표 줄들 → (분모, 축별 걸린 목록). 원판 동일은 뺀다. 테스트가 양성 대조로 부른다."""
    bad: dict[str, list[str]] = {k: [] for k in KEYS}
    n = 0
    for ln in lines:
        f = ln.split("\t")
        if len(f) < 3:
            continue
        jp, kr = f[1], f[2]
        if (f[3:4] and f[3] in SKIP_MARK) or not jp.strip() or not kr.strip() or KANA.search(kr):
            continue
        n += 1
        wide = (
            "C2" <= f[0][:2] <= "CB"
        )  # 대사 뱅크만 폭 50 — 전투 창(D4~)은 폭이 다르다(화면 촬영에서 따로 본다)
        mk, mj = measure_cell(kr, wide), measure_cell(jp.replace("　", " "), wide)
        for k in KEYS:
            if k in ("G3",) or len(mk[k]) > len(mj[k]):
                if k == "G3" and len(mk[k]) <= len(mj[k]):
                    continue
                bad[k].append(f"{f[0]} {(mk[k] or [''])[-1]!r}")
    return n, bad


def rom_pairs(rom: Path) -> list[str]:
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
        return (Path(td) / "pairs.tsv").read_text(encoding="utf-8").split("\n")[1:]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom = (
        Path(args[0])
        if args and Path(args[0]).suffix == ".sfc"
        else common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    )
    n, bad = scan(rom_pairs(rom))
    cnt = {k: len(v) for k, v in bad.items()}
    if "--list" in sys.argv:
        for x in bad[sys.argv[sys.argv.index("--list") + 1]]:
            print(x)
        return
    if "--freeze" in sys.argv:
        BASE.write_text(
            json.dumps({k: cnt[k] for k in KEYS if k not in HARD}, indent=1) + "\n",
            encoding="utf-8",
        )
        print("기준선 갱신:", cnt)
        return
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    print(
        f"롬 조판 점검 [sfc-ed2] 칸 {n} · "
        + " · ".join(f"{k} {cnt[k]}" for k in KEYS)
        + " (기준선 "
        + " · ".join(f"{k} {v}" for k, v in base.items())
        + ")"
    )
    fail = [f"{k} {cnt[k]}" for k in HARD if cnt[k]] + [
        f"{k} {cnt[k]} > 기준선 {base[k]}" for k in KEYS if k in base and cnt[k] > base[k]
    ]
    for k in HARD:
        for x in bad[k][:5]:
            print(f"  {k} {x}")
    if fail:
        print("조판 위반:", "; ".join(fail))
        sys.exit(1)
    print("조판 위반 0")


if __name__ == "__main__":
    main()
