#!/usr/bin/env python3
"""화면에 일본어가 남은 자리를 센다(PS1 `check_jp_left` 에 해당) — 분모를 같이 찍는다.

- **칸**(사전 · HUD/슬롯 지명 · 메뉴 라벨)은 미번역이 하나라도 있으면 실패 — 고정 폭 칸이라 지금 다 채울 수 있다.
- **문장**(대사·전투·시스템)은 미번역 수를 **알리기만** 한다 — 아직 번역 중인 대사가 「할 일」이지 「실패」가 아니다.
  늘 빨간불이면 아무도 안 본다(루트 CLAUDE.md). 대신 분모를 찍어 「0 이라 통과」 가짜 초록을 막는다.

  python3 tools/check_jp_left.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import names_corpus  # noqa: E402


def data_fragments() -> set[str]:
    """화면에 안 나온다는 근거가 있는 데이터 파편 id(textmap/data_fragments.json) — 경고로만 센다."""
    p = common.GAME_DIR / "textmap" / "data_fragments.json"
    return set(json.loads(p.read_text(encoding="utf-8"))["ids"]) if p.exists() else set()


_KANA_HAN = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def has_jp_text(jp: str) -> bool:
    """제어 코드 `<..>` · 사전 이름 `{..}` 를 뺀 글에 가나·한자가 있나 — 없으면(제어만 · 공백 · 숫자 · 말줄임) 번역할 일본어가 아니다."""
    return bool(_KANA_HAN.search(re.sub(r"<[^>]*>|\{[^}]*\}", "", jp)))


_BASELINE = common.GAME_DIR / "textmap" / "unregistered_runs_baseline.json"
_KANA_CODES = (
    set(range(0x11, 0x80))
    | {0x0B, 0x0C, 0x0E, 0x0F, 0x83, 0x84, 0x85, 0x86}
    | set(range(0x90, 0xC3))
)
_BASE_CODES = set(range(0x11, 0x70)) | set(range(0x90, 0xC3))
_TERM = {0xCF, 0xE0, 0xE4, 0xFF, 0xFE, 0xFA, 0xD0, 0xD1, 0xD2, 0xD3, 0xD5}


def unregistered_runs(rom: bytes) -> list[int]:
    """전체 훑기 — 원판 롬 전체를 문자 코드로 읽어 **정본에 안 올라간** 가나 런(5자↑, 끝이 종결·치환 코드)의 시작 오프셋.
    등록 = 포인터가 가리키는 본문·추가 구간·사전 문자열 · 전투 UI/지명 칸($02:A30A~B000) · 스태프롤($06:FB55~). 남는 건 그래픽·맵·코드 바이트가 우연히 가나 코드인 것이다.
    ⚠ 읽히는지는 기계가 못 가른다(그래픽 반복이 글보다 점수가 높다) — 그래서 **기준선(오프셋 목록)에 없는 새 런이 생기면 실패**로 친다."""
    import bisect
    import importlib.util as iu

    spec = iu.spec_from_file_location("sfc_text", Path(__file__).with_name("text.py"))
    t = iu.module_from_spec(spec)
    spec.loader.exec_module(t)
    reg = sorted([(o, o + len(r)) for *_h, o, r, _l in t.all_segments(rom)] + list(t.EXTRA_REGIONS))
    starts = [a for a, _b in reg]

    def registered(o: int) -> bool:
        k = bisect.bisect_right(starts, o) - 1
        bk, w = o // 0x8000, 0x8000 + o % 0x8000
        if (
            bk == 2
            and (0xE7E0 <= w < 0xF300 or 0xA30A <= w < 0xB000)
            or bk == 3
            and 0xEF00 <= w < 0xF600
            or bk == 6
            and w >= 0xFB55
        ):
            return True
        return k >= 0 and reg[k][0] <= o < reg[k][1]

    out, i, n = [], 0, len(rom)
    while i < n:
        if rom[i] in _KANA_CODES:
            j = i
            while j < n and rom[j] in _KANA_CODES:
                j += 1
            if (
                j - i >= 5
                and sum(1 for x in rom[i:j] if x in _BASE_CODES) >= 4
                and j < n
                and rom[j] in _TERM
                and not registered(i)
            ):
                out.append(i)
            i = j
        else:
            i += 1
    return out


def scan_gate(freeze: bool = False) -> int:
    runs = unregistered_runs(common.rom_bytes())
    base = set(json.loads(_BASELINE.read_text(encoding="utf-8"))["offsets"]) if _BASELINE.exists() else None
    if freeze:
        _BASELINE.write_text(
            json.dumps(
                {
                    "_doc": "전체 훑기 기준선 — 정본에 없는 가나 런(원판 오프셋). 눈으로 전수 확인함(11-05): 읽히는 글 0, 전부 그래픽·맵·코드. 새 오프셋이 생기면 실패.",
                    "offsets": runs,
                }
            ),
            encoding="utf-8",
        )
        print(f"전체 훑기 기준선 {len(runs)}건 얼림")
        return 0
    new = [r for r in runs if base is not None and r not in base] if base is not None else runs
    print(
        f"전체 훑기(정본 밖 가나 런) — {len(runs)}건 · 기준선 밖 새 런 {len(new)}"
        + (" ⛔" if new else "")
    )
    for r in new[:10]:
        print(f"      {r // 0x8000:02X}:{0x8000 + r % 0x8000:04X}")
    return 1 if new else 0


def main() -> int:
    tot: dict[str, int] = {}
    left: dict[str, list[str]] = {}
    warn: list[str] = []  # 근거 있는 데이터 파편(경고 — 통과)
    dead = data_fragments()
    segs = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    notext: list[str] = []
    for where, jp, kr, _kind in names_corpus.screen_pairs():
        area = where.split(":")[0]
        tot[area] = tot.get(area, 0) + 1
        if not kr:
            if area == "seg" and where.split(":")[1].split("@")[0] in dead:
                warn.append(where)
                continue
            if area == "seg" and (segs.get(where.split(":")[1].split("@")[0]) or {}).get("kr"):
                continue  # 번역 정본에 문안이 있다(글자가 없는 문안 — 색·호출만 남긴 조각)
            if area == "seg" and not has_jp_text(jp):
                notext.append(
                    where
                )  # 글 없는 조각(분기·호출만 · 공백 · 숫자 · 말줄임) — 화면에 일본어가 나갈 수 없다
                continue
            left.setdefault(area, []).append(f"{where} {jp[:14]!r}")
    bad = 0
    for area in sorted(tot):
        n = len(left.get(area, []))
        w = len(warn) if area == "seg" else 0
        nt = len(notext) if area == "seg" else 0
        slot = area != "seg"
        # 🔴 근거 있는 데이터 파편(textmap/data_fragments.json)은 「경고」로 따로 센다 — 검사에는 걸리지만 통과(마스터 10-11).
        #    목록 밖 잔존은 종전처럼 일본어 잔존으로 센다(문장은 번역 중이라 알리기만 · 칸은 실패)
        print(
            f"  {area:6s} 번역 {tot[area] - n - w - nt:,}/{tot[area]:,} · 일본어 잔존 {n}"
            + (f" · ⚠ 경고(화면에 안 나오는 데이터 파편) {w}" if w else "")
            + (f" · 글 없는 조각 {nt}" if nt else "")
            + (" ⛔" if slot and n else "")
        )
        if slot and n:
            bad += n
            for s in left[area][:10]:
                print("     ", s)
    print(f"화면 일본어(칸): {bad}건" + (" — 실패" if bad else ""))
    return 1 if (bad or scan_gate()) else 0


if __name__ == "__main__":
    if "--freeze-scan" in sys.argv:
        sys.exit(scan_gate(freeze=True))
    sys.exit(main())
