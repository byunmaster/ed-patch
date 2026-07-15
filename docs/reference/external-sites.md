# 외부 자료처 — 한글화·롬해킹 강좌/커뮤니티/도구

한식구 카페 밖에서 레트로게임 한글화에 참고할 만한 사이트 모음.
**출처 신호**: "인용 N회"는 우리가 수집한 카페 본문(공부방&도구·질의응답·작업/후기)에서 해당 도메인이 링크된 횟수 — 커뮤니티가 실제로 얼마나 참고하는지의 지표다.

## 한국어 강좌 블로그 (강좌 밀도 높음)

| 사이트 | 성격 | 신호 | 정리본 |
|---|---|---|---|
| [snowyegret.tistory.com](https://snowyegret.tistory.com) · 툴: [github.com/snowyegret23](https://github.com/snowyegret23) | 한글화·롬해킹 강좌 + 툴 제작(Unity Font Replacer 저자). 유니티·언리얼·게임메이커·기드라·폰트 (블로그 github.io는 현재 404) | **인용 49회** | `blog-snowyegret.md` |
| [sunlightface.github.io](https://sunlightface.github.io) | **PS1 전용** 강좌(일광면) — 루아로 폰트/이미지 찾기, no$psx 자막, Psy-Q ANM | 인용 4회 | `blog-sunlightface.md` |
| [mushsooni.github.io](https://mushsooni.github.io) | **물마루(Mulmaru) 도트폰트** 배포(강좌 아님) — 히라가나·가타카나·한자 포함, OFL. 일→한 임베드에 유용 | 인용 4회 | `blog-etc.md`·`fonts-korean.md` |
| [ohgoru.tistory.com](https://ohgoru.tistory.com) | **Godot 엔진 PC 한글화** 연재(.pck 분해·gdc 디컴파일·stex 왕복·XDelta 배포) | 인용 3회 | `blog-etc.md` |

## 한국어 커뮤니티 (게시판형 — 카페처럼 browse-on-demand)

- **[DCinside 레트로게임기 마이너 갤러리](https://gall.dcinside.com/mgallery/board/lists/?id=retrogame)** — 한글패치 정리·분석·질답 활발 (인용 gall.dcinside 36회)
- **[DCinside 에뮬게임 마이너 갤러리](https://gall.dcinside.com/mgallery/board/lists/?id=emugame)** — 에뮬 구동·한글패치
- **[Arca.live](https://arca.live)** — 한글화 관련 채널들 (인용 16회)
- **한식구 카페** (본 아카이브의 원천) — [docs/reference/README.md](README.md) 참조

## 국제 레퍼런스·하드웨어 문서 (강좌보다 구조/스펙)

| 사이트 | 내용 |
|---|---|
| [psx-spx.consoledev.net](https://psx-spx.consoledev.net) | **PS1 하드웨어 정본 문서**(nocash) — GPU/VRAM/CD/DMA. PS1 작업 필수 ★ |
| [wiki.superfamicom.org](https://wiki.superfamicom.org) | SFC 개발 위키 (65816·PPU·메모리맵) |
| [romhacking.net](https://www.romhacking.net) | 고전 롬해킹 허브 — 문서·유틸리티·번역 자료 |
| [w.atwiki.jp](https://w.atwiki.jp) | 일본 롬해킹 위키(게임별 해석 자료, 예: DQ3 롬맵) |
| [charset.fandom.com](https://charset.fandom.com) | 문자 인코딩(SJIS·EUC 등) 위키 |
| [en.wikibooks.org](https://en.wikibooks.org) | 어셈블리/하드웨어 문서 |
| [vg-resource.com](https://www.vg-resource.com) | 스프라이트·텍스처·팔레트 리소스 |

## 한글 폰트 소스

- **[noonnu.cc](https://noonnu.cc)** (눈누) — 무료 한글 폰트 라이선스 정리
- **[ownglyph.com](https://www.ownglyph.com)** (온글잎) — 손글씨/커스텀 한글 폰트
- 픽셀폰트(갈무리 등)는 [fonts-korean.md](fonts-korean.md) 참조

## 필수 도구 (카페에서 빈번 인용)

| 도구 | 용도 | URL |
|---|---|---|
| HxD | 헥스 에디터 | [mh-nexus.de](https://mh-nexus.de/en/hxd/) |
| Everything | 파일명 즉시 검색 | [voidtools.com](https://www.voidtools.com) |
| Notepad++ | 텍스트·정규식 | [notepad-plus-plus.org](https://notepad-plus-plus.org) |
| WinMerge | 바이너리/텍스트 diff | [winmerge.org](https://winmerge.org) |
| BGB | GB/GBC 디버거 에뮬 | [bgb.bircd.org](https://bgb.bircd.org) |
| 크리스탈 타일2 | 타일/폰트/팔레트 뷰어 | (카페 배포) |

## 방법론·프로젝트 구조 (mcpads 생태계 — 우리 스택 연관)

우리가 쓰는 **emucap** 계열(mcpads)에서 나온, 한글패치 프로젝트의 **신뢰성·검증 규율** 자료. 기법이 아니라 "어떻게 구조화하고 검증하나"에 관한 것. 초기 단계(MIT, 소규모)라 확정 표준이 아닌 **참고 프레임**으로.

- **[github.com/mcpads/create-kr-patch-template](https://github.com/mcpads/create-kr-patch-template)** — 플랫폼 중립 한글패치 프로젝트 템플릿(Rust 참고구현 + Python PoC + `adapters/emucap/`).
  - **7가지 검증 경계**: ①원본을 크기+강한 해시로 식별 ②모든 이진 수정은 사전에 행위자·목적·기대값 선언 ③겹침쓰기·미등록 변경은 실패 처리 ④어셈블리 원천 없는 기계어 수정 금지 ⑤제품 빌드 입력은 PoC가 아닌 순수 원천만 ⑥같은 입력→동일 결과(재현성) ⑦무변경 통과 테스트로 바이트 보존 확인
  - **조사/PoC ↔ 제품빌드 분리**: 후보 스캐너 결과(PoC)를 복사하지 말고 순수 원천에서 재구현. 빌드 모드 `development`(미완료는 원문 유지) / `release-candidate`(완료 범위만) / `verify`(재생성 동일성 확인).
- **create-retro-game-kr-patch** — 위 템플릿이 강제하는 판단의 **방법론을 설명**하는 짝 프로젝트(카페 AI활용 #32761 펌글).
- **emucap** — 런타임 검증 어댑터(우리 emucap MCP와 동일 계열, 카페 #32885). 상세는 [ai-workflow.md](ai-workflow.md).

> 참고: 외부 플러그인 `create-kr-patch`(kr-patch 마켓플레이스, 타인 소유)와 이름이 비슷하나 별개 자원이며, 우리는 어느 쪽도 수정·푸시하지 않는다.

## AI 워크플로 (별도 정리)

Google AI Studio·Gemini·DeepL·LM Studio 등 AI 활용은 [ai-workflow.md](ai-workflow.md)에 정리.

---

> 커뮤니티(DCinside·Arca)는 게시판 구조상 자동 수집보다 필요할 때 직접 검색이 낫다. 블로그(snowyegret·sunlightface 등)는 강좌 밀도가 높아 별도 문서로 정리했다.
