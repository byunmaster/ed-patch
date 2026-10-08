# 참고자료 — 카페 리서치 아카이브

레트로게임 한글화 커뮤니티에서 **기법·분석·도구 자료를 선별·정리**한 폴더.
우리 로드맵(PS1 → SFC·MD·PCE·SS·PSP·PC98·Windows)에 두루 쓸 재사용 기법을 모아둔다.
배포·인사·요청 글은 제외하고, 실제로 따라할 수 있는 기술 내용만 남긴다.

수집 대상 카페는 셋이고, **서로 겹치지 않는 자리를 메운다**:

| 슬러그     | 카페                              | clubid     | 무엇이 있나                                              |
| ---------- | --------------------------------- | ---------- | -------------------------------------------------------- |
| `hansicgu` | 한글화하는 사람들의 모임 (한식구) | `16259867` | 콘솔 전반 · 강좌 · 툴 · AI 워크플로 — **본류**           |
| `koeimod`  | KOEI 게임 연구소                  | `28702069` | **PC98·DOS** 코에이 게임 개조·한글패치, 조사·폰트 계산식 |
| `msx`      | MSX의 천국                        | `24860319` | MSX 본체 + **타기종 이식**(PCE·PC88·PC98·DOS·SFC·MD)     |

## 문서 구성

| 파일                            | 내용                                                                                                                                                             |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `our-findings.md`               | ⭐ **우리 프로젝트가 직접 발견·검증한 기법**(축적용 살아있는 문서 — 새 발견은 여기로)                                                                            |
| ↳ 짝: `../patcher-checklist.md` | ⭐ 위 발견을 **플랫폼 무관 체크리스트**로 정리(새 게임의 출발점 · 스킬 `patcher-safety`)                                                                         |
| `mistranslation-patterns.md`    | ⭐ **오역이 나는 자리 — 유형 대장**(옛 번역본을 저본으로 쓸 때. 게임 무관 — 다음 프로젝트에서 볼 자리를 좁힌다)                                                  |
| `translation-conventions.md`    | ⭐ **한글 출력 조판/표기 규약**(부호 뒤 공백 제거 등 — 새 규칙은 여기로)                                                                                         |
| `eiyuu-setting.md`              | ⭐ **영웅전설 세계관·인물 관계**(플랫폼 무관 — 새턴·PC88 도 그대로 쓴다). ⚠ 출처가 팬 위키라 **정본이 아니다** — 원문과 어긋나면 원문이 이긴다                   |
| `manual-items-spells.md`        | ⭐ **아이템·주문·몬스터 매뉴얼** — `shared/glossary` 를 펼친 것(`scripts/dump_manual.py`). **플랫폼이 달라도 표기는 하나다**                                     |
| `index-by-platform.md`          | 6개 게시판에서 선별한 **플랫폼별 자료 인덱스**(제목·추천·원문링크 — 요약 발췌는 로컬 `_inventory` 참조)                                                          |
| `compression-and-encoding.md`   | LZ/LZSS 변종 압축 해제, 압축·암호화 판별, SJIS↔JIS·UTF-8 인코딩 변환, 정규표현                                                                                   |
| `fonts-korean.md`               | 한글 픽셀폰트 자원(갈무리 등), 7비트 완성형 음절표, 폰트 제작 스크립트                                                                                           |
| `ps1-saturn.md`                 | PS1·세가새턴: 디버거 폰트 찾기, 팔레트 추출, mkpsxiso, 이미지 파일 구조                                                                                          |
| `sfc-pc98.md`                   | SFC ROM 확장·포인터, 비트→폰트 출력 원리, PC98 3bpp/1bpp 그래픽                                                                                                  |
| `koei-pc98-dos.md`              | ⭐ **PC98·DOS 기법**(koeimod) — 완성형 종성 판정·폰트 오프셋 계산식·칸 우겨넣기·대사길이 게이트·DOSBox 디버깅·NPK/RLE/LS11                                       |
| `msx-and-ports.md`              | **MSX·타기종 이식 사례**(msx) — PCE 이스4/에메랄드 드래곤, DOS 젤리아드, PC88 바리스, MSX 폰트 확장                                                              |
| `psp-and-handhelds.md`          | PSP 내장폰트 확장·prx, 기드라 분석, GB/GBC/GBA/NDS 기법                                                                                                          |
| `windows-pc-and-workflow.md`    | 유니티 SDF 폰트 교체, 엔진별 한글화, 입문 워크플로, DeepL 기계번역                                                                                               |
| `ai-workflow.md`                | **AI 활용 한글화**: 번역 프롬프트, AI OCR 폰트테이블, LZSS 재압축 보조, 파라트랜즈+Gemini                                                                        |
| `qa-nuggets.md`                 | 질의응답 게시판에서 건진 실전 해법(댓글 답변 위주), 플랫폼별                                                                                                     |
| `worklog-sfc-gb.md`             | SFC·GB 단계별 실전 작업일지(패트레이버·세일러문·아크맨3·잔쿠로무쌍검)                                                                                            |
| `worklog-consoles.md`           | PS/SS/PSP/PCE·일반 작업후기(자막시스템 구현·내장폰트 우회·폰트 위치 찾기)                                                                                        |
| `basics-and-hubs.md`            | 기초 개념·플랫폼 허브 **색인**(입문서·모음집은 카페북 페이지라 본문 추출 불가 → 주제+URL만)                                                                      |
| `external-sites.md`             | **카페 밖** 강좌 블로그·커뮤니티·국제 레퍼런스·폰트·도구 마스터 목록                                                                                             |
| `blog-snowyegret.md`            | snowyegret 블로그(한글화·롬해킹·툴 제작, 카페 최다 인용) 강좌 정리                                                                                               |
| `blog-sunlightface.md`          | sunlightface(일광면) PS1 한글화 강좌 정리                                                                                                                        |
| `blog-etc.md`                   | mushsooni·ohgoru 블로그 정리                                                                                                                                     |
| `_inventory/*.jsonl`            | 게시판별 전체 글 메타데이터 원본(제목·요약·추천·조회·id). 인덱스의 원천. **로컬 전용(gitignore)** — 타인 게시글 발췌라 리포에 담지 않음. 아래 재현 절차로 재수집 |

