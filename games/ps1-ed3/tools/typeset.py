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
import hashlib
import json
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
# 대사에서 부호 뒤 공백을 지우던 규약(`docs/reference/translation-conventions.md`, 옛 값 ".,")은 **ED3 에선 접는다**(마스터 10-07).
# 이유: 부호가 반 칸(6px)이 되며 「부호 12px 하나」가 「부호 6px + 공백 6px」과 폭이 같아졌다 — 공백을 남겨도 한 줄 폭이 그대로고,
#   지우면 「티나,내일」처럼 붙어 읽기 나쁘다(실측 캡처 `halfspace/P01`). ED4 는 엔진 패치가 없어 부호가 12px 라 아직 옛 규약이 맞다.
STRIP_AFTER = {"ed3": "", "ed4": ".,"}


CELL_PX = 12  # 화면에서 코드 하나가 차지하는 가로 픽셀 (`font.PITCH`)
# 코드별 폭(px). 🔴 엔진 패치(`engine_patch`)가 있는 디스크만 12 가 아닌 값을 가질 수 있다 —
#   공백 8px → 6px(반 칸): 유저 판정 2026-09-07 은 「한글 전각·공백만 반각」, 마스터 10-07 「대사창 공백 반각」 — 8px 는 2/3 칸이라 절반(6px)으로 내린다.
# 반각(6px): 공백 · `. , ? !` · `( )` — `… ～ 「」` 는 전각 유지(마스터 10-07: 점 셋 한 글리프·반각이면 모양이 안 남).
WIDTHS = {"ed3": {c: 6 for c in " .,?!()"}, "ed4": {}}
# 한 줄에 들어가는 글리프 수의 상한 = 스프라이트 격자 열 수(`engine_patch.COLS`). 패치 없으면 None.
COLS = {"ed3": 24, "ed4": None}  # 🔴 32 가 아니다 — `engine_patch.COLS` 머리말 참조(▼ 결함)


def cell_width(ch, disc="ed3"):
    """이 게임의 슬롯 폭 — 공백만 8/12, 나머지 1.

    ⚠ 공용 기본값(`krwrap.default_cell_width`)은 공백을 **0.5**로 센다. 그건 PS1 ED1+2 의
      규격이고 여기선 틀린다 — 이 게임엔 공백 코드가 아예 없어서 **빈 글리프를 한 자리
      구워 쓴다**(`hangul_map.EXTRA`). 엔진 패치가 공백을 6px(반 칸)로 보내니 그만큼(1/2)이다.
    """
    return WIDTHS[disc].get(ch, CELL_PX) / CELL_PX


def width_cells(text, disc="ed3"):
    """한 줄의 폭(칸, 소수). 부호 뒤 공백 제거 전 값이라 안전측이다."""
    return sum(cell_width(ch, disc) for ch in text)


