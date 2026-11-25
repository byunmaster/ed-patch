-- 조사용: 부팅→필드 동안 쓰기가 한 번도 없는 WRAM 구간을 찾는다(디버그 진입키 상태 바이트 자리). RF_LO/RF_HI = WRAM 오프셋(0x00000~0x1FFFF)
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local lo, hi = tonumber(os.getenv("RF_LO")), tonumber(os.getenv("RF_HI"))
local wr = {}
emu.addMemoryCallback(function(a, v) wr[a] = (wr[a] or 0) + 1 end, emu.callbackType.write, lo, hi, emu.cpuType.snes, emu.memType.snesWorkRam)
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
emu.addEventCallback(function()
  if L.f >= 3600 then
    local n = 0
    for a = lo, hi do if not wr[a] then n = n + 1 end end
    L.log(string.format("FREE %05X-%05X unwritten=%d/%d", lo, hi, n, hi - lo + 1))
    for a = lo, hi do if wr[a] then L.log(string.format("W %05X x%d", a, wr[a])) end end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
