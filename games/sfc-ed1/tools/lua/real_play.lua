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
-- RP_SRM=<2048B .srm> RP_SRMF=<프레임>: 그 프레임에 SRAM 에 **직접 쓴다**(파일을 Saves/ 에 두는 건 안 읽힌다 — playbook 🔑. snesSaveRam 쓰기 + 리셋이 되는 길)
local SRM = os.getenv("RP_SRM")
local SRMF = tonumber(os.getenv("RP_SRMF") or "5")
local srmdone = false
emu.addEventCallback(function()
  if SRM and not srmdone and L.f >= SRMF then
    srmdone = true
    local fh = io.open(SRM, "rb")
    if not fh then L.log("SRM open fail " .. SRM); return end
    local data = fh:read("a"); fh:close()
    for i = 1, #data do emu.write(i - 1, string.byte(data, i), emu.memType.snesSaveRam) end
    L.log("SRM written " .. #data .. " f=" .. L.f)
    if os.getenv("RP_RESET") == "1" then emu.reset(); L.log("reset") end
  end
end, emu.eventType.endFrame)
if os.getenv("RP_PADLOG") then
  local a, b = os.getenv("RP_PADLOG"):match("(%d+)-(%d+)")
  emu.addEventCallback(function()
    if L.f >= tonumber(a) and L.f <= tonumber(b) then
      L.log(string.format("HW 4218=%02X 4219=%02X ", emu.read(0x4218, emu.memType.snesMemory, false), emu.read(0x4219, emu.memType.snesMemory, false)))
      L.log(string.format("PAD f=%d 05FA=%02X 05FB=%02X 1145=%02X 1146=%02X 1902=%02X 05DE=%02X 05DD=%02X", L.f, L.rd(0x05FA), L.rd(0x05FB), L.rd(0x1145), L.rd(0x1146), L.rd(0x1902), L.rd(0x05DE), L.rd(0x05DD)))
    end
  end, emu.eventType.endFrame)
end
for hx in string.gmatch(os.getenv("RP_PCS") or "", "%x+") do
  local a, n = tonumber(hx, 16), 0
  emu.addMemoryCallback(function()
    n = n + 1
    if n <= 12 then L.log(string.format("PC %06X f=%d n=%d 05DE=%02X 05F0=%02X", a, L.f, n, L.rd(0x05DE), L.rd(0x05F0))) end
  end, emu.callbackType.exec, a, a, emu.cpuType.snes)
end
if os.getenv("RP_RDPAD") then
  local a, b = os.getenv("RP_RDPAD"):match("(%d+)-(%d+)")
  local seen = {}
  emu.addMemoryCallback(function(addr, val)
    if L.f >= tonumber(a) and L.f <= tonumber(b) then
      local st = emu.getState()
      local pc = (st["cpu.k"] or 0) * 65536 + (st["cpu.pc"] or 0)
      local key = string.format("%06X", pc)
      if not seen[key] then seen[key] = true; L.log(string.format("RDPAD pc=%s addr=%04X val=%02X f=%d", key, addr, val or -1, L.f)) end
    end
  end, emu.callbackType.read, 0x4218, 0x4219, emu.cpuType.snes)
end
if os.getenv("RP_TRACE") then
  local a, b = os.getenv("RP_TRACE"):match("(%d+)-(%d+)")
  a, b = tonumber(a), tonumber(b)
  local seen, order = {}, {}
  local function hook(lo, hi)
    emu.addMemoryCallback(function(addr)
      if L.f >= a and L.f <= b and not seen[addr] then seen[addr] = true; order[#order + 1] = addr end
    end, emu.callbackType.exec, lo, hi, emu.cpuType.snes)
  end
  hook(0x008000, 0x00FFFF); hook(0x028000, 0x02FFFF)
  emu.addEventCallback(function()
    if L.f == b + 1 then
      table.sort(order)
      local line, last = {}, -10
      for _, ad in ipairs(order) do
        line[#line + 1] = string.format("%06X", ad)
      end
      L.log("TRACE " .. table.concat(line, " "))
    end
  end, emu.eventType.endFrame)
end
for fr in string.gmatch(os.getenv("RP_WRAMDUMP") or "", "%d+") do
  local F = tonumber(fr)
  emu.addEventCallback(function()
    if L.f == F then
      local fh = io.open(L.OUT .. "/wram_" .. F .. ".bin", "wb")
      local t = {}
      for i = 0, 0x1FFF do t[#t + 1] = string.char(L.rd(i)) end
      fh:write(table.concat(t)); fh:close()
      -- 조사용: 훅 변수(`$7E:4625~`)·VRAM 도 같이 — 슬롯 소유·고정·앞 창 사본(`V_PREV`)과 타일 풀 점유를 본다
      local f2 = io.open(L.OUT .. "/var_" .. F .. ".bin", "wb")
      local t2 = {}
      for i = 0x4625, 0x4D00 do t2[#t2 + 1] = string.char(L.rd(i)) end
      f2:write(table.concat(t2)); f2:close()
      if os.getenv("RP_WRAMFULL") == "1" then -- 전체 WRAM 128KB(좌표·플래그 diff 용)
        local ff = io.open(L.OUT .. "/wfull_" .. F .. ".bin", "wb")
        local tf = {}
        for i = 0, 0x1FFFF do tf[#tf + 1] = string.char(emu.read(i, L.WR, false)) end
        ff:write(table.concat(tf)); ff:close()
      end
      local f3 = io.open(L.OUT .. "/vram_" .. F .. ".bin", "wb")
      local t3 = {}
      for a = 0, 0xFFFF do t3[#t3 + 1] = string.char(emu.read(a, emu.memType.snesVideoRam, false)) end
      f3:write(table.concat(t3)); f3:close()
    end
  end, emu.eventType.endFrame)
end
-- RP_INJ="프레임:번호,프레임:번호"(16비트 메시지 번호 hex) · RP_POKE="주소=값,…"(WRAM hex): 실제 필드의 루프 머리(`$00:8339`)에서 `JSL $02:DC8B` 를 흉내 내 메시지를 부른다
--   (msg_viewer 와 같은 방식 — 대신 시험 필드가 아니라 **세이브로 연 진짜 필드·창**에서). 변수 토큰(`{D9}`=`$0F42` 등)은 RP_POKE 로 먼저 세운다.
local INJ = {}
for f, id in string.gmatch(os.getenv("RP_INJ") or "", "(%d+):(%x+)") do INJ[#INJ + 1] = { tonumber(f), tonumber(id, 16), false } end
local POKE = {}
for a, v in string.gmatch(os.getenv("RP_POKE") or "", "(%x+)=(%x+)") do POKE[#POKE + 1] = { tonumber(a, 16), tonumber(v, 16) } end
-- RP_ADDR="번호=새롬SNES주소hex,…": 메인 표(`$07:8000`) 그 번호 항목을 그 주소로 바꾼다(`msg_addr.py` 로 구한 주소) — 사전·상자 문안을 진짜 필드 창으로 부르는 데 쓴다
for id, ad in string.gmatch(os.getenv("RP_ADDR") or "", "(%x+)=(%x+)") do
  local o, a = 0x38000 + 3 * tonumber(id, 16), tonumber(ad, 16)
  emu.write(o, a & 255, emu.memType.snesPrgRom); emu.write(o + 1, (a >> 8) & 255, emu.memType.snesPrgRom); emu.write(o + 2, (a >> 16) & 255, emu.memType.snesPrgRom)
end
if #INJ > 0 then
  emu.addMemoryCallback(function()
    for _, e in ipairs(INJ) do
      if not e[3] and L.f >= e[1] then
        e[3] = true
        for _, p in ipairs(POKE) do L.wr(p[1], p[2]) end
        L.wr(0x060B, e[2] & 255); L.wr(0x060C, e[2] >> 8)
        local st = emu.getState()
        local sp = st["cpu.sp"]
        local ret = 0x8339 - 1
        emu.write(sp, 0x00, emu.memType.snesMemory); emu.write(sp - 1, (ret >> 8) & 255, emu.memType.snesMemory); emu.write(sp - 2, ret & 255, emu.memType.snesMemory)
        st["cpu.sp"] = sp - 3; st["cpu.k"] = 0x02; st["cpu.pc"] = 0xDC8B
        emu.setState(st)
        L.log(string.format("INJ %04X f=%d", e[2], L.f))
        return
      end
    end
  end, emu.callbackType.exec, 0x008339, 0x008339, emu.cpuType.snes)
end
-- RP_POKEAT="프레임:주소=값,…"(WRAM hex) — 그 프레임 끝에 한 번 쓴다(소지품 칸에 장비를 써 넣어 장착 화면을 만든다)
for f, a, v in string.gmatch(os.getenv("RP_POKEAT") or "", "(%d+):(%x+)=(%x+)") do
  local F, A, V = tonumber(f), tonumber(a, 16), tonumber(v, 16)
  emu.addEventCallback(function() if L.f == F then L.wr(A, V) end end, emu.eventType.endFrame)
end
-- RP_SRMOUT="프레임:파일" — 그 프레임 끝에 세이브 램(2KB)을 파일로 쓴다(게임 안 저장을 마친 뒤 .srm 을 얻는다). RP_POKEAT 와 같이 쓰면 맵·좌표를 RAM 에 쓰고 게임 안 저장으로 세이브를 만든다(걷기 없이)
for f, path in string.gmatch(os.getenv("RP_SRMOUT") or "", "(%d+):([^,;]+)") do
  local F = tonumber(f)
  emu.addEventCallback(function()
    if L.f == F then
      local fh = io.open(path, "wb")
      local t = {}
      for i = 0, 2047 do t[#t + 1] = string.char(emu.read(i, emu.memType.snesSaveRam, false)) end
      fh:write(table.concat(t)); fh:close(); L.log("SRMOUT " .. path)
    end
  end, emu.eventType.endFrame)
end
-- RP_PCJUMP="프레임:PC(hex)" + RP_POKE: 그 프레임 이후 NMI 조이패드 읽기(`$00:AABF`)에서 WRAM 을 RP_POKE 대로 쓰고 PC 를 옮긴다(루틴 직접 호출 — 조건 RAM 을 세우고 읽는 코드를 부른다)
do
  local jf, jpc = string.match(os.getenv("RP_PCJUMP") or "", "(%d+):(%x+)")
  if jf then
    local done_j = false
    emu.addMemoryCallback(function()
      if done_j or L.f < tonumber(jf) then return end
      done_j = true
      for _, p in ipairs(POKE) do L.wr(p[1], p[2]) end
      local st = emu.getState()
      L.log(string.format("PCJUMP f=%d from %02X:%04X", L.f, st["cpu.k"], st["cpu.pc"]))
      local pc = tonumber(jpc, 16)
      st["cpu.k"] = (pc >> 16) & 0xFF; st["cpu.pc"] = pc & 0xFFFF
      st["cpu.ps"] = (st["cpu.ps"] or 0) | 0x30
      emu.setState(st)
    end, emu.callbackType.exec, 0x00AABF, 0x00AABF, emu.cpuType.snes)
  end
end
local done = false
local PINMAX = 0 -- 고정 칸(`pin` 표 = `$7E:4625 + 96 + 2*150`) 최대 수 — 슬롯 배정 한도 게이트의 예산 근거
local function pins()
  local n = 0
  for i = 0, 149 do if L.rd(0x4625 + 96 + 300 + i) ~= 0 then n = n + 1 end end
  if n > PINMAX then PINMAX = n; L.log("PINMAX " .. n .. " f=" .. L.f) end
end
emu.addEventCallback(function()
  if L.f % 30 == 0 then pins() end
  if shots[L.f] then
    local h = {}
    for i = 0, 22 do h[#h + 1] = string.format("%02X", emu.read(i, emu.memType.snesSaveRam, false)) end
    L.log(string.format("DBG f=%d sram=%s 171E=%02X 171F=%02X 05DE=%02X 05DD=%02X 05F0=%02X 05FA=%02X 05FB=%02X X=%02X%02X Y=%02X%02X MAP=%02X", L.f, table.concat(h, ""), L.rd(0x171E), L.rd(0x171F), L.rd(0x05DE), L.rd(0x05DD), L.rd(0x05F0), L.rd(0x05FA), L.rd(0x05FB), L.rd(0x13CE), L.rd(0x13CD), L.rd(0x13D0), L.rd(0x13CF), L.rd(0x1231)))
  end
  if shots[L.f] then L.shot(string.format("%s/shots/p%05d.png", L.OUT, L.f)) end
  if L.f >= MAXF and not done then done = true; L.log("END f=" .. L.f); emu.stop(0) end
end, emu.eventType.endFrame)
