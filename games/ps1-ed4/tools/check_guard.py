"""쓰기 가드·실패 처리 검사 — **무변경 구간을 건드리는 빌드가 그 자리에서 멈추고 산출물이 `*.failed` 가 되는가**(체크리스트 2).

    python3 tools/check_guard.py

실제 빌드 통로(`build.build`)로 ① PS-EXE 헤더를 한 바이트 고치는 편집 ② 선언 안 된 파일에 쓰는 편집 ③ 없는 조각을 가리키는 편집 ④ 한 쪽 3줄을 넘는 편집을 각각 굽는다.
넷 다 **실패해야** 하고, ①은 `*.failed` 가 남고 정상 `.bin` 이 없어야 한다. 초록불이 「가드가 있다」가 아니라 「가드가 실제로 막는다」가 되게 한다.
시험 칸(`test-guard`)에서만 돈다 — 끝나면 지운다.
"""

import os
import shutil
import sys

os.environ["ED_BUILD_TAG"] = "test-guard"  # common 을 임포트하기 전에 — 꼬리표가 칸을 정한다
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common

from shared.disc.guard import WriteGuard


def expect_fail(name, edits, exc):
    shutil.rmtree(common.BUILD_DIR, ignore_errors=True)
    try:
        build.build(edits, kind="guard", suffix=" (TEST)")
    except exc as e:
        files = os.listdir(common.BUILD_DIR) if os.path.isdir(common.BUILD_DIR) else []
        return True, f"{type(e).__name__}", files
    return False, "통과해 버렸다", []


def main():
    bad = 0

    # ① 무변경 구간(PS-EXE 헤더) 침범
    def header(exe):
        exe[0x20] ^= 0xFF

    ok, why, files = expect_fail("헤더", {"exe": header}, WriteGuard)
    failed = [f for f in files if f.endswith(".failed")]
    good = [f for f in files if f.endswith(".bin")]
    ok = ok and bool(failed) and not good
    print(
        f"{'✅' if ok else '🔴'} PS-EXE 헤더 침범 → {why} · *.failed {len(failed)} · 정상 .bin {len(good)}"
    )
    bad += not ok
    # ② 선언 안 된 파일(원본 파일 목록의 다른 아카이브 경로가 아니라 허용 목록 밖) — 직접 build 통로의 ALLOWED_WRITES 를 시험한다
    saved = build.ALLOWED_WRITES
    build.ALLOWED_WRITES = [r"/nothing"]
    try:
        ok, why, _ = expect_fail(
            "선언",
            {"exe": lambda exe: exe.__setitem__(common.EXE_HDR + 5, exe[common.EXE_HDR + 5] ^ 1)},
            SystemExit,
        )
    finally:
        build.ALLOWED_WRITES = saved
    print(f"{'✅' if ok else '🔴'} 선언 안 된 파일에 쓰기 → {why}")
    bad += not ok
    # ③ 없는 조각
    ok, why, _ = expect_fail(
        "조각", {"script": {("/O/SC400.DAT", "..\\BIN\\OP00000.BIN"): {9999: [1]}}}, SystemExit
    )
    print(f"{'✅' if ok else '🔴'} 없는 조각 편집 → {why}")
    bad += not ok
    # ④ 한 쪽 3줄 초과 — 넘치는 줄은 화면에서 조용히 사라진다(빌드가 막아야 한다)
    ok, why, _ = expect_fail(
        "쪽", {"script": {("/O/SC400.DAT", "..\\BIN\\OP00000.BIN"): {4: [0x40] * 73}}}, SystemExit
    )
    print(f"{'✅' if ok else '🔴'} 쪽 3줄 초과(조각 4 가 73코드 = 4줄) → {why}")
    bad += not ok
    shutil.rmtree(common.BUILD_DIR, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
