"""조립형 시스템 문장 조판 검사 — 가장 긴 이름·도구·주문을 넣어 13칸 창으로 돌린다.

필드 메시지 창은 **한 줄 13칸**이다. 원판은 넘치면 글자 단위로 넘기지만(2026-09-26 실측: 「사용했/다.」) 우리 후킹이
셋을 고친다 — `wrap()` 이 그 런타임을 그대로 흉내 낸다(`hook._wrap_asm` · `hook._wordck_asm`):
**어절 단위**(10-07, 마스터 09-30 「로그성 메시지도 어절 단위」) · 부호 넷은 줄 끝에 매단다 · 자동으로 넘긴 줄의
첫 공백은 칸을 안 먹는다. 공백은 **반각 4px**(마스터 10-07 — `font.HALF_SPACE`, 렌더러 훅 `hook._narrow_asm`)이라 칸은 `px // 12` 다.

문장은 **정본 조각**(`script/sys/sysmsg.json`)을 열쇠로 끌어와 조립한다 — 문안을 여기 다시 쓰지 않는다(DRY).
조립 순서(어느 조각 뒤에 무엇이 오는가)는 화면에서 본 흐름을 적은 것이라 **추정이 섞인 줄은 `guess=True`** 로 표시한다.

보는 것(마스터 조판 기반 09-27): ① 고아 온점(부호만 남은 줄) ② 빈 줄 ③ 줄 첫 칸 공백 ④ 묶음 끊김(낱말 가운데서 줄이 넘어감).
"""

import json
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import sysbuild
import sysstrings as S
import typeset

WIDTH = 13
PUNCT = set(".,!?。、！？…")

# 가장 긴 값(정본에서 계산) — 이름은 파티 다섯 중 최장, 대상은 파티 또는 「자신」
ACTOR = "세리오스"


def _msgs():
    return json.loads((common.GAME_DIR / "script" / "sys" / "sysmsg.json").read_text("utf-8"))[
        "messages"
    ]


def _keys():
    """주소 → 열쇠 (원본 파생물). 파생물이 없으면 None — 게이트는 건너뛴다."""
    try:
        return {r["addr"]: r["key"] for r in S.read_sysmsg()}
    except (OSError, FileNotFoundError):  # 원본을 안 링크한 트리
        return None


def longest(fam):
    names = sysbuild._load("names.json")
    gl = sysbuild.glossary()
    ks = {names.get(fam, {}).get(r["jp"], gl.get(r["jp"])) for r in S.read_fixed(fam) if r["jp"]}
    return max(sorted(k for k in ks if k), key=len)  # 같은 길이면 사전순 첫 것(결정적)


@dataclass
class Case:
    name: str
    parts: list  # 문자열(값) 또는 ("frag", 주소)
    guess: bool = False


def text_of(parts, frag, raw=None):
    """("frag", 주소[, 삽입]) = 조각 전부(삽입 = {토큰: 값}, 예 `{"0E": 도구}`) ·
    ("var", 주소, n) = `{0A}` 로 갈린 변형 중 n 번째(코드가 하나를 고른다)."""
    out = ""
    for p in parts:
        if isinstance(p, tuple) and p[0] == "var":
            out += clean(raw(p[1]).split("{0A}")[p[2]])
        elif isinstance(p, tuple):
            out += frag(p[1], *p[2:])
        else:
            out += p
    return out


JUMP = re.compile(r"\{0F([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})\}")


def follow(raw_of, addr, subs=None, depth=0):
    """조각 원문을 인터프리터처럼 읽는다 — `{0F lo hi}` 를 만나면 그 뒤 글은 버리고 **점프 자리 조각**으로 잇는다
    (「최대ＨＰ가」+수치+`0F`→「올랐다.」 — 점프 뒤에 남은 글은 아무도 안 읽는다). 삽입 토큰은 값으로 바꾼다."""
    s = raw_of(addr)
    for tok, val in (subs or {}).items():
        s = s.replace("{" + tok + "}", val)
    m = JUMP.search(s)
    if m and depth < 4:
        tgt = int(m.group(2) + m.group(1), 16)
        return s[: m.start()] + follow(raw_of, tgt, subs, depth + 1)
    return s


def clean(s):
    """조각 문안 → 화면 글자열: 제어 토큰은 줄바꿈만 살리고 나머지는 지운다. 조사 토큰은 앞 글자 받침으로 고른다."""
    import re

    s = s.replace("{01}", "\n").replace("{0A}", "\n\n")
    s = re.sub(r"\{[0-9A-Fa-f]+\}", "", s)
    return s


