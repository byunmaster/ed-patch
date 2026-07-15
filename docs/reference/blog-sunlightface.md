# sunlightface(일광면) 블로그 — PS1 한글화 강좌

sunlightface.github.io(일광면)는 PS1·NDS를 중심으로 한 한국어 레트로 게임 한글화·롬해킹 기술 블로그다. GPU/VRAM 하드웨어 문서를 기반으로 폰트·이미지 리소스를 추적하고, armips 어셈블러로 오버레이 실행파일을 패치하며, 스프라이트/애니메이션 바이너리 포맷을 직접 해석하는 실전 기법을 다룬다. 현재 우리 타깃인 PS1 관련 글(PCSX-Redux Lua VRAM 추적, no$psx 스택 문제, Psy-Q ANM 포맷)이 특히 유용하다.

> 출처: sunlightface.github.io

## PS1

### 루아 스크립트를 이용한 폰트 및 이미지 찾기

- URL: https://sunlightface.github.io/psx1/루아-스크립트를-이용한-폰트-및-이미지-찾기/
- 도구: PCSX-Redux(Lua + FFI + ImGui 지원), GPU Logger, Crystal Tile(텍스처 확인)

핵심 아이디어: PS1은 VRAM이 CPU 버스에 매핑되지 않아 CPU가 VRAM을 직접 못 읽는다. 데이터는 오직 GPU 커맨드(GP0)나 DMA로만 VRAM에 올라간다. 따라서 "화면에 보이는 이 이미지가 RAM의 어느 주소에서 왔는가"를 알려면 업로드(GP0 A0h)와 렌더링(GP0 64h~7Fh)을 하드웨어 레지스터 단에서 추적해야 한다.

관련 하드웨어 레지스터/커맨드:

| 대상 | 주소/코드 | 기능 |
|------|-----------|------|
| GP0 | 0x1F801810 (Write) | GPU 커맨드/패킷 전송 포트 |
| DMA2 MADR | 0x1F8010A0 | DMA 메모리 주소(RAM 소스/목적지) |
| DMA2 CHCR | 0x1F8010A8 | DMA 채널 제어(전송 시작 트리거) |
| GP0(A0h) | Copy Rectangle (CPU→VRAM) | 1st=커맨드, 2nd=목적좌표 YyyyXxxx(X는 halfword 단위), 3rd=Width+Height, 이후 픽셀 데이터 DMA 전송 |
| GP0(64h~7Fh) | Textured Rectangle | VRAM 텍스처를 화면에 렌더. 소스 위치는 TexPage(E1) + UV 오프셋으로 결정 |

추적이 어려운 이유: A0(업로드)과 0x64(렌더)는 순차 실행이 아니고, A0의 복사 크기가 부분적일 수 있어 1:1 대응이 안 된다. 해결 순서:

1. GPU Logger에서 렌더 대상 사각형(0x64)의 UV 값(예: u=896, v=256)을 확인한다.
2. 그 VRAM 좌표(X=896, Y=256)와 일치하는 A0 업로드 커맨드를 찾는다.
3. 그 A0에 뒤따르는 DMA2 MADR을 캡처해 RAM 소스 주소를 특정한다.

이를 자동화하는 PCSX-Redux Lua 스크립트의 동작 흐름은 세 단계 브레이크포인트다. HW 레지스터는 `getMemPtr()`로 못 읽으므로, `sw` 명령어(opcode 0x2B)를 디코딩해 CPU가 그 레지스터에 쓰려던 값을 rt 레지스터에서 뽑아낸다.

스크립트의 구성(우리 말로 요약):
- **값 추출 헬퍼**: `PCSX.getMemPtr()` 를 FFI 로 받아 RAM 을 읽고(주소는 `& 0x1FFFFF`), 브레이크포인트에 걸린 PC 의
  명령을 디코딩해 `sw`(opcode `0x2B`)면 rt 레지스터 값을 「쓰려던 값」으로 돌려준다.
