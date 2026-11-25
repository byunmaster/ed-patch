-- 조사용: 필드에서 프레임마다 +1 되는 WRAM 바이트를 찾는다(FC_FROM 프레임부터 120프레임).
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local FROM = tonumber(os.getenv("FC_FROM") or "3400")
local prev, inc, n = nil, {}, 0
emu.addEventCallback(function()
  if L.f < FROM then return end
  local cur = {}
  for a = 0, 0x1FFF do cur[a] = L.rd(a) end
  if prev then
    n = n + 1
    for a = 0, 0x1FFF do
      if cur[a] == ((prev[a] + 1) & 255) then inc[a] = (inc[a] or 0) + 1 end
    end
  end
  prev = cur
  if n >= 120 then
    for a = 0, 0x1FFF do if (inc[a] or 0) >= 100 then L.log(string.format("INC %04X %d/120", a, inc[a])) end end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
