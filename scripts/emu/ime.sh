#!/bin/sh
# macOS 입력 소스 함정 — 에뮬레이터 공용.
#
#   . "$HERE/emu/ime.sh"
#   warn_ime          # 한글 입력 소스면 경고한다
#
# 실측 (2026-08-21 갱신) — **기종마다 다르다**:
#   · DOSBox-X (SDL1)      🔴 한글 입력 소스면 **방향키가 죽는다**(2026-07-31 유저가 규명.
#                             조용히 방향키만 죽고 수정자키·메뉴는 멀쩡해 설정 문제로 오해했다)
#   · DOSBox Staging (SDL2) ✅ 한글 상태에서도 먹는다 (ED3 로 확인)
#   · mednafen              🔴 **글자 키(a·s·d·w…)가 죽는다. 방향키는 산다**(2026-08-22 실측).
#                             하필 우리 배치가 버튼을 전부 글자 키에 뒀으니(mednafen_keys.py)
#                             한글 모드면 **이동만 되고 확인·취소가 안 먹는** 상태가 된다.
#
# ⚠ 그래서 **단정하지 않는다.** 늘 뜨는 경고는 아무도 안 본다(이 레포가 게이트에 대해 못 박은
#   것과 같은 이유다). 「한글이니 안 된다」가 아니라 「안 먹으면 여기부터 보라」로 적는다.
#
# 근본 해결은 **앱별 입력 소스 기억**이다 — 켜 두고 에뮬에서 한 번 ABC 를 고르면 그 앱은
# 늘 ABC 로 뜬다(에뮬 종류와 무관하다):
#   defaults write com.apple.HIToolbox AppleGlobalTextInputProperties \
#     -dict TextInputGlobalPropertyPerContextInput -int 1
#   (시스템 설정 > 키보드 > 입력 소스 > 편집 > "문서의 입력 소스로 자동 전환")
warn_ime() {
  [ "$(uname -s)" = Darwin ] || return 0
  defaults read ~/Library/Preferences/com.apple.HIToolbox.plist AppleSelectedInputSources 2>/dev/null \
    | grep -qi 'inputmethod\.Korean' || return 0
  echo "ⓘ 입력 소스가 한글이다 — mednafen 은 글자 키(a·s·d·w)가 안 먹는다. 영문(ABC)으로 바꿀 것." >&2
  # 앱별 기억을 켜 두면 이 문제 자체가 없어진다. 이미 켜 뒀으면 두 번 말하지 않는다.
  if [ -z "$(defaults read com.apple.HIToolbox AppleGlobalTextInputProperties 2>/dev/null)" ]; then
    echo "  한 번에 끝내려면: 시스템 설정 > 키보드 > 입력 소스 > 편집 >" >&2
    echo "  「문서의 입력 소스로 자동 전환」 을 켜고 에뮬에서 ABC 를 한 번 고른다." >&2
  fi
}
