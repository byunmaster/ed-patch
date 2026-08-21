# CLAUDE.md — 만트라 DOS 영웅전설 II 복원 (트랙: fix)

국내 정발판 『영웅전설 II』(만트라 DOS 이식판)에서 **이식 과정에 생긴 결함**을 복구한다.
번역 프로젝트가 아니다 — 문안은 정발 그대로 두고 동작만 원본에 맞춘다.
레포 공용 규칙은 루트 `CLAUDE.md`.

- 패치 대상: `originals/kr/dos-ed2`
- 동작 레퍼런스: `originals/jp/pc98-ed2` (PC98 일판 — 원래 어떻게 동작해야 하는지의 기준)
- 배포: 웹 패처(`scripts/patcher.sh`) → 공개 리포 `ed-patch`

## 세션 시작 시

- **HANDOFF를 먼저 읽는다**: `docs/HANDOFF.md`.
- 엔진 구조는 `docs/01-scena-dll-format.md`, 디버깅 환경은 `docs/03-debugger.md`.

## 실행 · 검증

```bash
sh scripts/check.sh                      # ⭐ **커밋 전 이것 하나** (게이트: games/dos-ed2/check.sh)
sh scripts/emu/dosbox.sh ed2                 # 사본(work/dosbox/ed2)을 만들어 실행
sh scripts/emu/dosbox.sh ed2 --refresh       # 사본을 버리고 원본에서 다시 (패치 초기화)
sh scripts/emu/dosbox.sh ed2 --debug         # DOSBox-X 디버거

# 패치를 사본에 적용해 인게임 확인
python3 games/dos-ed2/tools/apply_patch.py \
    games/dos-ed2/patches/<spec>.json work/dosbox/ed2
```

- **커밋 전에는 `sh scripts/check.sh`.** ⚠ 2026-08-19 까지 **이 트랙엔 게이트가 없었다** —
  `scripts/check.sh` 가 사실상 ps1-ed1+2 전용이었다. 지금은 게임마다 `check.sh` 를 갖고
  진입점이 위임한다. 여기 게이트가 보는 것은 둘이다:
  - 🔴 **패치 스펙에 원본 바이트가 없나**(`tools/check_patches.py`). 이 JSON 은 웹 패처
    HTML 에 **통째로 인라인돼 공개 배포된다** — 한 번 새면 원저작물 조각을 배포하는 셈이다.
  - 웹 패처가 실제로 빌드되나 (스펙이 유효해도 인라인 단계에서 깨지는 자리가 있다)
- **originals는 절대 건드리지 않는다.** 실험은 전부 `work/dosbox/ed2` 사본에.
- 웹 패처 미리보기: `sh scripts/patcher.sh serve` (127.0.0.1 — `file://`로 열면
  `showDirectoryPicker`가 보안 컨텍스트를 요구해 동작하지 않는다).

## 패치 스펙 규약 (스키마 v2)

`patches/*.json`은 CLI 패처(`apply_patch.py`)와 웹 패처가 **같은 파일**을 읽는다.
웹 패처는 이 JSON을 HTML에 통째로 인라인해 공개 배포하므로:

- **원본 바이트를 담지 않는다.** 항목은 `{file, offset, to}`뿐이고, 원본 검증은
  `files[].sha1_from`/`sha1_to`/`size`(파일 전체 sha1)로 한다. `from` 필드를 되살리면
  상용 바이너리 조각을 재배포하는 셈이 된다.
- 그래서 **복원은 차분 역적용이 아니라 백업 기반**이다 — `apply_patch.py`가 적용 시
  `<파일>.orig`를 남기고 `--revert`가 그걸 되돌린다.
- 스펙은 손으로 쓰지 말고 `gen_patch.py --diff <게임내경로> <원본> <수정본>`으로 만든다.
- `kind`: `fix`(배포 대상 — 웹 패처에 실린다) · `candidate-fix` · `diagnostic`(실험용,
  배포에서 자동 제외) · 앞으로 `mod`. 패치 종류가 늘어도 `patches/`는 **평면 유지**한다 —
  `tools/`·`docs/`를 fix/mod가 그대로 공유하고, 패치끼리 바이트가 겹치는지 검사하려면
  한 디렉터리에 모여 있어야 한다. 구분은 `kind`와 파일명 접두어로 한다.

> ⚠ **같은 파일에 패치 둘을 겹쳐 올릴 수 없다.** 파일 전체 sha1 로 게이트하므로
> 첫 패치 적용 후엔 둘째의 `sha1_from` 과 어긋나 중단된다(진단용 `--force` 뿐).
> fix + mod 를 함께 적용해야 할 때가 오면 폴더를 나눠서 풀 문제가 아니라 **적용 모델**을
> 바꿔야 한다 — "원본에서 선택한 항목 전부를 한 번에 조립"(`sha1_from`은 항상 원본,
> 결과 해시는 조합별로 빌드 때 계산). 원본은 `.orig` 백업에 이미 남으니 조합이 바뀌면
> 거기서 다시 조립하면 된다.

## 패치 원칙

- **크기 불변 · 세그먼트 오프셋 불변.** NE 헤더·entry table·resident-name table을
  고쳐서 export를 늘리더라도 파일 크기와 세그먼트 sector 오프셋은 그대로 둔다
  (`ne_add_export.py`가 그 계약을 지킨다).
- **엔진(`ED2MAIN.EXE`)보다 데이터(`SCENA/*.DLL`)를 고친다.** 결함이 맵 DLL 하나에
  국한되면 그 DLL만 패치한다 — 영향 범위가 작고 되돌리기 쉽다.
- 원인 확정 전에는 `diagnostic` 패치로 가설을 하나씩 죽인다. 확정된 것만 `fix`로 승격.
