-- 원판 사본 읽힘 감시(마스터 11-17, 전 게임 점검) — 환경변수 SW_WATCH = "시작 끝(hex SNES, 끝 미포함) 이름" 줄 파일. 범위마다 첫 읽기를 SW_OUT/watch.txt 에 바로 적는다(스크립트가 어디서 끝나도 남는다).
-- 각 하네스 맨 위에서 `dofile(os.getenv("SW_WATCHLUA"))` 로 부른다. 읽기 콜백은 데이터 읽기만 — 사본은 글자 자료라 코드 인출과 겹치지 않는다.
do
  local OUTW=os.getenv("SW_OUT") or "out"
  local hits=io.open(OUTW.."/watch.txt","a")
  local seen={}
  for line in io.lines(os.getenv("SW_WATCH")) do
    local a,b,name=line:match("^(%x+)%s+(%x+)%s*(.*)$")
    if a then
      local lo,hi=tonumber(a,16),tonumber(b,16)-1
      emu.addMemoryCallback(function(addr)
        if seen[lo] then return end
        seen[lo]=true
        local pc=emu.getState()["cpu.pc"] or 0
        hits:write(string.format("%06X %06X %s pc=%04X\n",lo,addr,name,pc)); hits:flush()
      end, emu.callbackType.read, lo, hi, emu.cpuType.snes)
    end
  end
end