- **1단계 — GP0 쓰기 감시**(`0x1F801810`): 상위 바이트 `0xA0` 을 만나면 다음 두 워드를 좌표·크기로 읽고, 좌표가
  목표 X/Y 와 같으면 매칭 상태로 둔다(PC 기록).
- **2단계 — DMA2 MADR**(`0x1F8010A0`): 매칭 중일 때 쓰이는 값을 픽셀 소스 RAM 주소로 잡아 둔다.
- **3단계 — DMA2 CHCR**(`0x1F8010A8`): 매칭 + MADR 이 있으면 결과(MADR·W·H·A0 PC·CHCR PC)를 확정하고 에뮬을 멈춘다.
- **우리가 쓰려면**: 목표 VRAM 좌표만 바꾸면 된다. mednafen·emucap 쪽이면 같은 세 지점에 쓰기 브레이크포인트를
  거는 것으로 옮길 수 있다(레지스터 값 추출 방식은 디버거마다 다르다).
- 원문 코드 보관: `docs/reference/_inventory/code/sunlightface-lua-vram-finder.md` (로컬 전용, 커밋 안 함) · 원문은 위 URL.

스크립트에는 ImGui UI(`DrawImguiFrame`)가 붙어 있어 target X/Y 입력, Start/Stop/Clear/Copy 버튼, 매칭 로그 테이블(X, Y, W, H, MADR, A0 PC, CHCR PC 8열)을 제공한다.

사용 절차:
1. GPU Logger에서 첫 Rectangle의 UV 값 기록(예: u=896, v=256).
2. `dofile("경로\\gpu_a0_source_finder.lua")`로 스크립트 로드.
3. 확인한 X, Y를 입력 필드에 입력.
4. 이미지가 VRAM에 올라오기 **전에** Start 클릭.
5. 매칭되면 에뮬레이터가 자동 정지하고 결과 표시.

출력 예:
```
A0 MATCHED! X=896 Y=256 W=4 H=240 PC=0x80063FD4, waiting for CHCR...
MADR captured: 0x80139604
PIXEL DATA SOURCE! MADR=0x80139604 W=4 H=240 A0_PC=0x80063FD4 CHCR_PC=0x8006404C
```

결과 해석:
- W/H는 halfword 단위 폭. 실제 픽셀은 4bpp일 때 ×4, 8bpp ×2, 16bpp ×1로 환산.
- MADR = 텍스처 픽셀의 RAM 소스 주소.
- A0_PC / CHCR_PC = 해당 명령을 실행한 코드 주소.

추가 추적(발견한 MADR이 원본이 아닐 때):
- 모든 텍스처 일괄 업로드면 MADR이 곧 원본.
- 부분 조립이면 MADR에 Write Breakpoint를 걸어 조립 함수를 역추적.
- 압축 데이터면 해제 함수에 Breakpoint를 걸어 압축 원본 위치 확인.

교훈: 하드웨어 문서(GPU 커맨드 구조, DMA 전송 순서, VRAM-RAM 관계)를 먼저 학습한 뒤 자동화 스크립트를 짜는 것이 초기엔 느려도 최종적으로 가장 빠르고 정확하다.

### 사이킥 포스1 자막 기능 활성화와 no$psx 스택 문제

- URL: https://sunlightface.github.io/psx1/사이킥-포스1-자막-기능-활성화와-no$psx-스택-문제/
- 도구: armips(패치 어셈블러), no$psx(디버깅), 대상 SLPS_005.20

현상: PS1 Psychic Force 1(사이킥 포스1)에서 no$psx로는 오프닝 자막이 표시되나 음성이 없고 영상 후 크래시, 반면 다른 에뮬레이터/실기에서는 오프닝 자막이 아예 안 나온다.

