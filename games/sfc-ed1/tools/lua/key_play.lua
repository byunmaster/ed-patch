-- 인게임 확인용 최소 하네스(10-24): 세이브를 불러 RP_SCRIPT 입력을 넣고, KP_POKE "프레임:주소=값,…" 로 WRAM 을 쓰며, RP_SHOTS 프레임에 촬영한다.
-- 메모리 콜백이 없다(콜백을 건 debug_key 는 전투 시작에서 에뮬이 죽었다 — devlog). KP_DUMP "주소,…" 는 끝 프레임에 값을 로그한다.
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local sched = {}
for f, keys, d in string.gmatch(os.getenv("RP_SCRIPT") or "", "(%d+):([%w+]+):(%d+)") do
  local ks = {}
  for k in string.gmatch(keys, "[^+]+") do ks[#ks + 1] = k end
  sched[#sched + 1] = { tonumber(f), ks, tonumber(d) }
end
local shots = {}
for f in string.gmatch(os.getenv("RP_SHOTS") or "", "%d+") do shots[tonumber(f)] = true end
local pokes = {}
for f, a, v in string.gmatch(os.getenv("KP_POKE") or "", "(%d+):(0x%x+)=(0x%x+)") do
  pokes[#pokes + 1] = { tonumber(f), tonumber(a), tonumber(v) }
end
-- KP_BT="프레임:편성" — 메뉴 A 전투 테스트 루프에서 그 편성으로 Start(battle_sweep 와 같은 쓰기)
local btf, bti = string.match(os.getenv("KP_BT") or "", "(%d+):(%d+)")
-- KP_KEEP="주소=값,…" — 20프레임마다 다시 쓴다(파티 HP·MP 고정 — 무적)
local keep = {}
for a, v in string.gmatch(os.getenv("KP_KEEP") or "", "(0x%x+)=(%w+)") do keep[#keep + 1] = { tonumber(a), tonumber(v) } end
-- KP_SNAP="프레임,…" — 그 프레임에 WRAM $0000~$1FFF 를 OUT/snap_<프레임>.bin 으로 쓴다(커서 변수 차분용)
local snaps = {}
for f in string.gmatch(os.getenv("KP_SNAP") or "", "%d+") do snaps[tonumber(f)] = true end
local EHP = tonumber(os.getenv("KP_EHP") or "") -- 적 1 의 HP 를 이 값으로 눌러 둔다(쓰러짐 비트가 서면 멈춘다) — 주문 한 방으로 쓰러지는 경로 시험
local MAXF = tonumber(os.getenv("RP_MAXF") or "3000")
local LOGEVERY = tonumber(os.getenv("KP_LOG") or "0")
-- KP_CAST="목록 번호" — 전투 커맨드를 RAM 커서로 맞춘다: 커서 열 `$170F`·행 `$170E`(커맨드 창은 열=0 공격·1 주문·2 방어, 목록은 행=항목).
-- 주문(열 1·행 0) → 목록 행 = 번호 → 확정 → 대상 확정을 6프레임마다 한 걸음씩, 키를 누른 뒤엔 값이 바뀔 때까지 기다린다.
local CAST = tonumber(os.getenv("KP_CAST") or "")
local cph, cwait, ccount, cstuck, cattack = 0, 0, 0, 0, false
local lastsig, lastchg = "", 0
local function cast_keys()
  if cwait > 0 then cwait = cwait - 1; return nil end
  local col, row = L.rd(0x170F), L.rd(0x170E)
  local sig = string.format("%d/%d/%d/%d", col, row, ccount, L.rd16(0x107D))
  if sig ~= lastsig then lastsig = sig; lastchg = L.f end
  if L.f - lastchg > 240 then -- 한참 아무 변화가 없다(대상 없는 주문 목록에 갇힘 등) → 취소하고 그 차례는 공격으로
    lastchg = L.f; cattack = true; cph = 0; cwait = 15; return "b"
  end
  cwait = 5
  if cph == 0 then
    local want = cattack and 0 or 1
    cstuck = 0
    if col < want then return "right" elseif col > want then return "left" elseif row > 0 then return "up" end
    cph = 1; cwait = 25; return "a"
  elseif cph == 1 then
    if cattack then cph = 2; return nil end
    if row < CAST then return "down" elseif row > CAST then return "up" end
    cph = 2; cwait = 25; return "a"
  elseif cph == 2 then
    cstuck = cstuck + 1
    if cstuck > 12 and not cattack then -- 목록이 안 닫히고 서 있다(대상 없는 주문 등) → 취소하고 공격으로 대신한다
      cattack = true; cph = 0; cwait = 20; return "b"
    end
    cph = 3; cwait = 150; ccount = ccount + 1; cattack = false; return "a"
  else
    cph = 0; return nil
  end
end
emu.addEventCallback(function()
  local b = {}
  if CAST and L.f >= 3880 then
    local k = cast_keys()
    if k then b[k] = true end
    if L.f % 100 == 0 then L.log(string.format("CAST ph=%d col=%d row=%d casts=%d", cph, L.rd(0x170F), L.rd(0x170E), ccount)) end
    emu.setInput(b, 0)
    return
  end
  for _, s in ipairs(sched) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  for _, p in ipairs(pokes) do if L.f == p[1] then L.wr(p[2], p[3]) end end
  if L.f % tonumber(os.getenv("KP_EVERY") or "20") == 0 and L.f > 3600 then for _, k in ipairs(keep) do L.wr(k[1], k[2]) end end
  if EHP and ((os.getenv("KP_EHP_ONCE") or "") ~= "") and L.f == 3880 then L.wr16(0x107D, EHP) end
  if EHP and not ((os.getenv("KP_EHP_ONCE") or "") ~= "") and L.f > 3880 and L.rd16(0x107D) > EHP and (L.rd(0x108D) & 0x80) == 0 then L.wr16(0x107D, EHP) end
  if btf and L.f == tonumber(btf) then
    local j = tonumber(bti)
    L.wr(0x11FE, j); L.wr(0x124B, j); L.wr(0x1158, emu.read(0x008BD9 + j, emu.memType.snesMemory, false)); L.wr(0x11FB, 0x40)
  end
  if snaps[L.f] then
    local t = {}
    for a = 0, 0x1FFF do t[#t + 1] = string.char(L.rd(a)) end
    local fh = io.open(string.format("%s/snap_%d.bin", L.OUT, L.f), "wb"); fh:write(table.concat(t)); fh:close()
  end
  if shots[L.f] then L.shot(string.format("%s/shots/p%05d.png", L.OUT, L.f)) end
  if LOGEVERY > 0 and L.f % LOGEVERY == 0 then
    local st = emu.getState()
    L.log(string.format("PC %02X:%04X", st["cpu.k"], st["cpu.pc"]))
    L.log(string.format("f=%d en1hp=%d en2hp=%d en3hp=%d party=%d/%d/%d/%d", L.f, L.rd16(0x107D), L.rd16(0x107D + 50), L.rd16(0x107D + 100),
      L.rd16(0x13E5 + 1), L.rd16(0x13E5 + 39 + 1), L.rd16(0x13E5 + 78 + 1), L.rd16(0x13E5 + 117 + 1)))
  end
  if L.f >= MAXF then
    for a in string.gmatch(os.getenv("KP_DUMP") or "", "0x%x+") do L.log(string.format("DUMP %s=%02X", a, L.rd(tonumber(a)))) end
    local r0, r1 = string.match(os.getenv("KP_RANGE") or "", "(0x%x+)-(0x%x+)")
    if r0 then
      local t = {}
      for a = tonumber(r0), tonumber(r1) do t[#t + 1] = string.format("%02X", L.rd(a)) end
      L.log("RANGE " .. r0 .. ": " .. table.concat(t, " "))
    end
    local st = emu.getState()
    L.log(string.format("END f=%d pc=%02X:%04X en1hp=%d status=%02X", L.f, st["cpu.k"], st["cpu.pc"], L.rd16(0x107D), L.rd(0x108D)))
    L.log("END f=" .. L.f); emu.stop(0)
  end
end, emu.eventType.endFrame)
