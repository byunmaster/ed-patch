-- sfc-ed2 디버그 열쇠 시험 — 필드 주메뉴(B)에서 L+R+Select 1초 → 켜짐, 이어서 +X 매직 코드.
-- 환경변수: SW_OUT(출력 폴더) · SW_STATE(필드 첫 메시지 호출 상태 — `sweep.py mkstate dialog`) · SW_MAXF
-- 상태를 불러온 뒤 A 를 눌러 첫 대사를 넘기고(2700프레임), 그 뒤 시험을 건다. 상태 불러오기는 exec 콜백 안에서만 된다(endFrame 안에서는 조용히 실패).
local OUT=os.getenv("SW_OUT") or "out"
local WR=emu.memType.snesWorkRam
local f=0
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function rd(a) return emu.read(a,WR,false) end
local function shot(name) local h=io.open(OUT.."/"..name..".png","wb"); h:write(emu.takeScreenshot()); h:close() end
local h=io.open(os.getenv("SW_STATE"),"rb"); local S0=h:read("*a"); h:close()
-- (시작 프레임, 길이, 버튼들, 이름) — 상태를 불러온 뒤 프레임 기준
local OFF=2800
local T={
  {100,10,{"b"},"menu"},
  {300,70,{"l","r","select"},"chord"},
  {620,8,{"l","r","select","x"},"cmdX"},
  {600,40,{"l","r","select"},"hold_then_X"},
}
local SHOTS={680,720,780,840,900,1000,1100,1200}
local function cur()
  for _,t in ipairs(T) do if f>=OFF+t[1] and f<OFF+t[1]+t[2] then return t end end
end
local started=false
emu.addMemoryCallback(function() if f>=OFF+560 and f<OFF+700 then log(string.format("STUB f=%d 1B06=%02X 1B07=%02X 1B95=%02X 137A=%02X",f,rd(0x1B06),rd(0x1B07),rd(0x1B95),rd(0x137A))) end end, emu.callbackType.exec, 0xC0FD60, 0xC0FD60, emu.cpuType.snes)
emu.addMemoryCallback(function() if not started then started=true; emu.loadSavestate(S0); f=0; log("loaded") end end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
emu.addEventCallback(function()
  if not started then return end
  f=f+1
  for _,t in ipairs(T) do
    local k=f-OFF-t[1]
    if k==t[2]-3 then log(string.format("%s f=%d during: cnt=%d unlock=%02X 11A7=%02X 11A8=%02X 1B95=%02X 0B57=%02X",t[4],f,rd(0xB5A),rd(0xB5B),rd(0x11A7),rd(0x11A8),rd(0x1B95),rd(0xB57))) end
    if k==t[2]+20 then log(string.format("%s f=%d after : cnt=%d unlock=%02X 11A7=%02X 11A8=%02X 1B95=%02X",t[4],f,rd(0xB5A),rd(0xB5B),rd(0x11A7),rd(0x11A8),rd(0x1B95))); shot(t[4]) end
  end
    for _,q in ipairs(SHOTS) do if f==OFF+q then shot(string.format("s%d",q)); log(string.format("s%d 137A=%02X",q,rd(0x137A))) end end
  if f>(tonumber(os.getenv("SW_MAXF") or "4300")) then log("DONE"); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  local t=cur()
  if started and f<OFF-100 and f%30<4 then b.a=true end
  if t then for _,n in ipairs(t[3]) do b[n]=true end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
