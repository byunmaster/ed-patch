# snowyegret 블로그 — 한글화·롬해킹 강좌

snowyegret(snowyegret23)는 유니티·언리얼·게임메이커 등 현대 PC 게임 한글패치와, IMGUI 기반 네이티브 게임의 코드케이브 폰트 패치까지 폭넓게 다루는 한국어 롬해킹·리버싱 블로거다. **Unity Font Replacer**, **Unity Asset Text Searcher** 등 재사용 가능한 자작 툴 제작자이며, 우리 카페 자료에서 가장 많이 인용된(49회) 소스다. 이 문서는 그의 블로그에서 기법성(폰트 교체·리버싱·툴 사용법) 글만 골라 재현 가능한 요점으로 정리한 레퍼런스다. 각 글은 현대 PC 엔진 대상이지만, 폰트 아틀라스 확장·코드케이브 삽입·XOR 복호·오프셋 테이블 분석 등 방법론은 레트로 콘솔 한글화에도 그대로 적용된다.

> 출처: snowyegret.tistory.com / snowyegret23.github.io

참고: `snowyegret23.github.io`는 접속 시 HTTP 404(현재 사이트 없음). 툴 문서는 아래 GitHub 저장소들이 정본이다. 카테고리 "한글화 분석 (작업X)"의 일부 글(/79 Harvest Moon, /62 AVGN II)은 보호글이라 열람 불가.

---

## 자작 툴

