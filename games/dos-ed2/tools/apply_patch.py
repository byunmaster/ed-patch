#!/usr/bin/env python3
"""패치 스펙(JSON)을 게임 디렉터리에 적용/복원한다.

판정은 **파일 전체 sha1** 로 한다 — 스펙의 `files[].sha1_from` 이면 적용 대상,
`sha1_to` 면 이미 적용됨, 둘 다 아니면 중단. 판본이 다른 원본이나 이미 손댄 파일에
덧씌우는 사고를 막기 위해서다.

⚠ 스펙에는 **원본 바이트가 들어 있지 않다**(패치 스키마 v2, gen_patch.py 참조). 그래서
복원은 차분을 되돌리는 게 아니라, 적용할 때 남긴 백업(`<파일>.orig`)에서 되돌린다.
백업이 없으면 originals/ 의 소장본에서 다시 복사하면 된다.

usage:
  apply_patch.py <spec.json> <game_dir>            적용 (백업 <파일>.orig 생성)
  apply_patch.py <spec.json> <game_dir> --revert   백업에서 복원
  apply_patch.py <spec.json> <game_dir> --check    상태만 확인
  apply_patch.py ... --force                       sha1 게이트를 건너뛴다
                                                   (진단 패치를 겹쳐 적용할 때만)
"""

import hashlib
import json
import os
import sys


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def patched(data, items):
    """스펙 항목을 적용한 바이트열을 돌려준다 (원본은 안 건드린다)."""
    out = bytearray(data)
    for p in items:
        off = int(p["offset"], 16) if isinstance(p["offset"], str) else p["offset"]
        to = bytes.fromhex(p["to"].replace(" ", ""))
        out[off : off + len(to)] = to
    return bytes(out)


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        sys.exit(__doc__)
    spec = json.load(open(argv[0], encoding="utf-8"))
    root = argv[1]
    revert = "--revert" in argv
    check = "--check" in argv
    force = "--force" in argv

    if spec.get("schema_version") != 2:
        sys.exit(f"{argv[0]}: 패치 스키마 v2 가 아니다 — gen_patch.py 로 다시 만들어라")

    print(f"# {spec['name']}")
    if spec.get("description"):
        print(f"# {spec['description']}")
    print(f"# 대상: {root}  ({'복원' if revert else '확인' if check else '적용'})")

    meta = {m["file"]: m for m in spec["files"]}
    by_file = {}
    for p in spec["patches"]:
        by_file.setdefault(p["file"], []).append(p)

    changed = 0
    for rel, items in sorted(by_file.items()):
        path = os.path.join(root, rel)
        bak = path + ".orig"
        m = meta.get(rel)
        if m is None:
            sys.exit(f"  !! {rel}: files[] 에 항목이 없다 — 스펙이 깨졌다")
        if not os.path.isfile(path):
            print(f"  !! 없음: {path}")
            continue

        data = read(path)
        h = sha1(data)

        if revert:
            if h == m["sha1_from"]:
                print(f"  = {rel}  이미 원본 — 건너뜀")
                continue
            if not os.path.isfile(bak):
                sys.exit(
                    f"  !! {rel}: 백업({os.path.basename(bak)})이 없어 복원할 수 없다.\n"
                    "     originals/ 소장본에서 이 파일을 다시 복사해라."
                )
            orig = read(bak)
            if sha1(orig) != m["sha1_from"]:
                sys.exit(f"  !! {rel}: 백업이 이 스펙의 원본이 아니다 — 손대지 않고 중단")
            if not check:
                write(path, orig)
                os.remove(bak)
            changed += 1
            print(f"  - {rel}  백업에서 복원")
            continue

        if h == m["sha1_to"]:
            print(f"  = {rel}  이미 적용됨 — 건너뜀")
            continue
        if h != m["sha1_from"] and not force:
            why = "크기 다름" if len(data) != m["size"] else "판본 다름 / 이미 손댄 파일"
            sys.exit(f"  !! {rel}: {why} (sha1 {h[:12]}) — 중단")

        new = patched(data, items)
        if not force and sha1(new) != m["sha1_to"]:
            sys.exit(f"  !! {rel}: 적용 결과가 sha1_to 와 다르다 — 스펙이 깨졌다, 중단")
        n = sum(len(p["to"]) // 2 for p in items)
        if check:
            print(f"  · {rel}  {len(items)}구간 {n}B (미적용)")
            continue
        if not os.path.exists(bak):
            write(bak, data)
        write(path, new)
        changed += 1
        print(f"  + {rel}  {len(items)}구간 {n}B 적용  (백업: {os.path.basename(bak)})")

    if not check:
        print(f"# 파일 {changed}개 {'복원' if revert else '변경'}")


if __name__ == "__main__":
    main()
