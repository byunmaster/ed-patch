"""오프닝 자막 · 엔딩 자막 — 워드 스크립트 드라이버($176F0)의 표와 문안 영역. md-ed1 `captions.py` 의 ED2 판.

표는 워드 열이다: 상위 니블 = 오프코드(0 문안 · 2 대기 · 4 페이드 · 6 팔레트 · 8 그림 · C 선택), 하위
12비트 = 인자, `FFFF` 로 끝난다. 오프코드 0 의 인자는 **표 머리(a3) 기준 전방 12비트 오프셋**이라 문안은
표 뒤 4,095B 안에 있어야 한다. 스트림은 대사와 같은 제어코드(`fe 0e` 피치 14 · `01` 줄바꿈 · `fc 1e` 줄 사이
대기 · `06` 끝)라 `scene.parse_stream` 으로 읽는다.

ED1 과 다른 점(2026-10-12 조사):
- 표가 **넷**뿐이다 — 오프닝 하나(`bsr` 로 부른다) · 엔딩 셋(나레이션 6화면 · 프레이아 8화면 · 마지막 한 화면).
  엔딩 대사(초상화)·나레이션 창 넓히기 같은 ED1 의 가공이 없다.
- 오프닝은 줄마다 `<fc1e>` 가 붙어 한 줄씩 나타난다(원문 구조 그대로 둔다).
- 지우기 스트림 `<08><06>`(0x3516A)을 엔딩 표 셋이 같이 쓴다 — 꼬리로 옮길 땐 가족마다 사본을 싣는다.

재삽입: 표 묶음과 문안을 **꼬리 예약 칸**으로 옮기고(제자리 칸은 가족마다 빠듯하다) 표 포인터(`lea a3`)를 고친다.
옛 영역은 **0 으로 지운다** — 원문 바이트를 남기면 「남은 일본어」 검사가 그만큼 눈이 먼다.
"""

import json
import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import scene
import sysmsg

# (이름, 표 머리들, 문안 영역) — 영역 끝은 다음 코드·자료의 머리
FAMILIES = [
    (
        "opening",
        (0x178C2,),
        (0x1790E, 0x17D7A),
    ),  # 오프닝 7화면 + 지우기 — 뒤는 자료 표(0x17D7A, lea 로 참조)
    ("ending-a", (0x34E46,), (0x34E86, 0x34F8C)),  # 엔딩 나레이션 6 — 뒤는 코드
    ("ending-b", (0x34FA4,), (0x34FF8, 0x35116)),  # 엔딩 프레이아 8 — 뒤는 코드
    ("ending-c", (0x3512E,), (0x35136, 0x3516C)),  # 엔딩 마지막 한 화면 + 공용 지우기(0x3516A)
]
# 표 머리 → 그 표를 부르는 `lea $표,a3` 의 32비트 피연산자 자리
RELOCATE = {
    "opening": [(0x178C2, 0x16770)],
    "ending-a": [(0x34E46, 0x34E3A)],
    "ending-b": [(0x34FA4, 0x34F98)],
    "ending-c": [(0x3512E, 0x35122)],
}
# 글꼴은 **스트림마다** 고른다 — 정본이 머리에 `<fd85>`(와이드 글꼴 5)를 달면 그 자막만 리소스 5(네오둥근모 16px)로
# 그리고 끝에 `<fd80>` 으로 대사 글꼴(리소스 0)로 되돌린다. md-ed1 과 같은 글꼴·같은 이유(마스터 확정 10-08).
FONT_ID = 5
FONT_TAG = "<fd85>"
FONT_SRC = os.environ.get("MD_CAPTION_FONT", "neodgm")
FONT_CELL = int(os.environ.get("MD_CAPTION_CELL", "16"))
NARROW_ON, NARROW_OFF = "<fd05>", "<fd00>"
WIDTH_P16 = 14  # 피치 16 × 14 = 224px (오프닝)
WIDTH_P14 = 15  # 피치 14 — 원문 최장 줄이 16칸(224px)이라 창은 그 이상이다. 보수적으로 15칸
OFF_MAX = 0xFFF
# 화면 줄 수 상한 — 오프닝 원문은 7줄, 엔딩 원문은 전 화면 2줄 이하(ED1 실측: 3줄이면 첫 줄이 밀려 사라진다)
MAX_LINES = {"opening": 7, "ending-a": 2, "ending-b": 2, "ending-c": 2}
EXPECT = (4, 25)  # 표 · 고유 스트림(지우기 스트림 포함, 2026-10-12 실측)
MAP_JSON = common.GAME_DIR / "textmap" / "captions.json"


def font_tags(ours: str) -> str:
    """정본 문안의 글꼴 머리·꼬리에 반각 글꼴 선택을 덧붙인다(빌드 시점 — 정본은 `<fd85>`…`<fd80>` 그대로)."""
    if FONT_SRC != "neodgm" or FONT_TAG not in ours or NARROW_ON in ours:
        return ours
    return ours.replace(FONT_TAG, FONT_TAG + NARROW_ON, 1).replace(
        "<fd80>", "<fd80>" + NARROW_OFF, 1
    )


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


