-- 조사용(QA 디버그 워프): 맵 번호(`$1231`)·전환 레코드(`$0933~`)·`$0609` 에 쓰는 곳의 PC 를 기록한다. MW_LIST="주소hex,…"(WRAM 오프셋), RP_SCRIPT 는 real_play 와 같다.
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
for hx in string.gmatch(os.getenv("MW_LIST") or "1231", "%x+") do
  local a = tonumber(hx, 16)
  emu.addMemoryCallback(function(addr, val)
    if L.f < tonumber(os.getenv("MW_FROM") or "0") then return end
    n = n + 1
    if n > 400 then return end
    local st = emu.getState()
    local pc = (st["cpu.k"] or 0) * 65536 + (st["cpu.pc"] or 0)
    L.log(string.format("W %04X=%02X pc=%06X f=%d 1231=%02X 0609=%02X 1467=%02X", addr, val or -1, pc, L.f, L.rd(0x1231), L.rd(0x0609), L.rd(0x1467)))
  end, emu.callbackType.write, a, a, emu.cpuType.snes, emu.memType.snesWorkRam)
end
local MAXF = tonumber(os.getenv("RP_MAXF") or "3000")
local shots = {}
for f in string.gmatch(os.getenv("RP_SHOTS") or "", "%d+") do shots[tonumber(f)] = true end
emu.addEventCallback(function()
  if shots[L.f] then L.shot(L.OUT .. string.format("/shots/p%05d.png", L.f)) end
  if L.f >= MAXF then emu.stop(0) end
end, emu.eventType.endFrame)
