#!/bin/sh
# 게임별 워크트리를 연다 — 플랫폼 병행의 진입점.
#
# ⚠ **무엇을 병행하는가**(유저 확정 2026-08-18): 롬분석·기계번역처럼 **사람 판정이 안 걸리는**
#   기계 작업만 다른 트리로 뺀다. 정발 대조·QA 는 직렬이라 트리를 늘려도 안 빨라진다 —
#   손이 나뉠 뿐이다. 본 트리는 지금 굴리는 타이틀(ps1-ed1+2)이 잡는다.
#
#   sh scripts/worktree.sh ps1-ed1+2        # 열기(없으면 만든다)
#   sh scripts/worktree.sh --list
#
# ⚠ **`originals/` 는 gitignore 라 워크트리에 안 따라온다.** 심볼릭 링크로 이어야 도구가
#   원본을 찾는데, `originals/README.md` 가 추적되는 파일이라 디렉터리 자체는 이미 있으니
#   **통째로 걸면 `originals/originals` 가 된다** — 반드시 그 안에 건다. 이 스크립트가
#   대신한다(손으로 하면 매번 틀린다).
#
# ⚠ **그 게임이 읽는 것만 건다** — 목록은 `games/<게임>/originals.txt`(유저 요청 2026-08-18).
#   지역을 통째로 걸면 딴 게임 원본이 그 트리에서 보이는데, 도구가 엉뚱한 걸 읽어도
#   **빌드는 통과한다.** 조용히 틀리는 쪽이라 좁혀 둔다. 목록이 없으면 **안 건다** —
#   지금 못 찾는 게, 나중에 딴 걸 읽는 것보다 낫다.
#
# ⚠ `vendor/` · `.emucap/` 도 같은 이유로 안 따라온다 — 필요한 트랙에서만 잇는다.
#
# 왜 워크트리인가: `work/` 가 갈려 빌드가 안 섞이고, `BUILD_TAG`(=브랜치)로 이미지도 안
# 덮인다. 게임끼리는 디스크 이미지가 달라 겹칠 일이 없다(⚠ ED1/ED2 는 **합본이라 예외** —
# 같은 이미지라 한 트리에서 굴린다, `games/ps1-ed1+2/CLAUDE.md`).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR="$ROOT/.claude/worktrees"
# ⚠ 도구는 레포 `.venv` 로 돈다(numpy·PIL·fontTools). 워크트리엔 `.venv` 가 없고, 스톡
#   `python3` 로 돌리면 빌드 한복판에서 `ModuleNotFoundError` 로 죽는다 — 안내부터 맞춘다.
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

if [ "${1:-}" = "--list" ]; then
  git -C "$ROOT" worktree list
  exit 0
fi

