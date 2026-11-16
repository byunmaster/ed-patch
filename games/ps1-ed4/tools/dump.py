"""덤프 — 원본에서 **빌드가 읽는 파생물**을 `work/derived/` 로 뽑는다(원문 포함 — 커밋 금지).

    python3 tools/dump.py [script] [strings] [maps]      (인자 없으면 셋 다)

- `script`  — 대본 멤버 481(표 규격 356 + 풀 규격 125)의 조각 코드열 → `derived/script/<아카이브>_<멤버>.json`
              ⚠ 파서 규격 판정은 `scriptmap.layout` — 추측이 아니라 구조(표가 단조·범위 안)로 가른다.
- `strings` — 실행파일 낱말 표(구역 라벨은 사람이 붙인 판단 → 아래 `REGIONS`) → `derived/names.json`
- `maps`    — 실행파일 맵 이름 표 372항목(8B = 이름 7자 + 영역·플래그 1B) → `derived/maps.json`

🔴 이 모듈은 **읽기 전용**이다 — 원본 이미지는 열기만 한다.
"""

import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

from shared.ps1 import gmf_arc
from shared.ps1 import gmf_script as scriptmap

# 대본 멤버 = 아카이브 안 `..\BIN\*.BIN`
SCRIPT_MEMBER = "\\BIN\\"

# ── 실행파일 낱말 표 구역 ───────────────────────────────────────────────────
# 구역 라벨 — **사람이 눈으로 붙인 판단**(ps1-ed3 `dump_names.REGIONS` 의 ED4 몫을 옮겼다). 시작 오프셋이 키다 —
# 원본이 바뀌면 못 찾고, 그때 조용히 넘어가지 않게 `survey` 가 운다.
#   `text` 는 문장급이라 저작권 규율이 다르다 · `noise` 는 낱말처럼 걸리지만 뜻 없는 자리(글꼴 표·조판 자료).
# 🔴 ★ 여섯은 ED3 쪽 `dump_names --disc ed4` 에서 라벨이 없던 구역이다(그 도구는 ED4 에서 늘 빨간불) — 문장급이라 `text` 로 붙인 **제안**이다.
REGIONS = {
    0x000A28: "menu",
    0x06D3DE: "monster",
    0x06D7CC: "menu",
    0x06DFE4: "spell",
    0x06E2A2: "text",
    0x06E63E: "menu",
    0x06E860: "noise",
    0x06F208: "noise",
    0x06F49C: "noise",
    0x06FA02: "item",
    0x071B12: "text",  # ★ 의뢰문(아이템 설명·배달)
    0x072070: "text",  # ★ 이벤트 아이템 설명·안내문
    0x072A70: "text",  # ★ 일자리 대사 토막
    0x073058: "text",  # ★ 의뢰문 토막
    0x075A8C: "text",  # ★ 길드 의뢰문
    0x076FDA: "text",  # ★ 시험관 대사 토막
    0x07002A: "item",
    0x07054E: "text",
    0x070592: "menu",
    0x070806: "text",
    0x0709A6: "text",
    0x072774: "noise",
    0x072798: "person",
    0x0730A8: "text",
    0x073362: "text",
    0x07363A: "text",
    0x07391A: "text",
    0x073CCA: "text",
    0x074062: "text",
    0x07432E: "text",
    0x0749D0: "text",
    0x074E98: "text",
    0x0753CA: "text",
    0x075E5E: "text",
    0x07602A: "text",
    0x0763A0: "text",
    0x076678: "text",
    0x076C26: "text",
    0x076D48: "menu",
    0x076EA2: "text",
    0x077046: "text",
    0x07727A: "rank",
    0x077500: "menu",
    0x077816: "place",
    0x077A5C: "place",
    0x079722: "noise",
}
MAX_LEN = 24  # 이보다 길면 낱말 표가 아니다
GAP = 64  # 이만큼 안에서 이어지면 한 구역

MAP_TABLE = 0x80087808  # 맵 이름 표(RAM) — 8B 항목, 끝은 `Z`(0x5A)


def is_term(w):
    """종결인가 — `0x0000` · `0xFFFF` · **최상위 비트가 선 코드**(마법·몬스터·지명 표는 `0x8002` 로 끝난다)."""
    return w == 0xFFFF or w == 0 or w & 0x8000


def strings(data, cm, max_len=MAX_LEN):
    """[(바이트오프셋, 글자수, 문자열)] — 종결로 갈린 조각 중 **전부 아는 코드**인 것."""
    n = len(data) // 2
    w = struct.unpack(f"<{n}H", data[: n * 2])
    out, cur, start = [], [], 0
    for i, x in enumerate(w):
        if is_term(x):
            if cur and len(cur) <= max_len and all(c in cm for c in cur):
                out.append((start * 2, len(cur), "".join(cm[c] for c in cur)))
            cur, start = [], i + 1
        else:
            if not cur:
                start = i
            cur.append(x)
    return out


def regions(strs, min_count=8, min_avg=2.0, min_long=0.4):
    """이웃한 문자열을 구역으로 묶는다 — **낱말답지 않은 구역은 버린다**(밀도는 후보 좁히기지 판정이 아니다)."""
    regs = []
    for off, ln, s in strs:
        if regs and off - regs[-1]["end"] < GAP:
            regs[-1]["end"] = off + ln * 2 + 2
            regs[-1]["items"].append(s)
            regs[-1]["offs"].append(off)
        else:
            regs.append({"start": off, "end": off + ln * 2 + 2, "items": [s], "offs": [off]})
    ok = []
    for r in regs:
        it = r["items"]
        if len(it) < min_count:
            continue
        avg = sum(len(s) for s in it) / len(it)
        long = sum(1 for s in it if len(s) >= 3) / len(it)
        if avg < min_avg or long < min_long:
            continue
        ok.append(r)
    return ok


