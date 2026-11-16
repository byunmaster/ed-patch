"""원판 텍스트 사본 검사 — 우리가 번역해 바꾼 덩어리의 **원판 바이트 사본**이 제품 롬에 남았는지 롬 전체에서 센다.

    python3 tools/dup_text_scan.py [제품.bin]        # 사본이 있으면 실패

배경(pce-ed1 11-17): 원판 디스크에 대사 블록 사본이 우리가 고친 자리 **밖**에 따로 있었고, 정상 진행이 그 사본을 읽어 장면 전체가 일본어로 나왔다.
빌드·게이트는 「고친 자리」만 분모로 봐서 못 잡았다. 그래서 분모를 **롬 전체**로 잡는다.

세 갈래다(분모는 파서가 아니라 바이트):
 ① 압축 사본 — 원판의 대본·전투 LZ 블록(번역 대상 99+90)의 압축 바이트가 원판 롬 **다른 자리**에 또 있나(= 같은 블록을 가리키는 다른 포인터가 읽을 사본).
 ② 평문 사본 — 대본·전투·시스템 글의 원문 일본어 글줄(가나 2자↑ 포함 SJIS 5자↑)이 제품 롬에 **원판 바이트 그대로** 남았나: ㉠ 롬 원바이트 ㉡ 번역 대상 밖 LZ 묶음(gfx·misc)을 푼 출력.
    번역 대상 묶음(대본·전투)의 풀린 출력은 kana_gate(화면 일본어 게이트)가 이미 센다.
 ③ 원판 압축 블록 통째 잔존 — 제품 롬에서 원판 블록 압축 바이트가 (고친 자리가 아닌 곳에) 그대로 남았나.
허용은 `dup_text_baseline.json`(사유 포함, 사람이 확인한 것) — 기준선보다 늘면 실패.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import lz

BASELINE = Path(__file__).resolve().parents[1] / "textmap" / "dup_text_baseline.json"
RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){5,}")
KANA = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96])")
TRANSLATED = ("script", "battle")
MIN_BLOCK = 24  # 이보다 짧은 압축 블록은 우연히 같은 바이트가 많아 센다 해도 의미가 없다


def _jp_runs(blocks_out: list[bytes]) -> set[bytes]:
    out = set()
    for b in blocks_out:
        for m in RUN.finditer(b):
            if len(KANA.findall(m.group())) >= 2:
                out.add(m.group())
    return out


def _all_find(hay: bytes, needle: bytes) -> list[int]:
    out, i = [], hay.find(needle)
    while i >= 0:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def scan(orig: bytes, prod: bytes) -> dict[str, list[str]]:
    res: dict[str, list[str]] = {"①압축사본(원판)": [], "②평문(롬원바이트)": [], "②평문(비번역 묶음)": [], "③원판블록잔존": []}
    corpus: set[bytes] = set()
    spans = []
    for name in TRANSLATED:
        base = archives.ARCHIVES[name][0]
        for i, (s, out, e) in enumerate(archives.blocks(orig, base)):
            spans.append((name, i, s, e))
            corpus |= _jp_runs([out])
    # ① · ③
    for name, i, s, e in spans:
        raw = orig[s:e]
        if len(raw) < MIN_BLOCK:
            continue
        for p in _all_find(orig, raw):
            if p != s:
                res["①압축사본(원판)"].append(f"{name}[{i}] {s:#x}~{e:#x} 사본 @ {p:#x}")
        for p in _all_find(prod, raw):
            res["③원판블록잔존"].append(f"{name}[{i}] 원판 {s:#x} → 제품 @ {p:#x}")
    # ② 롬 원바이트
    for r in sorted(corpus):
        for p in _all_find(prod, r):
            res["②평문(롬원바이트)"].append(f"{p:#x} {len(r) // 2}자 {r[:24].hex()}")
    # ② 비번역 묶음 출력
    for name, (base, _n, _t) in archives.ARCHIVES.items():
        if name in TRANSLATED:
            continue
        for i, (s, out, _e) in enumerate(archives.blocks(prod, base)):
            for r in sorted(corpus):
                for p in _all_find(out, r):
                    res["②평문(비번역 묶음)"].append(f"{name}[{i}]+{p:#x} {len(r) // 2}자 {r[:24].hex()}")
    return res


def main() -> int:
    prod_path = Path(sys.argv[1]) if len(sys.argv) > 1 else common.BUILD_DIR / "md-ed2" / "ed2-kr.bin"
    orig, prod = common.rom(), prod_path.read_bytes()
    res = scan(orig, prod)
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    bad = 0
    for k, v in res.items():
        allowed = set(base.get(k, {}).get("allowed", []))
        new = [x for x in v if x not in allowed]
        print(f"  {k}: {len(v)}건" + (f" (허용 {len(v) - len(new)})" if len(v) != len(new) else ""))
        for x in new[:20]:
            print(f"    ✗ {x}")
        bad += len(new)
    if bad:
        print(f"❌ 원판 텍스트 사본 {bad}건 — 읽히는 경로면 장면 전체가 일본어로 나온다(pce-ed1 11-17)")
        return 1
    print("  원판 텍스트 사본 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
