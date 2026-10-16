-- 엔딩 보기: 테스트 필드 루프 머리(`$00:8B3D`)에서 엔딩 루틴(`$1E:EA76`)을 바로 불러 엔딩 장면·스태프롤을 실화면으로 찍는다(원판 JP·한글 디버그 롬 모두, 세이브·보스전 불필요).
-- 환경: EN_MAXF 실행 프레임(기본 30000 · 스태프롤까지 ≈ 24000~29000) · EN_EVERY 캡처 간격(기본 120) · EN_ENTRY 진입 주소(기본 0xEA76). 자동 A 연타. 산출: shots/e<번호>.png · log.txt
-- 🔑 롬 문안·글꼴을 바꾼 뒤 스태프롤 한 줄을 원판과 픽셀 대조할 때 쓴다(「J.D.K.」 — 정적 렌더가 못 잡은 D 굵기·줄 위치를 실화면이 잡았다).
local L = dofile(os.getenv("LUA_DIR") .. "/lib.lua")
local MAXF = tonumber(os.getenv("EN_MAXF") or "30000")
local EVERY = tonumber(os.getenv("EN_EVERY") or "120")
local ENTRY = tonumber(os.getenv("EN_ENTRY") or "0xEA76")
local S0, f0, called = nil, 0, false
emu.addMemoryCallback(function()
  if L.f < L.BOOT_DONE or called then return end
  called = true; f0 = L.f
  local st = emu.getState()
  local s = st["cpu.sp"]
  local ret = 0x8B3D - 1
  emu.write(s, 0x00, emu.memType.snesMemory); emu.write(s - 1, (ret >> 8) & 255, emu.memType.snesMemory); emu.write(s - 2, ret & 255, emu.memType.snesMemory)
  st["cpu.sp"] = s - 3; st["cpu.k"] = 0x1E; st["cpu.pc"] = ENTRY
  emu.setState(st)
  L.log("CALL entry=" .. string.format("%04X", ENTRY) .. " f=" .. L.f)
end, emu.callbackType.exec, 0x008B3D, 0x008B3D, emu.cpuType.snes)
local n = 0
emu.addEventCallback(function()
  if not called then return end
  local rel = L.f - f0
  if rel % EVERY == 0 then n = n + 1; L.shot(string.format("%s/shots/e%04d.png", L.OUT, n)) end
  if rel % 600 == 0 then local st = emu.getState(); L.log(string.format("f+%d pc=%02X:%04X", rel, st["cpu.k"], st["cpu.pc"])) end
  if rel >= MAXF then L.log("END"); emu.stop(0) end
end, emu.eventType.endFrame)
local cnt = 0
emu.addEventCallback(function()
  local b = {}
  if not called then L.boot_input(b)
  else cnt = cnt + 1; if (cnt // 6) % 2 == 0 then b.a = true end end
  emu.setInput(b, 0)
end, emu.eventType.inputPolled)
