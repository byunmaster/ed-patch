# 복원 #1 — 스엘 마을 세계 3대명소 유람 이벤트 크래시

## 증상

종장 이후 스엘 마을에서, 보아드 해운 유람선("세계 3대명소 유람여행", 10000G)
NPC에게 말을 걸고 배에 탄다. 배가 마을 밖으로 나가 **월드맵 위를 몇 칸 항해한 뒤,
가이드 나레이션이 한 번도 뜨지 못하고** 죽는다.
만트라 DOS판에서만 발생하며 PC98 일판·PC엔진판 등 타 기종은 정상.

## 현재 상태: 원인 미확정

정적 분석으로 세운 초기 가설은 **동적 재현으로 반증됐다**(아래 "폐기된 가설").
지금은 크래시 지점과 주변 구조만 확정된 상태다.

## 재현 환경

DOSBox-X 2026.07.02 + `originals/ED2` 사본 + 사용자 제공 세이브.
설정·실행 스크립트는 `repro/`에 있고, 게임 사본·로그는 `work/dosbox/`(gitignore).
100% 재현되고 레지스터까지 매번 동일하다.

```bash
repro/run.sh --app      # --app(앱 번들)이라야 키보드 입력이 안정적
```

## 확정된 사실

### 폴트 지점

```
UNHANDLED EXCEPTION 0D at 0217:0C9C  Error code: 501C
CS=0217 segment #04 of ED2MAIN.EXE
AX=000D BX=1396 CX=0001 DX=004C SI=2200 DI=34CE BP=0FA6 SP=0F98
```

`ED2MAIN` seg4의 비공개 far 함수(0x0c64~0x0c9c). 파일 바이트가 화면 덤프와
일치하고, 미해결 placeholder `FF FF`가 런타임에 `4E 0E`로 relocate된 것까지 맞다.

```
0c64: inc bp / push bp / mov bp,sp     ; NE far 프롤로그
0c68: cli
0c69: mov [0x2f7c], sp                 ; 현재 SS:SP를 전역에 저장
0c6d: mov [0x2f7e], ss
0c71: mov ss, <seg12>                  ; 전용 스택으로 전환
0c76: mov sp, 0x2b7b
0c79: sti
0c7a: cmp word [0xbfa], 0x20           ; 핸들 > 32 인지 (LoadLibrary 에러코드 관용구)
0c7f: jbe 0xc8a
0c81: push word [0xbfa]
0c85: lcall KERNEL.#96                 ; = FreeLibrary
0c8a: mov word [0xbfa], 0
0c90: cli
0c91: mov sp, [0x2f7c]                 ; 스택 복원
0c95: mov ss, [0x2f7e]
0c99: sti
0c9a: pop bp / dec bp / retf           ; ← 폴트. 복귀 CS가 쓰레기(0x501C)
```

= **직전 시나리오 모듈을 `FreeLibrary`로 해제하는 헬퍼**.

호출자는 딱 둘이고, 하나는 **동적으로 배제됐다**:

- `seg5:0x0116` — `_THEEND` 바로 앞의 종료 정리 루틴.
  → **배제**. 게임을 정상 종료하면 에러 없이 DOS로 빠진다.
- `seg4:0x0a49` — **`Scenario_Load` 본체**. → 남은 유일한 경로.

```
0a4d: lcall 0x0c64        ; ① 직전 모듈 FreeLibrary   ← 폴트는 여기
0aa8: push ds:0xcb9       ; ② "%s\%s" 로 경로 조립 (sprintf = seg1:0x35b3)
0ad2: lcall KERNEL.#95    ; ③ LoadLibrary
0ad7: mov [0xbfa], ax     ;    핸들 저장. <=0x20 이면 "Fails in loading DLL %s"
```

`-log-con`으로 받은 콘솔 출력에 **로드 실패 메시지가 없다** → ②③에 도달조차 못한다.
폴트는 ①로 확정.

### 엔진이 감지한 오류가 아니다 (동적 확인)

`repro/run.sh`는 `-log-con`으로 DOS 콘솔 출력을 로그에 남긴다. 크래시 재현 시
로그에는 예외 덤프만 있고 그 앞에 **`Where`/`What` 메시지가 없다**. 즉 엔진 에러
핸들러는 돌지 않았고, 생짜 GP fault다. (`FreeLibrary`를 막았을 때 나온
`Scenario_GetFuncPtr` 메시지는 그 패치가 만든 별개 현상이었다.)

### `WEP`은 용의선상 밖

