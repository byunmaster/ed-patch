-- 조사용(10-24 디버그 진입키): 세이브를 불러 필드에서 JF 프레임에 디버그 메뉴 진입점으로 PC 를 옮긴다(롬 불변) — 필드에서 열어도 화면·입력이 서는지 본다.
-- 환경: RP_SCRIPT(real_play 와 같다 — 부팅·세이브 불러오기) · DJ_FRAME 점프 프레임 · DJ_PC 진입점(0x02FB4D 메뉴 B · 0x02FA34 메뉴 A) · RP_SHOTS · RP_MAXF
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
local JF = tonumber(os.getenv("DJ_FRAME") or "3400")
local PC = tonumber(os.getenv("DJ_PC") or "0x02FB4D")
local jumped = false
emu.addMemoryCallback(function()
  if jumped or L.f < JF then return end
  jumped = true
  local st = emu.getState()
  L.log(string.format("JUMP f=%d from %02X:%04X ps=%s", L.f, st["cpu.k"], st["cpu.pc"], tostring(st["cpu.ps"])))
  st["cpu.k"] = (PC >> 16) & 0xFF; st["cpu.pc"] = PC & 0xFFFF
  st["cpu.ps"] = (st["cpu.ps"] or 0) | 0x30 -- 8비트 문맥(`$02:F57F` 의 SEP #$30)
  emu.setState(st)
end, emu.callbackType.exec, 0x0087D1, 0x0087D1, emu.cpuType.snes)
emu.addEventCallback(function()
  local b = {}
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
local done = false
emu.addEventCallback(function()
  if shots[L.f] then L.shot(string.format("%s/shots/p%05d.png", L.OUT, L.f)) end
  if L.f >= MAXF and not done then done = true; L.log("END f=" .. L.f); emu.stop(0) end
end, emu.eventType.endFrame)
