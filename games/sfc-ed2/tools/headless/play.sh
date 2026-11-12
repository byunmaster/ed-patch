#!/bin/sh
# sfc-ed2 플레이 하네스 한 번 돌리기 — 제품 롬을 헤드리스 Mesen2 로 돌려 입력 대본을 넣고 화면을 찍는다. 세션은 **대본 구간을 이어 붙여** 진행한다
# (구간 끝에서 게임 안 저장을 하고 SRAM 을 파일로 내리면 다음 구간이 그 저장을 불러 이어 간다).
#
#   NAME=<산출 폴더 이름> [IN_SRM=<불러올 .srm>] [SCRIPT="시작:길이:버튼+버튼,…"] [SHOTS="프레임,…"] [MAXF=<끝 프레임>] [OUT_SRM=<끝에 SRAM 을 내릴 파일>] [POKE="주소=값,…"] [DUMPW="프레임,…"(OFF 기준 그 프레임의 WRAM $0000~$1FFF 를 산출 폴더에 wram_<프레임>.bin 으로)] sh games/sfc-ed2/tools/headless/play.sh
#
#  · 프레임은 **OFF 기준**(IN_SRM 이 있으면 OFF=300 — 부팅 대사 넘기기 없이 바로 대본, 없으면 OFF=2800 — 첫 대사를 A 연타로 넘긴 뒤 자유 필드).
#  · 버튼 이름: a b x y l r start select up down left right (`+` 로 동시). 누름은 4프레임 단위로 읽힌다(필드는 입력을 약 4프레임마다 읽는다).
#  · MAXF 는 OFF 를 **포함한** 절대 프레임(예: 필드에서 1500프레임 돌리려면 OFF+1500).
#  · IN_SRM 을 쓰면 대본 앞에 불러오기를 직접 넣는다: `select`(로드 창) → 슬롯에 `a` → 확인 `a` … (게임 안 불러오기 — 필드 상태가 그대로 복구된다).
#  · 산출: <inbox>/play/<NAME>/{log.txt, s<프레임>.png} — 로그의 DONE 이 나와야 정상 종료. 에뮬이 죽으면(rc 135) 다시 돈다(HOME 격리로 대부분 피한다).
#  · 🔴 에뮬 실행은 `sh scripts/capture.sh sh games/sfc-ed2/tools/headless/play.sh` 로 줄 서서 돈다. 부스트(POKE)는 돈·경험치만 — 플래그·진행 변수는 쓰지 않는다.
set -eu
ROOT=$(git rev-parse --show-toplevel)
COMMON=$(git rev-parse --path-format=absolute --git-common-dir)
MAIN=$(dirname "$COMMON")
G=$ROOT/games/sfc-ed2
ROM=$G/work/build/${BUILD:-sfc-ed2}/"Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
ST=$G/work/derived/headless/S_dialog.bin
OFF=${OFF:-}
[ -n "${IN_SRM:-}" ] && : "${OFF:=300}" || : "${OFF:=2800}"
OUT=$MAIN/.local/work/inbox/sfc-ed2/play/${NAME:?NAME 필요}
HOMEDIR=$MAIN/.local/work/inbox/sfc-ed2/play/.home
rm -rf "$OUT"; mkdir -p "$OUT" "$HOMEDIR/.config/MesenCE/Saves"
rm -f "$HOMEDIR"/.config/MesenCE/Saves/*.srm
MESEN=$G/work/derived/headless/mesen/Mesen
env HOME=$HOMEDIR SW_OUT=$OUT SW_STATE=$ST SW_OFF=$OFF SW_SCRIPT="${SCRIPT:-}" SW_SHOTS="${SHOTS:-}" SW_MAXF="${MAXF:-$((OFF+600))}" \
 ${IN_SRM:+SW_LOADSRM=$IN_SRM} ${OUT_SRM:+SW_DUMPSRM=$OUT_SRM} ${POKE:+SW_POKE=$POKE} ${DUMPW:+SW_DUMPW=$DUMPW} ${TRACE:+SW_TRACE=$TRACE} ${DUMPV:+SW_DUMPV=$DUMPV} ${DUMPWN:+SW_DUMPWN=$DUMPWN} ${WWATCH:+SW_WWATCH=$WWATCH} ${RACE:+SW_RACE=$RACE} DISPLAY=${DISPLAY:-:99} \
 "$MESEN" --testRunner "$ROM" "$G/tools/headless/pad_script.lua" --timeout=1800 --debug.scriptWindow.allowIoOsAccess=true --preferences.singleInstance=false --snes.port1.type=SnesController --donotSaveSettings >/dev/null 2>&1 || true
grep -v '^f=' "$OUT/log.txt" 2>/dev/null || echo "(로그 없음 — 에뮬이 죽었다. 다시 돈다)"
