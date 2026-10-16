-- 실게임 흐름 재현(검수용): 세이브(SRAM)를 불러 필드에서 NPC 에게 말을 건다 — 테스트 필드·`$11FB` 같은 하네스 모드 없이 **실제 필드**로 간다.
-- 환경: RP_SCRIPT "프레임:버튼+버튼:길이;…"(예 `300:start:10;700:down+a:6`) · RP_SHOTS "프레임,프레임…" · RP_MAXF 끝 프레임(기본 3000)
-- 산출: shots/p<프레임>.png · log.txt(`MSG <번호> f=`: 메시지 입구 `$02:DCD3` 마다)
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
-- RP_SWAP=0x0979: 첫 메시지 입구(`$02:DCD3`)에서 번호를 RAM 으로 바꿔 친다(필드·창 위치는 실게임 그대로 — 4줄 등 시험 문안용)
local SWAP = tonumber(os.getenv("RP_SWAP") or "")
local swapped = false
L.on_message(function(id)
  if SWAP and not swapped and L.f > 3000 then
    swapped = true; L.wr(0x060B, SWAP & 255); L.wr(0x060C, SWAP >> 8); id = SWAP
  end
  L.log(string.format("MSG %04X f=%d", id, L.f))
end)
emu.addEventCallback(function()
  local b = {}
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
local done = false
local PINMAX = 0 -- 고정 칸(`pin` 표 = `$7E:4625 + 96 + 2*150`) 최대 수 — 슬롯 배정 한도 게이트의 예산 근거
local function pins()
  local n = 0
  for i = 0, 149 do if L.rd(0x4625 + 96 + 300 + i) ~= 0 then n = n + 1 end end
  if n > PINMAX then PINMAX = n; L.log("PINMAX " .. n .. " f=" .. L.f) end
end
emu.addEventCallback(function()
  if L.f % 30 == 0 then pins() end
  if shots[L.f] then L.shot(string.format("%s/shots/p%05d.png", L.OUT, L.f)) end
  if L.f >= MAXF and not done then done = true; L.log("END f=" .. L.f); emu.stop(0) end
end, emu.eventType.endFrame)
