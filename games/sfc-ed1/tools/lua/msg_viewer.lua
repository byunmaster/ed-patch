-- 「메시지 보기」: 메시지 번호를 하나씩 직접 불러 화면에 띄우고 캡처한다(NPC 를 안 찾아다녀도 된다). 롬 변경 없음.
-- 원리: 전투 테스트 필드의 루프 머리(`$00:8B3D`)에서 레지스터를 직접 세운다 — `JSL $02:DC8B` 를 흉내 내
--   스택에 복귀 주소(`$00:8B3D`)를 밀고 PC=`$02:DC8B`, `$060B/$060C`=번호. 메시지가 끝나 루프 머리로 돌아오면 다음 번호.
-- 환경: BT_OUT · MV_IDS "0x2000-0x2156,0x6000-0x6059"(번호 범위, 16비트 번호) · MV_TIMEOUT 번호당 프레임 상한(기본 900)
--       MV_PAGES 쪽당 캡처(기본 6) · MV_ACTOR/MV_TARGET(예약: 행동자·대상 이름은 전투 문맥이라 이 필드에선 비어 나온다)
-- 산출: shots/v<번호>_<쪽>.png · log.txt(`V <번호> done|timeout pages=`)
-- ⚠ 한계: 분기·선택 창·`$EE` 네이티브 호출을 품은 메시지는 문맥(플래그·맵)이 없어 멎을 수 있다 → timeout 으로 표시하고 넘어간다.
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")

