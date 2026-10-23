-- sfc-ed2 엔딩·후일담 전수 촬영 — 제품 롬 그대로. 타이틀에서 디버그 선택 1(`$137A`=0x81, 인자 `$1374`·`$1375`=0)로 「느닷없이 엔딩」을 띄운다(devlog 10-16).
-- 메시지 하나 뒤 엔딩이 입력 없이 흘러 스태프롤까지 간다. 화면이 EN_STABLE 프레임 안 변하면 찍고, 스크롤처럼 계속 변하는 구간은 EN_FORCE 프레임마다 찍는다.
-- 환경변수: SW_OUT · EN_AT(타이틀에서 쓰는 프레임) · EN_MAXF(끝 프레임) · EN_STABLE · EN_FORCE
local OUT=os.getenv("SW_OUT") or "out"
local WR=emu.memType.snesWorkRam
local AT=tonumber(os.getenv("EN_AT") or "900")
local MAXF=tonumber(os.getenv("EN_MAXF") or "45000")
local STABLE=tonumber(os.getenv("EN_STABLE") or "10")
local FORCE=tonumber(os.getenv("EN_FORCE") or "240")
local f=0
local LOG=io.open(OUT.."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local function wr(a,v) emu.write(a,v,WR) end
local function shot(path) local h=io.open(path,"wb"); h:write(emu.takeScreenshot()); h:close() end
local sched={ [100]={"start"} }
if os.getenv("EN_NEWGAME") then sched={ [100]={"start"}, [1700]={"a"}, [2300]={"down",5}, [2400]={"a"}, [3000]={"a"} } end   -- 처음부터 모험한다(dialog_sweep 와 같은 부팅 입력) — 디버그 값은 안 쓴다   -- 타이틀로 가는 부팅 입력(dialog_sweep 와 같다) — 이후는 EN_AT 에 디버그 값을 쓴다
-- 읽힌 바이트 기록(짝 표 행 대비 찍힌 행을 세려고) — $D7 뱅크와 그 뒤 확장 자리. 끝에 reads.txt 로 쓴다
local READS={}
if os.getenv("EN_READS") then
  emu.addMemoryCallback(function(a) READS[a]=true end, emu.callbackType.read, 0xD70000, 0xFFFFFF, emu.cpuType.snes)
end
local function dump_reads()
  if not os.getenv("EN_READS") then return end
  local h=io.open(OUT.."/reads.txt","w")
  local t={}; for a in pairs(READS) do t[#t+1]=a end; table.sort(t)
  for _,a in ipairs(t) do h:write(string.format("%06X\n",a)) end
  h:close()
end
local prevh,stable,lasth,lastf,n=nil,0,nil,0,0
local apress=0
local function hash()
  local b=emu.getScreenBuffer(); local h=5381
  for y=0,223,2 do local o=y*256; for x=0,255,2 do h=(h*33+(b[o+x+1] or 0))%4294967296 end end
  return h
end
emu.addEventCallback(function()
  f=f+1
  if os.getenv("EN_PRE") and f==AT-tonumber(os.getenv("EN_PRE")) then apress=6 end   -- 타이틀 로고에서 한 번 눌러 메뉴(모험을 계속한다…)로 간다
  if f==AT and not os.getenv("EN_NEWGAME") and not os.getenv("EN_PLAIN") then wr(0x137A,0x81); wr(0x1374,0); wr(0x1375,0); log("TRIGGER f="..f) end
  if os.getenv("EN_A") and f>AT+60 and f<AT+1500 and f%90==0 then apress=6 end
  if f>=AT then
    local h=hash()
    if prevh and h==prevh then stable=stable+1 else stable=0 end
    prevh=h
    local due=(f-lastf)>=FORCE
    if (stable==STABLE and h~=lasth) or (due and h~=lasth) then
      n=n+1; shot(string.format("%s/f%05d_%03d.png",OUT,f,n)); lasth=h; lastf=f
    end
  end
  if stable>=tonumber(os.getenv("EN_IDLE") or "1500") then log("IDLE-END f="..f); dump_reads(); LOG:close(); emu.stop(0) end   -- 스태프롤 뒤 화면이 오래 안 변하면 끝
  if f>=MAXF then log("END f="..f.." shots="..n); dump_reads(); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b={}
  if f<AT or os.getenv("EN_NEWGAME") then for k,v in pairs(sched) do local L=v[2] or 20; if f>=k and f<k+L then b[v[1]]=true end end end
  if apress>0 then b["a"]=true; apress=apress-1 end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)
