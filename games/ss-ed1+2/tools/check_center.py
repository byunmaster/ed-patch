"""가운데 맞춤을 실제 픽셀 폭으로 잰다 — 번역 규칙 2-8 (줄 끝 `.` `,` `…` 는 폭에서 뺀다).

    python3 tools/check_center.py            # 표 + 기준선 대조 (실패 부류가 0 이 아니면 종료코드 1)
    python3 tools/check_center.py --show 8

## 자리 (가운데 맞춤이 있는 곳)

- **오프닝·엔딩 자막**(`TITLE.BIN`, `patch_title.Composer.tiles`가 줄마다 비례 폭으로 놓는다) — 실제로 놓인 x 에서 좌우 여백을 재서
  차가 1px 를 넘는 줄을 센다. 가운데가 아닌 줄(원판 손배치 · 오른쪽 맞춤 · 원문 그대로인 스태프롤)은 `row_left` 가 가른다.
- **장 카드**(`第N章 …` / `完`, 씬 창 글자 칸) — 원판 줄의 가운데를 이어받는다. 칸(공백)은 반각 8px 단위라 가운데를 ±4px 이내로만
  놓을 수 있다(좌우 여백 차 8px) — 그 한계 안에서 **더 가까운 칸 수가 있는데 어긋난 줄**을 센다.
- 그림 판(타이틀 로고 · 알약 메뉴 · 장 판 · HUD)은 코드가 잉크 상자를 정수 나눗셈으로 놓아 여백 차가 1px 이하다(구조) — 이 게이트 몫이 아니다.

## 실패(0 이어야 하는 것)

    자막 가운데 어긋남   좌우 여백 차 > 1px (줄 끝 부호 제외 폭 기준)
    카드 칸 어긋남       더 가까운 공백 수가 있는데 다른 칸 수를 썼다(같은 거리면 왼쪽 — 최근접·동점 왼쪽, 마스터 11-09)
    장 제목 판 왼쪽 큼 · 최근접 아님   판 줄의 좌>우, 또는 우−좌 ≥ 2px(1px 단위라 차 ≤ 1 이 최근접, 동점은 왼쪽)
    카드 번호-제목 간격  `제N장`과 제목 사이가 전각 공백 한 칸(반각 2칸)이 아니다 — 규칙 2-8(마스터 11-03)
## 보고

    카드 한계(칸 8px·원문 바이트)      공백 단위(8px)로는 더 못 맞추는 카드 수 (좌우 여백 차 8px)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_title as PT
import patch_ui
import typeset_scn as T

FAIL = (
    "자막 가운데 어긋남",
    "카드 칸 어긋남",
    "카드 번호-제목 간격",
    "카드 끝 커서 어긋남",
    "장 제목 판 왼쪽 큼",
    "장 제목 판 최근접 아님",
)
REPORT = ("카드 한계(칸 8px·원문 바이트)", "카드 왼쪽 8px 초과(원문 바이트 한계)")
BASELINE = os.path.join(common.GAME_DIR, "center_baseline.json")
CELL = 8  # 공백 한 칸 = 반각 8px


def px(t):
    """씬 창 글자 폭(px) — 반각 8 · 전각(한글 포함) 16."""
    return sum(16 if ord(c) >= 0x80 else 8 for c in t)


def card_line(s):
    """카드 문자열 → (왼쪽 여백 px, 본문 px). 앞의 `\\t` 는 칸에 안 센다."""
    l1 = s.split("\n")[0].lstrip("\t")
    return (len(l1) - len(l1.lstrip(" "))) * CELL, px(l1.strip(" "))


def title_margins(x, total, trail, cap):
    """자막 한 줄이 놓인 자리 → (왼쪽 여백, 오른쪽 여백) px — 줄 끝 `.` `,` `…`(`trail`)는 글자 폭에서 뺀다."""
    return x, cap - x - (total - trail)


def nbytes(t):
    """굽는 바이트 — 전각(한글 포함) 2 · 반각 1 · `%c` 는 2 (`typeset_scn._chapter_card` 와 같은 잣대)."""
    return sum(2 if "\x80" <= c else 1 for c in t.replace("%c", "XX"))


def card_verdict(jp, kr):
    """원판 줄의 가운데를 이어받았나 → (더 나은 칸 수가 있는데 어긋난 줄인가, 여백 차 px).

    더 나은 칸 수는 **원문 바이트 칸 안**에서만 센다 — 넘기면 카드가 이주해 다른 자리를 먹는다(`typeset_scn._chapter_card`)."""
    jl, jw = card_line(jp)
    kl, kw = card_line(kr)
    want = jl + (jw - kw) / 2  # 가운데를 지키는 왼쪽 여백(px)
    pad = kl // CELL
    room = nbytes(jp) - (nbytes(kr) - pad)  # 칸에 쓸 수 있는 공백 수의 상한
    best = min(abs(want - k * CELL) for k in range(max(room, 0) + 1))
    got = abs(want - kl)
    # 🔴 최근접(마스터 11-09 「최대한 가운데」) — 같은 거리가 둘이면 **왼쪽만**(규칙 2-8): 같은 거리의 더 왼쪽 칸이 있는데 오른쪽을 골랐으면 어긋난 것
    tie_right = (
        abs(got - best) < 1e-9
        and kl > want + 1e-9
        and any(
            abs(abs(want - k * CELL) - best) < 1e-9 and k * CELL < kl
            for k in range(max(room, 0) + 1)
        )
    )
    return got > best + 1e-9 or tie_right, round(2 * got, 1)


def scan():
    hits = {k: [] for k in FAIL + REPORT}
    n_title = n_card = 0
    # ── 자막
    _f, mm = common.open_image()
    raw = PT._load(mm)
    mm.close()
    _f.close()
    with open(os.path.join(common.GAME_DIR, "script", "title.json"), encoding="utf-8") as f:
        kr = json.load(f)
    comp = PT.Composer()
    for name, i, _p, t, width, _nb in PT.plan(raw):
        idx = len(kr[name]) - 1 - i
        line = kr[name][idx]
        left = PT.row_left(name, idx, line, t, width)
        if left is not None or not line.strip():
            continue
        comp.tiles(line, width, None)
        lm, rm = title_margins(*comp.last_place)
        n_title += 1
        if abs(lm - rm) > 1:
            hits["자막 가운데 어긋남"].append(f"{name} #{idx} {line!r}: 왼 {lm}px · 오른 {rm}px")
    # ── 장 카드
    _f, mm = common.open_image()
    try:
        cards = patch_ui._cards()
        rows = patch_ui.card_rows(mm, cards)
    finally:
        mm.close()
        _f.close()
    for r in rows:
        jp, ui_kr = r[5], r[6]
        # 🔴 「씬」 변형(`_scene_card` — 원문 바이트에 맞춰 공백을 덜어 낸 꼴)은 **빌드에 안 나온다**(11-09 실측: 살아 있는 카드 열의 앞 공백 수가 「메뉴」 변형과 전부 같다 —
        #    ED1 6장·ED2 4장, ED2 의 이주 사본은 포인터 +1(탭 자리)을 이어받아 같은 칸 수로 보인다). 안 나오는 변형을 재면 가짜 −16px 이 났다 → 메뉴 변형만 잰다.
        for how, kr_s in (("메뉴", ui_kr),):
            if kr_s is None:
                continue
            n_card += 1
            # 「끝」은 아래 커서(▽)에 맞춘다(마스터 11-09) — 끝 앞 반각 공백이 커서 기준 고정 수여야 한다(실화면 측정: 14칸 → 끝 중심이 커서 중심 +2px, 최근접)
            _l2 = kr_s.split("\n")[-1].replace("%c", "")
            if _l2 != " " * patch_ui.CARD_END_SPACES + "끝":
                hits["카드 끝 커서 어긋남"].append(f"{how} {kr_s.split(chr(10))[0].strip()!r}: 끝 줄 {_l2!r}")
            if not re.fullmatch(
                r"[\t ]*(?:제[０-９]+장|서장|종장)\u3000[^\s\u3000].*", kr_s.split("\n")[0]
            ):  # 규칙 2-8 — 번호–제목 사이는 전각 1칸(반각 2칸) 고정
                hits["카드 번호-제목 간격"].append(f"{how} {kr_s.split(chr(10))[0].strip()!r}")
            jl_, jw_ = card_line(jp)
            kl_, kw_ = card_line(kr_s)
            if (
                kl_ < jl_ + (jw_ - kw_) / 2 - CELL / 2 - 1e-9
            ):  # 좌−우 < −8px — 8px 칸 하나 더 오른쪽이 가능하면 그쪽(원문 바이트가 모자라면 보고만)
                hits["카드 왼쪽 8px 초과(원문 바이트 한계)"].append(
                    f"{how} {kr_s.split(chr(10))[0].strip()!r}: 좌−우 {2 * (kl_ - (jl_ + (jw_ - kw_) / 2)):g}px"
                )
            off, diff = card_verdict(jp, kr_s)
            tag = f"{how} {kr_s.split(chr(10))[0].strip()!r}"
            if off:
                hits["카드 칸 어긋남"].append(f"{tag}: 여백 차 {diff}px")
            elif diff > 1:
                hits["카드 한계(칸 8px·원문 바이트)"].append(f"{tag}: 여백 차 {diff}px")
    _plate_scan(hits)
    return n_title, n_card, hits


def _plate_scan(hits):
    """장 제목 판(빌드 이미지의 192×40 그림) — 줄마다 잉크 좌·우 여백, 왼쪽이 더 크면 실패(규칙 2-8, 11-09). 빌드가 없으면 건너뛴다."""
    import glob

    import numpy as np
    import patch_gfx_cards as G

    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        return
    f, mm = common.open_image(img[0])
    try:
        files = {p: (lba, sz) for p, lba, sz in common.iso_files(mm)}
        ps, pal = G.plates(mm, files)
    finally:
        mm.close()
        f.close()
    for path, i, _start, px_ in ps:
        ink = (pal[px_].astype(int) >= 225).all(axis=2)
        ys = np.where(ink.any(axis=1))[0]
        groups, cur = [], [ys[0]]
        for y in ys[1:]:
            if y - cur[-1] > 2:
                groups.append(cur)
                cur = [y]
            else:
                cur.append(y)
        groups.append(cur)
        for g in groups:
            xs = np.where(ink[g[0] : g[-1] + 1].any(axis=0))[0]
            lm, rm = int(xs.min()), 191 - int(xs.max())
            if lm > rm:
                hits["장 제목 판 왼쪽 큼"].append(f"{path} #{i}: 좌 {lm}px · 우 {rm}px")
            elif rm - lm >= 2:  # 1px 단위로 놓을 수 있으니 최근접이면 차 ≤ 1(같은 거리는 왼쪽)
                hits["장 제목 판 최근접 아님"].append(f"{path} #{i}: 좌 {lm}px · 우 {rm}px")


def _scene_card(jp, cards):
    """씬 경로(`typeset_scn._chapter_card`)가 짓는 같은 카드 — 칸 수를 덜어 낸 뒤의 꼴."""
    for cjp, ch, ti in cards:
        if cjp in jp:
            return T._chapter_card(jp, f"{ch}　{ti}\n\n끝")
    return None


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    nt, nc, hits = scan()
    cur = {k: len(hits[k]) for k in FAIL + REPORT}
    print(
        f"  가운데 맞춤 2-8 [자막 {nt} · 카드 {nc}] — "
        + " · ".join(f"{k} {cur[k]}" for k in FAIL)
        + "  (보고: "
        + " · ".join(f"{k} {cur[k]}" for k in REPORT)
        + ")"
    )
    for k in FAIL + REPORT:
        for x in hits[k][:show]:
            print(f"      [{k}] {x}")
    if "--freeze" in sys.argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"  ✍ 기준선 갱신 {cur}")
        return 0
    bad = [k for k in FAIL if cur[k]]
    if bad:
        print("  🔴 가운데가 어긋난 줄이 있다 — " + " · ".join(f"{k} {cur[k]}" for k in bad))
        return 1
    try:
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    except OSError:
        print("  ⚠ 기준선 없음 — `--freeze` 로 만든다 (안 쟀다는 통과가 아니다)")
        return 1
    k2 = "카드 왼쪽 8px 초과(원문 바이트 한계)"
    if cur[k2] > base.get(k2, 0):
        print(f"  🔴 왼쪽 8px 초과 카드가 늘었다 {base.get(k2, 0)}→{cur[k2]}")
        return 1
    if cur["카드 한계(칸 8px·원문 바이트)"] > base.get("카드 한계(칸 8px·원문 바이트)", 0):
        print(
            f"  🔴 반 칸 한계 카드가 늘었다 {base.get('카드 한계(칸 8px·원문 바이트)', 0)}→{cur['카드 한계(칸 8px·원문 바이트)']}"
        )
        return 1
    print("  ✅ 가운데 맞춤 — 어긋난 줄 0 · 보고 부류는 기준선 이하")
    return 0


if __name__ == "__main__":
    sys.exit(main())