def pick_josa(s):
    """「은/는」 류를 직전 글자 받침으로(숫자는 읽는 소리 — hook 규칙)."""
    import re

    import font

    def has_batchim(ch):
        if ch in font.DIGIT_READING:
            ch = font.DIGIT_READING[ch]
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        return False

    out = ""
    i = 0
    pat = re.compile(r"(은/는|을/를|이/가|과/와|으로/로|아/야|이랑/랑)")
    for m in pat.finditer(s):
        out += s[i : m.start()]
        a, b = m.group().split("/")
        prev = out.rstrip()[-1:] if out.strip() else ""
        out += a if prev and has_batchim(prev) else b
        i = m.end()
    return out + s[i:]


HANG = set("!,.?")  # `hook.HANG_PUNCT` — 글리프 정본 앞 넷(F024·F025·F027·F02E)


def wrap(s):
    """13칸 창의 줄 — 런타임(후킹 포함)을 흉내 낸다. 꽉 찬(13칸) 줄 뒤의 명시 줄바꿈은 **빈 줄이 안 된다** — `01` 은 「다음 글자 전에
    줄 바꿈」 표시(`$6AB5` = `INC $CF15`)일 뿐이고 줄 넘김은 한 번만 일어난다. 처음엔 PS1 전례(122곳)로 「빈 줄이 된다」고 모델했지만
    **PCE 화면이 아니었다**(10-07 `round6-wordwrap-item` — 「류난은 횃불을 사용했다.」 정확히 13칸 + `01` 뒤 「하지만…」이 바로 다음 줄).

    · 칸 = `px // 12` — 글자 12px · **공백 4px(반각, 10-07)**. 칸이 13 에 닿은 뒤 오는 글자는 새 줄(`$6D95`).
    · 어절 첫 글자(앞이 공백)에서 「칸 + 어절 길이(매다는 부호 뺌) > 13」이면 그 글자부터 새 줄(`wordck`)
    · 칸 13 에 온 글자가 부호 넷이면 넘기지 않고 매단다(`orphan`) · 넘긴 줄 첫 공백은 칸을 안 먹는다(`eat` + `flag`)
    (줄들, 자동 넘김 자리들[(윗줄 번호, 낱말 가운데인가)]) 를 돌려준다."""
    lines, cuts = [], []
    paras = s.split("\n")
    for para in paras:
        cur, px = "", 0
        for j, ch in enumerate(para):
            prev = para[j - 1] if j else ""
            col = px // 12
            brk = False
            if col >= WIDTH and ch not in HANG:
                brk = True
            elif prev == " " and ch != " " and col > 0:
                n = 0
                for c in para[j:]:
                    if c == " ":
                        break
                    n += c not in HANG
                brk = col + n > WIDTH
            if brk:
                mid = prev != " " and ch != " " and prev not in PUNCT and ch not in PUNCT
                lines.append(cur)
                cuts.append((len(lines) - 1, mid))
                cur, px = "", 0
                if ch == " ":
                    continue  # 줄 머리 공백은 안 그린다(`flag`) — 화면엔 없는 것과 같다
            cur += ch
            px += 4 if ch in typeset.NARROW else 12
        lines.append(cur)
    return lines, cuts


def assert_no_loss(src, lines):
    """글 소실 없음 — 넘김 전후 글자(공백·개행 제외)가 같아야 한다."""
    import typeset

    assert typeset.ink(src) == typeset.ink("".join(lines)), ("검사기 넘김이 글을 잃었다", src)


def problems(lines, cuts=()):
    out = []
    for i, ln in enumerate(lines):
        if ln and all(c in PUNCT for c in ln):
            out.append(f"① 고아 부호 {i + 1}줄 「{ln}」")
        if ln == "" and 0 < i < len(lines) - 1:
            out.append(f"② 빈 줄 {i + 1}줄")
        if ln.startswith(" "):
            out.append(f"③ 줄 첫 칸 공백 {i + 1}줄")
    for i, mid in cuts:
        if mid:
            out.append(
                f"④ 낱말 가운데서 넘어감 {i + 1}→{i + 2}줄 「{lines[i][-2:]}/{lines[i + 1][:2]}」"
            )
    return out


