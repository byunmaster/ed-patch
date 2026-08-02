# CLAUDE.md — 작업 규칙 (레포 공용)

팔콤 『영웅전설』 시리즈 패치 통합 저장소. 트랙이 셋이고 한 벌의 originals·하네스를
공유한다. 사람용 개요는 README.md.

| 트랙    | 뜻                                     | 현재 게임         |
| ------- | -------------------------------------- | ----------------- |
| **kr**  | 일본 원판 한글 번역 패치               | `games/ps1-ed1+2` |
| **fix** | 국내 정발판의 이식 결함 복원(버그픽스) | `games/dos-ed2`   |
| **mod** | 기능 개조                              | (아직 없음)       |

## 세션 시작 시

1. **작업할 게임의 `games/<게임>/CLAUDE.md`를 읽는다** — 트랙별 규칙은 거기 있다.
   이 파일에는 트랙과 무관한 공용 규칙만 둔다.
2. 그 게임의 **HANDOFF를 읽는다**(`games/<게임>/docs/HANDOFF.md`) — 살아있는 상태
   문서다. 세션 끝에 "현재 상태"·"다음 할 일"을 갱신하되 **커밋에는 넣지 않는다**.

## 저장소 맵

```
games/<게임>/       게임별 코드베이스 — tools/ docs/ patches/ textmap/ assets/ + work/
  ps1-ed1+2/        [kr]  PS1 영웅전설 1+2 한글패치
  dos-ed2/          [fix] 만트라 DOS 영웅전설 II 복원
shared/             플랫폼 공용 라이브러리 (SJIS 스캔, ISO9660, 폰트 변환, 한글 조판 krwrap)
scripts/            진입점 셸 스크립트 — dosbox.sh(정발 DOS 실행) · patcher.sh(웹 패처)
  dosbox/           └ DOSBox-X conf 템플릿 (생성물은 .local/dosbox)
.local/             이 머신 전용 (gitignore) — dosbox 실행 사본 · 패처 빌드 · 배포 레포 클론
patcher/            웹 패처 일체 — index.html.tmpl · build.py · subset_font.py · fonts.css
                    빌드하면 games/*/patches/*.json 이 인라인된 자립형 HTML 하나가 나온다
docs/               레퍼런스·공개 체크리스트·소장 컬렉션
originals/<지역>/   원본 디스크·정발판 (gitignore, 소장자 제공 — originals/README.md)
vendor/             emucap 등 서드파티 (gitignore, 읽기 전용)
```

- **originals는 어떤 트랙에서도 읽기 전용**이다. `<지역>/<플랫폼>-ed<N>` 규약
  (`kr/dos-ed2`, `jp/ps1-ed1+2`, `us/pce-ed1`). 게임 폴더명은 여기서 지역만 뺀 이름.
- 게임이 늘면 `games/<플랫폼>-ed<N>/`을 파고, 그 게임의 `CLAUDE.md`에 트랙을 적는다.

## 작업 산출물은 전부 `work/` 아래

gitignore 한 줄로 덮이고 `rm -rf work/` 가 곧 리셋이다. 성격이 다르니 칸을 나눈다 —
경로 상수는 `games/<게임>/tools/common.py` 가 정본이다.

```
games/<게임>/work/
  derived/   OUT_DIR     원본에서 파생 — ⚠ **빌드가 읽는 입력**이다. 지우면 빌드가 안 돈다
  review/    REVIEW_DIR  검토표·페이로드 — ⚠ **원문·정발 문안 포함, 커밋 절대 금지**
  build/     BUILD_DIR   테스트 이미지(BIN/CUE) — 순수 출력, 2분이면 재생성
  dist/      DIST_DIR    배포 차분(xdelta/BPS) — 아직 미사용
```

루트에는 `work/` 를 두지 않는다. 스크립트가 만드는 머신 전용물은 **`.local/`** 이다
(dosbox 실행 사본 · 패처 빌드 · 배포 레포 클론). 두 단어로 갈린다 — **`work` 는 게임 작업물,
`.local` 은 머신 전용.** 숨김인 이유는 gitignore 라서가 아니라 사람이 거의 안 열기 때문이다.

⚠ `derived/` 를 "산출물이니 재생성되겠지" 하고 버리면 **빌드가 아예 안 돈다**(2026-07-30 레포
이관 때 실제로 겪었다). `derived/text/` 는 파생 출력이고, 커밋되는 소스는 `textmap/` 이다.

## 빌드 & 테스트

```bash
python3 games/ps1-ed1+2/tools/build.py     # [kr] 전 트랙 체인 → work/build/Eiyuu Densetsu (KR).bin/.cue
sh scripts/patcher.sh serve                # [fix] 웹 패처를 로컬에서 띄워 확인
sh scripts/check-updates.sh                # 외부 의존물(emucap·스킬·템플릿) 새 버전 확인
sh scripts/dosbox.sh ed1|ed2|ed3|ed4       # 정발 DOS판 실행 (문안 대조 · DOS 패치 검증)
```

- 테스트 이미지는 `games/ps1-ed1+2/work/build/Eiyuu Densetsu (KR).bin/.cue` **하나만** 유지.
- `dosbox.sh`는 원본을 읽기만 하고 **본체 사본**(`.local/dosbox/<game>`)을 실행한다 —
  세이브·설정은 물론 DOS 패치 파일을 덮어써 가며 검증할 수 있다. CD는 읽기 전용이라
  사본을 안 뜨고 originals에서 직접 마운트한다(4개 전부 떠도 사본 68MB).
  `--app`·`--debug`·`--refresh` 참조.
