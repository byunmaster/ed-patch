"""오프닝 자막 · 엔딩 나레이션 · 엔딩 대사 — 워드 스크립트 드라이버($14E44)의 표와 문안 영역.

표는 워드 열이다: 상위 니블 = 오프코드(0 문안 · 2 대기 · 4 페이드 · 6 팔레트 · 8 그림 · C 선택), 하위
12비트 = 인자, `FFFF` 로 끝난다. 오프코드 0 의 인자는 **표 머리(a3) 기준 전방 12비트 오프셋**
(`lea (a3,d2.w),a1` → 렌더러 $978C)이라 문안은 표 뒤 4,095B 안에 있어야 한다. 스트림은 대사와 같은
제어코드(`fe 0e` 피치 14 · `01` 줄바꿈 · `06` 끝)라 `scene.parse_stream` 으로 읽는다.

재삽입: 가족(표 묶음 + 문안 영역)마다 영역을 **제자리에서** 다시 채우고(원본 순서 · 짝수 정렬 · 남는
자리는 0), 표의 오프코드 0 워드를 새 오프셋으로 고친다. 영역 뒤는 코드·그래픽이라 넘치면 실패다.
"""

import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import scene
import sysmsg

from shared.text import krwrap

# (이름, 표 머리들, 문안 영역) — 영역 끝은 다음 자료의 머리(코드 · lea 로 참조되는 자료)
FAMILIES = [
    ("opening", (0x16224,), (0x16268, 0x16684)),  # 오프닝 자막 8 — 뒤는 코드
    ("ending-narr", (0x2DE9E,), (0x2DF0E, 0x2E14E)),  # 엔딩 나레이션 11 — 뒤는 그래픽 자료
    (
        "ending",  # 엔딩 대사 8화면 — 공용 지우기 스트림 <08><06> 이 머리에 있다(나레이션 표도 쓴다)
        (0x2ED38, 0x2ED46, 0x2ED84, 0x2EDB6, 0x2EDD0, 0x2EDDE, 0x2EE04, 0x2EE1E),
        (0x2EE2C, 0x2F1FE),
    ),
]
# 글꼴은 **스트림마다** 고른다 — 정본이 머리에 `<fd85>`(와이드 글꼴 5)를 달면 그 자막만 리소스 5 로 그리고
# 끝에 `<fd80>` 으로 대사 글꼴(리소스 0)로 되돌린다. 칸 16×16·피치 16(`<fe10>`) — 한 줄 14칸.
# 자막 글꼴 = **Galmuri11**(마스터 확정 2026-09-17 — 네오둥근모·갈무리14·갈무리11 세 후보를 같은 화면으로
# 비교, "크게 느껴진다"는 지적에 갈무리11 로). 그 전엔 네오둥근모였다(2026-09-06, 7줄 화면도 안 잘리고
# 여백비가 원본에 가깝다는 이유) — 그 전엔 Galmuri14 였다가 "붙어 보인다/가독성 저하"로 걷어냈다
# (여백 좌우2px·상하4px 인 원본 대비 Galmuri14 는 1px·2px 뿐이었다). `docs/devlog.md` 2026-09-06·09-17.
FONT_ID = 5
FONT_TAG = "<fd85>"
FONT_CELL = int(os.environ.get("MD_CAPTION_CELL", "16"))
# 후보 비교용 — 정본은 상수, `MD_CAPTION_FONT` 로 한 번씩 바꿔 구워 본다(실험 전용, 배포 빌드는 상수를 고친다).
FONT_SRC = os.environ.get("MD_CAPTION_FONT", "galmuri11")
WIDTH = 16  # 피치 14 × 16 = 224px
WIDTH_P16 = 14  # 피치 16 × 14 = 224px (네오둥근모)
OFF_MAX = 0xFFF
# 꼬리로 옮기는 가족 — (표 머리, 표 포인터 피연산자 자리). 드라이버는 오프코드 0 의 인자를
# **표 머리 기준 12비트 전방 오프셋**으로 읽으므로 표와 문안을 같이 옮기면 그대로 돈다.
# 제자리 영역이 만원이라(오프닝 1,052/1,052B · 나레이션 576/576B) 원문에 있는 말을 눌러 쓰고 있었다
# (2026-09-06 대조: 「어쩌면」·「필사적으로 싸웠고」·「살해」·「16세 생일」 …).
# ⚠ 옛 영역은 **0 으로 지운다** — 원문 바이트를 남기면 「남은 일본어」 검사가 그만큼 눈이 먼다.
RELOCATE = {
    "opening": (0x16224, 0x13782),  # lea $16224.l,a3 @0x13780
    "ending-narr": (0x2DE9E, 0x2DE92),  # lea $2de9e.l,a3 @0x2de90
}
EXPECT = (
    10,
    39,
)  # 표 · 고유 스트림 (2026-09-05 실측 — 지우기 스트림 <08><06> 을 표 9개가 같이 쓴다)
MAP_JSON = common.GAME_DIR / "textmap" / "captions.json"


