#!/usr/bin/env python3
"""원본/수정본을 바이트 비교해 `apply_patch.py` 용 패치 스펙(JSON)을 만든다.

수정본은 보통 `ne_add_export.py` 같은 도구가 만든다. 그 결과를 배포하려면
원본 전체가 아니라 **차분**만 있으면 되고, 이 리포지토리는 그 차분을
`apply_patch.py` 스펙으로 표현한다. 같은 JSON을 CLI 패쳐와 웹 패쳐가 함께 읽으므로
패치 소스가 하나로 유지된다.

⚠ **스펙에 원본 바이트를 담지 않는다** (패치 스키마 v2). 스펙은 우리가 쓴 값(`to`)과
원본/결과의 sha1 만 담는다 — 이 JSON 은 웹 패처 HTML 에 통째로 인라인돼 공개
배포되므로, 원본 바이트가 들어가면 상용 바이너리 조각을 재배포하는 셈이 된다.
"원본이 맞는지"는 파일 전체 sha1 로 판정하며, 이쪽이 구간 비교보다 오히려 엄격하다.

떨어진 변경은 사이 간격이 `--gap`(기본 16) 이하면 한 덩어리로 합친다.
`to`가 조금 길어지는 대신 항목 수가 줄어 스펙이 읽기 쉬워진다.

usage:
  gen_patch.py --out <spec.json> --name "..." [--label "..."] [--desc "..."] [--issue N] [--gap N] \\
      --diff <게임내 상대경로> <원본> <수정본> [--diff ... ]
"""

import hashlib
import json
import sys


def runs(a: bytes, b: bytes, gap: int):
    """서로 다른 구간을 [(start, end)] 로. 간격이 gap 이하면 병합."""
    if len(a) != len(b):
        sys.exit(f"크기가 다르다: {len(a)} != {len(b)} — 이 스펙 형식은 크기 불변만 다룬다")
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if not diff:
        return []
    out = [[diff[0], diff[0] + 1]]
    for i in diff[1:]:
        if i - out[-1][1] <= gap:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return [tuple(r) for r in out]


def main():
    argv = sys.argv[1:]

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    out = opt("--out")
    name = opt("--name")
    if not out or not name:
        sys.exit(__doc__)
    gap = int(opt("--gap", "16"))

    spec = {"schema_version": 2, "name": name}
    if opt("--label"):
        spec["label"] = opt("--label")  # 디스켓 라벨처럼 좁은 자리에 쓰는 짧은 문구
    if opt("--desc"):
        spec["description"] = opt("--desc")
    if opt("--issue"):
        spec["issue"] = int(opt("--issue"))
    spec["kind"] = "fix"
    spec["files"] = []
    spec["patches"] = []

    idx = [i for i, v in enumerate(argv) if v == "--diff"]
    if not idx:
        sys.exit("--diff 가 최소 하나 필요하다")
    for i in idx:
        rel, orig_p, new_p = argv[i + 1], argv[i + 2], argv[i + 3]
        a = open(orig_p, "rb").read()
        b = open(new_p, "rb").read()
        rr = runs(a, b, gap)
        spec["files"].append(
            {
                "file": rel,
                "size": len(a),
                "sha1_from": hashlib.sha1(a).hexdigest(),
                "sha1_to": hashlib.sha1(b).hexdigest(),
            }
        )
        total = sum(e - s for s, e in rr)
        print(f"{rel}: {len(rr)}개 구간, {total}B ({total * 100 // len(a)}%)")
        for s, e in rr:
            print(f"    {s:#08x}..{e:#08x}  ({e - s}B)")
            spec["patches"].append({"file": rel, "offset": f"{s:#08x}", "to": b[s:e].hex()})

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"# 기록: {out}")


if __name__ == "__main__":
    main()