def scene_cuts(t, pg):
    """조판기 출력의 줄 경계가 원문에서 공백이 아니었으면(낱말 가운데) 끊김."""
    flat = t.replace("\f", " ").replace("\n", " ")
    cuts = []
    for i in range(len(pg) - 1):
        a, b = pg[i], pg[i + 1]
        if a and b and (a[-3:] + b[:3]) in flat and a[-1] not in PUNCT:
            cuts.append((i, True))
    return cuts


def cases():
    item = longest("items")
    spell = longest("spells") + "1"
    val = {"1F}{22}{04": VALUE}  # 수치 삽입(강조색) — 4자리
    return [
        Case(
            # $9B8F(행위자+は) → $9BA8 = `10 B0 9B`(도구 이름 `0E` + を使った。01) → 06 → しかし → 何も…
            "도구 사용 · 아무 일 없음",
            [
                ACTOR,
                ("frag", 0x9B90),
                item,
                ("frag", 0x9BB0),
                "\n",
                ("frag", 0x9E09),
                ("frag", 0x9C02),
            ],
        ),
        Case(
            "도구 사용 · 짧은 도구",
            [
                ACTOR,
                ("frag", 0x9B90),
                "횃불",
                ("frag", 0x9BB0),
                "\n",
                ("frag", 0x9E09),
                ("frag", 0x9C02),
            ],
        ),
        Case(
            "주문 · 동료에게",
            [ACTOR, ("frag", 0x9B90), "소니아", ("frag", 0x9B93), "\n", spell, ("frag", 0x9C17)],
            guess=True,
        ),
        Case(
            "주문 · 자신에게",
            [ACTOR, ("frag", 0x9B90), ("frag", 0x9B9B), "\n", spell, ("frag", 0x9C17)],
            guess=True,
        ),
        Case(
            "주문 · MP 부족",
            [ACTOR, ("frag", 0x9B90), "\n", spell, ("frag", 0x9C17), "\n", ("frag", 0x9C22)],
            guess=True,
        ),
        Case("HP 회복", [ACTOR, ("frag", 0x9D7B), VALUE, ("frag", 0x9D90)]),
        # $9D87 은 뒤 단위 $9D90(수치+回復。)로 **흘러 들어간다**(점프 없음) — 레벨업 화면에서 실측 09-27
        Case("MP 회복", [ACTOR, ("frag", 0x9D87), VALUE, ("frag", 0x9D90)]),
        # 흡수 — $9C35 는 `0F`→$9C4A, $9C41 은 $9C4A 로 흘러 들어간다(수치+奪った！)
        Case("HP 흡수", [ACTOR, ("frag", 0x9C35), VALUE, ("frag", 0x9C4A)], guess=True),
        Case("MP 흡수", [ACTOR, ("frag", 0x9C41), VALUE, ("frag", 0x9C4A)], guess=True),
        Case("능력치 오름(공격력)", [ACTOR, ("frag", 0x9CA9), ("var", 0x9CCD, 0)], guess=True),
        Case("능력치 늘어남(민첩)", [ACTOR, ("frag", 0x9C57), ("var", 0x9CCD, 1)], guess=True),
        Case("최대 HP", [("frag", 0x99A5), ("frag", 0x9979)], guess=True),
        Case("상자", ["보물상자", ("frag", 0x995B)], guess=True),
        Case("도구를 얻음", [item, ("frag", 0x99E2)]),
        Case("더 못 가짐", [("frag", 0x99B1)]),
        Case("저장 묻기", [("frag", 0x9897), ("frag", 0x98AB), ("frag", 0x98B6)]),
        # 레벨업 — 화면 순서(2026-09-27 에뮬, 레벨업=수동): $9E74 → 최대HP $9E8C → 최대MP $9EB0 → HP 회복 $9D7B
        # → MP 회복 $9D87 → 포인트 $9EC0 → 배분 창. 각 「X가/이」+수치+`0F`→$9EA4「올랐다.」.
        # 능력치 넷($9EDE~$9F0A)은 코드(뱅크 0x77 +0x212~)로만 확인 — 이 세이브의 흐름에선 안 떴다.
        Case("레벨업", [ACTOR, ("frag", 0x9E74)]),
        Case("레벨업 · 최대HP", [("frag", 0x9E8C, val)]),
        Case("레벨업 · 최대MP", [("frag", 0x9EB0), VALUE, ("frag", 0x9EA4)]),
        Case("레벨업 · 힘", [("frag", 0x9EDE), VALUE, ("frag", 0x9EA4)], guess=True),
        Case("레벨업 · 지혜", [("frag", 0x9EEA), VALUE, ("frag", 0x9EA4)], guess=True),
        Case("레벨업 · 민첩성", [("frag", 0x9EFA), VALUE, ("frag", 0x9EA4)], guess=True),
        Case("레벨업 · 행운", [("frag", 0x9F0A), VALUE, ("frag", 0x9EA4)], guess=True),
        Case("레벨업 · 포인트", [VALUE, ("frag", 0x9EC0)]),
    ]