def split(regs, labels):
    """라벨이 붙은 오프셋에서 구역을 **자른다**(표끼리 딱 붙어 `GAP` 으로 안 갈리는 자리 — `REGIONS` 키가 곧 칼자국)."""
    out = []
    for r in regs:
        cuts = sorted(o for o in labels if r["start"] < o < r["end"])
        if not cuts:
            out.append(r)
            continue
        cur = {"start": r["start"], "end": r["start"], "items": [], "offs": []}
        for off, s in zip(r["offs"], r["items"], strict=True):
            if cuts and off >= cuts[0]:
                out.append(cur)
                cur = {"start": cuts.pop(0), "end": off, "items": [], "offs": []}
            cur["items"].append(s)
            cur["offs"].append(off)
            cur["end"] = off + len(s) * 2 + 2
        out.append(cur)
    return [r for r in out if r["items"]]


def survey(exe):
    """[구역] — 라벨 붙인 낱말 표 구역. 라벨 없는 구역이 나오면 `ValueError`(조용히 넘어가지 않는다)."""
    cm = textenc.charmap()
    regs = split(regions(strings(exe, cm)), REGIONS)
    for r in regs:
        r["kind"] = REGIONS.get(r["start"], "?")
    bad = [r for r in regs if r["kind"] == "?"]
    if bad:
        raise ValueError("라벨 없는 구역: " + ", ".join(f"0x{r['start']:06X}" for r in bad))
    return regs


def map_table(exe):
    """[(이름, 영역 번호 0~127, 플래그 0|1)] — 맵 이름 표. 끝 `Z` 를 못 찾으면 `ValueError`."""
    o = map_table_off()
    rows = []
    while exe[o] != 0x5A:
        name = exe[o : o + 7]
        if not name.isalnum():
            raise ValueError(f"맵 표 항목이 이름이 아니다 @0x{o:X}: {bytes(name)!r}")
        rows.append((name.decode("ascii"), exe[o + 7] & 0x7F, exe[o + 7] >> 7))
        o += 8
        if len(rows) > 4096:
            raise ValueError("맵 표 끝(`Z`)을 못 찾았다")
    return rows


def map_table_off():
    return MAP_TABLE - common.EXE_TADDR + common.EXE_HDR


def script_members(disc=None):
    """[(아카이브, 멤버 이름, 아카이브 바이트, 멤버 오프셋, 멤버 크기)] — 대본 후보(`..\\BIN\\*.BIN`) 전부."""
    out = []
    with common.open_disc() as d:
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if SCRIPT_MEMBER in nm and nm.endswith(".BIN") and sz >= 8:
                    out.append((path, nm, data, off, sz))
    return out


def dump_script(outdir):
    os.makedirs(outdir, exist_ok=True)
    n = {"table": 0, "pool": 0, "err": 0}
    segs_total = 0
    for path, nm, data, off, sz in script_members():
        mem = data[off : off + sz]
        try:
            info = scriptmap.parse(mem)
        except Exception as e:  # noqa: BLE001 — 규격 밖 멤버는 세고 알린다(조용히 안 뺀다)
            n["err"] += 1
            print(f"  ⚠ {path}!{nm}: 파싱 실패 {e}")
            continue
        n[info["layout"]] += 1
        segs_total += len(info["segments"])
        fn = f"{path.strip('/').replace('/', '_')}__{os.path.basename(nm.replace(chr(92), '/'))}.json"
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "archive": path,
                    "member": nm,
                    "layout": info["layout"],
                    "base": info["base"],
                    "size": sz,
                    "segments": [{"off": o, "codes": c} for o, c in info["segments"]],
                },
                f,
                separators=(",", ":"),
            )
    return n, segs_total


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv) or ["script", "strings", "maps"]
    common.verify_source()
    os.makedirs(common.OUT_DIR, exist_ok=True)
    exe = common.read_file(common.EXE_PATH)
    if "script" in argv:
        n, segs = dump_script(os.path.join(common.OUT_DIR, "script"))
        print(
            f"대본: 멤버 {n['table'] + n['pool'] + n['err']} (표 {n['table']} · 풀 {n['pool']} · 실패 {n['err']}) · 조각 {segs:,}"
        )
        if n["err"]:
            return 1
    if "strings" in argv:
        try:
            regs = survey(exe)
        except ValueError as e:
            print(f"🔴 {e} — `REGIONS` 에 손으로 붙인다")
            return 1
        words = sum(len(r["items"]) for r in regs if r["kind"] not in ("text", "noise"))
        with open(os.path.join(common.OUT_DIR, "names.json"), "w", encoding="utf-8") as f:
            json.dump({"exe": common.EXE_PATH, "regions": regs}, f, ensure_ascii=False, indent=1)
        print(
            f"실행파일 문자열: 구역 {len(regs)} · 문자열 {sum(len(r['items']) for r in regs):,} (낱말 {words:,})"
        )
    if "maps" in argv:
        rows = map_table(exe)
        with open(os.path.join(common.OUT_DIR, "maps.json"), "w", encoding="utf-8") as f:
            json.dump(
                [{"name": a, "area": b, "flag": c} for a, b, c in rows],
                f,
                ensure_ascii=False,
                indent=0,
            )
        print(f"맵 이름 표: {len(rows)}항목")
    return 0


if __name__ == "__main__":
    sys.exit(main())
