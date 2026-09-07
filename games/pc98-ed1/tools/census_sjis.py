"""게임이 실제로 쓰는 SJIS 코드 전수 — **한글을 어느 자리에 앉히나**의 근거.

글꼴이 ROM 이라 「폰트 표의 빈 슬롯」이라는 게 없다. 대신 후킹한 CG 루틴이
**어떤 코드를 가로챌지**를 정해야 하는데, 그러려면 **원본이 안 쓰는 코드 대역**을 알아야
한다. 쓰는 자리를 뺏으면 그 글자가 화면에서 사라진다.

CG 루틴이 코드를 JIS 로 바꿔 쓰므로(`sub ah,0x20` 앞뒤, status.md 2절) 여기서도
**SJIS → JIS 구(ku)·점(ten)** 으로 환산해 본다.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def sjis_to_jis(hi: int, lo: int) -> tuple[int, int]:
    """SJIS 2바이트 → (구, 점). JIS X 0208 의 1-based 좌표."""
    if hi <= 0x9F:
        hi -= 0x81
        ku = hi * 2 + 1
    else:
        hi -= 0xC1
        ku = hi * 2 + 1
    if lo < 0x9F:
        ten = lo - (0x40 if lo < 0x7F else 0x41) + 1
    else:
        ku += 1
        ten = lo - 0x9E
    return ku, ten


def collect() -> Counter:
    """🔴 **덤프한 문안에서만 센다.** 디스크를 생으로 훑으면 코드·그래픽이 우연히 SJIS 로
    읽혀 과대추정된다(실측: 생 훑기 6,333종 — 그 값으로는 판단이 안 선다)."""
    used: Counter = Counter()
    texts: list[str] = []
    for name in ("scn_jp/scenario", "scn_jp/combat", "sys_jp/event", "sys_jp/program"):
        path = common.OUT_DIR / f"{name}.json"
        if not path.exists():
            raise SystemExit(
                f"덤프가 없다: {path}\n  tools/dump_scn.py · tools/dump_sys.py 를 먼저 돌린다."
            )
        texts += [b["t"] for b in json.loads(path.read_text(encoding="utf-8"))]
    for t in texts:
        for ch in t:
            try:
                enc = ch.encode("shift_jis")
            except UnicodeEncodeError:
                continue
            if len(enc) == 2:
                used[(enc[0], enc[1])] += 1
    return used


def main() -> int:
    common.check_originals()
    used = collect()
    ku_hist: Counter = Counter()
    for (hi, lo), n in used.items():
        ku, _ = sjis_to_jis(hi, lo)
        ku_hist[ku] += n
    print(f"쓰이는 SJIS 코드 {len(used):,}종 (등장 {sum(used.values()):,}회)")
    # 🔴 자리는 **구 단위가 아니라 코드 단위**로 센다. 한글은 안 쓰는 구를 통째로 뺏는 게
    #    아니라 **안 쓰는 코드**에 하나씩 앉히면 된다(PS1 도 한자 슬롯에 그렇게 앉혔다).
    used_pos = set()
    for hi, lo in used:
        used_pos.add(sjis_to_jis(hi, lo))
    bands = {
        "1구역 비한자 (ku 1~8)": range(1, 9),
        "한자 1급 (ku 16~47)": range(16, 48),
        "한자 2급 (ku 48~84)": range(48, 85),
    }
    print("\n  JIS 자리 — 한글 2,350자를 앉힐 **빈 코드**가 있나")
    for name, rng in bands.items():
        total = len(rng) * 94
        u = sum(1 for k, t in used_pos if k in rng)
        print(f"    {name:22s} 전체 {total:5,} · 쓰임 {u:5,} · **빈 자리 {total - u:5,}**")
    kanji = [k for k in range(16, 85)]
    free_kanji = len(kanji) * 94 - sum(1 for k, t in used_pos if k in kanji)
    print(f"\n  한자 1·2급 빈 자리 합 {free_kanji:,} — 한글 2,350자가 ", end="")
    print("들어간다." if free_kanji >= 2350 else "🔴 안 들어간다.")
    empty_ku = [k for k in range(1, 95) if ku_hist.get(k, 0) == 0]
    print(f"  참고 · 한 번도 안 쓰인 구 {len(empty_ku)}개: {empty_ku}")

    out = common.REVIEW_DIR / "sjis_census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "ku_counts": {str(k): v for k, v in sorted(ku_hist.items())},
                "empty_ku": empty_ku,
                "used_codes": len(used),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
