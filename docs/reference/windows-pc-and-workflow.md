# Windows/PC게임 · 워크플로 · 기계번역

Windows/PC게임(주로 Steam 배포 상용 엔진 게임)과 범용 한글화 워크플로, 기계번역 파이프라인을 정리한 레퍼런스. 이 프로젝트의 현행 타깃은 PS1/레트로 콘솔이지만 Windows/PC는 로드맵 타깃이므로, 엔진별 추출·폰트 교체 흐름과 번역·검수·자동화 기법의 알짜만 보존한다. 각 원문의 본문·이미지 캡션·링크에서 확인되는 사실만 기록하며, 이미지로만 설명된 부분은 텍스트로 확인되는 범위까지만 옮긴다.

> 출처: hansicgu 카페

---

## 개념·워크플로

### 입문을 위한 언어 출력 원리 에세이 (#31716)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/31716
- 도구: 개념 에세이(특정 도구 없음). 언급 도구: CrystalTile2(커스텀 테이블 로드·문자 편집), 디버거(텍스트 로드 순간 추적).

인코딩의 역사적 배경으로 왜 한글화가 역공학이 되는지를 설명한다.

- 인코딩 계보: 영어권은 7비트(0~127) ANSI 기반 128자. 아시아권은 자국 문자용 인코딩을 표준화 없이 제각각 개발. 한국은 완성형(EUC-KR, 약 2,350자; 확장 CP949)과 조합형(초·중·종성 코드 조합)으로 갈림. 일본은 Shift_JIS(로마자 1바이트, 일본어 2바이트, 약 6,000자 한자). Shift_JIS는 가변 길이라 문자 시작·끝 구분이 어려워 텍스트 추출 시 중간에 끊기거나 깨짐. 회사·비주얼노벨 제작사마다 독자 확장 문자 테이블을 쓰는 경우도 많음.
- 한글 출력 트릭 — 덮어씌우기: 일본어 게임에 한글 넣을 공간이 없으므로, Shift_JIS에서 잘 안 쓰이는 한자 영역에 한글 이미지를 덮어씌운다. 대표 시작점이 亜(아). 게임은 여전히 '亜'를 출력하지만 화면엔 '가'로 보이게 하고, `Shift_JIS 코드값 = 한글` 1:1 매핑을 수동 작성 → 이를 커스텀 테이블이라 부르며 CrystalTile2 등에 로드해 편집.
- 함정 2가지: (1) 게임이 6천 한자를 전부 넣은 게 아니라 필요한 한자만 선별 수록한 경우, 덮어쓸 코드 자체가 없어 빈칸·기호가 뜸. (2) 폰트 테이블 순서 문제 — Shift_JIS 표준 순서를 안 따르고 자체 순서로 글리프를 정렬한 게임은 코드값↔폰트 이미지 매핑, 매핑 테이블 위치, 압축 여부까지 역분석 필요.
- 대사 삽입 난관: 일본어는 한자로 정보 밀도가 높아 짧고, 한국어는 길어짐(예: 理解 → 이해하다). 그대로 넣으면 잘리거나 튕김. 해결: 대사 길이 제어코드를 찾고(바이너리 패턴 추측 + 디버거 추적 병행), 번역문을 새 위치에 넣은 뒤 포인터를 새 주소로 수정. 포인터는 대개 리틀엔디안이라 바이트 플립 필요(0030A5 → A5 30 00).
- 한국식 혼합 기법: 중국식 폰트 영역 확장(폰트 재배치·새 영역 삽입 + 매핑 테이블 재구성)과 미국·서양식 대사 영역 확장(텍스트를 외부 파일로 분리·포인터 전환)을 상황에 따라 병행. 그래서 분석이 막히면 중국·일본·미국·러시아 등 해외 유저 번역 자료를 적극 참고하는 문화.
- 저자 방침: "시작을 어떻게 하든 한글 출력부터 확인하고, 그 뒤에 상세 분석을 진행한다."