def family_of(t: int) -> str:
    return next(n for n, _, (a, b) in FAMILIES if a <= t < b)


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
                    out[t] = {
                        "stream": scene.parse_stream(d, t),
                        "family": family_of(t),
                        "refs": [],
                    }
                out[t]["refs"].append((base, pos))
    return dict(sorted(out.items()))


def targets(ws: list, base: int) -> list[tuple[int, int]]:
    """표 워드 → [(오프코드, 인자)] — 오프코드 0 의 인자는 **원본 대상 자리**로 푼다(옮겨도 다시 잴 수 있게)."""
    return [(op, base + arg if op == 0 else arg) for _pos, op, arg in ws]


def cells(s: str) -> float:
    """화면 칸 — 이 렌더러는 **1바이트로 싣는 글자(ASCII)가 반각**이다(ED1 실측)."""
    return sum(0.5 if ord(c) < 0x80 else 1 for c in s)


def _width_errors(k: str, ours: str) -> list[str]:
    # 피치가 폭을 정한다 — **마지막** 피치 태그가 이긴다
    pitches = re.findall(r"<fe(0e|10)>", ours)
    limit = WIDTH_P16 if pitches and pitches[-1] == "10" else WIDTH_P14
    errs = []
    for ln in re.sub(r"<[^>]*>", "", ours).split("\n"):
        w = cells(ln.rstrip())
        if w > limit:
            errs.append(f"captions {k}: 줄 {w}칸 > {limit}: {ln!r}")
    return errs


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
    if MAP_JSON.exists():
        tm = json.loads(MAP_JSON.read_text(encoding="utf-8"))
        errs = []
        for t, e in strs.items():
            ours = tm.get(f"{t:06x}", {}).get("ours", "")
            if not ours:
                continue
            errs += _width_errors(f"{t:06x}", ours)
            n = len(ours.split("\n"))
            if n > MAX_LINES[e["family"]]:
                errs.append(f"captions {t:06x}: {n}줄 > {MAX_LINES[e['family']]}줄")
        if errs:
            raise SystemExit("\n".join(errs))
        done = sum(1 for t in strs if tm.get(f"{t:06x}", {}).get("ours"))
        print(f"  번역 {done}/{len(strs)}")


def seed(d: bytes) -> None:
    """정본 초안(해시만) — 원문 골격은 work/derived 에(커밋하지 않는다: 원문이다)."""
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


def font5_chars(textmap: dict) -> set[str]:
    """리소스 5 로 그리는 자막이 쓰는 글자 — 그만큼만 글리프를 만든다."""
    out: set[str] = set()
    for e in textmap.values():
        if FONT_TAG in e.get("ours", ""):
            out.update(re.sub(r"<[^>]*>", "", e["ours"]))
    return out


