"""코드 영역 문안(sysmsg) 커버리지 게이트 — **화면에 나가는데 번역이 빈 스트림**과 **번역에 남은 가나**를 실패로 친다.

    python3 tools/check_sysmsg_gaps.py            # 게이트(새 빈 스트림 · 번역 속 가나 · 낡은 기준선 항목)
    python3 tools/check_sysmsg_gaps.py --list     # 지금 비어 있는 스트림 전부(기준선 대조 없이)
    python3 tools/check_sysmsg_gaps.py --freeze   # 기준선을 지금 상태로 내린다(줄었을 때만 — 늘리는 데엔 쓰지 않는다)

왜 있나 — 엔딩 대사 19스트림이 `textmap/sysmsg.json` 에 `ours` 가 빈 채로 있었는데 게이트가 초록이었다(10-13). 빌드는 빈 항목을 **원문 그대로**
두므로 화면에 일본어가 나가는데도 조용히 통과한다(루트 CLAUDE.md 「화면에 나가는 바이트를 게이트로 본다」). 그래서 「일본어 글자를 가진
스트림인데 유효 번역(sysmsg.json + 장 카드)이 비었다」를 센다.

늘 빨간불이면 아무도 안 보므로 **기준선**(`textmap/sysmsg_gaps.json`: 키 → 사유)을 두는 래칫이다 — 기준선 밖의 새 빈 스트림은 실패, 기준선 항목이
번역으로 채워지면 「기준선에서 지우라」고 알린다(실패). 기준선이 줄어들 때만 `--freeze`.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chapters
import common
import sysmsg

BASELINE = common.GAME_DIR / "textmap" / "sysmsg_gaps.json"
JP = re.compile("[ぁ-んァ-ヶｦ-ﾟ一-龥々]")


def gaps(orig: bytes) -> dict[str, str]:
    """{키: 원문 앞머리} — 일본어 글자가 있는데 유효 번역이 빈 스트림."""
    strs = sysmsg.streams(orig)
    smap = json.loads(sysmsg.MAP_JSON.read_text(encoding="utf-8")) if sysmsg.MAP_JSON.exists() else {}
    cards = chapters.plan(strs)  # 장 카드는 정본 장 제목에서 만든다(build.load_sysmsg 와 같은 합침)
    out = {}
    for t, e in sorted(strs.items()):
        k = f"{t:06x}"
        txt = "".join(
            tk.raw.decode("cp932", "replace") for tk in e["stream"].tokens if tk.kind == "text"
        )
        if not JP.search(txt):
            continue
        if cards.get(k) or smap.get(k, {}).get("ours"):
            continue
        out[k] = txt.replace("\n", "")[:24]
    return out


def kana_in_ours() -> list[str]:
    smap = json.loads(sysmsg.MAP_JSON.read_text(encoding="utf-8")) if sysmsg.MAP_JSON.exists() else {}
    return [k for k, v in smap.items() if JP.search(v.get("ours", ""))]


def main() -> int:
    cur = gaps(common.rom())
    if "--list" in sys.argv:
        for k, v in cur.items():
            print(f"  {k} {v}")
        print(f"  빈 스트림 {len(cur)}")
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    if "--freeze" in sys.argv:
        new = {k: base.get(k, "P4 대기(이벤트 대사 번역 라운드)") for k in cur}
        if BASELINE.exists() and len(new) > len(base):
            raise SystemExit("기준선은 늘리지 않는다 — 새 빈 스트림은 번역으로 채운다")
        BASELINE.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  기준선 {len(base)} → {len(new)}")
        return 0
    bad = [k for k in cur if k not in base]
    stale = [k for k in base if k not in cur]
    kana = kana_in_ours()
    print(f"  sysmsg 화면 문안 — 빈 스트림 {len(cur)} (기준선 {len(base)}) · 번역 속 가나 {len(kana)}")
    rc = 0
    if bad:
        rc = 1
        print("  ✗ 번역이 비어 화면에 일본어가 나가는 새 스트림:")
        for k in bad:
            print(f"    {k} {cur[k]}")
    if kana:
        rc = 1
        print(f"  ✗ 번역에 가나가 남았다: {kana}")
    if stale:
        rc = 1
        print(f"  ✗ 번역이 채워졌다 — 기준선에서 지운다(--freeze): {stale}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
