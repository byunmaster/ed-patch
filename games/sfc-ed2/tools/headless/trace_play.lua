-- sfc-ed2 구조 흐름 추적 — 대사 단위를 자연 진행(A 연타)으로 끝까지 돌리며 엔진이 읽는 **구조 토큰**(끝·점프·호출·조건·스크립트)의 (주소, 바이트) 열을 남긴다.
-- 같은 단위를 「구조만 같은 기준 롬(ED_RELOC_OFF=*)」과 번역 롬에서 돌려 열이 같은지 본다 — 재배치가 다음 블록 호출·점프를 막거나 순서를 바꾸면 갈린다(ss-ed3 10-21).
-- 환경변수: SW_OUT · SW_STATE(필드 첫 A6E8 입구 상태) · SW_LIST("SNES주소 hex" 줄 — 비면 상태 그대로(첫 장면) 연속 재생) · SW_MAXF(단위당 프레임 상한)
local OUT=os.getenv("SW_OUT") or "out"
local WR=emu.memType.snesWorkRam
local SM=emu.memType.snesMemory
local LOG=io.open(OUT.."/trace.txt","a")
local function wr(a,v) emu.write(a,v,WR) end
local STATEFILE=os.getenv("SW_STATE")
local MAXF=tonumber(os.getenv("SW_MAXF") or "2500")
local UNITS={}
if os.getenv("SW_LIST") then for line in io.lines(os.getenv("SW_LIST")) do local a=tonumber(line:match("%x+"),16); if a then UNITS[#UNITS+1]=a end end end
local ALL=os.getenv("SW_ALL")=="1"
local S1=nil
local ui=0
local uf=0
local state="boot"
local msgs=0
local lastmsg=0
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local STRUCT={[0x00]=1,[0x06]=1,[0x07]=1,[0x0F]=1,[0x10]=1,[0x11]=1,[0x12]=1,[0x13]=1,[0x14]=1,[0x15]=1,[0xF0]=1,[0xF1]=1,[0xF2]=1,[0xF3]=1,[0xF4]=1,[0xF5]=1,[0xF6]=1,[0xF7]=1,[0xF8]=1,[0xF9]=1}
local function setptr(a) wr(0xA6,a&255); wr(0xA7,(a>>8)&255); wr(0xA8,(a>>16)&255) end
local function next_unit()
  ui=ui+1
  uf=0; msgs=0; lastmsg=0
  if #UNITS>0 and ui>#UNITS then log("ALLDONE"); LOG:close(); emu.stop(0); return false end
  if #UNITS==0 and ui>1 then log("ALLDONE"); LOG:close(); emu.stop(0); return false end
  log(string.format("UNIT %d %06X",ui,UNITS[ui] or 0))
  emu.loadSavestate(S1)
  if #UNITS>0 then setptr(UNITS[ui]) end
  state="run"
  return true
end
emu.addMemoryCallback(function()
  if S1==nil and STATEFILE then
    local h=io.open(STATEFILE,"rb"); S1=h:read("*a"); h:close()
    next_unit()
  end
end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
-- 토큰 읽기 `lda [$A6],y`(C0:A878) — 구조 토큰이면 (주소, 바이트) 를 남긴다
emu.addMemoryCallback(function()
  if state~="run" then return end
  local st=emu.getState()
  local y=st["cpu.y"]
  local p=emu.read(0xA6,WR,false)|(emu.read(0xA7,WR,false)<<8)|(emu.read(0xA8,WR,false)<<16)
  local addr=(p&0xFF0000)|((p+y)&0xFFFF)
  local b=emu.read(addr,SM,false)
  if STRUCT[b] or ALL then log(string.format("%s %06X %02X",STRUCT[b] and "T" or "t",addr,b)) end
end, emu.callbackType.exec, 0xC0A878, 0xC0A878, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if state=="run" then msgs=msgs+1; lastmsg=uf; log(string.format("M %06X",emu.read(0xA6,WR,false)|(emu.read(0xA7,WR,false)<<8)|(emu.read(0xA8,WR,false)<<16))) end
end, emu.callbackType.exec, 0xC0A6E8, 0xC0A6E8, emu.cpuType.snes)
-- 호출자 복귀 = 단위 끝(주입 단위만) · 첫 장면은 메시지가 600프레임 안 나오면 끝
emu.addMemoryCallback(function()
  if state=="run" and #UNITS>0 and uf>5 then log(string.format("END %d ret f=%d msgs=%d",ui,uf,msgs)); state="between"; next_unit() end
end, emu.callbackType.exec, 0xC18F14, 0xC18F14, emu.cpuType.snes)
local pressn=0
emu.addMemoryCallback(function()
  if state~="run" then return end
  uf=uf+1
  if uf%14==0 then pressn=6 end
  if pressn>0 then pressn=pressn-1 end
  if uf>=MAXF or (#UNITS==0 and msgs>0 and uf-lastmsg>900) then
    log(string.format("END %d maxf f=%d msgs=%d",ui,uf,msgs)); state="between"; next_unit()
  end
end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
emu.addEventCallback(function()
  local b={}
  if state=="run" and pressn>0 then b["a"]=true end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
