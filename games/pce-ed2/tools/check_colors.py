"""글자색 제어 대조 — 원판과 **구운 이미지 바이트**에서 같은 줄의 색 제어(`14` 끝 · `15 nn` 시작 · `17` = `15 04` · `18 a b c d` = `14` + 글 4바이트)를 세어 열이 같은지 본다.

왜(마스터 10-29 「대사 색상코드 누락 점검」 — pce-ed1 은 해설·품목 이름 뒤 색 전환 `1D` 를 조립기가 한 번도 안 내 35메시지가 엉뚱한 색이었다): `structcheck` S4 가 대사 덩이의 구조 제어 열을 보지만
본 프로그램 문자열(`S`)·표(`T`)·장면 코드 문자열(`C`)·章間 데모는 그 밖이고, `15` 의 **인자(색 번호)** 도 안 본다. 여기서 한꺼번에 쟀다.
`06`/`04`(+`05` `07`) 는 색이 아니라 **글자 방식(`$2C0B`) 전환**(좁은 반각 글꼴 — 한글이 깨져 일부러 뺀다, `status.md` 「이름 상자」)이라 대상이 아니다.

    python3 check_colors.py [--iso <이미지>] [--gate]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import kanma
import pairs
import pceview

COLOR_RE = re.compile(r"\{(14|15 [0-9A-F]{2}|17|18 [0-9A-F ]+)\}")


def colors(s: str) -> list[str]:
    out = []
    for m in COLOR_RE.finditer(s):
        t = m.group(1)
        out.append("14" if t.startswith("18") else ("15 04" if t == "17" else t))
    return out


def _kanma_colors(m: bytes) -> list[tuple]:
    """章間 평문 메시지의 색 제어 — 이 스크립트는 `17 …이름… 18` 이 이름 상자라 글 쪽 규칙(`17`=`15 04`)과 달라 그대로 열로 센다."""
    out, i = [], 0
    while i < len(m):
        a = m[i]
        if a < 0x20:
            n = 1 + (1 if a in (0x0C, 0x15) else 0)
            if a in (0x14, 0x15, 0x17, 0x18):
                out.append(tuple(m[i : i + n]))
            i += n
        else:
            i += 2
    return out


def analyze(iso: str) -> tuple[dict[str, tuple[int, int]], list[str]]:
    kg = pairs.KoGlyphs(iso)
    stat: dict[str, tuple[int, int]] = {}
    fails: list[str] = []
    for name, fn in (
        ("대사 덩이", pairs.package_rows),
        ("본 프로그램 문자열", pairs.literal_rows),
        ("표", pairs.table_rows),
        ("장면 코드 문자열", pairs.code_rows),
    ):
        rows = withc = 0
        for key, o, k, _sh in fn(iso, kg):
            rows += 1
            co, ck = colors(o), colors(k)
            if co or ck:
                withc += 1
                if co != ck:
                    fails.append(f"{key}: 원판 {co} ≠ 한글 {ck}")
        stat[name] = (rows, withc)
    rows = withc = 0
    for n in kanma.PKGS:
        rel = kanma.pkg_rel(n)
        po = bytes(common.track_data(rel, 128))
        pf = pceview.iso_pkg(iso, rel)
        mo = kanma.messages(po, n)
        s = kanma.PKGS[n][0]
        mk = pf[s : s + 0x6000].split(b"\x00")[: len(mo)]
        for (off, m), k in zip(mo, mk, strict=True):
            rows += 1
            co, ck = _kanma_colors(m), _kanma_colors(k)
            if co or ck:
                withc += 1
                if co != ck:
                    fails.append(f"章間 {n}:{off:#x}: 원판 {co} ≠ 한글 {ck}")
    stat["章間 메시지"] = (rows, withc)
    return stat, fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    stat, fails = analyze(a.iso)
    print(
        "  글자색 제어 대조 [pce-ed2] — "
        + " · ".join(f"{k} {r}행 중 색 {c}" for k, (r, c) in stat.items())
        + f" · 어긋남 {len(fails)}"
    )
    for f in fails[:40]:
        print("  ✖", f)
    return 1 if (a.gate and fails) else 0


if __name__ == "__main__":
    sys.exit(main())