모든 시나리오 DLL의 **seg1이 바이트 단위로 동일**하다(sha1 `b569c855…`). `WEP`을
포함한 DLL 보일러플레이트가 공통이므로 특정 DLL의 `WEP` 결함일 수 없다.

### 엔진 진단 문자열 (ED2MAIN 0x30d20~0x311ff)

엔진은 자체 에러 리포트를 갖고 있다 — `Where : %s` / `What  : %s`.

```
Scenario_Load / Fails in loading DLL %s / Fails in initializing DLL
Segment SIN_H is loaded with unexpected offset
Scenario_GetFuncPtr / Fails in getting func ptr
  Attempts to get func ptr that is undefined
  Attempts to get func ptr with using invalid DLL handle
GetDLLDataSeg, SINAL_INIT, SINAL, ALGO_00 ~ ALGO_19
Monster_Load / GetMDLLDataSeg / DisplayFuncKey / Fails in allocating memory
```

`Scenario_GetFuncPtr`가 **이름으로** export를 찾는다는 것, 그리고 찾는 이름
목록이 `SINAL_INIT`/`SINAL`/`GETDLLDATASEG`/`ALGO_00`~`ALGO_19`임을 알 수 있다.

게임이 그래픽 모드라 이 메시지는 보통 화면에 안 보인다. 원래 크래시에서도
출력됐는데 못 본 것일 가능성이 있다.

### 씬 ID 인코딩 (해독 완료)

```
scene_id = (prefix_index << 12) | number,   prefix_index -> "CDEFGHMTV"
파일명 템플릿: SCENA\C_000.DLL, MAP\C_000.BZH, MON\C_MO000.BZH, CHR\C_CHR00.BZH
```

`ENTER_PROG`/`ENTER_PROG2`가 받는 `bx`는 씬 ID가 아니라 **0x22바이트 레코드의
오프셋**이고, **레코드 오프셋 12의 워드가 씬 ID**다.

두 경로로 검증했다. `T_246`의 `rec@0x32`→`0x3500`(F_500), `rec@0x54`→`0x3501`
(F_501)이 실제 로드와 일치하고, `C_605`는 `mov ax,0x60a / mov [0x1ba],ax`로
레코드+12에 씬 번호를 런타임에 써넣는다(0x1ba−0x1ae=12).

`tools/scan_scenes.py`로 전체 검사: **참조 941건 중 938건이 실재 파일로 해석**.

### 로드 순서 (atime 프로브 실측)

`-log-fileio`가 이 빌드에서 아무것도 안 찍어서 `tools/atime_probe.py`로 대체했다
(APFS atime 비교). 크래시 직전에 열리는 것:

```
BGM/DS2_04.{INS,MUS}   BGM/DS2_12.{INS,MUS}
MAP/C_000.BZH          MAP/C_010.BZH
SCENA/C_605.DLL        SCENA/F_501.DLL       SCENA/T_246.DLL
```

목적지 시나리오까지 로드된 뒤에 죽는다 — 씬 전환 실패가 아니다.

**주의: 없는 파일을 열려다 실패한 경우는 이 프로브로 안 잡힌다.**

## 최유력 후보 — `Scenario_GetFuncPtr` 실패 (`ALGO_xx` 부재)

**해제 헬퍼의 스택 전환을 들어내자 크래시가 바뀌었다.** `0217:0C9C` 폴트가 사라지고
엔진이 자기 진단을 출력했다:

```
Where : Scenario_GetFuncPtr
What  : Fails in getting func ptr
UNHANDLED EXCEPTION 0D at 04D7:23A4  Error code: 20B4
```

`04D7` = seg86, 0x23A4 = `mov ss,[0x96af]` — 시나리오 함수를 far call한 뒤의 스택
복원 지점이다. 즉 **진짜 오류는 함수 포인터 획득 실패**이고, 엔진이 중단하려다
그 경로에서 또 죽는다.

### `Scenario_GetFuncPtr` = seg4:0x0bab (해독 완료)

```
0bd4: cmp [0xbfa], 0x20     ; 모듈 핸들 <= 0x20 → "invalid DLL handle"
0bdb: cmp [0x26ac], 0x16    ; 인덱스 >= 22 → "func ptr that is undefined"
0bf6: mov bx, [0x26ac]
0bfa: shl bx, 2             ; 인덱스 x 4
0bfd: push [bx+0xbfe]       ; 이름 문자열 far 포인터
0c05: lcall KERNEL.#50      ; = GetProcAddress (이름 기반)
0c18: jne 정상
0c1b: push 0xe5c            ; → "Fails in getting func ptr"
```

