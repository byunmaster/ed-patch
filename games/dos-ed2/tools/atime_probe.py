#!/usr/bin/env python3
"""파일 접근시간(atime)으로 게임이 실제로 어떤 SCENA DLL을 로드했는지 추적한다.

DOSBox-X의 `-log-fileio`가 이 빌드에서 아무것도 찍지 않아서 쓰는 우회 수단.
호스트 디렉터리 마운트라 게임의 파일 읽기가 그대로 호스트 open()이 되고,
APFS는 atime을 갱신하므로 실행 전후를 비교하면 로드된 파일과 대략의 순서가 나온다.

usage:
  atime_probe.py reset  <game_dir>   모든 대상 파일 atime을 과거로 밀어놓는다
  atime_probe.py report <game_dir>   reset 이후 접근된 파일을 시간순으로 출력
"""

import datetime as dt
import os
import sys

# 과거로 밀어둘 기준 시각 (이보다 나중이면 "이번 실행에서 접근됨")
EPOCH = dt.datetime(2000, 1, 1, 0, 0, 0, tzinfo=dt.UTC)

# 세이브는 실행 중 게임이 쓰므로 제외 — 노이즈만 된다
SKIP_DIRS = {"SAVE"}


def targets(root):
    """게임 디렉터리 전체를 재귀적으로 훑는다(SAVE 제외)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d.upper() not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            p = os.path.join(dirpath, name)
            if os.path.isfile(p):
                yield p


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, root = sys.argv[1], sys.argv[2]
    ts = EPOCH.timestamp()

    if cmd == "reset":
        n = 0
        for p in targets(root):
            st = os.stat(p)
            os.utime(p, (ts, st.st_mtime))  # atime만 과거로, mtime은 보존
            n += 1
        print(f"{n}개 파일 atime을 {EPOCH:%Y-%m-%d %H:%M:%S}로 초기화했다.")
        print("이제 게임을 실행해 크래시를 재현한 뒤 `report`를 돌려라.")
        return

    if cmd == "report":
        hits = []
        for p in targets(root):
            at = os.stat(p).st_atime
            if at > ts + 1:
                hits.append((at, p))
        hits.sort()
        if not hits:
            print("접근된 파일 없음 — reset을 안 했거나 게임이 실행되지 않았다.")
            return
        print(f"이번 실행에서 접근된 파일 {len(hits)}개 (시간순):")
        base = hits[0][0]
        for at, p in hits:
            rel = os.path.relpath(p, root)
            stamp = dt.datetime.fromtimestamp(at, tz=dt.UTC).astimezone()  # 로컬 시각으로 표시
            print(f"  +{at - base:7.2f}s  {stamp:%H:%M:%S}  {rel}")
        return

    sys.exit(__doc__)


if __name__ == "__main__":
    main()
