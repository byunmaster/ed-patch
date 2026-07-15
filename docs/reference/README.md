# 참고자료 — 한식구 카페 리서치 아카이브

레트로게임 한글화 커뮤니티 **"한글화하는 사람들의 모임"**(네이버 카페, 통칭 *한식구*, clubid `16259867`)의
공부방&도구 게시판에서 **기법·분석·도구 자료를 선별·정리**한 폴더.

우리 로드맵(PS1 → SFC·MD·PCE·SS·PSP·PC98·Windows)에 두루 쓸 재사용 기법을 모아둔다.
배포·인사·요청 글은 제외하고, 실제로 따라할 수 있는 기술 내용만 남긴다.

## 문서 구성

| 파일 | 내용 |
|---|---|
| `our-findings.md` | ⭐ **우리 프로젝트가 직접 발견·검증한 기법**(축적용 살아있는 문서 — 새 발견은 여기로) |
| `index-by-platform.md` | 6개 게시판에서 선별한 **플랫폼별 자료 인덱스**(제목·추천·원문링크 — 요약 발췌는 로컬 `_inventory` 참조) |
| `compression-and-encoding.md` | LZ/LZSS 변종 압축 해제, 압축·암호화 판별, SJIS↔JIS·UTF-8 인코딩 변환, 정규표현 |
| `fonts-korean.md` | 한글 픽셀폰트 자원(갈무리 등), 7비트 완성형 음절표, 폰트 제작 스크립트 |
| `ps1-saturn.md` | PS1·세가새턴: 디버거 폰트 찾기, 팔레트 추출, mkpsxiso, 이미지 파일 구조 |
| `sfc-pc98.md` | SFC ROM 확장·포인터, 비트→폰트 출력 원리, PC98 3bpp/1bpp 그래픽 |
| `psp-and-handhelds.md` | PSP 내장폰트 확장·prx, 기드라 분석, GB/GBC/GBA/NDS 기법 |
| `windows-pc-and-workflow.md` | 유니티 SDF 폰트 교체, 엔진별 한글화, 입문 워크플로, DeepL 기계번역 |
| `ai-workflow.md` | **AI 활용 한글화**: 번역 프롬프트, AI OCR 폰트테이블, LZSS 재압축 보조, 파라트랜즈+Gemini |
| `qa-nuggets.md` | 질의응답 게시판에서 건진 실전 해법(댓글 답변 위주), 플랫폼별 |
| `worklog-sfc-gb.md` | SFC·GB 단계별 실전 작업일지(패트레이버·세일러문·아크맨3·잔쿠로무쌍검) |
| `worklog-consoles.md` | PS/SS/PSP/PCE·일반 작업후기(자막시스템 구현·내장폰트 우회·폰트 위치 찾기) |
| `basics-and-hubs.md` | 기초 개념·플랫폼 허브 **색인**(입문서·모음집은 카페북 페이지라 본문 추출 불가 → 주제+URL만) |
| `external-sites.md` | **카페 밖** 강좌 블로그·커뮤니티·국제 레퍼런스·폰트·도구 마스터 목록 |
| `blog-snowyegret.md` | snowyegret 블로그(한글화·롬해킹·툴 제작, 카페 최다 인용) 강좌 정리 |
| `blog-sunlightface.md` | sunlightface(일광면) PS1 한글화 강좌 정리 |
| `blog-etc.md` | mushsooni·ohgoru 블로그 정리 |
| `_inventory/*.jsonl` | 게시판별 전체 글 메타데이터 원본(제목·요약·추천·조회·id). 인덱스의 원천. **로컬 전용(gitignore)** — 타인 게시글 발췌라 리포에 담지 않음. 아래 재현 절차로 재수집 |

> `index-by-platform.md`의 "범용·기타"는 추천순 상위 120건만 표시한다. 전체는 `_inventory/`의 원본 JSONL 참조(로컬 재수집 필요).

## 게시판 지도 (menuid)

공부방&도구 6개 (수집 대상):

