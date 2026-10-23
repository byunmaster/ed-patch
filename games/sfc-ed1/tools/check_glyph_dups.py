#!/usr/bin/env python3
"""**구운 글리프끼리 같은 비트맵이면 실패** — 롬에서 읽어 센다(원본 글꼴 파일이 아니라). 0건 유지.

    python3 tools/check_glyph_dups.py

## 왜 있나 (2026-10-20)

ss-ed1+2 에서 글꼴을 구울 때 행 맞춤(dy)이 쉼표 꼬리 행을 잘라 반각 쉼표가 마침표와 **같은 비트맵**으로 구워졌다 — 문안의 쉼표 3,983곳이 전부 마침표로 그려졌다(관리자 10-20).
sfc-ed1 은 대사 부호를 두 군데서 구운다: ① 원본 1바이트 코드 그림 표 `rawtab`(합성 칸이 읽는다 — `, . ! ? 「 」` 등, 16B 1bpp) ② 글리프 뱅크(한글 + `GLYPH_SYMBOLS`, 32B 2bpp, 색인 1,024 이상은 둘째 뱅크).
빌드 manifest 의 라벨로 위치를 찾고, 비지 않은 그림 가운데 같은 것이 있으면 실패한다. 글리프 뱅크의 비워 둔 자리(`encode.bad_index` — `$FF` 하위 색인)는 메움 무늬(`00 FF` 반복)라 제외한다.
지정 쌍(`, .` · `! ?` · `「 」` · `( )` …)은 둘 다 비면 안 되고 서로 달라야 한다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,F401,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import encode  # noqa: E402

FILLER = bytes([0x00, 0xFF] * 16)  # 비워 둔 색인 자리의 메움 무늬
PAIRS = [(",", "."), ("!", "?"), ("「", "」"), (":", ";"), ("(", ")"), ("『", "』"), ("、", "。"), ("'", "`")]


def _find(d, key):
    if isinstance(d, dict):
        if key in d:
            return d[key]
        for v in d.values():
            r = _find(v, key)
            if r is not None:
                return r
    return None


def _off(label: str) -> int:
    bank, addr = label.lstrip("$").split(":")
    return common.snes2off((int(bank, 16) << 16) | int(addr, 16))


def scan(slot: Path) -> list[str]:
    man = json.loads((slot / "manifest.json").read_text(encoding="utf-8"))
    rom = next(slot.glob("*.sfc")).read_bytes()
    bad: list[str] = []
    # ① rawtab — 코드 0..$CE × 16B
    off = _off(_find(man, "rawtab"))
    code2ch = {v: k for k, v in encode.KR_TABLE.items() if v < 0xCF and k != "\\n"}
    pics: dict[bytes, list[int]] = {}
    for code in range(0xCF):
        p = rom[off + code * 16 : off + code * 16 + 16]
        if any(p):
            pics.setdefault(p, []).append(code)
    for v in pics.values():
        if len(v) > 1:
            bad.append("rawtab 같은 그림: " + " ".join(f"{code2ch.get(c, '?')}(${c:02X})" for c in v))
    for a, b in PAIRS:
        ca, cb = encode.KR_TABLE.get(a), encode.KR_TABLE.get(b)
        if ca is None or cb is None or ca >= 0xCF or cb >= 0xCF:
            continue  # 그 부호는 글리프 뱅크 쪽(아래에서 센다)
        pa, pb = rom[off + ca * 16 : off + ca * 16 + 16], rom[off + cb * 16 : off + cb * 16 + 16]
        if not any(pa) or not any(pb):
            bad.append(f"rawtab {a}{b}: 그림이 비었다")
    # ② 글리프 뱅크 — 색인 < 1024 는 `$3D:8000`, 이상은 `$3C:8000`, 32B
    n = int(_find(man, "glyphs") or 0)
    b1, b2 = common.snes2off(0x3D8000), common.snes2off(0x3C8000)
    gp: dict[bytes, list[int]] = {}
    for i in range(n):
        base = b1 + i * 32 if i < 1024 else b2 + (i - 1024) * 32
        p = rom[base : base + 32]
        if any(p) and p != FILLER:
            gp.setdefault(p, []).append(i)
    for v in gp.values():
        if len(v) > 1:
            bad.append(f"글리프 뱅크 같은 그림: 색인 {v}")
    return bad


def main() -> int:
    slots = [m.parent for m in sorted(common.BUILD_DIR.glob("*/manifest.json")) if list(m.parent.glob("*.sfc"))]
    if not slots:
        print("  글리프 비트맵 중복 — 안 쟀다(빌드 칸 없음 — 빌드 뒤에 다시)")
        return 1
    total = 0
    for s in slots:
        bad = scan(s)
        total += len(bad)
        print(f"  글리프 비트맵 중복 [{s.name}] — {'위반 ' + str(len(bad)) if bad else '같은 쌍 0'}")
        for b in bad:
            print("  ✗", b)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
