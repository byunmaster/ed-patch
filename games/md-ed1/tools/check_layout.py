"""조립형 시스템 메시지의 조판 검사 — 가장 긴 이름·도구·주문·숫자를 끼워 창 폭으로 돌린다.

    python3 tools/check_layout.py        # 위반 목록(없으면 ✅)
    python3 tools/check_layout.py -v     # 조립 결과를 줄별 폭과 함께

도구·주문·상태·레벨업 메시지는 **조각을 코드가 이어 붙인다**(시전자 「<02>は」 + 대상 「<02>に」 + 주문 이름 +
「を唱えた」). 조각 하나하나는 칸에 들어가도 **이어 붙이면** 창을 넘는다 — 2026-09-27 「류난은 세리오스에게 레스1을
외웠다」가 온점만 다음 줄로 떨궜다(마스터 인게임). 그래서 조각을 실제 순서대로 잇고 빈 자리엔 **가장 긴 값**을 넣어 잰다.

폭(실측): 전각·한글 12px · 반각 6px(대사창 피치, status 5절). 메시지 창(`$642C`, 224×40)은 **210px(반각 35칸)까지** 한
줄에 든다(「게일은 세리오스에게 레스1을 외웠다」 210px 한 줄 — 구 롬 86ce835d, 09-27).
🔴 **줄넘김은 어절 단위다(마스터 최종 판정 2026-10-05, 전 기종 — 09-27 밤의 "글자 단위" 를
09-30 에 다시 뒤집었다).** 대사(씬·NPC)도 로그성 메시지(도구·주문·전투)도 **넘칠 때 공백 뒤
어절을 통째로 다음 줄로** 보낸다(렌더러 패치 `tools/wordwrap.py`). 그 위에 최소 가드 둘만
더 막는다: **① 고아 부호**(.!?, 「!!」·「!?」 연쇄 포함)가 혼자 줄 첫머리로 못 가고 앞줄 끝에
매달린다(넘쳐도 그대로 그린다) · **② 줄이 공백으로 시작하지 않는다**(넘친 공백은 버린다).
**한 어절이 줄보다 길면**(공백을 못 찾으면) 원판 그대로 글자 단위로 접는다. `wrap` 은 그
패치와 **같은 모형**이다.
**꽉 찬 줄 + 박은 `\\n` 은 빈 줄을 만들지 않는다** — 창은 다음 글자가 안 들어갈 때만 넘긴다(`r5-typeset-210px-newline.png`,
09-27 — pce 는 반대라 빈 줄이 생겼다). 그래서 ②는 **우리가 박은 빈 줄**만 센다.
규칙(라운드⑤ 조판 기반) — **접은 결과**에서 센다: ① 고아 부호(부호만 한 줄) ② 빈 줄 ③ 줄 첫칸 공백 ⑤ 조사 병기 「(을)」류 남음
⑦ **글 소실 없음** — 줄을 가르기 전후 글자 수(공백·줄바꿈 빼고)가 같아야 한다. PS1 이 어절 단위 줄넘김을 고치다 특정 폭에서
꼬리 글을 잃었다(「ＨＰ를 112 / 빼앗았다!!」 소실, 09-27) — 폭·위반만 보는 검사는 그걸 못 본다. 씬은 빌드 조판기(`build.typeset`)
전후를, 시스템·전투는 창 줄넘김 모형(`wrap`) 전후를 잰다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

LIMIT = 210  # 메시지 창 한 줄(px)
FULL, HALF = 12, 6
T = common.GAME_DIR / "textmap"


def width(s: str) -> int:
    return sum(HALF if ord(c) < 0x80 else FULL for c in s)


def longest(names: list[str]) -> str:
    return max(names, key=width)


def fillers() -> dict[str, str]:
    """빈 자리에 넣을 가장 긴 값."""
    nm = json.loads((T / "names.json").read_text(encoding="utf-8"))
    ours = lambda cat: [o["ours"] for o in nm[cat].values() if o.get("ours")]
    party = [re.sub(r"<[0-9a-f]+>", "", s).strip() for s in ours("party_name")]
    items = ours("item")
    spells = [
        s + "８" for s in ours("spell")
    ]  # 레벨은 전각 숫자 한 자(「레스１」) — 가장 넓은 자리
    return {
        "name": longest(party),
        "item": longest(items),
        "spell": longest(spells),
        "num": "9999",  # HP·MP 최대 네 자리(반각)
        "josa": "을",  # 조사 훅은 한 글자(을·를·은·는·이·가) — 전각 한 칸
    }


def expand(s: str, f: dict[str, str]) -> str:
    s = re.sub(r"<02>|<0b>", f["name"], s)  # <0b> = 리더 이름(`$FF1AEC`) — 가장 긴 파티 이름으로
    s = re.sub(r"<0e>", f["item"], s)
    s = re.sub(r"<e[bc][0-9a-f]{2}>", f["josa"], s)
    s = re.sub(
        r"\n?<0[35]>", "\n", s
    )  # 03 대기·05 쪽 넘김 = 새 줄에서 시작(바로 앞 줄바꿈은 겹쳐 빈 줄이 되지 않는다)
    s = re.sub(r"<(06|07|0a|0d|00|04|17|1a|1e|08)>", "", s)
    s = re.sub(r"<0f:[0-9a-f]+>|<10:[0-9a-f]+>", "", s)
    return re.sub(r"<[0-9a-f]+>", "", s)


# 조각을 실제 순서대로 — (이름, [조각 키 또는 {자리}])
CHAINS = [
    ("주문 · 남에게", ["0073fe", "007402", "{spell}", "007412"]),
    ("주문 · 자기에게", ["0073fe", "007406", "{spell}", "007412"]),
    ("도구 · 남에게", ["0073fe", "007662"]),
    ("도구", ["0073fe", "007672"]),
    ("도구 · 자기에게", ["0073fe", "00767e"]),
    ("회복 HP", ["0076a6", "{num}", "0076be"]),
    ("회복 MP", ["0076b2", "{num}", "0076be"]),
    ("흡수 HP", ["007560", "{num}", "00762a"]),
    ("흡수 MP", ["00756c", "{num}", "00762a"]),
    ("능력 오름", ["0075b6", "{num}", "007640"]),
    ("레벨업", ["004172"]),
    ("레벨업 HP", ["004189", "{num}", "0041b2"]),
    ("레벨업 능력", ["0041cd", "{num}", "0041b2"]),
    ("레벨업 보너스", ["{num}", "0041d9"]),
    ("도구 효과", ["{item}", "007694"]),
    (
        "상자",
        ["007604", "{item}", "00760f"],
    ),  # 첫 <0e> 는 상자 이름 — 가장 긴 도구 이름으로 넉넉히 잰다
    ("획득", ["003688"]),
]

PUNCT = set(".,!?…")


def glyphs(s: str) -> str:
    """글 소실 비교용 — 공백·줄바꿈을 뺀 글자열."""
    return re.sub(r"\s", "", s)


ORPHAN = set(".!?")  # 혼자 줄 첫머리로 못 가는 부호(마스터 확정 2026-09-27 밤, 기종 공통) — 「!!」·「!?」는 낱자 둘의 연쇄로 걸린다


def wrap_ex(line: str, limit: int) -> list[str]:
    """렌더러(어절 단위 + 최소 가드 둘)와 같은 모형(마스터 최종 판정 2026-09-30, 전 기종).

    로그성 메시지도 대사와 같이 **어절 단위**로 접는다 — 넘칠 글자 바로 앞에서 공백을 찾아 그
    뒤(어절)를 통째로 다음 줄로 옮긴다(공백 자신은 버려진다). 그 위에 ① 고아 부호(.!?)가 혼자
    다음 줄 첫머리로 떨어지지 않게(넘쳐도 앞줄 끝에 매단다) · ② 줄 첫 칸이 공백으로 시작하지
    않게 이 둘을 막는다. **한 어절이 줄보다 길어 공백을 못 찾으면**(또는 애초에 공백이 없으면)
    원판 그대로 글자 단위로 접는다 — `tools/wordwrap.py` 의 ASM과 같은 모형이다.
    """
    out, cur = [], ""
    for c in line:
        if width(cur) + width(c) > limit and cur:
            if c == " ":  # 넘친 공백은 버리고 줄만 바꾼다(줄 첫 칸 공백 금지)
                out.append(cur)
                cur = ""
                continue
            if c in ORPHAN:  # 부호는 줄 끝에 매단다(넘어도 그대로 이어 그린다, 고아 부호 금지)
                cur += c
                continue
            sp = cur.rfind(" ")
            if sp == -1:  # 공백이 없다 — 한 어절이 줄보다 길다, 글자 단위로 자른다(원판 그대로)
                out.append(cur)
                cur = ""
            else:  # 공백 뒤 어절을 통째로 다음 줄로(공백 자신은 옛 줄에도 새 줄에도 안 남는다)
                out.append(cur[:sp])
                cur = cur[sp + 1 :]
        cur += c
    out.append(cur)
    return out


def wrap(line: str, limit: int) -> list[str]:
    return wrap_ex(line, limit)


def lost(before: str, after: str) -> str | None:
    """⑦ 글 소실 — 빠진 글자가 있으면 그 꼬리를 돌려준다."""
    a, b = glyphs(before), glyphs(after)
    if a == b:
        return None
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return a[i:] or "(글자 수는 같은데 순서가 다르다)"


def check_line_set(
    label: str,
    text: str,
    out: list[str],
    verbose: bool,
    tail: bool = False,
    limit: int = LIMIT,
) -> None:
    shown_lines = []
    for ln in text.split("\n"):
        shown_lines += wrap_ex(ln, limit)
    miss = lost(text, "\n".join(shown_lines))
    if miss:
        out.append(f"{label}: ⑦ 글 소실 — {miss!r}")
    for i, ln in enumerate(shown_lines):
        if verbose:
            print(f"   {width(ln):3d}px |{ln}|")
        if i and ln == "" and i < len(shown_lines) - 1:
            out.append(f"{label}: ② 빈 줄")
        if ln.startswith(" ") and not (tail and i == 0):  # 꼬리 조각은 숫자·이름 뒤에 붙는다
            out.append(f"{label}: ③ 줄 첫칸 공백 — {ln!r}")
        if i and ln and set(ln.strip()) <= PUNCT:
            out.append(f"{label}: ① 고아 부호 — {ln!r}")
    if re.search(r"\((을|를|은|는|이|가|과|와|으로|로)\)", text):
        out.append(f"{label}: ⑤ 조사 병기 — {text!r}")


BATTLE_LIMIT = 288  # 전투 창(`$2165A`, 312×48) 한 줄 — 반각 숫자 60자를 넣은 시험 롬으로 쟀다: 48자(288px)에서 글자 단위로 넘어간다(09-27, `r5-typeset-battle-288px.png`)
DIALOG_LIMIT, DIALOG_CODE = (
    210,
    0x30000,
)  # 대사창 210px — 원판도 글자 단위로 저절로 넘긴다(전각 17자 뒤, 09-27 실측) · 미니게임·오델로 문안(4줄 쪽)이 쓰는 창
BATTLE_CODE = (
    0x22000,
    0x25000,
)  # 코드 영역의 전투 문안(시스템 메시지 정본에 든다) — 전투 창으로 잰다
# 🔴 조사·주어를 **코드가 먼저 그리는** 조각 — 원문이 「は…」「の…」로 시작한다(몬스터 이름을 코드가 그린 뒤
# 이 조각을 잇는다). 조각만 재면 이름 몫이 빠져 폭이 모자라게 나온다(09-27 전투 145 조각 중 다수).
SUBJECT_FIRST = re.compile(r"^(<08>)?[はのがをにともへで、 ]")
# 전투에서 코드가 잇는 순서를 아는 것 — (이름, [조각 열쇠(시스템 6자리 · 전투 해시) 또는 {자리}])
BATTLE_CHAINS = [
    # 「(대상) 9999의 대미지!!」 — 수치 앞 공백 한 칸은 **게임이** 붙인다($236C0: 8칸 칸에서 앞 공백을 건너뛰고 한 칸 되돌린다)
    ("전투 대미지", ["024a68", " ", "{num}", "024a6c"]),
    ("전투 회심", ["024a96", "024a68", " ", "{num}", "024a6c"]),
    ("전투 주문 · 몬스터가 남에게", ["{name}", "d5d969f1ab", "{spell}", "a35f88d0e2"]),  # 블록 73
]


def width_jp(s: str) -> int:
    """원판 폭 — 반각 가나(U+FF61~)도 6px."""
    return sum(HALF if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else FULL for c in s)


def _jp_battle() -> dict[str, str]:
    import battle

    _, strs = battle.survey(common.rom())
    return {k: e["text"] for k, e in strs.items()}


def battle_texts() -> list[tuple[str, str]]:
    """(이름, 조립한 문안) — 전투 영역 전부(전투 아카이브 + 코드 영역 전투 문안 + 아는 조립 순서)."""
    import battle

    mons = json.loads((T / "monsters.json").read_text(encoding="utf-8"))
    f = fillers()
    longest_mon = longest([v["ours"] for v in mons.values() if v.get("ours")]) + "A"
    name = longest([f["name"], longest_mon])
    f = {**f, "name": name}
    bt = json.loads((T / "battle.json").read_text(encoding="utf-8"))
    sm = json.loads((T / "sysmsg.json").read_text(encoding="utf-8"))
    jp = _jp_battle()
    smjp = _jp_sysmsg()
    out = []

    def prep(s: str, jp_s: str) -> str:
        try:
            s = battle.expand_names(s, mons)
        except SystemExit:
            pass
        if SUBJECT_FIRST.match(jp_s or ""):
            s = re.sub(r"^(<08>)?", lambda m: (m.group(1) or "") + "{name}", s, count=1)
        if s.endswith("<06>"):
            s += "{num}"
        s = s.replace("<01>", "\n").replace("<05>", "\n")
        s = re.sub(r"<02>|<09[0-9a-f]{2}>", "{name}", s)
        s = s.replace("{name}", f["name"]).replace("{num}", f["num"])
        return expand(s, f)

    for k, o in bt.items():
        s = o.get("ours") or ""
        if s:
            out.append((f"battle {k}", prep(s, jp.get(k.split("@")[0], ""))))
    for k, o in sm.items():
        s = o.get("ours") or ""
        if s and BATTLE_CODE[0] <= int(k, 16) < BATTLE_CODE[1]:
            out.append((f"sysmsg {k}", prep(s, smjp.get(k, ""))))
    for label, parts in BATTLE_CHAINS:
        buf = "".join(
            f[p[1:-1]]
            if p.startswith("{")
            else (sm.get(p) or bt.get(p) or {"ours": p})[
                "ours"
            ]  # 정본에 없는 열쇠는 글자 그대로(공백 등)
            for p in parts
        )
        buf = buf.replace("<01>", "\n").replace("<05>", "\n")
        buf = re.sub(r"<02>|<09[0-9a-f]{2}>", f["name"], buf)
        out.append((label, expand(buf, f)))
    return out


def battle_region(out: list[str]) -> None:
    """전투 문안 — 이름 자리엔 가장 긴 파티·몬스터 이름(+접미 A). 줄은 `<01>`, 쪽은 `<05>`."""
    for label, text in battle_texts():
        check_line_set(label, text, out, False, tail=True, limit=BATTLE_LIMIT)


def scene_region(out: list[str]) -> None:
    """씬 대사 — 빌드와 같은 조판기(`build.typeset`, 210px × 3줄)를 돌린 결과를 본다."""
    import build

    for p in sorted((common.GAME_DIR / "script").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for off, e in d.get("streams", {}).items():
            s = e.get("ours") or ""
            if not s or e.get("raw"):  # raw 장 카드는 조판기를 안 탄다(빌드와 같게)
                continue
            body = re.sub(r"<[0-9a-f]{2}(:[0-9a-f]+)?>|<[0-9a-f]{4,}>", "", s)
            try:
                pages = build.typeset(body)
            except SystemExit as err:
                out.append(f"scene {p.stem}/{off}: ④ 조판 실패 — {err}")
                continue
            miss = lost(build.normalize(body), "".join("".join(pg) for pg in pages))
            if miss:
                out.append(f"scene {p.stem}/{off}: ⑦ 글 소실 — {miss!r}")
            for pg in pages:
                check_line_set(
                    f"scene {p.stem}/{off}", "\n".join(pg), out, False, limit=DIALOG_LIMIT
                )


# ── 원판(JP) — 같은 규칙을 원문에 대 본다(①~④만; ⑤⑥⑦은 한국어 조판의 축이라 해당 없다) ──────


def _jp_sysmsg() -> dict[str, str]:
    import sysmsg

    d = common.rom()
    return {f"{t:06x}": sysmsg.render(e["stream"]) for t, e in sysmsg.streams(d).items()}


def _jp_fill() -> dict[str, str]:
    import battle

    nm = json.loads((T / "names.json").read_text(encoding="utf-8"))
    jp = lambda cat: [o["jp"] for o in nm[cat].values() if o.get("jp")]
    mons = [
        r["name"].decode("cp932", "replace")
        for _s, b, _e in battle.blocks(common.rom())
        for r in battle.records(b)
    ]
    lw = lambda xs: max(xs, key=width_jp)
    # 파티 이름 원문엔 피치 태그(FE 0C … FE 10)가 든다 — 글자만 남긴다
    party = [
        re.sub(r"[\x00-\x1f\ue000-\uf8ff]|<[0-9a-f]+>", "", s).strip() for s in jp("party_name")
    ]
    return {
        "name": lw(party + mons),
        "item": lw(jp("item")),
        "spell": lw(jp("spell")) + "８",
        "num": "9999",
    }


def jp_line_set(label: str, text: str, out: list[str], limit: int) -> None:
    for i, ln in enumerate(text.split("\n")):
        w = width_jp(ln)
        if i and ln == "" and i < len(text.split("\n")) - 1:
            out.append(f"{label}: ② 빈 줄")
        if ln.startswith((" ", "　")) and i:
            out.append(f"{label}: ③ 줄 첫칸 공백")
        if w > limit:
            acc, cut = 0, len(ln)
            for k, c in enumerate(ln):
                acc += width_jp(c)
                if acc > limit:
                    cut = k
                    break
            rest = ln[cut:]
            kind = "① 고아 부호" if rest and set(rest) <= set("。、！？!?.,") else "④ 저절로 줄넘김"
            out.append(f"{label}: {kind} — {w}px")


def jp_expand(s: str, f: dict[str, str], num: bool = True) -> str:
    s = re.sub(r"<02>|<0b>|<09[0-9a-f]{2}>", f["name"], s)
    s = re.sub(r"<0e>", f["item"], s)
    s = re.sub(r"\n?<0[135]>", "\n", s.replace("<01>", "\n"))
    if num:  # 시스템·전투의 끝 06 = 수치 자리. 씬의 06 은 반환이다
        s = re.sub(r"<(06)[^>]*>$", f["num"], s)
    return re.sub(r"<[^>]*>", "", s)


def jp_counts() -> dict[str, int]:
    """영역별 원판 위반 수 — 시스템(210px) · 전투(288px) · 씬(210px, 정본이 든 블록만)."""
    import archives
    import scene

    f = _jp_fill()
    sm = json.loads((T / "sysmsg.json").read_text(encoding="utf-8"))
    smjp = _jp_sysmsg()
    sysv, bv, sv = [], [], []
    for k in sm:
        if k not in smjp:
            continue
        in_b = BATTLE_CODE[0] <= int(k, 16) < BATTLE_CODE[1]
        s = smjp[k]
        if SUBJECT_FIRST.match(s):
            s = f["name"] + s
        lim = BATTLE_LIMIT if in_b else DIALOG_LIMIT if int(k, 16) >= DIALOG_CODE else LIMIT
        jp_line_set(f"sysmsg {k}", jp_expand(s, f), bv if in_b else sysv, lim)
    for k, s in _jp_battle().items():
        if SUBJECT_FIRST.match(s):
            s = f["name"] + s
        jp_line_set(f"battle {k}", jp_expand(s, f), bv, BATTLE_LIMIT)
    d = common.rom()
    bl = archives.blocks(d, archives.ARCHIVES["script"][0])
    for p in sorted((common.GAME_DIR / "script").glob("*.json")):
        mod = scene.parse_module(bl[int(p.stem)][1])
        for off, e in json.loads(p.read_text(encoding="utf-8")).get("streams", {}).items():
            if not e.get("ours") or e.get("raw") or int(off, 16) not in mod.streams:
                continue  # raw = 손으로 가운데 맞춘 장 카드(빈 줄·앞 공백이 자리다)
            txt = mod.streams[int(off, 16)].text()
            jp_line_set(f"scene {p.stem}/{off}", jp_expand(txt, f, num=False), sv, DIALOG_LIMIT)
    return {"시스템": len(set(sysv)), "전투": len(set(bv)), "씬": len(set(sv))}


def main(verbose: bool) -> int:
    sm = json.loads((T / "sysmsg.json").read_text(encoding="utf-8"))
    f = fillers()
    if verbose:
        print("채우는 값:", f)
    out: list[str] = []
    for label, parts in CHAINS:
        buf = ""
        for p in parts:
            buf += f[p[1:-1]] if p.startswith("{") else sm[p]["ours"]
        text = expand(buf, f)
        if verbose:
            print(f"── {label}")
        check_line_set(label, text, out, verbose)
    # 홀로 선 조각도 한 번씩(이어 붙이는 순서를 모르는 것) — 끝이 <06> 이면 숫자를 붙여 본다
    for k, o in sm.items():
        s = o.get("ours") or ""
        if (
            not s or BATTLE_CODE[0] <= int(k, 16) < BATTLE_CODE[1]
        ):  # 전투 창 문안은 전투 영역에서 잰다
            continue
        text = expand(s + ("{num}" if s.endswith("<06>") else ""), f).replace("{num}", f["num"])
        # 미니게임·오델로(0x30000~)는 4줄 쪽 — 대사창(210px, 넘치면 글자 단위로 저절로 넘긴다)
        lim = DIALOG_LIMIT if int(k, 16) >= DIALOG_CODE else LIMIT
        check_line_set(f"sysmsg {k}", text, out, False, tail=True, limit=lim)
    sysv = list(dict.fromkeys(out))
    bv: list[str] = []
    battle_region(bv)
    sv: list[str] = []
    scene_region(sv)
    bv, sv = list(dict.fromkeys(bv)), list(dict.fromkeys(sv))
    for ln in sysv + bv + sv:
        print("  ❌", ln)
    print(
        f"  조판 검사 — 시스템 {len(sysv)} (조립 {len(CHAINS)} · 조각 {len(sm)}, {LIMIT}px)"
        f" · 전투 {len(bv)}({BATTLE_LIMIT}px 실측) · 씬 {len(sv)}({DIALOG_LIMIT}px)"
    )
    if "--jp" in sys.argv:
        print("  원판(JP, ①~④) —", " · ".join(f"{k} {v}" for k, v in jp_counts().items()))
    return 1 if (sysv or bv or sv) else 0


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv))
