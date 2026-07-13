# ED1 오프닝 작업 핸드오프

회사↔집 이어작업용 **살아있는 문서**. 세션 시작 시 이걸 먼저 읽고, 끝낼 때 "현재 상태"·"다음 할 일"을 갱신한다.
상세 여정은 [opening-font-devlog.md](opening-font-devlog.md), 메모리 `ed1-opening-render`.

마지막 갱신: 2026-07-13 (회사)

---

## 지금 어디까지 됐나

**오프닝 = 완료 ✅** (유저 확인: 전 50줄 정상 렌더, 인게임 검증 DuckStation/mednafen)

- **폰트**: PS1 BIOS 한자폰트(수정불가) 대신 **임베드 한글폰트**(Galmuri9, 행-마스크 압축 3966B)를
  PC0 후킹 디코더가 자유 RAM(`0x80080000`)에 전개. 렌더는 원본 그대로(base 리다이렉트만).
- **텍스트**: 정발판(`originals/kr/ED1/OPENING.EXE`, CP949 평문 0x5E07B~) 원문 우선으로 50줄 재작성.
  JP에만 있는 부분(다섯 나라 11~13행·몬스터 습격 확장 26~40행)은 정발 어투로 신규 번역.
  저주소 텍스트 영역(0x974~0xEEE, 1402B) 내 재packing — **여유 6B뿐**, 문안 수정 시 예산 확인 필수.
- **핵심 규명 3가지** (상세는 devlog):
  1. **줄 끝 0x0A(개행)가 필드 클리어를 발동** — 없으면 짧은 줄에 이전 줄 잔상이 딸림. enc()가 자동 부가.
  2. **전각 advance 4→3 패치**(폭측정 0x13370·표시 0x13750)로 간격 축소 + 줄당 한계 16→**21슬롯** 확대.
  3. **스크립트(0x145A0)는 주소 범위로 text/command 구분** — 줄을 고주소로 옮기면 검은화면(재배치 금지).
- **표기 규칙(유저 확정)**: 쉼표 뒤 공백 없음, 문장 끝 마침표 일관, 따옴표 사용 안 함(전각 슬롯 여백 과대).
  문안 변경은 반드시 사전 보고(메모리 `text-changes-need-approval`).
  **정발 표기에서 부득이 바꾼 것은 전부 [jeongbal-deviations.md](jeongbal-deviations.md)에 기록.**

## 빌드 & 테스트

```bash
cd games/ps1-eiyuu12
python3 tools/build.py                       # 베이스(대사·UI 등) → work/Eiyuu Densetsu (KR).bin
python3 tools/patch_opening_font.py          # 오프닝 폰트+텍스트 패치(제자리 갱신)
```

에뮬레이터(mednafen 포크+emucap MCP):

- 오프닝까지: 부팅 ~2900프레임 → `start` → 120프레임 → `circle`(ED1) → ~200프레임이면 내레이션.
- 정밀 캡처는 free-run 말고 **pause 후 step**(free-run은 프레임 점프). step은 240프레임 이하(초과 시 타임아웃).
- ⚠ **빌드 교체 후엔 reset이 아니라 프로세스 kill + launch** — mednafen이 디스크를 캐시해 reset은 구 이미지 유지.
- exec/read/write BP는 free-run에서 정지 안 함(로그만) → 검증은 디스어셈블+Python 시뮬 또는 write_memory 라이브 패치.
- BIOS: `~/.mednafen/firmware/scph5500.bin`. 종료: `pkill -9 -f "emucap/mednafen/47800/mednafen"`(자기 포트만).

## 다음 할 일 (우선순위)

1. `patch_opening_font.py`를 `build.py` 체인에 통합(현재 수동 2단계).
2. 오프닝 외 나머지 진행(HANDOFF 범위 밖 — 본편 대사 정렬 swap 검수 등, 메모리 `reinsert-status`).

## 핵심 주소·수치 (빠른 참조)

| 항목 | 값 |
|---|---|
| 디코더 스텁(PC0 훅) | `0x80025414`~ (파일 0x15C14), 23명령, setjmp(`0x800254A4`) 전 |
| 압축 폰트 소스 | 파일 `0x15CE0` → RAM `0x800254E0` (안전 상한 파일 0x16CC0) |
| 폰트 자유RAM | `0x80080000` (214글리프×30B) — base 리다이렉트 `0x8001BE84` |
| 내레이션 텍스트 영역 | 파일 `0x974~0xEEE` (RAM `0x80010174~0x800106EE`), 1402B, 50줄 재packing |
| 내레이션 포인터테이블 | 파일 `0x145A0~` (text_ptr 0x8001xxxx / command_ptr 0x80026Dxx — 주소 범위로 구분) |
| 렌더 폭측정 루프 | `0x800132D4`~ (전각 advance `0x80013370` — 3으로 패치) |
| 렌더 표시 루프 | `0x800133F4`~ (전각 advance `0x80013750` — 3으로 패치, 0x0A 핸들러 `0x8001366C`) |
| 줄당 한계 | **21전각슬롯** (필드 64유닛 ÷ advance 3) — 초과 시 앞뒤 잘림 |
| 원 PC0 | `0x80021D50` |

## MIPS 손인코딩 함정 (재발 방지)

**andi rs 필드**(v1↔t3 혼동으로 폰트 안뜨는 버그 겪음), **load-delay 슬롯**(lw 직후 sw면 +4밀림 → 사이에 addiu).
항상 디스어셈블+Python시뮬로 검증.
