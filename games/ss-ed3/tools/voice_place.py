"""인게임 음성 자막 **배치** — 초안 + 정적 타임라인 + 실측 프레임 → `script/voice.json` 의 `hooks[]`.

    python3 games/ss-ed3/tools/voice_place.py --skeleton V02      # 초안에서 뼈대(문안·화자·길이)
    python3 games/ss-ed3/tools/voice_place.py --recipe V02        # 에뮬에서 프레임 재는 법
    python3 games/ss-ed3/tools/voice_place.py --place V02 frames.json   # 실측 → hooks[]

V01 을 손으로 한 번 해 보고 나서 만들었다. 손으로 하면 장면마다 **같은 지루한 일 넷**을
반복하게 된다 — 초안 표를 JSON 으로 옮기고, 이름을 화자 번호로 바꾸고, 다음 마디까지의
간격으로 표시 시간을 잡고, 실측 프레임에서 `delay` 를 빼는 것. 열아홉 장면이 남았다.

🔴 **왜 정적 타임라인만으로는 안 되나** (V01 실측, 2026-09-06). `script_ops.py --timeline` 은
`FF 35` 대기만 세는데, 그 사이 **대기 아닌 옵코드가 프레임을 먹는다**. V01 에서 실측과 정적의
차이가 장면 내내 **-0.1 초 → +9.1 초**로 벌어졌고, 계단처럼 특정 자리에서 튀었다
(배우 이동 `FF 25`·`FF 30`·`FF 2E` 가 몰린 구간에서 88f·180f·139f). 옵코드별 고정 비용으로
설명되지도 않는다(같은 `FF 25` 넷이 한 번은 88f, 한 번은 139f — 인자에 따라 다르다).
⇒ **자리는 정적으로 고르고, 프레임은 반드시 실기에서 잰다.** 이 파일이 그 둘을 잇는다.

🔑 **재는 법은 「스크립트 PC 전역에 값 필터를 건 쓰기 브레이크포인트」다** — `--recipe` 참조.
   ⚠ 좁게 걸면 **안 걸린다** — `0x9408C..0x9408F` 로는 한 번도 안 멈췄고
   `0x94080..0x9409F` 로 넓히니 걸렸다(2026-09-06 실측, mednafen 어댑터).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

FPS = 59.83  # 실측(NTSC 새턴) — 프레임↔초는 이 값으로만 환산한다
BASE = 0x200000  # 스크립트 포인터 기준 (voice_sub.BASE 와 같다)
PCVAR = 0x0609408C  # 스크립트 PC 전역
PCVAR_BP = (0x94080, 0x9409F)  # ⚠ 넓게 걸어야 걸린다 (위 독스트링)
DRAFT = os.path.join(C.REVIEW_DIR, "voice")
TIMELINE = os.path.join(DRAFT, "timeline")

#   전역 인물표(`/0.BIN` 0x76c60) — 이 미만(0x14)만 얼굴이 있다. 맵 이름표는 맵마다 달라서
#   여기서 못 정한다(`speaker: null` 로 두고 사람이 채운다).
CAST = {
    "쥬리오": 0,
    "크리스": 1,
    "샤라": 2,
    "구스": 3,
    "로디": 4,
    "휘리": 5,
    "알프": 6,
    "모리슨": 7,
    "죠안나": 8,
    "스텔라": 9,
    "바다트": 0xA,
    "방방": 0xB,
    "듀르젤": 0xC,
    "허크": 0xD,
    "라프": 0xE,
    "이자벨": 0xF,
    "레바스": 0x10,
    "카지무": 0x11,
    "알프레드": 0x12,
    "루레": 0x13,
}
DUR_MIN, DUR_MAX, DUR_GAP = 1.0, 6.0, 0.15  # 다음 마디까지 — 살짝 앞서 닫는다

#   장면 → (맵, `FF 42` 자리). 맵은 `docs/status.md` 의 표와 같지만 **자리는 여기 말고
#   커밋되는 곳이 없다** — 초안(`work/review/`)은 gitignore 라 지우면 다시 찾아야 한다.
#   실행 경로 위에서 뽑은 값이다(`script_ops.py --path`).
SCENES = {
    "V01": ("MAP076", 0x1BC74),
    "V02": ("MAP002", 0x14068),
    "V03": ("MAP005", 0x0F48E),
    "V04": ("MAP006", 0x1BBE2),
    "V05": ("MAP014", 0x1779A),
    "V06": ("MAP015", 0x1A1D8),
    "V07": ("MAP017", 0x0EFD6),
    "V08": ("MAP019", 0x122BE),
    "V09": ("MAP035", 0x0FC2E),
    "V10": ("MAP031", 0x15910),
    "V11": ("MAP056", 0x187F6),
    "V12": ("MAP060", 0x14900),
    "V13": ("MAP046", 0x12372),
    "V14": ("MAP047", 0x1579E),
    "V15": ("MAP049", 0x116B6),
    "V16": ("MAP066", 0x0AECC),
    "V17": ("MAP083", 0x143A8),
    "V18": ("MAP003", 0x13D16),
    "V19": ("MAP052", 0x145E4),
    "V21": ("MAP031", 0x18428),
}


def parse_draft(name):
    """초안 표 → `[{t, who, jp, lines, warn}]`. `~`(시각 없음)은 앞 마디를 잇는다."""
    path = os.path.join(DRAFT, f"{name}-draft.md")
    if not os.path.exists(path):
        raise SystemExit(f"초안이 없다: {path}")
    rows = []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cell = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cell) < 4 or cell[0] in ("시각", "----") or set(cell[0]) <= set("- "):
            continue
        t, who, jp, kr = cell[0], cell[1], cell[2], cell[3]
        warn = "⚠" in who or "⚠" in kr or "⚠" in jp
        who = who.replace("⚠", "").strip()
        kr = re.sub(r"<!--.*?-->", "", kr).replace("⚠", "").strip()
        m = re.match(r"^([\d.]+)$", t)
        rows.append(
            {
                "t": float(m.group(1)) if m else None,
                "who": who,
                "jp": jp,
                "lines": [x for x in kr.split("\\n") if x],
                "warn": warn,
            }
        )
    return rows


def parse_timeline(name):
    """정적 타임라인 → `[{t, off, ops, len, wait}]` (자리 순서·후킹 길이의 출처)."""
    path = os.path.join(TIMELINE, f"{name}.txt")
    if not os.path.exists(path):
        raise SystemExit(f"타임라인이 없다 — `script_ops.py --timeline` 으로 먼저 뽑는다: {path}")
    out = []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for line in text.splitlines():
        m = re.match(
            r"\s*([\d.]+)초\s+(0x[0-9a-f]+)\s+(.*?)\s+← 후킹 (\d+)B(?: · 대기 (\d+)f)?", line
        )
        if m:
            out.append(
                {
                    "t": float(m.group(1)),
                    "off": int(m.group(2), 16),
                    "ops": m.group(3).strip(),
                    "len": int(m.group(4)),
                    "wait": int(m.group(5) or 0),
                }
            )
    return out


def durations(rows):
    """다음 마디까지의 간격으로 표시 시간을 잡는다 — 마지막은 `DUR_MAX` 로 닫는다."""
    ts = [r["t"] for r in rows]
    out = []
    for i, r in enumerate(rows):
        nxt = next((t for t in ts[i + 1 :] if t is not None), None)
        if r["t"] is None or nxt is None:
            out.append(round(min(DUR_MAX, DUR_MIN + 0.22 * sum(len(x) for x in r["lines"])), 1))
        else:
            out.append(round(max(DUR_MIN, min(DUR_MAX, nxt - r["t"] - DUR_GAP)), 1))
    return out


def skeleton(name):
    """초안 → 문안·화자·표시 시간까지 채운 `hooks[]`. `off`·`delay` 는 실측 몫이다."""
    rows = parse_draft(name)
    durs = durations(rows)
    hooks = []
    for r, d in zip(rows, durs, strict=True):
        who = r["who"]
        sp = next((v for k, v in CAST.items() if who.startswith(k)), None)
        h = {"off": None, "len": None, "_t": f"{r['t']}초" if r["t"] is not None else "~"}
        if r["warn"]:
            h["_warn"] = "초안에 ⚠ — 인게임에서 화자·문안을 확인한다"
        h["lines"] = r["lines"]
        h["speaker"] = sp
        h["who"] = who
        h["dur"] = d
        hooks.append(h)
    return hooks


def recipe(name, scene):
    """에뮬에서 프레임 재는 법 — 자리마다 값 필터를 건 브레이크포인트."""
    tl = parse_timeline(name)
    ff42 = next((r for r in tl if r["ops"].startswith("FF 42")), None)
    print(f"── {name} · {SCENES[name][0]} — 실측 절차")
    print("① 그 장면 직전 세이브를 띄우고, 스크립트 PC 전역에 **쓰기** BP 를 건다:")
    print(
        f"     kind=write · memory_type=workramh · start={PCVAR_BP[0]:#x} · end={PCVAR_BP[1]:#x}"
        " · pause_on_hit=true"
    )
    print(f"   ⚠ 좁게({PCVAR:#x} 하나만) 걸면 **안 걸린다** — 위 범위 그대로 건다.")
    print("② `value` 로 자리를 고른다(값 = 그 자리의 절대 주소, `value_len=4`).")
    print("   멈출 때마다 응답의 `frame` 을 적는다. 그게 그 자리에 **도착한 프레임**이다.")
    off42 = ff42["off"] if ff42 else SCENES[name][1]
    print(f"   t0 = `FF 42` {off42:#x} — value = {BASE + off42} ({BASE + off42:#x})")
    waits = [r for r in tl if r["wait"]]
    if waits:
        print("③ 아래 자리들을 같은 식으로 잰다(대기가 있는 자리만 — 마디가 그 안에 든다):")
        for r in waits:
            v = BASE + r["off"]
            print(f"     {r['off']:#08x}  len={r['len']:2}  대기 {r['wait']:4}f  value={v}")
    else:
        #   ⚠ 정적 걷기는 이름판·정렬 이탈에서 바로 멈춘다 — 그런 장면이 대부분이다.
        print("③ ⚠ 이 장면은 **정적 타임라인에 대기 자리가 없다**(걷기가 일찍 멈췄다).")
        print(
            "   그러면 값 필터를 걸지 말고 **멈출 때마다 훑는다** — 그게 곧 프레임이 붙은 경로다:"
        )
        print("     BP 를 값 필터 없이(pause_on_hit=true) 걸고 `resume` → `status.frame` →")
        print("     `poll_events` 의 `value`(= 다음에 실행할 스크립트 주소)를 한 쌍으로 적는다.")
        print("     `value - 0x200000` 이 곧 자리다. 한 장면에 쉰 번 남짓이면 끝난다.")
    print("④ 잰 값을 frames.json 으로 적고 `--place` 에 준다:")
    print('     {"t0": <FF42 프레임>, "sites": {"0x14068": 12345, …}}')


def place(name, scene, frames):
    """실측 프레임 → `hooks[]` (`off`·`len`·`delay` 까지)."""
    tl = {r["off"]: r for r in parse_timeline(name)}
    sites = sorted(((int(k, 0), v) for k, v in frames["sites"].items()), key=lambda x: x[1])
    if not sites:
        raise SystemExit("frames.json 에 `sites` 가 없다")
    hooks = skeleton(name)
    t0 = int(frames["t0"])
    out = []
    for h in hooks:
        m = re.match(r"([\d.]+)", h["_t"])
        if not m:
            h["_todo"] = "시각이 없다 — 초안에서 마디를 가른 뒤 다시 돌린다"
            out.append(h)
            continue
        target = t0 + round(float(m.group(1)) * FPS)
        prev = [(o, f) for o, f in sites if f <= target]
        if not prev:
            h["_todo"] = f"프레임 {target} 앞에 잰 자리가 없다 — 더 이른 자리를 잰다"
            out.append(h)
            continue
        off, f = prev[-1]
        h["off"], h["len"], h["delay"] = off, tl[off]["len"] if off in tl else None, target - f
        if h["delay"] == 0:
            del h["delay"]
        w = tl.get(off, {}).get("wait", 0)
        if h.get("delay", 0) > w:
            h["_todo"] = (
                f"delay {h['delay']} 가 그 자리 대기 {w}f 를 넘는다 — 다음 자리를 재서 쓴다"
            )
        out.append(h)
    return out


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skeleton", metavar="V0N")
    ap.add_argument("--recipe", metavar="V0N")
    ap.add_argument("--place", nargs=2, metavar=("V0N", "frames.json"))
    a = ap.parse_args()
    with open(os.path.join(C.GAME_DIR, "script", "voice.json"), encoding="utf-8") as f:
        doc = json.load(f)
    name = a.skeleton or a.recipe or (a.place[0] if a.place else None)
    if not name:
        ap.error("--skeleton · --recipe · --place 중 하나")
    scene = doc.get(name, {})
    if a.recipe:
        recipe(name, scene)
        return 0
    hooks = place(name, scene, _load(a.place[1])) if a.place else skeleton(name)
    print(
        json.dumps(
            {name: {"map": scene.get("map") or SCENES[name][0], "hooks": hooks}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
