#!/bin/sh
# 창 크기 단축키가 든 mednafen 을 만든다 (유저 요청 2026-09-07).
#
#     sh scripts/emu/mednafen-build.sh          # 없거나 패치가 바뀌었으면 빌드
#     sh scripts/emu/mednafen-build.sh --force  # 무조건 다시 (--rebuild 도 같다)
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
# 패치는 순서대로 얹는다 — autofire 가 winsize 가 더한 명령 표 뒤를 잇는다(같은 input.cpp).
PATCHES="$ROOT/scripts/emu/mednafen-winsize.patch $ROOT/scripts/emu/mednafen-autofire.patch"
OUT="$ROOT/.local/cache/mednafen"
BIN="$OUT/bin/mednafen"
STAMP="$OUT/.patch.sha1"

VER=1.32.1
SHA=de7eb94ab66212ae7758376524368a8ab208234b33796625ca630547dbc83832
URL="https://mednafen.github.io/releases/files/mednafen-$VER.tar.xz"
# emucap 이 이미 받아 둔 것이 있으면 그걸 쓴다 — 같은 sha 라 네트워크가 필요 없다.
VENDORED="$ROOT/vendor/emucap/adapters/mednafen/work/mednafen-$VER.tar.xz"

# 🔴 **지문은 「무엇으로 지었나」 전부다**(마스터 10-06 — 「예전 버전 같은데 빌드하면 최신이라고 나온다」).
#   종전엔 창 크기 패치 하나만 쟀다. 그래서 ① 이 빌드 스크립트(configure 인자 · 기대 모듈)를 고쳐도
#   「최신」이었고 ② **모듈이 빠진 채 끝난 빌드도 지문을 남겨** 다음부터 「최신」이 됐다 — 빠진
#   기종은 `emu.sh` 가 시스템 mednafen(창 크기·키 패치 없는 옛것)으로 떨어뜨리니 「옛 버전」으로 보였다.
#   ⇒ 지문 = 패치 + 이 스크립트 + 버전, 그리고 모듈이 다 들어간 빌드만 지문을 남긴다.
want=$(cat $PATCHES "$0" | cksum | awk '{print $1"-"$2}')-$VER
have=$([ -f "$STAMP" ] && cat "$STAMP" || echo "")
WANT_MODS="ss psx pce pcfx md"
missing_mods() {   # 지은 바이너리에 빠진 모듈 목록(없으면 빈 문자열)
  _have=$("$BIN" --help 2>&1 | sed -n 's/.*Emulation modules: *//p' | head -1 || true)
  _miss=
  for m in $WANT_MODS; do
    printf '%s' "$_have" | tr ' ' '\n' | grep -qx "$m" || _miss="$_miss $m"
  done
  printf '%s' "$_miss"
}

case "${1:-}" in
  --check)
    if [ -x "$BIN" ] && [ -n "$(missing_mods)" ]; then
      echo "⚠ 모듈이 빠졌다:$(missing_mods) — 그 기종은 시스템 mednafen 으로 떨어진다 (sh $0 --force)"
    elif [ -x "$BIN" ] && [ "$want" = "$have" ]; then
      echo "✅ 최신 — $BIN"
    elif [ -x "$BIN" ]; then
      echo "⚠ 패치나 빌드 스크립트가 바뀌었다 — 다시 빌드해야 한다 (sh $0)"
    else
      echo "· 아직 없다 — 시스템 mednafen 으로 돈다 (창 크기 단축키 없음)"
    fi
    exit 0 ;;
  --force|--rebuild) have="" ;;
esac

if [ -x "$BIN" ] && [ "$want" = "$have" ] && [ -z "$(missing_mods)" ]; then
  echo "✅ 이미 최신이다 — $BIN   (mednafen $VER · 다시 지으려면 --force)"
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

for p in $PATCHES; do
  echo "· 패치를 얹는다 — $(basename "$p")"
  patch -p0 --forward < "$p"
done