def plan(
    d: bytes, textmap: dict, encode, tail_at: int, tail_size: int
) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 목록. 번역이 하나라도 있는 가족만 꼬리로 옮기고 표 포인터를 고친다."""
    strs = streams(d)
    writes: list[tuple[str, int, bytes]] = []
    errs: list[str] = []
    newpos: dict[int, int] = {}
    areas: dict[str, bytes] = {}
    touched: set[str] = set()
    for name, _bases, (lo, _hi) in FAMILIES:
        area = bytearray()
        for t, e in ((t, e) for t, e in strs.items() if e["family"] == name):
            st = e["stream"]
            k = f"{t:06x}"
            ent = textmap.get(k)
            if ent and ent.get("ours"):
                if ent["jp"] != sysmsg.jp_key(st):
                    raise SystemExit(f"captions {k}: 원문 해시가 갈렸다")
                ours = ent["ours"]
                errs += _width_errors(k, ours)
                n = len(ours.split("\n"))
                if n > MAX_LINES[name]:
                    errs.append(f"captions {k}: {n}줄 > {MAX_LINES[name]}줄 ({name})")
                body = b"".join(
                    tk.raw for tk in sysmsg._tokens_from_ours(st, font_tags(ours), encode)
                )
                touched.add(name)
            else:
                body = d[t : st.end]
            if len(area) & 1:
                area.append(0)
            newpos[t] = lo + len(area)
            area += body
        areas[name] = bytes(area)
    if errs:
        raise SystemExit("\n".join(errs))
    moved: dict[int, int] = {}  # 원래 표 머리 → 꼬리의 표 머리
    local: dict[str, dict[int, int]] = {}  # 가족 → {다른 가족 스트림: 이 가족 블롭 안의 자리}(사본)
    cur = tail_at
    for name, tables in RELOCATE.items():
        if name not in touched:
            continue
        # 표를 먼저 줄지어 놓고 그 뒤에 문안 — 오프셋이 표 머리 기준 **전방** 12비트라서다
        for base, _ptr in tables:
            moved[base] = cur
            cur += len(words(d, base)) * 2 + 2
        text_at = cur
        lo = next(a for n, _b, (a, _h) in FAMILIES if n == name)
        for t in list(newpos):
            if strs[t]["family"] == name:
                newpos[t] = text_at + (newpos[t] - lo)  # 옛 영역 기준 → 꼬리 기준
        # ⚠ 표가 **다른 가족의 스트림**(공용 지우기 `<08><06>`)을 가리키면 12비트로 못 짚으니 사본을 블롭에 싣는다
        blob = bytearray(areas[name])
        for base, _ptr in tables:
            for op, t in targets(words(d, base), base):
                if op != 0 or t in local.get(name, {}) or strs[t]["family"] == name:
                    continue
                if len(blob) & 1:
                    blob.append(0)
                local.setdefault(name, {})[t] = text_at + len(blob)
                blob += d[t : strs[t]["stream"].end]
        areas[name] = bytes(blob)
        writes.append((f"captions-tail:{name}", text_at, areas[name]))
        for base, ptr in tables:
            writes.append((f"captions-ptr:{base:06x}", ptr, struct.pack(">I", moved[base])))
        _lo, _hi = next((a, h) for n, _b, (a, h) in FAMILIES if n == name)
        writes.append((f"captions:{name}", _lo, b"\x00" * (_hi - _lo)))  # 옛 영역 지우기
        cur = text_at + len(areas[name])
        cur += cur & 1
    if cur - tail_at > tail_size:
        raise SystemExit(f"captions: 꼬리 {cur - tail_at}B 가 예약 {tail_size}B 를 넘는다")
    # 표 — 옮긴 가족의 표는 오프코드 0 워드를 새 오프셋으로 다시 쓴다
    for name, bases, _area in FAMILIES:
        if name not in touched:
            continue
        for base in bases:
            seq = targets(words(d, base), base)
            here = moved[base]
            tbl = bytearray()
            for op, arg in seq:
                if op == 0:
                    arg = local.get(name, {}).get(arg, newpos.get(arg)) - here
                    if not 0 <= arg <= OFF_MAX:
                        raise SystemExit(
                            f"captions 표 {base:#x}: 오프셋 {arg:#x} 이 12비트를 넘는다"
                        )
                tbl += struct.pack(">H", op << 12 | arg)
            tbl += b"\xff\xff"
            writes.append((f"captions-table:{base:06x}", here, bytes(tbl)))
    return writes


def verify_readback(buf: bytes, d: bytes, textmap: dict, encode) -> int:
    """🔴 되읽기 게이트 — 구운 이미지에서 `lea a3` 포인터 → 표 → 워드를 **따라가** 읽은 스트림이 의도한 바이트와 같은지.
    표 포인터·12비트 오프셋·사본·옛 영역 지우기가 조용히 어긋나도 여기서 걸린다. 확인한 스트림 수를 돌려준다."""
    strs = streams(d)
    n = 0
    for name, tables in RELOCATE.items():
        for base, ptr in tables:
            nbase = struct.unpack(">I", buf[ptr : ptr + 4])[0]
            old, new = words(d, base), words(buf, nbase)
            if len(old) != len(new):
                raise SystemExit(f"captions 되읽기 {base:#x}: 표 길이가 다르다")
            for (_p, op, arg), (_q, nop, narg) in zip(old, new, strict=True):
                if op != nop:
                    raise SystemExit(f"captions 되읽기 {base:#x}: 오프코드가 다르다")
                if op != 0:
                    if arg != narg:
                        raise SystemExit(f"captions 되읽기 {base:#x}: 인자가 다르다")
                    continue
                t = base + arg
                ent = textmap.get(f"{t:06x}")
                if ent and ent.get("ours"):
                    ours = font_tags(ent["ours"])
                    toks = sysmsg._tokens_from_ours(strs[t]["stream"], ours, encode)
                    want = b"".join(tk.raw for tk in toks)
                else:
                    want = d[t : strs[t]["stream"].end]
                got = buf[nbase + narg : nbase + narg + len(want)]
                if got != want:
                    raise SystemExit(f"captions 되읽기 {t:06x}: 구운 스트림이 의도와 다르다")
                n += 1
    return n


def allowed(d: bytes, at: int, size: int) -> dict[str, tuple[int, int]]:
    """쓰기 라벨 — 옛 영역(0 지우기) · 꼬리 칸(블롭·옮긴 표) · 표 포인터 피연산자."""
    out: dict[str, tuple[int, int]] = {}
    for name, bases, (lo, hi) in FAMILIES:
        out[f"captions:{name}"] = (lo, hi)
        out[f"captions-tail:{name}"] = (at, at + size)
        for base in bases:
            out[f"captions-table:{base:06x}"] = (at, at + size)
    for tables in RELOCATE.values():
        for base, ptr in tables:
            out[f"captions-ptr:{base:06x}"] = (ptr, ptr + 4)
    return out


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
