# 시나리오 DLL 포맷 노트

만트라 DOS판 `SCENA/*.DLL` — 맵/이벤트 단위로 컴파일된 16비트 DPMI DLL.

## 개요

- 헤더: DOS `MZ` 스텁 + DPMI 페이로드(`16STUB`, `PM STUB built 06/07/94`).
  스텁 로더는 `rtm.exe` / `dpmi16bi.ovl`(Phar Lap 계열 16비트 DPMI)을 사용.
- `ED2MAIN.EXE`가 런타임에 `Scenario_Load` → `Scenario_GetFuncPtr`로
  **이름 기반 동적 링킹**해 호출한다. 관련 심볼: `_BEFORECALLSCENARIO`,
  `CUR_SCENARIO`, `LOAD_SCENARIO`.
- 각 DLL의 export(예시, C_000): `C_000`(엔트리), `ALGO_00`, `SINAL`,
  `SINAL_INIT`, `GETDLLDATASEG`.
- 대사 텍스트는 DLL 데이터 세그먼트에 **EUC-KR**로 내장.

## 파일 접두어 규약

| 접두어              | 용도                          |
| ------------------- | ----------------------------- |
| `C_`                | 메인 스토리 이벤트            |
| `T_`                | 마을 NPC 대화                 |
| `M_` / `P_`         | 맵 데이터(`MAP/*.BZH`와 대응) |
| `D_` `V_` `H_` `F_` | 컷신·특수 연출류              |

## 실제 포맷: outer MZ 스텁 + 내부 NE

트레일러는 **NE(New Executable)** 16비트 세그먼트 실행 형식이다. 두 번째 MZ의
`e_lfanew`가 NE 헤더를 가리킨다. 예) `T_246.DLL`:

```
outer MZ(0) + DPMI 스텁(16STUB/PM STUB) → 내부 MZ(0x344) → NE@0xf60
NE: ver6 flags=0x8009(DLL) segs=4 modrefs=2 align=2^9 autodata=seg2
seg1: CODE off=0x1200 len=0x15dd   ← 이벤트 로직 (메인 코드)
seg2: DATA off=0x2c00 len=0x05fe   ← autodata
seg3: DATA off=0x3400 len=0x0925   ← export thunk 꼬리 포함
seg4: DATA off=0x4200 len=0x3fe2   ← EUC-KR 대사 문자열
modrefs: ED2MAIN, KERNEL (import; reloc으로 lcall 0:0xffff 자리를 패치)
```

### export (resident-name + entry table)

resident-name table의 ord0은 모듈명(`T_246`), 나머지가 진입점.
entry table(`NE+enttab`)이 ordinal→(seg:offset) 매핑:

| ord | 이름            | 위치                  | 비고                            |
| --- | --------------- | --------------------- | ------------------------------- |
| 1   | `WEP`           | seg1:0x00b4 (movable) |                                 |
| 2   | `SINAL_INIT`    | seg3:0x05f9           | 이벤트/플래그 초기화 추정       |
| 3   | `GETDLLDATASEG` | seg3:0x05f0           | 데이터 세그먼트 핸들 반환       |
| 4   | `SINAL`         | seg3:0x05f4           | **이벤트 핸들러 디스패치 추정** |

`ED2MAIN.EXE`는 `Scenario_Load`로 DLL을 올린 뒤 이 export들을 이름/ordinal로
호출한다. 스엘 유람선 크래시는 `SINAL`(또는 그것이 호출하는 seg1 코드)에서
발생할 가능성이 높다.

## 도구

- `tools/ne_info.py <dll>` — NE 헤더·세그먼트·export 덤프.
- `tools/ne_disasm.py <dll> <seg> [--from HEX] [--count N]` — 세그먼트 16비트
  디스어셈블(capstone). `.venv` 필요: `pip install -r tools/requirements.txt`.