# `--shared` — **공용(main) 쪽을 빼낸다.** 게임 트리를 워크트리로 옮기는 것보다 이쪽이 싸다:
# 공용 편집(shared · scripts · skills · docs)은 **원본도 파생물도 빌드도 필요 없다.**
# 무거운 쪽(게임: originals 링크 · derived 14M · 빌드 이미지 2GB)은 본 트리에 그대로 둔다.
# ⚠ 이걸 안 쓰면 공용을 고칠 때마다 본 트리의 브랜치를 갈아타게 되는데, 그 트리에서 다른
#   세션(에이전트 포함)이 파일을 읽고 있으면 **바뀐 파일을 읽고도 성공한다**(2026-08-18 실제로
#   백그라운드 에이전트 셋이 도는 중에 갈아탔다).
if [ "${1:-}" = "--shared" ]; then
  WT="$DIR/shared"
  if [ -d "$WT" ]; then
    echo "이미 있다: $WT"
  else
    mkdir -p "$DIR"
    git -C "$ROOT" worktree add --detach "$WT" main
    git -C "$WT" switch main 2>/dev/null || git -C "$WT" checkout main
    echo "만들었다: $WT  (브랜치 main)"
  fi
  ln -sfn "$ROOT/.venv" "$WT/.venv" && echo "  .venv 연결(테스트가 여기서 돈다)"
  # 공용 트리는 **전 게임의 회귀 테스트**를 돌리는 자리라 각 게임이 선언한 원본이 필요하다
  # (링크라 비용은 0). 게임 트리와 달리 좁히지 않는 이유가 이것이다.
  for man in "$ROOT"/games/*/originals.txt; do
    [ -f "$man" ] || continue
    sed 's/#.*//' "$man" | tr -d ' \t' | while IFS= read -r item; do
      [ -n "$item" ] || continue
      [ -e "$ROOT/originals/${item%/}" ] || continue
      mkdir -p "$(dirname "$WT/originals/${item%/}")"
      ln -sfn "$ROOT/originals/${item%/}" "$WT/originals/${item%/}"
    done
  done
  echo "  originals 연결(게임들이 선언한 것만)"
  # `work/derived` 도 잇는다 — 회귀 테스트 하나가 JP 덤프를 읽는다. 게임 트리와 달리
  # **복사가 아니라 링크**다: 공용 트리는 빌드를 안 하니 쓰기 충돌이 없고, 링크라야 게임
  # 쪽이 다시 뜬 덤프를 그대로 본다. (⚠ 그래서 여기서 빌드를 돌리면 안 된다.)
  for d in "$ROOT"/games/*/work/derived; do
    [ -d "$d" ] || continue
    g=$(basename "$(dirname "$(dirname "$d")")")
    mkdir -p "$WT/games/$g/work"
    dst="$WT/games/$g/work/derived"
    # ⚠ **대상이 실물 디렉터리면 링크가 그 안으로 들어간다**(`derived/derived`). 오늘
    #   `originals/originals` 로 한 번 겪은 함정과 같은 것이다. 심볼릭 링크면 갱신하고,
    #   실물이면 **덮지 않고 알린다**(생성물이라도 지우는 판단은 사람이 한다).
    if [ -L "$dst" ] || [ ! -e "$dst" ]; then
      ln -sfn "$d" "$dst"
      echo "  games/$g/work/derived 연결(읽기용)"
    else
      echo "  ⚠ games/$g/work/derived 가 실물 디렉터리다 — 링크하지 않았다(지우고 다시 돌려라)"
    fi
  done
  # 🔴 **허브(main 트리)도 파생물을 봐야 한다** — 회귀 테스트 하나가 JP 덤프를 읽는다.
#    배치를 뒤집어 본 트리가 main 이 되면(유저 확정 2026-08-18) 그 트리엔 `work/` 가 없다.
#    게임 트리 것을 **링크로** 되비춘다(쓰는 쪽은 게임 트리 하나뿐이라 충돌이 없다).
# 🔴 **`build` 도 같이 잇는다**(2026-08-19). `scripts/pull-build.sh` 는 **허브 경로**를 보는데
#    빌드는 워크트리 안에 생긴다 — 유저가 QA 이미지를 받으려다 「원격에 꼬리표가 없다」로
#    막혔고, 허브에 남아 있던 **8/18 낡은 이미지**를 대신 받을 뻔했다(이 레포의 1급 사고).
HUB="$ROOT/games/$GAME/work"
for sub in derived build; do
  [ -d "$WT/games/$GAME/work/$sub" ] || continue
  mkdir -p "$HUB"
  if [ -L "$HUB/$sub" ] || [ ! -e "$HUB/$sub" ]; then
    ln -sfn "$WT/games/$GAME/work/$sub" "$HUB/$sub"
    echo "  (허브) games/$GAME/work/$sub → 워크트리 것을 본다"
  else
    echo "  ⚠ 허브에 실물 games/$GAME/work/$sub 가 있다 — 링크하지 않았다(지우고 다시 돌려라)"
  fi
done

cat <<EOF

다음:
  cd $WT          # ← 공용은 여기서만 고친다
  sh scripts/test.sh

⚠ 여기선 **빌드를 돌리지 않는다** — 원본도 파생물도 없다. 게임 검증은 본 트리에서.
EOF
  exit 0
fi

GAME="${1:-}"
[ -n "$GAME" ] || { echo "쓰기: sh scripts/worktree.sh <게임>   (예: ps1-ed1+2)"; exit 2; }

BR="game/$GAME"
WT="$DIR/$GAME"

if [ -d "$WT" ]; then
  echo "이미 있다: $WT"
else
  mkdir -p "$DIR"
  if git -C "$ROOT" show-ref --quiet "refs/heads/$BR"; then
    git -C "$ROOT" worktree add "$WT" "$BR"
  else
    git -C "$ROOT" worktree add -b "$BR" "$WT"
  fi
  echo "만들었다: $WT  (브랜치 $BR)"
fi

# originals — 그 게임이 선언한 것만 건다
# ⚠ **워크트리 것을 먼저 본다** — 목록은 게임 소유라 게임 브랜치가 갱신한다.
#   main 것만 보면 게임이 원본을 하나 더 쓰게 됐을 때 조용히 안 걸린다.
MAN="$WT/games/$GAME/originals.txt"
[ -f "$MAN" ] || MAN="$ROOT/games/$GAME/originals.txt"
if [ -f "$MAN" ]; then
  # 주석(`#`)과 빈 줄을 걷고 `<지역>/<타이틀>` 만 남긴다
  sed 's/#.*//' "$MAN" | tr -d ' \t' | while IFS= read -r item; do
    [ -n "$item" ] || continue
    src="$ROOT/originals/${item%/}"
    if [ ! -e "$src" ]; then
      echo "  ⚠ originals/${item%/} 없음 — 소장본을 채우고 다시 돌린다"
      continue
    fi
    mkdir -p "$(dirname "$WT/originals/${item%/}")"
    ln -sfn "$src" "$WT/originals/${item%/}"
    echo "  originals/${item%/} 연결"
  done
