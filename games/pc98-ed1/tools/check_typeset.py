#!/usr/bin/env python3
"""조판 검사기 — 메시지 창 출력기를 **그대로 흉내 내** 여섯 규칙 위반을 영역별로 센다.

## 흉내 내는 것 — 출력기(program 플랫 `0x79c8~0x7a32`·`0x7c05`, 2026-09-27 해독)

- `ch` 가 칸을 센다(전각 +2 · 반각 +1). 글자를 그린 **뒤** `ch ≥ 34` 면 접는다.
  넓은 글자가 33칸에서 시작하면 34칸까지 차 **35칸**이 보인다 — 창 안쪽이 딱 거기까지다.
- 원판은 **글자 단위로 접는다**(낱말을 안 본다 — 대본도 같다, 새 게임 첫 장면 실측).
  우리 훅(`patch_josa_hook.hang`)이 **어절 접기**를 더했다: 반각 공백을 그린 뒤 다음 어절이
  34칸 앞에서 다 시작하지 못하면 공백 뒤에서 접는다. 어절은 제어 바이트(조각 경계)에서 끝난다.
- 원판 금칙: 딱 `ch == 34` 에서 다음이 `!`·`。` 이면 줄 끝에 매단다.
- 우리 판정(`patch_josa_hook.hang`): 딱 34칸에서 `. , ? !` 도 매달고, 다음이 명시 줄바꿈이면
  먼저 접지 않고, 접는 자리의 반각 공백은 먹는다.
- 제어: `01` 줄바꿈 · `03`(`<WAIT>`) 기다린 뒤 줄 중간이면 줄바꿈 · `05`(`<PAGE>`) 새 쪽.
- 쪽당 4줄(`cl` 이 4 가 되면 올린다).

## 여섯 규칙(`r5-typeset.md`)

① 고아 부호 — 부호만 남은 줄 ② 빈 줄 — 자동 접힘 바로 뒤 명시 줄바꿈 ③ 줄 머리 공백
④ 낱말 쪼갬 — 공백이 아닌 자리에서 접힘(이름+조사·숫자+단위 포함) ⑤ 전각 부호·공백
⑥ 조사 빠짐 — 원문 조각이 조사로 시작하는데(앞에 이름이 끼워지는 자리) 우리 문안에 자리표시가 없다

## 글 소실 없음(불변식 — 실패로 친다)

⑴ 흉내 낸 조판 전후 **보이는 글자 수가 같다**(공백만 먹을 수 있다)
⑶ 쪽넘침은 윗줄이 **밀려 사라진다**(화면 실측) — 소실과 같은 무게로 센다
⑵ 칸 표를 **잘라서** 쓴 자리가 없다(`patch_sys` 「잘림」 0)

⚠ 못 보는 것: 조각이 **줄 어디서 시작하는지**는 모른다 — 대본 블록은 0칸에서 시작한다고 본다.
   런타임에 끼워지는 이름·수치는 **예제**(가장 긴 이름 세리오스 · 4자리 수)로만 본다.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import josa_tables
import patch_scn
import patch_sys
import translate

LIMIT = 34
PAGE_LINES = 4
HANG_ORIG = {"!", "。"}
HANG_OURS = {"!", ".", ",", "?"}
CARD = re.compile(r"제[０-９0-9]장")
PUNCT = set(".,?!…。、！？")
PARTICLE_JP = {"は": "{은}", "を": "{을}", "が": "{이}", "と": "{과}"}
TOKEN = re.compile(r"\\n|\n|<PAGE>|<WAIT>|<F>|\{은\}|\{을\}|\{이\}|\{과\}")


def width(ch: str) -> int:
    return 1 if ord(ch) < 0x80 or 0xFF61 <= ord(ch) <= 0xFF9F else 2


def has_batchim(ch: str) -> bool | None:
    if ch.isdigit() and ord(ch) < 0x80:
        return bool(josa_tables.digit_mask() >> int(ch) & 1)
    if "가" <= ch <= "힣":
        return josa_tables.has_batchim(ch)
    return False


def tokens(text: str) -> list[tuple]:
    """문안 → [("g", 글자) | ("nl",) | ("wait",) | ("page",)]. 자리표시는 직전 받침으로 푼다."""
    out: list[tuple] = []
    last = None
    i = 0
    while i < len(text):
        m = TOKEN.match(text, i)
        if m:
            t = m.group(0)
            if t in ("\\n", "\n"):
                out.append(("nl",))
            elif t == "<PAGE>":
                out.append(("page",))
            elif t == "<WAIT>":
                out.append(("wait",))
            elif t == "<F>":
                out.append(("frag",))  # 조각 경계(`10`·`0e` 등) — 폭 0, 어절 재기가 여기서 멈춘다
            else:
                pair = next(p for p in patch_scn.JOSA_PAIRS if p[0] == t)
                ch = pair[1] if last and has_batchim(last) else pair[2]
                out.append(("g", ch))
                last = ch
            i = m.end()
            continue
        ch = text[i]
        out.append(("g", ch))
        if ch not in " \u3000":
            last = ch
        i += 1
    return out


def word_fits(toks: list[tuple], j: int, ch: int) -> bool:
    """④ 어절 접기(`patch_josa_hook.hang`) — 공백 뒤 어절을 그려 보며 34칸 앞에서 시작하나 본다."""
    while j < len(toks) and toks[j][0] == "g" and toks[j][1] != " ":
        c = toks[j][1]
        if ch > LIMIT or (ch == LIMIT and c not in HANG_OURS and c != "。"):
            return False
        if ch == LIMIT:  # 매다는 부호 — 어절의 마지막 글자일 때만
            return not (j + 1 < len(toks) and toks[j + 1][0] == "g" and toks[j + 1][1] != " ")
        ch += width(c)
        j += 1
    return True


def layout(toks: list[tuple], ours: bool = True) -> dict:
    """→ {"pages": [[줄, …], …], "auto": {(쪽, 줄)}, "blank": n} — 줄은 글자 목록."""
    pages = [[[]]]
    auto: set = set()
    eaten: set = set()
    blank = 0
    ch = 0
    i = 0

    def newline(kind: str):
        nonlocal ch, blank
        # ② 자동으로 막 접힌 빈 줄에서 또 명시 줄바꿈 — 빈 줄이 하나 생긴다
        if kind == "nl" and not pages[-1][-1] and (len(pages) - 1, len(pages[-1]) - 1) in auto:
            blank += 1
        pages[-1].append([])
        if kind == "auto":
            auto.add((len(pages) - 1, len(pages[-1]) - 1))
        ch = 0

    while i < len(toks):
        t = toks[i]
        if t[0] == "g":
            pages[-1][-1].append(t[1])
            ch += width(t[1])
            if ours and t[1] == " " and ch < LIMIT and not word_fits(toks, i + 1, ch):
                newline("auto")
            elif ch >= LIMIT:
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                if ours and nxt and nxt[0] == "nl":
                    pass
                elif ours and nxt and nxt[0] == "g" and nxt[1] == " ":
                    i += 1
                    newline("auto")
                    eaten.add(
                        (len(pages) - 1, len(pages[-1]) - 1)
                    )  # 공백을 먹고 접었다 = 어절 경계
                elif (
                    ch == LIMIT
                    and nxt
                    and nxt[0] == "g"
                    and nxt[1] in (HANG_OURS if ours else HANG_ORIG)
                ):
                    pass
                elif nxt is not None:
                    newline("auto")
        elif t[0] == "nl":
            newline("nl")
        elif t[0] == "wait":
            if ch:
                newline("nl")
        elif t[0] == "frag":
            pass
        elif t[0] == "page":
            pages.append([[]])
            ch = 0
        i += 1
    return {"pages": pages, "auto": auto, "eaten": eaten, "blank": blank}


def judge(toks: list[tuple], ours: bool = True, speaker: bool = False) -> dict:
    """`speaker` — 첫 쪽 첫 줄을 화자 이름이 먹는다(화면 실측: 「라이아스」 + 본문 3줄)."""
    lay = layout(toks, ours)
    v = {"①": 0, "②": lay["blank"], "③": 0, "④": 0, "쪽넘침": 0, "소실": 0}
    for pi, page in enumerate(lay["pages"]):
        body = page[:-1] if page and not page[-1] else page  # 끝 빈 줄은 안 그린다
        cap = PAGE_LINES - (1 if speaker and pi == 0 else 0)
        # 🔴 넘치면 윗줄이 **밀려 올라가 사라진다**(▽ 에서 멈출 땐 이미 안 보인다) — 화면 실측
        if len(body) > cap:
            v["쪽넘침"] += 1
        for li, line in enumerate(page):
            if not line:
                continue
            if (pi, li) in lay["auto"]:
                if all(c in PUNCT for c in line if c != " "):
                    v["①"] += 1
                prev = page[li - 1] if li else []
                at_space = (pi, li) in lay["eaten"] or (prev and prev[-1] == " ")
                if prev and not at_space and line[0] != " " and line[0] not in PUNCT:
                    v["④"] += 1
            # ③ 은 **접힌 뒤** 줄만 — 첫 줄 머리 공백은 정렬(장 카드·메뉴 채움)이다
            if li and line[0] in (" ", "\u3000"):
                v["③"] += 1
    seen = sum(1 for p in lay["pages"] for ln in p for c in ln if c != " ")
    given = sum(1 for t in toks if t[0] == "g" and t[1] != " ")
    if seen != given:
        v["소실"] += 1
    return v


def fullwidth_marks(text: str, jp: str = "") -> int:
    """⑤ — 전각 부호·공백(숫자 전각은 `check_style` 몫). 원문과 전각 공백 수가 같으면 칸 맞춤이다
    (전투 명령 메뉴 「싸움　　주문」 같은 고정 칸) — 그건 원문 모양을 따른 것이라 안 센다."""
    n = len(re.findall(r"[。、！？]", text))
    sp = text.count("\u3000")
    return n + (0 if sp and sp == jp.count("\u3000") else sp)


def regions() -> dict[str, list[tuple[str, str, str, bool]]]:
    """→ {영역: [(열쇠, 원문, 문안, 화자 있음)]}"""
    canon = translate.load_script()
    out: dict[str, list] = {"대본": [], "전투": [], "시스템": []}
    # 같은 열쇠가 여러 자리에 나간다 — 한 자리라도 화자가 붙으면 그 조건(더 좁은 첫 쪽)으로 본다
    rows: dict[str, list] = {}
    for k, b in translate.keyed(translate.blocks()):
        if k not in canon or "t" not in canon[k] or b.get("sp"):
            continue
        src = b["src"]
        reg = "전투" if src == "scn_jp/combat" else "대본" if src == "scn_jp/scenario" else None
        if not reg:
            continue
        if k in rows:
            rows[k][4] = rows[k][4] or "s" in b
        else:
            rows[k] = [reg, k, b["t"], canon[k]["t"], "s" in b]
    for reg, k, jp, kr, sp in rows.values():
        if CARD.search(kr):  # 장 카드 — 메시지 창이 아니다(가운데 정렬 채움이 곧 모양)
            continue
        out[reg].append((k, jp, kr, sp))
    sites = {d: patch_sys.sites(d) for d in patch_sys.DISKS}
    for key, v in patch_sys.load().items():
        if "t" not in v:
            continue
        d, _, off = key.partition(":")
        # event 는 오프닝·엔딩 나레이션 — 전면 화면의 다른 출력기라 이 모델이 안 맞는다
        if d != "program":
            continue
        jp = sites.get(d, {}).get(int(off, 16), {}).get("t", "")
        out["시스템"].append((key, jp, v["t"], False))
    return out


def particle_drop(reg: str, jp: str, kr: str) -> bool:
    """⑥ — 원문 조각이 조사로 시작(= 앞에 이름·아이템이 끼워지는 자리)하는데 자리표시가 없다."""
    s = jp.lstrip(" \u3000")
    if not s or s[0] not in PARTICLE_JP:
        return False
    # 문장 조각만 — 「はがねのやり」(이름)·「はい」(대답)는 조사가 아니다
    if not (re.search(r"[。｡！!？?]|\\n", s) or s.endswith((" ", "た"))):
        return False
    # 대본은 「では」「にわとり」처럼 낱말 머리일 때가 많다 — 조사 뒤가 공백·한자일 때만 센다
    if reg == "대본" and not re.match(r".[ \u3000\u4e00-\u9fff]", s):
        return False
    return not kr.lstrip().startswith(tuple(p[0] for p in patch_scn.JOSA_PAIRS))


def examples() -> list[tuple[str, str]]:
    """런타임에 끼워지는 것 — 가장 긴 이름(세리오스)·4자리 수로 세운 문장."""
    sysj = patch_sys.load()

    def t(k):
        return sysj[k]["t"]

    # `<F>` = 조각 경계 — 출력기는 제어 바이트 너머 어절을 못 잰다(실제 바이트 흐름과 같게 둔다)
    return [
        (
            "주문 시전",
            "세리오스<F>"
            + t("program:0x4be2")
            + "<F>"
            + t("program:0x4bee")
            + "<F>레지나 1<F>"
            + t("program:0x4c66")
            + "\\n"
            + t("program:0x4c72")
            + "!",
        ),
        (
            "도구 사용",
            "세리오스<F>"
            + t("program:0x4be2")
            + "<F>요슈아의 눈<F>"
            + t("program:0x4c03")
            + "\\n하지만 아무 일도 없었다.",
        ),
        ("4자리 Gold", "세리오스{은} 9999 Gold를 훔쳤다."),
        ("4자리 데미지", "세리오스{은} 9999 포인트의 데미지를 받았다!"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", type=int, default=0, help="규칙마다 보기 N 개")
    ap.add_argument("--orig", action="store_true", help="원판 금칙으로 흉내 낸 수도 같이 낸다")
    a = ap.parse_args()

    rules = ["①", "②", "③", "④", "⑤", "⑥", "쪽넘침"]
    fail = 0
    print(f"{'영역':6s} {'줄':>6s} " + " ".join(f"{r:>5s}" for r in rules) + "   소실")
    samples: dict[str, list] = {r: [] for r in rules}
    for reg, rows in regions().items():
        tot = dict.fromkeys(rules, 0)
        loss = 0
        for key, jp, kr, sp in rows:
            v = judge(tokens(kr), speaker=sp)
            for r in ("①", "②", "③", "④", "쪽넘침"):
                if v[r]:
                    tot[r] += v[r]
                    samples[r].append((reg, key, kr))
            tot["⑤"] += fullwidth_marks(kr, jp)
            if particle_drop(reg, jp, kr):
                tot["⑥"] += 1
                samples["⑥"].append((reg, key, f"{jp[:16]!r} → {kr[:24]!r}"))
            loss += v["소실"]
        fail += loss
        print(f"{reg:6s} {len(rows):6,d} " + " ".join(f"{tot[r]:5d}" for r in rules) + f"   {loss}")
        if a.orig:
            o = dict.fromkeys(["①", "②", "③"], 0)
            for _k, _jp, kr, sp in rows:
                v = judge(tokens(kr), ours=False, speaker=sp)
                for r in o:
                    o[r] += v[r]
            print(f"{'  원판금칙':8s}      " + " ".join(f"{o[r]:5d}" for r in o))

    print("── 예제(세리오스·4자리) — 🔴 게이트: 이 넷은 늘 깨끗해야 한다")
    ex_bad = 0
    for name, text in examples():
        v = judge(tokens(text))
        lay = layout(tokens(text))
        bad = [r for r in ("①", "②", "③", "④", "쪽넘침") if v[r]]
        ex_bad += bool(bad)
        mark = "✅" if not bad else "🔴 " + "".join(bad)
        print(f"  {mark} {name}: " + " / ".join("".join(ln) for p in lay["pages"] for ln in p))
        fail += v["소실"]

    _out, st = patch_sys.plan()
    cut = st.get("잘림", 0)
    print(f"── 글 소실 없음: 조판 흉내 소실 {fail} · 칸 표 잘림 {cut}")
    if a.list:
        for r in rules:
            for reg, key, kr in samples[r][: a.list]:
                print(f"  {r} [{reg}] {key[:16]} {kr[:60]!r}")
    if fail or cut:
        print("🔴 글이 사라지는 자리가 있다")
        return 1
    if ex_bad:
        print("🔴 예제가 규칙을 어긴다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