- 인게임 확인: emucap MCP(mednafen) 또는 유저 DuckStation. **유저가 직접 확인하는 쪽이
  훨씬 빠름** — 빌드 완료를 알리고 유저 스크린샷으로 검증받는 흐름 권장.

- ⚠ mednafen은 디스크 캐시 → 빌드 교체 후 reset 무효. 프로세스 kill + 재launch.
- ⚠ **emucap 어댑터 빌드는 macOS 에서 `flock` 이 필요**하다(0.12부터). 스톡 macOS 엔
  `flock`·`lockf` 둘 다 없어 `ERROR: lockf or flock is required` 로 즉시 죽는다 —
  `brew install flock`. `vendor/` 는 읽기 전용이라 스크립트를 고치지 않는다.
- ⚠ emucap 을 올리면 **MCP 서버(메모리)·어댑터(디스크)·에뮬레이터 바이너리** 셋이 엇갈린다.
  서버는 Claude Code 재시작, 에뮬레이터는 `adapters/<이름>/build.sh` 로 맞춘다.

### 트랙을 병행할 때 — git worktree

트랙끼리는 파일 트리·원본·에뮬이 안 겹쳐서 동시에 굴릴 수 있다. 워크트리로 빼면
`work/`가 분리돼 서로의 빌드·사본을 안 건드리고 커밋도 브랜치별로 갈린다.

자리는 **`.claude/worktrees/<이름>`** — Claude Code가 만드는 워크트리의 기본 위치라
손으로 만드는 것도 여기 맞춘다(gitignore 처리돼 있다).

```bash
git worktree add -b fix/dos-ed2-se .claude/worktrees/ed2-se
cd .claude/worktrees/ed2-se
for r in kr jp us; do ln -sfn "../../../../originals/$r" "originals/$r"; done
```

⚠ **`originals/`는 gitignore라 워크트리에 안 따라온다.** 지역 폴더(`kr`/`jp`/`us`)를
심볼릭 링크로 이어야 도구가 원본을 찾는다 — `originals/README.md`는 추적되는 파일이라
`originals/` 디렉터리 자체는 이미 있으니 통째로 걸면 `originals/originals`가 된다.
반드시 그 **안에** 지역별로 건다. 워크트리가 레포 안에 있으므로 링크가 레포 밖을
가리키지 않아, 레포 폴더를 옮겨도 안 끊긴다.
`vendor/`·`.emucap/`도 같은 이유로 안 따라온다(필요한 트랙에서만 이어주면 된다).

## Git 정책

- **커밋은 유저가 "커밋해줘"라고 명시할 때만.** 자동/단계별 커밋 금지(유저가 계속
  squash해야 해 번거로움). 작업 자체는 확인 없이 자율 진행하되 **커밋만 게이팅**.
  여러 단계 작업은 한 커밋으로 묶는 걸 선호.
- **푸시 금지** — 릴리스는 유저가 직접.
- **원본 게임 데이터 커밋 절대 금지** — `originals/` `work/` `out/` `vendor/` `.emucap/`,
  디스크 이미지(*.bin/.cue/.iso …)는 gitignore. BIOS·에뮬 바이너리도 금지.
- **`vendor/`는 읽기 전용** 서브레포(emucap 등) — 커밋·수정 금지, 빌드해서 도구로만 사용.
- 코드·커밋에 **로컬 절대경로(`/Users/...` 등) 금지**.
- 커밋 메시지 끝: `Co-Authored-By: Claude <noreply@anthropic.com>`.
- 릴리스 태그는 `<게임>-<트랙>-v<버전>` (`ps1-ed1+2-kr-v1.0.0`, `dos-ed2-fix-v1.0.0`).

## 저작권 — 리포에 원본을 남기지 않는다

이 레포는 **공개를 전제로 관리한다**(배포 페이지 `ed-patch`는 이미 공개). 그래서
소스·산출물 어디에도 원저작물의 축자 복제가 남으면 안 된다. 트랙별로 지키는 방식:

- **[kr] 문장급 문안은 코드에 임베드 금지.** 문장 테이블은 `textmap/*.json`(정발 원본
  포인터 + 우리 번역) → `tools/derive_text.py`가 빌드 시 소장 원본(originals/)에서
  파생. JP 키는 sha1 해시. 단어 수준 명칭·라벨(아이템·몬스터·지명·메뉴)은 저작권
  대상이 아니라 코드 유지 OK.
- **[fix] 패치 스펙에 원본 바이트 금지.** `patches/*.json`(패치 스키마 v2)은 우리가 쓴 값
  (`to`)과 원본/결과의 sha1만 담는다. 이 JSON은 웹 패처 HTML에 통째로 인라인돼
  공개 배포되므로 `from` 같은 원본 바이트 필드를 되살리면 안 된다.
- **[kr] 패치를 `games/*/patches/*.json`으로 만들지 말 것.** 그 JSON은 커밋되는데
  kr의 `to` 바이트는 파생된 정발 문안 전량이라 위 규칙과 정면으로 충돌한다(크기도
  2.5MB). kr 배포물은 `work/`의 빌드 산출물(xdelta/BPS)로 만든다 — 근거와 수치는
  `docs/publishing.md`의 "패처를 다른 게임으로 넓힐 때".
- 공개 전 점검 절차: **`docs/publishing.md`**.

## 코드 스타일

- Python: **ruff** (`python3 -m ruff check --fix` + `python3 -m ruff format`). 설정 `ruff.toml`
  (line 100, py312, I/UP/B). 리버싱 관용상 한 글자 변수·매직 오프셋 상수 허용.
- Markdown: **oxfmt**로 정리.
- 주변 코드의 주석 밀도·명명·관용을 따른다(도구 스크립트는 한국어 주석 + 헥스 오프셋 상수).