근본 원인: SYSTEM.CNF의 초기값이 `STACK = 801FCE00`인데, no$psx는 start 진입점의 스택 포인터를 `0x801FFFF0`으로 초기화한다. 이로 인해 메모리 오염이 발생하고, 복귀 주소 `$ra = 0x8011F5D0`이 하필 자막 활성화 조건 메모리에 우연히 기록되어 no$psx에서만 의도치 않게 자막이 켜진다. 즉 정상 동작이 아니라 스택 불일치가 부른 우연이다.

자막 처리 구조 — `sub_80111970` 안에서 다음 함수들이 불린다:
- ClearImage (sub_80123B3C): VRAM 초기화
- MoveImage (sub_80123C98): 자막 이미지를 표시 영역으로 복사
- DrawSync (sub_801239A8): GPU 작업 완료 대기

핵심 분기:
```
80111980  beqz  $v0, loc_80111AB0
```
자막 플래그($v0)가 0이면 위 처리 경로 전체가 스킵된다. 그래서 글리프 데이터가 VRAM에는 올라가도 화면에는 안 뜬다.

해결: 모든 에뮬레이터에서 정상적으로 자막이 나오고 no$psx 크래시도 없도록, 오버레이 실행파일(MOVVIEW.EXE, MONOVL.EXE)을 armips로 패치한다. DumpClut 함수의 미사용 영역을 code cave로 써서 hook → 스택 재설정 → 원래 주소 복귀 흐름을 만들고, 자막 플래그 분기를 nop 처리한다.

패치의 요지(armips, 두 오버레이 공통):
- **훅 지점**: 각 EXE 의 한 지점(MOVVIEW `0x80110F80`, MONOVL `0x80028340`)을 `j` 로 덮어 코드 케이브로 보낸다.
- **코드 케이브**: DumpClut 의 미사용 영역(MOVVIEW `0x801262DC`, MONOVL `0x800C2EB4`)을 0x40 바이트 비우고,
  `v1` 을 세팅하고(덮어쓴 원래 명령을 되살리는 것으로 보인다) `sp`·`fp` 를 SYSTEM.CNF 값 `0x801FCE00` 으로 다시 세팅하고 훅 다음 주소로 돌아간다.
- **자막 강제**: MOVVIEW 의 자막 플래그 분기(`0x80111980` `beqz`)를 `nop` 으로.
- **우리가 쓰려면**: armips `.open` 의 로드 주소(EXE 헤더 0x800 보정)·훅 주소·케이브 주소를 대상 실행 파일에 맞추고,
  덮어쓴 명령 두 개를 케이브에서 반드시 재실행한다(지연 슬롯 포함).
- 원문 코드 보관: `docs/reference/_inventory/code/sunlightface-psychic-force-subtitle.md` (로컬 전용, 커밋 안 함) · 원문은 위 URL.

패치 후 모든 에뮬레이터에서 자막이 정상 표시되고 no$psx 크래시도 해결된다. 핵심 기법은 (1) 에뮬레이터마다 다른 스택 초기값을 코드에서 명시적으로 `sp`/`fp`를 다시 세팅해 통일하고, (2) 자막을 켜는 분기 조건을 무력화(nop)하는 것.

### Psy-Q Sprite Editor ANM 포맷

- URL: https://sunlightface.github.io/psx1/Psy-Q-Sprite-Editor-ANM/
- 도구: Psy-Q Sprite Editor(공식 PS1 SDK 툴), TIM 텍스처 편집기

ANM은 Psy-Q Sprite Editor가 쓰는 스프라이트 애니메이션 메타데이터 포맷이다. 픽셀 자체는 TIM에 있고, ANM은 "어떤 프레임에서 TIM의 어느 영역을 어떤 좌표/스케일로 그릴지"만 정의한다. 리틀엔디안.

식별자: ID=0x21, VERSION=0x03.

헤더(8바이트):
| Offset | Size | 필드 | 설명 |
|--------|------|------|------|
| 0x00 | 1 | ID | 0x21 |
| 0x01 | 1 | VERSION | 0x03 |
| 0x02 | 2 | FLAG | ANM 플래그 |
| 0x04 | 2 | NSPRITEGp | 스프라이트 그룹 개수 |
| 0x06 | 2 | NSEQUENCE | 시퀀스 개수 |

