"""코드 영역에 남은 일본어 — **정본이 안 덮은 자리**를 찾는다.

    python3 tools/jp_left.py            # 남은 자리 목록
    python3 tools/jp_left.py --check    # 알려진 목록과 다르면 실패(게이트)
    python3 tools/jp_left.py --freeze   # 지금 남은 자리를 알려진 목록으로 굳힌다

왜 필요한가 — 시스템 문안은 `lea/pea` 참조로 찾는데, **참조가 없는 자리가 많다**(워드 오프셋 표 ·
`06` 뒤로 물리적으로 이어지는 꼬리말 · 다른 스트림의 goto 대상). 2026-09-06 에 이 스캔으로
주문/아이템 효과 메시지 30여 개 · 패배 메뉴 · 상점 · 미니게임 문안이 통째로 빠져 있는 걸 찾았다.
「참조로 찾는다」는 방식은 조용히 새므로, **화면에 나갈 수 있는 바이트**를 직접 센다.

원본을 훑고, 정본이 덮는 구간(시스템 메시지 묶음 · 표 레코드 · 자막 영역)을 뺀다. 빌드 산출물이
아니라 **원본 + 정본**만 보므로 게이트에서 빌드 없이 돈다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import captions
import common
import sysmsg
import tables

CODE_END = 0x40000
KNOWN_JSON = common.GAME_DIR / "textmap" / "jp_left.json"


def _is_jp(w: int) -> str | None:
    b1, b2 = w >> 8, w & 0xFF
    if not (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xEF):
        return None
    if not (0x40 <= b2 <= 0xFC and b2 != 0x7F):
        return None
    try:
        ch = bytes([b1, b2]).decode("cp932")
    except UnicodeDecodeError:
        return None
    return ch if ("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿") else None


def covered(d: bytes) -> list[tuple[int, int]]:
    """정본이 다시 쓰는 구간 — 시스템 메시지 묶음(번역이 하나라도 있는) · 표 레코드 · 자막 영역."""
    out: list[tuple[int, int]] = []
    smap = json.loads((common.GAME_DIR / "textmap" / "sysmsg.json").read_text(encoding="utf-8"))
    strs = sysmsg.streams(d)
    for cl in sysmsg.clusters(strs):
        lo, hi = sysmsg.span(strs, cl)
        if any(smap.get(f"{t:06x}", {}).get("ours") for t in cl):
            out.append((lo, hi))
    names = json.loads((common.GAME_DIR / "textmap" / "names.json").read_text(encoding="utf-8"))
    for name, recs in tables.records(d).items():
        tbl = names.get(name, {})
        for i, (p, body) in enumerate(recs):
            if tbl.get(str(i), {}).get("ours"):
                out.append((p, p + len(body)))
    for fam in captions.FAMILIES:
        for lo, hi in [fam[2]]:
            out.append((lo, hi))
    return out


def scan(d: bytes) -> list[tuple[int, str]]:
    cov = covered(d)

    def is_cov(a: int) -> bool:
        return any(lo <= a < hi for lo, hi in cov)

    runs: list[tuple[int, str]] = []
    i = 0
    while i < CODE_END - 1:
        if _is_jp(int.from_bytes(d[i : i + 2], "big")):
            j, chars = i, []
            while j < CODE_END - 1:
                c = _is_jp(int.from_bytes(d[j : j + 2], "big"))
                if not c:
                    break
                chars.append(c)
                j += 2
            s = "".join(chars)
            # 가나가 든 2자 이상만 — 한자만 이어진 것은 코드·그림이 우연히 풀린 것이 대부분이다
            if len(s) >= 2 and any("぀" <= c <= "ヿ" for c in s) and not is_cov(i):
                runs.append((i, s))
            i = j
        else:
            i += 1
    return runs


def scan_battle(d: bytes) -> list[tuple[str, str]]:
    """전투 아카이브(압축을 푼 110블록)에 남은 일본어. 자리는 `battle:<블록>:<오프셋>`.

    ⚠ 정본이 덮는 자리를 빼지 않는다 — **빌드 결과가 아니라 원본**을 보기 때문이다. 대신 정본에
    번역이 있는 스트림·이름은 이미 덮이므로, 여기 남는 건 (a) 우리가 못 찾은 문안 (b) 비어 있다고
    표시된 예비 레코드의 죽은 이름 (c) 한글 코드가 홀수 자리에서 우연히 풀린 것 셋 중 하나다.
    """
    import json as _json

    bmap = _json.loads((common.GAME_DIR / "textmap" / "battle.json").read_text(encoding="utf-8"))
    mons = _json.loads((common.GAME_DIR / "textmap" / "monsters.json").read_text(encoding="utf-8"))
    out = []
    for n, (_s, b, _e) in enumerate(battle.blocks(d)):
        cov = []
        for tgt, e in battle.refs(b).items():
            if bmap.get(battle.jp_key(e["stream"]), {}).get("ours"):
                cov.append((tgt, e["stream"].end))
        for r in battle.records(b):
            if battle.base_name(r["name"].decode("cp932", "replace")) in mons:
                cov.append((r["name_at"], r["name_at"] + len(r["name"])))
        i = 0
        while i < len(b) - 1:
            ch = _is_jp(int.from_bytes(b[i : i + 2], "big"))
            if ch:
                j, chars = i, []
                while j < len(b) - 1:
                    c = _is_jp(int.from_bytes(b[j : j + 2], "big"))
                    if not c:
                        break
                    chars.append(c)
                    j += 2
                t = "".join(chars)
                if (
                    len(t) >= 2
                    and any("぀" <= c <= "ヿ" for c in t)
                    and not any(lo <= i < hi for lo, hi in cov)
                ):
                    out.append((f"battle:{n}:{i:04x}", t))
                i = j
            else:
                i += 1
    return out


def known() -> dict[str, str]:
    return json.loads(KNOWN_JSON.read_text(encoding="utf-8")) if KNOWN_JSON.exists() else {}


def main() -> None:
    d = common.rom()
    runs = [(f"{a:06x}", s) for a, s in scan(d)] + scan_battle(d)
    if "--freeze" in sys.argv:
        KNOWN_JSON.write_text(
            json.dumps(dict(runs), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"  {KNOWN_JSON}: 남은 자리 {len(runs)} 굳힘")
        return
    k = known()
    new = [(a, s) for a, s in runs if a not in k]
    gone = [a for a in k if not any(x == a for x, _ in runs)]
    print(f"  남은 일본어 {len(runs)} (알려진 {len(k)} · 새 {len(new)} · 없어진 {len(gone)})")
    for a, s in new:
        print(f"    새로 보임 {a}  {s}")
    if "--check" in sys.argv:
        if new:
            raise SystemExit("정본이 안 덮는 일본어가 늘었다 — 옮기거나 tools/jp_left.py --freeze")
    else:
        for a, s in runs:
            print(f"    {a}  {s}")


if __name__ == "__main__":
    main()