### PC 게임 한글화 입문자를 위한 가이드 (#31893)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/31893 (원본 갱신본: https://gall.dcinside.com/indiegame/248798)
- 도구: SteamDB, Google AI Studio(Gemini 2.5 Pro), 눈누(noonnu.cc), Notepad++, WinMerge, Everything, HxD, FontForge, 엔진별 툴(UABEA, XUnity.AutoTranslator, FModel/UnrealLocres/Repak, UndertaleModTool, GodotPCKExplorer 등).

PC 게임 한글화 종합 가이드. 핵심 소제목·체크리스트 위주로 압축.

- 한글패치 ≠ 번역: 표준 5단계 — ① 게임엔진 확인·분석 ② Unpack/Export ③ 번역·폰트 교체 ④ Import/Repack ⑤ 실행 테스트·배포. 입문자 최다 실수는 한글 출력이 기술적으로 가능한지 확인하기 전에 전부 번역부터 하는 것. 번역은 언제든 가능하나 성패는 기술 파트가 가른다 → 반드시 한글 출력 가능 여부부터 검증.
- 게임엔진 확인: SteamDB 검색 → Technologies 항목이 엔진. 없으면 스팀 토론장·구글링. SteamDB instantsearch로 엔진·언어·장르 필터링해 한패할 게임 찾기도 가능.
- 개발사 사전허락: 법적 시비에서 자유로워짐. 연락처는 SteamDB Metadata의 Social Media가 가장 쉬움. 공식 메일보다 Discord DM 응답률이 높음. 문의에 포함할 3요소 — ① 한패 이유(게임 고유 특징 구체 칭찬) ② '팬 번역'(비상업)임을 명시 ③ 공식 품질 보증을 요구하는 게 아니라 존중 차원의 허락임을 언급. 한글로 쓰고 AI로 번역·다듬어 발송. 묵묵부답은 각자 판단.
- Google AI Studio: 학습 데이터 수집 목적으로 최신 모델을 거의 무제한 무료 제공. 번역엔 Gemini 2.5 Pro(한국어 번역 원탑 평가). 설정 — Model을 2.5 Pro로, Temperature 0.7(직역=낮춤/의역=높임), Tools(Code execution·Grounding with Google Search·URL context 필요 시), Safety settings 전부 off, System Instructions에 상시 지시, Ctrl+Enter로 실행. 제한 — 무료는 대화가 학습에 사용(기밀은 유료), 모델별 분당/일당 한도, 대화 길어질수록 품질·속도 저하(주제 바뀌면 새 대화), 빠른 응답은 2.5 Flash/Flash-Lite. 간단한 스크립트(파편화된 원문 → csv/xlsx 병합, 역변환, 사용 글자 추출 등)는 바이브 코딩으로 구현 가능하나 검증 필수. 리버싱을 AI만으로 무지성 시도는 금물.
- 번역 '조금 더' 잘하기: (1) 초벌은 AI(MTPE: AI 번역 후 원문 대조 검수가 손번역보다 효율·품질 우위인 경우 많음). (2) 번역이 아니라 현지화 — 관용구·말장난·고유명사를 한국어에 맞게, 높임말·호칭 등 관계 반영. 단 번역자 자아·유행어·과잉 초월번역 금지("한패는 창작 활동이 아니다"). (3) 검수는 아무리 해도 부족 — 특히 플레이 검수(LQA)로 대사 귀속·표정·말투 불일치 잡기. 검수용 프롬프트 추천(예: '빨간펜 프로토콜' https://rentry.co/2uob6a6m).
- 저작권 문제 없는 폰트: 상업용 무료 폰트만. 눈누(noonnu.cc)가 탑이나 라이선스 요약표에 오류 있으니 원출처 확인. 임베딩 가능 여부, 폰트 파일이 게임 폴더에 그대로 들어가면 재배포(OFL)까지 허용 폰트 권장. 눈누 미수록 사이트: 온글잎·ClipartKorea·문자동맹·포티·HWH. 픽셀 게임은 Raster화 켜고 Anti-aliasing 꺼야 외곽이 픽셀로 뚜렷. glyph_px(실제 보이는 글자 세로 픽셀) 기준으로 원문과 비교해 고르고 px 값으로 게임 데이터 폰트 크기 수정. 무난한 선택: 갈무리, Neo둥근모.
- 필수 범용 프로그램: Notepad++(인코딩·줄바꿈 확인, 자동 백업, 메모장 대체 필수), WinMerge(폴더·파일 diff, 변환 전후 형식 동일성 검증·번역 일괄 확인; 유사 DoubleKiller), Everything 1.5 알파(초고속 파일·내용 검색 — unpack 후 대사 파일 찾기에 유용), HxD(바이너리를 16진수로 열람·편집; 헤더·오프셋 작업).
- 답변 잘 달리는 질문법: ① 게임 이름·엔진 ② 작업 툴 ③ 작업 내용·방식(수정한 폰트·대사 포함) ④ 증상(이미지) ⑤ 샘플 파일. 커뮤니티 — 한식구(최대 규모, 콘솔 자료 다수/PC 최신 자료는 약함), 손번역 채널(비주얼노벨·에로게, 쯔꾸르·렌파이·울프툴), 인디게임 갤러리.
- 엔진별 강의자료(요약):
  - 유니티: 정석은 UABEA로 대사·폰트·이미지 교체(snowyegret.tistory.com에 자료 다수). 대안은 XUnity.AutoTranslator(게임 실행 중 후킹 자동번역 — 폰트 출력 간편하나 실제 출력된 텍스트만 번역 가능; FontOverride만 써서 폰트 패치 전용 활용도 가능). 자동번역 시 구글·파파고 대신 Gemini API(2.5 Flash-Lite 무료 분당 15/일 1000회).
  - 언리얼: FModel로 unpack → UE4localizationsTool 또는 UnrealLocres로 locres export/import → Repak 또는 Unrealpak으로 repack. locres key가 무작위 해시면 UE4TextExtractor로 uasset 경로를 뽑아 key로 활용.
  - 게임메이커: UndertaleModTool로 폰트 텍스처(.png)·좌표(.csv) export → 게임메이커 스튜디오로 한글 폰트 텍스처·좌표(.yy) 제작 → 파이썬으로 .yy→.csv 변환 → 재import. 대사는 Strings export/import. YYC 컴파일 게임은 어려움.
  - 고도(Godot): GodotPCKExplorer로 pck unpack/repack, Godot RE Tools로 gdc↔gd decompile/compile. 대사가 소스코드에 섞여 Everything 검색 활용. .translation 컴파일 게임은 snowyegret23/UntilThen_translationfile 참고.
  - 클릭팀퓨전: 손번역 채널의 ToolForClickteamFusion 전용툴.
- 기타 미세팁: (1) 대사는 txt/ini/tscn을 csv(권장) 또는 xlsx로 변환 후 구글 스프레드시트에서 번역, 변환 전후 WinMerge 검증 필수(정석은 Trados 등 CAT). (2) 네이버 사전 — 뜻풀이 검색·유의어로 자연스러운 어휘. (3) FontForge로 원문 폰트 디자인(영문·숫자·기호)에 한글 글리프만 병합, 크기·줄간격·위치 수정도 가능. (4) 완성형 한글 목록: taggon gist(2350자+자모+영문+기호, 최다 사용), 한식구 글자집합(2350/2780/4358/11172자), Snowyegret 목록(rentry CharList_3864, 3864자+@). 극한 최적화는 번역에 실제 쓰인 글자만 추출.
- 맺음말: 한패는 직업·봉사가 아닌 취미. 게이머에게 시달릴 이유도 신격화될 이유도 없다.

---

## 유니티/엔진

### 유니티 게임의 한글화 강좌 (#22398)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/22398
- 도구: UnityEX, UABE, AssetStudio, HxD/FlexHEX, 유니티 에디터 2017(TextMeshPro Font Asset Creator), UnityText, CrystalTile2(크탈2), Photoshop/paint.net(dds 플러그인), WTV. 예시 게임은 SpookyUnity.

폰트·대사·그래픽 3가지를 수정한다는 전체 흐름. 대용량 문서라 핵심 단계 위주로 압축.

- TTF 폰트 교체: UnityEX로 sharedassets0.assets 열기 → Lunchds.ttf 추출 확인 → 한글 TTF(예: 둥근모꼴.ttf)를 같은 이름으로 바꿔 폴더에 넣고 Import all files. TTF만 쓰는 게임은 이후 대사만 수정하면 됨.
- SDF 폰트 교체(핵심): SDF 폰트는 이미지(글리프 아틀라스) + 좌표파일(각 글리프 위치)로 구성 → 이미지만 한글로 덮으면 좌표 불일치로 엉뚱한 글자 출력. 절차:
  1. StreamingAssets의 mansionrooms를 UnityEX(파일형식 ALL)로 열어 `Lunchds sdf.tex`를 export with convert(dds)로 추출, WTV로 폰트 이미지 확인. UnityEX가 안 되면 uabe.
  2. 좌표파일 찾기: UnityEX 하단 Search Text로 `sdf` 검색(대사 찾기에도 응용). 좌표파일 앞부분에 폰트 이름 기록됨.
  3. HxD로 한 줄 36바이트로 조정해 열람. 각 글리프 좌표는 36바이트 단위 — 앞 4바이트(예: 2000)가 유니코드 코드포인트(바이트플립: 20 00→00 20=U+0020 공백, 21=!, 41=A…), 이후 X·Y·너비·높이, 끝 80 3F는 아틀라스 장수·ARGB채널(전부 동일해 무시, 종료 지표로 활용). 4100↔4200 코드를 맞바꿔 넣으면 A자리에 B가 나오는 것으로 구조 검증 가능.
  4. 한글 좌표파일 제작: 유니티 2017(최신은 좌표 형식 다름) 설치 → 첨부 Assets 덮어쓰기 → Window–TextMeshPro–Font Asset Creator → Font Source에 영문명 TTF 지정(한글명 불가) → 폰트 크기·아틀라스 크기 지정, Character Set을 Custom Characters로 한글 2350자 입력, Font Padding으로 안티에일리어싱(픽셀 느낌 원하면 0) → Generate Font Atlas → Save. UI–TextMesh Pro–Text 생성 후 Font Asset 지정 → File–Build Settings로 Build → 생성된 sharedassets0에서 이미지·좌표파일 추출.
  5. 좌표파일 수정치: 이미지 가로·세로 크기가 파일에 기록됨(원본 512px → `00000044` 두 번, 한글 아틀라스 4096px → `00008045`로 교체)와 폰트 개수(2바이트, 예 원본 5e00=94자 → 유니티 제작 한글 좌표는 9b09=2459자로 교체). 원본 좌표를 지우면 오류 나는 게임이 있음 → 그 경우 영문 좌표 위에 한글 좌표를 얹고(위쪽이 먼저 인식됨) 개수는 2459+94=2553(09F9→바이트플립 F909)로 기재. 끝의 80 3F가 없는 게임은 한 줄 32바이트로 조정하고, FlexHEX 리플레이스로 40 00 00 80 3F → 40 식으로 끝자리만 제거.
- 대사 수정: (2019 수정) 정석은 UABE가 더 편함. 대사가 txt면 Notepad++로 수정(메모장 금지 — 줄바꿈 깨짐). 분산 저장 시 UnityText 사용 — 좌측 하단 C에서 Hangul Syllables 선택(안 하면 빈칸 출력), O에서 파일·대사 최대 길이 조정·Save=Yes·Min String Length=1, 파일 로드 후 수정→pack. 여러 줄 대사는 csv로 export해 수정 후 csv 버튼으로 재로드. 한 글자 대사가 인식 안 되면 CrystalTile2로 열어 영어로 바꿔주고 재로드. 제어코드는 건드리면 오류 나므로 대사와 구분.
- 아카이브 개념: 한 파일에 여러 분류(아카이브)가 묶여 있어 UnityEX는 한 번에 한 아카이브만 추출. 대사 위치를 못 찾으면 AssetStudio의 File–extract file로 전체 아카이브 추출 → Notepad++로 대사 있는 아카이브(예 BuildPlayer-Credits) 검색 → 해당 아카이브를 UnityEX로 열어 수정. 한글 안 나오면 그 아카이브 폰트 미교체 가능성.
- 그래픽: AssetStudio로 sharedassets1.assets 탐색 → tex를 dds로 저장 → Photoshop(dds 플러그인, 검은 화면이면 알파1 채널 눈 켜기) 또는 paint.net에서 png 32비트로 수정 → dds로 저장·삽입.

### 유니티 에디터 없이 SDF 폰트 교체하는 법 (#32224)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/32224
- 도구: Unity Font Replacer(snowyegret23, CLI; unity_font_replacer_ko.exe·export_fonts_ko.exe·make_sdf.exe). 대안 C# 버전 Unity_Font_Replacer_AT. 보조: UABEA, AssetStudio, ttfinfo. 예시 게임 Chill with You: Lo-Fi Story, v1.2.3 기준 Windows.

유니티 에디터·허브 설치 없이 SDF 폰트를 만들고 교체하는 CLI 툴 사용법. #22398의 수작업을 대체. 7단계.

- 저장소: https://github.com/snowyegret23/Unity_Font_Replacer (C# 신버전: https://github.com/snowyegret23/Unity_Font_Replacer_AT — 더 빠르나 UnityCN 중국 게임은 기존 툴만 가능).
- 주의: 반드시 폰트 미가공 원본 상태에서 진행. 스팀은 '게임 파일 무결성 검사'로 수정 파일만 원복 가능 — 오류 재작업 시마다 무결성 검사.
- 0. 사전 준비: 릴리즈 압축 해제. 커스텀 폰트면 1단계부터, 내장 폰트(나눔고딕·물마루) 일괄 교체면 6단계부터.
- 1. 폰트 정보 추출: `unity_font_replacer_ko.exe` 실행 → 게임 설치 경로 붙여넣기 → 스캔 워커 수 5(클수록 빠르나 메모리↑) → 1 입력 Enter → 에셋 전체 스캔해 폰트 목록을 json으로 추출. Il2Cpp 게임도 별도 사전작업 없이 자동 덤프(mono=`_data\Managed`에 dll, il2cpp=`_data\il2cpp_data`로 구분).
- 2. SDF 폰트 추출: `export_fonts_ko.exe` → 게임 경로 붙여넣기 → 자동 추출. 오류 시 UABEA/AssetStudio 사용.
- 3. 폰트 모양 확인: 추출된 png로 대략 확인(SDF는 외곽 음영으로 불명확) → Material 없는 json의 `m_FamilyName`(실제 폰트명)·`m_StyleName`(굵기) 확인 후 구글링으로 원본 모양 파악.
- 4. SDF 폰트 제작: 원본과 비슷한 ttf/otf를 make_sdf.exe 폴더에 넣고 cmd에서 `make_sdf.exe --ttf "Galmuri9.ttf"`. 픽셀 폰트는 `--rendermode raster` 추가(안티앨리어싱 방지). 글자 목록 기본은 `CharList_3911.txt`, 변경은 `--charset "목록.txt"`. 생성 후 원본·제작 폰트를 KR_ASSETS로 이동.
- 5. 폰트 정보 매칭: 1단계 json에서 교체 대상의 `Replace_to`에 폰트명 입력(SDF는 Atlas/Material 제외한 파일명, 예 `Galmuri9 Raster`). 공란이면 원본 유지. Raster로 만든 픽셀 폰트(내장 Mulmaru SDF 포함)는 `force_raster`를 `True`로(안 하면 회색 음영).
- 6. 폰트 교체(명령줄 권장):
  - 일괄: `unity_font_replacer_ko.exe --gamepath "<경로>" --max-workers 5 --nanumgothic` 또는 `--mulmaru --force-raster`.
  - 커스텀: `--list "<게임>.json"`.
  - 대화형은 실행 후 경로·워커 입력 → 3/4로 나눔고딕·물마루 일괄, 2로 커스텀(json 파일명 입력).
  - 옵션: `--use-game-material`(외곽선 등 폰트 효과 오류 시, 원본 Material값 유지), `--use-game-line-metrics`(글자 크기·줄간격 오류 시, 원본 값 사용). 그래도 안 되면 UABEA로 MonoBehaviour의 `m_AscentLine` 수동 조절(snowyegret.tistory.com/37).
- 7. 기타 트러블슈팅:
  - 크래시·정지: assetbundle CRC 체크 문제 가능성 → catalog.json CRC 우회(snowyegret.tistory.com/64, /86).
  - □·⛝ 출력: ① 원본 ttf/otf가 해당 글자 지원하는지 ttfinfo(https://snowyegret23.github.io/ttfinfo/)로 확인 ② 지원하면 CharList_3911.txt에 글자 추가해 재제작(한식구 28508 글자집합 활용) ③ 원본·목록 둘 다 있으면 Dynamic 폰트 폴백 오류 → UABEA로 MonoBehaviour의 `m_AtlasPopulationMode = 1`을 `0`으로 수정.

### Adobe Air 엔진 게임의 한글화 (#32304)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/32304
- 도구: JPEXS Decompiler(https://github.com/jindrapetrik/jpexs-decompiler), Java 런타임 8.0+, Notepad++. Flash/ActionScript/SWF 기반 Adobe Air 게임 대상.

Flash 리마스터에 흔한 Adobe Air 엔진 게임(HTML/JS/Flash/ActionScript)의 한글화.

- 작업 대상 파일: 게임 폴더의 `Data/assets`에서 용량 큰 `Main.assets`(주 작업 대상)와 `Player.swf`(구동·화면 출력 역할). Main.assets의 확장자를 `.swf`로 바꿔 JPEXS로 열고, 작업 후 다시 `.assets`로 되돌려 덮어씀.
- 살펴볼 트리: fonts(한글 미지원 → 한글 TTF 삽입), texts(태그 포함 번역 대상 영문), shapes(영어 이미지), scripts(일부 시스템 용어 텍스트 — Notepad++ 폴더 검색 또는 디컴파일러에서 즉시 수정).
- 폰트 삽입: 폰트 하나 선택 → 우측 Embed 버튼 → 한글 TTF 로드 → Basic Latin·Basic Hangul 체크, Set ascent/descent and leading 체크(Hangul All은 용량 급증, Basic Hangul이면 대개 충분) → 갱신 팝업 전부 긍정. 쓰인 폰트(예시 13개) 모두 동일 처리.
- 텍스트·이미지: texts는 미리보기에서 즉시 수정 가능. 전체 추출 시 texts 폴더 우클릭 → 내보내기 → Formatted text 선택(태그 보존으로 재임포트 편함). shapes는 PNG로 추출. 추출물은 옮기지 말고 생성한 폴더 그대로 두어야 재인식됨.
- 재삽입: 트리에서 texts/shapes 선택 → 상단 import → import shapes / import text. 완료 후 반드시 저장·종료 → main.swf를 main.assets로 확장자 변경 → 게임 폴더에 덮어쓰기.

---

## 도구·자동화

### Hello Win32API! 비주얼스튜디오로 윈도우 애플리케이션 만들기 (#32359)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/32359
- 도구: Visual Studio Community(무료), Win32API/C. 취미·입문용(상업 개발은 C# WinForms/WinUI, 파이썬 tkinter 등이 일반적이라고 저자 부연). 한글화 전용 팁은 아니지만 배포 가능한 윈도우 도구를 직접 만드는 최소 절차.

배포 가능한 Win32 GUI 실행파일을 만드는 최소 워크플로.

- 설치: VS Community 다운로드 → 'C++을 사용한 데스크톱 개발' 워크로드 체크 → 설치 후 재부팅 필수(컴파일러 정상 작동 조건).
- 프로젝트: 새 프로젝트 → 빈 프로젝트 → 솔루션 탐색기의 '소스 파일'에 우클릭 새 항목 추가(프로젝트에 포함돼야 컴파일 반영). Win32API는 C 기반이라 .c/.cpp 무관.
- 최소 코드: `#include <Windows.h>` + `WinMain`에서 `MessageBox(NULL, TEXT("..."), TEXT("..."), MB_OK)` 반환 0.
- 빌드가 실패하는 3가지 설정(프로젝트 속성에서 교정):
  1. 서브시스템: 빈 프로젝트는 콘솔로 잡힘 → 링커–시스템–하위 시스템을 '창'으로 변경.
  2. 문자 인코딩: 빌드 출력에 '표시할 수 없는 문자' 경고 → C/C++–명령줄–추가 옵션에 `/utf-8` 입력(C/C++ 항목이 안 보이면 설치·재부팅 문제).
  3. 배포 호환: C/C++–코드 생성–런타임 라이브러리를 '다중 스레드 DLL(/MDd 등)'에서 '다중 스레드(/MT)'로 변경(MSVCR***.dll 없음 오류 방지).
- 릴리즈: 빌드–구성 관리자에서 Debug→Release. Release는 별도 속성 세트라 /utf-8·런타임 라이브러리 등을 다시 설정해야 함(구성 바뀌면 초기화됨). F7=솔루션 빌드, F5=빌드+디버그 실행. 산출 exe는 다른 윈도우 PC에 옮겨 실행 가능(단 32/64비트 구분, Windows for ARM은 미보장). 파이썬 대안 PyInstaller는 제약으로 대상 PC에 동일 파이썬 환경이 필요할 때가 있음.

### 파이썬을 활용한 DeepL API + 용어집 기계번역 (#30523)

- 원문: https://cafe.naver.com/f-e/cafes/16259867/articles/30523
- 도구: Python, DeepL API(무료 api-free.deepl.com 포함, 용어집 지원), Google Sheets API(google-api-python-client), pandas, ParaTranz(csv 원문 소스). 요구 라이브러리: `pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client requests`.

용어집(glossary)을 적용해 csv 단위로 자동 기계번역하는 파이프라인. 3단계.

- 1. 구글 스프레드시트에 용어집 작성: DeepL 웹페이지 용어집과 API 용어집은 별개라 수동 작성 필요. 시트 URL의 SPREADSHEET_ID와 RANGE_NAME(예 `시트1!A2:B`)을 기억.
- 2. 시트 → DeepL 용어집 업로드: `POST https://api-free.deepl.com/v2/glossaries`에 `{name, source_lang:"EN", target_lang:"KO", entries:<TSV>, entries_format:"tsv"}`, 헤더 `Authorization: DeepL-Auth-Key <키>`. 시트 데이터는 `sheets.values().get(...)`으로 읽고, 소스 용어 기준 중복 제거(`remove_duplicates`) 후 `"\n".join("\t".join(row) ...)`로 TSV화. OAuth는 `credentials.json`→`token.json` 캐시. 응답의 `glossary_id`를 챙길 것.
- 3. 용어집으로 csv 번역: pandas로 csv 로드 → 지정 컬럼(예 `Content`)의 각 행을 `POST https://api-free.deepl.com/v2/translate`에 `{text, source_lang:"EN", target_lang:"KO", auth_key, glossary_id}`로 전송 → `translations[0].text`를 `<컬럼>_translated`로 추가 → `to_csv`로 저장. 원문 csv는 ParaTranz에서 내려받는 방식.
- 효과: 원래도 매끄럽게 번역되지만 고유명사·음차 통일에 유용(예 "부드러운 타이어→소프트 타이어", "선수→드라이버"). 검수 보조용.
- 과금: 무료·유료 모두 글자 수 차감. 무료는 소진 시 익월까지 대기, 유료는 100만 자당 25달러.