> `index-by-platform.md`의 "범용·기타"는 추천순 상위 120건만 표시한다. 전체는 `_inventory/`의 원본 JSONL 참조(로컬 재수집 필요).

## 게시판 지도 (menuid)

### 한식구 (`hansicgu`)

공부방&도구 6개:

| menuid | 게시판           | 수집 건수 |
| ------ | ---------------- | --------- |
| 27     | 한글화 강좌      | 288       |
| 61     | 롬 분석          | 196       |
| 19     | 한글화 툴        | 306       |
| 38     | 한글화 관련 자료 | 173       |
| 41     | 프로그램 강좌    | 11        |
| 32     | 프로그래밍       | 53        |

추가 조사(공부방&도구 외):

| menuid   | 게시판                     | 상태                                         |
| -------- | -------------------------- | -------------------------------------------- |
| 12       | 질의응답                   | 2,050건 → `qa-nuggets.md`로 알짜 선별        |
| 71       | 작업/후기                  | 376건 → 실전 작업일지 선별 → `worklog-*.md`  |
| 73       | AI 활용                    | 65건 중 47건 요약 → `ai-workflow.md`(2026-10-08) |
| 56       | 한글화 입문서              | 6건 → `basics-and-hubs.md`                   |
| 57       | 한글화 모음집              | 12건(플랫폼 링크허브) → `basics-and-hubs.md` |
| 35       | 공식 한글화 정보           | 96건 — 대부분 배포뉴스라 **문서화 생략**     |
| 28/39/40 | 개발자 공간/포럼/Win32 API | **비어 있음**(글 0, 접근제한 아님)           |
| 31       | 주요 Site                  | **비어 있음**                                |

그 외 저가치라 미수집: 자유(2)·구인구직(29)·요청및문의(51)·공개번역(62)·간단번역(30)·한글화스샷(14)·한글패치(21)·리뷰(25)·맞춤법(66)·소식류(8/22/74).

