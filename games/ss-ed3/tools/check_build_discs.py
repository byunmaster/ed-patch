"""빌드 이미지가 **지금 소스**의 것이고, **두 장이 같은 세대**인가.

🔴 **실제로 물렸다**(유저 실측 2026-08-28). `build.py` 는 두 장을 차례로 굽는데, 굽는
**도중에** 소스를 고치면 앞장만 낡은 채로 남는다 — disc2 가 23:04, disc1 이 23:06 이었고
그 사이에 말풍선 폭 수정이 들어가 **disc2 만 한 판 뒤처졌다.** 빌드는 성공했고, 게이트도
초록이었고, `pull-build.sh` 는 「변경없음」이라고 정확히 보고했다. **아무도 안 울었다.**

⚠ 이건 「한 장만 구우면 원문으로 돌아간다」(루트 CLAUDE.md)의 변종이다 — 두 장을 다
구웠는데도 갈린다. 사람이 눈으로 시각을 비교해야만 잡히던 것을 여기서 자동으로 잡는다.

**보는 것 둘**

1. **세대** — 지금 소스로 `build.patched()` 를 다시 돌려 나온 바이트가 이미지 안의 것과
   같은가. 다르면 그 이미지는 **낡았다**(두 장이 사이좋게 같이 낡은 경우도 잡힌다).
2. **일치** — 두 장에 다 있는 파일이 서로 같은가. 게임 데이터가 한 벌이라(`check_discs`)
   패치 결과도 한 벌이어야 한다.

⚠ **이미지가 없으면 건너뛴다.** 원본만 링크하고 아직 안 구운 트리에서 늘 빨간불이 되면
아무도 안 본다(루트 CLAUDE.md 「게이트는 지금 고칠 수 있는 것만 실패로 친다」).

    python3 games/ss-ed3/tools/check_build_discs.py
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import build
import common as C

from shared.disc.iso9660 import SECTOR, USER_SIZE


def read_extent(path, lba, size):
    """구운 이미지(MODE1/2352)에서 파일 하나를 읽는다."""
    out = bytearray()
    with open(path, "rb") as f:
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            f.seek((lba + i) * SECTOR + C.USER_OFF)
            out += f.read(USER_SIZE)
    return bytes(out[:size])


def sha(b):
    return hashlib.sha1(b).hexdigest()


def survey(disc):
    """`(이미지 경로, {이름: (기대 sha, 실제 sha)})` — 이미지가 없으면 `(None, None)`."""
    path = build.out_paths(disc)[0]
    if not os.path.exists(path):
        return None, None
    got = {}
    for name, lba, size, _old, new, _cnt in build.patched(disc):
        #   ⓘ 음성 자막이 붙은 맵은 `size` 가 원본보다 길다(섹터 여백에 꼬리) — 그 길이로 읽는다
        got[name] = (sha(new), sha(read_extent(path, lba, size)))
    return path, got


def main():
    n_img = 0
    stale = []
    per_disc = {}
    for disc in C.DISCS:
        _path, got = survey(disc)
        if got is None:
            print(f"   disc{disc} — 이미지가 없다 (건너뛴다)")
            continue
        n_img += 1
        per_disc[disc] = got
        bad = [n for n, (want, have) in got.items() if want != have]
        if bad:
            stale.append((disc, bad))
            print(f"   🔴 disc{disc} 는 낡았다 — 지금 소스와 다른 파일 {len(bad)}")
            for n in bad[:5]:
                print(f"        {n}")
        else:
            print(f"   disc{disc} ✅ 지금 소스의 것 (패치 파일 {len(got)})")

    if n_img == 0:
        print("   ⓘ 구운 이미지가 없다 — 이 검사는 건너뛴다")
        return 0

    #   두 장 대조 — 게임 데이터가 한 벌이니 패치 결과도 한 벌이어야 한다.
    if len(per_disc) == 2:
        a, b = (per_disc[d] for d in sorted(per_disc))
        #   ⓘ ISO 구조(PVD · 디렉터리)는 장마다 다른 게 맞다 — 옮긴 맵의 새 자리가 트랙 1
        #     끝이라 두 장에서 LBA 가 다르고, 디스크 2 는 트랙 2 파일 레코드까지 민다(relocate.py).
        common = {n for n in set(a) & set(b) if n != "PVD" and not n.startswith("디렉터리")}
        split = sorted(n for n in common if a[n][1] != b[n][1])
        if split:
            print(f"   🔴 두 장이 갈렸다 — 공통 {len(common)} 중 {len(split)}")
            for n in split[:5]:
                print(f"        {n}")
            stale.append(("두 장", split))
        else:
            print(f"   두 장 ✅ 같은 세대 (공통 패치 파일 {len(common)})")
    elif n_img == 1:
        #   ⚠ 실패로 치지 않는다 — 확인용으로 한 장만 굽는 건 정상 절차다(`--disc`).
        print("   ⚠ 한 장만 구워져 있다 — 배포 전에는 두 장을 다 굽는다")

    if stale:
        print("\n   ⇒ `python3 games/ss-ed3/tools/build.py` 로 다시 굽는다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
