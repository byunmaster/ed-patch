#!/usr/bin/env python3
"""런타임 조립 글 검사 — 구운 롬의 씬 블록을 **스크립트 VM 으로 따라가** 화면에 이어 찍히는 창 단위 글을 뽑고 검사한다(11-18).

번역 정본·메시지 한 줄씩의 검사로는 못 잡는다: 원판은 메시지를 **조각**으로 쪼개 호출·점프·표 분기로 이어 찍는다
(「으음.」+「이건 분명…」 → 「으음.이건」, 「어!?」+「이, 이건…」 → 「어!?이」). 조각 하나하나는 멀쩡하고 **이은 글**만 깨진다.

VM(상태 문서 3절 옵코드 + 11-18 실측):
    00 끝(창 닫힘) · 05 쪽 넘김+지움 · 03 쪽 대기(창 유지) · 06/07 서브루틴이면 복귀 · 01 줄바꿈 · 1F 이름 04 화자 머리
    09 nn 공용 문구 · 0F 점프 · 10 호출(복귀 있음) · 11/12 조건(두 갈래: 3B 뒤로 가기 / 뒤의 점프까지 건너뛰기)
    13/14/15 3B 건너뜀 · 16 호출표(`16` + 포인터 5개 = 한 명이 골라 부르고 표 뒤로 복귀 — 씬 69 의 「으음.」 넷)
    그 밖의 옵코드는 `M.OTHER_OPS`/`M.TEXT_OPS` 길이.
모든 메시지 시작(원문 블록 `M.parse`)에서 출발해 갈래를 전부 돈다(경로 수 상한). 조각 경계는 `∥` 로 표시해 둔다.

    python3 games/pce-ed1/tools/runtime_text.py [--iso <ed1.iso>] [--scene N] [--all-windows] [--dump out.tsv]
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import jump_readout as J
import messages as M

CODE = "⟨#⟩"  # 이름·수치를 찍는 코드 호출 자리
BOUND = "∥"  # 조각 경계(점프·호출·복귀·표 분기 지점)
MAX_PATHS = 48
MAX_STEPS = 600
TABLE_N = 5


def _is_msg_start(buf: bytes, p: int) -> bool:
    return 0 <= p < len(buf) and (buf[p] >= 0x24 or buf[p] in (0x1F, 0x09, 0x01))


def walk(buf: bytes, start: int, inv: dict, starts: frozenset = frozenset()) -> list[list]:
    """`start` 에서 출발한 경로들 — 경로 = 이벤트 목록. 이벤트: ("t", 글) · ("nl",) · ("pg",) · ("clr",) · ("end",) · ("com", nn) · ("head", 이름) · ("b",)."""
    paths: list[list] = []
    work = [(start, (), [], 0)]  # (pos, stack, events, steps)
    seen_states: set = set()
    while work and len(paths) < MAX_PATHS:
        pos, stack, ev, steps = work.pop()
        while True:
            steps += 1
            if steps > MAX_STEPS or not (0 <= pos < len(buf)):
                paths.append(ev + [("end",)])
                break
            key = (pos, stack, len(ev) // 8)
            b = buf[pos]
            if b == 0x00:
                paths.append(ev + [("end",)])
                break
            if b in (0x06, 0x07):
                if stack:
                    pos, stack = stack[-1], stack[:-1]
                    ev = ev + [("b",)]
                    continue
                if buf[pos - 2 : pos] == b"\x05\x04":  # 쪽 넘김 뒤 `04 06` — 서브루틴 밖에서도 스크립트가 다음 쪽으로 이어진다(씬 69 「…05 04 06」 뒤 「 석비에는」 11-18 실측)
                    pos += 1
                    ev = ev + [("b",)]
                    continue
                paths.append(ev + [("end",)])
                break
            if b == 0x01:
                ev = ev + [("nl",)]
                pos += 1
            elif b == 0x03:
                ev = ev + [("pg",)]
                pos += 1
            elif b == 0x05:
                ev = ev + [("clr",)]
                pos += 1
            elif b == 0x1D:
                ev = ev + [("code",)]  # 수치 찍기(1D 22)
                pos += 1
            elif b == 0x04 or 0x19 <= b <= 0x20 and b != 0x1F:
                pos += 1
            elif b == 0x1F:
                q = pos + 1
                name = bytearray()
                while q < len(buf) and buf[q] != 0x04 and len(name) < 40:
                    if buf[q] == 0x0F:
                        q = (buf[q + 1] | buf[q + 2] << 8) - M.BASE
                        continue
                    name.append(buf[q])
                    q += 1
                ev = ev + [("head", J._head(bytes(name), inv))]
                pos = q + 1
            elif b == 0x09:
                ev = ev + [("com", buf[pos + 1])]
                pos += 2
            elif b == 0x0F:
                t = (buf[pos + 1] | buf[pos + 2] << 8) - M.BASE
                if not 0 <= t < len(buf):
                    paths.append(ev + [("end",)])
                    break
                ev = ev + [("b",)]
                pos = t
                if key in seen_states:
                    paths.append(ev + [("end",)])
                    break
                seen_states.add(key)
            elif b == 0x10:
                t = (buf[pos + 1] | buf[pos + 2] << 8) - M.BASE
                if 0 <= t < len(buf) and len(stack) < 4 and (t in starts or buf[t] in (0x16, 0x1F, 0x09, 0x01, 0x05, 0x03, 0x0D, 0x11, 0x12, 0x13, 0x14, 0x10, 0x0F)):
                    stack = stack + (pos + 3,)
                    ev = ev + [("b",)]
                    pos = t
                else:
                    ev = ev + [("code",)]  # 코드 서브루틴 — 이름·수치를 찍을 수 있다(뒤 글 앞 공백이 정당한 자리)
                    pos += 3
            elif b == 0x16:
                ptrs = []
                q = pos + 1
                for _ in range(TABLE_N):
                    if q + 1 >= len(buf):
                        break
                    ptrs.append((buf[q] | buf[q + 1] << 8) - M.BASE)
                    q += 2
                ok = [t for t in dict.fromkeys(ptrs) if 0 <= t < len(buf)]
                if not ok:
                    pos = q
                    continue
                for t in ok[1:]:
                    work.append((t, stack + (q,), ev + [("b",)], steps))
                stack = stack + (q,)
                ev = ev + [("b",)]
                pos = ok[0]
            elif b in (0x11, 0x12):
                nxt = pos + 3
                if nxt < len(buf) and buf[nxt] == 0x0F:  # 조건이 거짓이면 뒤의 점프를 건너뛴다
                    work.append((nxt + 3, stack, ev, steps))
                pos = nxt
            elif b in (0x13, 0x14, 0x15):
                if b == 0x15:
                    ev = ev + [("code",)]
                pos += 3
            elif b == 0x0C:
                ev = ev + [("sfx", buf[pos + 1] if pos + 1 < len(buf) else -1)]  # 효과음(0C nn) — 원판 대비 수 감소 검사용
                pos += 2
            elif b in M.OTHER_OPS:
                if b == 0x0D:
                    ev = ev + [("code",)]  # 0D 08 = 주문 현자 꼬리 앞 이름 찍기
                pos += max(1, M.OTHER_OPS[b])
            elif b >= 0x24:
                s = pos
                while pos < len(buf) and buf[pos] >= 0x24:
                    pos += 2
                txt, _u = J._dec2(buf[s:pos], inv)
                ev = ev + [("t", txt)]
            else:
                if b == 0x0E:
                    ev = ev + [("code",)]  # 0E = 이름 찍기(상점 「(품목) 말씀이군요」 앞)
                pos += 1
    return paths


def windows(ev: list) -> list[str]:
    """이벤트 → 창 글(화자 머리 〔…〕 · 줄바꿈 \\n · 쪽 대기 ⏸ · 경계 ∥). 창 = 05(지움)·00(끝) 사이."""
    out: list[str] = []
    cur: list[str] = []
    first = True
    for e in ev:
        k = e[0]
        if k == "t":
            cur.append(e[1])
        elif k == "nl":
            cur.append("\n")
        elif k == "pg":
            cur.append("⏸")
        elif k == "b":
            cur.append(BOUND)
        elif k == "code":
            cur.append(CODE)
        elif k == "head":
            cur.append(f"〔{e[1]}〕")
        elif k == "com":
            cur.append(f"<공용{e[1]}>")
        elif k in ("clr", "end"):
            s = "".join(cur)
            if s.strip(BOUND + "\n ⏸"):
                out.append(("⟦시작⟧" if first else "") + s)
            first = False
            cur = []
    return out


# ---- 검사 -------------------------------------------------------------------------------------------------------

END_PUNCT = ".!?…~)」』"
HANGUL = "가-힣"


def strip_head(w: str) -> str:
    return re.sub(r"〔[^〕]*〕\n?", "", w)


SPACES = (" ", "\u2002", "\u200a", "\u3000")
START = "⟦시작⟧"  # 경로 첫 창 표지 — 꼬리 조각에서 출발한 인공 창일 수 있어 첫칸 공백은 화자 머리가 있을 때만 센다


def checks(w: str) -> list[tuple[str, str]]:
    """창 글 하나의 결함 목록 [(분류, 근거)]. 경계(∥) 없는 글은 조판 검사 몫이라 건너뛰는 것은 ① 뿐이다."""
    out: list[tuple[str, str]] = []
    artificial = w.startswith(START)
    w = w.removeprefix(START)
    flat = w.replace(BOUND, "")
    m0 = re.search(r"[가-힣A-Za-z0-9.!?]", w)  # 첫 글자 앞에 코드(이름·수치 찍기)가 있으면 앞 공백은 정당하다
    has_code = CODE in (w[: m0.start()] if m0 else w)
    flat = flat.replace(CODE, "")
    # ① 조각 경계에서 문장 끝 부호 + 한글이 붙음 (「으음.이건」 「어!?이」)
    for m in re.finditer(rf"([{re.escape(END_PUNCT)}])\s*{BOUND}+\s*([{HANGUL}])", w):
        if not re.search(rf"[{re.escape(END_PUNCT)}]{BOUND}+[ \n]|[{re.escape(END_PUNCT)}][ \n]{BOUND}", w[m.start() : m.end() + 1]):
            out.append(("붙음", w[max(0, m.start() - 6) : m.end() + 6]))
    # ② 한글 + 경계 + 한글: 낱말 한가운데가 아니라면 공백이 있어야 하는 경계 — 어절 끝 표지(다/요/죠/까/라/네/군/지…)로 끝나는 조각만 의심
    for m in re.finditer(rf"([다요죠까라네군지어야]\.?)(?<![.])\s*{BOUND}+([{HANGUL}])", w):
        pass
    # ③ 창 첫 칸 공백 (화자 머리 뒤 본문 첫 글자가 공백). 코드가 앞에 뭘 찍는 창(이름·수치)이나 꼬리 조각에서 출발한 인공 창은 정당하다
    body = strip_head(flat).lstrip("⏸")
    if not has_code and (not artificial or w.startswith("〔")) and (body[:1] in SPACES or (body[:1] == "\n" and body[1:2] in SPACES)):
        out.append(("첫칸공백", body[:10]))
    # ③-b 쪽 대기(⏸) 뒤 새 쪽 첫 칸 공백 (씬 69 「 석비에는」)
    for m in re.finditer(r"⏸[\u2060∥⟨코드⟩\n]*([ \u2002\u200a\u3000])", w):
        if CODE not in w[m.start() : m.end()]:
            out.append(("쪽첫공백", w[max(0, m.start() - 8) : m.end() + 6]))
            break
    # ④ 줄 첫 칸 공백(줄바꿈 바로 뒤)
    if re.search(r"\n[   ]", flat):
        out.append(("줄첫공백", re.search(r".{0,6}\n[   ].{0,6}", flat).group(0)))
    # ⑤ 공백 둘
    if re.search(r"[가-힣.!?…,] {2,}[가-힣]", flat):
        out.append(("공백둘", re.search(r".{0,6}[가-힣.!?…,] {2,}[가-힣].{0,4}", flat).group(0)))
    # ⑥ 화자 이름이 본문에 반복 (「로엘로엘」 · 머리 뒤 이름 또 나옴)
    for hm in re.finditer(r"〔([^〕]*)〕\n?", w):
        nm = hm.group(1).strip()
        if len(nm) >= 2:
            rest = w[hm.end() :].replace(BOUND, "").lstrip("\n⏸ ")
            if rest.startswith(nm) or re.match(rf"{re.escape(nm)}{re.escape(nm)}", rest):
                out.append(("이름반복", f"〔{nm}〕 {rest[:14]}"))
    for m in re.finditer(r"([가-힣]{2,4})\1", flat):
        if m.group(1) not in ("두두", "서서", "하하", "소소"):
            out.append(("글자반복", flat[max(0, m.start() - 4) : m.end() + 4]))
    # ⑦ 모르는 글자 코드
    if "<?" in w:
        out.append(("모르는코드", re.search(r".{0,6}<\?[0-9a-f]+>.{0,4}", w).group(0)))
    return out


def scan(iso: Path, only: int | None = None, quiet: bool = False):
    track = J.built_track(iso)
    found = containers.scan(track)
    rows = []
    n_win = 0
    for f in sorted(glob.glob(str(common.OUT_DIR / "text" / "*.bin"))):
        sid = int(re.search(r"_(\d+)\.bin$", f).group(1))
        if only is not None and sid != only:
            continue
        orig = Path(f).read_bytes()
        nb = J._blocks(found, sid, orig)
        if nb is None:
            continue
        inv = J.inverse_table(sid)
        seen: dict[str, int] = {}
        msgs = M.parse(orig)
        starts = frozenset(m.start for m in msgs)
        for m in msgs:
            for p in walk(nb, m.start, inv, starts):
                for w in windows(p):
                    if w not in seen:
                        seen[w] = m.start
        for w, st in seen.items():
            n_win += 1
            for cls, why in checks(w):
                rows.append({"sid": sid, "at": st, "cls": cls, "why": why, "win": w})
    return rows, n_win


def main() -> int:
    argv = sys.argv[1:]
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if "--iso" in argv:
        iso = Path(argv[argv.index("--iso") + 1])
    only = int(argv[argv.index("--scene") + 1]) if "--scene" in argv else None
    rows, n = scan(iso, only)
    print(f"창 {n}개 훑음 · 결함 후보 {len(rows)}")
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["cls"], []).append(r)
    for cls, rs in by.items():
        print(f"\n## {cls} {len(rs)}")
        for r in rs[:80]:
            print(f"  씬 {r['sid']}@{r['at']}: {r['why']!r}")
    if "--dump" in argv:
        Path(argv[argv.index("--dump") + 1]).write_text("\n".join(f"{r['sid']}\t{r['at']}\t{r['cls']}\t{r['why']!r}\t{r['win']!r}" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
