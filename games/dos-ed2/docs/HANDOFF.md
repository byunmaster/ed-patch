# 핸드오프 — 이어서 작업하기

마지막 갱신: 2026-07-30(5차). 브랜치 `main`.

## 2026-07-30 — 레포 통합으로 바뀐 것

`ed2-mantra-restore`가 영웅전설 패치 통합 저장소의 `games/dos-ed2/`로 들어왔다
(커밋 7개 히스토리 보존). 이 문서의 명령은 전부 갱신해 뒀지만, 손이 기억하는 것과
다른 부분:

- 저장소 루트가 한 단계 위다 — 명령은 **레포 루트에서** 돌린다
  (`python3 games/dos-ed2/tools/...`). `.venv` 대신 시스템 `python3`.
- 원본은 `originals/kr/dos-ed2`, 사본은 `work/dosbox/ed2` (한 단계 얕아졌다).
- `scripts/`(dosbox.sh·patcher.sh)와 `patcher/`(웹 패처 일체)는 **레포 공용**으로 올라갔다.
- **패치 포맷이 v2로 바뀌었다** — 원본 바이트(`from`)를 담지 않고 파일 sha1로
  검증한다. 웹 패처 HTML에 스펙이 통째로 인라인돼 공개 배포되기 때문이다
  (공개 페이지에 원본 822B가 실려 나가고 있었다). 복원은 백업(`<파일>.orig`) 기반.
  → `docs/publishing.md`
- `originals/kr/dos-ed2`의 `F_501`/`F_502`가 패치된 채로 있었다(원본은 `.bak`).
  **원본으로 되돌렸다** — sha1 확인 완료(`15ccf218…`/`e002c40b…` = 스펙의 `sha1_from`),
  `.bak`도 정리했다. originals는 읽기 전용이 원칙이니 실험은 반드시
  `work/dosbox/ed2` 사본에서 한다.

## 한 줄 요약