def run():
    keys = _keys()
    if keys is None:
        return None
    msgs = _msgs()

    def raw(addr):
        return msgs.get(keys[addr], "")

    def frag(addr, subs=None):
        return clean(follow(raw, addr, subs))

    rows = []
    for c in cases():
        s = pick_josa(text_of(c.parts, frag, raw))
        lines, cuts = wrap(s)
        assert_no_loss(s, lines)
        rows.append((c, lines, problems(lines, cuts)))
    return rows


VALUE = "9999"  # 수치는 4자리(마스터 09-27)


def scene_rows():
    """씬 대사 — 빌드와 같은 조판기(typeset.pages)의 결과를 그대로 본다. 빌드는 꽉 찬 줄 뒤에 개행을 안 넣으므로(②)
    줄 단위 ①③④ 만 본다. 화자 창은 첫 줄 10칸이라 화자 있음으로 짠다(더 엄한 쪽)."""
    import font
    import typeset

    rows = []
    for p in sorted((common.GAME_DIR / "script").glob("scn*.json")):
        for k, v in json.loads(p.read_text("utf-8")).get("messages", {}).items():
            t = v.get("t", "")
            if not t:
                continue
            if "\n" in t:  # 하드 개행 창(장 끝 카드) — 줄을 손으로 맞춘 것이라 안 본다
                continue
            src = font.expand_packed(t)
            pgs = typeset.pages(src, speaker=True)  # 글 소실은 typeset.pages 가 스스로 assert 한다
            for pg in pgs:
                probs = [
                    x
                    for x in problems(pg, scene_cuts(font.expand_packed(t), pg))
                    if not x.startswith("②")
                ]
                if probs:
                    rows.append((f"{p.stem}:{k}", pg, probs))
    return rows


def battle_rows():
    """전투 문구 — 가장 긴 몬스터 이름·수치 4자리를 끼워 13칸으로(행위자가 앞에 붙는 조각은 이름을 앞에)."""
    import re

    import battle

    names, _missing = battle.kr_names()
    mon = max(names.values(), key=len)
    msgs = json.loads((common.GAME_DIR / "script" / "sys" / "battle.json").read_text("utf-8"))[
        "messages"
    ]
    rows = []
    for k, v in msgs.items():
        t = v
        if re.match(r"(은/는|을/를|이/가|의|에게|에)", t):
            t = mon + t
        t = t.replace("{01}", "\n")
        t = re.sub(r"\{(22|1F2204)\}", VALUE, t)
        t = re.sub(r"\{02\}", ACTOR, t)
        t = re.sub(r"\{[0-9A-Fa-f]+\}", "", t)
        t = pick_josa(t)
        lines, cuts = wrap(t)
        assert_no_loss(t, lines)
        probs = problems(lines, cuts)
        if probs:
            rows.append((k, lines, probs))
    return rows, len(msgs), mon


if __name__ == "__main__":
    if "--all" in sys.argv:
        sc = scene_rows()
        bt, nbt, mon = battle_rows()
        sy = [r for r in run() or [] if r[2]]
        print(
            f"영역별 위반 — 시스템 {len(sy)}/{len(cases())} · 전투 {len(bt)}/{nbt}(몬스터 최장 「{mon}」) · 씬 {len(sc)}창"
        )
        for name, rows in (
            ("시스템", [(c.name, l, p) for c, l, p in sy]),
            ("전투", bt),
            ("씬", sc),
        ):
            print(f"== {name}")
            for key, lines, probs in rows[:200]:
                print(f"  {key}: " + " / ".join(probs) + "  ⟨" + "|".join(lines) + "⟩")
        sys.exit(0)
    rows = run()
    if rows is None:
        print("원본 파생물이 없어 건너뛴다")
        sys.exit(0)
    bad = 0
    for c, lines, probs in rows:
        mark = "✗" if probs else "✓"
        bad += bool(probs)
        print(f"{mark} {c.name}{' (조립 추정)' if c.guess else ''}")
        for ln in lines:
            print(f"    |{ln:<{WIDTH}}|")
        for p in probs:
            print("    " + p)
    print(f"위반 문장 {bad}/{len(rows)}")