def words(d: bytes, base: int) -> list[tuple[int, int, int]]:
    """표 → [(워드 자리, 오프코드, 인자)] — FFFF 앞까지."""
    out = []
    p = base
    while True:
        w = struct.unpack(">H", d[p : p + 2])[0]
        if w == 0xFFFF:
            return out
        out.append((p, w >> 12, w & 0xFFF))
        p += 2


def streams(d: bytes) -> dict[int, dict]:
    """문안 시작 → {stream, family, refs:[(표 머리, 워드 자리)]}."""
    out: dict[int, dict] = {}
    for _name, bases, _area in FAMILIES:
        for base in bases:
            for pos, op, arg in words(d, base):
                if op != 0:
                    continue
                t = base + arg
                if t not in out:
                    st = scene.parse_stream(d, t)
                    fam = next(n for n, _, (a, b) in FAMILIES if a <= t < b)
                    out[t] = {"stream": st, "family": fam, "refs": []}
                out[t]["refs"].append((base, pos))
    return dict(sorted(out.items()))


def check(d: bytes) -> None:
    strs = streams(d)
    ntab = sum(len(b) for _, b, _ in FAMILIES)
    for name, _, (lo, hi) in FAMILIES:
        mine = [s for s in strs.values() if s["family"] == name]
        used = max(s["stream"].end for s in mine) - lo
        print(f"  {name}: 스트림 {len(mine)} · 영역 {lo:#x}~{hi:#x} {hi - lo}B 중 {used}B")
        if any(s["stream"].end > hi for s in mine):
            raise SystemExit(f"{name}: 스트림이 영역을 넘는다")
    if (ntab, len(strs)) != EXPECT:
        raise SystemExit(f"자막 분모가 갈렸다 {(ntab, len(strs))} (기대 {EXPECT})")


def seed(d: bytes) -> None:
    strs = streams(d)
    cur = json.loads(MAP_JSON.read_text(encoding="utf-8")) if MAP_JSON.exists() else {}
    lines = []
    fam = None
    for t, e in strs.items():
        if e["family"] != fam:
            fam = e["family"]
            lines.append(f"# {fam}")
        st = e["stream"]
        k = f"{t:06x}"
        cur.setdefault(k, {"jp": sysmsg.jp_key(st), "ours": ""})
        lines.append(f"{k}\t{st.end - t}B\t{len(e['refs'])}ref\t{sysmsg.render(st)!r}")
    MAP_JSON.parent.mkdir(exist_ok=True)
    MAP_JSON.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    out = common.OUT_DIR / "text" / "captions.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {MAP_JSON}: {len(cur)} · 원문 {out}")


def _width_errors(k: str, ours: str) -> list[str]:
    import re

    limit = WIDTH_P16 if "<fe10>" in ours else WIDTH  # 피치가 폭을 정한다
    errs = []
    for ln in re.sub(r"<[^>]*>", "", ours).split("\n"):
        w = krwrap.text_width(ln.rstrip())
        if w > limit:
            errs.append(f"captions {k}: 줄 {w}칸 > {limit}: {ln!r}")
    return errs


def font5_chars(textmap: dict) -> set[str]:
    """리소스 5 로 그리는 자막이 쓰는 글자 — 그만큼만 글리프를 만든다."""
    import re

    out: set[str] = set()
    for e in textmap.values():
        if FONT_TAG in e.get("ours", ""):
            out.update(re.sub(r"<[^>]*>", "", e["ours"]))
    return out


