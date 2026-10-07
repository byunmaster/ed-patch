"""조판 — 번역문을 대사창(17칸)에 맞게 어절 단위로 개행하고(빌드가 부른다), 결과를 실제 후보로 흘려 검사한다.

SFC 대사창은 **17칸 × 4줄 칸 배열**이고 엔진이 글자마다 칸 번호를 하나씩 올린다(`$02:DE73`) — 17칸째에서
**단어와 상관없이 기계적으로** 다음 줄로 넘어가고, 68칸을 넘으면 한 줄 올린다(`$02:DE23`). 개행 `$CF`(`\\n`)는
칸 번호를 「지금 줄의 끝 칸」으로 옮길 뿐이라(`$02:DE4F`) **17칸을 꽉 채운 직후의 개행은 빈 줄을 안 만든다**
(2026-09-27 코드 판독). 그래서 조판 위반은 거의 다 「줄이 넘쳐 기계적으로 넘어간 자리」에서 생긴다:
  ① 고아 온점 — 줄 첫 칸이 `. , ! ? …` 류          ② 빈 줄 — 겹친 개행(엔진이 무시해 의도가 샌다) · 쪽 첫머리 개행
  ③ 줄 첫 칸 공백 — 넘친 자리가 공백                 ④ 묶음 끊김 — 넘친 자리가 **어절 한가운데**
⇒ **조판기(`wrap`)**: 명시 개행 사이의 한 줄을 어절로 채우다가 17칸을 넘을 어절 앞 공백을 개행으로 바꾼다.
런타임 치환(`{D6}` 인물 · `{D7}` 대상 · `{D8}` 파티 · `{D9}` 도구 · `{DB}` 주문+레벨 · `{DC}` 수 · `{DD}` 장소)은
**가장 긴 후보 폭**으로 센다 — 짧은 이름이면 줄이 조금 일찍 꺾일 뿐 넘치지 않는다(결정적 · 정본 `textmap` 은 안 바꾼다).
부호는 어절에 붙어 있으니 ① 은 넘침이 없으면 안 생긴다. 한 어절이 17칸을 넘으면 조판기로도 못 막는다(보고).
오프닝·엔딩 크롤(`$0B:E8E5~$0B:F337`)은 다른 엔진(`open_fetch`)이고 줄을 손으로 맞춰 마스터 확인을 받았다 — 안 건드린다.

🔴 **마스터 최종 판정(2026-10-07, 전 기종 공통) — 09-27③ 번복.** 로그성 메시지(도구·주문 사용 등,
`FIELD`)도 **다른 영역과 똑같이 어절 단위 개행을 한다.** 09-27③ 「엔진 글자 단위 개행만, 어절 조판은
영구 취소」는 대체됐다 — `Typesetter.__call__`·`check_all()` 둘 다 이제 `FIELD` 를 안 건너뛰고 `wrap()`
을 건다(다만 FIELD 는 런타임 치환 후보가 **파티원뿐**이라 후보 폭표를 따로 쓴다 — `ml_field`). 엔진의
①③ 훅(`kinsoku_carry`·재진입, hook.py)은 **그대로 둔다** — 어절 조판이 못 막는 나머지 자리(한 어절이
17칸을 넘는 극단값 등)의 안전망이다. ④ 묶음 끊김은 더 이상 FIELD 라고 봐주지 않는다 — 다른 영역과
같이 0이어야 한다.

    python3 tools/typeset.py            # 전 영역 위반 수(시스템·전투·씬) + 예
    python3 tools/typeset.py --check    # tm-draft 제외 「본질 위반」이 있으면 실패
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: F401, I001
import common
import hook
import namesrc

COLS = 17
NO_HEAD = set(".,!?…:;)」』")
CRAWL = (0x0BE8E5, 0x0BF337)  # 오프닝·엔딩 크롤 — 다른 엔진, 조판하지 않는다
FIELD = {
    0x07A740,
    0x07A7FB,
    0x07A81F,
    0x07A84F,
    0x07A865,
    0x07A876,
    0x07A887,
    0x07A89D,
    0x07A8B3,
    0x07A8F8,
    0x07A910,
    0x07A99F,
    0x07A9B1,
    0x07A9BF,
    0x07AA5F,
    0x07AAAD,
    0x07AB61,
    0x07AC5D,
    0x07AD1A,
    0x07AD2E,
    0x07AD44,
}  # fmt: skip — 필드에서 도구·주문을 쓸 때 나오는 조립형(`field-use-messages.md` ★) — 게이트
BATTLE = (0x07A721, 0x07C7FF)  # 시스템·전투 메시지 덩이(필드 ★ 를 뺀 나머지는 전투 쪽으로 센다)


def _dict() -> dict[str, str]:
    d = namesrc.dict_map()
    return {k: v["kr"] for k, v in d.items()}


def candidates(dm: dict[str, str] | None = None, field: bool = False) -> dict[str, list[str]]:
    """런타임 치환 후보. `field=True` 면 필드 도구·주문 메시지용 — 쓰는 이도 받는 이도 **파티원뿐**이다.
    ⚠ 전투용 후보(몬스터 이름 포함)로 필드 문장을 재면 「아크담의 부하」 폭에 맞춰 짧은 이름도 일찍 꺾인다
    (2026-09-27 마스터 판정 — 로그성 메시지는 넘칠 때만 꺾는다)."""
    dm = dm or _dict()
    party = ["세리오스", "류난", "로우", "게일", "소니아"]
    monsters = sorted({v for k, v in dm.items() if k.startswith("D3:")})
    items = sorted({v for k, v in dm.items() if k.startswith("D2:")})
    spells = sorted({v for k, v in dm.items() if k.startswith("D4:")})
    places = namesrc.places_map()
    people = party if field else party + monsters
    return {
        "D6": people,
        "D7": people + ["자신"],
        "D8": party,
        "D9": items,
        "DB": [s + str(n) for s in spells for n in (1, 2, 3)],
        "DC": ["1", "2", "5", "10", "12", "99", "120", "999", "1285", "9999", "65535"],
        "DD": sorted(set(places["names"].values())),
    }


def representatives(vals: list[str]) -> list[str]:
    """길이마다 받침 있음/없음 대표 하나씩 — 조판은 길이와 조사 길이만 탄다."""
    seen: dict[tuple[int, bool], str] = {}
    for v in vals:
        seen.setdefault((len(v), hook.has_batchim(v[-1])), v)
    return list(seen.values())


def maxlens(cand: dict[str, list[str]]) -> dict[str, int]:
    return {k: max(len(v) for v in vals) for k, vals in cand.items()}


TOK = re.compile(
    r"\{(D[6-9A-F])\}|\{(D[0-5]:[0-9A-F]{2})\}|\{([^}]*/[^}]*)\}|<[^>]*>|\n|.", re.DOTALL
)


# ── 조판기 ─────────────────────────────────────────────────────────────────────────────
def wrap(kr: str, dm: dict[str, str], maxlen: dict[str, int]) -> str:
    """명시 개행·페이지 사이 한 줄을 어절로 채우다가 17칸을 넘을 어절 앞 공백을 `\\n` 으로 바꾼다."""
    atoms: list[tuple[str, int]] = []  # (원문 조각, 폭) — 폭 -1 = 줄 초기화(개행·페이지·창 지움)
    for m in TOK.finditer(kr):
        s = m.group(0)
        if m.group(1):
            atoms.append((s, maxlen[m.group(1)]))
        elif m.group(2):
            atoms.append((s, len(dm.get(m.group(2), ""))))
        elif m.group(3):
            atoms.append((s, max(len(x) for x in m.group(3).split("/"))))
        elif s == "\n" or s in ("<EF>", "<FF>"):
            atoms.append((s, -1))
        elif s.startswith("<"):
            atoms.append((s, 0))
        else:
            atoms.append((s, 1))
    out: list[str] = []
    col = 0
    for i, (s, w) in enumerate(atoms):
        if w == -1:
            out.append(s)
            col = 0
        elif s == " ":
            j, ww = i + 1, 0  # 다음 어절 폭
            while j < len(atoms) and atoms[j][0] != " " and atoms[j][1] != -1:
                ww += atoms[j][1]
                j += 1
            if col and col + 1 + ww > COLS:
                out.append("\n")
                col = 0
            else:
                out.append(" ")
                col += 1
        else:
            out.append(s)
            col += w
    res = "".join(out)
    lossless(kr, res)
    return res


class TextLost(RuntimeError):
    """조판이 글을 잃거나 바꿨다 — 빌드를 멈춘다(`build.py` 의 `except ValueError` 에 안 먹히게 따로 둔다)."""


def lossless(kr: str, res: str) -> None:
    """🔴 「글 소실 없음」 불변식 — 조판기가 하는 일은 **공백 하나를 개행 하나로 바꾸는 것뿐**이다.

    그래서 길이가 같고, 다른 자리는 전부 `' ' → '\\n'` 이어야 한다(공백·개행을 뺀 글자 열이 같다는 것보다 세다).
    PS1 에서 어절 단위로 물러나 끊는 수정이 특정 폭에서 꼬리 글을 잃었는데 검사기가 폭·위반만 봐서 못 잡았다(09-27 관리자 공유).
    """
    bad = len(kr) != len(res) or any(
        a != b and (a, b) != (" ", "\n") for a, b in zip(kr, res, strict=False)
    )
    if bad:
        raise TextLost(f"조판이 글을 바꿨다: {kr!r} → {res!r}")


class Typesetter:
    """빌드가 쓰는 입구 — 사전·후보 폭을 한 번만 읽는다."""

    def __init__(self) -> None:
        self.dm = _dict()
        self.ml = maxlens(candidates(self.dm))
        self.ml_field = maxlens(candidates(self.dm, field=True))

    def __call__(self, kr: str, addr: int) -> str:
        if CRAWL[0] <= addr <= CRAWL[1]:
            return kr
        # 마스터 최종 판정(2026-09-30, 전 기종 공통) — 로그성 메시지도 어절 단위 개행을 한다
        # (09-27③ 「엔진 기계적 개행만」을 대체). FIELD 는 후보 폭이 파티원뿐이라 더 좁다.
        ml = self.ml_field if addr in FIELD else self.ml
        return wrap(kr, self.dm, ml)


# ── 검사 ───────────────────────────────────────────────────────────────────────────────
def expand(kr: str, vals: dict[str, str], dm: dict[str, str]) -> list[tuple[str, str]]:
    """번역문 → (글자, 묶음 표지) 열. 같은 표지의 이웃 사이에서 넘치면 ④."""
    out: list[tuple[str, str]] = []
    unit = 0
    for m in TOK.finditer(kr):
        s = m.group(0)
        if m.group(1) or m.group(2):
            unit += 1
            src = vals[m.group(1)] if m.group(1) else dm.get(m.group(2), "?")
            out += [(ch, f"u{unit}") for ch in src]
        elif m.group(3):
            prev = next((c for c, _u in reversed(out) if c.strip()), "")
            a, b = m.group(3).split("/")
            pick = a if prev and hook.has_batchim(prev) else b
            tag = out[-1][1] if out else "j"
            out += [(ch, tag) for ch in pick]
        elif s == "\n":
            out.append(("\n", ""))
        elif s.startswith("<"):
            if s in ("<EF>", "<FF>"):
                out.append(("\f", ""))
        else:
            out.append((s, ""))
    word, res = 0, []
    for ch, u in out:
        if ch in (" ", "\n", "\f"):
            word += 1
            res.append((ch, u))
        else:
            res.append((ch, u or f"w{word}"))
    return res


def newline_cursor(c: int) -> int:
    """개행 `$CF` 가 칸 번호 `$173B`(마지막으로 쓴 칸)를 옮기는 값 — `$02:DE53~DE6D` 를 8비트 그대로 옮겼다.

    `c // 17` 줄의 끝 칸으로 간다. 쪽 첫머리는 `$173B = $FF` 라 **15**(다음 글자가 첫 줄 16칸째)가 된다.
    """
    x, a = -1, c
    while True:
        x += 1
        if a - 17 < 0:
            break
        a -= 17
    a = 0
    for _ in range(x + 1):
        a += 17
    return (a - 1) & 0xFF


def layout(chars: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """엔진처럼 흘린다 → (줄들, 위반 목록).

    칸 번호는 엔진과 같게 센다 — 글자는 +1(17칸째를 넘으면 기계적으로 다음 줄), 개행은 `newline_cursor`.
    ⇒ **꽉 찬 줄 뒤 개행은 빈 줄을 안 만들고**, 겹친 개행 `\\n\\n` 도 둘째가 아무 일도 안 한다(같은 끝 칸) —
    SFC 에선 개행으로 빈 줄을 **못** 만든다. 그래서 ② 는 「빈 줄을 의도했는데 화면엔 안 생기는」 자리와
    「쪽 첫머리 개행(다음 글자가 16칸째로 튄다)」을 잡는다.

    🔴 **마스터 최종 판정(2026-09-27④) — 엔진 훅(`hook.kinsoku_carry` · `h_kspace`/`hb_kspace`)이
    ①③을 실제로 막는다.** 이 시뮬레이션도 같은 규칙으로 움직인다: 줄 첫 칸이 될 공백은 칸을 안 쓰고
    버리고, 줄 첫 칸이 될 부호(`NO_HEAD`)는 **겹쳐 그리기 없이** 이전 줄 마지막 글자를 새 줄 첫 칸으로
    옮기고 부호는 그 다음 칸에 놓는다(이전 줄은 한 칸 짧아진 채 끝) — 값으로 확인: `hook.py` 의
    `kinsoku_carry` 라이브 트레이스, `r5-kinsoku-*.png`.
    """
    lines: list[list[tuple[str, str]]] = [[]]
    bad: list[str] = []
    c = 0xFF  # 쪽 첫머리(`$173B = $FF`)
    explicit = False  # 방금 줄이 개행으로 끝났나(기계적 넘침과 가른다)
    i = 0
    n = len(chars)
    while i < n:
        ch, u = chars[i]
        if ch == "\f":
            lines.append([])
            c, explicit = 0xFF, False
            i += 1
            continue
        if ch == "\n":
            if c == 0xFF:
                bad.append("② 쪽 첫머리 개행")
            elif i and chars[i - 1][0] == "\n":
                bad.append("② 빈 줄(겹친 개행 — 엔진은 무시한다)")
            c = newline_cursor(c)
            explicit = True
            i += 1
            continue
        nc = (c + 1) & 0xFF
        if nc == 4 * COLS:
            nc = 3 * COLS  # 68칸째면 한 줄 올리고 마지막 줄 첫 칸에 쓴다(`$DE79`→`$DE23`)
        col = nc % COLS
        if col == 0 and lines[-1]:
            if ch == " ":  # 훅: 줄 첫 칸 공백 — 칸을 안 쓰고 버린다(c 는 그대로)
                i += 1
                continue
            if ch in NO_HEAD:  # 훅: 이전 줄 마지막 글자를 새 줄 첫 칸으로, 부호는 다음 칸
                prev = lines[-1].pop()
                lines.append([prev])
                c2 = (nc + 1) & 0xFF
                if c2 == 4 * COLS:
                    c2 = 3 * COLS
                lines[-1].append((ch, u))  # 부호를 직접 놓는다 — col==0 재검사를 안 거친다
                c = c2
                i += 1
                continue
        c = nc
        if col == 0 and lines[-1]:
            prev_ch, prev_u = lines[-1][-1]
            lines.append([])
            if not explicit and prev_ch != " " and prev_u == u:
                bad.append("④ 묶음 끊김")
        while len(lines[-1]) < col:
            lines[-1].append((" ", ""))  # 쪽 첫머리 개행이 건너뛴 칸
        lines[-1].append((ch, u))
        explicit = False
        i += 1
    return ["".join(ch for ch, _u in ln) for ln in lines], bad


def region(addr: int) -> str:
    if addr in FIELD:
        return "시스템(필드)"
    if BATTLE[0] <= addr <= BATTLE[1]:
        return "전투·시스템"
    return "씬"


def targets() -> list[dict]:
    segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    units = json.loads((common.OUT_DIR / "units" / "segments.json").read_text(encoding="utf-8"))
    out = []
    for u in units:
        a = int(u["addr"], 16)
        e = segs.get(u["id"]) or {}
        if not e.get("kr") or CRAWL[0] <= a <= CRAWL[1]:
            continue
        out.append({"id": u["id"], "addr": a, "kr": e["kr"], "state": e.get("state")})
    return out


def check_all(typeset: bool = True) -> list[dict]:
    dm = _dict()
    sets = {f: candidates(dm, field=f) for f in (False, True)}  # 조판기와 같은 후보로 잰다
    reps_by = {f: {k: representatives(v) for k, v in c.items()} for f, c in sets.items()}
    ml_by = {f: maxlens(c) for f, c in sets.items()}
    rep = []
    for s in targets():
        f = s["addr"] in FIELD
        reps, ml = reps_by[f], ml_by[f]
        # 마스터 최종 판정(2026-09-30, 전 기종 공통) — 로그성 메시지도 어절 단위 개행(빌드와 같은 경로).
        kr = wrap(s["kr"], dm, ml) if typeset else s["kr"]
        toks = sorted(set(re.findall(r"\{(D[6-9A-F])\}", kr)))
        combos = [{}]
        for t in toks:
            combos = [dict(c, **{t: v}) for c in combos for v in reps[t]]
        accepted: set[str] = set()
        worst, worst_hard, n_bad, n_hard = None, None, 0, 0
        for c in combos:
            lines, bad = layout(expand(kr, c, dm))
            if bad:
                n_bad += 1
                if worst is None:
                    worst = (lines, bad, c)
                if set(b[:1] for b in bad) - accepted:
                    n_hard += 1
                    if worst_hard is None:
                        worst_hard = (lines, bad, c)
        rep.append({**s, "region": region(s["addr"]), "combos": len(combos), "bad": n_bad,
                    "hard": n_hard, "worst": worst_hard or worst, "typeset": kr})  # fmt: skip
    return rep


def summary(rep: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for reg in ("시스템(필드)", "전투·시스템", "씬"):
        rs = [r for r in rep if r["region"] == reg]
        bad = [r for r in rs if r["bad"]]
        hard = [r for r in rs if r["hard"]]
        kinds = Counter(b[:1] for r in bad for b in set(r["worst"][1]))
        out[reg] = {"조각": len(rs), "위반": len(bad), "본질위반": len(hard),
                    "tm-draft": sum(r["state"] == "tm-draft" for r in hard),
                    "종류": dict(kinds)}  # fmt: skip
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="tm-draft 아닌 위반이 한 영역이라도 있으면 실패")
    ap.add_argument("--raw", action="store_true", help="조판기를 안 거친 정본 그대로 검사(비교용)")
    ap.add_argument("--show", type=int, default=12, help="예를 몇 개 보일지")
    a = ap.parse_args()
    rep = check_all(typeset=not a.raw)
    for reg, s in summary(rep).items():
        hard = s["본질위반"] - s["tm-draft"]
        mark = "🔴" if hard else ("⚠" if s["위반"] else "✅")
        print(
            f"{mark} {reg}: 조각 {s['조각']} · 위반 {s['위반']}(본질 {s['본질위반']}·그중 tm-draft {s['tm-draft']}) {s['종류']}"
        )
    shown = 0
    for r in sorted(rep, key=lambda r: (r["region"] != "시스템(필드)", r["addr"])):
        if not r["bad"] or shown >= a.show:
            continue
        shown += 1
        lines, bad, c = r["worst"]
        print(f"  ${r['addr'] >> 16:02X}:{r['addr'] & 0xFFFF:04X} {r['id']} [{r['region']}] "
              f"{sorted(set(bad))} {c}")  # fmt: skip
        for ln in lines:
            print(f"      |{ln:<17}|")
    # 🔴 필드만 막으면 전투·씬이 되돌아가도 초록이다(2026-09-27① 전 세션 점검 — ss-ed1+2 에서 일본어가
    #   남은 빌드가 ✅ 로 끝났다). tm-draft 꼬리(P4 대사 라운드 몫)만 할 일로 두고 나머지는 전 영역에서 막는다.
    # 10-07 번복 뒤로는 FIELD 도 다른 영역과 똑같이 전부(①②③④) 막는다 — 예외가 없다.
    hard = [r for r in rep if r["hard"] and r["state"] != "tm-draft"]
    if a.check and hard:
        print(f"🔴 조판 위반 {len(hard)}건(tm-draft 제외) — 커밋 불가")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