local TIMEOUT = tonumber(os.getenv("MV_TIMEOUT") or "900")
local PAGES = tonumber(os.getenv("MV_PAGES") or "6")
local IDS = {}
for a, b in string.gmatch(os.getenv("MV_IDS") or "0x2000-0x2010", "(%w+)%-?(%w*)") do
  a = tonumber(a); b = (b ~= "" and tonumber(b)) or a
  for i = a, b do IDS[#IDS + 1] = i end
end
-- MV_DEBOUNCE=1: **완성 프레임만** 찍는다 — 대사창 안쪽 픽셀이 8프레임(4프레임 간격 표본 둘) 안 변하는 가장 마지막 장을 쥐고 있다가, 쪽 지우기 시작(`$02:E327`, 훅 `pagesnap` 자리 —
--   앞 쪽이 아직 화면에 있다)과 메시지 끝에서 파일로 쓴다. 타자 중간 프레임·빈 창이 안 섞인다(쪽 번호 = 쪽 순서).
-- MV_DEBOUNCE=2: **▼ 대기 커서가 뜬 장**을 완성의 근거로 삼는다(마스터·관리자 10-19 — 8프레임 안정은 타자 중간 대기에 속는다). ▼ 가 보이면 그 장을 쥐고 A 를 눌러 다음 쪽으로,
--   60프레임 안 변해도 ▼ 가 없으면 그 장을 쥐되 log 에 `NOARROW <번호> <쪽>` 을 남긴다. A 는 타이머가 아니라 이때만 누른다(타자를 건너뛰지 않는다).
local DEB2 = os.getenv("MV_DEBOUNCE") == "2"
local ISOLATE = os.getenv("MV_ISOLATE") == "1" -- 번호마다 저장점 복귀 — 빈 창을 쥔 채 끝난 번호(BLANK)만 다시 찍는 데 쓴다
local DEB = os.getenv("MV_DEBOUNCE") == "1" or DEB2
local got_arrow = false
local reloadf = 0
local waitseen = false -- 쪽 넘김 키 대기(`$02:E31A`)에 닿았나 — 닿았으면 그 쪽은 끝까지 타자됐다(완성 근거)
local lasth, stable, shoth, pend = nil, 0, nil, nil
local pendink = 0 -- 쥔 장의 창 안쪽 글자 잉크 수(`region_hash` 값) — 빈 창 판정용
local function arrow_count(buf)
  local n = 0
  for y = 95, 102 do
    for x = 80, 87 do
      local v = buf[y * 256 + x + 1] or 0
      if (v & 0xFF) > 0xE6 and ((v >> 8) & 0xFF) > 0xE6 and ((v >> 16) & 0xFF) > 0xE6 then n = n + 1 end
    end
  end
  return n
end
local function region_hash()
  local buf = emu.getScreenBuffer()
  local w = 256
  local h, ink = 5381, 0
  for y = 24, (DEB2 and 93 or 100) do
    for x = 8, 152 do
      local v = buf[y * w + x + 1] or 0
      if (v & 0xFF) > 0xC0 and ((v >> 8) & 0xFF) > 0xC0 then ink = ink + 1 end -- 흰·노랑 글자 픽셀
      if (x + y) % 2 == 0 then h = (h * 33 + v) % 4294967296 end
    end
  end
  return h, ink, DEB2 and arrow_count(buf) or 0
end
local rd, wr, log, shot = L.rd, L.wr, L.log, L.shot
local S0, idx, state, wf, page, presscnt = nil, 0, "boot", 0, 0, 0
emu.addMemoryCallback(function() waitseen = true end, emu.callbackType.exec, 0x02E31A, 0x02E31A, emu.cpuType.snes)
-- ▼ 는 완성 근거가 못 된다(실측 10-19): 쪽 넘김 **키를 누른 뒤** 25프레임쯤만 뜬다(실게임도 같다). 대신 `$02:E31A` 도달(PG ... wait=1)을 완성 근거로 센다.
--   wait=0 은 키 대기에 안 닿은 쪽 — why=turn(쪽 지우기 시작에 쥐고 있던 장) · end(메시지 끝) · timeout(제한 프레임)
local function flush_pend(id, why)
  if pend and page < PAGES then
    page = page + 1
    log(string.format("PG %04X %d wait=%d why=%s", id, page, waitseen and 1 or 0, why or "turn"))
    if pendink < 260 then log(string.format("BLANK %04X %d ink=%d", id, page, pendink)) end -- 창 안쪽 글자가 거의 없다 = 빈 창을 쥔 채 끝났다(하네스 인공물) — MV_ISOLATE=1 로 그 번호만 다시 찍는다
    waitseen = false
    local h = io.open(string.format("%s/shots/v%04X_%d.png", L.OUT, id, page), "wb"); h:write(pend); h:close()
  end
  pend = nil; shoth = nil; got_arrow = false; stable = 0
end
-- ⚠ emu.loadSavestate 는 CPU 실행 콜백 안에서만 된다 — NMI 안 조이패드 읽기(`$00:AABF`)에서
emu.addMemoryCallback(function()
  if state == "reload" then state = "idle"; emu.loadSavestate(S0) end
end, emu.callbackType.exec, 0x00AABF, 0x00AABF, emu.cpuType.snes)

emu.addMemoryCallback(function() -- 쪽 지우기 시작 — 직전 쪽(완성)이 아직 화면에 있다
  if DEB and state == "show" then flush_pend(IDS[idx]) end
end, emu.callbackType.exec, 0x02E327, 0x02E327, emu.cpuType.snes)
-- MV_SPEED=0~3: 메시지 속도(`$1239` 비트 2~3 → `$174B`, 3 = 멈춤·한 번에 표시)를 부를 때마다 써 넣는다 — 타자 중간 프레임이 원천적으로 없다(마스터 10-19). 비우면 건드리지 않는다
local SPEED = tonumber(os.getenv("MV_SPEED") or "")
-- MV_FIELD=1: 필드 대화 모드 — `$11FB` 의 Start 비트(0x40, 전투 테스트 필드가 켠다)를 끄면 `$02:DC8B`·END 핸들러가 키를 기다리고 ▼ 를 그린다(안 끄면 `$02:E31A` 가 키 대기를 건너뛰어 ▼ 가 안 뜬다)
local FIELD = os.getenv("MV_FIELD") == "1"
-- MV_ADDR=<새 롬 SNES 주소 hex>(`tools/msg_addr.py` 가 번역 정본 주소에서 구한다): 번호표에 없는 씬 본문(표 목표)을 부른다 — 메인 표의 MV_ADDR_ID(기본 0x0001) 항목을 그 주소로 **RAM 쪽에서** 덮어쓰고 그 번호를 부른다(롬 파일은 안 바뀐다)
local ADDR = tonumber(os.getenv("MV_ADDR") or "")
local ADDR_ID = tonumber(os.getenv("MV_ADDR_ID") or "1")
local function call(id)
  if ADDR then
    local o = 0x38000 + 3 * ADDR_ID -- 메인 표 `$07:8000` = 파일 0x38000
    emu.write(o, ADDR & 255, emu.memType.snesPrgRom); emu.write(o + 1, (ADDR >> 8) & 255, emu.memType.snesPrgRom); emu.write(o + 2, (ADDR >> 16) & 255, emu.memType.snesPrgRom)
  end
  if FIELD then wr(0x11FB, 0) end
  if SPEED then wr(0x1239, (rd(0x1239) & 0xF3) | ((SPEED & 3) << 2)) end
  wr(0x060B, id & 255); wr(0x060C, id >> 8)
  local st = emu.getState()
  local s = st["cpu.sp"]
  local ret = 0x8B3D - 1
  L.wr(s, 0) -- 스택은 WRAM 이다($0100~$1FFF): 복귀 주소 = 뱅크 $00 · $8B3C+1
  emu.write(s, 0x00, emu.memType.snesMemory) ; emu.write(s - 1, (ret >> 8) & 255, emu.memType.snesMemory); emu.write(s - 2, ret & 255, emu.memType.snesMemory)
  st["cpu.sp"] = s - 3; st["cpu.k"] = 0x02; st["cpu.pc"] = 0xDC8B
  emu.setState(st)
  state = "show"; wf = 0; page = 0; presscnt = 0; lasth, stable, shoth, pend = nil, 0, nil, nil
  log(string.format("V %04X call", id))
end
emu.addMemoryCallback(function()
  if L.f < L.BOOT_DONE then return end
  if S0 == nil then S0 = emu.createSavestate() end
  if state == "show" then -- 메시지가 끝나고 돌아왔다
    if DEB then flush_pend(IDS[idx], "end") end
    log(string.format("V %04X done pages=%d", IDS[idx], page)); state = "idle"
    if ISOLATE then state = "reload"; return end -- 번호마다 저장점으로 되돌린다(앞 메시지의 슬롯·화면 상태를 지운다)
  end
  if state == "idle" or state == "boot" then
    idx = idx + 1
    if idx > #IDS then if not L.done then L.done = true; log("ALLDONE f=" .. L.f); emu.stop(0) end; return end
    call(IDS[idx])
  end
end, emu.callbackType.exec, 0x008B3D, 0x008B3D, emu.cpuType.snes)
emu.addEventCallback(function()
  if state ~= "show" then return end
  wf = wf + 1
  if DEB2 then
    if wf % 4 == 0 and not got_arrow and page < PAGES then
      local h, ink, ar = region_hash()
      if h == lasth then stable = stable + 1 else stable = 0; lasth = h end
      if ar >= 12 and ink >= 12 then
        pend = emu.takeScreenshot(); shoth = h; got_arrow = true; presscnt = 4
      elseif stable >= 15 and ink >= 12 then
        pend = emu.takeScreenshot(); shoth = h; got_arrow = true; presscnt = 4
        log(string.format("NOARROW %04X %d", IDS[idx], page + 1))
      end
    end
  elseif DEB then
    if wf % 4 == 0 then
      local h, ink = region_hash()
      if h == lasth then stable = stable + 1 else stable = 0; lasth = h end
      if stable >= 2 and ink >= 12 and h ~= shoth then pend = emu.takeScreenshot(); shoth = h; pendink = ink end
    end
    if wf % 40 == 0 and page < PAGES then presscnt = 4 end
  elseif wf % 40 == 0 and page < PAGES then
    page = page + 1; shot(string.format("%s/shots/v%04X_%d.png", L.OUT, IDS[idx], page)); presscnt = 4
  end
  if state == "reload" then -- 쓰레기 코드로 달려 NMI 가 꺼지면 저장점 복귀(`$00:AABF`)가 영영 안 온다 — 120프레임 기다려도 안 오면 이 번호까지 쓰고 끝낸다(실행기가 다음 번호부터 다시 띄운다)
    reloadf = reloadf + 1
    if reloadf > 120 and not L.done then L.done = true; log("STUCK " .. string.format("%04X", IDS[idx])); emu.stop(0) end
  else
    reloadf = 0
  end
  if wf >= TIMEOUT then
    if DEB then flush_pend(IDS[idx], "timeout") end
    log(string.format("V %04X timeout pages=%d", IDS[idx], page))
    state = "reload"
  end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local b = {}
  if S0 == nil then L.boot_input(b)
  elseif state == "show" and presscnt > 0 then b.a = true; presscnt = presscnt - 1 end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
