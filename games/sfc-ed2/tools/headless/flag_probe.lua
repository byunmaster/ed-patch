-- 공유 꼬리 도달 탐침 — 대사 단위 SW_UNIT(hex)를 불러 SW_FLAGS(hex 플래그 번호, 쉼표)의 모든 켬/끔 조합마다
-- 포인터($A6~$A8)가 SW_TAIL(hex)부터 SW_TAILN(기본 0x200)바이트 안에 드는지 본다. 플래그 번호 n 은 WRAM $0167+(n>>3) 의 비트 n&7.
local WR=emu.memType.snesWorkRam
local function rd(a) return emu.read(a,WR,false) end
local function wr(a,v) emu.write(a,v,WR) end
local UNIT=tonumber(os.getenv("SW_UNIT"),16)
local TAIL=tonumber(os.getenv("SW_TAIL"),16)
local TN=tonumber(os.getenv("SW_TAILN") or "512")
local FL={}
for h in os.getenv("SW_FLAGS"):gmatch("%x+") do FL[#FL+1]=tonumber(h,16) end
local FB=tonumber(os.getenv("SW_FLAGBASE") or "167",16)
local FR=tonumber(os.getenv("SW_FRAMES") or "240")
local h=io.open(os.getenv("SW_STATE"),"rb"); local S=h:read("*a"); h:close()
local LOG=io.open(os.getenv("SW_OUT").."/log.txt","a")
local function log(s) LOG:write(s.."\n"); LOG:flush() end
local combo=-1; local uf=0; local hit=false; local started=false
local function setflag(n,v) local a=FB+(n>>3); local m=1<<(n&7); local c=rd(a); if v then c=c|m else c=c&(~m&255) end; wr(a,c) end
local function nextcombo()
  combo=combo+1
  if combo>=(1<<#FL) then log("ALLDONE"); LOG:close(); emu.stop(0); return false end
  emu.loadSavestate(S); uf=0; hit=false
  return true
end
local need=true
local nmi=0xC00FC0
emu.addMemoryCallback(function()
  if not started then started=true; log(string.format("01EF=%02X",0)); if not nextcombo() then return end; need=true; return end
  if need then
    need=false
    for i,n in ipairs(FL) do setflag(n,(combo>>(i-1))&1==1) end
    wr(0xA6,UNIT&255); wr(0xA7,(UNIT>>8)&255); wr(0xA8,(UNIT>>16)&255)
    return
  end
  uf=uf+1
  local p=rd(0xA6)|(rd(0xA7)<<8)|(rd(0xA8)<<16)
  if p>=TAIL and p<TAIL+TN then hit=true end
  if hit or uf>=FR then
    local s={} for i,n in ipairs(FL) do s[#s+1]=string.format("%04X=%d",n,(combo>>(i-1))&1) end
    log(string.format("COMBO %s hit=%s f=%d ptr=%06X",table.concat(s," "),tostring(hit),uf,p))
    if nextcombo() then need=true end
  end
end, emu.callbackType.exec, nmi, nmi, emu.cpuType.snes)
emu.addEventCallback(function() emu.setInput({},0) end, emu.eventType.inputPolled)
