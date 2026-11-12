# 대화형 상주 하네스: srv.sh 를 띄워 두고 play_c.py "대본" "샷" 프레임 으로 명령을 보낸다(srv.lua 머리말 참고)
#!/bin/sh
cd /root/work/ed-patch/.claude/worktrees/sfc-ed2
MAIN=/root/work/ed-patch
G=/root/work/ed-patch/.claude/worktrees/sfc-ed2/games/sfc-ed2
ROM=$G/work/build/sfc-ed2/"Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
OUT=$MAIN/.local/work/inbox/sfc-ed2/play/srv
HOMEDIR=$MAIN/.local/work/inbox/sfc-ed2/play/.home2
rm -rf $OUT; mkdir -p $OUT $HOMEDIR/.config/MesenCE/Saves
rm -f $HOMEDIR/.config/MesenCE/Saves/*.srm
env HOME=$HOMEDIR SW_OUT=$OUT SW_STATE=$G/work/derived/headless/S_dialog.bin SW_OFF=2800 DISPLAY=:99 $G/work/derived/headless/mesen/Mesen --testRunner "$ROM" $G/tools/headless/srv.lua --timeout=36000 --debug.scriptWindow.allowIoOsAccess=true --preferences.singleInstance=false --snes.port1.type=SnesController --donotSaveSettings >$OUT/mesen.log 2>&1
echo srv-exit >> $OUT/exit.txt
