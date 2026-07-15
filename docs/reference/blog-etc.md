# 기타 한글화 블로그 (mushsooni · ohgoru)

한국어 롬해킹·한글화 관련 개인 페이지 두 곳을 조사한 요약이다. **mushsooni.github.io** 는 블로그가 아니라 레트로 한글화용 도트 폰트(Mulmaru) 배포 랜딩 페이지 하나뿐이며, 재사용 가치가 높은 폰트 리소스라 항목으로 정리했다. **ohgoru.tistory.com** 는 Godot 엔진 게임 한글화 기법을 언패킹→디컴파일→편집→재인코딩 순으로 다룬 연재가 알짜다(콘솔 롬해킹이 아니라 PC/Godot 대상이라 이 프로젝트의 PS1 파이프라인과 직접 겹치진 않지만, 리소스 왕복 인코딩·바이너리 델타 배포 발상은 이식 가능).

> 출처: mushsooni.github.io / ohgoru.tistory.com

## mushsooni.github.io

사이트 전체가 Mulmaru 폰트 소개 페이지이며 별도 기술 블로그 글은 없다. 폰트 리소스 하나를 정리한다.

### Mulmaru — 레트로 한글화용 도트(픽셀) 폰트
- URL: https://mushsooni.github.io/ (저장소: https://github.com/mushsooni/mulmaru)
- 도트 게임 한글화를 위해 제작한 픽셀 폰트. 기존 한글 픽셀 폰트가 16px로 크거나 너무 얇다는 불만에서 출발해, 더 작고 굵으며 가독성 높은 형태를 목표로 함.
- **권장 표시 크기: 12px(9pt) 또는 그 배수**. Yoon px Arcade 한글 형태에서 영향, "10×6×4벌식" 조합형 템플릿 기반, 굵은 세로줄기·둥근 모서리의 산세리프.
- **글자 수 11,937자**: 한글 완성형 11,172 + ASCII 95 + Latin-1 Supplement 77 + 그리스 49 + 키릴 65 + 히라가나 88 + 가타카나 90 + CJK 한자 7 + 특수문자 243. (일본어 가나까지 포함해 일→한 이식 시 원문 대조에도 유용.)
- 배포 형식: TTF·OTF, 그리고 Pixel Font Maker용 편집 소스 `.pfp` 제공. 변형 2종 — **Mulmaru(가변폭)**, **MulmaruMono(고정폭)**. 고정폭 변형은 타일/모노스페이스 그리드에 글리프를 얹는 콘솔 폰트 임베딩에 그대로 쓰기 좋음.
- 라이선스: **SIL Open Font License 1.1(OFL)** — 상업·비상업 무료, 수정·임베딩·재배포 허용(폰트 단독 판매만 금지). 즉 롬에 글리프 임베드 후 패치 배포에 라이선스 제약 없음.

## ohgoru.tistory.com

Godot 엔진으로 만든 PC 게임의 한글화 기법 연재(가이드 1편 + 각 공정 4편)가 핵심. "국내에 이 엔진 게임 언패킹 정보조차 없어" 해외 포럼을 모아 정리했다고 밝힘. 이하 5개 기법 글 + 배포 방식이 드러난 릴리스 글 1개.

### Godot 엔진 게임 한글화 가이드(총론)
- URL: https://ohgoru.tistory.com/15
- 전체 공정 개괄: `*.pck` 리소스 컨테이너 분해 → `gdc→gd`(컴파일된 GDScript 디컴파일) → `stex→png`(텍스처 디코딩) → 텍스트/이미지 편집 → **다시 인코딩**해 원본에 적용. 각 단계는 아래 개별 글로 연결.

### Godot 리소스 파일(.pck) 분해하기
- URL: https://ohgoru.tistory.com/16
- 도구: **GodotPCKExplorer** (https://github.com/DmitriySalnikov/GodotPCKExplorer).
- 절차: (1) 실행파일 속성으로 엔진 식별 → (2) "Extract All"로 `.pck` 아카이브 압축 해제 → (3) 대사 파일 위치 파악(게임에 따라 JSON으로 저장되기도) → (4) 편집 후 "Pack or Embed Folder"로 재패킹.
- 한계: 컴파일된 GDScript(`.gdc`)와 압축 PNG(`.stex`)는 이 도구만으로는 확인/편집 불가 → 아래 별도 공정 필요.

### GDC → GD 변환(컴파일된 스크립트 디컴파일)
- URL: https://ohgoru.tistory.com/18
- 도구: **Godot RE Tools(gdsdecomp)** (https://github.com/bruvzg/gdsdecomp). 메뉴 GDScript > "Decompile .GDC/.GDE script files..." → Add files → **게임 엔진 릴리스에 맞는 Script bytecode version 선택** → 출력 폴더 지정 후 디컴파일.
- 핵심 주의: 바이트코드 버전이 게임의 Godot 버전과 일치해야 함(불일치 시 디컴파일 실패). gdsdecomp는 gd→gdc **재컴파일은 미지원** → 재컴파일은 Godot 에디터의 프로젝트 익스포트로 우회(아래 재인코딩 글 참조).

### STEX → PNG 변환(텍스처 디코딩)
- URL: https://ohgoru.tistory.com/22
- 도구: Python 스크립트 `godot-stex-to-png`. 파일을 인자로 넘기거나, 스크립트를 고쳐 디렉터리 일괄 처리.
- 맥락/주의: 리소스는 `.import` 디렉터리 안에 `.stex`로 압축 저장되며 일반 이미지 편집기로 열 수 없음 → PNG로 되돌려야 텍스트가 박힌 이미지 에셋을 수정 가능.

### 편집 리소스 재인코딩 후 원본 적용
- URL: https://ohgoru.tistory.com/23
- 문제: 디컴파일한 gd·디코딩한 png는 **원본에 그대로 못 넣는다**. 해결: 게임과 **정확히 같은 Godot 버전**을 설치 → 임시 프로젝트를 만들어 수정 리소스를 넣고 → 프로젝트 익스포트로 PCK 생성 → GodotPCKExplorer로 다시 풀어 "제대로 인코딩된" 파일을 꺼내 원본에 덮어씀.
- PNG는 임포트 설정에서 자동 해상도 압축을 꺼 화질 유지.
- 함정: (GD) 익스포트 시 딸려 나오는 `.remap` 파일은 원본에서 에러를 유발하니 삭제하고 `.gdc`만 적용. (PNG) 임포트가 만드는 `.import` 메타는 실제 이미지를 숨김 디렉터리의 `.stex`로 가리키므로, 그 `.stex`를 원본 이름으로 바꿔 덮어써야 함.

### The Case of the Golden Idol 한글 패치(릴리스 + 배포 기법)
- URL: https://ohgoru.tistory.com/19
- 대부분 패치 배포/설치 안내글이지만, 재사용할 만한 배포 기법 한 가지: Godot의 `game.pck`에 대해 **XDelta 바이너리 델타 패치**를 **DeltaPatcher**로 적용하는 방식. 원본 아카이브를 파일 교체 없이 델타로 수정하고, 세이브 데이터를 지워 한글판을 적용. (실제 번역 작업 자체는 서술 없음.) 원본 저작물을 재배포하지 않고 diff만 배포하는 접근이라 콘솔 롬 패치 배포 관행과 동일한 발상.

> 참고: 이 블로그에 있는 또 다른 릴리스 글 "Mind Scanners Korean Patch"(https://ohgoru.tistory.com/14)도 Godot 계열 유저 패치 릴리스로, 위 연재 기법을 적용한 결과물 안내이며 새로운 기법 서술은 없어 상세 생략.
