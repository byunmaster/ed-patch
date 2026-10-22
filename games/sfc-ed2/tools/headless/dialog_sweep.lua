-- sfc-ed2 대사 직접 호출 일괄((b) 방식) — 필드 첫 메시지 호출 지점의 상태를 열고, 단위마다 $A6~$A8 포인터만 바꿔 같은 메시지 루틴으로 찍는다.
-- 환경변수: SW_OUT · SW_STATE(필드 첫 A6E8 입구 상태 파일, 없으면 부팅해서 만든다 SW_MKSTATE) · SW_LIST("SNES주소 hex" 줄 파일) · SW_MAXF(단위당 프레임 상한)
local OUT=os.getenv("SW_OUT") or "out"
local WR=emu.memType.snesWorkRam
local SM=emu.memType.snesMemory
local f=0
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function rd(a) return emu.read(a,WR,false) end
local function wr(a,v) emu.write(a,v,WR) end
local function shot(path) local h=io.open(path,"wb"); h:write(emu.takeScreenshot()); h:close() end
local sched={ [100]={"start"}, [1700]={"a"}, [2300]={"down",5}, [2400]={"a"}, [3000]={"a"} }
local MAXF=tonumber(os.getenv("SW_MAXF") or "900")
local STATEFILE=os.getenv("SW_STATE")
local MK=os.getenv("SW_MKSTATE")
local UNITS={}
if os.getenv("SW_LIST") then for line in io.lines(os.getenv("SW_LIST")) do local a=tonumber(line:match("%x+"),16); if a then UNITS[#UNITS+1]=a end end end
local S1=nil
local uf=0         -- 단위 프레임
local ui=0         -- 지금 단위(1..#UNITS)
local RA=nil       -- 첫 호출의 복귀 주소(= 호출 지점 + 4) — 단위 끝 판정
local state="boot"
local need_write=false
local function next_unit()
  ui=ui+1
  if ui>#UNITS then log("ALLDONE"); LOG:close(); emu.stop(0); return false end
  uf=0; need_write=true; state="run"
  os.execute(string.format("mkdir -p %s/raw/%06X",OUT,UNITS[ui]))
  log(string.format("UNIT %d %06X",ui,UNITS[ui]))
  return true
end
-- ① 필드에서 첫 메시지 호출 입구 — 상태 저장(및 복귀 주소 기록)
emu.addMemoryCallback(function()
  if S1==nil and state=="boot" then
    local st=emu.getState()
    local sp=st["cpu.sp"]
    RA=emu.read(sp+1,SM,false)|(emu.read(sp+2,SM,false)<<8)|(emu.read(sp+3,SM,false)<<16)
    S1=emu.createSavestate()
    log(string.format("S1 f=%d ra=%06X ptr=%06X",f,RA,rd(0xA6)|(rd(0xA7)<<8)|(rd(0xA8)<<16)))
    if MK then local h=io.open(MK,"wb"); h:write(S1); h:close(); LOG:close(); emu.stop(0) return end
    state="idle"
    if next_unit() then emu.loadSavestate(S1) end
  end
end, emu.callbackType.exec, 0xC0A6E8, 0xC0A6E8, emu.cpuType.snes)
local nmi=0xC00FC0
emu.addMemoryCallback(function()
  if STATEFILE and S1==nil then
    local h=io.open(STATEFILE,"rb"); S1=h:read("*a"); h:close()
    log("S1 loaded from file")
    state="idle"
    if next_unit() then emu.loadSavestate(S1) end
    return
  end
  if state~="run" then return end
  if need_write then
    need_write=false
    local a=UNITS[ui]
    wr(0xA6,a&255); wr(0xA7,(a>>8)&255); wr(0xA8,(a>>16)&255)
  end
  uf=uf+1
  if uf%20==0 then shot(string.format("%s/raw/%06X/%05d.png",OUT,UNITS[ui],uf)) end
  if uf>=MAXF then
    shot(string.format("%s/raw/%06X/%05d_end.png",OUT,UNITS[ui],uf))
    log(string.format("END %d %06X maxf",ui,UNITS[ui]))
    state="between"
    emu.loadSavestate(S1)
    if not next_unit() then return end
  end
end, emu.callbackType.exec, nmi, nmi, emu.cpuType.snes)
-- ② 메시지 루틴이 호출자로 돌아오는 자리 — 단위 끝(원래 이벤트가 이어지므로 여기서 끊는다)
local ra_set=false
emu.addMemoryCallback(function()
  if state=="run" and uf>5 then
    shot(string.format("%s/raw/%06X/%05d_end.png",OUT,UNITS[ui],uf))
    log(string.format("END %d %06X ret f=%d",ui,UNITS[ui],uf))
    state="between"
    emu.loadSavestate(S1)
    next_unit()
  end
end, emu.callbackType.exec, 0xC18F14, 0xC18F14, emu.cpuType.snes)
emu.addEventCallback(function() f=f+1 end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if S1==nil then for k,v in pairs(sched) do local L=v[2] or 20; if f>=k and f<k+L then b[v[1]]=true end end end
  if state=="run" and uf>0 and (uf%45)<10 then b["a"]=true end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