echo "· configure (조용히 — 로그는 $OUT/build.log)"
# 🔴 **새턴은 64비트 CPU 에서만 켜지는데, 그 판정을 configure 의 `host_cpu` 로 한다**(configure.ac:
#   `enable_ss` 기본값 = x86_64 amd64 aarch64* arm64* …). 맥 Apple Silicon 에서는 동봉된 옛
#   config.guess 가 CPU 를 `arm` 으로 읽어 목록에 안 걸리고, **새턴만 조용히 빠진다**(마스터 맥 실측
#   10-06 — 아래 모듈 확인이 잡았다). ⇒ 머신이 64비트면 `--enable-ss` 로 못 박는다.
SS_OPT=
case "$(uname -m)" in
  arm64|aarch64|x86_64|amd64) SS_OPT=--enable-ss ;;
esac
# 맥은 App Nap 끄기(mednafen-autofire.patch)가 objc 런타임을 부르므로 -lobjc 를 링크한다.
LIBS_OPT=
[ "$(uname -s)" = Darwin ] && LIBS_OPT=-lobjc
LIBS="$LIBS_OPT" ./configure --prefix="$OUT" --disable-nls $SS_OPT > "$OUT/build.log" 2>&1
echo "· make -j$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)" >> "$OUT/build.log" 2>&1
make install >> "$OUT/build.log" 2>&1

[ -x "$BIN" ] || { echo "🔴 빌드는 끝났는데 $BIN 이 없다 — $OUT/build.log" >&2; exit 1; }

# 🔴 **빌드 성공이 「모듈이 다 들어갔다」는 뜻이 아니다**(실측 2026-09-15). mednafen 의 configure 는
#   의존물이 없으면 **그 모듈만 조용히 끄고** 나머지를 짓는다 — 맥에서 `ss` 가 그렇게 빠졌고,
#   `emu.sh` 가 `-force_module ss` 를 주자 에뮬레이터가 「Unrecognized system」으로 죽어서
#   **원인이 에뮬레이터 쪽으로 보였다.** 두 기종에서 같은 증상을 겪고서야 갈렸다.
#   ⇒ 여기서 **기대 목록과 대 본다.** 우리가 실제로 쓰는 기종만 든다(`emu.sh` 의 `mednafen <모듈>`).
missing=$(missing_mods)
have=$("$BIN" --help 2>&1 | sed -n 's/.*Emulation modules: *//p' | head -1 || true)
if [ -n "$missing" ]; then
  echo "🔴 빌드는 됐는데 **모듈이 빠졌다:**$missing" >&2
  echo "   있는 것: $have" >&2
  echo "   왜 빠졌는지는 configure 로그에 있다 —" >&2
  echo "     grep -inE 'saturn|WARNING|disabl' $OUT/build.log | head -30" >&2
  echo "   ⚠ 이 상태로도 나머지 기종은 돌아간다. 빠진 기종만 시스템 mednafen 으로 떨어진다." >&2
  rm -f "$STAMP"   # 지문을 안 남긴다 — 다음 실행이 「최신」으로 넘어가지 않고 다시 짓게
else
  echo "· 모듈 확인:$(printf '%s' " $WANT_MODS")  전부 있다"
  printf '%s' "$want" > "$STAMP"
  # 새 설정 이름(`command.toggle_autofire` 등)을 cfg 에 미리 써 둔다 — mednafen 은 아는 설정을 종료할 때만
  #   cfg 에 적고, `mednafen_keys.py` 는 cfg 에 **없는 이름은 못 고친다.** 안 하면 새 빌드의 첫
  #   실행에서 새 키가 안 먹고 두 번째부터 먹는다. 게임 없이 띄우면 사용법만 찍고 cfg 를 쓰고 끝난다.
  "$BIN" >/dev/null 2>&1 || true
fi
echo "✅ $BIN"
echo "   이제 ⌥- · ⌥+ 로 한 단계씩, ⌥1~4 로 바로 창 크기를 · ⌥M 으로 소리를 끄고 켠다 (1 매우 작음 … 4 큼)"
echo "   ⌥F 를 뗀 뒤 3초 안에 패드 키 = 그 버튼 자동 연타, ⌥F 또는 아무 패드 키로 끈다"
