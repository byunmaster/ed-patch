# 복원 #1 — 스엘 마을 세계 3대명소 유람 이벤트 크래시

## 증상

종장 이후 스엘 마을에서, 보아드 해운 유람선("세계 3대명소 유람여행", 10000G)
NPC에게 말을 걸고 배에 타는 즉시 오류가 발생한다. 만트라 DOS판에서만 발생하며
PC98 일판 등 타 기종은 정상.

## 타겟 파일

`SCENA/T_246.DLL` — 아래 대사를 포함하는 것으로 특정됨:

- "자, ***"
- "***"

## 원인 가설

1. 지역화(한글화) 과정에서 문자열/포인터 테이블 오프셋이 어긋남.
2. 유람선 목적지(명소) 좌표/워프 데이터 참조 오류.
3. export 함수(`ALGO_xx`) 참조 또는 셀렉터/스택 오류.

## 정적 분석 진행 상황

### 이벤트 backbone = `SINAL` (seg3:0x5fe)

export `SINAL`(seg3:0x5f4)은 `push cs; call 0x5fe; retf` thunk. 실제 핸들러
seg3:0x5fe는 **step 기반 상태 머신**이다. 핵심 전역(ED2MAIN import, relocation
으로 해석됨):

- `KEYDAT`(주소0) = 이벤트 진행 step
- `SIN_FLAG`(주소0x80) = 이벤트 플래그 비트필드
- `PL_TOP`(주소2) = 플레이어 맵 좌표. `dx=0x260e`가 유람선 트리거 타일.

주요 엔진 호출: `TOWN_SCROLL`, `DISP_MESS_LOW`(si=메시지 오프셋), `MESS_EXIT`,
`ENTER_PROG`/`ENTER_PROG2`(하위 프로그램 진입), `SET_CHR`/`SET_CHR2`,
`SPRITE_LOAD`, `SLEEP_SUB`, `EXIT`, `YES_NO`, `AUTO_SAVE`.

유람선 분기: player가 트리거 타일이면 seg3:0x70c로 → `TOWN_SCROLL` 후
step 진행, `DISP_MESS_LOW si=0x377`(유람선 대사, 문자열 seg3:0x37e 부근).

### 도구 (이번에 확보)

- `tools/ne_relocs.py` — 세그먼트 relocation → import(`ED2MAIN.#ord`) 해석.
- `tools/annotate.py` — 위를 ED2MAIN export 이름(971개)까지 매핑해 주석 디스어셈블.
  → `lcall … ; -> ED2MAIN.DISP_MESS_LOW` 형태로 코드가 읽힌다.
- 전체 리스팅: `work/T_246.seg3-SINAL.asm`, `work/T_246.seg1.asm` (gitignore).

## 다음 작업

- [ ] 유람선 탑승 step 분기(0x70c→…)를 끝까지 따라가 크래시 유발 호출 특정
      (후보: 존재하지 않는 맵/좌표로 `ENTER_PROG`·워프, 범위 밖 `si`로 MESS 호출).
- [ ] 정상 동작하는 유사 배 탑승 DLL(`T_302`/`T_304`/`T_400`)의 SINAL과 구조 대조.
- [ ] DOSBox-X 디버거로 크래시 재현 → 폴트 주소를 seg3 오프셋으로 환산(교차검증).
- [ ] PC98 원본에서 의도된 동작(명소 3곳 순회) 확인.
