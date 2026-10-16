-- sfc-ed1 헤드리스 검수 공통 뼈대(Mesen2 `--testRunner` Lua). 쓰는 법은 docs/status.md 「디버그·일괄 검수」.
-- 각 스크립트가 `local L = dofile(os.getenv("LUA_DIR").."/lib.lua")` 로 읽는다.
local L = {}
L.OUT = os.getenv("BT_OUT") or "."
L.WR = emu.memType.snesWorkRam
L.f = 0 -- 지금까지 지난 프레임
function L.rd(a) return emu.read(a, L.WR, false) end
function L.wr(a, v) emu.write(a, v, L.WR) end
function L.rd16(a) return L.rd(a) | (L.rd(a + 1) << 8) end
function L.wr16(a, v) L.wr(a, v & 255); L.wr(a + 1, (v >> 8) & 255) end
local LOG = io.open(L.OUT .. "/log.txt", "a")
function L.log(s) LOG:write(s .. "\n"); LOG:flush() end
-- 콜백 안의 Lua 오류는 Mesen 이 조용히 삼키고 스크립트가 멎는다 — 전부 pcall 로 감싸 log 에 남긴다(실측: 전 편성 일괄이 오류 없이 5번째 편성에서 멎었다)
for _, name in ipairs({ "addEventCallback", "addMemoryCallback" }) do
  local orig = emu[name]
  emu[name] = function(cb, ...)
    return orig(function(...)
      local ok, r = pcall(cb, ...)
      if not ok then L.log("LUAERR " .. tostring(r)) end
      return r
    end, ...)
  end
end
function L.shot(path) -- 지금 화면을 PNG 로(마지막으로 그려진 프레임)
  local h = io.open(path, "wb"); h:write(emu.takeScreenshot()); h:close()
end
os.execute("mkdir -p '" .. L.OUT .. "/shots'")
-- 부팅: 타이틀 Start → 크레스트 Start → 선택 화면으로 넘어가는 동안 L+R+X(메뉴 A) → A(전투 테스트). 프레임은 실측(100%).
L.BOOT = { { 300, { "start" }, 10 }, { 1100, { "start" }, 6 }, { 1120, { "l", "r", "x" }, 800 }, { 2400, { "a" }, 6 } }
L.BOOT_DONE = 2500 -- 이 프레임 뒤엔 전투 테스트 필드(루프 머리 `$00:8B3D` 가 돈다)
function L.boot_input(b)
  for _, s in ipairs(L.BOOT) do
    if L.f >= s[1] and L.f < s[1] + s[3] then for _, k in ipairs(s[2]) do b[k] = true end end
  end
end
-- 메시지 입구 `$02:DCD3`(대사·시스템 입구가 모두 합류): `$060B/$060C` = 메시지 번호(상위 3비트가 표 고름: 20xx=alt2 · 60xx=alt1 · 00xx~0Bxx=main · 80xx=alt3)
function L.on_message(cb)
  emu.addMemoryCallback(function() cb(L.rd(0x060B) | (L.rd(0x060C) << 8)) end, emu.callbackType.exec, 0x02DCD3, 0x02DCD3, emu.cpuType.snes)
end
emu.addEventCallback(function() L.f = L.f + 1 end, emu.eventType.endFrame)
return L
