# 핸드오프 — 이어서 작업하기

마지막 갱신: 2026-07-29(3차). 브랜치 `main`.

## 한 줄 요약

이슈 #1(스엘 유람선 크래시)은 **원인 미확정**. 다만 **100% 재현 환경**과
**폴트 지점 확정**, **기각된 가설 5개**, **최유력 후보 1개**까지 왔다.
다음 할 일은 명확하다 — `F_501`에 `ALGO_00` export를 이식해보는 것.

## 지금 상태

### 증상 (실측)

스엘 마을에서 10000G 지불 → 승선 → **월드맵 위를 배가 몇 칸 항해** →
나레이션이 한 번도 못 뜨고 크래시. PC엔진판에서는 가이드 나레이션 5단계를 거쳐
스엘로 귀환한다(사용자 캡쳐로 확인).

```
UNHANDLED EXCEPTION 0D at 0217:0C9C  Error code: 501C
AX=000D BX=1396 CX=0001 DX=004C SI=2200 DI=34CE BP=0FA6 SP=0F98
```

레지스터가 매 실행 거의 동일하다(BX/DI만 진행 경로에 따라 변동).

### 확정 — 폴트 지점

`ED2MAIN` seg4:0x0c9c. `Scenario_Load`(seg4:0x0a49)가 **첫 동작으로 부르는
"직전 모듈 FreeLibrary" 헬퍼**(seg4:0x0c64)의 복귀 `retf`이고, 복귀 CS가
쓰레기(0x501C)다. 엔진 에러 핸들러는 돌지 않으므로 생짜 스택 손상이다.

### 최유력 후보 — `Scenario_GetFuncPtr` 실패

해제 헬퍼의 **스택 전환을 들어내면**(`patches/diag-no-stack-switch.json`)
크래시가 바뀌고 엔진이 자기 진단을 뱉는다:

```
Where : Scenario_GetFuncPtr
What  : Fails in getting func ptr
```