시퀀스(8바이트, 프레임에서 쓸 스프라이트 그룹 지정):
| Offset | Size | 필드 | 설명 |
|--------|------|------|------|
| +0x00 | 2 | SprGpNo | 사용할 스프라이트 그룹 번호 |
| +0x02 | 2 | TIME | 표시 시간 |
| +0x04 | 2 | X | 기준 X (signed) |
| +0x06 | 2 | Y | 기준 Y (signed) |
(SprGpNo, TIME은 안 쓰는 경우도 있음)

스프라이트 그룹:
| Offset | Size | 필드 | 설명 |
|--------|------|------|------|
| +0x00 | 4 | NSprite | 그룹 내 스프라이트 개수 |
| +0x04 | 0x14 × NSprite | Sprite[] | 스프라이트 엔트리 배열 |

스프라이트 엔트리(20바이트 = 0x14):
| Offset | Size | 필드 | 설명 |
|--------|------|------|------|
| +0x00 | 1 | u | TIM X 좌표 |
| +0x01 | 1 | v | TIM Y 좌표 |
| +0x02 | 1 | ofsX | 출력 X 보정 |
| +0x03 | 1 | ofsY | 출력 Y 보정 |
| +0x04 | 2 | CBA | CLUT/팔레트 값 |
| +0x06 | 2 | FLAG | 텍스처/렌더 플래그 |
| +0x08 | 2 | W | 이미지 폭 |
| +0x0A | 2 | H | 이미지 높이 |
| +0x0C | 2 | ROT | 회전값 |
| +0x0E | 2 | FLAG2 | 추가 플래그 |
| +0x10 | 2 | ScaleX | X 스케일 (0x1000 = 1.0) |
| +0x12 | 2 | ScaleY | Y 스케일 (0x1000 = 1.0) |

예시 1 (1 그룹, 1 스프라이트):
```
21 03 00 00 01 00 01 00 00 00 00 00 F8 FF 00 00
01 00 00 00 00 60 00 00 03 78 16 00 88 00 18 00
00 00 01 00 00 10 00 10
```
- 헤더: ID=0x21, VER=0x03, FLAG=0, NSPRITEGp=1, NSEQUENCE=1
- 시퀀스: SprGpNo=0, TIME=0, X=-8(0xFFF8 signed), Y=0
- 스프라이트: u=0, v=0x60, ofsX=0, ofsY=0, W=136, H=24, CBA=0x7803, FLAG=0x0016, ScaleX=ScaleY=0x1000
- 해석: TIM의 (0, 0x60)에서 136×24 영역을 가져옴.

예시 2 (2 그룹, 각 1 스프라이트 → 2프레임 애니메이션):
```
21 03 01 00 02 00 02 00 00 00 00 00 00 00 00 00
01 00 00 00 00 00 00 00 00 38 80 80 40 7C 8E 00
40 00 38 00 00 00 01 00 00 10 00 10
01 00 00 00 00 A8 80 80 40 7C 8E 00 40 00 38 00
00 00 01 00 00 10 00 10
```
- Frame 0: Group 0 → TIM (0, 0x38)에서 64×56
- Frame 1: Group 1 → TIM (0, 0xA8)에서 64×56

렌더링은 보통 `GsSortFastSprite()` 함수로 처리된다. 요지(블로그 의사코드를 우리 말로):
- 엔트리 첫 워드가 음수이거나 W(`+0x08`)·H(`+0x0A`)가 0이면 그리지 않는다 — **크기 0 으로 숨기기**가 가능하다는 뜻.
- 최종 좌표 = (시퀀스 X/Y + ofsX/ofsY) + 게임 기준점 + 전역 오프셋, GPU 패킷에는 `(Y<<16)|X` 로 들어간다.
- 우리가 쓰려면: 위치를 옮길 땐 이 덧셈의 어느 항을 고칠지(ANM 쪽인지 게임 기준점인지)부터 정한다.
- 원문 코드 보관: `docs/reference/_inventory/code/sunlightface-psyq-anm.md` (로컬 전용, 커밋 안 함) · 원문은 위 URL.

