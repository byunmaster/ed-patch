-- 대화형 서버: 부팅 대사 넘기기 뒤 cmd.txt 를 기다려 한 명령씩 실행. 명령: 1행 SCRIPT(시작:길이:버튼+..) 2행 SHOTS 3행 REL 최대프레임 4행 extra(dump=경로 loadsrm=경로 poke=addr=val,.. quit=1 hexdump=...)
local OUT=os.getenv("SW_OUT")
local WR=emu.memType.snesWorkRam
local SR=emu.memType.snesSaveRam
local f=0
local function rd(a) return emu.read(a,WR,false) end
local h=io.open(os.getenv("SW_STATE"),"rb"); local S0=h:read("*a"); h:close()
local OFF=tonumber(os.getenv("SW_OFF") or "2800")
local started=false
local cmdno=0
local T,SH,MAXREL,c0,active={}, {}, 0, 0, false
local POKE=nil
local DBG=io.open(os.getenv("SW_OUT").."/dbg.txt","a")
local function dbg(x) DBG:write(x.."\n"); DBG:flush() end
dbg("start")
local function wr(a,v) emu.write(a,v,WR) end
local function shot(name) local fh=io.open(OUT.."/"..name..".png","wb"); fh:write(emu.takeScreenshot()); fh:close() end
local function readcmd()
  local fh=io.open(OUT.."/cmd.txt","r"); if not fh then return nil end
  local s=fh:read("*a"); fh:close(); os.remove(OUT.."/cmd.txt"); return s
end
local function loadcmd(s)
  local L={} for line in (s.."\n"):gmatch("([^\n]*)\n") do L[#L+1]=line end
  T={} for a,b,c in (L[1] or ""):gmatch("(%d+):(%d+):([%w+]+)") do local bt={} for n in c:gmatch("%w+") do bt[#bt+1]=n end T[#T+1]={tonumber(a),tonumber(b),bt} end
  SH={} for v in (L[2] or ""):gmatch("%d+") do SH[tonumber(v)]=true end
  MAXREL=tonumber(L[3]) or 60
  local ex=L[4] or ""
  local p=ex:match("poke=(%S+)"); if p then POKE=p end
  if ex:match("nopoke") then POKE=nil end
  local lp=ex:match("loadsrm=(%S+)")
  if lp then local fh=io.open(lp,"rb"); local d=fh:read("*a"); fh:close(); for i=1,#d do emu.write(i-1,d:byte(i),SR) end end
  local dp=ex:match("dump=(%S+)")
  local wd=ex:match("wram=(%S+)")
  if ex:match("quit=1") then emu.stop(0) end
  cmdno=cmdno+1; c0=f; active=true
  return dp,wd
end
local pendDump,pendW=nil,nil
emu.addMemoryCallback(function() if not started then started=true; emu.loadSavestate(S0); f=0; dbg("loaded") end end, emu.callbackType.exec, 0xC00FC0, 0xC00FC0, emu.cpuType.snes)
emu.addEventCallback(function()
  if not started then return end
  f=f+1
  if active then
    local k=f-c0
    if SH[k] then shot(string.format("c%03d_%05d",cmdno,k)) end
    if POKE and f%20==0 then for a_,v_ in string.gmatch(POKE,"(%x+)=(%x+)") do wr(tonumber(a_,16),tonumber(v_,16)) end end
    if k>=MAXREL then
      active=false
      if pendDump then local fh=io.open(pendDump,"wb"); for i=0,0x1FFF do fh:write(string.char(emu.read(i,SR,false))) end fh:close(); pendDump=nil end
      if pendW then local fh=io.open(pendW,"wb"); for i=0,0x1FFF do fh:write(string.char(rd(i))) end fh:close(); pendW=nil end
      local fh=io.open(OUT.."/done.txt","w"); fh:write("done "..cmdno.." f="..f.."\n"); fh:close()
    end
  end
  if not active and f>OFF then
    if not DONEIDLE then DONEIDLE=true; dbg("idle-loop f="..f) end; local idle=0
    while true do
      local s=readcmd()
      if s then local d,w=loadcmd(s); pendDump=d; pendW=w; os.remove(OUT.."/done.txt"); break end
      local t0=os.clock(); while os.clock()-t0<0.15 do end; idle=idle+1
      if idle>6000 then emu.stop(0) end  -- 15분 무명령이면 종료(칸 반납)
    end
  end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if started and f<OFF-100 and f%30<4 then b.a=true end
  if active then local k=f-c0; for _,t in ipairs(T) do if k>=t[1] and k<t[1]+t[2] then for _,n in ipairs(t[3]) do b[n]=true end end end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