`Scenario_GetFuncPtr`(seg4:0x0bab)는 **이름 기반 `GetProcAddress`(KERNEL.#50)**다.
이름 테이블(DS:0x0bfc): idx0=`SINAL_INIT`, idx1=`SINAL`, idx2=`ALGO_00`,
idx3~21=`ALGO_01`~`ALGO_19`.

그리고 **`F_501`/`F_502`만 `ALGO`를 하나도 export하지 않는다**:

| DLL | ordinal | thunk |
| --- | --- | --- |
| `F_000/001/002`, `F_200/201/202`, `F_400/401/402`, `F_500` | WEP=1, **ALGO_00=2**, SINAL_INIT=3, GETDLLDATASEG=4, SINAL=5 | 4개 |
| **`F_501`, `F_502`** | WEP=1, SINAL_INIT=2, GETDLLDATASEG=3, SINAL=4 | **3개** |

thunk 자체가 없고 ordinal도 재번호돼 있다 = `ALGO_00` 없이 빌드됐다.
`F_001`의 `ALGO_00`은 **6바이트**뿐이다(`lcall ED2MAIN.HOOK_RET` + `retf`, seg3:0x1ee).

**유보**: 이 실패는 패치 빌드에서만 관측됐다. 원본은 그 전에 죽으므로 2차 증상일
가능성이 남아 있다.

## 다음에 할 일

1. **`F_501`에 `ALGO_00` 이식 (최우선)** — 6바이트 thunk를 seg3 슬랙(493B 여유)에
   넣고 entry table + resident-name table에 항목 추가. `F_001`이 정확한 본보기다.
   NE export 추가 도구가 필요하다(`tools/` 신규). 성공하면 그게 곧 실제 패치 형태.
   - 주의: ordinal 번호가 `F_001`과 다르므로(F_501은 SINAL_INIT=2 등) 충돌 없는
     새 ordinal을 써야 한다.
2. 되면 `F_502`도 동일 처리 후 전체 유람 흐름 확인.
3. 안 되면 → `Scenario_GetFuncPtr` 실패가 2차 증상이라는 뜻. 스택 손상 자체를
   다시 판다(아래 미해결 참조).

## 재현 환경

```bash
repro/run.sh --app     # 반드시 --app. 셸에서 직접 띄우면 키보드가 죽는다
```

클론 직후 바로 된다. `repro/run.sh`가 `originals/ED2` → `work/dosbox/ed2/ed2` 사본을
자동 생성하고, `repro/ed2.conf.tmpl`의 `@ROOT@`를 리포지토리 절대경로로 치환해
`work/dosbox/ed2.conf`를 만든다. **경로가 달라도 그대로 동작한다.**

- `repro/ed2.conf.tmpl` — `usescancodes=false`, `autolock=false` 필수
  (macOS SDL1 키보드 먹통 원인). 생성물을 직접 고치지 말고 템플릿을 고칠 것
- `work/dosbox/ed2/ed2/` = `originals/ED2` 쓰기 가능 사본(33M, gitignore).
  `originals/`는 어떤 실험에서도 건드리지 않는다
- `-log-con` 기본 활성 → DOS 콘솔 출력이 `work/dosbox/ed2.log`에 남는다.
  게임이 그래픽 모드라 엔진의 `Where`/`What` 진단이 화면엔 안 보인다.
- `--debug`(DOSBox-X 디버거)는 **기동 시 세그폴트가 잦아 실용성 없음**.
  절차는 `03-debugger.md`에 남겨뒀다.
- 세이브는 사용자 제공분이 `originals/ED2/SAVE/`에 있다.

## 도구 (`tools/`)

| 도구 | 용도 |
| --- | --- |
| `ne_info.py` | NE 헤더/세그먼트/export 덤프 |
| `ne_relocs.py` | relocation 파싱 (off16은 **additive** = 값이 addend) |
| `ne_entries.py` | entry table → ordinal:seg:offset. `--near SEG:OFF`로 주소→export 역추적 |
| `annotate.py` | 엔진 함수명까지 주석 단 디스어셈블 (제일 많이 씀) |
| `scan_sym.py` | 특정 엔진 심볼을 참조하는 자리를 SCENA 전체에서 수집 |
| `scan_scenes.py` | `ENTER_PROG` 씬 참조 전수 검증 (941건 중 938건 정상) |
| `atime_probe.py` | 파일 접근시간으로 실제 로드된 리소스 추적 (`-log-fileio`가 무용지물이라 대체) |
| `apply_patch.py` | 원본 바이트 확인 후 패치 적용/복원 (`--check`/`--revert`) |

```bash
.venv/bin/python tools/annotate.py originals/ED2/SCENA/F_501.DLL 3 --from 0x630
.venv/bin/python tools/ne_entries.py originals/ED2/ED2MAIN.EXE --near 4:0c90
.venv/bin/python tools/atime_probe.py reset  work/dosbox/ed2/ed2   # 실행 전
.venv/bin/python tools/atime_probe.py report work/dosbox/ed2/ed2   # 크래시 후
```

## 기각된 가설 (재시도 금지)

| 가설 | 검증 | 결과 |
| --- | --- | --- |
| `ROUTE_NO=8` 인덱스 초과 | 8→4, 8→6 패치 | 레지스터까지 동일. 무관 |
| 크래시가 `ENTER_PROG2` 하류 | `ljmp`→`retf` 1바이트 | 동일 크래시 |
| 종료 정리 경로 | 게임 정상 종료 | 에러 없음. 배제 |
| `MAP/C_017.BZH` 결번 | 대역 파일 투입 | 동일. 무관 |
| 목적지 씬 파일 누락 | `scan_scenes.py` 전수 | 941중 938 정상 |
| 유람선 커서 미초기화 | `SAVE_FLAG` 분기 NOP | 동일 크래시 |
| relocation 겹침 | atype 실측 | `F_501:0x62e`는 off16(2B), 안 겹침 |
| `WEP` 결함 | seg1 sha1 비교 | 모든 DLL 바이트 동일 |
| 메시지 오프셋 어긋남 | 문자열 시작 대조 | 5개 전부 일치 |
| 핸들러 테이블 off-by-one | 키데이터 종료바이트 추적 | `40`×5 → `20` 정확히 떨어짐 |

## 해독된 포맷 (재사용)

- **씬 ID** = `(prefix인덱스 << 12) | 번호`, prefix 문자셋 `"CDEFGHMTV"`.
  파일명 템플릿: `SCENA\C_000.DLL`, `MAP\C_000.BZH`, `MON\C_MO000.BZH`,
  `CHR\C_CHR00.BZH`.
- **씬 레코드** = 0x22바이트. `ENTER_PROG`/`ENTER_PROG2`의 `bx`는 이 레코드의
  **오프셋**이고, **레코드+12의 워드가 씬 ID**다.
- **relocation**: 엔진 전역 참조(off16)는 전부 **additive** → 파일의 값이 addend.
  `mov bx,[2] -> PL_TOP`은 `PL_TOP+2`(구조체 필드). ptr32/seg16은 chained이나
  실측 체인 길이는 전부 1.
- **키데이터** = (키,횟수) 쌍 + 종료바이트. 종료바이트가 다음 분기를 고른다 —
  `20`=도착 처리, `40`=`LOCAL_WORK+2` 커서 전진(유람선 전용 다단계 연출).
- **엔진 진단 문자열**: ED2MAIN 0x30d20~0x311ff에 `Where : %s` / `What : %s`와
  `Scenario_Load` / `Scenario_GetFuncPtr` / `Fails in ...` 등이 몰려 있다.

## 미해결

- **스택 손상의 진짜 범인.** 해제 헬퍼와 `Scenario_Load`, 그리고 seg86의 시나리오
  호출 트램폴린이 **각자 전역에 SS:SP를 저장하고 같은 전용 스택(seg12:0x2b7b)을
  공유**한다. `FreeLibrary`는 해제 대상 DLL의 `WEP`를 부르므로 재진입 경로가
  실재한다. 다만 게임 중 다른 씬 전환은 멀쩡히 도는데 이 전환만 깨지는 이유는
  설명 못 했다.
- DLL 코드 실행 중 `DS`가 정확히 무엇인지. 엔진 전역과 DLL seg3 데이터를 같은 DS로
  접근하는 것처럼 보인다(결론에는 영향 없음 — 테이블 위치는 독립 확증됨).
- 일반 정기선도 깨지는지 미확정. `F_501`은 7개 항구(T_046/106/118/20C/246/306/406)가
  공유하는 범용 항해 씬이라, 깨진다면 스코프가 완전히 달라진다.

## 별건 결함

- **`G_234.DLL` 누락** — `D_538`, `G_204`, `G_224`가 참조하는데 파일이 없다.
- `F_001`/`F_201`/`F_401`의 디스패치 테이블(8칸)에 범위 검사 없음.
  `F_501`만 9칸 + `cmp bx,8` 전용 분기를 가졌다. 이번 건과는 무관.

## 참고

- 이슈 #2(그로스토스성 성문 SE 누락)는 착수 전.
- PC98 일판은 현재 워킹 트리에 없다. PC엔진판 동작은 사용자 캡쳐로 확보.
- 관련 문서: [01-scena-dll-format.md](01-scena-dll-format.md),
  [02-suel-boat-tour-crash.md](02-suel-boat-tour-crash.md)(상세),
  [03-debugger.md](03-debugger.md).