이름 테이블(DS:0x0bfc, ptr32 relocation으로 채워짐)을 풀면:

| 인덱스 | 이름 | | 인덱스 | 이름 |
| --- | --- | --- | --- | --- |
| 0 | `SINAL_INIT` | | 2 | `ALGO_00` |
| 1 | `SINAL` | | 3~21 | `ALGO_01`~`ALGO_19` |

엔진 seg86에는 인덱스를 정해 공통 트램폴린으로 보내는 스텁들이 있다
(`mov bx,imm ; call 0x220a`) — 실측 5개: bx=7~11 → `ALGO_05`~`ALGO_09`.
트램폴린은 `Scenario_GetFuncPtr` 결과를 `[0x96a5]`에 받아 곧바로 `lcall`한다.

### 비대칭: `F_501`/`F_502`만 `ALGO`가 하나도 없다

| DLL | ordinal 구성 | seg3 thunk |
| --- | --- | --- |
| `F_000/001/002`, `F_200/201/202`, `F_400/401/402`, `F_500` | WEP=1, **ALGO_00=2**, SINAL_INIT=3, GETDLLDATASEG=4, SINAL=5 | 4개 |
| **`F_501`, `F_502`** | WEP=1, SINAL_INIT=2, GETDLLDATASEG=3, SINAL=4 | **3개** |

export만 빠진 게 아니라 **thunk 자체가 없고 ordinal도 재번호**가 매겨져 있다.
즉 `ALGO_00` 없이 빌드됐다. `F_001`의 `ALGO_00`은 6바이트에 불과하다
(`lcall ED2MAIN.HOOK_RET` + `retf`, seg3:0x1ee).

→ 엔진이 `F_501`에 `ALGO_xx`를 요청하면 `GetProcAddress`가 NULL을 반환한다.

**단, 이 실패는 패치를 넣은 빌드에서만 관측됐다.** 원본에서는 그 전에
`0217:0C9C`로 죽어 여기까지 오지 않으므로, 2차 증상일 가능성은 남아 있다.

### 검증되지 않은 가설 — relocation 겹침 (기각)

`F_501:0x62e`에 `HOOK_RET` relocation이 남아 있어 "thunk는 지웠는데 reloc이 남아
다음 명령을 덮는다"고 의심했으나, **atype이 ptr32가 아니라 off16(2바이트)**라
겹치지 않는다. 실측으로 `F_001/F_500/F_501/F_502` 모두 겹치는 레코드 쌍이 없다.
해당 워드는 `HOOK_RET` 주소를 담는 데이터이고 `F_502`도 같은 구조다. 정상.

## 의도된 동작 (PC엔진판 레퍼런스)

사용자가 PC엔진판 실기 진행을 캡쳐해왔다. 정상 흐름:

1. 스엘 마을에서 10000G 지불 → 승선
2. 월드맵(イセルハーサ) 위를 배가 항해
3. **ガイド(가이드)** NPC가 나레이션을 단계적으로 진행
   — 多島海(다도해) 진입 안내 → 島々 설명 → ラスタバン(라스타반) 조망
   → ニルキド(니르키드) 안내
4. 배가 スエルの村로 귀환, 船員이 "どうでしたか お客さん?"

즉 **월드맵 위를 항해하며 나레이션 5단계**를 거쳐 출발지로 돌아오는 왕복이다.
`F_501`의 핸들러 5개 + 메시지 5개(si=0x216/0x2da/0x3dd/0x4dc/0x532), 그리고 route 4/8의
목적지가 `0x7246`(스엘 자신)인 것과 정확히 대응한다 — DOS판 데이터 구조는 온전하다.

만트라판에서는 **2번 단계에서 배가 몇 칸 움직인 직후, 나레이션이 한 번도 뜨지 못하고**
죽는다.

## 폐기된 가설 — "커서 미초기화"

`F_501`의 유람선 커서 설치(`mov [LOCAL_WORK+2], 0x1a6`, seg3:0x802)는
`SAVE_FLAG == 0` 분기의 fall-through로만 도달하고, seg3 어디에도 0x7f7을 가리키는
분기·relocation이 없다. 그래서 커서가 설치되지 않는 것을 의심했다.

**반증**: `jne 0x813`(seg3:0x7e7)을 `nop nop`으로 바꿔 이 블록이 항상 실행되게 해도
**레지스터까지 동일하게 크래시**한다. 커서 초기화는 원인이 아니다.

