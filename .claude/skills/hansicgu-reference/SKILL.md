---
name: hansicgu-reference
description: >-
  한식구(한글화하는 사람들의 모임) 카페에서 수집·정리한 레트로게임 한글화 **기법 레퍼런스 조회** 스킬.
  PS1·세가새턴·SFC·PC98·PSP·MD·PCE·Windows/유니티 등 플랫폼별 역공학, LZ/LZSS 압축 해제,
  한글 픽셀폰트·SJIS/EUC 인코딩, 포인터 재배치, 디버거(NO$PSX 등)로 폰트 찾기,
  AI 활용 한글화 워크플로, 질의응답 실전 해법을 담은 repo `docs/reference/` 문서로 라우팅한다.
  이 프로젝트(eiyuu-densetsu-kr, PS1 영웅전설) 한글화 작업 중 특정 기법·사례·도구가 필요할 때,
  "이거 어떻게 하지"(폰트 찾기·압축 해제·인코딩·포인터·플랫폼별 분석·AI 번역) 참고자료를 찾을 때 사용.
  트리거: 한글화 기법 참고, 카페/커뮤니티 자료, 폰트 찾는 법, 압축 해제, 포인터 재배치, 플랫폼별 한글화 방법.
---

# 한식구 카페 기법 레퍼런스

## Overview

레트로게임 한글화 커뮤니티 **"한글화하는 사람들의 모임"**(네이버 카페, *한식구*, clubid 16259867)의
공부방&도구·질의응답·AI활용 게시판에서 선별·정리한 재사용 기법 레퍼런스다.
실제 원천 문서는 이 스킬이 아니라 repo의 **`docs/reference/`** 에 있다 — 이 SKILL.md는 **어떤 상황에 어느 문서를 읽을지 라우팅**만 한다.

작업 중 특정 기법·사례가 필요하면 아래 표에서 맞는 문서를 골라 `Read`로 열어라. 문서 안 각 항목엔 카페 원문 URL이 있으니, 더 깊이 필요하면 원문을 다시 볼 수 있다.

## 라우팅 — 무엇이 필요할 때 어느 문서를 읽나

| 상황·키워드 | 읽을 문서 |
|---|---|
| **우리가 직접 발견·검증한 기법** (커뮤니티 자료 아닌 우리 것) | `docs/reference/our-findings.md` |
| **번역·조판 규약** (한글 출력 표기 규칙 — 부호 뒤 공백 제거 등) | `docs/reference/translation-conventions.md` |
| **어디부터 볼지 모름 / 특정 게임·플랫폼 자료 목록** | `docs/reference/index-by-platform.md` (720건 플랫폼별 인덱스) |
| **PS1 / 세가새턴** — 디버거로 폰트 찾기(NO$PSX·루아), 팔레트 추출, mkpsxiso, CD 섹터 구조, 1bpp→4bpp | `docs/reference/ps1-saturn.md` |
| **SFC / PC98** — ROM 영역 확장·포인터 재계산, 비트→폰트 출력, PC98 3bpp/1bpp 그래픽 | `docs/reference/sfc-pc98.md` |
| **PSP / GB·GBC·GBA·NDS** — 내장폰트 확장, prx 하드코딩, 기드라 분석, VRAM 타일, unpack/repack | `docs/reference/psp-and-handhelds.md` |
| **Windows/PC·유니티·엔진** — SDF 폰트 교체, 엔진별 한글화, 입문 워크플로, DeepL MT | `docs/reference/windows-pc-and-workflow.md` |
| **압축·인코딩** — LZ/LZSS 변종 해제, 압축·암호화 판별, SJIS↔JIS·UTF-8 변환, 정규표현 | `docs/reference/compression-and-encoding.md` |
| **한글 폰트·인코딩표** — 갈무리 등 픽셀폰트 자원, 7비트 완성형 음절표, 폰트 제작 스크립트 | `docs/reference/fonts-korean.md` |
| **AI 활용 한글화** — 번역 프롬프트, VLM OCR 폰트테이블, AI로 LZSS 재압축, Claude+emucap 실전팁, 파라트랜즈+Gemini | `docs/reference/ai-workflow.md` |
| **막힌 문제의 실전 해법** — 페르소나·SFC 드퀘·PS1 압축·유니티 대사찾기 등 질의응답에서 건진 해법 | `docs/reference/qa-nuggets.md` |
| **SFC·GB 단계별 실전 walkthrough** — 패트레이버·세일러문·아크맨3·잔쿠로무쌍검 작업일지(분석→폰트/대사 확장→VRAM→압축) | `docs/reference/worklog-sfc-gb.md` |
| **PS/SS/PSP/PCE 작업후기** — 자막 시스템 구현(령 제로3·악마성), 내장폰트 우회(PSP), 폰트 위치 찾기, 대사 씹힘 해결 | `docs/reference/worklog-consoles.md` |
| **기초 개념** — 포인터·HEX·고유코드 등 (색인 형태) | `docs/reference/basics-and-hubs.md` |
| **카페 밖 자료처** — 다른 강좌 블로그·커뮤니티(DCinside·Arca)·국제 레퍼런스(psx-spx 등)·폰트·도구 | `docs/reference/external-sites.md` |
| **블로그 강좌** — snowyegret(한글화·툴), sunlightface(PS1), mushsooni·ohgoru | `docs/reference/blog-snowyegret.md` · `blog-sunlightface.md` · `blog-etc.md` |

## 카페에서 자료를 더 가져와야 할 때

새 게시판·글을 추가로 수집하려면 로그인된 크롬에 CDP로 붙어 카페 내부 JSON API를 호출한다.
접속 방법(Chrome 136+ 원격디버깅 함정, `--remote-allow-origins`, API 엔드포인트, menuid)은 **`docs/reference/README.md`** 에 정리돼 있다.
빠른 시작: 유저에게 `~/.cache/chrome-cdp-profile` 프로필로 크롬을 9222에 띄우고 네이버 로그인을 요청 → 그다음 boardlist/article API로 수집.

## 우리 발견을 축적하라

작업 중 **새로 발견·검증한 해결책이 이 문서들에 없으면 추가**한다(프로젝트 방침).
관련 플랫폼 문서에 주제가 있으면 거기 보강, 없으면 `docs/reference/our-findings.md`에 기록.
확정된 것만, 추정은 "가설"로. 커뮤니티 자료 + 우리 실전 발견을 한 곳에 쌓는 게 이 아카이브의 목적이다.

## create-kr-patch 스킬과의 관계

`create-kr-patch`(외부 플러그인)는 한글화 **전 과정을 수행**하는 스킬이다. 이 `hansicgu-reference`는 그 작업 중
**커뮤니티에서 검증된 구체 기법·사례를 조회**하는 보완재다. 한글화 작업을 진행하다 특정 플랫폼의 실전 기법이나
남들이 어떻게 풀었는지가 필요하면 이 스킬의 문서를 참고하라. (이 스킬은 우리 repo 전용이며 create-kr-patch 플러그인은 건드리지 않는다.)
