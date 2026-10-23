"""롬 전체 잔존 일본어 게이트 — 구운 롬에 **원문 가나·한자 12자↑ 런**이 알려진 자리 밖에 남았나(마스터 10-18, sfc-ed2 가 먼저 낸 꼴).

    python3 tools/check_residual_jp.py            # 게이트(새 런이 있으면 실패)
    python3 tools/check_residual_jp.py --list     # 런 목록

「번역 분모(구간 목록)만 세는 게이트는 분모에서 빠진 문안을 못 잡는다」 — `scene.py`·`battle.py` 스트림 발견이 못 찾는 자리와
필터에 걸려 분모에서 빠진 문안이 화면에 일본어로 나올 수 있다. 그래서 **바이트를 직접** 센다: 롬 본체 + 압축 블록(대본 225 · 전투 110 · 시스템)을 푼 것에서
SJIS 가나·한자가 12자 넘게 이어지는 런을 찾고, **우리 한글 코드(`textmap/hangul_codes.json`)는 빼고** 센다(한글이 SJIS 한자 코드 자리에 들어 있다).
알려진 자리는 근거와 함께 `KNOWN` 에 둔다 — 새 런이 생기면 빌드된 롬이 번역 안 한 일본어를 달고 나간다는 뜻이다.
구운 빌드 롬이 없으면 「안 쟀다」로 알리고 통과한다(게이트 환경에 원본·빌드가 없을 수 있다).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common

MIN_RUN = 12  # 롬 본체(그래픽 잡음이 많아 길게)
MIN_RUN_BLOCK = 5  # 압축 블록(문안 전용) — 5자↑. 실측: 5자에서도 0런, 4자에서 이진 잡음 2건(2026-10-18, 짧은 문장 구멍 방지)
TEXT_ARCHIVES = ("script", "battle", "sys")  # 문안이 든 압축 블록 묶음

# (구역, 시작, 끝, 근거) — 구역: "rom" 롬 본체 오프셋 · "<아카이브 이름>:<블록>" 푼 블록 안 오프셋.
KNOWN = [
    ("rom", 0x0AE86E, 0x0AE86E + 2 * 16, "그래픽 타일 반복 바이트(같은 글자가 이어지는 잡음)"),
    ("rom", 0x0B886E, 0x0B886E + 2 * 16, "그래픽 타일 반복 바이트(같은 글자가 이어지는 잡음)"),
    ("rom", 0x0B8C6E, 0x0B8C6E + 2 * 21, "그래픽 타일 반복 바이트(같은 글자가 이어지는 잡음)"),
    ("rom", 0x0B8D94, 0x0B8D94 + 2 * 13, "그래픽 타일 반복 바이트(같은 글자가 이어지는 잡음)"),
    (
        "rom",
        0x1A5E72,
        0x1A5E72 + 2 * 263,
        "글꼴 문자 코드표(SJIS 한자 순서 나열 — 글리프 순번표지 문안이 아니다)",
    ),
    ("rom", 0x1A623C, 0x1A623C + 2 * 73, "글꼴 문자 코드표(SJIS 가나 순서 나열)"),
]


def hangul_codes() -> set[int]:
    return set(
        json.loads(
            (common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")
        ).values()
    )


def _jp(a: int, b: int, ko: set[int]) -> bool:
    if ((a << 8) | b) in ko:
        return False
    try:
        c = ord(bytes([a, b]).decode("cp932"))
    except (UnicodeDecodeError, TypeError):
        return False
    return 0x3041 <= c <= 0x30FF or 0x4E00 <= c <= 0x9FFF


def _lead(x: int) -> bool:
    return 0x81 <= x <= 0x9F or 0xE0 <= x <= 0xEF


def find_runs(data: bytes, ko: set[int], min_run: int = MIN_RUN) -> list[tuple[int, int]]:
    """[(오프셋, 글자 수)] — 한글 코드를 뺀 가나·한자(2바이트)가 min_run 자 이상 이어지는 런."""
    out = []
    i, n = 0, len(data)
    while i < n - 1:
        if _lead(data[i]) and _jp(data[i], data[i + 1], ko):
            j = i
            while j < n - 1 and _lead(data[j]) and _jp(data[j], data[j + 1], ko):
                j += 2
            if (j - i) // 2 >= min_run:
                out.append((i, (j - i) // 2))
            i = j
        else:
            i += 1
    return out


def scan(rom: bytes, ko: set[int]) -> list[tuple[str, int, int]]:
    """[(구역, 오프셋, 글자 수)] — 롬 본체 + 압축 블록을 푼 것."""
    found = [("rom", o, n) for o, n in find_runs(rom, ko)]
    for (
        name
    ) in TEXT_ARCHIVES:  # gfx_* 는 그림이라 안 본다(픽셀 바이트가 가나·한자 코드로 읽히는 잡음)
        for k, (_s, b, _e) in enumerate(archives.blocks(rom, archives.ARCHIVES[name][0])):
            found += [(f"{name}:{k}", o, n) for o, n in find_runs(b, ko, MIN_RUN_BLOCK)]
    return found


def unknown(found: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    out = []
    for where, off, n in found:
        end = off + 2 * n
        if not any(w == where and s <= off and end <= e for w, s, e, _ in KNOWN):
            out.append((where, off, n))
    return out


def built_rom() -> bytes | None:
    p = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    return p.read_bytes() if p.exists() else None


def main() -> int:
    rom = built_rom()
    if rom is None:
        print("  롬 전체 잔존 일본어 — 구운 빌드 롬이 없어 안 쟀다")
        return 0
    found = scan(rom, hangul_codes())
    bad = unknown(found)
    if "--list" in sys.argv:
        for w, o, n in found:
            print(f"  {w} 0x{o:X} {n}자{'' if (w, o, n) not in bad else '  ← 새 런'}")
    print(f"  롬 전체 잔존 일본어 {len(found)}런 (알려진 {len(found) - len(bad)} · 새 {len(bad)})")
    if bad:
        for w, o, n in bad:
            print(f"  ❌ 새 런: {w} 0x{o:X} {n}자")
        print(
            "     번역 안 한 일본어가 구운 롬에 남았다 — 문안을 번역하거나, 글자표·그래픽 잡음이면 근거와 함께 KNOWN 에 올린다"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
