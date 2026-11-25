"""章間 자막(`data/kanma_ko.tsv`) 줄바꿈 재조판 — 마스터 11-22 「장종료 이벤트 전체적으로 개행처리 한번 손봐야할듯」.

원문 줄 나눔(음성 맞춤 일본어 줄)을 그대로 따라 한국어 줄이 짧게 끊기고 어절 사이가 갈렸다. 메시지 안 어절을 이어 붙여 **게임 줄바꿈 규칙(`linemetrics.flow` — 문장 끝 > 쉼표 > 연결어미 절째 내리기 ·
본용언+보조용언 · 줄머리 규칙 `local_glue`)** 으로 다시 나눈다. 폭 한도 = 해석기 열 수 18칸(216px, 글자 12 · 공백 4 · 부호 뒤 공백은 부호 칸이 맡는다).
`{wNN}`(대기)·`{fNN}`(얼굴)은 어절에 붙여 가져가므로 말·그림 타이밍의 **순서**는 그대로다. 줄 수가 한도(이름창 3 · 없음 4)를 넘거나 지표가 나빠지면 원문 줄 나눔을 둔다.

    python3 games/pce-ed2/tools/kanma_wrap.py          # 바뀔 메시지 목록(전/후)
    python3 games/pce-ed2/tools/kanma_wrap.py --write  # data/kanma_ko.tsv 에 반영
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import kanma
import linemetrics as L

TSV = kanma.common.GAME_DIR / "data" / "kanma_ko.tsv"
CTRL = re.compile(r"\{[0-9a-fA-F]{2}\}|\{[wf][0-9a-fA-F]{2}\}")
MAX_PX = kanma.MAX_CELLS * kanma.CELL_PX


TITLES = {"대장", "국왕", "왕비", "폐하", "님", "군", "씨", "공", "왕자", "왕자님", "황제", "장군"}  # 이름 뒤 직함 — 줄이 이름과 직함 사이에서 갈리지 않게(마스터 11-22 「가드인 나레사 / 대장에게」)
UNITS = {"년", "명", "개", "층", "번", "세", "세대", "억", "만", "장", "마리", "대"}  # 숫자 + 단위
_NUM = re.compile(r"^[0-9～]+[억만천백]?$")


def kw_glued(a: str, b: str) -> bool:
    """막간 자막에서 줄·쪽을 끊으면 안 되는 쌍 — 이름+직함 · 숫자+단위 · 「이름 N세」(공용 `linemetrics.glued` 에 더해)."""
    bw = re.sub(r"[,.!?…]+$", "", b)
    if re.match(r"^[0-9]+세", b):  # 게일 3세 · 고드윈 2세
        return True
    if bw in TITLES or any(bw.startswith(t) and len(bw) <= len(t) + 2 and bw[len(t) :] in ("께", "에게", "은", "는", "이", "가", "을", "를", "의", "도", "에", "와", "과") for t in TITLES):
        return True
    return bool(_NUM.match(a) and bw in UNITS)


def glued(a: str, b: str) -> bool:
    return L.glued(a, b) or kw_glued(a, b)


def violations() -> list[str]:
    """줄 끝/머리가 `glued` 쌍을 가른 곳(메시지 안 줄 경계) — `kanma.check_ko` 가 부른다. 실패 = 이 목록이 비지 않음."""
    out = []
    for k, (_n, text) in kanma.load_ko().items():
        lines = [CTRL.sub("", ln).strip() for ln in text.split("/")]
        lines = [x for x in lines if x]
        for x, y in zip(lines, lines[1:]):
            wx, wy = x.split(" "), y.split(" ")
            if wx and wy and kw_glued(wx[-1], wy[0]):
                out.append(f"{k}: {x} / {y}")
    return out


def px(line: str) -> int:
    return sum(
        kanma.SPACE_PX if t[0] == "sp" else 2 * kanma.SPACE_PX if t[0] in ("ds", "dg") else kanma.CELL_PX if t[0] == "g" else 0
        for t in kanma.tokenize(CTRL.sub("", line))
    )


def words_of(body: str) -> tuple[bool, list[tuple[str, str, str]]]:
    """본문 표기 → (맨 앞 `/` 여부, [(앞 제어, 글, 뒤 제어)]) — 줄바꿈 `/`·공백이 어절 경계."""
    lead = body.startswith("/")
    if lead:
        body = body[1:]
    out: list[tuple[str, str, str]] = []
    for raw in re.split(r"[ /]", body):
        if not raw:
            continue
        pre = ""
        m = re.match(
            r"^((?:\{[0-9a-fA-F]{2}\}|\{[wf][0-9a-fA-F]{2}\})*)(.*?)((?:\{[0-9a-fA-F]{2}\}|\{[wf][0-9a-fA-F]{2}\})*)$",
            raw,
        )
        pre, txt, post = m.group(1), m.group(2), m.group(3)
        if not txt:  # 글 없는 조각(제어만) — 앞 어절 뒤에 붙인다
            if out:
                a, b, c = out[-1]
                out[-1] = (a, b, c + pre + post)
            else:
                out.append((pre + post, "", ""))
            continue
        out.append((pre, txt, post))
    return lead, out


def _cost(lines: list[list[str]]) -> float:
    """줄 나눔의 나쁜 정도 — 끝 줄 빼고 남는 폭(칸²) · 끊는 자리의 세기(문장 끝 < 쉼표 < 연결어미 < 그 밖) · 갈리는 어절(보조용언·줄머리 규칙) · 끝 줄이 한 어절."""
    c = 0.0
    for i, ln in enumerate(lines):
        w = px(" ".join(ln))
        if w > MAX_PX:
            return 1e9
        last = i == len(lines) - 1
        if not last:
            slack = (MAX_PX - w) / kanma.CELL_PX
            c += slack * slack * 0.6
            k = L.kind(ln[-1])
            c += {3: 0, 2: 2, 1: 4, 0: 9}[k]
            if glued(ln[-1], lines[i + 1][0]):
                c += 100
        else:
            if len(ln) == 1 and len(lines) > 1:
                c += 45
            elif w < 4 * kanma.CELL_PX and len(lines) > 1:
                c += 8
    return c + 3 * len(lines)


def best_lines(texts: list[str], rows: int) -> list[list[str]] | None:
    """어절 열 → 줄 목록 — 줄 수 ≤ rows 에서 `_cost` 최소(동적 계획)."""
    n = len(texts)
    INF = 1e18
    # best[(i, r)] = (비용, 이전 시작) — i 어절까지 r 줄로 나눈 최소 비용(앞 줄 끝 어절 규칙은 줄 단위로 더한다)
    import functools

    @functools.cache
    def go(i: int, r: int):
        if i == n:
            return (0.0, ())
        if r == 0:
            return (INF, ())
        best = (INF, ())
        for j in range(i + 1, n + 1):
            seg = texts[i:j]
            if px(" ".join(seg)) > MAX_PX:
                break
            rest = go(j, r - 1)
            if rest[0] >= INF:
                continue
            cand_lines = [seg, *rest[1]]
            cst = _cost(cand_lines)
            if cst < best[0]:
                best = (cst, tuple(map(tuple, cand_lines)) if False else (seg, *rest[1]))
        return best

    res = go(0, rows)
    if res[0] >= INF:
        return None
    return [list(x) for x in res[1]]


def rewrap(name: str, body: str) -> str | None:
    if re.search(
        r"\{(0[0-9a-fA-F]|1[0-9a-fA-F])\}", body
    ):  # 원문 제어 바이트(`{13}` `{02}`)가 낀 메시지는 건드리지 않는다
        return None
    lead, ws = words_of(body)
    if not ws or any(not t for _a, t, _c in ws):
        return None
    texts = [t for _a, t, _c in ws]
    rows = kanma.MAX_ROWS_NAMED if name else kanma.MAX_ROWS_PLAIN
    lines = best_lines(texts, rows)
    if lines is None:
        return None
    old = [
        [t for t in re.split(" ", CTRL.sub("", seg)) if t] for seg in body.lstrip("/").split("/")
    ]
    if _cost(lines) >= _cost([o for o in old if o]):  # 나아지지 않으면 원문 줄 나눔을 둔다
        return None
    idx = 0
    out_lines = []
    for ln in lines:
        parts = []
        for k in range(len(ln)):
            a, t, c = ws[idx + k]
            parts.append(a + t + c)
        idx += len(ln)
        out_lines.append(" ".join(parts))
    return ("/" if lead else "") + "/".join(out_lines)


def score(name: str, body: str) -> int:
    plain = [CTRL.sub("", ln).strip() for ln in body.split("/")]
    plain = [p for p in plain if p]
    return L.count(L.chunk_metrics([plain])) * 10 + len(plain)


def main(write: bool) -> None:
    lines = TSV.read_text(encoding="utf-8").splitlines()
    out = []
    changed = 0
    for ln in lines:
        f = ln.split("\t")
        if ln.startswith("#") or len(f) < 3:
            out.append(ln)
            continue
        new = rewrap(f[1], f[2])
        if new is not None and new != f[2]:
            changed += 1
            print(f"{f[0]} {f[1]}\n  전  {f[2]}\n  후  {new}")
            f[2] = new
            ln = "\t".join(f)
        out.append(ln)
    print(f"바뀐 메시지 {changed}")
    if write:
        TSV.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main("--write" in sys.argv)