| menuid | 게시판 | 수집 건수 |
|---|---|---|
| 27 | 한글화 강좌 | 281 |
| 61 | 롬 분석 | 196 |
| 19 | 한글화 툴 | 302 |
| 38 | 한글화 관련 자료 | 170 |
| 41 | 프로그램 강좌 | 11 |
| 32 | 프로그래밍 | 53 |

추가 조사(공부방&도구 외):

| menuid | 게시판 | 상태 |
|---|---|---|
| 12 | 질의응답 | 2,000건 수집 → `qa-nuggets.md`로 알짜 선별 |
| 71 | 작업/후기 | 184건 수집 → 실전 작업일지 23건 선별 → `worklog-*.md` |
| 73 | AI 활용 | 23건 → `ai-workflow.md` |
| 56 | 한글화 입문서 | 6건 → `basics-and-hubs.md` |
| 57 | 한글화 모음집 | 12건(플랫폼 링크허브) → `basics-and-hubs.md` |
| 35 | 공식 한글화 정보 | 95건 — 대부분 배포뉴스라 **문서화 생략** |
| 28/39/40 | 개발자 공간/포럼/Win32 API | **비어 있음**(글 0, 접근제한 아님) |
| 31 | 주요 Site | **비어 있음** |

그 외 저가치라 미수집: 자유(2)·구인구직(29)·요청및문의(51)·공개번역(62)·간단번역(30)·한글화스샷(14)·한글패치(21)·리뷰(25)·맞춤법(66)·소식류(8/22/74/71).

## 카페 접속·수집 방법 (재현용)

로그인 세션이 필요한 카페라 **CDP(Chrome DevTools Protocol)로 로그인된 크롬에 붙어** JSON API를 호출한다.

### 1) 크롬을 CDP 모드로 띄우기 (macOS, Chrome 136+ 함정 주의)

Chrome 136+ 는 **기본 프로필에서는 원격 디버깅을 차단**한다. 반드시 **별도 `--user-data-dir` + `--remote-allow-origins`** 를 줘야 한다:

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.cache/chrome-cdp-profile" \
  --remote-allow-origins=http://localhost:9222 \
  --no-first-run --no-default-browser-check
```

- 이 전용 프로필(`~/.cache/chrome-cdp-profile`)에 **네이버 로그인을 한 번** 해두면 이후 세션에도 유지된다.
- `--remote-allow-origins` 없으면 websocket 핸드셰이크가 403으로 거부된다.
- 기존 메인 크롬과 별개 인스턴스로 공존한다. 재실행 시 옛 인스턴스가 안 죽으면 플래그가 무시되니
  `pkill -9 -f "user-data-dir=$HOME/.cache/chrome-cdp-profile"` 로 그 인스턴스만 정리 후 재실행.
- 확인: `curl -s http://localhost:9222/json/version`

### 2) 카페 내부 JSON API (page 컨텍스트에서 fetch, 쿠키 자동 포함)

- **게시판 목록**: `https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/16259867/menus/{menuid}/articles?page={n}&pageSize=50&sort=TIME`
  → `result.articleList[].item` 에 articleId·subject·summary·likeCount·commentCount·readCount·hasImage 등.
- **글 본문**: `https://apis.naver.com/cafe-web/cafe-articleapi/v3/cafes/16259867/articles/{id}?query=&menuId={menuid}&boardType=L&useCafeId=true&requestFrom=A`
  → `result.article.contentHtml`(스마트에디터 HTML) + `result.comments.items`(댓글).
- 직접 `Page.navigate`로 목록을 열면 React SPA가 목록을 안 채운다(iframe 미하이드레이션). **반드시 API로 접근**.

### 3) 수집 스크립트

세션 작업용 스크립트는 잡 tmp에 있었다(영구 아님). 재작성 시 위 API를 `Runtime.evaluate`의 in-page `fetch(url, {credentials:'include'})`로 호출하면 된다.
필요 라이브러리: `websocket-client`(.venv). 자세한 함정은 이 문서의 접속 방법 참조.
