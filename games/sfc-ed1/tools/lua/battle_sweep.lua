-- 전 편성 전투 일괄(디버그 롬 메뉴 A 「전투 테스트」 루프를 몬다). 롬 변경 없이 Lua 만으로:
--   파티 무적(매 프레임 HP·MP 복원) · 적 방어 필드를 올려 안 죽게(몬스터가 계속 행동) · 자동 A 연타(공격→표적)
--   새 메시지 번호가 나올 때 36프레임 간격으로 캡처(20xx 행동류 전체 1회·60xx 시스템류 편성마다 1회) · 난수 강제(BT_FORCE)
-- 환경: BT_OUT 출력 폴더 · BT_JOBS "0-0x67" 또는 "0,5,9"(편성 번호) · BT_MAXF 편성당 프레임(기본 3500)
--       BT_SEED 전투 시작 지연 프레임 · BT_RSEED 난수 시드 `$1904` · BT_FORCE>=0 이면 난수 두 루틴 반환을 순번으로 덮는다(패스 번호)
-- 산출: $BT_OUT/log.txt (`M j<작업> bf<프레임> id=<번호>` · `MON j combo types=` · `TIMEOUT`) · shots/*.png
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local MAXF = tonumber(os.getenv("BT_MAXF") or "3500")
local SEED = tonumber(os.getenv("BT_SEED") or "0")
local SEEDV = tonumber(os.getenv("BT_RSEED") or "-1")
local FORCE = tonumber(os.getenv("BT_FORCE") or "-1")
local TRACE = os.getenv("BT_TRACE") == "1"
local DUMPAT = tonumber(os.getenv("BT_DUMPAT") or "")
local QUEUE, qi = {}, 1 -- BT_Q "0x2000,0x2001-0x2010": 전투가 내는 메시지 번호를 이 목록의 번호로 바꿔 부른다(실제 전투 문맥 — 행동자·대상·글리프) · BT_QFROM 시작 프레임
for a, b in string.gmatch(os.getenv("BT_Q") or "", "(%w+)%-?(%w*)") do
  a = tonumber(a); b = (b ~= "" and tonumber(b)) or a
  for i = a, b do QUEUE[#QUEUE + 1] = i end
end
local QFROM = tonumber(os.getenv("BT_QFROM") or "200")
local JOBS = {}
for a, b in string.gmatch(os.getenv("BT_JOBS") or "0-0x67", "(%w+)%-?(%w*)") do
  a = tonumber(a); b = (b ~= "" and tonumber(b)) or a
  for i = a, b do JOBS[#JOBS + 1] = i end
end
local rd, wr, wr16, log, shot = L.rd, L.wr, L.wr16, L.log, L.shot
local S0, job, bf, state, started = nil, 0, 0, "boot", false
local seen, insp, presscnt, rk = {}, nil, 0, 0
local want_reload = false
local function boost()
  for i = 0, 3 do -- 파티 기록 39바이트: HP·최대·MP·최대
    local b = 0x13E5 + i * 39
    wr16(b, 9999); wr16(b + 2, 9999); wr16(b + 4, 99); wr16(b + 6, 99)
  end
  if started and bf >= 150 then -- 적 기록 50바이트(`$107C`~): +0 종류 · +1 HP · +13 방어 필드를 크게(실측: 12 오프셋이 먹는다)
    for k = 0, 7 do
      local b = 0x107D + k * 50
      if (rd(b) | rd(b + 1) << 8) > 0 then wr16(b + 12, 0x3000) end
    end
  end
end
local function start_job()
  job = job + 1
  if job > #JOBS then if not L.done then L.done = true; log("ALLDONE f=" .. L.f); emu.stop(0) end; return end
  bf = 0; state = "run"; insp = nil; started = false
  log(string.format("JOB %d combo=%d", job, JOBS[job]))
end
-- 루프 머리(`$00:8B3D`): 첫 도착에 저장점, 이후엔 작업 시작·끝(전투가 끝나 돌아오면 다음 편성)
emu.addMemoryCallback(function()
  if L.f < L.BOOT_DONE then return end
  if S0 == nil then
    S0 = emu.createSavestate(); log("S0 f=" .. L.f); start_job()
  elseif state == "run" and started and bf > SEED + 60 then
    shot(string.format("%s/shots/c%03d_end.png", L.OUT, JOBS[job]))
    log(string.format("END job=%d bf=%d", job, bf))
    state = "between"; start_job(); emu.loadSavestate(S0) -- ⚠ loadSavestate 는 콜백을 끊으니 마지막에
    return
  end
  if state == "run" and bf >= SEED and not started then
    started = true; rk = 0
    -- 위/아래 입력 처리(`$00:8C41`)가 하는 일을 그대로: `$11FE`·`$124B`=편성 번호, `$1158`=배경(표 `$00:8BD9`), 그리고 `$11FB`=0x40 이 Start
    wr(0x11FE, JOBS[job]); wr(0x124B, JOBS[job]); wr(0x1158, emu.read(0x008BD9 + JOBS[job], emu.memType.snesMemory, false)); wr(0x11FB, 0x40)
    if SEEDV >= 0 then wr(0x1904, SEEDV & 255); wr(0x1905, (SEEDV >> 8) & 255) end
  end
end, emu.callbackType.exec, 0x008B3D, 0x008B3D, emu.cpuType.snes)
-- ⚠ emu.loadSavestate 는 **CPU 실행 콜백 안에서만** 된다(endFrame 콜백에서 부르면 오류로 조용히 무시된다) — NMI 안 조이패드 읽기(`$00:AABF`)에서
emu.addMemoryCallback(function()
  if want_reload then want_reload = false; start_job(); emu.loadSavestate(S0) end
end, emu.callbackType.exec, 0x00AABF, 0x00AABF, emu.cpuType.snes)
if FORCE >= 0 then -- 난수: `$00:957B`(나머지 N → `$0950`) · `$00:952A`(백분율 → `$0949` 0=성공/FF=실패) 반환을 순번으로
  emu.addMemoryCallback(function()
    if state ~= "run" or not started then return end
    local n = rd(0x0949); if n == 0 then n = 1 end
    rk = rk + 1; wr(0x0950, (rk + FORCE) % n)
  end, emu.callbackType.exec, 0x0095B9, 0x0095B9, emu.cpuType.snes)
  emu.addMemoryCallback(function()
    if state ~= "run" or not started then return end
    rk = rk + 1; wr(0x0949, (((rk + FORCE) % 2) == 0) and 0 or 0xFF)
  end, emu.callbackType.exec, 0x009579, 0x009579, emu.cpuType.snes)
end
local WATCH = os.getenv("BT_WATCH") -- 조사용: 롬 구간 읽기 감시 "0x02E9B4,0x02ECFF" — 16바이트 블록마다 첫 읽기의 PC 를 log 에 남긴다
if WATCH then
  local lo, hi = string.match(WATCH, "(%w+),(%w+)")
  local seen = {}
  emu.addMemoryCallback(function(addr, val)
    local blk = addr >> 4
    if seen[blk] then return end
    seen[blk] = true
    local st = emu.getState()
    log(string.format("WATCH bf%d job=%d addr=%06X pc=%02X:%04X", bf, job, addr, st["cpu.k"], st["cpu.pc"]))
  end, emu.callbackType.read, tonumber(lo), tonumber(hi), emu.cpuType.snes)
end
if TRACE then -- 조사용: 칸 번호 `$173B` 를 쓰는 PC (전투 로그 한 번)
  emu.addMemoryCallback(function(addr, val)
    if state ~= "run" then return end
    local st = emu.getState()
    log(string.format("W173B bf%d pc=%02X:%04X val=%02X", bf, st["cpu.k"], st["cpu.pc"], val))
  end, emu.callbackType.write, 0x00173B, 0x00173B, emu.cpuType.snes)
end
-- 🔴 완성 근거(10-19 관리자): 고정 36프레임이 아니라 **메시지 완료 지점**에서 찍는다 — `$02:E31A`(쪽 넘김 키 대기 직전 = 그 쪽이 끝까지 타자됨) · `$02:E798`(메시지 끝 `$FF` 처리 뒤).
--   ▼ 는 키를 누른 뒤에만 뜨므로 근거가 못 된다(devlog 10-19 (12)). 어느 쪽에도 안 닿으면 300프레임 뒤 why=timeout 으로 찍고 log 에 남긴다.
emu.addMemoryCallback(function() if insp and not insp.hit then insp.hit = "wait" end end, emu.callbackType.exec, 0x02E31A, 0x02E31A, emu.cpuType.snes)
emu.addMemoryCallback(function() if insp and not insp.hit then insp.hit = "end" end end, emu.callbackType.exec, 0x02E798, 0x02E798, emu.cpuType.snes)
-- 🔴 조우·등장 문구(`{이름}{이/가} 나타났다` 등)는 `<E4>`(END2)로 끝난다 — `$02:E216` 디스패치가 E4 를 `$02:E288`(E0 처럼 창을 올리고 기다렸다 지우는 쪽 끝 처리)로 보내고 `$02:E79E`(`PLP/RTL`)로 나간다 — E29D·E31A·E798 어느 쪽도 안 지난다. 글자는 E288 에 닿을 때 다 찍혀 있고 E79E 에선 이미 지워졌다(빈 창)(주입 8번호가 완료 지점 없이 하위 메시지에 가로채인 원인, 10-20)
emu.addMemoryCallback(function() if insp and not insp.hit then insp.hit = "e4" end end, emu.callbackType.exec, 0x02E288, 0x02E288, emu.cpuType.snes)
-- 전투 로그는 `$FF`(`E798`)가 아니라 `<E0>` 쪽 끝 처리(`$02:E29D` — 창을 화면에 올리고 속도만큼 기다렸다 `$02:E327` 이 쪽을 지운다)로 끝난다(실측: 글자는 E29D 에 닿기 전에 다 찍히고 지움은 ~50프레임 뒤)
emu.addMemoryCallback(function() if insp and not insp.hit then insp.hit = "e0" end end, emu.callbackType.exec, 0x02E29D, 0x02E29D, emu.cpuType.snes)
if os.getenv("BT_PROBE") then
  for _, a in ipairs({ 0x02E29D, 0x02E2DB, 0x02E30C, 0x02E327, 0x02E798 }) do
    emu.addMemoryCallback(function() log(string.format("PROBE bf%d %06X insp=%s", bf, a, insp and string.format("%04X", insp.id) or "-")) end, emu.callbackType.exec, a, a, emu.cpuType.snes)
  end
end
L.on_message(function(id)
  if state ~= "run" then return end
  if qi <= #QUEUE and bf >= QFROM and not insp then -- 주입: 이 입구에서 번호를 덮어쓰면 그대로 그 메시지가 열린다
    id = QUEUE[qi]; qi = qi + 1; wr(0x060B, id & 255); wr(0x060C, id >> 8)
    log(string.format("Q j%d bf%d id=%04X", job, bf, id))
  end
  log(string.format("M j%d bf%d id=%04X", job, bf, id))
  if TRACE then -- 조사용: 메시지 시작 때 칸 번호 `$173B`·`$1777`·`$1779/A` 와 칸 배열(`$0305` 68B)
    local c = {}
    for i = 0, 67 do c[#c + 1] = string.format("%02X", rd(0x0305 + i)) end
    log(string.format("T id=%04X cell=%02X u1777=%02X u1779=%02X%02X cells=%s", id, rd(0x173B), rd(0x1777), rd(0x1779), rd(0x177A), table.concat(c, "")))
  end
  if insp and insp.hit and insp.id ~= id then -- 완료 지점에 닿은 뒤 8프레임이 차기 전에 다음 메시지가 시작됐다 — 지금 장을 먼저 쓴다(그대로 두면 검사 대상이 새 메시지로 바뀌며 사라진다)
    insp.step = insp.step + 1
    shot(string.format("%s/shots/m%04X_c%03d_%d.png", L.OUT, insp.id, JOBS[job], insp.step))
    log(string.format("C id=%04X j%d step=%d why=%s frames=%d early=1", insp.id, job, insp.step, insp.hit, insp.wait))
    insp = nil
  end
  local sys = (id >> 13) == 3
  local key = sys and (id * 1000 + JOBS[job]) or id
  if not seen[key] then
    seen[key] = JOBS[job]; insp = { id = id, step = 0, wait = 0, settle = 8, max = sys and 1 or 6 }
  elseif insp and insp.id ~= id then insp = nil end
end)
emu.addEventCallback(function()
  if state ~= "run" then return end
  bf = bf + 1
  boost()
  if DUMPAT and bf == DUMPAT then -- 조사용: VRAM·OAM·CGRAM 덤프(BT_DUMPAT=프레임)
    for _, d in ipairs({ { "vram", emu.memType.snesVideoRam, 0x10000 }, { "oam", emu.memType.snesSpriteRam, 544 }, { "cgram", emu.memType.snesCgRam, 512 } }) do
      local name, mt, n = d[1], d[2], d[3]
      local h = io.open(L.OUT .. "/" .. name .. string.format("_c%03d.bin", JOBS[job]), "wb")
      for a = 0, n - 1 do h:write(string.char(emu.read(a, mt, false))) end
      h:close()
    end
  end
  if DUMPAT and bf == DUMPAT then
    local st = emu.getState()
    for k, v in pairs(st) do if string.find(k, "oam") or string.find(k, "obj") or string.find(k, "Obj") or string.find(k, "layers%[") then log("PPU " .. k .. "=" .. tostring(v)) end end
  end
  if bf == 100 then -- 이 편성의 몬스터 종류(사전 D3 번호)
    local t = {}
    for k = 0, 7 do
      local b = 0x107C + k * 50
      if (rd(b + 1) | rd(b + 2) << 8) > 0 then t[#t + 1] = string.format("%02X", rd(b)) end
    end
    log(string.format("MON j%d combo=%d types=%s", job, JOBS[job], table.concat(t, ",")))
  end
  if insp then
    insp.wait = insp.wait + 1
    local why
    if insp.hit then
      insp.settle = insp.settle - 1 -- 완료 지점 뒤 8프레임(마지막 글자·창이 화면에 올라가길 기다린다)
      if insp.settle <= 0 then why = insp.hit end
    elseif insp.wait >= 300 then why = "timeout" end
    if why then
      insp.step = insp.step + 1
      shot(string.format("%s/shots/m%04X_c%03d_%d.png", L.OUT, insp.id, JOBS[job], insp.step))
      log(string.format("C id=%04X j%d step=%d why=%s frames=%d", insp.id, job, insp.step, why, insp.wait))
      presscnt = 4; insp.wait = 0; insp.hit = nil; insp.settle = 8
      if insp.step >= insp.max or why == "end" or why == "e0" or why == "e4" then insp = nil end
    end
  end
  if bf >= MAXF then
    shot(string.format("%s/shots/c%03d_timeout.png", L.OUT, JOBS[job]))
    log(string.format("TIMEOUT job=%d", job)); state = "between"; want_reload = true
  end
  if L.f > 600000 then log("FRAMELIMIT"); emu.stop(2) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b = {}
  if S0 == nil then L.boot_input(b)
  elseif state == "run" and started and bf > SEED + 60 then
    if insp and presscnt > 0 then b.a = true; presscnt = presscnt - 1
    elseif not insp and (bf // 4) % 2 == 0 then b.a = true end -- 자동 A 연타(새 메시지를 보는 동안은 멈춘다)
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