좌표 계산 예: ANM 기준점 (0,0) + 게임 기준점 (-68,-20) + 전역 오프셋 (0,0) → 최종 XY = 0xFFECFFBC (상위 16비트 Y, 하위 16비트 X).

한글화 시 주요 편집 대상:
- 화면 위치: Sequence의 X/Y(signed 2바이트, 음수 가능), 엔트리의 ofsX/ofsY
- TIM 이미지 선택: u, v(추출 위치), W, H(추출 크기)

결론: 원본과 완전히 동일한 포맷/배치를 유지할 필요는 없고, 이 구조만 이해하면 원하는 이미지를 가공해 자유롭게 배치할 수 있다. (블로그는 패치 파일의 유료 판매·상업적 활용을 금지한다.)

## NDS

### XOR 기법을 이용한 스프라이트 이동과 백 버퍼 개선

- URL: https://sunlightface.github.io/nds/XOR-기법을-이용한-스프라이트-이동과-백-버퍼-개선/
- 도구: armips(ARM 어셈블러), Melon DS(에뮬레이터), Python(CRC 패치)

NDS에서 스프라이트를 화면에 직접 그리는 두 방식(XOR vs 백버퍼+DMA)을 정상 NDS ROM 구조로 구현·비교한다. Mode 2(VRAM 직접 출력, 프레임버퍼 방식)로 VRAM Bank A의 256×192×16bpp를 LCD에 직접 뿌린다.

주요 레지스터:
- DISPCNT (0x04000000): bit16~17로 디스플레이 모드. Mode1=일반 2D, Mode2=VRAM 프레임버퍼 직접 출력, Mode3=메인 메모리 직접 출력
- VCOUNT (0x04000006): 현재 스캔라인(≥192면 VBlank)
- KEYINPUT (0x04000130): 입력 상태
- DMA3 (0x040000D4~): 채널 3 DMA (SAD/DAD/CNT)

주소 계산: 16bpp라 `offset = (x * 2) + (y * 256 * 2)` (한 라인 512바이트). 색상은 5-5-5 BGR + bit15 = 투명/불투명 플래그(1=불투명 그림, 0x8000 = 그리기 대상; 백버퍼 방식에선 bit15로 투명 판정). 예: 0x83FF, 0x8000.

NDS 펌웨어 부팅 검증 3가지(그래서 raw ROM을 만들면 CRC 패치가 필수):
1. 헤더 0x0B2에 0x96 존재
2. 닌텐도 로고 데이터 0x0C0~0x15B(156바이트)의 CRC-16이 0xCF56
3. 헤더 0x000~0x15D의 CRC-16이 0x15E에 기록

CRC-16 패치(Python 스크립트의 요지): CRC-16/MODBUS 꼴(초기값 `0xFFFF`, 반사 다항식 `0xA001`)로
헤더 `0x000~0x15D` 를 계산해 `0x15E` 에 리틀엔디안으로 쓴다(로고 구간 `0x0C0~0x15B` 는 `0xCF56` 확인용).
우리가 쓰려면 파일 이름만 바꾸면 되고, 헤더를 고친 **뒤에** 돌려야 한다.
- 원문 코드 보관: `docs/reference/_inventory/code/sunlightface-nds-xor-backbuffer.md` (로컬 전용, 커밋 안 함) · 원문은 위 URL.

