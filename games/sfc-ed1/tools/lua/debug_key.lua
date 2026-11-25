-- 디버그 진입키 검증(10-24, 11-07 갱신): 세이브를 불러 RP_SCRIPT 의 입력을 넣고(**주메뉴를 먼저 연다 — `2100:b:6` — 그 뒤 `l+r+select`(+`x`) 60프레임 이상**; 옛 필드 L+R 은 더는 안 열린다), 조이패드 읽기(`$00:AAC2`) 호출 수·카운터($1F42)·메뉴 진입을 로그한다.
-- 환경: RP_SCRIPT(부팅·세이브 불러오기 + 시험 입력, real_play 와 같은 꼴) · RP_SHOTS · RP_MAXF · DK_FROM 로그 시작 프레임(기본 3300)
-- 로그: DISP f=… 호출(`$00:AAC2` 프레임마다) · MENU B/A f=… 진입 · CNT f=… 카운터가 바뀔 때 · MIRROR/WARP/... 디스패치가 실제로 간 곳
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local sched = {}
for f, keys, d in string.gmatch(os.getenv("RP_SCRIPT") or "", "(%d+):([%w+]+):(%d+)") do
  local ks = {}
  for k in string.gmatch(keys, "[^+]+") do ks[#ks + 1] = k end
  sched[#sched + 1] = { tonumber(f), ks, tonumber(d) }
end
local shots = {}
for f in string.gmatch(os.getenv("RP_SHOTS") or "", "%d+") do shots[tonumber(f)] = true end
local MAXF = tonumber(os.getenv("RP_MAXF") or "3000")
local FROM = tonumber(os.getenv("DK_FROM") or "3300")
local calls, last = 0, -1
emu.addMemoryCallback(function()
  if L.f < FROM then return end
  calls = calls + 1
  local c = L.rd(0x1F42)
  if c ~= last then L.log(string.format("CNT f=%d calls=%d cnt=%d", L.f, calls, c)); last = c end
end, emu.callbackType.exec, 0x00AAC2, 0x00AAC2, emu.cpuType.snes)
-- DK_POKE="주소=값,…" 를 필드가 선 뒤(DK_POKEF, 기본 3320)에 WRAM 에 쓴다 — 예: 거울 소지 `0x1201=0x54`
-- DK_POKE2="프레임:주소=값,…" 프레임마다 쓰기(메뉴 안에서 편성 번호 등)
for f, a, v in string.gmatch(os.getenv("DK_POKE2") or "", "(%d+):(0x%x+)=(0x%x+)") do
  local ff, aa, vv = tonumber(f), tonumber(a), tonumber(v)
  emu.addEventCallback(function() if L.f == ff then L.wr(aa, vv) end end, emu.eventType.endFrame)
end
local poked = false
emu.addEventCallback(function()
  if not poked and L.f >= tonumber(os.getenv("DK_POKEF") or "3320") then
    poked = true
    for a, v in string.gmatch(os.getenv("DK_POKE") or "", "(0x%x+)=(0x%x+)") do L.wr(tonumber(a), tonumber(v)) end
  end
end, emu.eventType.endFrame)
emu.addMemoryCallback(function() L.log(string.format("MIRROR_TRY f=%d", L.f)) end, emu.callbackType.exec, 0x0088BB, 0x0088BB, emu.cpuType.snes)
local function hit(name) return function() L.log(string.format("%s f=%d", name, L.f)) end end
emu.addMemoryCallback(hit("MENU_B"), emu.callbackType.exec, 0x02FB4D, 0x02FB4D, emu.cpuType.snes)
emu.addMemoryCallback(hit("MENU_A"), emu.callbackType.exec, 0x02FA34, 0x02FA34, emu.cpuType.snes)
emu.addMemoryCallback(hit("DISPATCH_ORIG"), emu.callbackType.exec, 0x00882F, 0x00882F, emu.cpuType.snes)
emu.addMemoryCallback(hit("SKILL_WINDOW"), emu.callbackType.exec, 0x008855, 0x008855, emu.cpuType.snes)
emu.addEventCallback(function()
  local b = {}
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
local done = false
emu.addEventCallback(function()
  if os.getenv("DK_PC") and L.f >= tonumber(os.getenv("DK_PC")) and L.f < tonumber(os.getenv("DK_PC")) + 40 then
    local st = emu.getState()
    L.log(string.format("PC f=%d %02X:%04X sp=%04X", L.f, st["cpu.k"], st["cpu.pc"], st["cpu.sp"]))
  end
  if shots[L.f] then L.shot(string.format("%s/shots/p%05d.png", L.OUT, L.f)) end
  if L.f >= MAXF and not done then done = true; local st = emu.getState()
    L.log(string.format("END f=%d calls=%d pc=%02X:%04X ps=%s s=%04X flag=%02X start=%02X ctr=%02X", L.f, calls, st["cpu.k"], st["cpu.pc"], tostring(st["cpu.ps"]), st["cpu.sp"], L.rd(0x1F42), L.rd(0x1F43), L.rd(0x05EF))); emu.stop(0) end
end, emu.eventType.endFrame)