def _extra_lines():
    """{원문 지문: 줄 수} — 한 줄 예산인 조각 중 **두 줄로 푸는 것**(`extra_lines.json`, 지문만 — 원문은 안 둔다).

    엔진엔 대사 개행이 없고 글자가 **격자 24칸째에서 저절로 접힌다**(시험 롬 실측 10-18, 접히는 자리는 글자 수(공백 포함)로 정해진다 —
    슬롯 폭이 아니다). 그래서 24글리프를 넘는 번역은 한 줄로 못 맞추지만, 첫 줄을 **공백 글리프로 24칸까지 채우면** 다음 어절이
    둘째 줄 머리에서 시작한다(`pad_rows`). 창은 4행이라 둘째 줄이 창 안에 그려지고 쪽 넘김도 정상이다."""
    path = os.path.join(common.ROOT, "extra_lines.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


EXTRA_LINES = _extra_lines()


def pad_rows(text, disc):
    """두 줄 조각을 **구울 꼴**로 — 첫 줄을 공백 글리프로 격자 열까지 채우고 개행은 없앤다(엔진이 24칸째에서 접는다).

    줄이 하나뿐이면 그대로다. 줄 수는 `extra_lines.json` 이 정한 조각만 둘이 된다."""
    rows = text.split("\n")
    if len(rows) == 1:
        return text
    cols = COLS[disc]
    if len(rows) != 2 or not cols or len(rows[0]) > cols:
        raise TypesetError(f"두 줄을 격자에 못 맞춘다: {text!r}")
    return rows[0] + " " * (cols - len(rows[0])) + rows[1]


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
    n = min(max(len(ls), 1), lim["lines"])
    if jp is not None:
        n = max(n, EXTRA_LINES.get(hashlib.sha1(jp.encode("utf-8")).hexdigest()[:8], 0))
    return min(w, lim["width"]), n


# ── 창 단위 재조판(마스터 10-20 「어절단위 개행」 · 규칙 2-6·2-10) ──────────────────────────────────
# 한 창 = `0F 90 V (01 90 W)* 00` 시퀀스 하나이고, 조각 하나가 한 줄이다(조각이 빈 꼬리면 그 줄은 안 그려진다 — 10-20 실측).
# 원문 줄 구조를 따르지 않고 창 문장을 이어 **창 폭(24글리프)을 채워** 어절 경계에서 다시 나눈다. 쪽(=시퀀스) 경계는 그대로.
BIND = "\ue000"  # 띄어 쓴 정본 이름의 공백을 임시로 바꾸는 사적 문자(줄바꿈 금지) — 끝나면 공백으로 되돌린다


def _bind_names():
    """[(이름, 묶은 이름)] — 정본 nouns 중 공백이 든 이름(긴 것부터)."""
    from shared import canon

    names = sorted({kr for _c, _jp, kr in canon.all_names("ed3") if " " in kr}, key=len, reverse=True)
    return [(n, n.replace(" ", BIND)) for n in names]


_BOUND = None


def _cw(ch, disc):
    return cell_width(" " if ch == BIND else ch, disc)


def _fits(line, disc, cols):
    return len(line) <= cols and sum(_cw(c, disc) for c in line) <= cols


def reflow(texts, disc="ed3", cols=None):
    """창 하나의 조각들 → 같은 개수의 조각(앞에서부터 한 줄씩, 남는 꼬리는 빈 문자열). 못 하면 None(원래 구조 유지).

    규칙: 문장을 이어 놓고 ① 앞 줄 남은 칸에 문장이 **통째로** 들어가면 거기 잇고(2-10) ② 아니면 새 줄에서 시작하며 ③ 한 줄보다
    긴 문장만 어절 경계로 나눈다(2-6). 띄어 쓴 정본 이름은 한 어절로 묶는다. 줄이 조각 수보다 늘면 None.
    변수가 끼는 창(조각 앞뒤 공백 · 런타임 조사 표지 · 병기 `(이)` · 개행)은 건드리지 않는다."""
    global _BOUND
    import josa_rt

    cols = cols or COLS[disc] or 24
    if any(
        not t or t != t.strip(" ") or "\n" in t or josa_rt._TOKEN.search(t) or t[0] in josa_rt.MARKER_CHARS or t.startswith("\u3000")
        for t in texts
    ):
        return None
    if _BOUND is None:
        _BOUND = _bind_names()
    para = " ".join(texts)
    for name, bound in _BOUND:
        para = para.replace(name, bound)
    rows, cur = [], ""
    for sent in krwrap.split_sentences(para):
        cand = f"{cur} {sent}" if cur else sent
        if _fits(cand, disc, cols):
            cur = cand
        elif _fits(sent, disc, cols):
            rows.append(cur)
            cur = sent
        else:  # 한 줄보다 긴 문장 — 새 줄에서 시작해 어절 경계로 나눈다(2-10: 앞 줄에 통째로 안 들어가면 새 줄)
            if cur:
                rows.append(cur)
            width = float(cols)
            while True:
                out = krwrap.wrap(
                    sent,
                    width=width,
                    cell_width=lambda ch: _cw(ch, disc),
                    strip_after=STRIP_AFTER[disc],
                )
                if all(_fits(x, disc, cols) for x in out) or width <= 4:
                    break
                width -= 0.5
            if not all(_fits(x, disc, cols) for x in out):
                return None
            rows += out[:-1]
            cur = out[-1]
    if cur:
        rows.append(cur)
    rows = [r.replace(BIND, " ") for r in rows]
    if len(rows) > len(texts) or "".join("".join(rows).split()) != "".join("".join(texts).split()):
        return None
    return rows + [""] * (len(texts) - len(rows))


class TypesetError(Exception):
    pass


def wrap(text, disc, jp=None, width=None, lines=None, floor=0):
    """우리 문안 → 줄로 나눈 문안(`\\n` 포함).

    `jp` 를 주면 그 조각의 원문이 쓴 폭·줄 수를 예산으로 삼는다(권장). 멤버 대사는 `floor`
    (`script.member_floors`)도 준다 — 검사기(`script.py --check`)와 **같은 자**여야 한다.

    🔴 **예산을 넘으면 운다 — 자르지 않는다.** 예전엔 넘친 줄을 `out[:lines]` 로 버렸고, 빌드가
       `floor` 없이 불러 **ED3 37줄 · ED4 59줄의 꼬리가 조용히 사라졌다**(09-27, 화면 실측:
       `...아무튼,` · `을(를)` 에서 끊김). 검사기는 `floor` 를 줘서 0건이라 했다.
    🔴 **앞뒤 공백은 지키지 않고 남긴다.** 조각은 엔진이 끼우는 아이템 이름·숫자와 **한 줄로**
       이어 붙는다(스크립트 opcode `0x04`·`0x05`·`0x07`) — `쥬리오는 ` + [아이템] 의 공백을
       `split()` 이 먹으면 `쥬리오는短剣` 으로 붙는다.
    """
    if not text.strip():
        return ""
    lead = text[: len(text) - len(text.lstrip(" "))]
    trail = text[len(text.rstrip(" ")) :]
    if width is None or lines is None:
        w, n = (
            budget(disc, jp, floor)
            if jp is not None
            else (LIMITS[disc]["width"], LIMITS[disc]["lines"])
        )
        width = width if width is not None else w
        lines = lines if lines is not None else n
    cols = COLS[disc]
    while True:
        out = krwrap.wrap(
            text.replace("\n", " "),
            width=width,
            cell_width=lambda ch: cell_width(ch, disc),
            strip_after=STRIP_AFTER[disc],
        )
        # 🔴 슬롯 폭 안이어도 **글리프(공백 포함)가 격자 열을 넘으면** 엔진이 어절 한복판에서 접는다 — 줄 수 여유가 있을 때만
        #    폭을 반 칸씩 줄여 어절 경계에서 접는다(여유가 없으면 아래에서 운다 / 한 줄이면 `violations` 가 잡는다).
        if not cols or len(out) >= lines or max(len(x) for x in out) <= cols or width <= 4:
            break
        width -= 0.5
    if len(out) > lines:
        raise TypesetError(f"{len(out)}줄 > 예산 {lines}줄 (폭 {width:g}): {text!r}")
    res = lead + "\n".join(out) + trail
    if "".join(res.split()) != "".join(text.split()):  # 불변식: 조판은 공백·개행만 옮긴다
        raise TypesetError(f"글이 바뀌었다: {text!r} → {res!r}")
    return res


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
