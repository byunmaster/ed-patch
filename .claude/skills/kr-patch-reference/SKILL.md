---
name: kr-patch-reference
description: >-
  레트로게임 한글화 **기법 레퍼런스 조회** 스킬 — 이 레포의 `docs/reference/` 아카이브로 라우팅한다.
  출처는 한 곳이 아니다: 커뮤니티 카페(한식구 · KOEI 게임 연구소 · MSX의 천국) · 강좌 블로그 ·
  카페 밖 국제 레퍼런스 · **우리가 직접 발견·검증한 것**을 한 아카이브에 쌓는다.
  PS1·세가새턴·SFC·PC98·DOS·PSP·MD·PCE·MSX·Windows/유니티 등 플랫폼별 역공학, LZ/LZSS·NPK·RLE 압축 해제,
  한글 픽셀폰트·SJIS/EUC 인코딩과 **문자코드→폰트 오프셋 계산식**, 완성형 **조사(종성) 판정**,
  포인터 재배치, 디버거(NO$PSX · DOSBox 디버그 빌드 · 치트엔진)로 폰트·데이터 찾기,
  AI 활용 한글화 워크플로, 질의응답 실전 해법까지 주제별 문서로 갈라 둔 아카이브다.
  이 프로젝트(eiyuu-densetsu-patch, PS1 영웅전설) 한글화 작업 중 특정 기법·사례·도구가 필요할 때,
  "이거 어떻게 하지"(폰트 찾기·압축 해제·인코딩·포인터·플랫폼별 분석·AI 번역) 참고자료를 찾을 때 사용.
  **텍스트 재삽입을 설계·수정하기 전, 또는 인게임 버그(먹통·소프트락·이벤트 정지·대사 꼬임·깨진 글자)를
  만났을 때도 반드시 조회** — `our-findings.md`에 재삽입 "구조 계약" 주의사항(창/세그먼트 수 부족 =
  소프트락, 미참조 데이터 이동 금지)과 소프트락 디버깅 절차가 있다.
  트리거: 한글화 기법 참고, 레퍼런스 조회, 카페/블로그/외부 사이트 자료, 폰트 찾는 법, 압축 해제, 포인터 재배치, 플랫폼별 한글화 방법,
  조사 처리, 받침 판정, 폰트 오프셋 계산, 칸 모자람, DOS/PC98 디버깅,
  재삽입 주의사항, 먹통/소프트락/프리징, 이벤트 진행 안 됨, 대사 꼬임, 깨진 글자, 창 수 계약, 블록 재배치.
---

# 한글패치 기법 레퍼런스

## Overview

레트로게임 한글화에 쓰는 **재사용 기법 아카이브**의 라우터다. 실제 원천 문서는 이 스킬이 아니라
repo 의 **`docs/reference/`** 에 있고, 이 SKILL.md 는 **어떤 상황에 어느 문서를 읽을지**만 안다.

**출처는 한 곳이 아니다** — 이름에 특정 출처를 안 박은 이유다:

| 출처               | 무엇                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| 커뮤니티 카페      | 한식구(`16259867`, 콘솔 전반) · KOEI 게임 연구소(`28702069`, PC98·DOS) · MSX의 천국(`24860319`, 타기종 이식) |
| 강좌 블로그        | snowyegret · sunlightface(PS1) · mushsooni · ohgoru                                                          |
| 카페 밖 사이트     | 국제 레퍼런스(psx-spx 등) · 폰트·도구 — `external-sites.md`                                                  |
| **우리 실전 발견** | `our-findings.md` — ⭐ **이 아카이브의 중심.** 새 발견은 여기로                                              |

⇒ 출처가 늘어도 **문서는 주제별로 갈리고 이 표만 는다.** 새 출처를 여기에 한 줄 더한다.

작업 중 특정 기법·사례가 필요하면 아래 표에서 맞는 문서를 골라 `Read` 로 열어라.
문서 안 각 항목엔 원문 URL 이 있으니 더 깊이 필요하면 원문을 다시 볼 수 있다.

## 라우팅 — 무엇이 필요할 때 어느 문서를 읽나