def plan(
    d: bytes, textmap: dict, encode, tail_at: int | None = None
) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 목록. 번역이 하나라도 있는 가족만 영역·표를 다시 쓴다.

    `tail_at` 을 주면 `RELOCATE` 가족은 **표+문안을 꼬리로** 옮기고 표 포인터를 고친다(제자리 칸을
    안 쓰므로 문안 길이가 자유롭다). 옛 영역은 0 으로 지운다.
    """
    strs = streams(d)
    writes: list[tuple[str, int, bytes]] = []
    errs: list[str] = []
    newpos: dict[int, int] = {}
    areas: dict[str, bytes] = {}
    touched_fams = set()
    for name, _bases, (lo, hi) in FAMILIES:
        mine = [(t, e) for t, e in strs.items() if e["family"] == name]
        area = bytearray()
        for t, e in mine:
            st = e["stream"]
            k = f"{t:06x}"
            ent = textmap.get(k)
            if ent and ent.get("ours"):
                if ent["jp"] != sysmsg.jp_key(st):
                    raise SystemExit(f"captions {k}: 원문 해시가 갈렸다")
                errs += _width_errors(k, ent["ours"])
                body = b"".join(tk.raw for tk in sysmsg._tokens_from_ours(st, ent["ours"], encode))
                touched_fams.add(name)
            else:
                body = d[t : st.end]
            if len(area) & 1:
                area.append(0)
            newpos[t] = lo + len(area)
            area += body
        if tail_at is not None and name in RELOCATE and name in touched_fams:
            areas[name] = bytes(area)  # 자리는 표 길이를 안 뒤에 잡는다(아래 2패스)
            continue
        if len(area) > hi - lo:
            errs.append(f"captions {name}: 영역 {hi - lo}B 를 {len(area) - (hi - lo)}B 넘는다")
            continue
        area += b"\x00" * (hi - lo - len(area))
        if name in touched_fams:
            writes.append((f"captions:{name}", lo, bytes(area)))
    if errs:
        raise SystemExit("\n".join(errs))
    moved: dict[str, int] = {}  # 가족 → 꼬리의 표 머리
    local: dict[str, dict[int, int]] = {}  # 가족 → {스트림: 그 가족 블롭 안의 자리}(사본용)
    if tail_at is not None:
        cur = tail_at
        for name, (base, ptr) in RELOCATE.items():
            if name not in areas:
                continue
            ws = words(d, base)
            tbl_len = len(ws) * 2 + 2
            text_at = cur + tbl_len
            lo = next(a for n, _b, (a, _h) in FAMILIES if n == name)
            for t in list(newpos):
                if strs[t]["family"] == name:
                    newpos[t] = text_at + (newpos[t] - lo)  # 옛 영역 기준 → 꼬리 기준
            # ⚠ 표가 **다른 가족의 스트림**을 가리키기도 한다(공용 지우기 스트림 `<08><06>` — 문서 6절).
            # 옮긴 표에서 그 자리를 12비트로 못 짚으므로 **사본을 블롭에 같이 싣는다**(2B 짜리다).
            blob = bytearray(areas[name])
            for _pos, op, arg in ws:
                if op != 0:
                    continue
                t = base + arg
                if strs[t]["family"] == name:
                    continue
                if len(blob) & 1:
                    blob.append(0)
                # 🔴 **원본 newpos 를 덮지 않는다** — 제자리에 남는 다른 가족의 표가 그 값을 쓴다
                local.setdefault(name, {})[t] = text_at + len(blob)
                blob += d[t : strs[t]["stream"].end]
            areas[name] = bytes(blob)
            moved[name] = cur
            writes.append((f"captions-tail:{name}", text_at, areas[name]))
            writes.append((f"captions-ptr:{name}", ptr, struct.pack(">I", cur)))
            _lo, _hi = next((a, h) for n, _b, (a, h) in FAMILIES if n == name)
            writes.append((f"captions:{name}", _lo, b"\x00" * (_hi - _lo)))  # 옛 영역 지우기
            cur = text_at + len(areas[name])
            cur += cur & 1
    # 표 — 참조하는 문안이 하나라도 옮겨졌으면 표 전체를 다시 쓴다(오프코드 0 워드만 바뀐다)
    for _name, bases, _area in FAMILIES:
        for base in bases:
            ws = words(d, base)
            if not any(strs[base + a]["family"] in touched_fams for _, op, a in ws if op == 0):
                continue
            tbl = bytearray(d[base : base + len(ws) * 2 + 2])
            here = moved.get(_name, base)  # 옮겼으면 꼬리의 표 머리가 기준이다
            for pos, op, arg in ws:
                if op != 0:
                    continue
                tgt = local.get(_name, {}).get(base + arg, newpos[base + arg])
                off = tgt - here
                if not 0 <= off <= OFF_MAX:
                    raise SystemExit(f"captions 표 {base:#x}: 오프셋 {off:#x} 이 12비트를 넘는다")
                tbl[pos - base : pos - base + 2] = struct.pack(">H", off)
            writes.append((f"captions-table:{base:06x}", moved.get(_name, base), bytes(tbl)))
    return writes


def allowed_tail(at: int, size: int) -> dict[str, tuple[int, int]]:
    """꼬리로 옮길 때 여는 자리 — 블롭·옮긴 표·표 포인터 피연산자.

    ⚠ 옮긴 표는 `allowed()` 가 이미 **제자리** 범위로 연 라벨과 이름이 같다. 두 자리 중 어디에 써도
    되게 **합집합**으로 넓힌다(제자리 자리는 옛 영역 지우기에 쓴다)."""
    out = {f"captions-tail:{n}": (at, at + size) for n in RELOCATE}
    out.update({f"captions-ptr:{n}": (p, p + 4) for n, (_b, p) in RELOCATE.items()})
    return out


def widen_for_tail(base: dict, at: int, size: int) -> dict:
    """`allowed()` 의 표 라벨을 꼬리까지 넓힌다 — 옮긴 표는 꼬리에 쓰인다."""
    out = dict(base)
    for b, _p in RELOCATE.values():
        k = f"captions-table:{b:06x}"
        lo, hi = out.get(k, (at, at + size))
        out[k] = (min(lo, at), max(hi, at + size))
    return out


def allowed(d: bytes) -> dict[str, tuple[int, int]]:
    out = {}
    for name, bases, (lo, hi) in FAMILIES:
        out[f"captions:{name}"] = (lo, hi)
        for base in bases:
            out[f"captions-table:{base:06x}"] = (base, base + len(words(d, base)) * 2 + 2)
    return out


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
