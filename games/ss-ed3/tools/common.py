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


def secrets_path():
    """`.local/secrets.env` 를 **위로 올라가며** 찾는다 — 없으면 있을 자리를 돌려준다.

    ⚠ 열쇠는 `.local/` 에 둔다 — 이 레포가 이미 「머신 전용」으로 쓰는 자리이고
    `.gitignore` 에 들어 있다. **새 `.env` 규약을 만들지 않는다.**
    ⚠ **워크트리에는 `.local/` 이 따라오지 않는다** — 워크트리 루트에서 시작해 메인
    트리까지 거슬러 올라간다.
    """
    d = ROOT
    fallback = None
    for _ in range(6):
        p = os.path.join(d, ".local", "secrets.env")
        if os.path.exists(p):
            return p
        if fallback is None and os.path.isdir(os.path.join(d, ".local")):
            fallback = p
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return fallback or os.path.join(ROOT, ".local", "secrets.env")


def secret(name):
    """바깥 서비스 열쇠 — **환경변수 → `.local/secrets.env`** 순. 없으면 빈 문자열.

    열쇠가 느는 자리가 이미 둘이다(`DEEPL_API_KEY` · `GEMINI_API_KEY`). 도구마다 읽는
    법을 따로 쓰면 곧 갈리므로 여기 하나로 둔다.
    ⚠ 값을 로그·오류 메시지에 찍지 않는다 — 있는지 없는지만 말한다.
    """
    v = os.environ.get(name)
    if v:
        return v
    p = secrets_path()
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def need_secret(name, how):
    """없으면 **어디에 어떻게 두는지** 알려주고 멈춘다."""
    v = secret(name)
    if v:
        return v
    raise SystemExit(
        f"{name} 가 없다. 둘 중 하나로 준다:\n"
        f"  ① {secrets_path()} 에\n"
        f"       {name}=여기에키\n"
        "     (`.local/` 은 gitignore 라 커밋되지 않는다. 권한은 600 으로)\n"
        f"  ② {name}=... 로 환경변수\n"
        f"  ⓘ {how}"
    )


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

# 🔴 **디스크는 트랙이 여럿이고, 디스크2 는 ISO 가 트랙 1 을 넘어간다**(실측 2026-08-28).
#    disc2 트랙1 은 200,805 섹터인데 파일 18 개(`END00~16.GRP` · `V20.SAP` 45.9MB)의 LBA 가
#    그 너머다 — **트랙 2 를 빼면 엔딩 그림과 그 음성이 통째로 없다.** 트랙1 만 담은 `.cue`
#    로 여태 구웠고, 타이틀·초반만 봐서 안 드러났다.
#    ⚠ 우리가 고치는 것은 **트랙 1 뿐**이므로 나머지는 원본을 그대로 복사해 옆에 둔다.
_TRACKS = {  # 디스크 → [(트랙 번호, 모드, 파일명 꼬리)]
    1: [(1, "MODE1/2352", "(Track 1)"), (2, "AUDIO", "(Track 2)")],
    2: [(1, "MODE1/2352", "(Track 1)"), (2, "MODE2/2352", "(Track 2)"), (3, "AUDIO", "(Track 3)")],
}
_DT = "Shiroki Majo - Mou Hitotsu no Eiyuu Densetsu (Japan) (Disc %d) %s.bin"


#   🔴 **`/MAP/MAP077.FON` 을 넣었다가 뺐다 — 엔진이 닿을 수 없는 자료다**(2026-08-29).
#     2026-08-28 에 「`MAP077.BIN` 이 껍데기고 대사가 `.FON` 에 있다」고 보고 파이프라인에
#     넣었는데, **틀렸다.** 근거 셋:
#       ① `MAP077.BIN` 은 껍데기가 아니다 — 맵 이름 `弐章`, 포인터 **37/37 이 다 살아 있다**.
#       ② **모든 맵의 포인터는 자기 `.BIN` 안에만 있다**(88 맵 전수, 밖을 가리키는 것 0).
#          `MAP077.BIN` 은 최대 `0x1F68` / 크기 `0x1F6C` 다 — `.FON` 에 닿을 길이 없다.
#       ③ `.FON` 쪽 문안은 `MAP001`(서장 오르골 장면)의 **바이트가 끼어든 사본**이다 —
#          `MAP001` 이 `82 b5 [82 c8] 82 ad` 인 자리가 `82 b5 [82 79 c8] 82 ad` 로,
#          전각 문자의 앞뒤 바이트 사이에 한 바이트가 끼어 있다(여러 자리에서 같은 꼴).
#     ⇒ **개발 중 남은 죽은 자료**다. 옮겨도 화면에 안 나오고, 쓰면 챕터 2 맵의 그래픽
#       파일에 1,147 바이트를 공연히 쓴다. **다시 넣지 마라.**
#     ⓘ 예외 장치 자체는 남겨 둔다 — 다음에 진짜 예외가 나오면 여기 한 줄이면 된다.
MAP_EXTRA = {}


def is_map_file(name):
    """대사 맵인가 — `(맵인가, 꼬리표)`. 꼬리표가 `script/<꼬리표>.json` 이 된다."""
    if name in MAP_EXTRA:
        return True, MAP_EXTRA[name]
    if name.startswith("/MAP/") and name.endswith(".BIN"):
        return True, os.path.basename(name)[:-4]
    return False, None


def disc_tracks(disc):
    """`[(번호, 모드, 원본 경로)]` — 트랙 1 이 늘 첫 항목이다."""
    return [(n, m, os.path.join(ORIG_DIR, _DT % (disc, tail))) for n, m, tail in _TRACKS[disc]]


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
