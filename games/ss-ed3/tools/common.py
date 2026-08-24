"""새턴 『백의 마녀 — 또 하나의 영웅전설』 — 경로·원본 지문·2디스크 계약의 정본.

⚠ **원본은 읽기 전용이다.** 쓰기 계열 헬퍼는 재삽입 설계가 서기 전까지 두지 않는다
(`docs/patcher-checklist.md` 2 — 사전조건 없는 쓰기 경로를 미리 만들지 않는다).

🔴 **두 디스크는 게임 데이터가 같은 한 벌이다**(2026-08-24 실측 — `check_discs()` 가 매번
확인한다). 공통 811 파일이 **전부 바이트 동일**이고, 갈리는 건 무비(`/CPK`)·음성(`/SAP`)·
엔딩 그림(`/END0*.GRP`)뿐이다. 그래서 **번역·재삽입은 한 벌만 만들고 두 장에 같이 쓴다** —
디스크별로 문안을 갈라 들면 두 장이 어긋나는 사고가 난다.
"""

import os
import sys

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(GAME_DIR))
ORIG_DIR = os.path.join(ROOT, "originals", "jp", "ss-ed3")

sys.path.insert(0, ROOT)
from shared.build_tag import build_tag
from shared.disc import MODE1_USER_OFF, Disc, digests

WORK_DIR = os.path.join(GAME_DIR, "work")
OUT_DIR = os.path.join(WORK_DIR, "derived")  # 원본에서 파생 — ⚠ 빌드가 읽는 입력
REVIEW_DIR = os.path.join(WORK_DIR, "review")  # 검토표 — ⚠ 원문 포함, 커밋 금지
BUILD_TAG = build_tag()
BUILD_DIR = os.path.join(WORK_DIR, "build", BUILD_TAG)

# ── 원본 ──────────────────────────────────────────────────────────────────────
# 트랙1 = MODE1/2352 (새턴 ED1+2 와 같다. PS1 합본은 MODE2/2352 라 `user_off` 가 다르다)
USER_OFF = MODE1_USER_OFF

_D = "Shiroki Majo - Mou Hitotsu no Eiyuu Densetsu (Japan) (Disc %d) (Track 1).bin"
DISCS = (1, 2)
DISC_BIN = {n: os.path.join(ORIG_DIR, _D % n) for n in DISCS}

# 입력 지문 — 2026-08-24 실측 (patcher-checklist 1)
SRC = {
    1: {"size": 334_245_072, "sha1": "17de3ba500a6c62cf3755a58dbccf466e3d4479e"},
    2: {"size": 472_293_360, "sha1": "dc71a89a89028cd15c9f7d12fe48d17a0656f974"},
}

# 디스크마다 **있고 없고가 갈리는** 부류 — 전부 매체(무비·음성·음악·엔딩 그림)와
# 디스크 표식이다. 번역 대상은 여기 하나도 없다.
DISC_LOCAL = ("/CPK/", "/SAP/", "/SND/MUS", "/END", "/WW_DISK", "/V20.SAP")


def verify_source(disc, strict=None):
    """원본이 그 덤프인지 확인. 크기가 다르면 즉시, 같으면 sha1 로 확정한다."""
    path = DISC_BIN[disc]
    want = SRC[disc]
    size = os.path.getsize(path)
    if size != want["size"]:
        bad = f"크기 {size:,} (기대 {want['size']:,})"
    else:
        got = digests(path)["sha1"]
        bad = None if got == want["sha1"] else f"sha1 {got} (기대 {want['sha1']})"
    if not bad:
        return
    msg = f"⚠ 원본 불일치: disc{disc} {path}\n  {bad}"
    if strict is False:
        print(msg + "\n  (strict=False — 계속한다)")
    else:
        raise SystemExit(msg)


def open_disc(disc=1, *, verify=True):
    """`Disc` 하나를 연다 — `with common.open_disc(1) as d:` 로 쓴다."""
    if verify:
        verify_source(disc)
    return Disc(DISC_BIN[disc], user_off=USER_OFF)


def is_disc_local(path_in_iso):
    """그 파일이 **디스크마다 있고 없고가 갈리는** 부류인가(매체·표식)."""
    return any(k in path_in_iso for k in DISC_LOCAL)


def check_discs():
    """🔴 2디스크 계약 — 「양쪽에 있는 파일은 바이트 동일하고, 갈리는 건 매체뿐」.

    돌려주는 것: `{"common", "mismatch", "only1", "only2", "unexpected"}`.
      · `mismatch`   — 양쪽에 있는데 내용이 다른 것. **여기가 비어 있어야 한다.**
      · `unexpected` — 한쪽에만 있는데 매체가 아닌 것. 여기도 비어 있어야 한다.

    ⚠ 이 계약이 깨지면 **한 벌만 만든다**는 전제가 무너진다 — 재삽입 설계의 뿌리다.
    그래서 게임 게이트가 이걸 매번 돌린다.
    """
    import hashlib

    snaps = {}
    for n in DISCS:
        with open_disc(n) as d:
            snaps[n] = {
                name: (size, hashlib.sha1(d.read_extent(lba, size)).hexdigest())
                for name, lba, size in d.files()
            }
    a, b = snaps[1], snaps[2]
    common = sorted(set(a) & set(b))
    only1, only2 = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    return {
        "common": len(common),
        "mismatch": [
            (k, f"{a[k][0]:,}B/{a[k][1][:8]} vs {b[k][0]:,}B/{b[k][1][:8]}")
            for k in common
            if a[k] != b[k]
        ],
        "only1": only1,
        "only2": only2,
        "unexpected": [k for k in only1 + only2 if not is_disc_local(k)],
    }


if __name__ == "__main__":
    for n in DISCS:
        verify_source(n)
        print(f"disc{n} ✅ {os.path.basename(DISC_BIN[n])}")
    r = check_discs()
    print(
        f"2디스크 계약 — 공통 {r['common']} · 어긋남 {len(r['mismatch'])} · "
        f"d1 전용 {len(r['only1'])} · d2 전용 {len(r['only2'])} · 뜻밖 {len(r['unexpected'])}"
    )
    for k, why in r["mismatch"][:10]:
        print(f"  ⚠ {k}  {why}")
    for k in r["unexpected"][:10]:
        print(f"  ⚠ 매체가 아닌데 한쪽에만 있다: {k}")