else
  cat <<EOF
  ⚠ games/$GAME/originals.txt 가 없어 **원본을 하나도 안 걸었다**.
     그 게임이 읽는 원본을 한 줄에 하나씩 적는다 (예: jp/$GAME).
     지역을 통째로 걸지 않는 이유는 이 스크립트 머리말에 있다.
EOF
fi
# 🔴 `work/derived/` — **빌드가 읽는 입력**이다(산출물이 아니다). 새 워크트리엔 없어서
#    빌드가 그냥 죽는다(실측: `derived/align/ED2_SCN2.json` 없음). 그중 의미정렬 제안
#    `align/*.json` 은 **비결정적**이라 그 자리에서 다시 만들면 안 된다 — 머신이 다르면
#    다른 배정이 나온다(제1 원칙, 루트 CLAUDE.md). 그래서 **본 트리 것을 복사**한다.
#    ⚠ 링크가 아니라 복사다 — 빌드가 여기에 쓰기 때문에(덤프 갱신) 두 트리가 섞이면 안 된다.
SRC_DERIVED="$ROOT/games/$GAME/work/derived"
DST_DERIVED="$WT/games/$GAME/work/derived"
# ⚠ **허브는 파생물의 주인이 아니라 거울이다**(배치를 뒤집은 뒤로 — 본 트리 = main).
#   허브 쪽이 심볼릭 링크면 그건 이 워크트리를 되비추는 것이라, 복사하면 **자기를 자기에게
#   복사**하게 된다(실측 2026-08-18: 그렇게 44K 짜리 반쪽 사본이 생겼다).
if [ -L "$SRC_DERIVED" ]; then
  echo "  work/derived — 허브가 이 트리를 되비추고 있다(복사 안 함)"
elif [ -d "$SRC_DERIVED" ]; then
  # ⚠ **없는 것만 채운다**(`-n`) — 실패한 빌드가 덤프를 일부 만들어 둔 상태로도 돌아야 하고,
  #   이 트리가 이미 만든 것을 본 트리 것으로 덮어쓰면 안 된다.
  mkdir -p "$DST_DERIVED"
  cp -an "$SRC_DERIVED/." "$DST_DERIVED/" 2>/dev/null || true
  echo "  work/derived 채움 ($(du -sh "$DST_DERIVED" | cut -f1)) — 빌드가 읽는 입력이다"
elif [ ! -d "$DST_DERIVED" ]; then
  echo "  ℹ work/derived 없음 — 아직 파생 단계가 없는 게임이다(롬분석·기계번역엔 필요 없다)"
fi

# ⚠ `.venv` 는 워크트리에 안 따라온다 — `check.sh`·`test.sh` 가 `$ROOT/.venv` 를 찾는다.
#   없으면 스톡 python3 로 떨어져 빌드 한복판에서 죽는다(실측 2026-08-18: 빌드는 직접
#   돌리면 되는데 `check.sh` 만 실패해 원인이 안 보였다).
[ -e "$ROOT/.venv" ] && ln -sfn "$ROOT/.venv" "$WT/.venv" && echo "  .venv 연결"

# 읽기 전용 서드파티 — 있으면 잇는다
for d in vendor .emucap; do
  [ -e "$ROOT/$d" ] && ln -sfn "$ROOT/$d" "$WT/$d" && echo "  $d 연결"
done

cat <<EOF

다음:
  cd $WT
  $PY games/$GAME/tools/build.py      # 원본이 보이는지부터
  sh scripts/check.sh

⚠ 이 워크트리에서는 **자기 games/$GAME/ 만** 만진다.
   \`shared/\` · \`scripts/\` · \`.claude/skills/\` · \`docs/\` 는 **main 에서** 고치고 받아 온다 —
   여기서 고치면 다른 게임의 조판이 조용히 바뀐다(조판 지문이 잡지만, 그건 사후다).
EOF
