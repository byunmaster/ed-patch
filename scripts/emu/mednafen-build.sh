#!/bin/sh
# 창 크기 단축키가 든 mednafen 을 만든다 (유저 요청 2026-09-07).
#
#     sh scripts/emu/mednafen-build.sh          # 없거나 패치가 바뀌었으면 빌드
#     sh scripts/emu/mednafen-build.sh --force  # 무조건 다시
#     sh scripts/emu/mednafen-build.sh --check  # 상태만 본다
#
# `emu.sh` 가 실행 직전에 이 바이너리를 먼저 찾고, 없으면 시스템 mednafen 으로 간다 —
# 그때는 창 크기 명령이 없어 `--size` 인자만 듣는다(설정으로 크기를 정하고 띄운다).
#
# ⚠ **왜 따로 빌드하나** — 스톡 mednafen 에는 **창 크기 명령이 아예 없다**(전체화면 토글뿐).
#   ⌥-·⌥+ 를 쓰려면 명령을 소스에 더해야 한다 — `scripts/emu/mednafen-winsize.patch`.
#   ⚠ 숫자(⌘1~4)는 안 된다 — mednafen 기본이 1~9 를 세이브 슬롯 선택에 물려 두어 그쪽이 먼저 먹는다.
#   emucap 어댑터 쪽에 얹을 수는 없다: 그 빌드는 패치셋 sha256 을 `upstream.lock` 으로
#   검증하므로 우리 패치를 더하면 **빌드가 거부된다**. 그리고 `vendor/` 는 읽기 전용이다.
#   ⇒ **순정 타르볼을 따로 풀어** 우리 패치만 얹는다. emucap 어댑터는 그대로 두고,
#   이건 **유저가 직접 플레이할 때 쓰는 바이너리**다(세션 자동 조작은 emucap 것을 쓴다).
#
# ⚠ **패치 지문을 남긴다** — 패치를 고쳤는데 실행 파일이 옛것이면 조용히 안 먹는다.
#   np2kai 에서 실제로 물렸다(설치기가 실행 파일이 있으면 안 돌아서, 새 패치가 안 들어갔다).
set -e

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PATCH="$ROOT/scripts/emu/mednafen-winsize.patch"
OUT="$ROOT/.local/cache/mednafen"
BIN="$OUT/bin/mednafen"
STAMP="$OUT/.patch.sha1"

VER=1.32.1
SHA=de7eb94ab66212ae7758376524368a8ab208234b33796625ca630547dbc83832
URL="https://mednafen.github.io/releases/files/mednafen-$VER.tar.xz"
# emucap 이 이미 받아 둔 것이 있으면 그걸 쓴다 — 같은 sha 라 네트워크가 필요 없다.
VENDORED="$ROOT/vendor/emucap/adapters/mednafen/work/mednafen-$VER.tar.xz"

want=$(cksum "$PATCH" | awk '{print $1"-"$2}')
have=$([ -f "$STAMP" ] && cat "$STAMP" || echo "")

case "${1:-}" in
  --check)
    if [ -x "$BIN" ] && [ "$want" = "$have" ]; then
      echo "✅ 최신 — $BIN"
    elif [ -x "$BIN" ]; then
      echo "⚠ 패치가 바뀌었다 — 다시 빌드해야 한다 (sh $0)"
    else
      echo "· 아직 없다 — 시스템 mednafen 으로 돈다 (창 크기 단축키 없음)"
    fi
    exit 0 ;;
  --force) have="" ;;
esac

if [ -x "$BIN" ] && [ "$want" = "$have" ]; then
  echo "✅ 이미 최신이다 — $BIN"
  exit 0
fi

echo "── mednafen $VER + 창 크기 패치를 빌드한다"
mkdir -p "$OUT/src"
TAR="$OUT/mednafen-$VER.tar.xz"

if [ ! -f "$TAR" ]; then
  if [ -f "$VENDORED" ]; then
    echo "· 소스: emucap 이 받아 둔 타르볼을 쓴다"
    cp "$VENDORED" "$TAR"
  else
    echo "· 소스: 내려받는다 — $URL"
    curl -fL --retry 3 -o "$TAR" "$URL"
  fi
fi

# ⚠ 지문을 먼저 본다 — 「받아졌으니 맞겠지」로 넘어가면 조용히 다른 소스를 빌드한다.
got=$(shasum -a 256 "$TAR" 2>/dev/null | awk '{print $1}' || sha256sum "$TAR" | awk '{print $1}')
[ "$got" = "$SHA" ] || { echo "🔴 타르볼 지문이 다르다: $got" >&2; exit 1; }

rm -rf "$OUT/src/mednafen"
tar -xf "$TAR" -C "$OUT/src"
cd "$OUT/src/mednafen"

echo "· 패치를 얹는다"
patch -p0 --forward < "$PATCH"

echo "· configure (조용히 — 로그는 $OUT/build.log)"
./configure --prefix="$OUT" --disable-nls > "$OUT/build.log" 2>&1
echo "· make -j$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)" >> "$OUT/build.log" 2>&1
make install >> "$OUT/build.log" 2>&1

[ -x "$BIN" ] || { echo "🔴 빌드는 끝났는데 $BIN 이 없다 — $OUT/build.log" >&2; exit 1; }

# 🔴 **빌드 성공이 「모듈이 다 들어갔다」는 뜻이 아니다**(실측 2026-09-15). mednafen 의 configure 는
#   의존물이 없으면 **그 모듈만 조용히 끄고** 나머지를 짓는다 — 맥에서 `ss` 가 그렇게 빠졌고,
#   `emu.sh` 가 `-force_module ss` 를 주자 에뮬레이터가 「Unrecognized system」으로 죽어서
#   **원인이 에뮬레이터 쪽으로 보였다.** 두 기종에서 같은 증상을 겪고서야 갈렸다.
#   ⇒ 여기서 **기대 목록과 대 본다.** 우리가 실제로 쓰는 기종만 든다(`emu.sh` 의 `mednafen <모듈>`).
WANT_MODS="ss psx pce pcfx md"
have=$("$BIN" --help 2>&1 | sed -n 's/.*Emulation modules: *//p' | head -1 || true)
missing=
for m in $WANT_MODS; do
  printf '%s' "$have" | tr ' ' '\n' | grep -qx "$m" || missing="$missing $m"
done
if [ -n "$missing" ]; then
  echo "🔴 빌드는 됐는데 **모듈이 빠졌다:**$missing" >&2
  echo "   있는 것: $have" >&2
  echo "   왜 빠졌는지는 configure 로그에 있다 —" >&2
  echo "     grep -inE 'saturn|WARNING|disabl' $OUT/build.log | head -30" >&2
  echo "   ⚠ 이 상태로도 나머지 기종은 돌아간다. 빠진 기종만 시스템 mednafen 으로 떨어진다." >&2
else
  echo "· 모듈 확인:$(printf '%s' " $WANT_MODS")  전부 있다"
fi
printf '%s' "$want" > "$STAMP"
echo "✅ $BIN"
echo "   이제 ⌥- · ⌥+ 로 한 단계씩, ⌥1~4 로 바로 창 크기를 · ⌥M 으로 소리를 끄고 켠다 (1 매우 작음 … 4 큼)"
