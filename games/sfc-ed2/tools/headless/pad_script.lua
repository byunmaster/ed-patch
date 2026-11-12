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
local DW={} for v in (os.getenv("SW_DUMPW") or ""):gmatch("%d+") do DW[tonumber(v)]=true end
local started=false
-- SW_RACE=1: NMI 진입 때 끊긴 자리(스택의 복귀 PC)가 화면 패널 버퍼($1B3F~) 쓰는 루틴($C0:B3xx~BAxx)이고 DMA 대기 수($1779)가 남아 있으면 로그 — 패널을 덜 쓴 채 DMA 되는 경쟁 검출
if os.getenv("SW_RACE") then
  local RL=io.open(OUT.."/race.txt","w")
  emu.addMemoryCallback(function()
    local st=emu.getState(); local sp=st["cpu.sp"]
    local pcl=emu.read(sp+2,WR,false); local pch=emu.read(sp+3,WR,false); local pb=emu.read(sp+4,WR,false)
    local pc=pcl|(pch<<8)
    local pend=emu.read(0x1779,WR,false)
    if pb==0xC0 and pc>=0xB300 and pc<=0xBB00 then
      RL:write(string.format("%d NMI in %02X:%04X pend1779=%d sp=%04X\n",f-OFF,pb,pc,pend,sp)); RL:flush()
    end
  end,emu.callbackType.exec,0xC00FC0,0xC00FC0,emu.cpuType.snes)
end
local TR=os.getenv("SW_TRACE")  -- "시작,끝"(OFF 기준 프레임) 동안 VRAM 쓰기($2116~$2119)를 vtrace.txt 에 「프레임 PC 주소 값」으로 남긴다 — 화면 그리기 루틴 추적용
local TA,TB=0,-1
if TR then TA,TB=TR:match("(-?%d+),(-?%d+)"); TA,TB=tonumber(TA),tonumber(TB) end
local VT=TR and io.open(OUT.."/vtrace.txt","w")
local vaddr=0
local WW=os.getenv("SW_WWATCH")  -- "시작주소,끝주소"(hex WRAM) 쓰기를 트레이스 구간에 vtrace.txt 로 — 「프레임 W 주소 값 PC」
if WW and VT then
  local a0,a1=WW:match("(%x+),(%x+)")
  emu.addMemoryCallback(function(a,v)
    local k=f-OFF
    if k<TA or k>TB then return end
    local st=emu.getState()
    VT:write(string.format("%d W %04X=%02X %02X:%04X\n",k,a,v,st["cpu.k"] or 0,st["cpu.pc"] or 0))
  end,emu.callbackType.write,tonumber(a0,16),tonumber(a1,16),emu.cpuType.snes,emu.memType.snesWorkRam)
end
if TR then
  local function cb(a,v)
    local k=f-OFF
    if a==0x2116 then vaddr=(vaddr&0xFF00)|v elseif a==0x2117 then vaddr=(vaddr&0xFF)|(v<<8) end
    if k>=TA and k<=TB and (a==0x2118 or a==0x2119) then
      local st=emu.getState()
      VT:write(string.format("%d %02X:%04X %04X %d %02X\n",k,st["cpu.k"] or 0,st["cpu.pc"] or 0,vaddr,a-0x2118,v))
    end
    if a==0x2119 then vaddr=(vaddr+1)&0xFFFF end  -- VMAIN 가정: 상위 바이트 쓰기 뒤 +1
  end
  emu.addMemoryCallback(cb,emu.callbackType.write,0x2116,0x2119,emu.cpuType.snes)
  emu.addMemoryCallback(function(a,v)
    local k=f-OFF
    if k<TA or k>TB then return end
    for ch=0,7 do if (v>>ch)&1==1 then
      local b=0x4300+ch*16
      local function r(x) return emu.read(b+x,emu.memType.snesMemory,false) end
      VT:write(string.format("%d DMA ch%d vaddr=%04X src=%02X:%04X size=%04X ctl=%02X\n",k,ch,vaddr,r(4),r(2)|r(3)<<8,r(5)|r(6)<<8,r(0)))
    end end
  end,emu.callbackType.write,0x420B,0x420B,emu.cpuType.snes)
end
emu.addMemoryCallback(function() if not started then started=true; emu.loadSavestate(S0); f=0; log("loaded") end end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
emu.addEventCallback(function()
  if not started then return end
  f=f+1
  local k=f-OFF
  if f%250==0 then log("f="..f) end
  if SH[k] then shot(string.format("s%05d",k)) end
  if os.getenv("SW_DUMPV") and (","..os.getenv("SW_DUMPV")..","):find(","..k..",",1,true) then local fh=io.open(string.format("%s/vram_%05d.bin",OUT,k),"wb"); for i=0,0xFFFF do fh:write(string.char(emu.read(i,emu.memType.snesVideoRam,false))) end fh:close() end  -- VRAM 64KB 덤프(SW_DUMPV="프레임,…")
  if DW[k] then local fh=io.open(string.format("%s/wram_%05d.bin",OUT,k),"wb"); for i=0,tonumber(os.getenv("SW_DUMPWN") or "8191") do fh:write(string.char(rd(i))) end fh:close() end
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
  if os.getenv("SW_POKE") and f%20==0 and k>=0 then  -- 진단·플레이: WRAM 주입("addr=val,…" hex, 20프레임마다) — 돈·경험치 부스트용(플래그·진행 변수는 만지지 않는다)
    for a_,v_ in string.gmatch(os.getenv("SW_POKE"),"(%x+)=(%x+)") do wr(tonumber(a_,16),tonumber(v_,16)) end
  end
  if f>(tonumber(os.getenv("SW_MAXF") or "4300")) then log("DONE"); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if started and f<OFF-100 and f%30<4 then b.a=true end
  for _,t in ipairs(T) do if f>=OFF+t[1] and f<OFF+t[1]+t[2] then for _,n in ipairs(t[3]) do b[n]=true end end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