| 상황·키워드                                                                                                                                                     | 읽을 문서                                                                    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **우리가 직접 발견·검증한 기법** (커뮤니티 자료 아닌 우리 것)                                                                                                   | `docs/reference/our-findings.md`                                             |
| **⚠ 재삽입 설계·수정 전 필독 / 먹통·소프트락·이벤트 정지·대사 꼬임 디버깅** — 구조 계약(세그먼트 수·`%s`·제어코드), 미참조 데이터 이동 금지, 소프트락 진단 절차 | `docs/reference/our-findings.md` (⚠ 구조 계약 절)                            |
| **번역·조판 규약** (한글 출력 표기 규칙 — 부호 뒤 공백 제거 등)                                                                                                 | `docs/reference/translation-conventions.md`                                  |
| **옛 번역본을 저본으로 쓸 때 어디서 어긋나나** — 오역 유형 대장(방향·낱말 수준만, 문안은 안 남긴다). 정발 대조 판정 전에 본다                                   | `docs/reference/mistranslation-patterns.md`                                  |
| **어디부터 볼지 모름 / 특정 게임·플랫폼 자료 목록**                                                                                                             | `docs/reference/index-by-platform.md` (720건 플랫폼별 인덱스)                |
| **PS1 / 세가새턴** — 디버거로 폰트 찾기(NO$PSX·루아), 팔레트 추출, mkpsxiso, CD 섹터 구조, 1bpp→4bpp                                                            | `docs/reference/ps1-saturn.md`                                               |
| **SFC / PC98** — ROM 영역 확장·포인터 재계산, 비트→폰트 출력, PC98 3bpp/1bpp 그래픽                                                                             | `docs/reference/sfc-pc98.md`                                                 |
| **PC98 / DOS 기법 · 조사(종성) 판정 · 문자코드→폰트 오프셋 계산식 · 칸에 글자 우겨넣기 · 대사길이 게이트 · DOSBox·치트엔진 디버깅 · NPK/RLE/LS11 압축**         | `docs/reference/koei-pc98-dos.md`                                            |
| **MSX · 타기종 이식 사례** — PCE(이스4·에메랄드 드래곤) BIOS 폰트/스프라이트 자막, DOS 젤리아드, PC88 섹터 분석, MSX 폰트 확장                                  | `docs/reference/msx-and-ports.md`                                            |
| **PSP / GB·GBC·GBA·NDS** — 내장폰트 확장, prx 하드코딩, 기드라 분석, VRAM 타일, unpack/repack                                                                   | `docs/reference/psp-and-handhelds.md`                                        |
| **Windows/PC·유니티·엔진** — SDF 폰트 교체, 엔진별 한글화, 입문 워크플로, DeepL MT                                                                              | `docs/reference/windows-pc-and-workflow.md`                                  |
| **압축·인코딩** — LZ/LZSS 변종 해제, 압축·암호화 판별, SJIS↔JIS·UTF-8 변환, 정규표현                                                                            | `docs/reference/compression-and-encoding.md`                                 |
| **한글 폰트·인코딩표** — 갈무리 등 픽셀폰트 자원, 7비트 완성형 음절표, 폰트 제작 스크립트                                                                       | `docs/reference/fonts-korean.md`                                             |
| **AI 활용 한글화** — 번역 프롬프트, VLM OCR 폰트테이블, AI로 LZSS 재압축, Claude+emucap 실전팁, 파라트랜즈+Gemini                                               | `docs/reference/ai-workflow.md`                                              |
| **막힌 문제의 실전 해법** — 페르소나·SFC 드퀘·PS1 압축·유니티 대사찾기 등 질의응답에서 건진 해법                                                                | `docs/reference/qa-nuggets.md`                                               |
| **SFC·GB 단계별 실전 walkthrough** — 패트레이버·세일러문·아크맨3·잔쿠로무쌍검 작업일지(분석→폰트/대사 확장→VRAM→압축)                                           | `docs/reference/worklog-sfc-gb.md`                                           |
| **PS/SS/PSP/PCE 작업후기** — 자막 시스템 구현(령 제로3·악마성), 내장폰트 우회(PSP), 폰트 위치 찾기, 대사 씹힘 해결                                              | `docs/reference/worklog-consoles.md`                                         |
| **기초 개념** — 포인터·HEX·고유코드 등 (색인 형태)                                                                                                              | `docs/reference/basics-and-hubs.md`                                          |
| **카페 밖 자료처** — 다른 강좌 블로그·커뮤니티(DCinside·Arca)·국제 레퍼런스(psx-spx 등)·폰트·도구                                                               | `docs/reference/external-sites.md`                                           |
| **블로그 강좌** — snowyegret(한글화·툴), sunlightface(PS1), mushsooni·ohgoru                                                                                    | `docs/reference/blog-snowyegret.md` · `blog-sunlightface.md` · `blog-etc.md` |

## 카페에서 자료를 더 가져와야 할 때

**도구가 있다 — 직접 CDP 를 짜지 않는다.**

```bash
sh scripts/cafe.sh chrome                    # 로그인된 CDP 크롬
sh scripts/cafe.sh list                      # 카페 좌표·수집 현황
sh scripts/cafe.sh fetch <카페> [menuid…]    # 증분 수집
sh scripts/cafe.sh body <카페> <menuid> <글id…>
sh scripts/cafe.sh probe <카페주소> --save <슬러그>   # 새 카페
```

좌표는 `scripts/cafe/sources.json`, 수집물은 `docs/reference/_inventory/<카페>/`(gitignore).
함정과 API 상세는 **`docs/reference/README.md`** 의 「카페 접속·수집 방법」.
⚠ `cafe.sh` 는 **네이버 카페 전용**이다 — 블로그·외부 사이트는 그냥 읽고 요약해서
해당 주제 문서(`blog-*.md` · `external-sites.md` 등)에 넣는다.
🔴 **수집물은 커밋하지 않는다** — 커밋되는 건 우리 말로 재구성한 요약 + 원문 링크뿐이다.

## 우리 발견을 축적하라

작업 중 **새로 발견·검증한 해결책이 이 문서들에 없으면 추가**한다(프로젝트 방침).
관련 플랫폼 문서에 주제가 있으면 거기 보강, 없으면 `docs/reference/our-findings.md`에 기록.
확정된 것만, 추정은 "가설"로. 커뮤니티 자료 + 우리 실전 발견을 한 곳에 쌓는 게 이 아카이브의 목적이다.

## create-kr-patch 스킬과의 관계

`create-kr-patch`(외부 플러그인)는 한글화 **전 과정을 수행**하는 스킬이다. 이 `kr-patch-reference`는 그 작업 중
**검증된 구체 기법·사례를 조회**하는 보완재다. 한글화 작업을 진행하다 특정 플랫폼의 실전 기법이나
남들이 어떻게 풀었는지가 필요하면 이 스킬의 문서를 참고하라. (이 스킬은 우리 repo 전용이며 create-kr-patch 플러그인은 건드리지 않는다.)