GitHub 프로필: https://github.com/snowyegret23 — 주요 저장소:
- **Unity_Font_Replacer** (Python) / **Unity_Font_Replacer_AT** (C#) — 유니티 폰트 교체
- **Unity_Asset_Text_Searcher** (Python) — 에셋 내 텍스트 검색
- **EditDllString** (C#) — mono DLL 내 문자열 수정
- **UnityPy** (Python, fork) — 유니티 에셋 추출/편집
- **Unity_Sprite_Fullrect_Replacer** (Python) — 스프라이트 에셋 교체
- **PS5_Unity_Texture_Tool** (Python) — PS5 유니티 게임 텍스처 조작
- **UnityInfoMCP** (C#) — MCP 기반 모딩/한글화용 런타임 인스펙션
- **Localize** (Python) — 한글화 프로젝트 툴/패치/기술 노트 모음
- **AddressablesTools**, **UniverseLib** (C#, fork) — 어드레서블/IL2CPP·Mono 플러그인용

### 유니티 폰트 교체 툴 (Unity Font Replacer)
- URL: https://snowyegret.tistory.com/110
- GitHub: https://github.com/snowyegret23/Unity_Font_Replacer (릴리스: /releases)
- 유니티 게임의 폰트를 한글 폰트로 교체. TTF와 TextMeshPro SDF 양쪽 지원. 여러 폰트를 자동 일괄 교체해 수작업 에셋 편집을 대체.
- 사용: 대화형 `unity_font_replacer.exe`, 또는 인자 방식 `--gamepath "D:\Games\Name" --mulmaru`. 옵션 `--parse`(폰트 목록을 JSON으로 생성), `--list <file>`(JSON 기반 선택 교체), `--sdfonly`/`--ttfonly`(폰트 타입 지정). 일괄 교체 프리셋은 물마루(픽셀)·나눔고딕(산세리프).
- 주의: 게임 파일을 수정하므로 백업 필수. 온라인 게임은 무결성 검사로 수정 에셋을 거부할 수 있음.

### 유니티 게임 대사 검색 툴 (Unity Asset Text Searcher)
- URL: https://snowyegret.tistory.com/87
- GitHub: https://github.com/snowyegret23/Unity_Asset_Text_Searcher (릴리스: /releases)
- 입력 문자열을 UTF-8로 인코딩해 유니티 게임 에셋 전반을 스캔, 일반 검색기가 못 여는 직렬화 에셋·압축 번들 내부 텍스트까지 찾는다. MonoBehaviour/Text/.dll 대상. .dll은 pythonnet + Mono.Cecil로 LDSTR 명령을 순회, .assets·assetbundle의 TextAsset/MonoBehaviour는 번들을 직접 열어 검사.
- 사용: 게임 `_Data` 디렉터리에 두고 대화형 또는 인자 실행 → 결과 .txt/.csv 저장. v2.0.1(2026.02.08)에서 폴더 탐색 개선·최신 UnityPy 문법 대응.

### 유니티 SDF폰트 이식 관련 파이썬 스크립트
- URL: https://snowyegret.tistory.com/95
- 새 폰트의 글리프 데이터를 원본 게임 폰트의 MonoBehaviour JSON에 병합해, 게임 내부 참조(GameObject/Script/Material ID, 원본 텍스처 경로)를 깨지 않고 폰트를 교체. 참조가 깨져 텍스트가 안 뜨는 문제를 해결.
- 사용: UABEA로 원본 게임 폰트와 새 커스텀 폰트를 각각 JSON으로 export → 스크립트 변수 `original_game_font`/`new_font`에 경로 지정 → 실행해 `new.json` 생성 → UABEA로 원본 폰트 MonoBehaviour에 import.

### XUnity.AutoTranslator 텍스쳐 이름 변경 프로그램
- URL: https://snowyegret.tistory.com/40 (기본 설명 /39)
- AssetStudio 등으로 추출한 이미지 파일명을 XUnity.AutoTranslator 덤프 포맷 `{원본명} [{hash1} - {hash2}].png`로 변환. 텍스처 번역 이미지를 AutoTranslator가 자동 인식하게 만듦.
- 사용: `input` 폴더에 원본명 이미지를 넣고 `hash.exe` 실행 → `output` 폴더에 리네임 결과.

---

## 유니티

### 한글화/에셋 수정에 사용되는 툴 (툴 목록)
- URL: https://snowyegret.tistory.com/24
- 유니티 한글화 상용 툴 큐레이션: **AssetStudio**(이미지·대사 추출, 타입·위치 표시), **UnityRipper**(유니티 프로젝트 형식으로 export), **UABE/UAAE/UABEA**(에셋 수정·import 핵심, 다양한 유니티 버전 지원), **UnityEX**(텍스처·MonoBehaviour export/import, 스크립트 일괄처리), **Parser_ULS**(배치설정으로 MonoBehaviour 대사 추출), **Parser_UMDcpp2txt**(IL2CPP 메타데이터 하드코딩 문자열 export/수정), **UnityText2**(MonoBehaviour 대사 검색·편집, CSV export), **dnSpyEx**(.NET DLL 디컴파일·수정, 특히 CSharp-Assembly.dll), **ILSpy+Reflexil**(DLL 열람·플러그인 편집), **HxD/010Editor/wxMEdit**(헥스 에디터), **Everything**(다중 인코딩·정규식 파일 검색).

### 유니티 게임 한글화 - SDF 폰트 교체
- URL: https://snowyegret.tistory.com/21 (변형: /30 AtlasPopulationMode=1인 경우)
- 도구: UABEA(에셋 편집), AssetStudio(폰트·에셋 식별), TextMeshPro Font Asset Creator(TTF→SDF 생성), VS Code/Notepad++(좌표 파일 수정).
- 절차: (1) 게임/DLL 속성으로 엔진 버전 확인 → (2) AssetStudio로 대상 폰트 찾기 → (3) 원본 폰트 MonoBehaviour에서 좌표 데이터 추출 → (4) Font Asset Creator로 한글 폰트 생성(포인트 크기·패딩·문자셋 지정) → (5) 텍스처·좌표 파일 export → (6) 좌표 파일의 에셋 ID를 원본 텍스처 경로에 맞게 수정 → (7) 번들에 import → (8) 실행 검증. **핵심: 유니티 버전을 정확히 일치**시켜야 TMP 데이터 구조(직렬화 변수)가 호환됨.

### 유니티 게임 한글화 - IL2CPP 게임에서 DLL 생성 (윈도우, 안드로이드)
- URL: https://snowyegret.tistory.com/33
- IL2CPP 게임은 Mono와 달리 DLL이 없어 MonoBehaviour 역직렬화가 불완전 → **Il2CppDumper**(https://github.com/Perfare/Il2CppDumper)로 DLL 생성.
- 윈도우: 실행폴더의 `GameAssembly.dll` + `{Game}_data\il2cpp_data\Metadata\global-metadata.dat`를 Il2CppDumper에 순서대로 지정 → 생성된 `DummyDll`을 `Managed`로 리네임해 `{Game}_data\`에 배치 → UABE/UAAE로 편집.
- 안드로이드: APK 추출 → `lib\arm64-v8a\libil2cpp.so` + `assets\bin\Data\Managed\Metadata\global-metadata.dat`로 동일 처리.

### 번역을 위한 유니티 Il2cpp 게임의 복호화/암호화
- URL: https://snowyegret.tistory.com/85
- 암호화된 에셋·메타데이터를 복호해 번역 후 동일 파라미터로 재암호화. 도구: MelonLoader, UnityExplorer, pycryptodome, Ghidra, dnSpyEx, Il2CppDumper.
- 절차: (1) Il2CppDumper로 DLL 추출 후 dnSpyEx로 password/salt 변수 위치 파악 → (2) MelonLoader+UnityExplorer로 런타임 C# 콘솔에서 실제 키 값 확인 → (3) il2cpp 헤더를 얹은 Ghidra로 암호 알고리즘 역공학(예시: AES-128 CBC, PBKDF2 1000회) → (4) pycryptodome로 키 유도·복호 스크립트 작성.

### global-metadata.dat이 없는 경우의 덤프법 (frida 이용)
- URL: https://snowyegret.tistory.com/90
- global-metadata.dat이 파일로 없을 때 실행파일의 리소스 섹션에서 Frida로 추출. kernel32 API `GetModuleHandleW`→`FindResourceW`→`LoadResource`/`LockResource`→`SizeofResource` 호출로 리소스(전형적으로 ID `0x65`, 타입 `0xA` — 게임마다 다름)를 찾아 `Memory.readByteArray()`로 읽고 파일로 저장.
- 실행: `frida -f ".\game.exe" -l script.js`. 리소스 ID/타입은 게임마다 다르니 먼저 식별 필요.

### UnityPy를 이용한 MonoBehaviour 특정 텍스트 필드 추출/삽입
- URL: https://snowyegret.tistory.com/89
- UnityPy로 MonoBehaviour의 지정 필드를 CSV로 export/import. 게임 아키텍처(Mono/IL2CPP)를 자동 감지해 적절한 메타데이터를 로드.
- 사용: 게임 루트에 두고 CLI로 모드(Export/Import), ClassName(기본 TextMeshProUGUI), FieldName(기본 m_text), CSV 지정. 옵션 `--forcereplace`(오브젝트 식별자 대신 텍스트 내용으로 매칭), `--filternumber`(순수 숫자 제외). 환경: Python 3.12.9 / UnityPy 1.21.1 / TypeTreeGeneratorAPI 0.0.5. 한계: UnityPy TypeTree 미완이라 일부 필드 누락 가능.

### 유니티 게임 한글화 시 한국어 조사 처리
- URL: https://snowyegret.tistory.com/94
- **csjosa** 라이브러리(GitHub: myevan/csjosa) 방식으로 조사 자동 처리. 원문에 "(은)는", "(을)를", "(이)가" 등 플레이스홀더를 넣고, 정규식으로 패턴을 잡아 앞 글자의 유니코드(0xAC00-0xD7A3) 종성 유무를 판정해 올바른 조사를 선택.
- 구현: dnSpyEx로 컴파일된 DLL을 편집해 `UnityEngine.UI.Text`(text setter·OnEnable)와 TextMeshPro(text setter·SetText)에 `Csjosa.Process()`를 후킹, 텍스트 대입 시 자동 처리.

### 유니티 게임 한글화 - assetbundle crc체크 우회
- URL: https://snowyegret.tistory.com/64
- StreamingAssets 번들 수정 시 카탈로그의 CRC 불일치로 로드 실패하는 문제 우회. 주 방법: nesrak1(UABEA 개발자)의 **AddressablesTools** — `catalog.json`을 exe와 같은 폴더에 두고 `Example.exe patchcrc catalog.json`(바이너리는 `catalog.bin`, 번들은 개조판+`catalog.bundle`) 실행 → 백업 `.old`와 패치본 생성.
- 폴백: 구버전은 `catalog.json`의 `"m_ExtraDataString": ""` 설정. `catalog.hash`가 있으면 수정 카탈로그의 MD5를 계산해 `.hash` 갱신. Mono 런타임은 dnSpy로 `Unity.ResourceManager.dll`의 CRC 파라미터를 `0U`로 변경, IL2CPP는 Ghidra/IDA로 역공학.

---

## 언리얼·게임메이커

### 언리얼 엔진 게임 한글화 (UnrealEngine 4 이상)
- URL: https://snowyegret.tistory.com/54 (작성중 문서)
- 절차: (1) pak를 체크 스크립트에 드래그해 엔진 버전 확인 후 해당 UE4 빌드(4.19.2~4.27.x) 설치 → (2) 버전별 스크립트로 pak 언팩(암호화 시 AES 키를 찾아 복호 스크립트에 투입) → (3) 헥스 에디터로 폰트 매직넘버 식별 후 원본과 파일명·확장자를 맞춰 폰트 교체 → (4) 텍스트는 `.locres`=UnrealLocres, `.uasset`=UAssetGUI로 수정 → (5) 텍스처는 UE4-DDS-Tools 또는 수동 헥스.

### UnrealEngine uasset 비트맵폰트 교체
- URL: https://snowyegret.tistory.com/109
- 모던 언리얼(IoStore)이 폰트를 pak가 아닌 utoc/ucas에 저장하는 문제를 다룸. 도구: FModel(추출), repak(재패킹), retoc(pak→IoStore 변환).
- 절차: (1) FModel로 pak 추출, 헥스에서 `PF_G8` 등 픽셀 포맷 마커로 비트맵 폰트 식별 → (2) 게임 루트 폴더명과 같은 이름의 UE 프로젝트 생성, 폴더 계층 재현(예: Content/DFT/SubtitleFont) → (3) 새 폰트 에셋 생성(Cache Type=Offline, ASCII+원하는 문자셋, Distance Field Alpha 활성), Platform>Windows>Cook Content로 쿠킹 → (4) repak로 pak 묶고 `retoc.exe to-zen --version <engine_version>`으로 utoc/ucas 변환.

### 게임메이커 게임 한글화 - 폰트 교체
- URL: https://snowyegret.tistory.com/65 (예시: Shovel Knight Pocket Dungeon)
- 도구: GameMaker Studio, UndertaleModTool(GUI 윈도우판 권장).
- 절차: (1) UndertaleModTool로 `data.win`을 열어 대상 폰트의 크기(예 10px)·스타일·문자셋·안티에일리어싱 확인 → (2) GameMaker에서 동일 사양의 새 폰트 생성, ASCII+한글 문자 범위 추가 → (3) 텍스처 재생성, `...\GameMakerProjects\{proj}\fonts\{font}`의 PNG+.yy 파일 확보 → (4) UndertaleModTool의 ImportGMS2FontData 스크립트로 data.win에 import 후 저장·테스트. 핵심: 폰트 크기를 원본과 일치시켜야 결과가 깔끔.

---

## 네이티브·리버싱

### Quake 2021 Remastered 메인메뉴 한글 출력
- URL: https://snowyegret.tistory.com/93
- 엔진: ImGUI. 도구: IDA Pro(정적 분석), 010 Editor(바이너리), CFF Explorer(PE 수정).
- 접근: 동적·정적 분석으로 폰트 아틀라스를 구성하는 ImGUI 초기화 함수 `sub_1401970C0` 식별. 문제는 문자 인식이 아니라 아틀라스에 한글 글리프 범위(KS1001+영문+기호)가 안 실리는 것.
- 절차: (1) Python으로 한글 텍스트의 유니크 코드포인트를 뽑아 ImGUI용 바이너리 글리프 레인지 생성 → (2) CFF Explorer로 실행권한 있는 `.patch` 섹션 추가, 코드케이브(`0x149F18236`) 확보 → (3) 5바이트 명령 4곳(`mov qword ptr [rsp+230h+advance_x], r14`)을 JMP로 치환해 케이브로 우회, 케이브에서 새 글리프 데이터 주소를 RAX에 적재.

### Quake II Enhanced 한글 출력
- URL: https://snowyegret.tistory.com/105
- 엔진: IMGUI. 핵심 원인: `AddFontFromMemoryTTF`에 글리프 레인지 인자가 null/0으로 전달돼 라틴 기본 문자만 아틀라스에 로드됨.
- 절차: (1) CFF Explorer로 실행권한 `.patch` 섹션 추가 → (2) 코드케이브(`1425C3850`)에 어셈블리 주입: 폰트 크기를 rax에 보존 → 한글 글리프 레인지 데이터를 rax에 적재 → 스택 조작으로 6번째 인자로 전달 → 레지스터 복구 후 다음 명령으로 JMP → (3) Python으로 원문에서 유니크 문자 추출·연속 유니코드 레인지 생성 후 올바른 오프셋에 패치. (/93과 같은 계열의 IMGUI 폰트 아틀라스 코드케이브 기법.)

### AI: The Somnium Files 한글화 분석
- URL: https://snowyegret.tistory.com/92
- 번들 내 Lua 바이트코드 복호 + 일본어 함수명 포함 컴파일 스크립트 수정. 도구: AssetStudio, UABEA, luac, unluac.
- 암호: 파일 5바이트 이후를 `(position & 0xff)` XOR로 복호. 문제: 디컴파일된 Lua에 일본어 식별자가 있어 표준 재컴파일(luac)이 실패.
- 해법(재컴파일 대신 디스어셈블/리어셈블): (1) 디컴파일로 텍스트 매핑 추출 → (2) 바이트코드 수준으로 디스어셈블 → (3) 상수(이스케이프된 유니코드)를 원문/번역으로 치환 → (4) 리어셈블. 재삽입 시 동일 XOR로 재암호화하고 유니티 TextAsset 구조(사이즈 헤더·패딩 정렬)에 맞춤.

### sailing era 한글화 분석
- URL: https://snowyegret.tistory.com/67
- 번들 앞 0x400바이트를 241자 키("EuCVe&D9…")로 XOR 암호화, 이후 압축(UnityEX로 해제). 텍스트는 번들 내 `table.bytes`에 길이접두 UTF-8 문자열+패딩 시퀀스로 존재. **외부 오프셋 테이블이 문자열을 참조**해, 텍스트 길이를 바꾸면 게임이 깨짐.
- 결론: 수동 번역은 바이트 길이 고정이 필요해 영→한이 어려움(디컴파일 소스 없이 오프셋 시스템 역공학은 포기). 실용안은 XUnity.AutoTranslator(기본 Papago, 딜레이 0.3~0.9초 설정)로 자동번역 후 번역 파일 수동 편집.

### Ghidra에 Gemini CLI 연결하기
- URL: https://snowyegret.tistory.com/102
- Ghidra 리버싱에 AI 보조를 붙이는 MCP 연동. 도구: GhidrAssistMCP(Ghidra 확장), Ghidra 11.4.2, JDK 21, Gemini-CLI.
- 절차: (1) File→Install Extensions로 GhidrAssistMCP 설치 → (2) Gemini-CLI에서 Preview Features 활성(Gemini 3 Pro) → (3) Gemini settings.json에 MCP 서버 `http://127.0.0.1:8080/mcp` 추가 → (4) Gemini-CLI 실행 후 GhidrAssistMCP 툴 접근 승인. AI로 바이너리 분석을 보조.
