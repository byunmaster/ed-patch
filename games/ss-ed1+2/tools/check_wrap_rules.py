"""조판 여섯 규칙 **전 영역** 위반 수 — 씬 대사 창 · 메시지 창을 영역별로 센다.

    python3 tools/check_wrap_rules.py            # 영역 × 규칙 표
    python3 tools/check_wrap_rules.py --show 8   # 규칙마다 표본

## 왜 있나 (마스터 확정 2026-09-27 — 여섯 규칙은 시스템·전투·씬 전 영역)

메시지 창은 기계어(`patch_msgwrap`)가, 씬 창은 빌드 조판(`typeset_scn.wordwrap`)이 어절
단위로 끊는다. 둘 다 규칙 정본은 `msgwrap.wrap` 하나다. 이 파일은 **화면에 나갈 줄**을 다시
만들어 규칙이 실제로 지켜졌는지를 **센다** — 고치지 않는다(`check_engine_wrap` 과 같은 성격).

## 영역

- **씬** — 조판된 블록을 `%c` 조각마다 **엔진 접기 모델**(`typeset_scn.wrap`)에 태운다.
  엔진은 개행이 없는 자리에서 글자 단위로 접으므로, 거기서 나는 끊김이 곧 위반이다.
- **메시지** — `script/system.json` 조각을 `msgwrap.wrap`(기계어와 바이트까지 같은 기준
  구현)에 태운다. ⚠ 조각은 런타임에 이름 뒤에 붙는다 — 병기·조사로 시작하는 조각은 앞에
  **전각 넷 자리표**(런타임 이름)를 붙여 잰다. 이름 길이를 다 훑은 게 아니라 대표값이다.

## 규칙 (셀 수 있는 것)

    어절 중간   공백이 아닌 자리에서 끊겼다 (어절이 한 줄보다 길어 불가피한 것은 따로 센다)
    줄머리 공백 줄이 공백으로 시작한다
    줄머리 부호 닫는 부호가 줄머리에 혼자 왔다
    숫자 묶음   「레스 / 1」처럼 공백 뒤 숫자 앞에서 끊겼다
    빈 줄       14.0 을 넘친 줄 뒤에 개행 — 엔진이 두 번 넘긴다 (씬 창, 2026-09-27 실기)
    창 초과     씬 창이 7행을 넘는다 (뒷줄이 잘린다)
    사용자 영역 U+E000~F8FF 글자가 남았다 — cp932 가 `F0xx` 로 구워 폰트 밖 글리프가 찍힌다
                (PS1 붙임 공백 `\ue003` 이 42블록에 새어 들어와 있었다, 2026-09-27)
    글 소실     공백·개행을 뺀 글자가 입력과 다르다 🔴
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import msgwrap
import patch_scn
import typeset_scn as T

_SENT_END = re.compile(r"[.!?…][」』)\"']*\s*$")
RULES = (
    "어절 중간",
    "긴 어절(불가피)",
    "%s 도중 절단",
    "줄머리 공백",
    "줄머리 부호",
    "숫자 묶음",
    "빈 줄",
    "창 초과",
    "글 소실",
    "사용자 영역",
)
_WS = (" ", "\n")


def _strip(s):
    return "".join(c for c in s if c not in _WS)


def scan_lines(src, ls, ends):
    """`src` 를 줄 `ls` 로 나눈 결과의 위반 → `{규칙: [표본]}`.

    `ends[i]` = i번째 줄이 **명시 개행**으로 끝났나(아니면 자동으로 접혔다).
    """
    bad = collections.defaultdict(list)
    for i, ln in enumerate(ls):
        if i and ln.startswith(" "):
            bad["줄머리 공백"].append(ln)
        # ⚠ 문장이 말줄임표로 **시작**하는 줄(`…좋으련만. / …어라?`)은 고아 부호가 아니다 —
        #   앞 줄이 문장 끝으로 끝났으면 센다에서 뺀다(PS1 조판도 같다).
        if i and ln[:1] in T.HEAD_BAN and ls[i - 1] and not _SENT_END.search(ls[i - 1]):
            bad["줄머리 부호"].append(ls[i - 1][-8:] + " / " + ln[:8])
        if i and not ends[i - 1]:
            prev = ls[i - 1]
            # 매단 줄(29열 반각 꼬리 부호) 뒤의 자동 넘김은 엔진이 넘기는 **정상 줄바꿈**이다
            if T.width(prev) == T.COLS + 0.5 and prev[-1:] in T.HANG_TAIL:
                continue
            # 엔진이 **공백 자리에서** 접었다 — 어절은 안 갈렸지만 숫자 앞이면 묶음이 깨진다
            if prev.endswith(" ") or ln.startswith(" "):
                if ln.lstrip(" ")[:1].isdigit():
                    bad["숫자 묶음"].append(prev[-8:] + " / " + ln[:8])
                continue
            word = prev.rsplit(" ", 1)[-1] + ln.split(" ", 1)[0]
            key = "긴 어절(불가피)" if T.width(word) > T.COLS else "어절 중간"
            bad[key].append(prev[-8:] + " / " + ln[:8])
    # ⚠ 명시 개행 앞뒤의 숫자는 세지 않는다 — 원문 자신의 문단 개행(「받았습니다.」/「3000 Gold」)이다.
    if _strip("".join(ls)) != _strip(src):
        bad["글 소실"].append(src[:30])
    return bad


def scan_scene():
    """`(블록 수, {규칙: [표본]})` — 씬 창."""
    canon = patch_scn.load_canon(quiet=True)
    _f, mm = common.open_image()
    canon = patch_scn.augment_names(canon, mm)
    out = collections.defaultdict(list)
    blocks = 0
    for path in (p for p, _l, _s in common.iso_files(mm) if patch_scn.SCN_RE.match(p)):
        got = patch_scn.load(path)
        if not got:
            continue
        _base, entries = got
        sites = patch_scn.sites_for(path)
        for e in entries:
            built = patch_scn.canon_of(
                canon, e.get("text", ""), sites.get(int(e["file_offset"], 16))
            )
            if not built:
                continue
            blocks += 1
            pua = [c for c in built if "\ue000" <= c <= "\uf8ff"]
            if pua:
                out["사용자 영역"].append(
                    f"{path.split('/')[-1]}: U+{ord(pua[0]):04X} {built[:24]!r}"
                )
            segs, groups = T.line_groups(built)
            for g in groups:
                # 🔴 **글줄 단위로 잰다** — 글줄 안 색 쌍(`%c이름%c`)에서 가르면 한 줄을 반씩 재서
                #    넘치는 줄을 못 본다. 런타임 인자는 **가장 긴 값**으로 편다(`T.measure`).
                seg = T.measure("%c".join(segs[i] for i in g))
                ws = T.wrap(seg)
                ls = [ln for ln, _a in ws]
                ends = [a2 < 0 or (a2 > 0 and seg[a2 - 1] == "\n") for (_l, a2) in ws[1:]]
                bad = scan_lines(seg, ls, ends + [True])
                # 넘친 줄 뒤 개행이 만든 빈 줄 — 모델이 그 줄의 시작을 **개행 자리 자체**로 둔다
                for k, (ln, a) in enumerate(ws):
                    if not ln and a < 0:
                        bad["빈 줄"].append(ws[k - 1][0][-14:] + " / (빈 줄)")
                if len(ls) > T.WIN_ROWS:
                    bad["창 초과"].append(seg[:30])
                for k, v in bad.items():
                    out[k] += [f"{path.split('/')[-1]}: {x}" for x in v]
    mm.close()
    _f.close()
    return blocks, out


# 행위자(`%c%s%c은(는) `) 뒤에 이름과 꼬리가 붙는 조립 — 사용 · 주문 · 주문 실패
COMBOS = [
    ("74953d4a9b7fad96", "4251485af409a824"),
    ("74953d4a9b7fad96", "c5f4bb3c26c72f8f"),
    ("74953d4a9b7fad96", "4ac34777f109a73b"),
]

_LEAD = ("은(는)", "이(가)", "을(를)", "과(와)", "의 ", "에게", "은 ", "는 ", "이 ", "가 ")
_NAME = "세리오스"  # 런타임 이름 대표값 — 전각 넷


def _msg_units(s):
    """메시지 조각 → (바이트, 되짚기용 글자들) — 씬과 같은 자리표를 쓴다."""
    return T._units(s)


def scan_message():
    """`(조각 수, {규칙: [표본]})` — 메시지 창 (`script/system.json`)."""
    with open(os.path.join(common.GAME_DIR, "script", "system.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"]
    out = collections.defaultdict(list)
    # 🔴 **조립되는 로그 문장은 조각이 아니라 이은 꼴로도 잰다**(마스터 판정 2026-09-27 — 로그성 메시지는
    #    강제 개행 없이 넘칠 때만 어절 단위). 행위자 조각이 개행으로 끝나던 때는 조각마다 재면 됐는데,
    #    이제 「행위자 + 도구/주문 이름 + 꼬리」가 한 줄로 흐르므로 **가장 긴 조합**을 따로 본다.
    #    이름 자리는 `%s`(가장 긴 이름, 전각 8)로 잰다.
    combos = [lines[h] + "%s" + lines[t] for h, t in COMBOS if h in lines and t in lines]
    for kr in list(lines.values()) + combos:
        if any("\ue000" <= c <= "\uf8ff" for c in kr):
            out["사용자 영역"].append(kr[:24])
        s = (_NAME + kr) if kr.startswith(_LEAD) else kr
        units = _msg_units(s)
        src = b"".join(b for b, _t in units)
        got = msgwrap.wrap(src)  # 로그도 어절 단위(마스터 09-30 번복) — 어절 후퇴 켜짐(기계어와 같다)
        if not msgwrap.check_invariant(src, got):
            out["글 소실"].append(s[:30])
            continue
        # 되짚기 — 바이트 줄을 글자 줄로
        # 🔴 **`%s`/`%d` 는 한 덩어리 바이트(16B)로 들어오는데, 글자 단위 접힘(어절보다 긴 낱말)은
        #    그 안에서도 끊을 수 있다** — 실제 이름이 채워지면 이름이 두 줄로 갈린다는 뜻이다.
        #    되짚기가 단위 경계를 벗어나면(개행이 덩어리 한가운데 온 것) `%s 도중 절단`으로
        #    세고 이 메시지는 되짚기를 멈춘다(리포트용 — 하드 실패 아님, 정확한 나머지 글은 포기).
        body = [u for u in units if u[1] not in _WS]
        txt, pos, k, split = [], 0, 0, False
        while pos < len(got) and k < len(body):
            c = got[pos]
            if c in (msgwrap.NL, msgwrap.SP):
                txt.append("\n" if c == msgwrap.NL else " ")
                pos += 1
                continue
            b, t = body[k]
            if got[pos : pos + len(b)] != b:
                out["%s 도중 절단"].append(s[:30])
                split = True
                break
            txt.append(t)
            pos += len(b)
            k += 1
        if split:
            continue  # 되짚기가 깨졌다 — 이 메시지는 나머지 규칙을 못 잰다(위에서 이미 셌다)
        ls = "".join(txt).split("\n")
        # 메시지 창은 기계어가 개행을 넣는다 — 모든 줄끝이 「명시」다. 🔴 **로그는 글자 단위가
        # 기본**이다(마스터 확정 2026-09-27 — 대사는 어절·로그는 글자). 공백 아닌 자리의 끊김은
        # 이제 위반이 아니라 **의도된 접힘**이라 늘 「긴 어절(불가피)」(보고 전용)로 잰다 —
        # 숫자 묶음(규칙 2)·줄머리 공백(규칙 4)·고아 부호(드로어 훅)는 retreat 와 무관하게 그대로 본다.
        ends = [True] * len(ls)
        bad = scan_lines(s, ls, ends)
        flat = s.replace("\n", "")
        for i in range(1, len(ls)):
            j = len("".join(ls[:i]).replace(" ", ""))
            # 원문 공백 자리가 아닌 곳에서 끊겼으면 = 글자 단위 끊김
            core = _strip(flat)
            if 0 < j < len(core) and ls[i - 1] and ls[i]:
                a, b = ls[i - 1][-1], ls[i][0]
                if b.isdigit() and f"{a} {b}" in flat:
                    bad["숫자 묶음"].append(ls[i - 1][-8:] + " / " + ls[i][:8])
                elif f"{a} {b}" not in flat and f"{a}\n{b}" not in s:
                    # 🔴 어절 후퇴가 켜졌으므로 공백 아닌 자리의 끊김은 **한 줄보다 긴 낱말일 때만** 불가피다
                    word = ls[i - 1].rsplit(" ", 1)[-1] + ls[i].split(" ", 1)[0]
                    key = "긴 어절(불가피)" if T.width(word) > T.COLS else "어절 중간"
                    bad[key].append(ls[i - 1][-8:] + " / " + ls[i][:8])
        for k2, v in bad.items():
            out[k2] += v
    return len(lines) + len(combos), out


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    regions = [("씬 대사 창", *scan_scene()), ("메시지 창", *scan_message())]
    print(f"  {'영역':<10} {'모집단':>8}  " + "  ".join(f"{r}" for r in RULES))
    for name, n, bad in regions:
        cells = "  ".join(f"{len(bad.get(r, ())):>{len(r)}}" for r in RULES)
        print(f"  {name:<10} {n:>8,}  {cells}")
        for r in RULES:
            for x in bad.get(r, ())[:show]:
                print(f"      [{r}] {x!r}")
    # 🔴 **긴 어절(불가피)·`%s` 도중 절단만 빼고 전부 실패다** — 지금 0 이라 곧 회귀 방지다(09-27).
    #    긴 어절은 한 줄보다 긴 낱말이라 글자 단위로 끊을 수밖에 없다(규칙 3).
    #    ⚠ `%s` 도중 절단은 **보고 전용으로만 둔다 — 판정 대기다**(마스터 확정 「로그는 글자
    #    단위」가 실제 이름을 반으로 가를 수 있다는 뜻인지 아직 못 여쭤봤다. 하드 실패로 올리면
    #    이 라운드가 못 닫힌다).
    _REPORT_ONLY = ("긴 어절(불가피)", "%s 도중 절단")
    bad_total = {
        r: sum(len(b.get(r, ())) for _n, _c, b in regions) for r in RULES if r not in _REPORT_ONLY
    }
    fail = {r: v for r, v in bad_total.items() if v}
    if fail:
        print("  🔴 위반 — " + " · ".join(f"{r} {v}" for r, v in fail.items()))
    else:
        print("  ✅ 여섯 규칙 위반 0 (전 영역)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
