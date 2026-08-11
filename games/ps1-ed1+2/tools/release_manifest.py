#!/usr/bin/env python3
"""배포용 지문표 — 원본과 결과의 체크섬 넷을 한 번에 뽑는다.

⚠ **받는 사람이 자기 원본이 맞는지 확인할 방법이 있어야 한다.** 우리 웹 패처는 sha1 하나로
게이트를 걸지만, 배포 페이지·릴리스 노트에는 **넷을 다 적는다** — 사람마다 손에 든 도구가
달라서(Flips 는 CRC32, 파일 관리자는 MD5, 우리 패처는 SHA-1) 하나만 적으면 대조를 못 한다.
mcpads 패처들의 배포 저장소가 넷을 다 적는 이유가 이것이다(2026-08-11 흡수).

⚠ 해시는 저작물이 아니라 **지문**이다 — 커밋·공개해도 원본이 복원되지 않는다.

  python3 tools/release_manifest.py            # 원본 + 최종 이미지
  python3 tools/release_manifest.py <파일 …>   # 임의 파일
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, ORIG_BIN, digests  # noqa: E402

FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")


def main(paths):
    if not paths:
        paths = [p for p in (ORIG_BIN, FINAL) if os.path.exists(p)]
    if not paths:
        raise SystemExit("대상이 없다 — 원본도 빌드 산출물도 못 찾았다")
    rows = []
    for p in paths:
        d = digests(p)
        rows.append((os.path.basename(p), d))
        print(f"\n{os.path.basename(p)}")
        print(f"  크기    {d['size']:,} bytes")
        for k in ("crc32", "md5", "sha1", "sha256"):
            print(f"  {k.upper():<7} {d[k]}")
    print("\n─ 붙여 쓸 표 ─\n")
    print("| 파일 | 크기 | CRC32 | MD5 | SHA-1 | SHA-256 |")
    print("| --- | ---: | --- | --- | --- | --- |")
    for name, d in rows:
        print(
            f"| {name} | {d['size']:,} | `{d['crc32']}` | `{d['md5']}` "
            f"| `{d['sha1']}` | `{d['sha256']}` |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