방식 1 — XOR: A⊕B=C로 그리고, C⊕B=A로 지운다(같은 데이터를 다시 XOR하면 원복). 핵심 그리기 루프(halfword씩 화면 프론트버퍼 0x06800000에 직접 EOR):
- **무엇**: 8×8 스프라이트를 프론트버퍼에 halfword 단위 EOR 로 찍는 루틴.
- **핵심 기법**: 시작 주소 = `0x06800000 + x*2 + y*512`. 한 줄 8픽셀을 읽어-EOR-쓰고, 줄 끝마다 512바이트 내려간다.
  같은 루틴을 한 번 더 부르면 지워진다.
- **우리가 쓰려면**: 쓸 일은 사실상 없다 — 아래 한계 때문에 비교용 기준선이다.
한계: 지우고 다시 그리는 사이 LCD가 갱신돼 깜빡임 발생, VBlank 미동기(Delay 루프뿐), 스프라이트 겹치면 XOR 간섭으로 색 손상, 검정(0x0000) 배경에서만 정상.

방식 2 — 백버퍼 + VBlank + DMA: CPU는 메인 RAM의 BackBuffer(256×192×2)에만 렌더하고, VBlank(라인 192~262) 동안 DMA로 VRAM(0x06800000)에 통째로 전송한다. bit15로 투명 판정해 겹침·임의 배경 지원. 프레임 루프:
- **무엇**: 키 입력 → 백버퍼 지우기 → 스프라이트 그리기 → VBlank 대기 → DMA 전송을 도는 프레임 루프.
- **핵심 기법**: VBlank 대기는 VCOUNT(`0x04000006`)가 192가 될 때까지 폴링. 전송은 DMA3(`0x040000D4`)에
  SAD=BackBuffer · DAD=`0x06800000` · CNT=켜기 비트 + 32비트 단위 + 워드 수(256×192×2 ÷ 4)를 차례로 쓴다.
- **우리가 쓰려면**: 목적지(VRAM 뱅크·모드)와 전송 크기를 대상 화면에 맞춘다. 타이밍이 빡빡하면 전체 전송 대신
  바뀐 줄만 보낸다.
- 원문 코드 보관: `docs/reference/_inventory/code/sunlightface-nds-xor-backbuffer.md` (로컬 전용, 커밋 안 함) · 원문은 위 URL.
DrawSprite는 `tst r3, #0x8000; beq Skip`으로 bit15가 꺼진 픽셀은 투명 처리(스킵)한다.

비교표:

| 항목 | XOR | 백버퍼+DMA |
|------|-----|-----------|
| 깜빡임 | 있음 | 없음 |
| VRAM 직접 수정 | 함(프론트버퍼) | 안 함(백버퍼) |
| VBlank 동기 | 없음 | 있음 |
| 투명 처리 | 불가 | bit15로 구분 |
| 스프라이트 겹침 | XOR 간섭 | 정상 |
| 배경 제한 | 검정만 | 임의 배경 |

### NDS Nitro 2D Sprite Resource Format

- URL: https://sunlightface.github.io/nds/NDS-Nitro-2D-Sprite-Resource-Format/
- 도구: (포맷 분석 문서. Nitro SDK 리소스 파일 대상)

닌텐도 DS Nitro 엔진의 2D 스프라이트 리소스 4종 포맷. 전부 리틀엔디안, BOM 0xFEFF, 버전 0x0100 통일. 매직은 역순 기록(예: NCLR → "RLCN").

NCLR (Nitro CoLoR, 팔레트):
- 파일 헤더 16바이트: 0x00 매직 `RLCN`, 0x04 BOM 0xFEFF, 0x08 파일 크기(가변)
- PLTT 팔레트 테이블: 색은 RGB555, `R5 | (G5<<5) | (B5<<10)`

NCGR (Nitro Character Graphic, 타일):
- CHAR 데이터 헤더(24바이트): 0x18 tilesY(8px 단위), 0x1A tilesX(8px 단위), 0x1C pixelFmt(3=4bpp, 4=8bpp)
- 타일 데이터는 4bpp 리니어, 각 타일 `32 << boundary` 바이트 정렬

