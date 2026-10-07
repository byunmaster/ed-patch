# 공통 확인 눈금 — 스물둘 (정본 `docs/ed1-phases.md`, 2026-09-15 신설)

PS1 ED1+2 는 다른 이식판의 **잣대**(`docs/ui-canon.md`)라, 정작 표준 22항목 눈금이
이 문서엔 없었다(관리자 09-15 지적 — 여덟 게임 중 이 게임과 `ss-ed1+2` 만 빠져 있었다).
값은 여기, **근거·상세**는 `docs/ui-canon.md`(UI 자리·정렬 규칙) ·
`docs/ed1-status.md`·`docs/ed2-status.md`(편별 진행)를 가리킨다 — 문안 정본은 옮기지 않는다.

⚠ PS1 은 **ED1+ED2 합본**이라 대부분 항목이 편마다 갈린다 — 두 값을 같이 적는다.
`—` 는 그 게임에 없는 화면(B3 「건네기」는 PS1 ED1 파티 메뉴에 없다).

| ID | 항목 | ED1 | ED2 | 확인 빌드 · 근거 |
| --- | --- | --- | --- | --- |
| A1 | 커맨드 창 | ✅ | ✅ | `ui-canon.md` ①-a(`ui-1a-커맨드.png`) |
| A2 | 상태 창 | ✅ | ✅ | `ui-canon.md` ①-b(`ui-1b-상태.png`) |
| A3 | 시스템 설정 창 | ✅ | ✅ | `ui-canon.md` ①-c(`ui-1c-시스템설정.png`) |
| A4 | 전투 설정 창 | ✅ | ✅ | `ui-canon.md` ①-c(`ui-1c-전투설정.png`) |
| A5 | 저장·로드 창 | ✅ | ✅ | `ui-canon.md` ①-d(`ui-1d-저장로드-ED2-결함.png` — 결함 아님, 오독이었음) |
| A6 | HUD | ✅ | ✅ | `ui-canon.md` ①-e(`ui-1e-HUD.png`). ⚠ 경로 라벨 구분자(하이픈) 되읽기는
`check_copy_completeness.check_route_label_separator()`(18칸) — 이번 라운드 몫 아님, 다음 A6 재확인 때 참조 |
| B1 | 도구 사용 결과 | 🔧 | ⬜ | 검사기(`check_josa_agreement` 등) 통과, 화면 미확인 — 던전 진입 필요 |
| B2 | 주문 사용 결과 | 🔧 | ⬜ | 위와 같음 |
| B3 | 장비·버리기·건네기 | 🔧 | ⬜ | 「건네기」는 PS1 ED1 파티 메뉴에 없음(`ui-canon.md` 참조) — 장비·버리기만 해당 |
| B4 | 상점 창 | ✅ | 🔧 | ED1 은 044(상점 구매문 134곳) 반영·화면 확인 이력 있음(devlog), ED2 미확인 |
| B5 | 보물상자·획득 안내 | ✅ | ✅ | 045·063 등 반영, `check_scn_jp_left` 게이트 |
| C1 | 전투 커맨드 | ✅ | ✅ | `ui-canon.md` ③, `textmap/battle.json`·`battle_ed2.json` 대조 완료 |
| C2 | 몬스터 등장·이름 | ✅ | ✅ | 047·034 등 다수 QA 라운드로 화면 확인 |
| C3 | 행동 메시지 | ✅ | ✅ | 041①·042 등으로 화면 확인 |
| C4 | 상태이상 | ✅ | ✅ | 034(상태 라벨 ED2.EXE 사본 포함) 화면 확인 |
| C5 | 레벨업 | 🔧 | 🔧 | 검사기 통과, 이번 라운드 화면 재확인은 안 함 |
| C6 | 승리·패배·도망 | ✅ | ✅ | `textmap/battle.json` 승리 로그 3종 등 화면 확인 |
| D1 | 오프닝 내레이션·자막 | ✅ | ✅ | 🖥 **2026-09-15 이번 라운드 확인** — 정상 부팅으로 재생, `textmap/opening.json`·`opening_ed2.json` 문안과 일치. 스크린샷 미보관(육안 확인, 화면 자체는 화질 손실 없이 재현 가능) |
| D2 | 장 카드·챕터 전환 | ✅ | ✅ | 🖥 **2026-09-15 확인** — ED1 "제1장 왕자의 여행"(`.local/work/inbox/ps1-ed1+2/d2-chapter1-ed1.png`), ED2 "서장 평화로운 나날"(`d2-chapter1-ed2.png`). `patch_gfx_cards.CARDS` 12개 중 챕터1만 실제로 봤다 — 나머지 10개는 그림 재작성 파이프라인이 같아 위험 낮음(미완주) |
| D3 | 엔딩·스태프롤 | ✅ | ✅ | 🖥 **2026-09-15 확인** — `movie_swap()`(`ED_MOVIE_SWAP="OPEN1=END1,OPEN2=END2"`)으로 부팅 직후 재생, `textmap/ending_ed1.json`·`ending_ed2.json` 문안과 일치(ED1: `movie-swap-ending-poc-2.png`, ED2: `d3-ending-ed2-poc.png`). 기법은 `docs/reference/our-findings.md` 참조 |
| E1 | 타이틀 로고 | ✅ | ✅ | `ui-canon.md` ⑤(`ui-5-타이틀-컬렉션.png`·`ui-5-타이틀-ED2.png`) — 그림 |
| E2 | 처음부터/이어하기·파일 선택 | ✅ | ✅ | 이번 라운드 D1/D2 확인 중 자연히 통과(타이틀→서브타이틀→New/Continue 메뉴 전부 한글) |

## D1~D3 상세 경위 (2026-09-15)

- **부팅 경로**: BIOS 로고 → GMF → Falcom → 대표제목(`영웅전설` 콜라주) → START →
  ED1/ED2 선택 → **오프닝 내레이션(D1)** → 서브타이틀("The Legend of Heroes Ⅰ/Ⅱ") →
  처음부터/이어하기(E2) → **첫 대사 직전 장 카드(D2)**.
- **D2 는 별도 풀스크린 카드가 아니라 HUD 하단 배너**(필드 창의 이름표 자리에 뜬다) —
  대사 한 번(아무 키)을 진행해야 나타난다. 부팅 직후 화면만 보면 "카드가 없다"로
  오판하기 쉽다(첫 시도 때 300프레임씩 건너뛰다 놓쳤다).
- **D3 는 세이브 없이 확인**(`our-findings.md` 「부팅 직후 오프닝 자리에 엔딩을 띄운다」)
  — ED1·ED2 둘 다 스왑 후 자막이 각 `ending_ed1.json`·`ending_ed2.json` 문안과 글자까지
  일치함을 확인했다. ⚠ 스왑 빌드는 **검증 전용**(환경변수 게이트, 배포 빌드엔 안 씀).
