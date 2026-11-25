-- 오프닝 크롤 보기: 타이틀에서 Start 를 눌러 새 게임(오프닝)으로 들어가 OV_EVERY 프레임마다 찍는다(입력은 OV_SCRIPT "프레임:키+키:길이,…" 만).
-- 환경: OV_MAXF 끝 프레임(기본 6000) · OV_EVERY 캡처 간격(기본 30) · OV_SCRIPT. 산출: shots/o<프레임>.png · log.txt
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local MAXF = tonumber(os.getenv("OV_MAXF") or "6000")
local EVERY = tonumber(os.getenv("OV_EVERY") or "30")
local sched = {}
for f, keys, d in string.gmatch(os.getenv("OV_SCRIPT") or "300:start:10,1100:start:6", "(%d+):([%w+]+):(%d+)") do
  local ks = {}
  for k in string.gmatch(keys, "[^+]+") do ks[#ks + 1] = k end
  sched[#sched + 1] = { tonumber(f), ks, tonumber(d) }
end
emu.addEventCallback(function()
  if L.f % EVERY == 0 then L.shot(string.format("%s/shots/o%05d.png", L.OUT, L.f)) end
  if L.f >= MAXF then L.log("END"); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b = {}
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