NCER (Nitro CEll, 셀/OAM): 셀 = 여러 OAM 객체. OAM 속성 6바이트:
- attr0: Y좌표, OBJ Mode, 모자이크, 색상모드, Shape
- attr1: X좌표, H/V-Flip, Size
- attr2: 타일 인덱스, 우선순위, 팔레트 인덱스

Shape/Size → 픽셀 크기:
| Shape | Size0 | Size1 | Size2 | Size3 |
|-------|-------|-------|-------|-------|
| 정사각 | 8×8 | 16×16 | 32×32 | 64×64 |
| 가로 | 16×8 | 32×8 | 32×16 | 64×32 |
| 세로 | 8×16 | 8×32 | 16×32 | 32×64 |

NANR (Nitro ANimation, 애니메이션):
- 시퀀스 배열(16바이트): numFrames, loopStart, playMode(1=forward, 2=forward_loop, 3=reverse, 4=reverse_loop)
- 프레임 배열(8바이트): resultOffset, duration(프레임 단위)
- 결과 배열: cellIndex로 NCER 셀 참조

### 발키리 프로파일 -죄를 짊어진 자- 한글 패치 (배포글 + 기법 목록)

- URL: https://sunlightface.github.io/nds/발키리프로파일_죄를-짊어진자-패치/
- 도구/기법: 16색→256색 확장 + 알파블렌딩 합성(글자 렌더링 개선), CRI CPK 미들웨어 프리웨어판 리버싱(음성/영상 재압축), Nitro SDK 2D Sprite Resource Format 분석 + OAM 매핑, Extended VRAM 동작 메커니즘 이해·검증, 가변폭 폰트. xdelta 패치 배포(MD5 포함). (구체 절차는 미기재, 적용 기술만 나열)

### 패미컴 워즈DS 한글 패치 (배포글 + 기법 목록)

- URL: https://sunlightface.github.io/nds/패미컴-워즈DS-한글-패치/
- 도구/기법: 폰트 확장, 애니메이션 개조, 타일 이미지 확장, 한글 자판 입력 시스템. xdelta 배포(MD5 44F7D625F1CCA24CB5E203119FAAFA4E, 2026/01/27 초판). (구체 절차 미기재)

### 드래곤 볼 카이 -사이어인의 내습- 그래픽 패치 (배포글)

- URL: https://sunlightface.github.io/nds/사이어인-내습-그래픽-패치/
- 내용: xdelta 그래픽 패치. Morb님 블로그의 한글 패치 위에 추가 적용. 기존 패치 기반이라 CRC 미언급, 테스트 미진행. 제작 기술 세부는 없음.

## 기타

### [TAS] Advanced V.G. 2

- URL: https://sunlightface.github.io/etc/TAS-Advanced-V.G.-2/
- 도구/기법: 에뮬레이터 Lua/메모리 스크립트로 TAS 제작. 메모리 주소를 `800C8E78,WORD` 형식으로 워칭해 체력·게이지·위치를 추적하고, `memory.writebyte(0xc941c,0x2f)`처럼 기술 데이터·입력 코드·히트수를 직접 기록해 조작. 원본 TAS 파일은 유실되어 해킹 기록만 남음.

### 에세이/회고 (비기술)

블로그 etc 카테고리의 나머지 글은 롬해킹 씬·개인 회고 등 비기술 에세이다. 참고용 목록:
- 왜 점점 좋은 자료가 사라지는가 — https://sunlightface.github.io/etc/왜-점점-좋은-자료가-사라지는가/
- 도구만 바뀌었지 인간은 그대로다 — https://sunlightface.github.io/etc/도구만-바뀌었지-인간은-그대로다/
- 아쉬운 생각들.. — https://sunlightface.github.io/etc/아쉬운-생각들/
- 어느 소규모 바이럴 마케팅 회사에서의 1년 — https://sunlightface.github.io/etc/어느-소규모-바이럴-마케팅-회사에서의-1년/
- 추억의 스컬걸즈 — https://sunlightface.github.io/etc/추억의-스컬걸즈/
