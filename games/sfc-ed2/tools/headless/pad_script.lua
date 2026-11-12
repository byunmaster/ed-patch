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
-- SW_RWATCH="시작주소,끝주소,시작프레임,끝프레임"(hex WRAM 주소 · OFF 기준 프레임) — 구간의 **읽기**를 (주소, PC) 쌍별 한 번씩 rw.txt 로(누가 이 변수를 읽나)
local RW=os.getenv("SW_RWATCH")
if RW then
  local a0,a1,f0,f1=RW:match("(%x+),(%x+),(%d+),(%d+)")
  f0=tonumber(f0); f1=tonumber(f1)
  local seen={}
  local rh=io.open(OUT.."/rw.txt","w")
  emu.addMemoryCallback(function(a,v)
    local k=f-OFF
    if k<f0 or k>f1 then return end
    local st=emu.getState()
    local key=string.format("%04X %02X:%04X",a,st["cpu.k"] or 0,st["cpu.pc"] or 0)
    if not seen[key] then seen[key]=true; rh:write(k.." "..key.."\n"); rh:flush() end
  end,emu.callbackType.read,tonumber(a0,16),tonumber(a1,16),emu.cpuType.snes,emu.memType.snesWorkRam)
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
  if os.getenv("SW_POKE") and f%20==0 and k>=(tonumber(os.getenv("SW_POKEFROM") or "0")) then  -- 진단·플레이: WRAM 주입("addr=val,…" hex, 20프레임마다) — 돈·경험치 부스트용(플래그·진행 변수는 만지지 않는다)
    for a_,v_ in string.gmatch(os.getenv("SW_POKE"),"(%x+)=(%x+)") do wr(tonumber(a_,16),tonumber(v_,16)) end
  end
  if f>(tonumber(os.getenv("SW_MAXF") or "4300")) then log("DONE"); LOG:close(); emu.stop(0) end
