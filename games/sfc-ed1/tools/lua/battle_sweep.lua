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
local KILL = os.getenv("BT_KILL") == "1" -- 전투 완료 시험: 적 방어를 안 올리고 메시지 캡처도 안 한다(파티 무적 + 자동 A 연타로 승리까지 가는지만 본다)
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
local PEND = {}
if os.getenv("BT_DEATH") == "1" then -- 진단: 적 기록(`$107C`~ 8칸×50B)에 게임이 쓰는 바이트 — 쓰러질 때 바뀌는 상태 비트를 찾는다
  emu.addMemoryCallback(function(addr, val)
    if state ~= "run" then return end
    local o = addr - 0x107C
    local st = emu.getState()
    log(string.format("EW bf%d k=%d off=%d val=%02X pc=%02X:%04X", bf, o // 50, o % 50, val, st["cpu.k"], st["cpu.pc"]))
  end, emu.callbackType.write, 0x107C, 0x107C + 8 * 50 - 1, emu.cpuType.snes)
end
local BTSCRIPT = nil
if os.getenv("BT_SCRIPT") then
  BTSCRIPT = {}
  for f, keys, d in string.gmatch(os.getenv("BT_SCRIPT"), "(%d+):([%w+]+):(%d+)") do
    local ks = {}
    for k in string.gmatch(keys, "[^+]+") do ks[#ks + 1] = k end
    BTSCRIPT[#BTSCRIPT + 1] = { tonumber(f), ks, tonumber(d) }
  end
end
local BTSHOTS = {}
for f in string.gmatch(os.getenv("BT_SHOTF") or "", "%d+") do BTSHOTS[tonumber(f)] = true end -- 조사용: 전투 프레임별 장
-- 조사용: BT_PCS="01F4FB,1EEA76" — 그 주소를 실행하면 `PCHIT job pc bf` 를 남긴다(어느 편성이 엔딩 루틴 등으로 가는지)
for hx in string.gmatch(os.getenv("BT_PCS") or "", "%x+") do
  local a = tonumber(hx, 16)
  emu.addMemoryCallback(function() log(string.format("PCHIT j%d combo=%d %06X bf=%d", job, JOBS[job] or -1, a, bf)) end, emu.callbackType.exec, a, a, emu.cpuType.snes)
end
-- 조사용: BT_PCJUMP="전투프레임:주소hex" — 그 프레임 뒤 첫 NMI 조이패드 읽기(`$00:AABF`)에서 PC 를 옮긴다(마지막 보스 AI 의 끝 단계 `$01:F4E4` 를 직접 불러 엔딩으로 간다)
do
  local jf, jpc = string.match(os.getenv("BT_PCJUMP") or "", "(%d+):(%x+)")
  if jf then
    local jumped = false
    emu.addMemoryCallback(function()
      if jumped or state ~= "run" or not started or bf < tonumber(jf) then return end
      jumped = true
      local st = emu.getState()
      log(string.format("PCJUMP bf=%d from %02X:%04X", bf, st["cpu.k"], st["cpu.pc"]))
      local pc = tonumber(jpc, 16)
      st["cpu.k"] = (pc >> 16) & 0xFF; st["cpu.pc"] = pc & 0xFFFF
      st["cpu.ps"] = (st["cpu.ps"] or 0) | 0x30
      emu.setState(st)
    end, emu.callbackType.exec, 0x00AABF, 0x00AABF, emu.cpuType.snes)
  end
end
local HPFLOOR = tonumber(os.getenv("BT_HPFLOOR") or "1") -- 완료 시험이 적 HP 를 내리는 값(기본 1, 0 이면 맞기 전에 죽은 칸으로)
local ANIM = -999 -- 마지막으로 HP 굴림 애니메이션(`$00:9BE2`: [$23] 의 HP 를 `$1B02` 씩 목표 `$1B00` 까지 올리거나 내림)이 돈 프레임.
-- 🔴 그 도는 동안 HP 를 1 로 덮으면 굴림이 매번 처음부터라 영영 안 끝난다(보스 자가 회복 장면 — 10-24 완료 시험이 「멈춤」으로 오인했던 것)
emu.addMemoryCallback(function() ANIM = bf end, emu.callbackType.exec, 0x009BE2, 0x009BE2, emu.cpuType.snes)
local DIRS = os.getenv("BT_DIRS") == "1"
local want_reload = false
local function boost()
  for i = 0, 3 do -- 파티 기록 39바이트: HP·최대·MP·최대
    local b = 0x13E5 + i * 39
    wr16(b, 9999); wr16(b + 2, 9999); wr16(b + 4, 99); wr16(b + 6, 99)
  end
  if started and bf >= 150 and not KILL then -- 적 기록 50바이트(`$107C`~): +0 종류 · +1 HP · +13 방어 필드를 크게(실측: 12 오프셋이 먹는다)
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
    local ehp = 0
    for k = 0, 7 do ehp = ehp + (rd(0x107D + k * 50) | rd(0x107E + k * 50) << 8) end
    log(string.format("END job=%d bf=%d enemy_hp=%d", job, bf, ehp)) -- 적 HP 합이 0 이어야 승리로 닫힌 것
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
if os.getenv("BT_HITALL") == "1" then -- 완료 시험: 백분율 판정(`$00:952A` → `$0949`: 0 성공)을 늘 성공으로 — 회피 높은 보스에게도 파티 공격이 맞는다
  emu.addMemoryCallback(function() if state == "run" and started then wr(0x0949, 0) end end, emu.callbackType.exec, 0x009579, 0x009579, emu.cpuType.snes)
end
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
  if KILL then -- 완료 시험: 번호만 남긴다(멈춘 자리 진단). BT_MSHOT=1 이면 번호마다 처음 한 번 60프레임 뒤 화면도(진단 전용)
    log(string.format("M j%d bf%d id=%04X", job, bf, id))
    if os.getenv("BT_MSHOT") == "1" and not seen["s" .. id] then seen["s" .. id] = true; PEND[#PEND + 1] = { bf + 60, id } end
    return
  end
  if qi <= #QUEUE and bf >= QFROM and not insp then -- 주입: 이 입구에서 번호를 덮어쓰면 그대로 그 메시지가 열린다
    id = QUEUE[qi]; qi = qi + 1; wr(0x060B, id & 255); wr(0x060C, id >> 8)
    log(string.format("Q j%d bf%d id=%04X", job, bf, id))
    for d in string.gmatch(os.getenv("BT_QSHOT") or "", "%d+") do PEND[#PEND + 1] = { bf + tonumber(d), id, "d" .. d } end -- 조사용: 주입 뒤 d 프레임에 장(글자가 찍히는 중 — `<E4>` 끝 메시지는 완료 지점 장이 빈다)
  end
  log(string.format("M j%d bf%d id=%04X", job, bf, id))
  if os.getenv("BT_NSHOT") and not seen["n" .. id] then -- 조사용: 자연 흐름의 새 메시지마다 시작 뒤 d 프레임 장(주입 말고 실제 조우 메시지의 타자 중)
    seen["n" .. id] = true
    for d in string.gmatch(os.getenv("BT_NSHOT"), "%d+") do PEND[#PEND + 1] = { bf + tonumber(d), id, "n" .. d } end
  end
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
  if KILL and os.getenv("BT_NOIMM") == "1" and bf >= 100 then -- 완료 시험: 적 기록 +17 의 0x08·0x20 비트(`$01:A75B`·`$A78D` 가 읽는 면역류 — 이게 서면 일반 공격이 「맞지 않았다」가 된다)를 끈다
    for k = 0, 7 do
      local b = 0x107C + k * 50 + 17
      local v = rd(b); if v & 0x28 ~= 0 then wr(b, v & 0xD7) end
    end
  end
  if KILL and os.getenv("BT_DEAD") == "1" and bf >= 200 and bf % 20 == 0 then -- 완료 시험(승리 후처리만 본다): 적 기록 +17 의 0x80(쓰러짐 — 일반 몬스터가 죽을 때 `$01:A477` 이 켜는 비트)과 HP 0 을 직접 쓴다
    for k = 0, 7 do
      local b = 0x107C + k * 50
      if rd(b) ~= 0xFF and (rd(b + 17) & 0x80) == 0 then wr(b + 17, rd(b + 17) | 0x80); wr16(b + 1, 0) end
    end
  end
  if BTSHOTS[bf] then shot(string.format("%s/shots/f%03d_%05d.png", L.OUT, JOBS[job], bf)) end
  for i = #PEND, 1, -1 do
    if bf >= PEND[i][1] then shot(string.format("%s/shots/q%04X%s.png", L.OUT, PEND[i][2], PEND[i][3] and ("_" .. PEND[i][3]) or "")); table.remove(PEND, i) end
  end
  if KILL and os.getenv("BT_HPTRACE") == "1" and bf >= 150 and bf <= 1500 and bf % 10 == 0 then -- 진단: 적 기록 처음 두 칸 50바이트 전부
    local t = {}
    for k = 0, 1 do
      local c = {}
      for i = 0, 49 do c[#c + 1] = string.format("%02X", rd(0x107C + k * 50 + i)) end
      t[#t + 1] = table.concat(c)
    end
    log(string.format("REC bf%d %s", bf, table.concat(t, " ")))
  end
  if KILL and os.getenv("BT_PC") == "1" and bf % 50 == 0 and bf >= 1000 then local st = emu.getState(); local sp = st["cpu.sp"]; local t = {}
    for i = 1, 24 do t[#t + 1] = string.format("%02X", emu.read(sp + i, emu.memType.snesMemory, false)) end
    log(string.format("PC bf%d %02X:%04X sp=%04X stack=%s", bf, st["cpu.k"], st["cpu.pc"], sp, table.concat(t))) end
  if KILL and bf >= 150 and bf % 20 == 10 and bf - ANIM > 30 then -- 완료 시험: 적 HP 를 1 로(한 대만 맞으면 쓰러진다) — 파티 화력과 무관하게 승리 처리 경로까지 가 보게 한다. 보스가 중간에 HP 를 되채워도(단계 전환) 다시 1 로
    for k = 0, 7 do
      local b = 0x107D + k * 50
      if (rd(b) | rd(b + 1) << 8) > HPFLOOR then wr16(b, HPFLOOR) end
    end
  end
  if KILL and bf % 600 == 0 then -- 완료 시험 진단: 적·파티 HP 를 600프레임마다
    local e, p = {}, {}
    for k = 0, 7 do e[#e + 1] = rd(0x107D + k * 50) | rd(0x107E + k * 50) << 8 end
    for i = 0, 3 do p[#p + 1] = rd(0x13E5 + i * 39) | rd(0x13E6 + i * 39) << 8 end
    log(string.format("HP j%d bf%d enemy=%s party=%s", job, bf, table.concat(e, ","), table.concat(p, ",")))
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
  if L.f > (KILL and 3000000 or 600000) then log("FRAMELIMIT"); emu.stop(2) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b = {}
  if S0 == nil then L.boot_input(b)
  elseif state == "run" and started and bf > SEED + 60 and BTSCRIPT then -- 조사용(BT_SCRIPT="전투프레임:버튼+버튼:길이;…"): 자동 A 대신 직접 입력(주문 선택 등 — 커맨드를 화면 읽어 가며 고른다)
    for _, sc in ipairs(BTSCRIPT) do
      if bf >= sc[1] and bf < sc[1] + sc[3] then for _, k in ipairs(sc[2]) do b[k] = true end end
    end
  elseif state == "run" and started and bf > SEED + 60 then
    if insp and presscnt > 0 then b.a = true; presscnt = presscnt - 1
    elseif not insp and (bf // 4) % 2 == 0 then b.a = true -- 자동 A 연타(새 메시지를 보는 동안은 멈춘다)
    elseif KILL and DIRS and (bf // 4) % 2 == 1 then -- 완료 시험: 표적 커서를 돌린다(0번 칸이 죽어 있으면 A 만으론 영영 못 맞힌다) — 오른쪽/아래를 번갈아
      local ph = (bf // 64) % 3
      if ph == 1 then b.right = true elseif ph == 2 then b.down = true end
    end
  end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
