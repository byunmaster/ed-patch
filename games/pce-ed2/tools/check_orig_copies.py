"""원판 사본 잔존 게이트 — 우리가 고친 원판 덩어리의 **원판 바이트 그대로의 사본**이 이미지 어딘가에 남았는지 본다 (마스터 11-17, PCE I 사고의 재발 방지).

    python3 games/pce-ed2/tools/check_orig_copies.py [ISO 경로] [--gate] [--verbose]

왜: pce-ed1 에서 원판 디스크에 대사 블록의 **사본이 우리가 고친 자리 밖**(맵별 레코드 안)에 따로 있었고, 정상 진행이 그 사본을 읽어 장면 전체가 일본어 원문으로 나왔다.
빌드·게이트는 고친 자리만 분모로 봐서 못 잡았다. 이 검사의 분모는 **이미지 전체**다.

방법(원문을 문서에 옮기지 않는다 — 바이트만 다룬다):
  1. 원판과 제품의 데이터 트랙 유저 데이터를 맞대 **고친 덩어리**(차이가 `MERGE` 바이트 안으로 이어진 구간, `MIN_LEN`↑)를 뽑는다.
  2. 각 덩어리의 **원판 바이트**에서 앵커 창(앞·가운데·뒤, 서로 다른 바이트 `MIN_DISTINCT`↑ — 0·FF 채움 · 반복 무늬는 거른다)을 골라 **원판 전체**에서 찾는다.
  3. 덩어리 밖에서 찾았고, 제품에도 그 자리가 **원판 바이트 그대로**면 「남은 사본」이다. 알려진 목록(`data/orig_copies_known.tsv`)에 없으면 실패한다.
     (앵커 한 창만 우연히 같은 반복 무늬는 거른다 — 덩어리 전체가 절반↑ 원판과 같고 제품도 그 바이트 그대로여야 사본이다.)
     알려진 목록에는 위치(`rel:오프셋`)와 사유만 둔다(원문 없음). 줄어든 것(이제 안 남은 것)이 목록에 있어도 실패 — 래칫.
  · 평문 문자열이든 압축 블록이든 같다 — 바이트가 같으면 사본이다(압축본은 압축된 바이트로 찾는다).
  · 데이터 트랙 거울(rel +36,864)은 빌드가 같이 쓰므로 사본이 아니다 — 거울에서 찾은 건 거울 위치끼리 짝이 맞는지로 갈라 센다.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

MIN_LEN = 16  # 이보다 짧은 고침(주소·상수 몇 바이트)은 덩어리로 안 센다. 단 `LONG_LEN` 미만은 SJIS 글자 쌍이 `MIN_SJIS` 개↑일 때만(팔레트·표 조각 거름)
LONG_LEN = 64  # 이 길이↑ 덩어리는 글자 모양을 안 따진다(압축 블록 포함)
MIN_SJIS = 4  # 짧은 덩어리는 SJIS 글자(앞바이트 81~9F·E0~EA + 뒷바이트 40~FC) 쌍이 이만큼↑이어야 문안으로 본다
MERGE = 8  # 차이 사이 이만큼까지는 같은 덩어리
WIN = 16  # 앵커 창 길이
MIN_DISTINCT = 6  # 앵커(16B)에 서로 다른 바이트가 이만큼↑ 있어야 한다 — 채움·반복·팔레트 무늬 거름
MIRROR = 36864 * common.USER
KNOWN = common.GAME_DIR / "data" / "orig_copies_known.tsv"


def load_track(iso: Path) -> bytes:
    """ISO(2352B raw)에서 데이터 트랙 유저 데이터만 이어 붙인다."""
    raw = np.fromfile(iso, dtype=np.uint8, count=(common.T2_SECTOR + common.T2_LEN) * common.RAW)
    raw = raw[common.T2_SECTOR * common.RAW :].reshape(common.T2_LEN, common.RAW)
    return raw[:, common.USER_OFF : common.USER_OFF + common.USER].tobytes()


def chunks(orig: bytes, prod: bytes) -> list[tuple[int, int]]:
    a = np.frombuffer(orig, np.uint8)
    b = np.frombuffer(prod, np.uint8)
    n = min(len(a), len(b))
    idx = np.flatnonzero(a[:n] != b[:n])
    out: list[tuple[int, int]] = []
    if len(idx) == 0:
        return out
    start = prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - prev > MERGE:
            out.append((start, prev + 1))
            start = i
        prev = i
    out.append((start, prev + 1))
    return [
        (s, e)
        for s, e in out
        if e - s >= MIN_LEN and (e - s >= LONG_LEN or sjis_pairs(orig[s:e]) >= MIN_SJIS)
    ]


def sjis_pairs(seg: bytes) -> int:
    n = i = 0
    while i < len(seg) - 1:
        if (0x81 <= seg[i] <= 0x9F or 0xE0 <= seg[i] <= 0xEA) and 0x40 <= seg[i + 1] <= 0xFC:
            n += 1
            i += 2
        else:
            i += 1
    return n


def anchors(seg: bytes) -> list[tuple[int, bytes]]:
    """덩어리 원판 바이트에서 앵커 창 — (덩어리 안 오프셋, 바이트)."""
    if len(seg) < WIN:
        return []
    picks = {0, (len(seg) - WIN) // 2, len(seg) - WIN}
    out = []
    for off in sorted(picks):
        w = seg[off : off + WIN]
        if len(set(w)) >= MIN_DISTINCT:
            out.append((off, w))
    return out


def find_copies(orig: bytes, prod: bytes) -> tuple[list[tuple[int, int]], dict[int, list[int]]]:
    """(고친 덩어리 목록, {남은 사본 시작(원판 오프셋): [출처 덩어리 시작…]})."""
    ch = chunks(orig, prod)
    starts = [s for s, _ in ch]
    import bisect

    def inside(pos: int) -> bool:
        i = bisect.bisect_right(starts, pos) - 1
        return i >= 0 and ch[i][0] <= pos < ch[i][1]

    found: dict[int, list[int]] = {}
    for s, e in ch:
        seg = orig[s:e]
        for off, w in anchors(seg):
            p = orig.find(w)
            while p != -1:
                base = p - off  # 같은 덩어리의 사본이면 이 자리에서 덩어리가 시작한다
                if p != s + off and not inside(p) and prod[p : p + WIN] == w and base >= 0:
                    # 앵커 한 창만 우연히 같은 것(반복 표 무늬)은 사본이 아니다 — 덩어리 전체가 절반↑ 같아야 한다
                    cand = orig[base : base + len(seg)]
                    same = int(
                        (
                            np.frombuffer(cand, np.uint8)
                            == np.frombuffer(seg[: len(cand)], np.uint8)
                        ).sum()
                    )
                    if same * 2 >= len(seg) and prod[base : base + len(seg)] == cand:
                        found.setdefault(base, []).append(s)
                p = orig.find(w, p + 1)
    return ch, found


def load_known() -> dict[str, str]:
    out: dict[str, str] = {}
    if KNOWN.exists():
        for ln in KNOWN.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#"):
                k, _, why = ln.partition("\t")
                out[k] = why
    return out


def key(pos: int) -> str:
    return f"{pos // common.USER}:{pos % common.USER:#x}"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gate = "--gate" in sys.argv
    verbose = "--verbose" in sys.argv
    iso = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / f"{common.ROM_STEM}.iso"
    orig = load_track(common.ORIG_ISO)
    prod = load_track(iso)
    ch, found = find_copies(orig, prod)
    known = load_known()
    # 같은 덩어리 사본은 앵커 셋이 한 자리로 모인다 — 자리(기준 오프셋)당 한 건
    # 거울(+36,864) 쪽 사본은 짝이 있으면 한 자리로 센다
    items = sorted(
        (p, src) for p, src in found.items() if not (p >= MIRROR and p - MIRROR in found)
    )
    print(
        f"고친 덩어리 {len(ch)}개 · 원판 바이트 그대로 남은 사본 자리 {len(items)}곳 (제품 {iso.name})"
    )
    bad = [(p, src) for p, src in items if key(p) not in known]
    for p, src in items:
        tag = "알려짐" if key(p) in known else "신규"
        if verbose or tag == "신규":
            print(f"  {tag} {key(p)} ← 덩어리 {key(src[0])} (앵커 {len(src)}개 일치)")
    stale = [k for k in known if k not in {key(p) for p, _ in items}]
    for k in stale:
        print(f"  낡은 목록 {k} — 이제 안 남았다(목록에서 지운다)")
    if not gate:
        return 0
    if bad or stale:
        print(f"❌ 원판 사본 잔존: 신규 {len(bad)} · 낡은 목록 {len(stale)}")
        return 1
    print(f"✅ 원판 사본 {len(items)}곳(전부 알려짐)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
