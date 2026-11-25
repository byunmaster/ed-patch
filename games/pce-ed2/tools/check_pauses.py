"""멈춤 개수 게이트 — 원판 줄마다 연출 멈춤(`11 nn nn`)·속도(`10 nn`) 제어 개수가 제품 줄과 같은가(빌드 산출물 대조, 11-07).

번역 때 멈춤은 구절 경계에 되살리는데(`dialogue._encode`) 빌드 공간이 모자라 끄거나 조판이 줄을 합치면 **원판 연출 멈춤이 조용히 사라진다**. 줄 수가 같은 덩이의 줄 짝마다 개수를 세어 다르면 낸다.
기준선(`data/pause_count_baseline.tsv`)은 지금 알려진 차이 — 새 차이가 생기면 실패, 줄면 `--freeze`.
실행: `python3 games/pce-ed2/tools/check_pauses.py [iso] [--freeze]`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import package
import residual_gate
import systext

BASE = common.GAME_DIR / "data" / "pause_count_baseline.tsv"


def _count(line: bytes, code: int) -> int:
    return sum(1 for k, b in systext.tokens(line) if k == "ctrl" and b[0] == code)


def diffs(iso: Path) -> dict[str, tuple[int, int, int]]:
    """{`rel:메시지:줄`: (코드, 원판 개수, 제품 개수)} — 개수가 다른 줄. 줄 수가 다른 덩이·200줄↑ 자료 덩이는 건너뛴다."""
    t = residual_gate._built(iso)
    out = {}
    for rel in sorted(package.CLEAN):
        o = bytes(common.track_data(rel, 128))
        p = t(rel)
        To, tabo = package.msg_table(o)
        Tp, tabp = package.msg_table(p)
        eo, ep = dict(package.chunks(o)), dict(package.chunks(p))
        seen = set()
        for m, (a, c) in enumerate(zip(tabo, tabp, strict=False)):
            if a <= To or c <= Tp or (a, c) in seen or a not in eo or c not in ep:
                continue
            seen.add((a, c))
            try:
                do = package.decode_chunk(o, a, eo[a])[0].split(b"\x00")
                dp = package.decode_chunk(p, c, ep[c])[0].split(b"\x00")
            except Exception:
                continue
            if len(do) > 200 or len(do) != len(dp):
                continue
            for i, (x, y) in enumerate(zip(do, dp, strict=True)):
                for code in (0x11,):
                    nx, ny = _count(x, code), _count(y, code)
                    if nx != ny:
                        out[f"{rel}:{m}:{i}"] = (code, nx, ny)
    return out


def known() -> dict[str, str]:
    if not BASE.exists():
        return {}
    return dict(
        ln.split("\t")[:2]
        for ln in BASE.read_text(encoding="utf-8").splitlines()
        if ln and not ln.startswith("#")
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iso = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2.iso"
    now = diffs(iso)
    cur = {k: f"{v[1]}→{v[2]}" for k, v in now.items()}
    if "--freeze" in sys.argv:
        BASE.write_text(
            "# 원판과 멈춤(`11 nn nn`) 개수가 다른 줄 — `rel:메시지:줄 <TAB> 원판→제품`. 줄면 `check_pauses.py --freeze`.\n"
            + "".join(f"{k}\t{v}\n" for k, v in sorted(cur.items())),
            encoding="utf-8",
        )
        print(f"{len(cur)}줄 → {BASE.relative_to(common.ROOT)}")
        return 0
    kn = known()
    new = sorted(set(cur) - set(kn))
    gone = sorted(set(kn) - set(cur))
    worse = sorted(k for k in set(cur) & set(kn) if cur[k] != kn[k])
    if new or worse:
        print(
            f"✖ 멈춤 개수가 원판과 다른 새 줄 {len(new)} · 바뀐 줄 {len(worse)} — 예: {[(k, cur[k]) for k in (new + worse)[:6]]}"
        )
        return 1
    if gone:
        print(
            f"✖ 기준선이 낡았다(이제 같아진 줄 {len(gone)}) — `check_pauses.py --freeze` 로 내린다: {gone[:6]}"
        )
        return 1
    print(f"멈춤 개수 게이트 OK — 원판과 다른 줄 {len(cur)}(기준선)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
