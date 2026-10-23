"""화면 글 출처 커버리지 — **디스크를 직접 훑어** 일본어 SJIS 글이 남은 자리를 센다(어댑터 목록이 아니라 본물 계측).

어댑터(`names_corpus.pairs()`)가 낸 목록은 「우리가 아는 출처」일 뿐이라, 모르는 출처는 이름 검사·화면 일본어 게이트
둘 다 못 본다(ps1-ed3 월드맵 지명이 그랬다 — 검사기 분모 밖). 이 도구는 원본 이미지의 비압축 구간(프로그램·표·모듈)에서
SJIS 글(가나가 든 4자 이상 런)을 찾고, **빌드 산출물의 같은 자리가 그대로인가**(= 일본어가 화면에 남는다)를 본 뒤,
그 글이 `pairs()` 원문에 들어 있는지(=게이트가 아는 출처인지)를 가른다.

    python3 games/pce-ed1/tools/coverage_scan.py [--iso <빌드 이미지>] [--list]     # → work/review/coverage.md

씬·전투 컨테이너(LZ 압축)는 훑지 않는다 — `pairs()` 의 `scn`·`battle` 이 이미 전량이다. ADPCM(rel 1750~)도 뺀다.
"""

import argparse
import re
import sys
from pathlib import Path

import common
import names_corpus

SCAN = (0, 1750)
SKIP = ((162, 210), (1252, 1684))  # 전투·씬 컨테이너 — pairs 가 전량
KANA = re.compile("[ぁ-ヺー]")
JPCH = re.compile("[ぁ-ヺー-ヿ㐀-鿿ｦ-ﾟ]")


