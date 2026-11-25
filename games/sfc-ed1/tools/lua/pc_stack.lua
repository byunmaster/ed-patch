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
emu.addEventCallback(function() if L.f >= MAXF then emu.stop(0) end end, emu.eventType.endFrame)
-- PS_TRACE="a-b": 프레임 a..b 에서 처음 실행된 PC 를 실행 순서대로 (뱅크 00~02, 19~1D, 3F) 한 줄에 기록한다.
local ta, tb = (os.getenv("PS_TRACE") or ""):match("(%d+)-(%d+)")
if ta then
  ta, tb = tonumber(ta), tonumber(tb)
  local seen, order = {}, {}
  local function hook(lo, hi)
    emu.addMemoryCallback(function(addr)
      if L.f >= ta and L.f <= tb and not seen[addr] then seen[addr] = true; order[#order + 1] = addr end
    end, emu.callbackType.exec, lo, hi, emu.cpuType.snes)
  end
  for _, b in ipairs({ 0x00, 0x01, 0x02, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x3F }) do hook(b * 65536 + 0x8000, b * 65536 + 0xFFFF) end
  emu.addEventCallback(function()
    if L.f == tb + 1 then
      local t = {}
      for _, ad in ipairs(order) do t[#t + 1] = string.format("%06X", ad) end
      L.log("TRACE " .. table.concat(t, " "))
    end
  end, emu.eventType.endFrame)
end
