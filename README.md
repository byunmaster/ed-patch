# 영웅전설 패치 프로젝트

팔콤 『영웅전설』(드래곤 슬레이어 계보) 시리즈의 패치를 만드는 통합 저장소입니다.
리버싱·도구 제작에 Claude Code를 활용합니다.

트랙이 셋이고, 소장 원본 한 벌과 공용 하네스(DOSBox 실행, 웹 패처, 폰트·조판
라이브러리) 위에서 같이 굴러갑니다.

| 트랙    | 뜻                                     | 대상                         |
| ------- | -------------------------------------- | ---------------------------- |
| **kr**  | 일본 원판을 한국어로 번역              | 일본 원판 (`originals/jp`)   |
| **fix** | 국내 정발판의 이식 결함 복원(버그픽스) | 국내 정발판 (`originals/kr`) |
| **mod** | 기능 개조                              | (아직 없음)                  |

패치 파일에는 원본 게임 데이터가 포함되지 않습니다. 적용하려면 직접 소장한 원본이
필요합니다.

## 패치 현황

| 게임                             | 트랙 | 플랫폼           | 상태              | 배포                                                    |
| -------------------------------- | ---- | ---------------- | ----------------- | ------------------------------------------------------- |
| [영웅전설 1+2](games/ps1-ed1+2/) | kr   | PS1 (SLPS-01323) | 🔧 리버싱 진행 중 | -                                                       |
| [영웅전설 II](games/dos-ed2/)    | fix  | 만트라 DOS 정발  | ✅ 이슈 #1 해결   | [브라우저 패처](https://byunmaster.github.io/ed-patch/) |

- 릴리스 태그는 `<게임>-<트랙>-v<버전>` 형식입니다 (`ps1-ed1+2-kr-v1.0.0`,
  `dos-ed2-fix-v1.0.0`). 완성된 패치는 [Releases](../../releases)에 올라갑니다.
- 정발 복원 패치는 브라우저에서 바로 적용할 수 있는 웹 패처로도 배포합니다
  (외부 요청이 0인 자립형 HTML 한 장 — 파일이 서버로 올라가지 않습니다).
- 진행 계획과 마일스톤은 [ROADMAP.md](ROADMAP.md).

## 저장소 구조

```
games/<게임>/       게임별 코드베이스 (도구 · 리버싱 노트 · 패치 스펙 · 번역 테이블)
  ps1-ed1+2/        [kr]  PS1 영웅전설 1+2 한글패치
  dos-ed2/          [fix] 만트라 DOS 영웅전설 II 복원
shared/             플랫폼 공용 라이브러리 (SJIS 스캔, ISO9660, 폰트 변환, 한글 조판)
scripts/            진입점 스크립트 — dosbox.sh(정발 DOS 실행) · patcher.sh(웹 패처)
                    dosbox/ 에 DOSBox-X 설정 템플릿
patcher/            웹 패처 일체 — 템플릿 · 빌드 · 폰트 서브셋
                    빌드하면 games/*/patches/*.json 이 인라인된 자립형 HTML 하나
docs/               레퍼런스 · 공개 체크리스트 · 소장 컬렉션
originals/          원본 게임 데이터 (gitignore — 직접 소장본으로 채움)
```

브랜치는 **`main` = 공통(`shared/` · `scripts/` · `docs/` · 스킬), `game/<타이틀>` = 각 게임**
으로 갈립니다. 게임끼리는 디스크 이미지가 달라 독립이라 워크트리로 병행합니다 —
`sh scripts/worktree.sh <게임>`. 겹치는 건 공용뿐이라, 공용은 `main` 에서만 고칩니다.

원본은 `originals/<지역>/<플랫폼>-ed<번호>/` 규약으로 한 벌만 둡니다
(`kr/dos-ed2`, `jp/ps1-ed1+2`, `us/pce-ed1`). 자세한 건
[originals/README.md](originals/README.md).

## 주요 진입점

```bash
python3 games/ps1-ed1+2/tools/build.py   # [kr] 한글패치 디스크 빌드
sh scripts/patcher.sh serve              # [fix] 웹 패처를 로컬에서 띄워 확인
sh scripts/emu/dosbox.sh ed1|ed2|ed3|ed4     # 정발 DOS판 실행 (문안 대조 · 패치 검증)
sh scripts/worktree.sh ps1-ed1+2         # 게임별 워크트리 (originals 링크까지)
sh scripts/check.sh                      # 커밋 전 — 빌드 + 화면·조판 검사
```

