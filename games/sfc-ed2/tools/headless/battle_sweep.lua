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
local NOSHOT=(os.getenv("SW_NOSHOT") or "0")=="1"  -- 완료 시험(촬영 안 함) — 멈춤(`_end` 가 timeout 으로 끝난 작업)만 한 장 남긴다
local DUMP=tonumber(os.getenv("SW_DUMP") or "0"); if DUMP==0 then DUMP=nil end
local WINKILL=(os.getenv("SW_WINKILL") or "0")=="1"  -- 진단: 적 칸을 죽음 표시(0x80)로 직접 쓴다
local WRAMDUMP=tonumber(os.getenv("SW_WRAMDUMP") or "0"); if WRAMDUMP==0 then WRAMDUMP=nil end
local WINMODE=(os.getenv("SW_WIN") or "0")=="1"    -- 완료 시험: 첫 메시지부터 적 HP 1 로 두고 이겨서 필드로 돌아오는지만 본다
local function shot(path,force)
  if NOSHOT and not force then return end
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
local WW=os.getenv("SW_WWATCH")  -- "시작,끝"(hex WRAM) 쓰기 로그 — 「W 프레임 주소=값 PC」
if WW then
  local a0,a1=WW:match("(%x+),(%x+)")
  emu.addMemoryCallback(function(a,v)
    local st=emu.getState()
    log(string.format("W f=%d %04X=%02X %02X:%04X",f,a,v,st["cpu.k"] or 0,st["cpu.pc"] or 0))
  end,emu.callbackType.write,tonumber(a0,16),tonumber(a1,16),emu.cpuType.snes,emu.memType.snesWorkRam)
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
    for a_,v_ in string.gmatch(os.getenv("SW_POKE") or "","(%x+)=(%x+)") do wr(tonumber(a_,16),tonumber(v_,16)) end  -- 진단: 전투 시작 직전 WRAM 주입("1325=20,…")
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
  -- 진단(10-24 붉은 슬라임): 이름 버퍼(`$063B` 계열) 바이트를 로그로 남기고 SW_NAMEMODE=nospace(공백 삭제)·fwspace(공백→전각 공백 `80 00`)로 바꿔 글줄 겹침이 공백 탓인지 가른다
  if (p==0x63B or p==0x67B or p==0x6BB or p==0x6FB) then
    local mode=os.getenv("SW_NAMEMODE")
    local t={}; local i=0
    while i<24 do local v=rd(p+i); t[#t+1]=v; if v==6 or v==0 then break end; i=i+1 end
    local hex={} for _,v in ipairs(t) do hex[#hex+1]=string.format("%02X",v) end
    log(string.format("NAME %06X bf=%d %s",p,bf,table.concat(hex," ")))
    local raw={} for k=0,19 do raw[#raw+1]=string.format("%02X",rd(p+k)) end
    log(string.format("NAMERAW %06X bf=%d %s",p,bf,table.concat(raw," ")))
    if mode and mode:sub(1,3)=="sub" then  -- 진단: `84 06`(「임」 코드) → `84 NN`(sub07 = 07)
      local nn=tonumber(mode:sub(4),16)
      for k=0,18 do if rd(p+k)==0x84 and rd(p+k+1)==0x06 then wr(p+k+1,nn); log("NAME sub "..k) end end
    end
    if mode=="nospace" or mode=="fwspace" then
      local out={}
      local k=1
      while k<=#t do
        local v=t[k]
        if v==0x20 then
          if mode=="fwspace" then out[#out+1]=0x80; out[#out+1]=0x00 end
        elseif v>=0x80 and v<=0x87 then out[#out+1]=v; out[#out+1]=t[k+1]; k=k+1
        else out[#out+1]=v end
        k=k+1
      end
      for j,v in ipairs(out) do wr(p+j-1,v) end
      log("NAME->"..mode)
    end
  end
  cur={start=bf, n=msgn}   -- 찍기 전에 기다린다: 창 안쪽이 안정될 때까지(아래 NMI 쪽에서 찍는다)
  boost()
  if state=="run" and not WINMODE then
    local ph=(bf//1000)%2
    enemies(function(b) wr16(b+6,9999); wr16(b+4, ph==0 and 9999 or 2500) end)
  else
    enemies(function(b) if WINKILL then wr16(b+4,0); wr(b,rd(b)|0x80) elseif rd16(b+4)>1 then wr16(b+4,1) end end)  -- 0 이 된 적을 1 로 되살리지 않는다(되살리면 쓰러뜨릴 수 없다)
  end
end, emu.callbackType.exec, 0xC0A6E8, 0xC0A6E8, emu.cpuType.snes)
local WTRP=tonumber(os.getenv("SW_WTRAP") or "0")  -- 진단: 이 주소(24비트 hex, WRAM 은 7E 뱅크)에 쓰기가 일어날 때 PC·값(앞 N개)
if WTRP~=0 then local wn=0
  emu.addMemoryCallback(function(addr,val)
    wn=wn+1; if wn>(tonumber(os.getenv("SW_TRAPN") or "3")) then return end
    local q=emu.getState(); log(string.format("WTRAP bf=%d pc=%02X:%04X val=%02X",bf,q["cpu.k"],q["cpu.pc"],val or -1))
  end, emu.callbackType.write, WTRP, WTRP, emu.cpuType.snes)
end
-- 진단: 주소 범위(SW_WRANGE="시작-끝" hex 24비트, WRAM 은 7E/7F 뱅크)의 쓰기를 전투 프레임 SW_WFROM~SW_WTO 사이에 전부(최대 SW_WMAX 줄) 로그 — 누가 어느 타일을 덮는지(10-24 붉은 슬라임 글줄 겹침)
local WRG=os.getenv("SW_WRANGE")
if WRG then
  local lo,hi=WRG:match("(%x+)-(%x+)"); lo=tonumber(lo,16); hi=tonumber(hi,16)
  local wf,wt,wm=tonumber(os.getenv("SW_WFROM") or "0"),tonumber(os.getenv("SW_WTO") or "99999"),tonumber(os.getenv("SW_WMAX") or "4000"); local wc=0
  emu.addMemoryCallback(function(addr,val)
    if bf<wf or bf>wt then return end
    wc=wc+1; if wc>wm then return end
    local q=emu.getState()
    local pb=os.getenv("SW_WPCBANK")  -- 진단: 이 뱅크(hex, 콤마)의 PC 쓰기만 — 전투 AI(`$D4`·`$D5`)가 이름 버퍼를 건드리는 곳
    if pb then local ok=false for b in pb:gmatch("%x+") do if tonumber(b,16)==q["cpu.k"] then ok=true end end if not ok then wc=wc-1 return end end
    log(string.format("WR j=%d bf=%d pc=%02X:%04X addr=%06X val=%02X",(JOBS[job] and JOBS[job][1]) or -1,bf,q["cpu.k"],q["cpu.pc"],addr,val or -1))
  end, emu.callbackType.write, lo, hi, emu.cpuType.snes)
end
-- 진단: 전투 프레임 SW_VRAMDUMP(콤마 목록)에 캔버스(WRAM $7F:BF28~$C627)와 VRAM 전체를 파일로 — 글줄 타일이 VRAM 에서 덮였는지(10-24)
local VD={} for v in (os.getenv("SW_VRAMDUMP") or ""):gmatch("%d+") do VD[tonumber(v)]=true end
emu.addEventCallback(function()
  if VD[bf] then
    local h=io.open(string.format("%s/canvas_%05d.bin",OUT,bf),"wb"); for i=0,0x6FF do h:write(string.char(emu.read(0x7FBF28+i,emu.memType.snesMemory,false))) end h:close()
    local g=io.open(string.format("%s/vram_%05d.bin",OUT,bf),"wb"); for i=0,0xFFFF do g:write(string.char(emu.read(i,emu.memType.snesVideoRam,false))) end g:close()
    log("VRAMDUMP bf="..bf)
  end
end, emu.eventType.endFrame)
-- 진단: 이 주소들(SW_EXECLIST, hex 콤마)에 실행이 닿으면 군·프레임을 로그 — 전투 AI 의 이름 버퍼 쓰기 자리가 어느 군에서 도는지(10-24)
for v in (os.getenv("SW_EXECLIST") or ""):gmatch("%x+") do local ad=tonumber(v,16)
  emu.addMemoryCallback(function() log(string.format("EXEC %06X j=%d bf=%d",ad,(JOBS[job] and JOBS[job][1]) or -1,bf)) end, emu.callbackType.exec, ad, ad, emu.cpuType.snes) end
local TRP=tonumber(os.getenv("SW_TRAP") or "0")  -- 진단: 이 SNES 주소(hex)에 처음 닿을 때 레지스터·스택을 로그로(멈춘 군에서 어디서 들어왔나)
if TRP~=0 then local n=0
  emu.addMemoryCallback(function()
    if bf<(tonumber(os.getenv("SW_TRAPFROM") or "0")) then return end
    n=n+1; if n>(tonumber(os.getenv("SW_TRAPN") or "3")) then return end
    local q=emu.getState(); local sp=q["cpu.sp"]; local t={}
    for k=1,24 do t[#t+1]=string.format("%02X",emu.read(sp+k,emu.memType.snesMemory,false)) end
    log(string.format("TRAP bf=%d pc=%02X:%04X a=%04X x=%04X y=%04X sp=%04X stk=%s",bf,q["cpu.k"],q["cpu.pc"],q["cpu.a"],q["cpu.x"],q["cpu.y"],sp,table.concat(t," ")))
  end, emu.callbackType.exec, TRP, tonumber(os.getenv("SW_TRAPEND") or TRP), emu.cpuType.snes)
end
emu.addEventCallback(function() f=f+1
  if DUMP and f%DUMP==0 and (state=="run" or state=="finish") then local q=emu.getState(); local sp=q["cpu.sp"]; local t={}; for k=1,20 do t[#t+1]=string.format("%02X",emu.read(sp+k,emu.memType.snesMemory,false)) end
    log(string.format("EF bf=%d %02X:%04X a=%04X x=%04X y=%04X d=%04X sp=%04X stk=%s",bf,q["cpu.k"],q["cpu.pc"],q["cpu.a"],q["cpu.x"],q["cpu.y"],q["cpu.d"],sp,table.concat(t," "))) end
end, emu.eventType.endFrame)
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
    if WRAMDUMP and bf==WRAMDUMP then local h=io.open(OUT.."/wram_"..bf..".bin","wb"); local t={}; for a=0,0x1FFF do t[#t+1]=string.char(rd(a)) end; h:write(table.concat(t)); h:close() end  -- 진단: WRAM 0000~1FFF 통째
    if DUMP and bf%DUMP==0 then  -- 진단: 8칸(아군 0~3·적 4~7)의 0x40B 상태를 로그로 — 멈춘 군의 원인 찾기(10-24)
      local st_=emu.getState(); log(string.format("PC bf=%d %02X:%04X a=%04X",bf,st_["cpu.k"],st_["cpu.pc"],st_["cpu.a"]))
      for i=0,7 do local b=0x050B+i*0x40; local t={}
        for k=0,0x3F do t[#t+1]=string.format("%02X",rd(b+k)) end
        log(string.format("S bf=%d slot=%d %s",bf,i,table.concat(t," "))) end
    end
    if state=="run" and bf>=FRAMES then state="finish"; finish_at=bf; log("FINISH "..job.." bf="..bf) end
    if state=="finish" and bf>=finish_at+300 then
      shot(string.format("%s/%05d_end.png",dir,bf),true)
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
  if WINMODE and S0~=nil and (state=="run" or state=="finish") and f%24<3 then b.a=true end  -- 승리·획득 메시지는 키 대기 — 완료 시험은 A 를 눌러 넘긴다
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