### KOEI 게임 연구소 (`koeimod`)

게시판이 **130개가 넘는데 대부분이 게임별 편집방**(「삼국지4」·「대2]그래픽 편집」…)이다.
**게임 무관한 칸만** 연다 — 나머지는 `scripts/cafe/sources.json` 의 `candidates` 에 남겨 두고
필요할 때 `menus` 로 옮긴다.

| menuid | 게시판             | 수집 | 무엇이 있나                                                |
| ------ | ------------------ | ---- | ---------------------------------------------------------- |
| 69     | 연구 자료실        | 57   | ⭐ 데이터 구조 분석 · 조사 처리 · 폰트 계산식 · DOS 디버깅 |
| 93     | 프로그램 툴 자료실 | 30   | ⭐ 폰트·압축·tbl·검사기 등 **도구 원본**                   |
| 86     | 한글패치 자료실    | 40   | PC98/DOS 코에이 한글패치 배포(기법은 얕다 — 색인용)        |
| 16     | 정보게시판         | 15   | PC98 실기·에뮬 정보                                        |
| 15     | 질문게시판         | 64   | hex edit·에뮬 설정 실전 문답                               |

미수집: 게임별 편집방 전부 · 자료실류(73·104·139) · 팁&공략(114) · 스탭(105).

### MSX의 천국 (`msx`)

| menuid | 게시판               | 수집 | 무엇이 있나                                             |
| ------ | -------------------- | ---- | ------------------------------------------------------- |
| 66     | 타기종 - 활용/관리   | 757  | ⭐ **MSX 밖 한글화 작업기**(PCE·PC88·PC98·DOS·SFC·MD)   |
| 67     | 타기종 - 질문/답변   | 146  | 위의 실기 검증 문답                                     |
| 16     | 기술/개발 이야기     | 383  | 하드웨어 제작기가 다수 — **폰트 확장·분석 글만** 건진다 |
| 24     | 시스템: BIOS/툴      | 143  | 한글 BIOS·디스크롬 디스어셈블 자료                      |
| 25     | 일반: 베이식/도스/롬 | 222  | 베이식·DOS 유틸                                         |
| 28     | 문서: 텍스트         | 287  | Z80·VDP·BASIC PDF 문서, 어셈 소스                       |
| 6      | 질문/답변            | 2000 | 한글롬·폰트팩 문의가 반복적으로 올라온다                |

미수집: 게임 자료실(26·27·29·30) · 하드웨어(18) · 소모임·장터·친목 전부.

## 카페 접속·수집 방법 (재현용)

**입구는 `sh scripts/cafe.sh` 하나다.** 로그인 세션이 필요한 카페라
**CDP(Chrome DevTools Protocol)로 로그인된 크롬에 붙어** 카페 JSON API 를 부른다.

```bash
sh scripts/cafe.sh chrome                   # CDP 크롬 (없으면 띄우고, 있으면 확인만)
sh scripts/cafe.sh list                     # 카페 좌표 · 게시판별 수집 현황
sh scripts/cafe.sh fetch hansicgu           # 전 게시판 **증분** 수집 (menuid 를 대면 그것만)
sh scripts/cafe.sh fetch koeimod 69 93      #   게시판을 골라서
sh scripts/cafe.sh body koeimod 69 717 663  # 글 본문·댓글 받기
sh scripts/cafe.sh probe https://cafe.naver.com/새카페 --save 슬러그 --name "이름"
```

- 좌표(clubid · menuid)는 코드가 아니라 **`scripts/cafe/sources.json`** 에 있다.
- 수집물은 `docs/reference/_inventory/<카페슬러그>/{menuid}.jsonl`, 본문은 그 아래 `bodies/`.
- **증분이 기본**이다 — 이미 받은 글이 나오는 면에서 멈춘다. 전량은 `--full`.

### 자격증명은 어디에도 두지 않는다