## 폐기된 가설 — "ROUTE_NO 8 인덱스 초과"

`T_246`은 승선 시 `ROUTE_NO`(#772)에 **8**을 쓰고, `F_001`/`F_201`/`F_401`은
seg3 오프셋 0의 6바이트 엔트리 테이블을 **범위 검사 없이** 인덱싱하는데 엔트리가
8칸(0~7)뿐이다. 그래서 8은 테이블 밖을 읽는다고 봤다.

**반증**:

- atime 실측 결과 승선 시 `F_001`/`F_201`/`F_401`은 **아예 로드되지 않는다**.
  배 경로가 아니었다. 전제부터 틀렸다.
- `ROUTE_NO`를 4로, 6으로(정상 항구 T_300 계열이 쓰는 값) 바꿔도 **레지스터까지
  완전히 동일하게** 크래시한다. 크래시는 항로 번호와 무관하다.
- 8→4 실험이 무의미했던 이유도 밝혀졌다. `F_501`에서 route 4와 8은 디스패치
  엔트리가 동일하고(`dx=0x00be, code=0x06df, si=0x05f2`), route 4 역시 어떤
  마을도 쓰지 않는 미검증 슬롯이다.

다만 **`F_001`/`F_201`/`F_401`의 무검사 인덱싱 자체는 실재하는 잠재 결함**이다.
`F_501`만 9번째 엔트리와 `cmp bx,8` 전용 분기를 갖고 있다. 이번 건과는 무관하나
별도 이슈 후보로 남긴다.

## 배제된 것들

| 가설 | 검증 방법 | 결과 |
| --- | --- | --- |
| `ROUTE_NO` 인덱스 초과 | 8→4, 8→6 패치 | 동일 크래시. 무관 |
| 크래시가 `ENTER_PROG2` 하류 | `ljmp ENTER_PROG2`→`retf` (1B) | 동일 크래시 |
| 종료 정리 경로 | 게임 정상 종료 | 에러 없음. 배제 |
| `MAP/C_017.BZH` 결번 | 대역 파일 투입 | 동일 크래시. 무관 |
| 목적지 씬 파일 누락 | `scan_scenes.py` 전수 검사 | 941건 중 938건 정상 |

`FreeLibrary` 호출을 무력화(`jbe`→`jmp`)하면 크래시가
`Scenario_GetFuncPtr / Fails in getting func ptr`로 **바뀐다**. 다만 이 패치는
모듈 누수로 엔진 상태를 망가뜨리므로(정상 종료도 깨진다) 하류 부작용일 수 있어
단정하지 못한다.

## 미확정 / 다음 작업

- [ ] **정상 배 대조 실험(최우선)** — `F_501`은 유람선 전용이 아니라 **7개 항구
      (T_046, T_106, T_118, T_20C, T_246, T_306, T_406)가 공유하는 범용 항해 씬**
      이다(F_501의 목적지 7개와 같은 집합). 스엘에서 일반 정기선을 타보면 갈린다.
      정상이면 유람선 고유 문제, 같이 죽으면 **만트라판 해상 이동 전체가 결함**이라
      스코프가 완전히 달라진다.
- [ ] 그래픽 모드 때문에 안 보이는 `Where`/`What` 진단 메시지를 잡을 방법
      (DOSBox-X 디버거는 이 빌드에 포함돼 있다 — `DEBUGBOX`, 브레이크포인트 가능).
- [ ] `seg4:0x0a49`(시나리오 로더) 전체 해독. `[0xbfa]`에 어떤 핸들이 들어가는지.
- [ ] 재진입 가능성 — `[0x2f7c]/[0x2f7e]` 저장 슬롯과 전용 스택(seg12:0x2b7b)을
      로더와 해제 헬퍼가 **공유**한다. 해제 도중 같은 전역을 쓰는 코드가 끼어들면
      엉뚱한 스택으로 복귀한다. 폴트가 정확히 그 복귀 지점이라 유력하다.
      `FreeLibrary`는 해제되는 DLL의 `WEP`를 호출하므로 재진입 경로가 존재한다.

## 별건으로 발견한 결함

- **`G_234.DLL` 누락** — `D_538`, `G_204`, `G_224`가 참조하는데 파일이 없다.
  유람선 경로와 무관하지만 실재하는 결함이다.
- `F_001`/`F_201`/`F_401`의 무검사 디스패치 인덱싱(위 참조).