end, emu.eventType.endFrame)
-- SW_NAV="시작프레임;x:y:o;…"(OFF 기준) — 좌표 `$038C`·`$038E`(8px 타일)를 읽어 길목(웨이포인트)을 차례로 걷는다(o=h 가로 먼저·v 세로 먼저). 60프레임 제자리면 다음 길목으로 넘어간다.
local NAV={}
local NAVSTART=0
do
  local ns=os.getenv("SW_NAV")
  if ns then
    NAVSTART=tonumber(ns:match("^(%d+)")) or 0
    for x,y,o in ns:gmatch("(%d+):(%d+):(%a)") do NAV[#NAV+1]={tonumber(x),tonumber(y),o} end
  end
end
local navi,navlast,navstill=1,nil,0
-- SW_WANDER="시작프레임;씨앗[;멈춤프레임]" — (멈춤 이후는 대본 입력만) 길목 없이 마구 걷는다(막히면 방향을 바꾸고 150프레임마다 a). 20프레임마다 좌표를 wander.txt 에 남겨 지도 전환(좌표 뜀)·상점 진입을 나중에 찾는다.
local WN=os.getenv("SW_WANDER")
local WSTART,WSEED=0,1
local WSTOP=1e9
if WN then WSTART=tonumber(WN:match("^(%d+)")) or 0; WSEED=tonumber(WN:match(";(%d+)")) or 1; WSTOP=tonumber(WN:match(";%d+;(%d+)")) or 1e9 end
local wdir,wlast,wstill,wrng="down",nil,0,WSEED*7919
local function wrand(n) wrng=(wrng*1103515245+12345)%2147483648; return (math.floor(wrng/65536)%n)+1 end
local WL=WN and io.open(OUT.."/wander.txt","w")
emu.addEventCallback(function()
  local b={}
  if WN and started and f>=OFF+WSTART and f<OFF+WSTOP then
    local x,y=rd(0x38c),rd(0x38e)
    if (f-OFF)%20==0 then WL:write(string.format("%d %d %d %02x\n",f-OFF,x,y,rd(0x39d))); WL:flush() end
    local cur=x*256+y
    if cur==wlast then wstill=wstill+1 else wstill=0 end
    wlast=cur
    if wstill>=2 or (f-OFF)%90==0 then local d={"up","down","left","right"}; wdir=d[wrand(4)]; wstill=0 end
    b[wdir]=true
    if (f-OFF)%70<4 then b.a=true; b[wdir]=nil end
  end
  if #NAV>0 and started and f>=OFF+NAVSTART and navi<=#NAV then
    local w=NAV[navi]
    local x,y=rd(0x38c),rd(0x38e)
    local cur=x*256+y
    if cur==navlast then navstill=navstill+1 else navstill=0 end
    navlast=cur
    local dx,dy=w[1]-x,w[2]-y
    local function hor() if dx>1 then b.right=true elseif dx<-1 then b.left=true end end
    local function ver() if dy>1 then b.down=true elseif dy<-1 then b.up=true end end
    local needh,needv=(dx>1 or dx<-1),(dy>1 or dy<-1)
    if not needh and not needv then navi=navi+1; navstill=0
    elseif w[3]=="h" then if needh then hor() else ver() end
    else if needv then ver() else hor() end end
    if navstill>60 then navi=navi+1; navstill=0 end
  end
  if started and f<OFF-100 and f%30<4 then b.a=true end
  for _,t in ipairs(T) do if f>=OFF+t[1] and f<OFF+t[1]+t[2] then for _,n in ipairs(t[3]) do b[n]=true end end end
  emu.setInput(b,0)
end, emu.eventType.inputPolled)

-- SW_SHOPHIT=1 — 가게 UI 입구(`$C0:ED0D`)에 닿으면 shop.txt 에 프레임을 남기고 그 뒤 30·90·150프레임에 화면을 찍는다(걸어 다니며 가게를 찾는 시험용).
if os.getenv("SW_SHOPHIT") then
  local hits={}
  local SHF=io.open(OUT.."/shop.txt","a")
  emu.addMemoryCallback(function()
    hits[#hits+1]=f
    SHF:write(string.format("HIT f=%d map=%02X x=%d y=%d\n",f-OFF,rd(0x100),rd(0x38c),rd(0x38e))); SHF:flush()
  end,emu.callbackType.exec,0xC0ED0D,0xC0ED0D,emu.cpuType.snes)
  emu.addEventCallback(function()
    for _,h in ipairs(hits) do
      local d=f-h
      if d>=30 and d<=600 and d%30==0 then shot(string.format("shop%d_%d",h-OFF,d)) end
    end
  end,emu.eventType.endFrame)
end

-- SW_EXECLOG="주소hex,주소hex" — 그 주소를 실행할 때마다 execlog.txt 에 「프레임 주소 sp 스택 12바이트」(호출 경로 추적용)
if os.getenv("SW_EXECLOG") then
  local XL=io.open(OUT.."/execlog.txt","a")
  for ad in os.getenv("SW_EXECLOG"):gmatch("%x+") do
    local a=tonumber(ad,16)
    emu.addMemoryCallback(function()
      local q=emu.getState(); local sp=q["cpu.sp"]; local t={}
      for i=1,12 do t[#t+1]=string.format("%02X",emu.read(sp+i,emu.memType.snesMemory,false)) end
      XL:write(string.format("%d %06X sp=%04X %s\n",f-OFF,a,sp,table.concat(t," "))); XL:flush()
    end,emu.callbackType.exec,a,a,emu.cpuType.snes)
  end
end

-- SW_MOVE="프레임;맵;x;y|프레임;맵;x;y…" (OFF 기준, 여러 번 가능) — 디버그 이동: 엔진의 「목적지 기록으로 이동」 코드(`$C2:00E5` = `jsl $C1:A8B3` + `jml $C1:94F7`, 워프의 날개·문이 쓰는 길)를
-- 호출한다. 기록(25B: 01 · x2 · y2 · `$0100~` 블록 19B)을 WRAM `$7F:F000` 에 만들고 `$54~$56` 로 가리킨다. 새 맵의 NPC·이벤트가 정식으로 다시 만들어진다. 시험 전용.
local MV=os.getenv("SW_MOVE")
if MV then
  local jobs={}
  for jf,jm,jx,jy,js in MV:gmatch("(%d+);(%d+);(%d+);(%d+);?(%d*)") do jobs[#jobs+1]={tonumber(jf),tonumber(jm),tonumber(jx),tonumber(jy),false,tonumber(js)} end
  emu.addMemoryCallback(function()
    for _,jb in ipairs(jobs) do
      if not jb[5] and f>=OFF+jb[1] then
        jb[5]=true
        local mm,mx,my=jb[2],jb[3],jb[4]
        local rec={0x01,mx&255,mx>>8,my&255,my>>8,mm,0x02,jb[6] or 0x18,0,0,0,0x02,0xC0,0,0x03,0x01,0,0xFF,0x0D,0x10,0x11,0x0C,0x0B,0x16,0xAD}
        local WM=emu.memType.snesWorkRam
        for i,v in ipairs(rec) do emu.write(0x1F000+i-1,v,WM) end   -- $7F:F000
        emu.write(0x54,0x00,WM); emu.write(0x55,0xF0,WM); emu.write(0x56,0x7F,WM)
        local st=emu.getState(); st["cpu.pc"]=0x00E5; st["cpu.k"]=0xC2; st["cpu.ps"]=(st["cpu.ps"] or 0)|0x30; st["cpu.dbr"]=0
        emu.setState(st)
        local h=io.open(OUT.."/move.txt","a"); h:write(string.format("MOVE f=%d map=%d x=%d y=%d\n",f-OFF,mm,mx,my)); h:close()
        return
      end
    end
  end,emu.callbackType.exec,0xC00FC0,0xC00FC0,emu.cpuType.snes)
end

-- SW_MOVEREC="프레임;기록hex(25B)|…" — 목적지 기록을 통째로 준다(서장·단계별 마을 판 — 같은 맵 번호에 `$0107` 이벤트 번호만 다른 기록이 워프 표에 있다, `$CA:7225` 등).
local MR=os.getenv("SW_MOVEREC")
if MR then
  local jobs={}
  for jf,hx in MR:gmatch("(%d+);(%x+)") do local rec={} for b in hx:gmatch("%x%x") do rec[#rec+1]=tonumber(b,16) end jobs[#jobs+1]={tonumber(jf),rec,false} end
  emu.addMemoryCallback(function()
    for _,jb in ipairs(jobs) do
      if not jb[3] and f>=OFF+jb[1] then
        jb[3]=true
        local WM=emu.memType.snesWorkRam
        for i,v in ipairs(jb[2]) do emu.write(0x1F000+i-1,v,WM) end
        emu.write(0x54,0x00,WM); emu.write(0x55,0xF0,WM); emu.write(0x56,0x7F,WM)
        local st=emu.getState(); st["cpu.pc"]=0x00E5; st["cpu.k"]=0xC2; st["cpu.ps"]=(st["cpu.ps"] or 0)|0x30; st["cpu.dbr"]=0
        emu.setState(st)
        local h=io.open(OUT.."/move.txt","a"); h:write(string.format("MOVEREC f=%d\n",f-OFF)); h:close()
        return
      end
    end
  end,emu.callbackType.exec,0xC00FC0,0xC00FC0,emu.cpuType.snes)
end

-- ⚠ SW_MSG 화면의 **첫 줄(화자 머리 줄)은 믿지 않는다** — 창을 안 지우고 올려 앞 대사의 타일 줄이 남는다(11-06 「여관을 주무셨군요」 오인). 본문 줄만 본다. 같은 주소를 두 번 부르고 사이에 `a` 를 넣으면 본문 줄은 깨끗하다(앞 창이 열려 있어야 한다 — 닫힌 창에서 부르면 화면이 까맣게 된다). 같은 메시지를 `$C3:EDF1`(끝 쪽 `05`) 으로 부르면 창이 닫힌다.
-- SW_MSG="프레임;SNES주소hex|…"(OFF 기준) — 대사 단위를 진짜 필드에서 부른다(`$A6~$A8` = 주소, PC = `$C1:8F0B` — 이벤트 스크립트의 `jml $C1:8F0B` 와 같다). 「동료가 되었습니다」 같은 구조 토큰이 든 단위로 진행 상태(파티)를 바꾸는 시험용.
-- SW_CARD="프레임;SNES주소hex|…"(OFF 기준) — 장 끝 카드를 진짜 카드 출력 길로 부른다(`$CA:A5BE~A5DA` 와 같게: `$0130`←`$0131`, `$0131`=(`$0131`&C3)|0C, `$A6~$A8`=주소, PC=`$C0:A6E8`). 돌아갈 곳이 없어 카드 뒤는 믿지 않는다 — 카드 화면만 찍는 용도
local SCD=os.getenv("SW_CARD")
if SCD then
  local jobs={}
  for jf,ad in SCD:gmatch("(%d+);(%x+)") do jobs[#jobs+1]={tonumber(jf),tonumber(ad,16),false} end
  emu.addMemoryCallback(function()
    for _,jb in ipairs(jobs) do
      if not jb[3] and f>=OFF+jb[1] then
        jb[3]=true
        local WM=emu.memType.snesWorkRam
        local m31=emu.read(0x131,WM)
        emu.write(0x130,m31,WM); emu.write(0x131,(m31&0xC3)|0x0C,WM)
        emu.write(0xA6,jb[2]&255,WM); emu.write(0xA7,(jb[2]>>8)&255,WM); emu.write(0xA8,(jb[2]>>16)&255,WM)
        local st=emu.getState(); st["cpu.pc"]=0xA6E8; st["cpu.k"]=0xC0; st["cpu.ps"]=(st["cpu.ps"] or 0)|0x30; st["cpu.dbr"]=0
        emu.setState(st)
        local h=io.open(OUT.."/move.txt","a"); h:write(string.format("CARD f=%d %06X\n",f-OFF,jb[2])); h:close()
        return
      end
    end
  end,emu.callbackType.exec,0xC00FC0,0xC00FC0,emu.cpuType.snes)
end
local SMG=os.getenv("SW_MSG")
if SMG then
  local jobs={}
  for jf,ad in SMG:gmatch("(%d+);(%x+)") do jobs[#jobs+1]={tonumber(jf),tonumber(ad,16),false} end
  emu.addMemoryCallback(function()
    for _,jb in ipairs(jobs) do
      if not jb[3] and f>=OFF+jb[1] then
        jb[3]=true
        local WM=emu.memType.snesWorkRam
        emu.write(0xA6,jb[2]&255,WM); emu.write(0xA7,(jb[2]>>8)&255,WM); emu.write(0xA8,(jb[2]>>16)&255,WM)
        local st=emu.getState(); st["cpu.pc"]=0x8F0B; st["cpu.k"]=0xC1; st["cpu.ps"]=(st["cpu.ps"] or 0)|0x30; st["cpu.dbr"]=0
        emu.setState(st)
        local h=io.open(OUT.."/move.txt","a"); h:write(string.format("MSG f=%d %06X\n",f-OFF,jb[2])); h:close()
        return
      end
    end
  end,emu.callbackType.exec,0xC00FC0,0xC00FC0,emu.cpuType.snes)
end