def user_bytes(iso: bytes, rel: int, n: int) -> bytes:
    out = []
    for i in range(n):
        a = (common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF
        out.append(iso[a : a + common.USER])  # ⚠ `iso[a:][:n]` 은 뒷부분 600MB 를 매번 복사한다
    return b"".join(out)


def runs(buf: bytes, min_chars: int = 4):
    """가나가 하나라도 든 SJIS 2바이트 런(전각 글자만) → (오프셋, 글)."""
    i, n = 0, len(buf)
    while i < n - 1:
        j = i
        while (
            j + 1 < n
            and (0x81 <= buf[j] <= 0x9F or 0xE0 <= buf[j] <= 0xEA)
            and 0x40 <= buf[j + 1] <= 0xFC
        ):
            j += 2
        if (j - i) // 2 >= min_chars:
            try:
                s = buf[i:j].decode("cp932")
            except UnicodeDecodeError:
                s = ""
            if s and KANA.search(s) and len(JPCH.findall(s)) >= min_chars:
                yield i, s
            i = j
        else:
            i += 2 if j > i else 1


BASELINE = common.GAME_DIR / "script" / "coverage_baseline.json"
MIN_CHARS = 4  # 문장 영역 최소 런 길이 — 「…が現れた」 11자·「ありがとう」 5자·「が現れた」 4자가 다 걸린다(합성 테스트). 그래픽·코드 잡음은 기준선이 받는다.


def category(rel: int, in_corpus: bool) -> str:
    """안 바뀐 일본어 런의 부류 — 구역으로 가른다(실측 10-08·10-18). 기준선에 부류를 함께 적는다."""
    if rel == 0:
        return "헤더 저작권 문구(화면에 안 뜸)"
    if 210 <= rel < 322:
        return "씬 평문 사본(엘아스타 적재에서 안 읽힘 — 죽은 사본 가능성, 한 흐름 한정)" if in_corpus else "씬 평문 사본의 깨진 조각"
    if rel == 57 and in_corpus:
        # 시스템 문구 표 앞쪽 사본(뱅크 0x6D+0x182F~) — 코드가 가리키는 건 뒤쪽 사본(+0x1A0B~, sysbuild 가 번역)뿐이다
        # (`sysstrings.bank6d_refs()` 137개 중 앞쪽 시작 주소 0건 — 정적 근거, 실행 실측은 못 했다)
        return "죽은 사본(코드 참조 없음 — 정적)"
    if in_corpus:
        return "코퍼스에 있으나 안 바뀜(화면 문장 후보 — 미판정: rel 85 · 1142 · 1222~1235)"
    return "코드·글꼴·그림 데이터의 우연한 SJIS(화면 글 아님)"


def check(rows, baseline: dict) -> list[tuple]:
    """기준선에 없는 런(= 새로 일본어가 남은 자리)."""
    known = {(r, o) for r, o, *_ in baseline.get("runs", [])}
    return [r for r in rows if (r[0], r[1]) not in known]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="기준선에 없는 안 바뀐 일본어 런이 있으면 실패(check.sh)")
    ap.add_argument("--freeze", action="store_true", help="지금 결과를 기준선으로 박는다")
    ap.add_argument("--iso", default=str(common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    orig = common.iso_bytes()
    built = Path(a.iso).read_bytes()
    corpus = " ".join(jp for _w, jp, _o, *_ in names_corpus.pairs() if isinstance(jp, str))
    rows = []
    for rel in range(*SCAN):
        if any(lo <= rel < hi for lo, hi in SKIP):
            continue
        o, b = user_bytes(orig, rel, 1), user_bytes(built, rel, 1)
        for off, s in runs(o, MIN_CHARS):
            same = b[off : off + 2 * len(s)] == o[off : off + 2 * len(s)]
            if same:
                rows.append((rel, off, s, s in corpus))
    left = rows
    inn = [r for r in left if r[3]]
    out = [r for r in left if not r[3]]
    lines = [
        "# 화면 글 출처 커버리지 (디스크 직접 훑기)",
        "",
        (
            f"비압축 구간 rel {SCAN[0]}~{SCAN[1] - 1}(전투·씬 컨테이너 제외)에서 **빌드가 안 바꾼 일본어 런** {len(left)}개 — "
            f"코퍼스(`pairs()` 원문)에 있음 {len(inn)} · **없음 {len(out)}**."
        ),
        "",
        "| rel | 오프셋 | 글 | 코퍼스 |",
        "|---|---|---|---|",
    ]
    for rel, off, s, ok in left:
        lines.append(f"| {rel} | 0x{off:03X} | {s} | {'O' if ok else '✗'} |")
    p = common.REVIEW_DIR / "coverage.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"빌드가 안 바꾼 일본어 런 {len(left)} — 코퍼스에 있음 {len(inn)} · 없음 {len(out)}  → {p}"
    )
    if a.list:
        for rel, off, s, _ok in out:
            print(f"  ✗ rel {rel} +0x{off:03X} {s}")
    import collections
    import json

    cats = collections.Counter(category(r, ok) for r, _o, _s, ok in left)
    for c, n in cats.most_common():
        print(f"  {n:4d}  {c}")
    if a.freeze:
        BASELINE.write_text(
            json.dumps(
                {
                    "_doc": "coverage_scan 기준선 — 빌드가 안 바꾼 일본어 런의 (rel, 오프셋, 부류). 글은 안 적는다(원문). 새 런이 생기면 check.sh 가 실패한다 — 번역으로 없애거나 사유와 함께 올린다.",
                    "runs": [[r, o, category(r, ok)] for r, o, _s, ok in left],
                },
                ensure_ascii=False,
                indent=0,
            )
            + "\n",
            "utf-8",
        )
        print(f"기준선 {len(left)}런 → {BASELINE}")
    if a.check:
        new = check(left, json.loads(BASELINE.read_text("utf-8")) if BASELINE.exists() else {})
        if new:
            for rel, off, s, ok in new:
                print(f"  🔴 새 런 rel {rel} +0x{off:03X} {s}")
            print(f"기준선 밖 안 바뀐 일본어 런 {len(new)} — 화면에 일본어가 남는다")
            return 1
        print(f"안 바뀐 일본어 런 {len(left)} 전부 기준선 안(새 런 0)")


if __name__ == "__main__":
    sys.exit(main())
