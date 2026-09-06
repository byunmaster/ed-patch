"""조판 — 우리 문안을 이 게임의 창 규격에 맞춰 줄로 나눈다.

엔진은 **자동 개행을 안 한다** — 줄바꿈은 문안 안의 `0x01`(=`\\n`)이 정한다(ED3 PoC 실측).
그래서 「몇 칸까지 되나」는 코드가 아니라 **원본이 실제로 쓴 값**에서 온다.

    ED3  줄 최대 30칸 · 창 최대 5줄   (조각 33,958 · 줄 44,834 실측)
    ED4  줄 최대 35칸 · 창 최대 5줄   (조각 24,390 · 줄 33,524 실측)

🔴 **상수를 원본에서 다시 잰다**(`--check`). 「24칸」으로 알고 있던 값이 실은 30/35 였다 —
   앞서 잰 것은 표본이 좁았다. 상수를 박아 두기만 하면 언제 틀렸는지 모른다.

⚠ 이건 **상한이지 목표가 아니다.** 원본이 30칸을 쓴 자리가 58줄뿐이니(0.13%), 그 폭을
   기본으로 삼으면 대부분의 창에서 글자가 창 밖으로 나갈 수도 있다 — 창은 자리마다 다르다.
   ⇒ 조판은 **그 조각의 원문이 쓴 폭**을 넘지 않게 맞추는 것이 1급이고, 상한은 그 위의 뚜껑이다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import common

from shared.text import krwrap

# 원본이 실제로 쓴 상한 (`--check` 가 다시 잰다)
# 🔴 **조각 하나 = 줄 하나**다(2026-09-07). 0x01 을 줄바꿈으로 읽던 때는 「5줄」이 나왔는데
#    그건 쉼표였다 — 실측 다시: ED3 30칸/1줄 · ED4 37칸/1줄.
LIMITS = {
    "ed3": {"width": 30, "lines": 1},
    "ed4": {"width": 37, "lines": 1},
}
# 대사에서 부호 뒤 공백을 지운다 — 이 레포의 조판 규약(`docs/reference/translation-conventions.md`)
STRIP_AFTER = ".,"


CELL_PX = 12  # 화면에서 코드 하나가 차지하는 가로 픽셀 (`font.PITCH`)
# 코드별 폭(px). 🔴 엔진 패치(`engine_patch`)가 있는 디스크만 12 가 아닌 값을 가질 수 있다 —
#   공백 8px 는 유저 판정(2026-09-07: 한글은 전각, 공백만 반각). 첫 씬 실측 5.2% 절약.
WIDTHS = {"ed3": {" ": 8}, "ed4": {}}
# 한 줄에 들어가는 글리프 수의 상한 = 스프라이트 격자 열 수(`engine_patch.COLS`). 패치 없으면 None.
COLS = {"ed3": 32, "ed4": None}


def cell_width(ch, disc="ed3"):
    """이 게임의 슬롯 폭 — 공백만 8/12, 나머지 1.

    ⚠ 공용 기본값(`krwrap.default_cell_width`)은 공백을 **0.5**로 센다. 그건 PS1 ED1+2 의
      규격이고 여기선 틀린다 — 이 게임엔 공백 코드가 아예 없어서 **빈 글리프를 한 자리
      구워 쓴다**(`hangul_map.EXTRA`). 엔진 패치가 공백을 8px 로 보내니 그만큼(2/3)이다.
    """
    return WIDTHS[disc].get(ch, CELL_PX) / CELL_PX


def width_cells(text, disc="ed3"):
    """한 줄의 폭(칸, 소수). 부호 뒤 공백 제거 전 값이라 안전측이다."""
    return sum(cell_width(ch, disc) for ch in text)


def budget(disc, jp, floor=0):
    """(폭, 줄 수) — **그 조각의 원문이 쓴 만큼**. 상한을 넘지 않는다.

    창은 자리마다 다르다(대사창·간판·설명문). 원문이 그 창에서 몇 칸을 썼는지가
    우리가 아는 가장 정확한 증거다 — 상한만 보고 넓게 잡으면 창 밖으로 나간다.
    """
    lim = LIMITS[disc]
    ls = jp.split("\n")
    w = max((len(x) for x in ls), default=1)
    # 🔴 **폭은 그 조각이 아니라 창이 정한다.** 조각별로 잡으면 원문이 우연히 짧은 자리에서
    #    허수 예산이 나온다 — 같은 화자가 연달아 말하는 창들이 4·19·15·21칸으로 널뛴다.
    #    인게임 실측(2026-09-07, `SC000!FT0000` 크리스 엄마 창): 프레임 안쪽 25~331px ·
    #    글자 피치 12px · 글자 시작 34 ⇒ **약 24칸**. 그 멤버의 원문 최대가 23칸이었다.
    #    ⇒ `floor` 로 **그 멤버의 최대 폭**을 받아 바닥으로 깐다. 줄 수는 창 높이라 그대로 둔다.
    if floor:
        w = max(w, floor)
    return min(w, lim["width"]), min(max(len(ls), 1), lim["lines"])


def wrap(text, disc, jp=None, width=None, lines=None, floor=0):
    """우리 문안 → 줄로 나눈 문안(`\\n` 포함).

    `jp` 를 주면 그 조각의 원문이 쓴 폭·줄 수를 예산으로 삼는다(권장).
    """
    if width is None or lines is None:
        w, n = (
            budget(disc, jp, floor)
            if jp is not None
            else (LIMITS[disc]["width"], LIMITS[disc]["lines"])
        )
        width = width if width is not None else w
        lines = lines if lines is not None else n
    out = krwrap.wrap(
        text.replace("\n", " "),
        width=width,
        cell_width=lambda ch: cell_width(ch, disc),
        strip_after=STRIP_AFTER,
    )
    return "\n".join(out[:lines]) if len(out) > lines else "\n".join(out)


def violations(text, disc, jp=None, floor=0):
    """[사유] — 조판 규격을 어긴 자리. 빈 목록이면 통과."""
    lim = LIMITS[disc]
    w, n = budget(disc, jp, floor) if jp is not None else (lim["width"], lim["lines"])
    bad = []
    ls = text.split("\n")
    cols = COLS[disc]
    for i, line in enumerate(ls):
        wc = width_cells(line, disc)
        if wc > w:
            bad.append(f"{i + 1}행이 {wc:g}칸 (예산 {w})")
        if cols and len(line) > cols:
            bad.append(f"{i + 1}행이 {len(line)}글리프 (격자 {cols}열)")
    if len(ls) > n:
        bad.append(f"{len(ls)}줄 (예산 {n})")
    return bad


def measure(disc):
    """원본이 실제로 쓴 (줄 최대 폭, 창 최대 줄 수, 조각 수, 줄 수)."""
    import scriptmap
    import textenc

    w = n = segs = lines = 0
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            if not nm.endswith(".BIN") or sz < 8:
                continue
            try:
                info = scriptmap.parse(data[off : off + sz])
            except Exception:  # noqa: BLE001, S112 — 규격 밖 멤버는 check_script 가 센다
                continue
            for _, codes in info["segments"]:
                txt = textenc.decode(codes, disc)
                if not txt.strip():
                    continue
                ls = txt.split("\n")
                segs += 1
                lines += len(ls)
                n = max(n, len(ls))
                w = max(w, max(len(x) for x in ls))
    return w, n, segs, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--check", action="store_true", help="상수를 원본에서 다시 잰다")
    a = ap.parse_args()
    lim = LIMITS[a.disc]
    if not a.check:
        print(f"{a.disc}: 줄 {lim['width']}칸 · 창 {lim['lines']}줄 (상한)")
        return 0
    common.verify_source(a.disc)
    w, n, segs, lines = measure(a.disc)
    print(f"{a.disc}: 조각 {segs:,} · 줄 {lines:,} → 원본 최대 {w}칸 / {n}줄")
    bad = []
    if w > lim["width"]:
        bad.append(f"줄 폭 상한 {lim['width']} < 원본 {w}")
    if n > lim["lines"]:
        bad.append(f"창 줄 수 상한 {lim['lines']} < 원본 {n}")
    for m in bad:
        print(f"  🔴 {m} — 상수를 고치고 문안을 다시 조판한다")
    if not bad and (w, n) != (lim["width"], lim["lines"]):
        print(f"  ⚠ 상한이 원본보다 넉넉하다 ({lim['width']}/{lim['lines']} vs {w}/{n})")
    print(f"{a.disc}: 조판 상수 — {'🔴 원본을 못 담는다' if bad else '✅ 원본을 담는다'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
