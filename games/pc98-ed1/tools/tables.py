"""고정 stride 이름 표를 찾아 뜬다 — 가나 필터가 버린 **순수 한자 이름**의 회수 경로.

`dump_sys.py` 는 「가나가 있나」로 오탐을 걸러서 「薬草」 류를 놓친다. 이름은 대개
**고정 폭 레코드**에 우측정렬로 들어 있으므로, 표를 찾으면 필터 없이 통째로 회수된다.

실측 예 — 아이템 표: `program` 0x3f0f, **stride 0x14, 이름 14B**, 117 레코드.
꼬리 6B 는 값(가격·종별·수치)으로 보인다.

    0x003f0f '      何もない' + 00 00 00 00 ff 0f
    0x003f23 '        ナイフ' + 0a 01 10 03 ff 61

⚠ 이 스크립트는 **후보를 낸다**. 「진짜 표인가」는 사람이 본다 — stride 가 우연히 맞는
바이트 나열이 걸릴 수 있다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

MIN_RECORDS = 8
MIN_CHARS = 2
MAX_STRIDE = 64


def _lead(b: int) -> bool:
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def text_islands(flat: bytes) -> list[tuple[int, int]]:
    """전각 SJIS 가 이어지는 섬 — (시작, 끝). 표를 찾는 뼈대다."""
    out = []
    i = 0
    n = len(flat)
    while i < n - 1:
        if not _lead(flat[i]):
            i += 1
            continue
        j, chars = i, 0
        while j < n - 1 and _lead(flat[j]):
            try:
                flat[j : j + 2].decode("shift_jis")
            except UnicodeDecodeError:
                break
            j += 2
            chars += 1
        if chars >= MIN_CHARS:
            out.append((i, j))
        i = max(j, i + 1)
    return out


def _group(islands: list[tuple[int, int]], anchor: int) -> list[dict]:
    """`anchor`(0=섬 시작, 1=섬 끝)의 간격이 일정한 묶음을 표로 본다."""
    found: list[dict] = []
    k = 0
    while k < len(islands) - 1:
        stride = islands[k + 1][anchor] - islands[k][anchor]
        if not (4 <= stride <= MAX_STRIDE):
            k += 1
            continue
        m = k + 1
        while m < len(islands) - 1 and islands[m + 1][anchor] - islands[m][anchor] == stride:
            m += 1
        count = m - k + 1
        if count >= MIN_RECORDS:
            # 우측정렬이면 레코드 머리는 **섬 끝 - stride** 다(앞이 공백이라 섬 시작이 들쭉날쭉).
            head = islands[k][1] - stride if anchor == 1 else islands[k][0]
            name_len = (
                islands[k][1] - head if anchor == 1 else max(e - s for s, e in islands[k : m + 1])
            )
            found.append({"off": head, "stride": stride, "name_len": name_len, "n": count})
            k = m + 1
        else:
            k += 1
    return found


def scan(flat: bytes) -> list[dict]:
    """섬의 **시작 또는 끝** 간격이 일정하면 표로 본다.

    🔴 시작만 보면 **우측정렬 표를 통째로 놓친다** — 아이템 표가 그렇다(이름이 14B 칸의
    오른쪽에 붙어 있어 섬 시작이 레코드마다 다르다). 실측: 시작만 보면 후보 1건뿐이었다.
    """
    islands = text_islands(flat)
    found = _group(islands, 0) + _group(islands, 1)
    seen: set[int] = set()
    out: list[dict] = []
    for f in sorted(found, key=lambda f: -f["n"] * f["stride"]):
        span = set(range(f["off"], f["off"] + f["stride"] * f["n"]))
        if span & seen:
            continue
        seen |= span
        out.append(f)
    return out


def read_table(flat: bytes, off: int, stride: int, name_len: int, n: int) -> list[str]:
    """레코드 창 안에서 **이름 섬을 다시 뽑는다**.

    칸 안 어디에 붙어 있는지(좌/우 정렬)를 미리 안 정한다 — 표마다 다르고, 틀리면
    이름이 값 바이트를 먹거나 잘린다.
    """
    out = []
    for k in range(n):
        window = flat[off + k * stride : off + (k + 1) * stride]
        best = ""
        for s, e in text_islands(window):
            if e - s > len(best.encode("shift_jis", "replace")):
                best = window[s:e].decode("shift_jis", "replace")
        out.append(best)
    return out


def main() -> int:
    common.check_originals()
    out_dir = common.REVIEW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for key in ("program", "event"):
        flat = common.read_flat(common.disk_path(key))
        cands = scan(flat)
        print(f"=== {key}: 표 후보 {len(cands)}건 (레코드 {MIN_RECORDS} 이상)")
        rows = []
        for c in cands[:12]:
            names = read_table(flat, c["off"], c["stride"], c["name_len"], c["n"])
            rows.append({**c, "names": names})
            head = " · ".join(n for n in names[:5] if n)
            print(
                f"  {c['off']:#08x} stride {c['stride']:#04x} 이름 {c['name_len']:2d}B "
                f"× {c['n']:3d}  {head[:52]}"
            )
        report[key] = rows
    (out_dir / "tables.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n→ {out_dir / 'tables.json'}  ⚠ 원문이다, 커밋 금지")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
