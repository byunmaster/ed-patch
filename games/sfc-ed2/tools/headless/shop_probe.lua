-- sfc-ed2 가게 화면 강제 진입 — 필드 첫 메시지 호출 상태를 불러 PC 를 가게 루틴 입구(SW_ENTRY, hex SNES 주소)로 돌린 뒤 입력 대본을 넣는다.
-- 환경변수: SW_OUT · SW_STATE · SW_ENTRY · SW_SCRIPT("시작:길이:버튼+버튼,…", 입구 기준 프레임) · SW_SHOTS("프레임,…") · SW_MAXF · SW_GOLD(hex 2바이트 LE, 있으면 `$0xxx` 금화에 씀 — SW_GOLDADDR)
-- 가게 루틴은 `$1302~` 등 표 주소를 즉치로 세팅하고 `jsl $C0:ED0D`(가게 UI) → `jml $C1:8F15`(메시지 끝)로 돈다.
local OUT=os.getenv("SW_OUT") or "out"
if os.getenv("SW_WATCH") then dofile(os.getenv("SW_WATCHLUA")) end   -- 원판 사본 읽힘 감시(watch.lua)
local WR=emu.memType.snesWorkRam
local f=0
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function rd(a) return emu.read(a,WR,false) end
local function shot(name) local h=io.open(OUT.."/"..name..".png","wb"); h:write(emu.takeScreenshot()); h:close() end
local h=io.open(os.getenv("SW_STATE"),"rb"); local S0=h:read("*a"); h:close()
local ENTRY=tonumber(os.getenv("SW_ENTRY"),16)
local T={}
for a,b,c in (os.getenv("SW_SCRIPT") or ""):gmatch("(%d+):(%d+):([%w+]+)") do local bt={} for n in c:gmatch("%w+") do bt[#bt+1]=n end T[#T+1]={tonumber(a),tonumber(b),bt} end
local SH={} for v in (os.getenv("SW_SHOTS") or ""):gmatch("%d+") do SH[tonumber(v)]=true end
local started=false
emu.addMemoryCallback(function()
  if started then return end
  started=true
  emu.loadSavestate(S0)
  local st=emu.getState()
  st["cpu.pc"]=ENTRY&0xFFFF; st["cpu.k"]=(ENTRY>>16)&0xFF
  st["cpu.ps"]=(st["cpu.ps"] or 0)|0x30
  emu.setState(st)
  f=0
  if os.getenv("SW_GOLDADDR") then local a=tonumber(os.getenv("SW_GOLDADDR"),16); local v=tonumber(os.getenv("SW_GOLD") or "FFFF",16); emu.write(a,v&255,WR); emu.write(a+1,(v>>8)&255,WR) end
  log(string.format("entered %06X",ENTRY))
end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
local CNT={}
for v in (os.getenv("SW_COUNT") or ""):gmatch("%x+") do local ad=tonumber(v,16); CNT[ad]=0
  emu.addMemoryCallback(function() CNT[ad]=CNT[ad]+1 end, emu.callbackType.exec, ad, ad, emu.cpuType.snes) end
local BP=os.getenv("SW_BP") and tonumber(os.getenv("SW_BP"),16)
if BP then emu.addMemoryCallback(function()
  if not started then return end
  local q=emu.getState(); local sp=q["cpu.sp"]; local t={}
  for i=1,8 do t[#t+1]=string.format("%02X",emu.read(sp+i,emu.memType.snesMemory,false)) end
  log(string.format("BP %06X f=%d sp=%04X stack=%s",BP,f,sp,table.concat(t," ")))
end, emu.callbackType.exec, BP, BP, emu.cpuType.snes) end
local pcseen={}
emu.addEventCallback(function()
  if not started then return end
  f=f+1
  if SH[f] and os.getenv("SW_DUMP") then
    local q=emu.getState(); local t={} for i=0,31 do t[#t+1]=string.format("%02X",rd(0x1201+i)) end
    log(string.format("DUMP f=%d x=%04X y=%04X a=%04X p97=%02X%02X%02X 1201=%s",f,q["cpu.x"],q["cpu.y"],q["cpu.a"],rd(0x99),rd(0x98),rd(0x97),table.concat(t," ")))
  end
  if SH[f] then shot(string.format("s%05d",f)); local q=emu.getState(); log(string.format("f=%d pc=%02X:%04X 1B95=%02X",f,q["cpu.k"],q["cpu.pc"],rd(0x1B95))) end
  if f>(tonumber(os.getenv("SW_MAXF") or "1500")) then for ad,c in pairs(CNT) do log(string.format("COUNT %06X=%d",ad,c)) end log("DONE"); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if started then for _,t in ipairs(T) do if f>=t[1] and f<t[1]+t[2] then for _,n in ipairs(t[3]) do b[n]=true end end end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