**이슈 #1 원인 확정 + 수정 동작 확인.** 원인은 `F_501`/`F_502`에
**`ALGO_00` export 누락**. 엔진 `FIELD_MAIN`(#354)이 필드 씬 DLL에서
인덱스 2 = `ALGO_00`을 `GetProcAddress`로 찾는데 F(Field) 계열 12개 중
이 둘만 없다. `tools/ne_add_export.py`로 `F_500`의 6바이트 thunk를 이식하니
**가이드 나레이션이 정상 출력**됐다. `ED2MAIN.EXE`는 손대지 않는다.

```bash
python3 games/dos-ed2/tools/ne_add_export.py originals/kr/dos-ed2/SCENA/F_501.DLL ALGO_00 \
    --model originals/kr/dos-ed2/SCENA/F_500.DLL --out work/dosbox/ed2/SCENA/F_501.DLL
# F_502 도 동일
```

**스엘 귀환까지 무사 완주 확인됨.** 배포 수단(CLI 스펙 + 웹 패처)까지 만들었다 —
아래 "배포" 절 참조. 남은 일은 패처를 올릴 공개 리포지토리를 만드는 것뿐이다.

## 지금 상태

### 증상 (수정 전, 실측)

스엘 마을에서 10000G 지불 → 승선 → **월드맵 위를 배가 몇 칸 항해** →
나레이션이 한 번도 못 뜨고 크래시. PC엔진판에서는 가이드 나레이션 5단계를 거쳐
스엘로 귀환한다(사용자 캡쳐로 확인).

```
UNHANDLED EXCEPTION 0D at 0217:0C9C  Error code: 501C
AX=000D BX=1396 CX=0001 DX=004C SI=2200 DI=34CE BP=0FA6 SP=0F98
```

레지스터가 매 실행 거의 동일하다(BX/DI만 진행 경로에 따라 변동).

### 폴트 지점 (2차 증상)

`ED2MAIN` seg4:0x0c9c. `Scenario_Load`(seg4:0x0a49)가 **첫 동작으로 부르는
"직전 모듈 FreeLibrary" 헬퍼**(seg4:0x0c64)의 복귀 `retf`. 겉보기엔 스택 손상이나
**진짜 원인은 아래 `ALGO_00` 누락**이고, 이건 그 실패 처리 경로에서 터진 것이다.

폴트 시 `SS=0277 Limit=FDF0 segment #0C`(= seg12, ED2MAIN의 DGROUP)이고
`SP=0x0F98`이다. NE 헤더가 `autodata=seg12, heap=0x1000, stack=0x1400`,
초기화 데이터 `0xd9f0` → `0xd9f0+0x1000+0x1400 = 0xFDF0`으로 실측 Limit과 정확히
일치하므로 **진짜 스택 영역은 0xE9F0~0xFDF0**이다. 즉 `SP=0x0F98`은 스택이 아니라
전역 데이터 한복판 — 그래서 그 주변 워드(`0x0FA7`, `0x501C`)를 스택 프레임으로
읽는 해석은 전부 무의미하다. seg4의 함수 5개가 쓰는 전용 스택 `seg12:0x2b7b`도
같은 DGROUP 안이다.

### 확정 — 호출 그래프 (4차)

```
DLL 코드 ─(엔진 API)─> ...
        seg86:0x591a  LOAD_SCENARIO (ED2MAIN export #280)
          └ seg86:0x595c  lcall ──> seg4:0x0a49  Scenario_Load   (비공개)
                                     └ 0x0a4d lcall ──> seg4:0x0c64  모듈 해제 (비공개)
                                                          └ 0x0c85 lcall KERNEL.#96 FreeLibrary
                                                                     └ 대상 DLL의 WEP (seg1:0x00b4)
                                                                        └ 0x00dd lcall KERNEL.#96 ← **또 FreeLibrary**
```

- 해제 헬퍼(0x0c64) 호출자는 딱 둘: `seg4:0x0a4e`(Scenario_Load), `seg5:0x0117`(종료).
- `Scenario_Load` 호출자는 **딱 하나**: `seg86:0x595d`.
- `LOAD_SCENARIO`를 직접 부르는 시나리오 DLL은 `T_551` 하나뿐 — 일반 씬 전환은
  `ENTER_PROG` → 메인 루프 경유다.
- **DS 정체 해명**: `seg86:0x5950`이 `mov ds, seg12` 후 호출한다. 엔진 전역
  (`[0x2f7c]`, `[0x0bfa]`, `[0x26ac]`)은 전부 **seg12**에 있다.
- **`04D7:23A4`는 DOS 종료 경로**다(`mov ss,[0x96af]` → `mov ax,4c00h; int 21h`).
  3차의 2차 크래시는 트램폴린 버그가 아니라 "엔진이 중단하려다 죽은 것"이 맞다.

### 확정 — 진짜 원인: `F_501`/`F_502`의 `ALGO_00` export 누락

`Scenario_GetFuncPtr`(seg4:0x0bab)의 **호출자 9곳이 넘기는 인덱스**를 전수로
뽑으면 답이 나온다(인덱스 0=`SINAL_INIT`, 1=`SINAL`, 2=`ALGO_00`, 3~~21=`ALGO_01`~~`19`):

| 호출자                                                    | 인덱스      | 찾는 export      |
| --------------------------------------------------------- | ----------- | ---------------- |
| `FIELD_START` #355                                        | 0           | `SINAL_INIT`     |
| **`FIELD_MAIN` #354**                                     | **2**       | **`ALGO_00`**    |
| `EXEC_EVENT` #353                                         | 1           | `SINAL`          |
| `TOWN_START` #933 / `UDG_START` #936 / `MG_WARP_SUB` #501 | 0           | `SINAL_INIT`     |
| `SINAL_KEY_IN` #869                                       | 1           | `SINAL`          |
| `TOWN_ALGO` #667                                          | `(bx>>1)+2` | `ALGO_xx` (동적) |
| `_ALGO_00_5..9_MAIN` #533/517/519/572/577                 | 7~11        | `ALGO_05`~`09`   |

**`FIELD_MAIN`이 필드 씬 DLL에서 `ALGO_00`을 요구한다.** `F_` 접두는 **Field**고
유람선은 월드맵 위를 항해하므로 정확히 이 경로다. 그리고 F 계열 12개
(`F_000/001/002/200/201/202/400/401/402/500/501/502`) 중 **`F_501`/`F_502`만
`ALGO_00`이 없다**.

`0217:0C9C` GP fault는 **2차 증상**이었다 — `GetProcAddress`가 NULL을 반환한 뒤
실패 처리 경로가 `seg12:0x2b7b` 전용 스택 위에서 돌다 터진 것이다. 그래서
스택 전환을 들어내자(`patches/diag-no-stack-switch-all3.json`) GP fault가 사라지고
진짜 진단(`Where : Scenario_GetFuncPtr / What : Fails in getting func ptr`)이
드러났다.

#### 3차 결론은 맞았고, 4차 초반의 "반증"이 틀렸다

4차에 전수 조사로 "356개 중 176개가 `ALGO_00` 없이 정상 동작"을 근거로
`ALGO_00` 부재설을 기각했는데, **그 기각이 오판이었다.** 그 176개는 마을·이벤트
씬이라 `FIELD_MAIN`을 타지 않는다. `ALGO_00`이 필수인 건 **필드 씬뿐**이고,
비교 모집단은 전체 SCENA가 아니라 **F 계열**이 맞았다.

교훈: export 유무의 통계만으로 판단하지 말고 **엔진이 그 export를 언제 요구하는지**
(= `GetFuncPtr` 호출자의 인덱스)를 먼저 확인할 것. `scan_exports.py`는
모집단을 잘못 잡으면 정반대 결론을 준다.

### 수정 — `ALGO_00` thunk 이식

`F_500`의 `ALGO_00`은 6바이트 무동작 스텁이다:
`9a ff ff 00 00 cb` = `lcall ED2MAIN.HOOK_RET(#566)` + `retf` (ptr32 fixup 1개).
이걸 `tools/ne_add_export.py`로 대상 DLL seg3 **끝에** 덧붙이고 entry table /
resident-name table / NE 헤더 오프셋을 갱신한다. 세그먼트 뒤 패딩에서 자리를
빌리므로 **파일 크기와 모든 세그먼트 sector 오프셋이 그대로**다.

```bash
python3 games/dos-ed2/tools/ne_add_export.py originals/kr/dos-ed2/SCENA/F_501.DLL ALGO_00 \
    --model originals/kr/dos-ed2/SCENA/F_500.DLL --out work/dosbox/ed2/SCENA/F_501.DLL
python3 games/dos-ed2/tools/ne_add_export.py originals/kr/dos-ed2/SCENA/F_502.DLL ALGO_00 \
    --model originals/kr/dos-ed2/SCENA/F_500.DLL --out work/dosbox/ed2/SCENA/F_502.DLL
```

결과: `F_501` seg3 0x819→0x81f, `#5 ALGO_00 @ seg3:0x819`.
`ED2MAIN.EXE`는 **손대지 않는다**.

> **함정 — `minalloc`**: 세그먼트 테이블 엔트리는 `{sector, length, flags, minalloc}`
> 이고 이 게임의 DLL은 전부 `minalloc == length`다. DPMI 로더는 **`minalloc`으로
> 셀렉터를 만든 뒤 파일에서 `length`만큼 읽어 넣는다.** `length`만 늘리면 로더가
> 마지막 바이트를 쓰다가 죽는다:
>
> ```
> Limit check 81a+1-1 = 81a > 819 ES:DI
> UNHANDLED EXCEPTION 0D at 00B7:13EE   ← CS=00B7 은 ED2MAIN도 DLL도 아닌 로더 코드
> ES = 059F Limit =0819 segment #03 of SCENA\F_501.DLL   DI = 081A  CX = 0005
> ```
>
> `ne_add_export.py`는 둘 다 갱신한다.

### 검증 (실측 완료)

승선 → 월드맵 항해 → 가이드 나레이션(관광 투어 환영 인사) → 전 구간 진행 →
**스엘 마을 귀환까지 무사 완주**.
PC엔진판 레퍼런스와 일치한다.

## 배포

패치 소스는 **`patches/issue-1-suel-boat-tour.json` 하나**고, CLI 패처와 웹 패처가
같은 파일을 읽는다. 그래서 둘이 어긋날 일이 없다. xdelta/IPS는 쓰지 않는다 —
변경이 연속 구간 5개·748B뿐이라 JSON에 그대로 담기고, **파일 sha1 판본 검증**이
공짜로 따라온다(IPS엔 없다). 스펙에 원본 바이트는 담지 않는다(패치 스키마 v2).

```
F_501.DLL  32784B  5개 구간  598B (1%)     ← 파일 크기 불변
F_502.DLL  31760B  5개 구간  150B (0%)
```

```bash
# 1) 수정본 생성 → 스펙 생성 (원본은 절대 건드리지 않는다)
python3 games/dos-ed2/tools/ne_add_export.py originals/kr/dos-ed2/SCENA/F_501.DLL ALGO_00 \
    --model originals/kr/dos-ed2/SCENA/F_500.DLL --out /tmp/F_501.DLL
python3 games/dos-ed2/tools/gen_patch.py --out games/dos-ed2/patches/issue-1-suel-boat-tour.json \
    --issue 1 --name "..." --desc "..." \
    --diff SCENA/F_501.DLL originals/kr/dos-ed2/SCENA/F_501.DLL /tmp/F_501.DLL \
    --diff SCENA/F_502.DLL originals/kr/dos-ed2/SCENA/F_502.DLL /tmp/F_502.DLL

# 2) CLI 적용 (--check / --revert 도 된다)
python3 games/dos-ed2/tools/apply_patch.py games/dos-ed2/patches/issue-1-suel-boat-tour.json work/dosbox/ed2

# 3) 웹 패처 확인 — 배포는 main 머지 뒤 Pages 워크플로가 한다(옛 deploy 는 2026-10-07 에 걷었다)
sh scripts/patcher.sh              # 빌드해서 로컬에 띄워 확인
```

웹 패처는 `patcher/index.html.tmpl` + 스펙을 합친 **자립형 HTML 하나**(약 30KB)다.
외부 요청이 없고 파일이 브라우저 밖으로 나가지 않는다. 486 데스크탑 화면에서
**디스켓을 드라이브에 넣으면** 게임 폴더를 묻고, File System Access API로
제자리 수정한 뒤 원본을 `.BAK`으로 남긴다. 진행 상황은 CRT에 DOS 프롬프트로
찍힌다. 적용 전에 크기·SHA-1·`from` 바이트를 대조해 판본 불일치와 재적용을 막는다.

- **Chrome·Edge 전용**이다(File System Access API). 다른 브라우저에서는 화면에
  그렇게 안내하고 디스켓을 비활성화한다. 파일 업로드/다운로드 방식은 쓰지 않는다.
- 디스켓이 슬롯으로 빨려 들어가는 이동량은 JS가 `getBoundingClientRect`로 실측해
  `--dx`/`--dy`에 넣으므로 반응형에서도 정확히 들어간다. `prefers-reduced-motion`
  존중.
- **이슈 #2가 생기면 디스켓을 여러 장으로** 늘린다. `patcher/build.py`는 이미
  `kind == "fix"` 스펙을 전부 싣지만, 현재 UI는 디스켓 한 장이 전체 스펙을
  처리한다. 스펙별 디스켓으로 나누려면 `SPECS`를 순회해 디스켓을 렌더링하고
  클릭한 디스켓의 스펙만 적용하도록 바꾸면 된다.

> **공개 범위**: 이 리포지토리는 비공개다. GitHub Free는 비공개 리포지토리로
> Pages를 배포할 수 없으므로, **패처 전용 공개 리포지토리**(예: `ed2-mantra-patch`)를
> 따로 파서 생성된 `index.html` 하나만 올린다. 이름을 `<user>.github.io`로 하면
> 루트 URL을 먹으니 프로젝트 리포지토리로 만들 것.
> 공개되는 원본 바이트는 748B(전체의 2%, 대부분 링커 relocation 테이블)다.

## 다음에 할 일

1. 패처 전용 공개 리포지토리 생성 + Pages 활성화, `--repo` 에 그 URL을 넣어 재빌드.
2. 이슈 #2(그로스토스성 성문 SE 누락) 착수. 스펙이 늘면 `patcher/build.py`가
   `patches/`의 `kind == "fix"` 스펙을 자동으로 모두 싣는다.

## 실행 환경 (DOSBox-X)

```bash
sh scripts/emu/dosbox.sh ed2 --app     # 반드시 --app. 셸에서 직접 띄우면 키보드가 죽는다
```

클론 직후 바로 된다. `scripts/emu/dosbox.sh ed2`가 `originals/kr/dos-ed2` → `work/dosbox/ed2` 사본을
자동 생성하고, `scripts/emu/dosbox/game.conf.tmpl`의 `@GAME@`·`@DRIVE@`·`@CMD@`·`@MOUNTCD@`·
`@SBTYPE@`·`@SBIRQ@`를 채워 `work/dosbox/ed2.conf`를 만든다. 경로는 전부 상대라
생성 conf 에 로컬 절대경로가 안 남는다 — **클론 위치가 달라도 그대로 동작한다.**

- `scripts/emu/dosbox/game.conf.tmpl` — `usescancodes=false`, `autolock=false` 필수
  (macOS SDL1 키보드 먹통 원인). 생성물을 직접 고치지 말고 템플릿을 고칠 것
- `work/dosbox/ed2/` = `originals/kr/dos-ed2` 쓰기 가능 사본(33M, gitignore).
  `originals/`는 어떤 실험에서도 건드리지 않는다
- `-log-con` 기본 활성 → DOS 콘솔 출력이 `work/dosbox/ed2.log`에 남는다.
  게임이 그래픽 모드라 엔진의 `Where`/`What` 진단이 화면엔 안 보인다.
- `--debug`(DOSBox-X 디버거)는 **기동 시 세그폴트가 잦아 실용성 없음**.
  절차는 `03-debugger.md`에 남겨뒀다.
- 세이브는 사용자 제공분이 `originals/kr/dos-ed2/SAVE/`에 있다.

### 실행 스크립트 공용화 (해결 — 2026-07-30 레포 통합)

한글패치 저장소가 이 저장소로 합쳐지면서 두 벌의 DOSBox 하네스도 하나가 됐다.
정본은 레포 루트의 `scripts/emu/dosbox.sh` + `scripts/emu/dosbox/game.conf.tmpl`이고, 여기서
쓰던 `scripts/emu/dosbox.sh`·`scripts/emu/dosbox/game.conf.tmpl`은 지웠다.

정본이 나은 점(그대로 얻은 것):

- **상대경로** — `work/dosbox`로 `cd` 한 뒤 실행해서 conf 에 로컬 절대경로가
  안 남는다(옛 `@ROOT@` 방식은 커밋되는 파일에 부적절했다).
- **CD 자동 마운트** — `--cd`, 없으면 `originals/…/CD/*.cue` 를 찾아 물린다.
  아래 "아직 안 물린 것 — CD" 가 이걸로 풀린다.
- 게임 테이블(ed1~4), `--setup`(SETUP.EXE), `--refresh`, `DOSBOX` 환경변수.
- macOS 키보드 함정(`usescancodes=false`)은 여기서 실측한 게 이미 반영돼 있다.

사본 경로가 `work/dosbox/ed2/ed2` → **`work/dosbox/ed2`** 로 한 단계 얕아졌다.
이 문서의 명령들은 갱신해 뒀다.

남은 개선 후보 둘:

1. **IRQ/Port/DMA 를 게임 CNF 에서 읽을 것.** 정본 테이블은 ed2 를 `IRQ 7`로
   하드코딩하는데, 이건 게임이 아니라 **설치본의 성질**이다(같은 `ED2MAIN.EXE`
   `a7ac15f3…` 인데 SETUP.EXE 가 설치 때 쓴 값이 설치본마다 다르다). 지금
   `originals/kr/dos-ed2/ED2.CNF`는 `IRQ = 7` 이라 우연히 맞지만, 다른 설치본을
   물리면 소리가 안 난다. `DataDir`은 이미 CNF 에서 읽어 고쳐 쓰므로 같은 자리에
   IRQ/Port/DMA 도 얹으면 된다.
2. **overlay 마운트** — 지금은 본체 33MB를 통째로 복사한다. 원본 위에 쓰기 전용
   오버레이를 얹으면 복사 0에 원본이 구조적으로 읽기 전용이 된다. 다만 그러면
   `apply_patch.py`가 쓸 대상이 오버레이에 없어서, **패치할 파일만 오버레이에
   미리 심는 단계**가 필요하다(DLL 2개 = 64KB). `--patch <spec.json>` 플래그가
   자연스럽다.

### 아직 안 물린 것 — CD

`originals/kr/dos-ed2/CD/ED2.cue`에 **오디오 트랙이 3개** 있는데 지금 실행 환경은
CD 를 마운트하지 않는다. `BGM/`의 `.MUS`/`.INS`(FM 음악)만 나오는 상태다.
**이슈 #2(성문 SE 누락)는 CD 를 물리고 판정해야 한다** — 안 그러면 CD 오디오로
트는 소리가 없는 것을 게임 결함으로 오판할 수 있다.
`GAME.BAT`은 `opening.exe` → `ed2main.exe` 순인데 우리는 오프닝을 건너뛴다
(테스트가 빨라서). 오프닝은 CD 에서 재생된다.

## 도구 (`tools/`)

| 도구               | 용도                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| `ne_info.py`       | NE 헤더/세그먼트/export 덤프                                                                     |
| `ne_relocs.py`     | relocation 파싱 (off16은 **additive** = 값이 addend)                                             |
| `ne_entries.py`    | entry table → ordinal:seg:offset. `--near SEG:OFF`로 주소→export 역추적                          |
| `annotate.py`      | 엔진 함수명까지 주석 단 디스어셈블 (제일 많이 씀)                                                |
| `scan_sym.py`      | 특정 엔진 심볼을 참조하는 자리를 SCENA 전체에서 수집                                             |
| `scan_exports.py`  | SCENA 전체 export 구성 집계. **모집단을 잘못 잡으면 정반대 결론이 나온다** — `ALGO_00` 오판 참조 |
| `scan_scenes.py`   | `ENTER_PROG` 씬 참조 전수 검증 (941건 중 938건 정상)                                             |
| `atime_probe.py`   | 파일 접근시간으로 실제 로드된 리소스 추적 (`-log-fileio`가 무용지물이라 대체)                    |
| `apply_patch.py`   | 파일 sha1 검증 후 패치 적용/복원 (`--check`/`--revert`/`--force`)                                |
| `ne_add_export.py` | **NE DLL에 export 이식** (본보기 DLL에서 thunk+reloc을 뜬다). `length`와 `minalloc`을 함께 갱신  |
| `gen_patch.py`     | 원본/수정본 diff → `apply_patch.py` 스펙(JSON) 생성                                              |

레포 공용 도구는 루트 `tools/` 에 있다 — `patcher/build.py`(스펙 +
`patcher/index.html.tmpl` → 자립형 웹 패처 HTML), `subset_font.py`(갈무리 폰트 서브셋).

## 스크립트 (레포 루트 `scripts/`)

| 스크립트        | 용도                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------- |
| `dosbox.sh ed2` | 게임 구동. `--app`(macOS 키 입력) / `--debug` / `--refresh`. 설정은 `scripts/emu/dosbox/game.conf.tmpl` |
| `patcher.sh`    | 웹 패처 `build` / `serve` / `deploy`. 하위 명령을 생략하면 `serve`                                  |

```bash
sh scripts/patcher.sh                       # = serve. 빌드해서 127.0.0.1:8731 로 띄운다
```

- **`file://`로 열면 안 된다** — `showDirectoryPicker`가 보안 컨텍스트를 요구해서
  디스켓을 눌러도 아무 반응이 없다. `127.0.0.1`은 보안 컨텍스트로 쳐준다.
- 세 갈래가 모두 스크립트 안의 `build()` 하나를 거친다. `serve`로 본 것과
  `deploy`되는 것이 바이트 단위로 같다는 뜻이라, 미리보기가 어긋날 수 없다.
- 푸터 소스 링크는 `patcher.sh`의 `SRC_URL` 한 줄로 정한다(현재 비어 있어 푸터가
  숨는다). 이 리포가 비공개라 걸 곳이 없어서다.

```bash
python3 games/dos-ed2/tools/scan_exports.py originals/kr/dos-ed2/SCENA --lacks ALGO_00
python3 games/dos-ed2/tools/annotate.py originals/kr/dos-ed2/SCENA/F_501.DLL 3 --from 0x630
python3 games/dos-ed2/tools/ne_entries.py originals/kr/dos-ed2/ED2MAIN.EXE --near 4:0c90
python3 games/dos-ed2/tools/atime_probe.py reset  work/dosbox/ed2   # 실행 전
python3 games/dos-ed2/tools/atime_probe.py report work/dosbox/ed2   # 크래시 후
```

## 기각된 가설 (재시도 금지)

| 가설                        | 검증                      | 결과                                               |
| --------------------------- | ------------------------- | -------------------------------------------------- |
| `ROUTE_NO=8` 인덱스 초과    | 8→4, 8→6 패치             | 레지스터까지 동일. 무관                            |
| 크래시가 `ENTER_PROG2` 하류 | `ljmp`→`retf` 1바이트     | 동일 크래시                                        |
| 종료 정리 경로              | 게임 정상 종료            | 에러 없음. 배제                                    |
| `MAP/C_017.BZH` 결번        | 대역 파일 투입            | 동일. 무관                                         |
| 목적지 씬 파일 누락         | `scan_scenes.py` 전수     | 941중 938 정상                                     |
| 유람선 커서 미초기화        | `SAVE_FLAG` 분기 NOP      | 동일 크래시                                        |
| relocation 겹침             | atype 실측                | `F_501:0x62e`는 off16(2B), 안 겹침                 |
| `WEP` 결함                  | seg1 sha1 비교            | 모든 DLL 바이트 동일                               |
| 메시지 오프셋 어긋남        | 문자열 시작 대조          | 5개 전부 일치                                      |
| 핸들러 테이블 off-by-one    | 키데이터 종료바이트 추적  | `40`×5 → `20` 정확히 떨어짐                        |
| SS:SP 전역 슬롯 재진입 충돌 | `DI`/`BP`로 복원하는 패치 | SP·BP가 패치 전과 **완전히 동일**. 슬롯은 멀쩡했다 |

`ALGO_00` 부재설을 "356개 중 176개가 없이 정상"으로 기각했던 4차 초반 판단은
**오판이었다**(그 176개는 `FIELD_MAIN`을 안 타는 마을·이벤트 씬). 위 "진짜 원인"
절 참조.

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

## 미해결 (원인과 무관, 남은 궁금증)

- `F_502`가 실제로 어느 항로에서 쓰이는지. `ALGO_00`은 같이 이식해 뒀다.
- 엔진이 `GetProcAddress` 실패를 감지하고도 계속 진행하는 점
  (`0x0c18 jne` 실패 시 NULL을 `[0x96a5]`에 저장하고 fall through).
  `GetFuncPtr` 실패 시 `HOOK_RET`를 폴백으로 넣으면 `ALGO` 누락 DLL 전반이
  안전해진다 — `ED2MAIN` 한 곳 수정으로 끝나지만, 이번 건은 DLL만 고쳐 해결했다.
- `WEP`이 부르는 `FreeLibrary([0x41])`의 `[0x41]`이 어떤 모듈 핸들인지.
  DLL seg1은 전 DLL 바이트 동일이므로 값만 다르다.

### 해결됨 (4차)

- ~~DLL 코드 실행 중 `DS`가 무엇인지~~ → **seg12**(ED2MAIN의 DGROUP).
  `seg86:0x5950`이 `mov ds, seg12` 후 엔진 API를 부른다.
- ~~seg86 트램폴린이 같은 전용 스택을 공유하는지~~ → **아니다.** 트램폴린은
  별도 슬롯 `[0x96af]`/`[0x96b1]`(seg85)에 저장하고 `SS=seg85, SP=0x90f8`로
  갈아탄다. 공유하는 건 seg4의 비공개 함수 5개(`0x2b7b`)다.
- ~~일반 정기선도 깨지는가~~ → 무의미해졌다. `F_501`은 7개 항구가 공유하는
  범용 항해 씬이고 `ALGO_00` 누락은 항로와 무관하게 필드 진입 시 터진다.
  즉 **이 배들 전부 깨져 있었고 한 번에 고쳐진다.**

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
