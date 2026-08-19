#!/usr/bin/env python3
"""패치 스펙이 **공개돼도 되는 모양인가** — [fix] 트랙의 커밋 전 게이트.

**왜.** `patches/*.json` 은 웹 패처 HTML 에 **통째로 인라인돼 공개 배포된다**(publishing.md).
그래서 여기에 원본 바이트가 한 번 새면 그 순간 원저작물 조각을 배포하는 셈이 된다 —
루트 `CLAUDE.md` 「저작권」이 `from` 같은 원본 바이트 필드를 금지하는 이유다. 규칙을 문서로만
두면 샌다(kr 트랙에서 실제로 샜다). 그래서 기계가 본다.

세 축이다. 전부 **0건 유지**가 목표다:

    ① 원본 바이트 필드     `from`·`orig`·`before`·`original` 이 있으면 실패
    ② 스키마               `schema_version` · `patches[].file/offset/to` 가 있나
    ③ 결과 지문            `files[]` 에 sha1 이 붙어 있나 (없으면 엉뚱한 원본에 발라진다)

  python3 games/dos-ed2/tools/check_patches.py
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 🔴 원본 바이트를 담을 법한 이름들. 되살아나면 저작권 규칙 위반이다.
FORBIDDEN = ("from", "orig", "original", "before", "src_bytes")


def main():
    bad_bytes, bad_schema, no_sha = [], [], []
    paths = sorted(glob.glob(os.path.join(ROOT, "patches", "*.json")))
    for p in paths:
        rel = os.path.relpath(p, ROOT)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if "schema_version" not in d:
            bad_schema.append(f"{rel}: schema_version 없음")
        for i, e in enumerate(d.get("patches", [])):
            for k in FORBIDDEN:
                if k in e:
                    bad_bytes.append(f"{rel}#{i}: `{k}`")
            for k in ("file", "offset", "to"):
                if k not in e:
                    bad_schema.append(f"{rel}#{i}: `{k}` 없음")
        files = d.get("files")
        if not files:
            no_sha.append(f"{rel}: files 없음")
        elif isinstance(files, list) and not any(
            isinstance(x, dict) and any("sha" in k for k in x) for x in files
        ):
            no_sha.append(f"{rel}: files 에 sha1 없음")

    print(f"  패치 스펙 {len(paths)}개")
    ok = True
    if bad_bytes:
        ok = False
        print(f"  ❌ **원본 바이트 필드 {len(bad_bytes)}건** — 이 JSON 은 공개 배포된다")
        for x in bad_bytes[:10]:
            print(f"      {x}")
    else:
        print("  ✅ 원본 바이트 필드 없음")
    if bad_schema:
        ok = False
        print(f"  ❌ 스키마 어긋남 {len(bad_schema)}건")
        for x in bad_schema[:10]:
            print(f"      {x}")
    else:
        print("  ✅ 스키마 유효")
    # ⚠ 지문은 **게이트가 아니다** — 진단용 실험 패치(`diag-*`)엔 아직 없는 게 정상이다.
    print(f"  ⚠ 결과 지문 없음 {len(no_sha)}건" if no_sha else "  ✅ 결과 지문 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
