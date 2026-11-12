-- sfc-ed2 입력 대본 실행기 — 상태를 불러 A 로 첫 대사를 넘겨(OFF 프레임) 자유 필드에 닿은 뒤, 환경변수 SW_SCRIPT 대본을 입력한다.
-- SW_SCRIPT="시작:길이:버튼+버튼,…"(OFF 기준 프레임) · SW_SHOTS="프레임,…"(OFF 기준) · SW_HASH="프레임,…"(그때 WRAM $0100~$060A 해시+저장 슬롯 SRAM 해시)
-- SW_STATE · SW_OUT · SW_MAXF. 상태 불러오기는 exec 콜백(NMI) 안에서만 된다.
local OUT=os.getenv("SW_OUT") or "out"
local WR=emu.memType.snesWorkRam
local SR=emu.memType.snesSaveRam
local f=0
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function rd(a) return emu.read(a,WR,false) end
local function wr(a,v) emu.write(a,v,WR) end
local function shot(name) local h=io.open(OUT.."/"..name..".png","wb"); h:write(emu.takeScreenshot()); h:close() end
local h=io.open(os.getenv("SW_STATE"),"rb"); local S0=h:read("*a"); h:close()
local OFF=tonumber(os.getenv("SW_OFF") or "2800")
local T={}
for a,b,c in (os.getenv("SW_SCRIPT") or ""):gmatch("(%d+):(%d+):([%w+]+)") do local bt={} for n in c:gmatch("%w+") do bt[#bt+1]=n end T[#T+1]={tonumber(a),tonumber(b),bt} end
local function set(s) local r={} for v in (s or ""):gmatch("%d+") do r[tonumber(v)]=true end return r end
local SH,HS=set(os.getenv("SW_SHOTS")),set(os.getenv("SW_HASH"))
local function hash(mt,from,to) local x=5381 for a=from,to do x=(x*33+emu.read(a,mt,false))%4294967296 end return x end
local started=false
emu.addMemoryCallback(function() if not started then started=true; emu.loadSavestate(S0); f=0; log("loaded") end end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
emu.addEventCallback(function()
  if not started then return end
  f=f+1
  local k=f-OFF
  if f%250==0 then log("f="..f) end
  if SH[k] then shot(string.format("s%05d",k)) end
  if HS[k] then
    local sr=0 for s=0,2 do sr=(sr*31+hash(SR,0x15+s*0x50C,0x15+s*0x50C+0x50B))%4294967296 end
    local diff=0 for i=0,0x50A do if emu.read(0x100+i,WR,false)~=emu.read(0x15+i,SR,false) then diff=diff+1 end end
    log("DIFF wram-vs-slot0="..diff)
    log(string.format("HASH k=%d wram=%08X sram=%08X 0124=%02X slot0=%08X slot1=%08X slot2=%08X",k,hash(WR,0x100,0x60A),sr,rd(0x124),hash(SR,0x15,0x15+0x50B),hash(SR,0x15+0x50C,0x15+0x50C+0x50B),hash(SR,0x15+2*0x50C,0x15+2*0x50C+0x50B)))
  end
  if os.getenv("SW_LOADSRM") and k==-50 then  -- 다른 롬에서 만든 저장 파일(.srm)의 SRAM 을 통째로 써 넣는다(상태 불러오기가 SRAM 도 덮으므로 그 뒤에)
    local fh=io.open(os.getenv("SW_LOADSRM"),"rb"); local d=fh:read("*a"); fh:close()
    for i=1,#d do emu.write(i-1,d:byte(i),SR) end
    log("SRM loaded "..#d)
  end
  if os.getenv("SW_DUMPSRM") and f==(tonumber(os.getenv("SW_MAXF") or "4300")) then
    local fh=io.open(os.getenv("SW_DUMPSRM"),"wb"); for i=0,0x1FFF do fh:write(string.char(emu.read(i,SR,false))) end fh:close(); log("SRM dumped")
  end
  if f>(tonumber(os.getenv("SW_MAXF") or "4300")) then log("DONE"); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if started and f<OFF-100 and f%30<4 then b.a=true end
  for _,t in ipairs(T) do if f>=OFF+t[1] and f<OFF+t[1]+t[2] then for _,n in ipairs(t[3]) do b[n]=true end end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
