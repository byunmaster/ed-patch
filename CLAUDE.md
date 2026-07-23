# CLAUDE.md — 작업 규칙

팔콤 『영웅전설』 시리즈 한글 패치 프로젝트. 현재 작업은 **PS1 영웅전설 1+2**
(`games/ps1-eiyuu12`). 리버싱·도구 제작 + AI 번역 + 인간 검수. 사람용 개요는 README.md.

## 세션 시작 시

- 작업 대상 게임의 **HANDOFF를 먼저 읽는다**: `games/ps1-eiyuu12/docs/HANDOFF.md`
  (살아있는 상태 문서 — 세션 끝에 "현재 상태"·"다음 할 일" 갱신).
- 표기 편차 대장: `games/ps1-eiyuu12/docs/jeongbal-deviations.md` (표기 바꾸면 갱신 의무).
- 진행 중 트랙별 상세: `docs/*-handoff.md`, `docs/*-devlog.md`.

## 빌드 & 테스트

```bash
cd games/ps1-eiyuu12
python3 tools/build.py              # 전 트랙 체인 → work/Eiyuu Densetsu (KR).bin/.cue
```

- 테스트 이미지는 `work/Eiyuu Densetsu (KR).bin/.cue` **하나만** 유지.
- 인게임 확인: emucap MCP(mednafen) 또는 유저 DuckStation. **유저가 직접 확인하는 쪽이
  훨씬 빠름** — 빌드 완료를 알리고 유저 스크린샷으로 검증받는 흐름 권장.
- ⚠ mednafen은 디스크 캐시 → 빌드 교체 후 reset 무효. 프로세스 kill + 재launch.

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

## 코드 스타일

- Python: **ruff** (`python3 -m ruff check --fix` + `python3 -m ruff format`). 설정 `ruff.toml`
  (line 100, py312, I/UP/B). 리버싱 관용상 한 글자 변수·매직 오프셋 상수 허용.
- Markdown: **oxfmt**로 정리.
- 주변 코드의 주석 밀도·명명·관용을 따른다(도구 스크립트는 한국어 주석 + 헥스 오프셋 상수).

## 번역 정책

- **정발판(만트라 DOS)에 있는 건 다 이식**(이스터에그 포함), 없는 것만 정발 문법으로 신규 번역.
- 정발 표기 그대로가 원칙. 기술 제약(슬롯·렌더폭)이나 정발 내부 불일치로 바꾼 것만
  **편차 대장(jeongbal-deviations.md)에 기록**. ED1↔ED2 표기 충돌 시 일본어 원음으로 판정.
- **문안(특히 정발 원문) 변경은 사전 보고** — 공간 부족 시 어색한 한국어·중복부터 줄여
  공간 확보, 조용히 바꾸지 않는다. 그래픽 로고류는 볼드 근사/유저 에셋 합성 OK.
- **문장급 문안은 코드에 임베드 금지**(저작권 — 팔콤 일문·만트라 문안이 리포에 남으면 안 됨).
  문장 테이블은 `textmap/*.json`(정발 원본 포인터 + 우리 번역) → `tools/derive_text.py`가
  빌드 시 소장 원본(originals/)에서 파생. 문장 추가·수정은 textmap에서, JP 키는 sha1 해시.
  단어 수준 명칭·라벨(아이템·몬스터·지명·메뉴)은 저작권 대상이 아니라 코드 유지 OK.

## 재삽입 주의 — 구조 계약 (소프트락의 근원)

**엔진은 블록의 텍스트가 아니라 "구조"를 계약으로 읽는다.** 번역문만 맞추고 구조를 바꾸면
증상이 오타가 아니라 **소프트락·이벤트 정지**로 나온다(음악은 계속 나옴 = 프리징 아님).

- **세그먼트(창) 수 부족 = 소프트락(치명)**, 초과 = 꼬리 잘림(표시 손실). 재조립본의 `%c` 수가
  원본보다 적으면 엔진이 종단을 못 만나 뒤 데이터까지 읽는다 → 깨진 글자 + 무한 대기.
- 원본의 **`%s`·`%d`·인라인 제어코드**는 장식이 아니라 흐름 제어 — 임의로 빼거나 공백 치환 금지.
- **갱신 가능한 포인터(lui+addiu/ori)로 참조되지도, 번역되지도 않는 블록은 이동 금지.**
  텍스트 영역엔 값 테이블·이름·스크립트 조각이 "블록"으로 섞여 있고, 무참조 = 절대주소로 읽힌다.
- 인게임 먹통을 만나면 코드 추적보다 **differential 빌드로 원인 계층을 이분**하는 게 훨씬 빠르다
  (`PILOT_TEXT_IDENTITY`·`PILOT_FIXED`·`PILOT_NOSPLICE`·`PILOT_IDENTITY`).

상세 규칙·체크리스트·소프트락 디버깅 절차: **`docs/reference/our-findings.md`** (⚠ 구조 계약 절).

## 저장소 맵

```
games/ps1-eiyuu12/
  tools/     패처·리버싱 도구 (build.py가 오케스트레이션, common.py 공용 헬퍼)
  docs/      HANDOFF·편차 대장·devlog (트랙별 상태·지식)
  assets/    번역 그래픽 에셋 (title_logo.png 등 — 유저 제작 커밋 OK)
  out/       분석 산출물 (gitignore)
  work/      빌드 결과 디스크 (gitignore)
shared/      플랫폼 공용 (SJIS 스캔, ISO9660, 폰트 변환)
originals/   원본 디스크·DOS 정발 (gitignore, 소장자 제공)
vendor/      emucap 등 서드파티 (gitignore, 읽기 전용)
```

- ED.EXE = LBA 257. RAM 주소 = file오프셋 − 0x800 + 0x80010000.
```