인증은 스크립트가 아니라 **크롬 프로필**이 든다. 쿠키는 `~/.cache/chrome-cdp-profile` 안에 있고
in-page `fetch(url, {credentials:'include'})` 가 자동으로 싣는다. 스크립트가 아는 건 CDP 포트뿐이다.

- 네이버는 캡차·2단계·기기등록이 걸려 **아이디/비번을 넣어도 자동 로그인이 안 된다.**
  전용 프로필에 **사람이 한 번** 로그인해 두는 지금 방식이 유일하게 도는 길이다.
- 🔴 **쿠키를 파일로 떨구지 않는다.** 그건 세션 탈취용 토큰이고 이 레포는 공개 전제다
  ([`../publishing.md`](../publishing.md)).

### 걸리는 자리 (전부 실측)

1. **Chrome 136+ 는 기본 프로필에서 원격 디버깅을 막는다** → 전용 `--user-data-dir` 이 필수다.
   `cafe.sh chrome` 이 대신 띄운다. 옛 인스턴스가 살아 있으면 플래그가 무시되니
   `sh scripts/cafe.sh chrome --restart`.
2. **websocket 핸드셰이크 403** — Origin 헤더를 보내면 크롬이 거절한다. 스크립트는
   `suppress_origin` 으로 아예 안 보낸다(그래서 `--remote-allow-origins` 없이도 붙는다).
3. **`/json/new` 는 GET 이 아니라 PUT 이다**(GET 은 405). 빈 새 탭만 있으면 그 탭을 쓴다.
4. 🔴 **`Page.navigate` 로 목록을 직접 열면 SPA 가 안 채운다**(iframe 미하이드레이션).
   **반드시 API.** 탭은 `cafe.naver.com` 에 세워 두기만 한다.
5. 🔴 **수집 0건은 에러가 아니라 빈 결과로 온다** — 그 프로필이 그 카페에 가입돼 있는지,
   등급 제한 게시판은 아닌지 먼저 의심한다. 스크립트가 그 경고를 낸다.
   (⚠ 읽기만 하는 데는 대개 가입이 필요 없다 — msx·koeimod 둘 다 비가입 상태로 읽혔다.)
6. **JSON 대신 HTML 이 오면 로그인이 풀린 것**이다. 스크립트가 그렇게 알려 준다.
7. ⚠ **옛 수집분은 `id`·조회수가 int 로 들어 있다** — 문자열과 안 맞아 이미 받은 글이 매번
   신규로 다시 붙었다(실측 2026-08-30). 읽을 때 전부 문자열로 맞춘다.

### 카페 내부 JSON API

- **게시판 목록**: `https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{clubid}/menus/{menuid}/articles?page={n}&pageSize=50&sort=TIME`
  → `result.articleList[].item` 에 `articleId`·`subject`·`summary`·`likeCount`·`commentCount`·`readCount`·`hasImage`·`hasLink`·`writeDateTimestamp`·`writerInfo`.
- **글 본문**: `https://apis.naver.com/cafe-web/cafe-articleapi/v3/cafes/{clubid}/articles/{id}?query=&menuId={menuid}&boardType=L&useCafeId=true&requestFrom=A`
  → `result.article.contentHtml`(스마트에디터 HTML) + `result.comments.items`(댓글, 첫 면만).
- **게시판 목록(menuid) 캐기**: 공개 menu API 는 카페마다 죽어 있어서(500 `잘못된 접근입니다`),
  `probe` 는 **카페를 열고 DOM 의 좌측 메뉴 링크에서 줍는다.** clubid 는 리다이렉트된 URL
  (`/cafes/<숫자>`)에서 얻는다.
- ⚠ 스마트에디터는 따옴표·등호까지 엔티티로 쓴다(`&#x27;`·`&#x3D;`). 안 풀면 본문에 박힌
  **오프셋 표기(`44D4C=44D4F`)가 깨진다** — 본문 추출기가 두 번 unescape 한다.

### 저작권 — 수집물은 커밋하지 않는다

`_inventory/` 는 gitignore 다(타인 게시글 원문·발췌). 커밋되는 건 **우리 말로 재구성한 요약 +
원문 링크**뿐이다. **새 카페도 예외 없다.**
