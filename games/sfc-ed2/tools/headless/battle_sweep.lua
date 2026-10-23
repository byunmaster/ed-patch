-- sfc-ed2 전 몬스터 전투 일괄 시험 — Mesen2 Lua(헤드리스 --testRunner). 제품 롬 그대로 쓴다(롬 패치 없음).
-- 환경변수: SW_OUT(출력 폴더) SW_JOBS("idx:seed,idx:seed,…") SW_FRAMES(전투 프레임 상한) SW_MODE("act"=행동 다 보기 | "hp1")
local OUT=os.getenv("SW_OUT") or "out"
local JOBS={}
for idx,seed in string.gmatch(os.getenv("SW_JOBS") or "0:1", "(%d+):(%d+)") do JOBS[#JOBS+1]={tonumber(idx),tonumber(seed)} end
local FRAMES=tonumber(os.getenv("SW_FRAMES") or "6000")
local WR=emu.memType.snesWorkRam
local f=0
local function rd(a) return emu.read(a,WR,false) end
local function rd16(a) return rd(a)|(rd(a+1)<<8) end
local function wr(a,v) emu.write(a,v,WR) end
local function wr16(a,v) wr(a,v&255); wr(a+1,(v>>8)&255) end
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function shot(path)
  local png=emu.takeScreenshot()
  local h=io.open(path,"wb"); h:write(png); h:close()
end
-- 조우 번호(n) ← 군 번호(idx): 지역 크기 [0x1E,0x1F,0x14,…]
local function nOf(idx)
  if idx<0x1E then return idx
  elseif idx<0x3D then return 0x20+idx-0x1E
  elseif idx<0x51 then return 0x40+idx-0x3D
  else return 0x60+idx-0x51 end
end
local sched={ [100]={"start"}, [1700]={"a"}, [2300]={"down",5}, [2400]={"a"}, [3000]={"a"} }
local S0=nil
local job=0          -- 지금 도는 작업(1~#JOBS), 0=부팅 중
local pending=false  -- 다음 9FDC 에서 전투로 보낸다
local bf=0           -- 전투 프레임
local state="boot"   -- boot | run | finish | between
local msgn=0
local finish_at=nil
local dir=nil
local function start_job()
  cur=nil
  job=job+1; shots={}
  if job>#JOBS then log("ALLDONE f="..f); LOG:close(); emu.stop(0); return end
  local idx,seed=JOBS[job][1],JOBS[job][2]
  dir=string.format("%s/raw/%02d_s%d",OUT,idx,seed)
  os.execute("mkdir -p "..dir)
  pending=true; bf=0; msgn=0; state="run"; finish_at=nil
  log(string.format("JOB %d idx=%d n=0x%02X seed=%d",job,idx,nOf(idx),seed))
end
emu.addMemoryCallback(function()
  if S0==nil then
    local a=emu.getState()["cpu.a"]&255
    if a==2 then
      S0=emu.createSavestate()
      log("S0 created f="..f)
      local mk=os.getenv("SW_MKSTATE")
      if mk then local h=io.open(mk,"wb"); h:write(S0); h:close(); LOG:close(); emu.stop(0); return end
      start_job()   -- 첫 작업: pending=true
    end
  end
end, emu.callbackType.exec, 0xC19540, 0xC19540, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if S0==nil then return end
  if (not pending) and (state=="run" or state=="finish") and bf>30 then
    shot(string.format("%s/%05d_end.png",dir,bf))
    log(string.format("END %d bf=%d msgs=%d reentry",job,bf,msgn))
    state="between"
    emu.loadSavestate(S0)
    start_job()
    return
  end
  if pending then
    pending=false
    local idx,seed=JOBS[job][1],JOBS[job][2]
    local st=emu.getState()
    st["cpu.pc"]=0x2663; st["cpu.k"]=0xC1; st["cpu.a"]=nOf(idx)
    emu.setState(st)
    wr16(0x1C24, (seed*40503+12345)&0xFFFF)
  end
end, emu.callbackType.exec, 0xC19FDC, 0xC19FDC, emu.cpuType.snes)
local SM=emu.memType.snesMemory
local site={}
local FORCE=(os.getenv("SW_FORCE") or "1")=="1"
emu.addMemoryCallback(function()
  if not FORCE or (state~="run" and state~="finish") then return end
  local st=emu.getState()
  local sp=st["cpu.sp"]
  local ra=emu.read(sp+1,SM,false)|(emu.read(sp+2,SM,false)<<8)
  local bank=emu.read(sp+3,SM,false)
  if bank~=0xD4 and bank~=0xD5 then return end
  local n=st["cpu.a"]&255
  if n==0 then return end
  local key=job*0x1000000+bank*0x10000+ra
  local c=(site[key] or 0)
  site[key]=c+1
  st["cpu.a"]=(st["cpu.a"]&0xFF00)|(c%n)
  st["cpu.pc"]=0x1E75; st["cpu.k"]=0xC1
  emu.setState(st)
end, emu.callbackType.exec, 0xC11E3A, 0xC11E3A, emu.cpuType.snes)
local shots={}
local hit={}
cur=nil
local superseded=0
local DEB=tonumber(os.getenv("SW_DEBOUNCE") or "8")
local PMAX=tonumber(os.getenv("SW_PAGEMAX") or "150")
local prevh,stable,lasth=nil,0,nil
local lasttx,lasth_cur=0,nil
local TXMIN=tonumber(os.getenv("SW_TXMIN") or "6")  -- 창 안쪽 글자 픽셀 하한 — 창이 열렸지만 글이 아직 안 나온 빈 창을 쪽으로 안 찍는다(10-20: 첫 「나타났다」 쪽이 전 그룹 빈 창이었다)
local function bandhash()
  local b=emu.getScreenBuffer(); local h=5381
  local tx=0
  for y=148,218,2 do local o=y*256
    for x=8,248,2 do
      local v=b[o+x+1] or 0
      h=(h*33+v)%4294967296
      if y>=156 and y<=204 then
        local r,g,bb=(v>>16)&255,(v>>8)&255,v&255
        if (r>=200 and g>=200 and bb>=200) or (math.abs(r-182)<=8 and math.abs(g-147)<=8 and math.abs(bb-92)<=8) then tx=tx+1 end
      end
    end
  end
  return h,tx
end
local function boost()
  for i=0,3 do
    wr16(0x050F+i*0x40,999); wr16(0x0511+i*0x40,999)
    wr(0x0536+i*0x40, rd(0x0536+i*0x40)|1)
  end
end
local function enemies(fn)
  for i=4,7 do local b=0x050B+i*0x40; if (rd(b)&0x80)==0 and rd(b)~=0xFF then fn(b) end end
end
emu.addMemoryCallback(function()
  if state~="run" and state~="finish" then return end
  msgn=msgn+1
  local p=rd(0xA6)|(rd(0xA7)<<8)|(rd(0xA8)<<16)
  log(string.format("M %d %d %06X",job,bf,p))
  if cur~=nil then
    log(string.format("SUPERSEDED %d %d",job,cur.start)); superseded=superseded+1
    -- 다음 호출이 이전 문구를 지우기 직전 화면 — 글자가 나와 있으면 찍는다(출현 문구가 곧바로 다른 메시지로 바뀌는 그룹이 첫 쪽 없이 지나갔다)
    if cur.n==1 and lasttx>=TXMIN and lasth_cur~=lasth then shot(string.format("%s/%05d_m%d_sup.png",dir,bf,cur.n)); lasth=lasth_cur end
  end
  cur={start=bf, n=msgn}   -- 찍기 전에 기다린다: 창 안쪽이 안정될 때까지(아래 NMI 쪽에서 찍는다)
  boost()
  if state=="run" then
    local ph=(bf//1000)%2
    enemies(function(b) wr16(b+6,9999); wr16(b+4, ph==0 and 9999 or 2500) end)
  else
    enemies(function(b) wr16(b+4,1) end)
  end
end, emu.callbackType.exec, 0xC0A6E8, 0xC0A6E8, emu.cpuType.snes)
emu.addEventCallback(function() f=f+1 end, emu.eventType.endFrame)
local nmi=0xC00FC0
local nmi_full=nmi
local STATEFILE=os.getenv("SW_STATE")
emu.addMemoryCallback(function()
  if STATEFILE and S0==nil then
    local h=io.open(STATEFILE,"rb"); S0=h:read("*a"); h:close()
    log("S0 loaded from file")
    start_job()
    emu.loadSavestate(S0)
    return
  end
  if state=="run" or state=="finish" then
    if not pending then bf=bf+1 end
    if cur~=nil then
      local h,tx=bandhash()
      lasttx=tx; lasth_cur=h
      if prevh~=nil and h==prevh then stable=stable+1 else stable=0 end
      prevh=h
      local age=bf-cur.start
      if stable>=DEB and age>=10 and h~=lasth and tx>=TXMIN then
        shot(string.format("%s/%05d_m%d.png",dir,bf,cur.n)); lasth=h; cur=nil
      elseif age>=PMAX then
        shot(string.format("%s/%05d_m%d_timeout.png",dir,bf,cur.n)); log(string.format("TIMEOUT %d bf=%d msg=%d stable=%d",job,bf,cur.n,stable)); lasth=h; cur=nil
      end
    end
    if #shots>0 then
      local keep={}
      for _,e in ipairs(shots) do if e[1]==bf then shot(e[2]) elseif e[1]>bf then keep[#keep+1]=e end end
      shots=keep
    end
    if state=="run" and bf>=FRAMES then state="finish"; finish_at=bf; log("FINISH "..job.." bf="..bf) end
    if state=="finish" and bf>=finish_at+300 then
      shot(string.format("%s/%05d_end.png",dir,bf))
      log(string.format("END %d bf=%d msgs=%d timeout",job,bf,msgn))
      state="between"
      emu.loadSavestate(S0)
      start_job()
    end
  end
  if f>3000000 then log("TIMEOUT"); emu.stop(2) end
end, emu.callbackType.exec, nmi, nmi, emu.cpuType.snes)
emu.addEventCallback(function()
  local b={}
  if S0==nil then
    for k,v in pairs(sched) do local L=v[2] or 20; if f>=k and f<k+L then b[v[1]]=true end end
  end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
