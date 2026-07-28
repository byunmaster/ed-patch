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

## MZ 헤더 파싱 예 (C_000.DLL)

```
sig MZ  pages 8  lastpage 349  relocs 1  header 512B
cs:ip 0x0d:0xa20  ss:sp 0x00:0xc8  reloc off 0x40
MZ 이미지 3933B / 파일 31248B → 트레일러 27315B = DPMI 16비트 페이로드
```

## 미해결

- DPMI 페이로드(트레일러) 정확한 포맷(NE/LE/커스텀) 및 export 테이블 구조 확인.
- 디스어셈블 파이프라인 확정(트레일러 언팩 → 16비트 세그먼트 디스어셈블).
