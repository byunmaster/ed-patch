#!/usr/bin/env python3
"""시스템 문안 재삽입 — 메뉴 · HUD · 표(아이템/주문) · 전투·주문 메시지 · 챕터 제목.

🔴 **시나리오와 규칙이 다르다.** 저기는 이벤트 스크립트라 `0F` 무조건 점프로 런을 밖으로
   뺄 수 있었다(`patch_scn.py`). 여기는 **실행 파일의 데이터 영역**이라 그런 통로가 없다 —
   **제자리에, 원본 길이 안에서만** 쓴다. 넘치면 넣지 않고 센다.

## 자리의 성질

- **고정 칸 표** — 아이템은 stride 0x14 안에 14B 이름을 **우측정렬**로, 주문은 8B 칸.
  칸을 넘으면 옆 레코드를 먹는다.
- **메뉴** — 한 문자열 안에서 전각 공백으로 열을 맞춘다(「 戦う　　呪文　　守る」).
- **메시지 조각** — 런타임에 이름과 이어 붙는다(「〜の攻撃」·「〜を倒した。」).
  🔴 그래서 **조사를 확정할 수 없다** — 앞말이 주입이므로 병기(`을(를)`)가 옳다
  (`rpg-translate` §⑥ · 그 판정은 `docs/policy.md` 에 적는다).

## 여백은 원본의 꼴을 따른다

원본이 앞을 비웠으면(우측정렬) 우리도 앞을 채운다. 그래야 표가 안 흐트러진다.
채움은 **반각 공백**(1바이트)이라 칸을 정확히 맞출 수 있다.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import patch_scn

SCRIPT = common.ROOT / "games" / "pc98-ed1" / "script" / "sys.json"
DUMP = common.OUT_DIR / "sys_jp"
DISKS = ("event", "program")


def load() -> dict:
    return json.loads(SCRIPT.read_text(encoding="utf-8")) if SCRIPT.exists() else {}


def sites(disk: str) -> dict[int, dict]:
    p = DUMP / f"{disk}.json"
    if not p.exists():
        raise SystemExit(f"덤프가 없다: {p} — tools/dump_sys.py 를 먼저")
    return {b["o"]: b for b in json.loads(p.read_text(encoding="utf-8"))}


def pad_shape(t: str) -> str:
    """원본 문자열이 어느 쪽을 비웠나 — 'left'(우측정렬) · 'right' · 'none'."""
    lead = len(t) - len(t.lstrip(" 　"))
    trail = len(t) - len(t.rstrip(" \u3000"))
    if lead > trail:
        return "left"
    return "right" if trail else "none"


def plan() -> tuple[dict[str, list], dict]:
    """{디스크: [(플랫 오프셋, 원본 바이트, 새 바이트)]} + 통계."""
    script = load()
    out: dict[str, list] = {d: [] for d in DISKS}
    st = {"넣음": 0, "건너뜀:넘침": 0, "건너뜀:자리 없음": 0, "쓴 바이트": 0}
    for disk in DISKS:
        flat = b"".join(x["data"] for x in common.read_sectors(common.disk_path(disk)))
        site = sites(disk)
        for key, v in script.items():
            d, _, off = key.partition(":")
            if d != disk:
                continue
            o = int(off, 16)
            # 「원문으로 둔다」고 적어 둔 자리 — 문안이 없다(`check_neighbors.py` 가 읽는다)
            if v.get("keep_jp") or "t" not in v:
                continue
            if o not in site:
                st["건너뜀:자리 없음"] += 1
                continue
            n = site[o]["n"]

            # ── 칸 표(지명 목록 등) — 한 문자열 안에 **고정 폭 칸이 여럿** 들어 있다.
            #    🔴 통째로 채우면 정렬이 통째로 깨진다. 칸마다 따로 넣고 **가운데 정렬**한다.
            #    ⚠ 구조를 **사전조건으로 검사한다** — 머리 + 칸수×폭 이 원본 길이와 안 맞으면
            #      우리가 표를 잘못 읽은 것이므로 그 자리에서 죽는다(patcher-checklist 2).
            if "table" in v:
                t = v["table"]
                head, stride = t["head"], t["stride"]
                items = v["items"]
                if head + stride * len(items) != n:
                    raise SystemExit(
                        f"🔴 {key}: 표 구조가 안 맞는다 — 머리 {head} + {stride}×{len(items)} ≠ {n}"
                    )
                blob = bytearray(flat[o : o + head])
                for name in items:
                    cell = patch_scn.encode(name)
                    if len(cell) > stride:
                        st["건너뜀:넘침"] += 1
                        cell = cell[:stride]
                    left = (stride - len(cell)) // 2  # 가운데 정렬
                    blob += b" " * left + cell + b" " * (stride - len(cell) - left)
                out[disk].append((o, flat[o : o + n], bytes(blob)))
                st["넣음"] += 1
                st["쓴 바이트"] += n
                continue

            core = patch_scn.encode(v["t"])
            if len(core) > n:
                st["건너뜀:넘침"] += 1
                continue
            pad = b" " * (n - len(core))
            # ⚠ 채움을 **어느 쪽에** 두느냐가 화면을 가른다.
            #   표(아이템)는 우측정렬이라 앞을 채워야 칸이 안 흐트러지고,
            #   **메뉴는 왼쪽 정렬**이라 뒤를 채워야 시작 자리가 안 밀린다.
            #   기본은 원본의 여백 꼴을 따르고, 정본이 `pad` 로 덮어쓴다.
            side = v.get("pad") or pad_shape(site[o]["t"])
            # ⚠ `center` 는 **정본이 명시할 때만** 쓴다 — 원본이 앞뒤를 다 비웠어도
            #   가운데 정렬이 아니라 **커서 자리**인 경우가 있다(메뉴의 앞 한 칸).
            if side == "center":
                left = len(pad) // 2
                blob = b" " * left + core + b" " * (len(pad) - left)
            else:
                blob = pad + core if side == "left" else core + pad
            out[disk].append((o, flat[o : o + n], blob))
            st["넣음"] += 1
            st["쓴 바이트"] += n
    return out, st


GLOSSARY = common.ROOT / "shared" / "glossary" / "eiyuu.json"


def canon() -> dict[str, str]:
    """공용 정본을 평평하게 편다 — {원문 낱말: 우리 표기}."""
    out: dict[str, str] = {}

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, str) and key and not key.startswith("_"):
            out[key] = o

    walk(json.loads(GLOSSARY.read_text(encoding="utf-8")))
    return out


def cmd_seed(dry: bool) -> int:
    """이름 표를 **공용 정본에서** 채운다.

    🔴 PS1 은 도구 표에 정본을 **하드코딩**하고 테스트로 묶는다(`docs/naming.md`). 우리는
       자리가 오프셋이라 사본을 둘 이유가 없다 — **런타임에 정본을 읽는다.** 정본이 바뀌면
       다음 빌드가 그대로 따라간다(사본이 없으니 갈릴 일도 없다).
    ⚠ 여백을 뗀 낱말이 정본에 **정확히** 있을 때만 넣는다. 부분일치는 안 본다.
    """
    tbl = canon()
    script = load()
    added = miss = 0
    misses: list[str] = []
    for disk in DISKS:
        for o, b in sites(disk).items():
            core = b["t"].strip(" \u3000")
            key = f"{disk}:{o:#x}"
            if key in script:
                continue
            if core in tbl:
                script[key] = {"t": tbl[core], "by": "glossary"}
                added += 1
            elif len(core) >= 2:
                miss += 1
                if len(misses) < 12:
                    misses.append(f"{key} {core[:14]}")
    print(f"정본에서 채운 자리 {added:,} · 정본에 없는 자리 {miss:,}")
    for m in misses:
        print(f"    {m}")
    if not dry:
        SCRIPT.write_text(json.dumps(script, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ {SCRIPT} (총 {len(script):,})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify", metavar="TAG", nargs="?", const=common.BUILD_TAG)
    ap.add_argument("--seed", action="store_true", help="이름 표를 공용 정본에서 채운다")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    common.check_originals()
    if a.seed:
        return cmd_seed(a.dry)
    marks, st = plan()
    if a.verify:
        bad = 0
        for disk, ms in marks.items():
            built = common.BUILD_DIR / a.verify / f"{disk}.d88"
            if not built.exists():
                raise SystemExit(f"🔴 빌드가 없다: {built}")
            flat = b"".join(x["data"] for x in common.read_sectors(built))
            bad += sum(1 for o, _e, new in ms if flat[o : o + len(new)] != new)
        n = sum(len(m) for m in marks.values())
        print(f"시스템 되읽기 {n:,}자리 · 바이트 불일치 {bad}")
        return 1 if bad else 0
    print(f"시스템 문안 {sum(len(m) for m in marks.values()):,}자리")
    for k, v in st.items():
        print(f"  {k:18s} {v:6,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
