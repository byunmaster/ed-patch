-- 조사용: PS_PCS="주소hex,…" 실행 때 PC·스택 위 24바이트·주요 RAM 을 기록한다(RP_SCRIPT·RP_SRM 은 map_watch 와 같다).
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local sched = {}
for f, keys, d in string.gmatch(os.getenv("RP_SCRIPT") or "", "(%d+):([%w+]+):(%d+)") do
  local ks = {}
  for k in string.gmatch(keys, "[^+]+") do ks[#ks + 1] = k end
  sched[#sched + 1] = { tonumber(f), ks, tonumber(d) }
end
emu.addEventCallback(function()
  local b = {}
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
local SRM = os.getenv("RP_SRM")
local done = false
emu.addEventCallback(function()
  if SRM and not done and L.f >= 5 then
    done = true
    local fh = io.open(SRM, "rb"); local data = fh:read("a"); fh:close()
    for i = 1, #data do emu.write(i - 1, string.byte(data, i), emu.memType.snesSaveRam) end
    emu.reset()
  end
end, emu.eventType.endFrame)
local n = 0
local FROM = tonumber(os.getenv("MW_FROM") or "0")
for hx in string.gmatch(os.getenv("PS_PCS") or "", "%x+") do
  local a = tonumber(hx, 16)
  emu.addMemoryCallback(function()
    if L.f < FROM then return end
    n = n + 1
    if n > 60 then return end
    local st = emu.getState()
    local sp = st["cpu.sp"]
    local t = {}
    for i = 1, 24 do t[#t + 1] = string.format("%02X", emu.read(sp + i, emu.memType.snesMemory, false)) end
    L.log(string.format("X %06X f=%d sp=%04X stack=%s 1467=%02X 1468=%02X 1231=%02X", a, L.f, sp, table.concat(t, " "), L.rd(0x1467), L.rd(0x1468), L.rd(0x1231)))
  end, emu.callbackType.exec, a, a, emu.cpuType.snes)
end
local MAXF = tonumber(os.getenv("RP_MAXF") or "3000")
-- 조사용: 걸음 함수 `$00:AF95` 호출마다 그 호출 안에서 처음 실행된 PC 순서와 시작 좌표를 기록한다(막힌/열린 걸음 대조).
-- ST_FROM=프레임 ST_N=기록할 호출 수(기본 40). 로그 한 줄 = `CALL f= pos=x,y seq=…`
local FROMF, NMAX = tonumber(os.getenv("ST_FROM") or "0"), tonumber(os.getenv("ST_N") or "40")
local cur, seen, calls = nil, {}, 0
local function flush()
  if cur then
    L.log(string.format("CALL f=%d pos=%d,%d dir=%02X seq=%s", cur.f, cur.x, cur.y, cur.d, table.concat(cur.seq, " ")))
  end
  cur = nil
end
emu.addMemoryCallback(function()
  if L.f < FROMF or calls >= NMAX then return end
  flush(); calls = calls + 1; seen = {}
  cur = { f = L.f, x = L.rd16(0x1245), y = L.rd16(0x1247), d = L.rd(0x05FA), seq = {} }
end, emu.callbackType.exec, 0x00AF95, 0x00AF95, emu.cpuType.snes)
local armed = false
emu.addEventCallback(function()
  if not armed and L.f >= FROMF - 1 then
    armed = true
    emu.addMemoryCallback(function(a)
      if cur and not seen[a] then seen[a] = true; cur.seq[#cur.seq + 1] = string.format("%04X", a & 0xFFFF) end
    end, emu.callbackType.exec, 0x00A000, 0x00CFFF, emu.cpuType.snes)
  end
end, emu.eventType.endFrame)
emu.addEventCallback(function() if calls >= NMAX and cur then flush() end end, emu.eventType.endFrame)