### 서드파티 도구

**create-kr-patch** — 한글 패치 제작 방법론 Agent Skill (추출·재삽입 전략,
라운드트립 규약의 단일 진실 원천). Claude Code 플러그인이며 **이 리포의
`.claude/settings.json`에 프로젝트 스코프로 선언**돼 있다(마켓플레이스 + 활성화).
따라서 이 리포에서만 로드되고 git으로 따라간다 — 다른 PC에서 리포를 처음 열면
Claude Code가 설치를 물어보므로 승인하면 된다(수동은 아래 한 줄).

```
claude plugin install create-kr-patch@kr-patch    # 자동 프롬프트 대신 수동 설치 시
```

**emucap** — 에뮬레이터 관찰·제어 MCP (메모리·화면·입력·브레이크포인트, 패치
디버깅·QA 자동화). Rust 빌드가 필요해 플러그인화 불가 — 클론 후 빌드해 등록한다:

```
git clone https://github.com/mcpads/emucap vendor/emucap
cd vendor/emucap && cargo build --release \
  --bin emucap --bin emucap-mcp --bin emucap-track-mcp --bin emucap-broker --bin emucap-mame-pc98-bridge
claude mcp add emucap-control -- "$(pwd)/target/release/emucap-mcp"
claude mcp add emucap-track   -- "$(pwd)/target/release/emucap-track-mcp"
```

PSX 검증은 Mednafen 포크 어댑터를 쓴다(`adapters/mednafen/build.sh`, BIOS
`scph5500.bin` → `~/.mednafen/firmware/`). BIOS·에뮬레이터 바이너리·원본은 커밋 금지.

## 소장 컬렉션

이 프로젝트는 아래 소장 원본을 기준으로 진행합니다. **[kr] 한글패치의 번역은 일본 원판에서 직접 합니다** — 국내 정발판(만트라)은 저본이 아니라 **표기 대조용**입니다. **[fix] 트랙**은 그 정발판 자체의 이식 결함을 복원하는 작업입니다.

|                                                       |                                                       |                                                        |
| ----------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| ![정발 패키지](docs/collection/kr-bigbox-series.jpg)  | ![콘솔판](docs/collection/jp-consoles-series.jpg)     | ![신 영웅전설](docs/collection/jp-windows-shin.jpg)    |
| 정발 영웅전설 시리즈                                  | SFC · 메가드라이브 · PCE-CD · 새턴 · PS1              | 신 영웅전설 — Windows                                  |
| ![영웅전설 I PC판](docs/collection/jp-retropc-1.jpg)  | ![영웅전설 II PC판](docs/collection/jp-retropc-2.jpg) | ![영웅전설 III·IV](docs/collection/jp-retropc-3-4.jpg) |
| 영웅전설 I — X68000 · FM TOWNS · MSX2 · PC-88 · PC-98 | 영웅전설 II — FM TOWNS · PC-88 · PC-98                | 영웅전설 III · IV — PC-98                              |

## 고지

- 본 프로젝트는 **비영리 팬 프로젝트**이며, 원작에 대한 어떠한 권리도 주장하지 않습니다.
- 『영웅전설』 시리즈의 저작권을 비롯한 모든 권리는 **Nihon Falcom Corporation** 및 각 권리자에게
  있습니다. 번역 저본으로 삼는 국내 정발판의 번역 문안 역시 해당 권리자에게 권리가 있습니다.
- 패치는 **차분(패치) 파일로만 배포**하며, 게임 원본 데이터·실행 파일·BIOS를 일절 포함하지
  않습니다. 적용에는 본인이 직접 소장한 원본이 필요합니다.
- 이 저장소의 소스에도 원본 게임 데이터를 남기지 않습니다 — 번역 테이블은 소장 원본에서
  빌드 때 파생하고, 패치 스펙은 바뀐 값과 검증용 해시만 담습니다
  ([docs/publishing.md](docs/publishing.md)).
- 패치의 판매·유료 배포 등 **상업적 이용을 금지**합니다.
- 권리자의 요청이 있을 경우 배포를 즉시 중단합니다.

## 크레딧

- 리버싱·도구: Claude Code 보조
- 번역: 정발판(만트라) 공식 번역 이식 + AI 번역 + 인간 QA
- 폰트: [Galmuri](https://github.com/quiple/galmuri)(Lee Minseo) ·
  [Neo둥근모](https://github.com/neodgm/neodgm)(Eunbin Jeong) — SIL OFL 1.1, 라이선스 전문 `shared/fonts/`
